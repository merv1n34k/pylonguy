"""Log widget - Application logging display"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QComboBox,
)
from pathlib import Path
import logging
import time

log = logging.getLogger("pylonguy")


class LogWidget(QWidget):
    """Log display widget with controls"""

    append_text = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.log_content = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Header with controls
        header_layout = QHBoxLayout()

        header_layout.addWidget(QLabel("Log"))
        header_layout.addStretch()

        # Log level selector
        self.level_combo = QComboBox()
        self.level_combo.addItems(["INFO", "DEBUG"])
        self.level_combo.setCurrentText("INFO")
        self.level_combo.setStyleSheet("color: white;")

        # Don't connect here - let app.py handle it
        header_layout.addWidget(QLabel("Level:"))
        header_layout.addWidget(self.level_combo)

        # Control buttons
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_log)
        header_layout.addWidget(self.btn_clear)

        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save_log)
        header_layout.addWidget(self.btn_save)

        layout.addLayout(header_layout)

        # Log display
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        layout.addWidget(self.log)

        self.setLayout(layout)

        self.append_text.connect(self._append_text_safe)

    def add(self, message: str):
        """Add message to log"""
        self.log_content.append(message)
        self.append_text.emit(message)

    def _append_text_safe(self, message: str):
        """Append text in GUI thread"""
        try:
            self.log.append(message)
            scrollbar = self.log.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except:
            pass

    def clear_log(self):
        """Clear the log display and content"""
        self.log.clear()
        self.log_content = []

    def save_log(self):
        """Save log content to file"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"log_{timestamp}.log"

        try:
            Path("./logs").mkdir(exist_ok=True)
            filepath = Path("./logs") / filename

            with open(filepath, "w") as f:
                f.write("\n".join(self.log_content))

            # Note: This will only appear if INFO level is selected
            logging.getLogger("pylonguy").info(f"Log saved to {filepath}")
        except Exception as e:
            logging.getLogger("pylonguy").error(f"Failed to save log: {e}")
