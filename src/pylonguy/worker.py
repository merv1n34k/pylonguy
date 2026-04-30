"""Worker module - frame and waterfall writer with post-processing"""

import shutil
import subprocess
import tempfile
import numpy as np
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Thread, Event
import logging
import time

from .constants import WRITER_QUEUE_SIZE, WRITER_THREAD_TIMEOUT, QUEUE_GET_TIMEOUT

log = logging.getLogger("pylonguy")


class VideoWorker:
    """Frame writer that dumps frames to temp dir then creates video"""

    def __init__(self, output_dir: str, prefix: str, width: int, height: int, fps: float):
        self.output_dir = Path(output_dir)
        self.prefix = prefix
        self.width = width
        self.height = height
        self.fps = fps

        # Temp dir created on start(), cleaned up after ffmpeg
        self.frames_dir = None

        # Simple queue for frame writing
        self.queue = Queue(maxsize=WRITER_QUEUE_SIZE)
        self.thread = None
        self._stop_event = Event()
        self.frame_count = 0

    def start(self) -> bool:
        """Start frame writer thread"""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.frames_dir = Path(tempfile.mkdtemp(prefix="pylonguy_", dir=self.output_dir))

            self._stop_event.clear()
            self.frame_count = 0

            # Start writer thread
            self.thread = Thread(target=self._writer_thread, daemon=True)
            self.thread.start()

            log.info(f"Frame writer started: {self.frames_dir}")
            return True

        except Exception as e:
            log.error(f"Failed to start: {e}")
            return False

    def write(self, frame: np.ndarray) -> bool:
        """Add frame to write queue"""
        if self._stop_event.is_set():
            return False

        # Drop oldest if full (never block camera)
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except Empty:
                pass

        try:
            self.queue.put_nowait((frame, self.frame_count))
            self.frame_count += 1
            return True
        except Full:
            return False

    def stop(self) -> str:
        """Stop writing and create video"""
        self._stop_event.set()

        # Wait for queue to empty
        if self.thread:
            remaining = self.queue.qsize()
            if remaining > 0:
                log.info(f"Writing {remaining} queued frames...")
            self.thread.join(timeout=WRITER_THREAD_TIMEOUT)
            if self.thread.is_alive():
                log.warning("Writer thread did not finish in time")

        log.info(f"Wrote {self.frame_count} frames")

        # Create video from frames
        video_path = self._make_video()

        return video_path

    def _writer_thread(self):
        """Write frames to disk as fast as possible"""
        while not self._stop_event.is_set() or not self.queue.empty():
            try:
                frame, idx = self.queue.get(timeout=QUEUE_GET_TIMEOUT)

                # Convert 16-bit to 8-bit if needed
                if frame.dtype == np.uint16:
                    frame = (frame >> 8).astype(np.uint8)

                # Write raw bytes
                path = self.frames_dir / f"{idx:08d}.raw"
                with open(path, "wb") as f:
                    f.write(frame.tobytes())

            except Empty:
                continue
            except Exception as e:
                log.debug(f"Write error: {e}")

    def _make_video(self) -> str:
        """Create video from raw frames, clean up temp dir after"""
        frames = sorted(self.frames_dir.glob("*.raw"))
        if not frames:
            log.error("No frames to convert")
            shutil.rmtree(self.frames_dir, ignore_errors=True)
            return ""

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        video_path = self.output_dir / f"{self.prefix}_{timestamp}.avi"

        try:
            log.info(
                f"Creating video from {len(frames)} frames at {self.fps} fps..."
            )

            input_pattern = str(self.frames_dir / "%08d.raw")

            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "image2",
                "-framerate",
                str(self.fps),
                "-pixel_format",
                "gray",
                "-video_size",
                f"{self.width}x{self.height}",
                "-i",
                input_pattern,
                "-c:v",
                "rawvideo",
                "-pix_fmt",
                "gray",
                str(video_path),
            ]

            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Cleanup thread: wait for ffmpeg, then handle temp dir
            cleanup = Thread(
                target=self._cleanup_after_encode,
                args=(proc, self.frames_dir, video_path),
                daemon=True,
            )
            cleanup.start()

            log.info(f"Video processing started: {video_path}")
            return str(video_path)

        except Exception as e:
            log.error(f"Failed to start ffmpeg: {e}")
            return ""

    @staticmethod
    def _cleanup_after_encode(proc, frames_dir, video_path):
        """Wait for ffmpeg and clean up temp frames"""
        video_path = Path(video_path)
        try:
            rc = proc.wait()
            if rc == 0:
                shutil.rmtree(frames_dir, ignore_errors=True)
                log.info(f"Video ready: {video_path}")
            else:
                # FFmpeg failed — keep raw frames, remove broken video
                if video_path.exists():
                    video_path.unlink()
                raw_dir = video_path.parent / f"raw_{video_path.stem}"
                frames_dir.rename(raw_dir)
                log.error(f"FFmpeg failed (exit {rc}), raw frames kept: {raw_dir}")
        except Exception as e:
            log.error(f"Cleanup error: {e}")


class WaterfallWorker:
    """Waterfall writer that saves lines to .wtf file with embedded header"""

    def __init__(
        self,
        output_path: str,
        width: int,
        buffer_size: int = 1000,
    ):
        self.output_path = Path(output_path)
        self.width = width
        self.buffer_size = buffer_size

        # Buffer for batched writes
        self.buffer = []
        self.line_count = 0
        self.file = None
        self.active = False

    def start(self) -> bool:
        """Start waterfall writer"""
        try:
            # Create output directory
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            # Open file in write binary mode
            self.file = open(self.output_path, "wb")

            # Write header: 'WTF1' + width (2 bytes)
            header = b"WTF1" + self.width.to_bytes(2, "little")
            self.file.write(header)

            self.active = True
            self.line_count = 0

            log.info(f"Waterfall writer started: {self.output_path}")
            return True

        except Exception as e:
            log.error(f"Failed to start waterfall writer: {e}")
            return False

    def write(self, frame: np.ndarray) -> bool:
        """Add frame (will be collapsed to line) to waterfall"""
        if not self.active or self.file is None:
            return False

        try:
            # Collapse frame to 1×W profile using median
            if len(frame.shape) > 2:
                frame = np.mean(frame, axis=2)

            # Add to buffer
            self.buffer.append(frame)
            self.line_count += 1

            # Flush buffer if full
            if len(self.buffer) >= self.buffer_size:
                self._flush_buffer()

            return True

        except Exception as e:
            log.debug(f"Waterfall write error: {e}")
            return False

    def _flush_buffer(self):
        """Write buffered lines to file"""
        if not self.buffer or not self.file:
            return

        try:
            # Stack lines and write as contiguous block
            block = np.vstack(self.buffer)
            self.file.write(block.tobytes())
            self.file.flush()  # Ensure data is written

            log.debug(f"Flushed {len(self.buffer)} lines to waterfall")
            self.buffer = []

        except Exception as e:
            log.error(f"Failed to flush waterfall buffer: {e}")

    def stop(self) -> str:
        """Stop writing and close file"""
        self.active = False

        try:
            # Flush remaining buffer
            if self.buffer:
                self._flush_buffer()
        finally:
            # Always close file
            if self.file:
                try:
                    self.file.close()
                except Exception as e:
                    log.warning(f"Error closing waterfall file: {e}")
                self.file = None

        log.info(
            f"Waterfall saved: {self.output_path} ({self.line_count} lines, width={self.width})"
        )

        return str(self.output_path)
