"""GUI module - Main interface exports"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout

from .preview import PreviewWidget
from .settings import SettingsWidget
from .log import LogWidget


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("PylonGuy")
        self.setGeometry(100, 100, 1400, 900)

        # Create widgets
        self.preview = PreviewWidget()
        self.settings = SettingsWidget()
        self.log = LogWidget()

        # Layout
        central = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Left: preview
        layout.addWidget(self.preview, 3)

        # Right: settings + log
        right_widget = QWidget()
        right_widget.setFixedWidth(400)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.addWidget(self.settings, 3)
        right_layout.addWidget(self.log, 1)

        right_widget.setLayout(right_layout)
        layout.addWidget(right_widget, 0)

        central.setLayout(layout)
        self.setCentralWidget(central)


__all__ = ["MainWindow", "PreviewWidget", "SettingsWidget", "LogWidget"]
