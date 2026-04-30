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
    """UI color theme constants — droplegen palette."""

    # Backgrounds — dark charcoal
    BG_BLACK = "#000"
    BG_DARK = "#1a1a1a"
    BG_DARKER = "#1a1a1a"
    BG_MEDIUM = "#2b2b2b"
    BG_CONTROL = "#2b2b2b"
    BG_CONTROL_HOVER = "#353535"
    BG_CONTROL_PRESSED = "#404040"

    # Status bar labels
    LABEL_BG = "#2b2b2b"
    LABEL_TEXT = "#888888"
    VALUE_TEXT = "#2ecc71"
    VALUE_TEXT_RECORDING = "#e74c3c"

    # Accent — blue
    ACCENT = "#3498db"
    ACCENT_HOVER = "#2980b9"
    SLIDER_GROOVE = "#444444"

    # Text
    TEXT_WHITE = "#d4d4d4"
    TEXT_YELLOW = "#f39c12"
    BORDER_COOL = "#333333"

    # Semantic status colors
    STATUS_GREEN = "#2ecc71"
    STATUS_GREEN_DARK = "#27ae60"
    STATUS_RED = "#e74c3c"
    STATUS_RED_DARK = "#c0392b"
    STATUS_ORANGE = "#f39c12"
    STATUS_BLUE = "#3498db"

    # Input field styling
    INPUT_BG = "#2b2b2b"
    INPUT_BORDER = "#333333"
    INPUT_BORDER_HOVER = "#444444"
    INPUT_BORDER_FOCUS = "#3498db"

    # Disabled state
    DISABLED_BG = "#222222"
    DISABLED_TEXT = "#555555"
    DISABLED_BORDER = "#2a2a2a"


GLOBAL_QSS = f"""
    /* Base widget */
    QWidget {{
        background: {Theme.BG_DARK};
        color: {Theme.TEXT_WHITE};
        font-size: 12px;
    }}

    /* Labels */
    QLabel {{
        background: transparent;
        color: {Theme.TEXT_WHITE};
        padding: 1px;
    }}

    /* Line edits */
    QLineEdit {{
        background: {Theme.INPUT_BG};
        color: {Theme.TEXT_WHITE};
        border: 1px solid {Theme.INPUT_BORDER};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QLineEdit:hover {{
        border-color: {Theme.INPUT_BORDER_HOVER};
    }}
    QLineEdit:focus {{
        border-color: {Theme.INPUT_BORDER_FOCUS};
    }}
    QLineEdit:disabled {{
        background: {Theme.DISABLED_BG};
        color: {Theme.DISABLED_TEXT};
        border-color: {Theme.DISABLED_BORDER};
    }}

    /* Push buttons */
    QPushButton {{
        background: {Theme.BG_CONTROL};
        color: {Theme.TEXT_WHITE};
        border: 1px solid {Theme.INPUT_BORDER};
        border-radius: 4px;
        padding: 6px 14px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background: {Theme.BG_CONTROL_HOVER};
        border-color: {Theme.INPUT_BORDER_HOVER};
    }}
    QPushButton:pressed {{
        background: {Theme.BG_CONTROL_PRESSED};
    }}
    QPushButton:disabled {{
        background: {Theme.DISABLED_BG};
        color: {Theme.DISABLED_TEXT};
        border-color: {Theme.DISABLED_BORDER};
    }}

    /* Combo boxes */
    QComboBox {{
        background: {Theme.INPUT_BG};
        color: {Theme.TEXT_WHITE};
        border: 1px solid {Theme.INPUT_BORDER};
        border-radius: 4px;
        padding: 4px 8px;
        min-height: 20px;
    }}
    QComboBox:hover {{
        border-color: {Theme.INPUT_BORDER_HOVER};
    }}
    QComboBox:focus {{
        border-color: {Theme.INPUT_BORDER_FOCUS};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox::down-arrow {{
        image: none;
        width: 0px;
        height: 0px;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {Theme.TEXT_WHITE};
        border-bottom: none;
        margin-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background: {Theme.BG_MEDIUM};
        color: {Theme.TEXT_WHITE};
        border: 1px solid {Theme.INPUT_BORDER};
        selection-background-color: {Theme.ACCENT};
        selection-color: {Theme.TEXT_WHITE};
    }}
    QComboBox:disabled {{
        background: {Theme.DISABLED_BG};
        color: {Theme.DISABLED_TEXT};
        border-color: {Theme.DISABLED_BORDER};
    }}

    /* Spin boxes */
    QSpinBox, QDoubleSpinBox {{
        background: {Theme.INPUT_BG};
        color: {Theme.TEXT_WHITE};
        border: 1px solid {Theme.INPUT_BORDER};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QSpinBox:hover, QDoubleSpinBox:hover {{
        border-color: {Theme.INPUT_BORDER_HOVER};
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {Theme.INPUT_BORDER_FOCUS};
    }}
    QSpinBox:disabled, QDoubleSpinBox:disabled {{
        background: {Theme.DISABLED_BG};
        color: {Theme.DISABLED_TEXT};
        border-color: {Theme.DISABLED_BORDER};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        background: {Theme.BG_CONTROL};
        border: none;
        width: 16px;
    }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {Theme.BG_CONTROL_HOVER};
    }}

    /* Checkboxes */
    QCheckBox {{
        color: {Theme.TEXT_WHITE};
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {Theme.INPUT_BORDER};
        border-radius: 3px;
        background: {Theme.INPUT_BG};
    }}
    QCheckBox::indicator:hover {{
        border-color: {Theme.INPUT_BORDER_HOVER};
    }}
    QCheckBox::indicator:checked {{
        background: {Theme.ACCENT};
        border-color: {Theme.ACCENT};
    }}
    QCheckBox:disabled {{
        color: {Theme.DISABLED_TEXT};
    }}
    QCheckBox::indicator:disabled {{
        background: {Theme.DISABLED_BG};
        border-color: {Theme.DISABLED_BORDER};
    }}

    /* Group boxes */
    QGroupBox {{
        border: 1px solid {Theme.INPUT_BORDER};
        border-radius: 6px;
        margin-top: 8px;
        padding-top: 14px;
        font-weight: bold;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 6px;
        color: {Theme.ACCENT};
    }}

    /* Scroll area */
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background: {Theme.BG_DARK};
        width: 8px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {Theme.SLIDER_GROOVE};
        border-radius: 4px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {Theme.INPUT_BORDER_HOVER};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        background: {Theme.BG_DARK};
        height: 8px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {Theme.SLIDER_GROOVE};
        border-radius: 4px;
        min-width: 20px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {Theme.INPUT_BORDER_HOVER};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}

    /* Text edit (log) */
    QTextEdit {{
        background: {Theme.BG_DARKER};
        color: {Theme.TEXT_WHITE};
        border: 1px solid {Theme.INPUT_BORDER};
        border-radius: 4px;
        padding: 4px;
    }}

    /* Sliders */
    QSlider::groove:horizontal {{
        height: 6px;
        background: {Theme.SLIDER_GROOVE};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        width: 18px;
        background: {Theme.ACCENT};
        border-radius: 9px;
        margin: -6px 0;
    }}
    QSlider::handle:horizontal:hover {{
        background: {Theme.ACCENT_HOVER};
    }}
    QSlider::groove:horizontal:disabled {{
        background: {Theme.DISABLED_BORDER};
    }}
    QSlider::handle:horizontal:disabled {{
        background: {Theme.DISABLED_TEXT};
    }}

    /* Splitter handle */
    QSplitter::handle {{
        background: {Theme.BG_MEDIUM};
    }}

    /* Message box overrides */
    QMessageBox {{
        background: {Theme.BG_DARK};
    }}
    QMessageBox QLabel {{
        color: {Theme.TEXT_WHITE};
    }}
"""
