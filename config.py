from dataclasses import dataclass
from pathlib import Path
import time
from typing import Optional

@dataclass
class Config:
    # Paths
    images_dir: str = "./output/images"
    videos_dir: str = "./output/videos"

    # Camera settings
    width: int = 1280
    height: int = 720
    offset_x: int = 0
    offset_y: int = 0
    exposure: float = 10000.0  # microseconds
    gain: float = 0.0
    sensor_readout_mode: str = "Normal"  # Normal or Fast
    acquisition_framerate_enable: bool = False
    acquisition_framerate: float = 30.0

    # Video settings
    video_fps: float = 24.0

    # Recording limits (optional)
    record_limit_frames: Optional[int] = None  # Stop after N frames
    record_limit_seconds: Optional[float] = None  # Stop after T seconds

    def __post_init__(self):
        # Create directories if they don't exist
        Path(self.images_dir).mkdir(parents=True, exist_ok=True)
        Path(self.videos_dir).mkdir(parents=True, exist_ok=True)

    def get_image_path(self) -> str:
        """Generate timestamped image path"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return str(Path(self.images_dir) / f"capture_{timestamp}.png")

    def get_video_path(self) -> str:
        """Generate timestamped video path"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return str(Path(self.videos_dir) / f"recording_{timestamp}.mp4")
