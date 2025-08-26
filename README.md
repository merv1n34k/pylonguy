# PylonGUY

Your friend for high-performance camera control GUI for Basler cameras with high-speed recording capabilities.

## Features

- Real-time preview with FPS monitoring
- Clear camera configuration with adaptation for camera capabilities
- High-speed frame capture to raw files
- Post-processing to video with configurable playback rate
- Interactive ROI selection on preview
- Preset configurations for different capture scenarios (quality, speed,
  balanced)

## Installation

```bash
# It is recommended to use virutal environment (via venv or any other way)
python -m venv pylonguy && source pylonguy/bin/activate

pip install -r requirements.txt
```

You also need to have `ffmpeg` at `PATH` for video processing. For macOS users, you can install it with `brew`:

```bash
brew install ffmpeg
```

Installing [pylon](https://www.baslerweb.com/pylon) might be required. See [known issues](https://github.com/basler/pypylon#known-issues) for further details.

## Usage

```bash
# To run the app
python app.py
```

The application separates capture from video encoding for maximum performance:

1. **Capture Phase**: Frames stream from camera → memory buffer → raw files on disk
2. **Processing Phase**: After recording stops, FFmpeg assembles raw frames into video

This allows you to specify any desired frame rate of a final video, e.g.:

- Camera captures at 1000 fps
- Video plays back at 24 fps
- Result: 1 second of capture = 41.7 seconds of slow-motion video

## License

Distributed under the MIT License. See `LICENSE` for more information.
