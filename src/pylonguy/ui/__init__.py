"""UI module - Main interface exports"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QSplitter,
    QSplitterHandle,
)

from .preview import PreviewWidget
from .settings import SettingsWidget
from .log import LogWidget
from ..constants import WINDOW_DEFAULT_GEOMETRY
from ..theme import Theme


class DottedSplitterHandle(QSplitterHandle):
    """Splitter handle with 3 dots that toggles the right panel on click."""

    HANDLE_WIDTH = 12
    DOT_RADIUS = 2
    DOT_SPACING = 6

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._collapsed = False
        self._saved_size = 400
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return super().sizeHint().expandedTo(
            self.minimumSizeHint()
        )

    def minimumSizeHint(self):
        return QSize(self.HANDLE_WIDTH, 0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(Theme.BG_DARK))

        # Draw 3 white dots vertically centered
        cx = self.width() // 2
        cy = self.height() // 2
        painter.setBrush(QColor(Theme.TEXT_WHITE))
        painter.setPen(Qt.PenStyle.NoPen)
        for dy in (-self.DOT_SPACING, 0, self.DOT_SPACING):
            painter.drawEllipse(
                cx - self.DOT_RADIUS,
                cy + dy - self.DOT_RADIUS,
                self.DOT_RADIUS * 2,
                self.DOT_RADIUS * 2,
            )

    def mousePressEvent(self, event):
        # Toggle instead of drag
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_panel()

    def mouseMoveEvent(self, event):
        # Disable drag
        pass

    def _toggle_panel(self):
        splitter = self.splitter()
        sizes = splitter.sizes()
        if sizes[1] > 0:
            self._saved_size = sizes[1]
            splitter.setSizes([sizes[0] + sizes[1], 0])
            self._collapsed = True
        else:
            splitter.setSizes([sizes[0] - self._saved_size, self._saved_size])
            self._collapsed = False


class CollapsibleSplitter(QSplitter):
    """QSplitter that uses DottedSplitterHandle."""

    def createHandle(self):
        return DottedSplitterHandle(self.orientation(), self)


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("PylonGuy")
        self.setGeometry(*WINDOW_DEFAULT_GEOMETRY)

        # Create widgets
        self.preview = PreviewWidget()
        self.settings = SettingsWidget()
        self.log = LogWidget()

        # Right panel: settings + log
        right_widget = QWidget()
        right_widget.setMinimumWidth(0)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.addWidget(self.settings, 3)
        right_layout.addWidget(self.log, 1)
        right_widget.setLayout(right_layout)

        # Splitter layout
        splitter = CollapsibleSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.preview)
        splitter.addWidget(right_widget)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, True)
        splitter.setSizes([1000, 400])

        self.setCentralWidget(splitter)


__all__ = ["MainWindow", "PreviewWidget", "SettingsWidget", "LogWidget"]
