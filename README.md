# PylonGUY

A clean, simple GUI for Basler cameras using pypylon SDK and PyQt5.

## Features

- **Live Preview** - Real-time camera feed with toggle control
- **Image Capture** - Save single frames as PNG images
- **Video Recording** - Record video with FFmpeg (H.264/MP4)
- **Area selection** - Select area on the preview window to see approximate area
- **Live Log** - Real-time status and error messages
- **Fine FPS control** - set the number of frame rate for capturing and recording individually, perfect for slow motion capturing.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install FFmpeg (required for video recording):
   - Windows: Download from https://ffmpeg.org
   - Linux: `sudo apt-get install ffmpeg`
   - macOS: `brew install ffmpeg`

3. Run the application:
```bash
python app.py
```

## Usage

1. **Connect Camera** - Click "Connect" in settings to connect to the first available Basler camera
2. **Configure** - Adjust camera settings (dimensions, exposure, gain) and click "Apply Settings"
3. **Live Preview** - Toggle "Start Live" to see real-time camera feed
4. **Capture** - Click "Capture" to save current frame as image
5. **Record** - Click "Record" to start video recording, click again to stop

## Time-Stretch Recording

The video fps setting controls playback speed, not capture rate:
- Camera captures at native speed (e.g., 4000 fps)
- Video plays at configured fps (e.g., 24 fps)
- Result: 1 second of capture = 166.7 seconds of video (slow motion)

## File Structure

- `app.py` - Main app logic
- `gui.py` - PyQt5 user interface
- `camera.py` - Simple camera wrapper
- `video_writer.py` - FFmpeg video recording
- `config.py` - Configuration management

## License

Distributed under the MIT License. See `LICENSE` for more information.

