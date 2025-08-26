"""Worker module - simple frame writer with post-processing"""
import subprocess
import numpy as np
import shutil
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
import logging
import time

log = logging.getLogger("pylonguy")


class VideoWorker:
    """Simple frame writer that dumps frames then creates video"""

    def __init__(self, frames_dir: str, width: int, height: int, fps: float, keep_frames: bool = False):
        # Frames directory path (full path passed from app.py)
        self.frames_dir = Path(frames_dir)
        self.width = width
        self.height = height
        self.fps = fps
        self.keep_frames = keep_frames

        # Simple queue for frame writing
        self.queue = Queue(maxsize=10000)
        self.thread = None
        self.active = False
        self.frame_count = 0

    def start(self) -> bool:
        """Start frame writer thread"""
        try:
            # Create frames directory
            if self.frames_dir.exists():
                shutil.rmtree(self.frames_dir)
            self.frames_dir.mkdir(parents=True, exist_ok=True)

            self.active = True
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
        if not self.active:
            return False

        # Drop oldest if full (never block camera)
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except:
                pass

        try:
            self.queue.put_nowait((frame, self.frame_count))
            self.frame_count += 1
            return True
        except:
            return False

    def stop(self) -> str:
        """Stop writing and create video"""
        self.active = False

        # Wait for queue to empty
        if self.thread:
            remaining = self.queue.qsize()
            if remaining > 0:
                log.info(f"Writing {remaining} queued frames...")
            self.thread.join(timeout=60)

        log.info(f"Wrote {self.frame_count} frames")

        # Create video from frames
        video_path = self._make_video()

        # Clean up frames if not keeping
        if not self.keep_frames and video_path:
            shutil.rmtree(self.frames_dir)
            log.info(f"Removed frame directory: {self.frames_dir}")
        elif self.keep_frames:
            log.info(f"Frame files kept in: {self.frames_dir}")

        return video_path

    def _writer_thread(self):
        """Write frames to disk as fast as possible"""
        while self.active or not self.queue.empty():
            try:
                frame, idx = self.queue.get(timeout=0.1)

                # Convert 16-bit to 8-bit if needed
                if frame.dtype == np.uint16:
                    frame = (frame >> 8).astype(np.uint8)

                # Write raw bytes
                path = self.frames_dir / f"{idx:08d}.raw"
                with open(path, 'wb') as f:
                    f.write(frame.tobytes())

            except Empty:
                continue
            except Exception as e:
                log.debug(f"Write error: {e}")

    def _make_video(self) -> str:
        """Create video from raw frames"""
        # Get frame files to check if any exist
        frames = sorted(self.frames_dir.glob("*.raw"))
        if not frames:
            log.error("No frames to convert")
            return ""

        # Video output path (in parent directory of frames)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        video_path = self.frames_dir.parent / f"vid_{timestamp}.avi"

        try:
            log.info(f"Creating video from {len(frames)} frames at {self.fps} fps...")

            # Use pattern matching to read all numbered raw files
            input_pattern = str(self.frames_dir / "%08d.raw")
            
            # FFmpeg command using image2 demuxer for raw video frames
            cmd = [
                "ffmpeg", "-y",
                "-f", "image2",
                "-framerate", str(self.fps),
                "-pixel_format", "gray",
                "-video_size", f"{self.width}x{self.height}",
                "-i", input_pattern,
                "-c:v", "rawvideo",  # Lossless raw video in AVI container
                "-pix_fmt", "gray",
                str(video_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300
            )

            if result.returncode == 0:
                size_mb = video_path.stat().st_size / (1024 * 1024)
                log.info(f"Video created: {video_path} ({size_mb:.1f} MB)")
                return str(video_path)
            else:
                log.error(f"FFmpeg failed: {result.stderr.decode()}")
                return ""

        except subprocess.TimeoutExpired:
            log.error("FFmpeg timed out after 5 minutes")
            return ""
        except Exception as e:
            log.error(f"Video creation failed: {e}")
            return ""
