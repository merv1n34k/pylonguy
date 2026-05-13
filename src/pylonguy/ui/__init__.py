"""UI module - Main interface exports"""

import dropletui as ui
from PySide6.QtWidgets import QMainWindow

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

        # Create widgets
        self.preview = PreviewWidget()
        self.settings = SettingsWidget()
        self.log = LogWidget()

        right_widget, right_layout = ui.side_panel()
        right_layout.addWidget(self.settings, 3)
        right_layout.addWidget(self.log, 1)

        self.setCentralWidget(
            ui.split_view(
                self.preview,
                right_widget,
                side_position="right",
                collapsible=True,
            )
        )


__all__ = ["MainWindow", "PreviewWidget", "SettingsWidget", "LogWidget"]
