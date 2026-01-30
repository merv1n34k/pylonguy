# PylonGUY

Your best friend for high-performance camera control for Basler cameras with high-speed recording capabilities and simple GUI.

![preview](https://raw.githubusercontent.com/merv1n34k/pylonguy/refs/heads/master/docs/preview.png)

## Features

- Real-time preview with adaptive grab strategy (lag-free at any FPS)
- Camera configuration with automatic adjustment to camera capabilities
- High-speed frame capture to raw frames with FFmpeg post-processing
- Configurable playback rate for slow-motion video
- Interactive ROI selection and offset controls
- Preset configurations (Default, HighSpeed, FullFrame, Microfluidics)
- Auto-apply presets on camera connection
- Waterfall mode for line-scan recording

## Installation

### From PyPI

```bash
pip install pylonguy
```

### From source

```bash
git clone https://github.com/merv1n34k/pylonguy.git
cd pylonguy
pip install -e .
```

### Requirements

- Python 3.12+
- ffmpeg in PATH (for video processing)
- Basler Pylon SDK (for camera communication)

#### Installing ffmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

#### Installing Pylon SDK

Download from [Basler website](https://www.baslerweb.com/pylon). See [pypylon known issues](https://github.com/basler/pypylon#known-issues) for platform-specific notes.

## Usage

```bash
# Run the application
pylonguy

# Or with uv
uv run pylonguy
```

## How it works

The application separates capture from video encoding for maximum performance:

1. **Capture Phase**: Frames stream from camera → memory buffer → raw files on disk
2. **Processing Phase**: After recording stops, FFmpeg assembles raw frames into video

This allows you to specify any desired playback frame rate, e.g.:

- Camera captures at 1000 fps
- Video plays back at 24 fps
- Result: 1 second of capture = 41.7 seconds of slow-motion video

## Waterfall Mode

Record single lines instead of full frames for:
- Maximum frame rates (minimal data transfer)
- Line-scan camera emulation
- Monitoring flow in microfluidic channels

Output format: `.wtf` (waterfall) files, convertible to PNG:

```bash
python -m pylonguy.wtf2png recording.wtf
```

## License

Distributed under the MIT License. See `LICENSE` for more information.
