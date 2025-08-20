"""Minimal video writer using FFmpeg"""
import subprocess
import os
import numpy as np

class VideoWriter:
    def __init__(self, path: str, width: int, height: int, fps: float = 24.0):
        self.path = path
        self.width = width
        self.height = height
        self.fps = fps
        self.process = None

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def start(self) -> bool:
        """Start FFmpeg process"""
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-pix_fmt", "gray",  # Will be grayscale for most Basler cameras
                "-s", f"{self.width}x{self.height}",
                "-r", str(self.fps),
                "-i", "-",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-pix_fmt", "yuv420p",  # Output format for compatibility
                self.path
            ]

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
            return True
        except:
            return False

    def write(self, frame) -> bool:
        """Write frame to video"""
        if self.process and self.process.stdin:
            try:
                # Convert 16-bit to 8-bit if needed for FFmpeg
                if frame.dtype == np.uint16:
                    frame = (frame >> 8).astype(np.uint8)

                self.process.stdin.write(frame.tobytes())
                return True
            except:
                return False
        return False

    def stop(self):
        """Stop recording"""
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
