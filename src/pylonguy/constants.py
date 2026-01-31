"""Application-wide constants"""

# Camera sensor limits
MAX_OFFSET_X = 4096
MAX_OFFSET_Y = 3072
MIN_ROI_WIDTH = 16
MIN_ROI_HEIGHT = 16

# Timing intervals
CAMERA_APPLY_TIMEOUT = 0.05  # seconds
FPS_UPDATE_INTERVAL_MS = 200
FPS_RESET_INTERVAL = 5.0  # seconds
STATS_UPDATE_INTERVAL = 0.2  # seconds
SIGNAL_TIMER_INTERVAL_MS = 100

# Threading
WRITER_QUEUE_SIZE = 10000
WRITER_THREAD_TIMEOUT = 60  # seconds
QUEUE_GET_TIMEOUT = 0.1  # seconds
LIMIT_CHECK_INTERVAL = 100  # frames

# UI geometry
SETTINGS_PANEL_WIDTH = 400
WINDOW_DEFAULT_GEOMETRY = (100, 100, 1400, 900)
LOG_MAX_HEIGHT = 150
CONTROLS_MAX_HEIGHT = 150

# Slider configuration
OFFSET_SLIDER_STEP = 16


class Theme:
    """UI color theme constants."""

    BG_BLACK = "#000"
    BG_DARK = "#1a1a1a"
    BG_DARKER = "#222"
    BG_MEDIUM = "#2a2a2a"
    BG_CONTROL = "#3c3c3c"
    BG_CONTROL_HOVER = "#4c4c4c"
    BG_CONTROL_PRESSED = "#2c2c2c"

    LABEL_BG = "#444"
    LABEL_TEXT = "#bbb"
    VALUE_TEXT = "#0f0"
    VALUE_TEXT_RECORDING = "#f00"

    ACCENT = "#0af"
    SLIDER_GROOVE = "#555"

    TEXT_WHITE = "white"
    TEXT_YELLOW = "#ff0"
