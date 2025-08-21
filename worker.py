"""Worker module - handles video writing and frame dumping"""
import subprocess
import numpy as np
from pathlib import Path
from queue import Queue, Full
from threading import Thread
import shutil
import logging
import time

log = logging.getLogger("pylonguy")

class VideoWriter:
    """Real-time video writer using FFmpeg"""

    def __init__(self, path: str, width: int, height: int, fps: float):
        self.path = path
        self.width = width
        self.height = height
        self.fps = fps
        self.process = None
        self.queue = Queue(maxsize=1000)
        self.thread = None
        self.active = False

    def start(self) -> bool:
        """Start FFmpeg process and writer thread"""
        try:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

            cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-pix_fmt", "gray",
                "-s", f"{self.width}x{self.height}",
                "-r", str(self.fps),
                "-i", "-",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                self.path
            ]

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                bufsize=10**7
            )

            self.active = True
            self.thread = Thread(target=self._writer_thread, daemon=True)
            self.thread.start()

            log.info(f"Video writer started: {self.path}")
            return True
        except Exception as e:
            log.error(f"Failed to start video writer: {e}")
            return False

    def write(self, frame: np.ndarray) -> bool:
        """Queue frame for writing"""
        if not self.active:
            return False

        try:
            self.queue.put_nowait(frame.copy())
            return True
        except Full:
            return False  # Drop frame silently

    def stop(self):
        """Stop video writer and flush queue"""
        self.active = False

        if self.thread:
            self.thread.join(timeout=10)

        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                self.process.wait(timeout=5)
            except:
                self.process.terminate()
            self.process = None

        log.info(f"Video saved: {self.path}")

    def _writer_thread(self):
        """Background thread for writing frames"""
        while self.active or not self.queue.empty():
            try:
                frame = self.queue.get(timeout=0.1)
                if self.process and self.process.stdin:
                    # Convert 16-bit to 8-bit if needed
                    if frame.dtype == np.uint16:
                        frame = (frame >> 8).astype(np.uint8)
                    self.process.stdin.write(frame.tobytes())
            except:
                continue


class FrameDumper:
    """High-speed frame dumper for post-processing"""

    def __init__(self, output_dir: str, width: int, height: int, fps: float, keep_frames: bool = False):
        self.output_dir = Path(output_dir)
        self.width = width
        self.height = height
        self.fps = fps
        self.keep_frames = keep_frames  # Option to keep frame files after conversion
        self.queue = Queue(maxsize=500)
        self.thread = None
        self.active = False
        self.frame_count = 0
        self.frames_written = 0

    def start(self) -> bool:
        """Start frame dumping"""
        try:
            # Create or clean directory
            if self.output_dir.exists():
                # Clear existing frames
                existing_frames = list(self.output_dir.glob("frame_*.npy"))
                if existing_frames:
                    log.warning(f"Removing {len(existing_frames)} existing frames in {self.output_dir}")
                    for f in existing_frames:
                        f.unlink()
            else:
                self.output_dir.mkdir(parents=True, exist_ok=True)

            self.active = True
            self.frame_count = 0
            self.frames_written = 0
            self.thread = Thread(target=self._dumper_thread, daemon=True)
            self.thread.start()

            log.info(f"Frame dumper started: {self.output_dir}")
            return True
        except Exception as e:
            log.error(f"Failed to start frame dumper: {e}")
            return False

    def write(self, frame: np.ndarray) -> bool:
        """Queue frame for dumping"""
        if not self.active:
            return False

        try:
            self.queue.put_nowait((frame.copy(), self.frame_count))
            self.frame_count += 1
            return True
        except Full:
            return False  # Drop frame silently

    def stop(self) -> str:
        """Stop dumping and convert to video"""
        self.active = False

        if self.thread:
            # Wait for all frames to be written
            queue_size = self.queue.qsize()
            if queue_size > 0:
                log.info(f"Waiting for {queue_size} queued frames to be written...")

            # Dynamic timeout based on queue size (10ms per frame, min 10s, max 120s)
            timeout = max(10, min(120, queue_size * 0.01))
            self.thread.join(timeout=timeout)

            if self.thread.is_alive():
                log.warning(f"Writer thread did not finish in {timeout}s, some frames may be lost")

        log.info(f"Dumped {self.frames_written} frames (queued {self.frame_count})")

        # Only convert if we have frames
        if self.frames_written > 0:
            video_path = self._convert_to_video()

            # Optionally clean up frame directory
            if not self.keep_frames and video_path:
                self._cleanup_frames()
            elif self.keep_frames:
                log.info(f"Frame files kept in: {self.output_dir}")

            return video_path
        else:
            log.error("No frames were written to disk")
            # Clean up empty directory
            if self.output_dir.exists() and not any(self.output_dir.iterdir()):
                self.output_dir.rmdir()
            return ""

    def _cleanup_frames(self):
        """Remove frame directory and all its contents"""
        try:
            if self.output_dir.exists():
                shutil.rmtree(self.output_dir)
                log.info(f"Removed frame directory: {self.output_dir}")
        except Exception as e:
            log.warning(f"Could not remove frame directory: {e}")

    def _dumper_thread(self):
        """Background thread for dumping frames"""
        while self.active or not self.queue.empty():
            try:
                frame, idx = self.queue.get(timeout=0.1)
                path = self.output_dir / f"frame_{idx:06d}.npy"
                np.save(path, frame)
                self.frames_written += 1
            except:
                continue

    def _convert_to_video(self) -> str:
        """Convert dumped frames to video"""
        video_path = self.output_dir.parent / f"video_{time.strftime('%Y%m%d_%H%M%S')}.mp4"

        try:
            log.info("Converting frames to video...")

            # Get all frame files and sort them
            frame_files = sorted(self.output_dir.glob("frame_*.npy"))

            if not frame_files:
                log.error("No frame files found for conversion")
                return ""

            log.info(f"Found {len(frame_files)} frame files")

            # Determine the actual frame range from filenames
            frame_numbers = []
            for f in frame_files:
                try:
                    num = int(f.stem.split('_')[1])
                    frame_numbers.append(num)
                except:
                    pass

            if not frame_numbers:
                log.error("No valid frame files found")
                return ""

            min_frame = min(frame_numbers)
            max_frame = max(frame_numbers)
            total_frames = max_frame - min_frame + 1

            log.info(f"Frame range: {min_frame} to {max_frame} ({total_frames} total, {len(frame_files)} available)")

            # Start FFmpeg process
            cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-pix_fmt", "gray",
                "-s", f"{self.width}x{self.height}",
                "-r", str(self.fps),
                "-i", "-",
                "-c:v", "libx264",
                "-preset", "slow",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                str(video_path)
            ]

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )

            # Feed frames sequentially, handling missing frames
            frames_processed = 0
            missing_frames = []
            last_good_frame = None

            for i in range(min_frame, max_frame + 1):
                frame_file = self.output_dir / f"frame_{i:06d}.npy"

                if frame_file.exists():
                    try:
                        frame = np.load(frame_file)
                        if frame.dtype == np.uint16:
                            frame = (frame >> 8).astype(np.uint8)

                        process.stdin.write(frame.tobytes())
                        last_good_frame = frame
                        frames_processed += 1

                        if frames_processed % 100 == 0:
                            log.info(f"Processing frame {frames_processed}/{total_frames}")
                    except Exception as e:
                        log.warning(f"Failed to load frame {i}: {e}")
                        missing_frames.append(i)
                        # Use last good frame or black frame
                        if last_good_frame is not None:
                            process.stdin.write(last_good_frame.tobytes())
                        else:
                            black_frame = np.zeros((self.height, self.width), dtype=np.uint8)
                            process.stdin.write(black_frame.tobytes())
                else:
                    missing_frames.append(i)
                    # Use last good frame or black frame for missing frame
                    if last_good_frame is not None:
                        process.stdin.write(last_good_frame.tobytes())
                    else:
                        black_frame = np.zeros((self.height, self.width), dtype=np.uint8)
                        process.stdin.write(black_frame.tobytes())

            process.stdin.close()
            result = process.wait(timeout=30)

            if missing_frames:
                log.warning(f"Missing {len(missing_frames)} frames during conversion (filled with last good frame)")

            if result == 0:
                log.info(f"Video created successfully: {video_path} ({frames_processed}/{total_frames} frames)")
                return str(video_path)
            else:
                log.error(f"FFmpeg returned error code: {result}")
                return ""

        except Exception as e:
            log.error(f"Failed to convert frames: {e}")
            return ""
