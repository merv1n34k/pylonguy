"""Minimal GUI - only UI elements, no logic"""
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor
from PyQt5.QtWidgets import *

class PreviewWidget(QWidget):
    """Preview display widget"""
    def __init__(self):
        super().__init__()
        self.pixmap = None
        self.selection = None
        self.selecting = False
        self.select_start = None
        self.mouse_pos = QPoint(0, 0)
        self.frame_shape = None  # Store current frame dimensions

        # UI
        layout = QVBoxLayout()

        # Display
        self.display = QLabel("No Camera")
        self.display.setFixedSize(800, 600)
        self.display.setStyleSheet("background: black;")
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setMouseTracking(True)
        self.display.installEventFilter(self)
        layout.addWidget(self.display)

        # Status
        self.status = QLabel("Not connected")
        self.status.setStyleSheet("background: #333; color: white; padding: 5px;")
        layout.addWidget(self.status)

        # Buttons
        buttons = QHBoxLayout()
        self.btn_live = QPushButton("Start Live")
        self.btn_capture = QPushButton("Capture")
        self.btn_record = QPushButton("Record")
        buttons.addWidget(self.btn_live)
        buttons.addWidget(self.btn_capture)
        buttons.addWidget(self.btn_record)
        layout.addLayout(buttons)

        self.setLayout(layout)

    def show_frame(self, frame):
        """Display numpy array as image"""
        if frame is None:
            return

        h, w = frame.shape[:2]
        self.frame_shape = (w, h)  # Store frame dimensions

        # Create QImage from raw data
        if len(frame.shape) == 2:  # Grayscale
            # Handle different bit depths
            import numpy as np
            if frame.dtype == np.uint16:
                # Convert to 8-bit for display
                frame_8bit = (frame >> 8).astype(np.uint8)
                img = QImage(frame_8bit.data, w, h, w, QImage.Format_Grayscale8)
            else:
                img = QImage(frame.data, w, h, w, QImage.Format_Grayscale8)
        else:  # Color
            img = QImage(frame.data, w, h, w * 3, QImage.Format_RGB888)

        # Scale to fit display
        self.pixmap = QPixmap.fromImage(img).scaled(
            self.display.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        self.update_display()

    def update_display(self):
        """Update display with selection overlay"""
        if not self.pixmap:
            return

        # Create display pixmap
        display_pixmap = QPixmap(self.display.size())
        display_pixmap.fill(Qt.black)

        # Draw image centered
        painter = QPainter(display_pixmap)
        x = (self.display.width() - self.pixmap.width()) // 2
        y = (self.display.height() - self.pixmap.height()) // 2
        painter.drawPixmap(x, y, self.pixmap)

        # Draw selection if exists
        if self.selection or (self.selecting and self.select_start):
            painter.setBrush(QColor(0, 120, 255, 100))
            painter.setPen(Qt.NoPen)

            if self.selection:
                painter.drawRect(self.selection)
            elif self.selecting and self.select_start:
                rect = QRect(self.select_start, self.mouse_pos)
                painter.drawRect(rect.normalized())

        painter.end()
        self.display.setPixmap(display_pixmap)

    def eventFilter(self, obj, event):
        if obj == self.display:
            if event.type() == event.MouseMove:
                self.mouse_pos = event.pos()
                if self.selecting:
                    self.update_display()
            elif event.type() == event.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self.select_start = event.pos()
                    self.selecting = True
                    self.selection = None
            elif event.type() == event.MouseButtonRelease:
                if event.button() == Qt.LeftButton and self.selecting:
                    self.selecting = False
                    if self.select_start != self.mouse_pos:
                        self.selection = QRect(self.select_start, self.mouse_pos).normalized()
                    else:
                        self.selection = None
                    self.update_display()
        return super().eventFilter(obj, event)

class SettingsWidget(QWidget):
    """Settings panel"""
    def __init__(self):
        super().__init__()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout()

        # Connection
        group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        conn_layout.addWidget(self.btn_connect)
        conn_layout.addWidget(self.btn_disconnect)
        group.setLayout(conn_layout)
        layout.addWidget(group)

        # ROI
        group = QGroupBox("ROI")
        roi_layout = QFormLayout()
        self.width = QSpinBox()
        self.width.setRange(160, 4096)
        self.width.setValue(1280)
        self.height = QSpinBox()
        self.height.setRange(120, 3072)
        self.height.setValue(720)
        self.offset_x = QSpinBox()
        self.offset_x.setRange(0, 4096)
        self.offset_x.setValue(0)
        self.offset_y = QSpinBox()
        self.offset_y.setRange(0, 3072)
        self.offset_y.setValue(0)
        roi_layout.addRow("Width:", self.width)
        roi_layout.addRow("Height:", self.height)
        roi_layout.addRow("Offset X:", self.offset_x)
        roi_layout.addRow("Offset Y:", self.offset_y)
        group.setLayout(roi_layout)
        layout.addWidget(group)

        # Exposure & Gain
        group = QGroupBox("Acquisition")
        acq_layout = QFormLayout()
        self.exposure = QDoubleSpinBox()
        self.exposure.setRange(10, 1000000)
        self.exposure.setValue(10000)
        self.exposure.setSuffix(" μs")
        self.gain = QDoubleSpinBox()
        self.gain.setRange(0, 48)
        self.gain.setValue(0)
        acq_layout.addRow("Exposure:", self.exposure)
        acq_layout.addRow("Gain:", self.gain)
        group.setLayout(acq_layout)
        layout.addWidget(group)

        # Output
        group = QGroupBox("Output")
        out_layout = QFormLayout()
        self.video_fps = QDoubleSpinBox()
        self.video_fps.setRange(1, 120)
        self.video_fps.setValue(24)
        self.video_fps.setSuffix(" fps")
        out_layout.addRow("Video FPS:", self.video_fps)
        group.setLayout(out_layout)
        layout.addWidget(group)

        # Apply button
        self.btn_apply = QPushButton("Apply Settings")
        layout.addWidget(self.btn_apply)

        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)

        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

class LogWidget(QWidget):
    """Log display"""
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Log"))

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        layout.addWidget(self.log)

        self.setLayout(layout)

    def add(self, text):
        self.log.append(text)

class MainWindow(QMainWindow):
    """Main application window"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pylon Camera GUI")
        self.setGeometry(100, 100, 1200, 800)

        # Create widgets
        self.preview = PreviewWidget()
        self.settings = SettingsWidget()
        self.log = LogWidget()

        # Layout
        central = QWidget()
        layout = QHBoxLayout()

        # Left: preview
        layout.addWidget(self.preview, 2)

        # Right: settings + log
        right = QVBoxLayout()
        right.addWidget(self.settings, 3)
        right.addWidget(self.log, 1)
        layout.addLayout(right, 1)

        central.setLayout(layout)
        self.setCentralWidget(central)

    def closeEvent(self, event):
        """Clean up on close"""
        event.accept()
