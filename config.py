"""Simple configuration"""
import time
from pathlib import Path

class Config:
    def __init__(self):
        # ROI
        self.width = 1280
        self.height = 720
        self.offset_x = 0
        self.offset_y = 0

        # Acquisition
        self.exposure = 10000.0  # microseconds
        self.gain = 0.0

        # Video
        self.video_fps = 24.0

        # Paths
        self.output_dir = Path("./output")
        self.output_dir.mkdir(exist_ok=True)

    def get_image_path(self):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return str(self.output_dir / f"img_{timestamp}.png")

    def get_video_path(self):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return str(self.output_dir / f"vid_{timestamp}.mp4")
