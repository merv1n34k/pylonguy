# PylonGUY

Your best friend for high-performance camera control for Basler (and GenICam) cameras with high-speed recording capabilities and simple GUI.

![preview](https://raw.githubusercontent.com/merv1n34k/pylonguy/refs/heads/master/docs/preview.png)

## Features

- Real-time preview with FPS monitoring
- Clear camera configuration with automatic adjustments to camera capabilities
- High-speed frame capture to raw frames
- Post-processing recording with configurable playback rate
- Interactive ROI selection on preview
- Preset configurations for different capture scenarios (quality, speed,
  balanced, custom)
- Waterfall recording (see Waterfall)

## Installation

It is recommended to use [uv](https://docs.astral.sh/uv/):

```bash
No prior actions needed (see Usage)
```

Alternatively, one can do:

```bash
python -m venv .venv && source .venv/bin/activate

python -m pip install -r requirements.txt
```

You also need to have `ffmpeg` at `PATH` for video processing. For macOS users, you can install it with `brew`:

```bash
brew install ffmpeg
```

Installing [pylon](https://www.baslerweb.com/pylon) might be required. See [known issues](https://github.com/basler/pypylon#known-issues) for further details.

## Usage

```bash
# To run with uv
uv run main.py

# Other users
source .venv/bin/activate # if not activated
python main.py
```

## How it works

The application separates capture from video encoding for maximum performance:

1. **Capture Phase**: Frames stream from camera → memory buffer → raw files on disk
2. **Processing Phase**: After recording stops, FFmpeg assembles raw frames into video

This allows you to specify any desired frame rate of a final video, e.g.:

- Camera captures at 1000 fps
- Video plays back at 24 fps
- Result: 1 second of capture = 41.7 seconds of slow-motion video

## Waterfall

Another interesting feature lets you record single line instead of ROI capture,
called `waterfall`. Use this for:
- Maximum camera's frame rate
- Line-scanners
- Recording all lines in custom `.wtf` format, process to frames with `wtf2png.py`
script

## License

Distributed under the MIT License. See `LICENSE` for more information.
