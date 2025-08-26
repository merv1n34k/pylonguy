# PylonGUY

Your friend for high-performance camera control GUI for Basler cameras with high-speed recording capabilities.

## Features

- Real-time preview with FPS monitoring
- High-speed frame capture to raw files
- Post-processing to video with configurable playback rate
- ROI selection on preview
- Preset configurations for different capture scenarios (quality, speed,
  balanced)
- Optional preview disable during recording for maximum throughput

## Installation

```bash
# Install Basler Pylon SDK first from baslerweb.com
pip install pypylon numpy PyQt5

# Ensure FFmpeg is installed for video generation
python app.py
```

## Usage

The application separates capture from video encoding for maximum performance:

1. **Capture Phase**: Frames stream from camera → memory buffer → raw files on disk
2. **Processing Phase**: After recording stops, FFmpeg assembles raw frames into video

This allows you to specify any desired frame rate of a final video, e.g.:

- Camera captures at 1000 fps
- Video plays back at 24 fps
- Result: 1 second of capture = 41.7 seconds of slow-motion video

## License

Distributed under the MIT License. See `LICENSE` for more information.
