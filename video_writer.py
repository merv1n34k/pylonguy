"""Optimized video writer with buffering for high-speed recording"""
import subprocess
import os
import numpy as np
from queue import Queue
from threading import Thread
import logging

log = logging.getLogger("pylonguy")

class VideoWriter:
    def __init__(self, path: str, width: int, height: int, fps: float = 24.0):
        self.path = path
        self.width = width
        self.height = height
        self.fps = fps
        self.process = None
        self.write_queue = Queue(maxsize=1000)  # Buffer up to 1000 frames
        self.writer_thread = None
        self.writing = False

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def _writer_worker(self):
        """Background thread that writes frames from queue to FFmpeg"""
        while self.writing or not self.write_queue.empty():
            try:
                frame = self.write_queue.get(timeout=0.1)
                if self.process and self.process.stdin:
                    # Convert 16-bit to 8-bit if needed
                    if frame.dtype == np.uint16:
                        frame = (frame >> 8).astype(np.uint8)

                    self.process.stdin.write(frame.tobytes())
            except:
                continue

    def start(self) -> bool:
        """Start FFmpeg process and writer thread"""
        try:
            # Use optimized FFmpeg settings for high-speed recording
            cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-pix_fmt", "gray",
                "-s", f"{self.width}x{self.height}",
                "-r", str(self.fps),
                "-i", "-",
                "-c:v", "libx264",
                "-preset", "ultrafast",  # Use ultrafast for high-speed recording
                "-tune", "fastdecode",   # Optimize for fast decoding
                "-crf", "18",           # Lower CRF for better quality
                "-pix_fmt", "yuv420p",
                self.path
            ]

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                bufsize=10**8  # Large buffer for pipe
            )

            # Start writer thread
            self.writing = True
            self.writer_thread = Thread(target=self._writer_worker)
            self.writer_thread.start()

            return True
        except Exception as e:
            log.error(f"Failed to start video writer: {e}")
            return False

    def write(self, frame) -> bool:
        """Add frame to write queue"""
        if self.writing:
            try:
                # Non-blocking put - drop frame if queue is full
                self.write_queue.put_nowait(frame.copy())  # Copy needed here
                return True
            except:
                log.warning("Frame buffer full, dropping frame")
                return False
        return False

    def stop(self):
        """Stop recording and wait for all frames to be written"""
        self.writing = False

        if self.writer_thread:
            log.info(f"Flushing {self.write_queue.qsize()} buffered frames...")
            self.writer_thread.join(timeout=30)  # Wait up to 30s for buffer to flush

        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.terminate()
                except:
                    pass
            self.process = None
