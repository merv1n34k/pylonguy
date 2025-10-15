"""GUI module - user interface elements"""

from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QTransform, QFont
from PyQt5.QtWidgets import *
import numpy as np
import logging
import json
import time
import math
from pathlib import Path

log = logging.getLogger("pylonguy")


class PreviewDisplay(QWidget):
    """Pure zero-copy frame display - real-time rendering, no caching"""

    selection_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()

        # Frame data (zero-copy)
        self.current_frame = None  # numpy array reference only

        # Geometry
        self.frame_rect = QRect()

        # Selection state
        self.selection_rect = None
        self.selecting = False
        self.select_start = None
        self.mouse_pos = None

        # Waterfall state
        self.waterfall_buffer = None
        self.waterfall_row = 0
        self.waterfall_mode = False

        # Display modes
        self.flip_x = False
        self.flip_y = False
        self.rotation = 0
        self.ruler_v = False
        self.ruler_h = False
        self.ruler_radial = False

        # Deshear parameters
        self.deshear_enabled = False
        self.deshear_angle = 0
        self.deshear_px_um = 3.8

        # Message display
        self.message = ""

        # Setup widget
        self.setMouseTracking(True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), Qt.black)
        self.setPalette(pal)

    def setFrame(self, frame: np.ndarray):
        """Zero-copy frame update - no caching"""
        if frame is None:
            return

        if self.waterfall_mode and self.waterfall_buffer is not None:
            # Waterfall mode - frame is already a single line (height=1)
            if len(frame.shape) == 2:
                if frame.shape[0] == 1:
                    # Single row frame - extract it
                    line = frame[0, :].astype(np.uint8)
            else:
                # Already 1D array or unexpected shape
                line = frame[: self.waterfall_buffer.shape[1]].astype(np.uint8)

            # Add to buffer directly (no deshearing in preview)
            self.waterfall_buffer[self.waterfall_row] = line
            self.waterfall_row = (self.waterfall_row + 1) % self.waterfall_buffer.shape[
                0
            ]

            # Prepare display array
            if self.waterfall_row == 0:
                self.current_frame = self.waterfall_buffer
            else:
                self.current_frame = np.vstack(
                    [
                        self.waterfall_buffer[self.waterfall_row :],
                        self.waterfall_buffer[: self.waterfall_row],
                    ]
                )
        else:
            # Normal mode - just store reference
            if frame.dtype == np.uint16:
                frame = (frame >> 8).astype(np.uint8)
            self.current_frame = frame

        self.message = ""
        self.update()  # Trigger repaint

    def showMessage(self, text: str):
        """Show text message"""
        self.message = text
        self.current_frame = None
        self.update()

    def paintEvent(self, event):
        """Real-time painting - no caching"""
        painter = QPainter(self)

        # Always clear background
        painter.fillRect(self.rect(), Qt.black)

        # Draw message if set
        if self.message:
            painter.setPen(Qt.white)
            font = QFont()
            font.setPointSize(20)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, self.message)
            return

        # Draw frame if available
        if self.current_frame is not None:
            # Create QImage wrapper every time (no caching)
            h, w = self.current_frame.shape[:2]

            if len(self.current_frame.shape) == 2:
                # Grayscale
                qimage = QImage(
                    self.current_frame.data, w, h, w, QImage.Format_Grayscale8
                )
            else:
                # RGB
                qimage = QImage(
                    self.current_frame.data, w, h, w * 3, QImage.Format_RGB888
                )

            # Calculate display rectangle
            widget_rect = self.rect()
            scale_x = widget_rect.width() / w if w > 0 else 1
            scale_y = widget_rect.height() / h if h > 0 else 1
            scale = min(scale_x, scale_y)

            final_w = int(w * scale)
            final_h = int(h * scale)
            x = (widget_rect.width() - final_w) // 2
            y = (widget_rect.height() - final_h) // 2

            self.frame_rect = QRect(x, y, final_w, final_h)

            # Apply transforms if needed
            if self.flip_x or self.flip_y or self.rotation != 0:
                painter.save()
                painter.translate(self.frame_rect.center())

                transform = QTransform()
                if self.rotation != 0:
                    transform.rotate(self.rotation)
                if self.flip_x:
                    transform.scale(-1, 1)
                if self.flip_y:
                    transform.scale(1, -1)

                painter.setTransform(transform, True)

                offset_rect = QRect(
                    -self.frame_rect.width() // 2,
                    -self.frame_rect.height() // 2,
                    self.frame_rect.width(),
                    self.frame_rect.height(),
                )

                # Scale and draw the image
                scaled_image = qimage.scaled(
                    self.frame_rect.width(),
                    self.frame_rect.height(),
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,
                )
                painter.drawImage(offset_rect, scaled_image)
                painter.restore()
            else:
                # Scale and draw directly
                scaled_image = qimage.scaled(
                    self.frame_rect.width(),
                    self.frame_rect.height(),
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,
                )
                painter.drawImage(self.frame_rect, scaled_image)

            # Draw overlays
            self._drawOverlays(painter)

    def _drawOverlays(self, painter):
        """Draw selection, rulers, and indicators"""

        # Draw selection
        if self.selection_rect or (
            self.selecting and self.select_start and self.mouse_pos
        ):
            pen = QPen(QColor(0, 180, 255), 2, Qt.DashLine)
            pen.setDashPattern([5, 3])
            painter.setPen(pen)
            painter.setBrush(QColor(0, 120, 255, 30))

            if self.selection_rect:
                painter.drawRect(self.selection_rect)
            else:
                temp_rect = QRect(self.select_start, self.mouse_pos).normalized()
                painter.drawRect(temp_rect)

        # Draw rulers only if frame rect is valid
        if (
            self.ruler_v or self.ruler_h or self.ruler_radial
        ) and not self.frame_rect.isEmpty():
            painter.setPen(QPen(QColor(255, 255, 0, 180), 1, Qt.SolidLine))

            cx = self.frame_rect.center().x()
            cy = self.frame_rect.center().y()

            if self.ruler_v:
                step = max(1, self.frame_rect.width() // 10)
                for x in range(
                    self.frame_rect.left(), self.frame_rect.right() + 1, step
                ):
                    painter.drawLine(
                        x, self.frame_rect.top(), x, self.frame_rect.bottom()
                    )
                painter.drawLine(
                    cx, self.frame_rect.top(), cx, self.frame_rect.bottom()
                )

            if self.ruler_h:
                step = max(1, self.frame_rect.height() // 10)
                for y in range(
                    self.frame_rect.top(), self.frame_rect.bottom() + 1, step
                ):
                    painter.drawLine(
                        self.frame_rect.left(), y, self.frame_rect.right(), y
                    )
                painter.drawLine(
                    self.frame_rect.left(), cy, self.frame_rect.right(), cy
                )

            if self.ruler_radial:
                import math

                # Use maximum dimension for radius to reach corners
                radius = int(
                    math.sqrt(
                        (self.frame_rect.width() / 2) ** 2
                        + (self.frame_rect.height() / 2) ** 2
                    )
                )

                for angle in range(0, 360, 30):
                    radian = math.radians(angle)
                    x_end = cx + radius * math.cos(radian)
                    y_end = cy - radius * math.sin(radian)
                    painter.drawLine(cx, cy, int(x_end), int(y_end))

                    # Labels at 45% of radius
                    label_radius = radius * 0.45
                    x_label = cx + label_radius * math.cos(radian)
                    y_label = cy - label_radius * math.sin(radian)

                    label_text = f"{angle}°"
                    painter.setPen(QPen(QColor(0, 0, 0), 2))
                    painter.drawText(
                        int(x_label - 15),
                        int(y_label - 5),
                        30,
                        10,
                        Qt.AlignCenter,
                        label_text,
                    )
                    painter.setPen(QPen(QColor(255, 255, 0), 1))
                    painter.drawText(
                        int(x_label - 14),
                        int(y_label - 6),
                        28,
                        10,
                        Qt.AlignCenter,
                        label_text,
                    )

        # Draw transform indicators
        if self.flip_x or self.flip_y or self.rotation != 0:
            transform_text = []
            if self.flip_x:
                transform_text.append("FlipX")
            if self.flip_y:
                transform_text.append("FlipY")
            if self.rotation != 0:
                transform_text.append(f"Rot{self.rotation}°")
            painter.setPen(QColor(255, 255, 0))
            painter.drawText(10, 20, " ".join(transform_text) + " (preview only)")

        if self.deshear_enabled and self.waterfall_mode:
            painter.setPen(QColor(255, 255, 0))
            painter.drawText(
                10, 40, f"DESHEAR {self.deshear_angle:.1f}° (not shown in preview)"
            )

    # Keep all mouse event handlers and other methods unchanged
    def mousePressEvent(self, event):
        """Start selection"""
        if event.button() == Qt.LeftButton:
            self.select_start = event.pos()
            self.selecting = True
            self.selection_rect = None

    def mouseMoveEvent(self, event):
        """Track selection"""
        self.mouse_pos = event.pos()
        if self.selecting:
            self.update()

    def mouseReleaseEvent(self, event):
        """Finish selection"""
        if event.button() == Qt.LeftButton and self.selecting:
            self.selecting = False
            if (
                self.select_start
                and self.mouse_pos
                and self.select_start != self.mouse_pos
            ):
                self.selection_rect = QRect(
                    self.select_start, self.mouse_pos
                ).normalized()
                if self.selection_rect.isValid() and self.selection_rect.width() > 5:
                    pixel_rect = self._mapToFrameCoords(self.selection_rect)
                    self.selection_changed.emit(pixel_rect)
                else:
                    self.clearSelection()
            else:
                self.clearSelection()
            self.update()

    def _mapToFrameCoords(self, display_rect: QRect) -> QRect:
        """Map display coordinates to frame coordinates"""
        if self.current_frame is None or self.frame_rect.isEmpty():
            return QRect()

        h, w = self.current_frame.shape[:2]

        rel_x = display_rect.x() - self.frame_rect.x()
        rel_y = display_rect.y() - self.frame_rect.y()

        scale_x = w / self.frame_rect.width() if self.frame_rect.width() > 0 else 1
        scale_y = h / self.frame_rect.height() if self.frame_rect.height() > 0 else 1

        frame_x = max(0, min(int(rel_x * scale_x), w - 1))
        frame_y = max(0, min(int(rel_y * scale_y), h - 1))
        frame_w = min(int(display_rect.width() * scale_x), w - frame_x)
        frame_h = min(int(display_rect.height() * scale_y), h - frame_y)

        return QRect(frame_x, frame_y, frame_w, frame_h)

    def clearSelection(self):
        """Clear selection"""
        self.selection_rect = None
        self.selecting = False
        self.select_start = None
        self.mouse_pos = None
        self.update()

    def getSelection(self) -> QRect:
        """Get current selection in frame coordinates"""
        if self.selection_rect and self.selection_rect.isValid():
            return self._mapToFrameCoords(self.selection_rect)
        return QRect()

    def getWaterfallBuffer(self) -> np.ndarray:
        """Get waterfall buffer for capture"""
        if self.waterfall_mode and self.waterfall_buffer is not None:
            if self.waterfall_row == 0:
                return self.waterfall_buffer.copy()
            else:
                return np.vstack(
                    [
                        self.waterfall_buffer[self.waterfall_row :],
                        self.waterfall_buffer[: self.waterfall_row],
                    ]
                )
        return None


class PreviewControls(QWidget):
    """Preview control panel - status, buttons, sliders"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Status bar
        status_widget = QWidget()
        status_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_widget.setStyleSheet("QWidget { background: #1a1a1a; }")

        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)

        # FPS Section
        fps_widget = QWidget()
        fps_layout = QHBoxLayout()
        fps_layout.setContentsMargins(0, 0, 0, 0)
        fps_layout.setSpacing(0)
        fps_label = QLabel(" FPS ")
        fps_label.setStyleSheet(
            "background: #444; color: #bbb; padding: 5px 10px; font-weight: bold;"
        )
        self.fps_value = QLabel(" 0.0 ")
        self.fps_value.setStyleSheet(
            "background: #222; color: #0f0; padding: 5px 10px;"
        )
        fps_layout.addWidget(fps_label)
        fps_layout.addWidget(self.fps_value, 1)
        fps_widget.setLayout(fps_layout)

        # Recording Section
        rec_widget = QWidget()
        rec_layout = QHBoxLayout()
        rec_layout.setContentsMargins(0, 0, 0, 0)
        rec_layout.setSpacing(0)
        rec_label = QLabel(" REC ")
        rec_label.setStyleSheet(
            "background: #444; color: #bbb; padding: 5px 10px; font-weight: bold;"
        )
        self.rec_status = QLabel(" OFF ")
        self.rec_status.setStyleSheet(
            "background: #222; color: #0f0; padding: 5px 10px;"
        )
        rec_layout.addWidget(rec_label)
        rec_layout.addWidget(self.rec_status, 1)
        rec_widget.setLayout(rec_layout)

        # Frames/Lines Section
        frames_widget = QWidget()
        frames_layout = QHBoxLayout()
        frames_layout.setContentsMargins(0, 0, 0, 0)
        frames_layout.setSpacing(0)
        self.frames_label = QLabel(" FRAMES ")
        self.frames_label.setStyleSheet(
            "background: #444; color: #bbb; padding: 5px 10px; font-weight: bold;"
        )
        self.rec_frames = QLabel(" 0 ")
        self.rec_frames.setStyleSheet(
            "background: #222; color: #0f0; padding: 5px 10px;"
        )
        frames_layout.addWidget(self.frames_label)
        frames_layout.addWidget(self.rec_frames, 1)
        frames_widget.setLayout(frames_layout)

        # Time Section
        time_widget = QWidget()
        time_layout = QHBoxLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(0)
        time_label = QLabel(" TIME ")
        time_label.setStyleSheet(
            "background: #444; color: #bbb; padding: 5px 10px; font-weight: bold;"
        )
        self.rec_time = QLabel(" 0.0s ")
        self.rec_time.setStyleSheet("background: #222; color: #0f0; padding: 5px 10px;")
        time_layout.addWidget(time_label)
        time_layout.addWidget(self.rec_time, 1)
        time_widget.setLayout(time_layout)

        # ROI Section
        roi_widget = QWidget()
        roi_layout = QHBoxLayout()
        roi_layout.setContentsMargins(0, 0, 0, 0)
        roi_layout.setSpacing(0)
        roi_label = QLabel(" ROI ")
        roi_label.setStyleSheet(
            "background: #444; color: #bbb; padding: 5px 10px; font-weight: bold;"
        )
        self.roi_value = QLabel(" --- ")
        self.roi_value.setStyleSheet(
            "background: #222; color: #0f0; padding: 5px 10px;"
        )
        roi_layout.addWidget(roi_label)
        roi_layout.addWidget(self.roi_value, 1)
        roi_widget.setLayout(roi_layout)

        # Selection Section
        sel_widget = QWidget()
        sel_layout = QHBoxLayout()
        sel_layout.setContentsMargins(0, 0, 0, 0)
        sel_layout.setSpacing(0)
        sel_label = QLabel(" SEL ")
        sel_label.setStyleSheet(
            "background: #444; color: #bbb; padding: 5px 10px; font-weight: bold;"
        )
        self.sel_value = QLabel(" None ")
        self.sel_value.setStyleSheet(
            "background: #222; color: #0f0; padding: 5px 10px;"
        )
        sel_layout.addWidget(sel_label)
        sel_layout.addWidget(self.sel_value, 1)
        sel_widget.setLayout(sel_layout)

        # Add all status sections
        status_layout.addWidget(fps_widget, 1)
        status_layout.addWidget(rec_widget, 1)
        status_layout.addWidget(frames_widget, 1)
        status_layout.addWidget(time_widget, 1)
        status_layout.addWidget(roi_widget, 1)
        status_layout.addWidget(sel_widget, 1)

        status_widget.setLayout(status_layout)
        layout.addWidget(status_widget)

        # Control buttons
        button_widget = QWidget()
        button_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button_widget.setStyleSheet("""
            QWidget {
                border-left: 1px solid #333;
                border-right: 1px solid #333;
                background: #2a2a2a;
            }
            QPushButton {
                background: #3c3c3c;
                color: white;
                border: none;
                font-weight: bold;
                font-size: 12px;
                padding: 10px;
            }
            QPushButton:hover {
                background: #4c4c4c;
            }
            QPushButton:pressed {
                background: #2c2c2c;
            }
        """)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(1, 0, 1, 0)
        button_layout.setSpacing(1)

        self.btn_live = QPushButton("Start Live")
        self.btn_capture = QPushButton("Capture")
        self.btn_record = QPushButton("Record")
        self.btn_clear_selection = QPushButton("Clear Selection")

        button_layout.addWidget(self.btn_live)
        button_layout.addWidget(self.btn_capture)
        button_layout.addWidget(self.btn_record)
        button_layout.addWidget(self.btn_clear_selection)

        button_widget.setLayout(button_layout)
        layout.addWidget(button_widget)

        # Offset sliders
        slider_widget = QWidget()
        slider_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        slider_widget.setStyleSheet("QWidget { background: #2a2a2a; padding: 5px; }")

        slider_layout = QVBoxLayout()
        slider_layout.setContentsMargins(10, 5, 10, 5)
        slider_layout.setSpacing(5)

        # X Offset slider
        x_layout = QHBoxLayout()
        x_label = QLabel("Offset X:")
        x_label.setStyleSheet("color: white; min-width: 60px;")
        self.offset_x_slider = QSlider(Qt.Horizontal)
        self.offset_x_slider.setRange(0, 4096)
        self.offset_x_slider.setValue(0)
        self.offset_x_slider.setSingleStep(16)
        self.offset_x_slider.setPageStep(16)
        self.offset_x_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #555;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                background: #0af;
                border-radius: 9px;
                margin: -6px 0;
            }
        """)
        self.offset_x_value = QLabel("0")
        self.offset_x_value.setStyleSheet("color: white; min-width: 40px;")
        x_layout.addWidget(x_label)
        x_layout.addWidget(self.offset_x_slider)
        x_layout.addWidget(self.offset_x_value)

        # Y Offset slider
        y_layout = QHBoxLayout()
        y_label = QLabel("Offset Y:")
        y_label.setStyleSheet("color: white; min-width: 60px;")
        self.offset_y_slider = QSlider(Qt.Horizontal)
        self.offset_y_slider.setRange(0, 3072)
        self.offset_y_slider.setValue(0)
        self.offset_y_slider.setSingleStep(16)
        self.offset_y_slider.setPageStep(16)
        self.offset_y_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #555;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                background: #0af;
                border-radius: 9px;
                margin: -6px 0;
            }
        """)
        self.offset_y_value = QLabel("0")
        self.offset_y_value.setStyleSheet("color: white; min-width: 40px;")
        y_layout.addWidget(y_label)
        y_layout.addWidget(self.offset_y_slider)
        y_layout.addWidget(self.offset_y_value)

        slider_layout.addLayout(x_layout)
        slider_layout.addLayout(y_layout)
        slider_widget.setLayout(slider_layout)
        layout.addWidget(slider_widget)

        # Connect slider value displays
        self.offset_x_slider.valueChanged.connect(
            lambda v: self.offset_x_value.setText(str(v))
        )
        self.offset_y_slider.valueChanged.connect(
            lambda v: self.offset_y_value.setText(str(v))
        )

        self.setLayout(layout)

    def updateStatus(self, **kwargs):
        """Update status displays"""
        if "fps" in kwargs:
            self.fps_value.setText(f" {kwargs['fps']:.1f} ")

        if "recording" in kwargs:
            if kwargs["recording"]:
                self.rec_status.setText(" ON ")
                self.rec_status.setStyleSheet(
                    "background: #222; color: #f00; padding: 5px 10px;"
                )
            else:
                self.rec_status.setText(" OFF ")
                self.rec_status.setStyleSheet(
                    "background: #222; color: #0f0; padding: 5px 10px;"
                )

        if "frames" in kwargs:
            self.rec_frames.setText(f" {kwargs['frames']} ")

        if "elapsed" in kwargs:
            self.rec_time.setText(f" {kwargs['elapsed']:.1f}s ")

        if "roi" in kwargs:
            self.roi_value.setText(f" {kwargs['roi']} ")

        if "selection" in kwargs:
            if kwargs["selection"]:
                self.sel_value.setText(f" {kwargs['selection']} ")
            else:
                self.sel_value.setText(" None ")

    def setWaterfallMode(self, enabled: bool):
        """Update labels for waterfall mode"""
        if enabled:
            self.frames_label.setText(" LINES ")
        else:
            self.frames_label.setText(" FRAMES ")


class PreviewWidget(QWidget):
    """Container widget that combines display and controls"""

    # Forward signals from internal widgets
    selection_changed = pyqtSignal(object)
    offset_x_changed = pyqtSignal(int)
    offset_y_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Display area (takes all available space)
        self.display = PreviewDisplay()
        self.display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.display)

        # Controls area (fixed height, minimal space)
        self.controls = PreviewControls()
        self.controls.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.controls.setMaximumHeight(150)  # Fixed height for controls
        layout.addWidget(self.controls)

        # Connect internal signals
        self.display.selection_changed.connect(self._on_selection_changed)
        self.controls.btn_clear_selection.clicked.connect(self.clear_selection)
        self.controls.offset_x_slider.valueChanged.connect(self.offset_x_changed.emit)
        self.controls.offset_y_slider.valueChanged.connect(self.offset_y_changed.emit)

        # Create references for backward compatibility
        self.btn_live = self.controls.btn_live
        self.btn_capture = self.controls.btn_capture
        self.btn_record = self.controls.btn_record
        self.offset_x_slider = self.controls.offset_x_slider
        self.offset_y_slider = self.controls.offset_y_slider
        self.offset_x_value = self.controls.offset_x_value
        self.offset_y_value = self.controls.offset_y_value

        # These are needed by main.py
        self.fps_value = self.controls.fps_value
        self.rec_status = self.controls.rec_status
        self.rec_frames = self.controls.rec_frames
        self.rec_time = self.controls.rec_time
        self.roi_value = self.controls.roi_value
        self.sel_value = self.controls.sel_value

        self.setLayout(layout)

    # Public interface methods
    def show_frame(self, frame: np.ndarray):
        """Display frame with zero copy"""
        self.display.setFrame(frame)

    def show_message(self, message: str):
        """Show text message"""
        self.display.showMessage(message)

    def set_waterfall_mode(self, enabled: bool, width: int = 640, lines: int = 500):
        """Configure waterfall mode"""
        self.display.waterfall_mode = enabled
        if enabled:
            self.display.waterfall_buffer = np.full((lines, width), 255, dtype=np.uint8)
            self.display.waterfall_row = 0
            self.controls.setWaterfallMode(True)
        else:
            self.display.waterfall_buffer = None
            self.display.waterfall_row = 0
            self.controls.setWaterfallMode(False)

    def set_transform(self, flip_x: bool, flip_y: bool, rotation: int):
        """Set preview transform"""
        self.display.flip_x = flip_x
        self.display.flip_y = flip_y
        self.display.rotation = rotation

    def set_rulers(self, v: bool, h: bool, radial: bool):
        """Set ruler display"""
        self.display.ruler_v = v
        self.display.ruler_h = h
        self.display.ruler_radial = radial
        self.display.update()

    def set_deshear(self, enabled: bool, angle: float, px_um: float):
        """Set deshear parameters"""
        self.display.deshear_enabled = enabled
        self.display.deshear_angle = angle
        self.display.deshear_px_um = px_um

    def update_status(self, **kwargs):
        """Update status displays"""
        self.controls.updateStatus(**kwargs)

    def clear_selection(self):
        """Clear selection"""
        self.display.clearSelection()
        self.controls.sel_value.setText(" None ")
        self.selection_changed.emit(None)

    def get_selection(self) -> QRect:
        """Get current selection"""
        return self.display.getSelection()

    def get_waterfall_buffer(self) -> np.ndarray:
        """Get waterfall buffer for capture"""
        return self.display.getWaterfallBuffer()

    def _on_selection_changed(self, rect):
        """Handle selection change from display"""
        if rect and rect.isValid():
            self.controls.sel_value.setText(f" {rect.width()}x{rect.height()} ")
        else:
            self.controls.sel_value.setText(" None ")
        self.selection_changed.emit(rect)


class SettingsWidget(QWidget):
    """Settings panel with all controls"""

    settings_changed = pyqtSignal()
    mode_changed = pyqtSignal(str)  # New signal for mode changes
    transform_changed = pyqtSignal(bool, bool, int)  # flip_x, flip_y, rotation
    ruler_changed = pyqtSignal(bool, bool, bool)  # ruler v, h, radial

    def __init__(self):
        super().__init__()
        self.presets = {}
        self.init_ui()
        self.init_presets()

    def init_presets(self):
        """Initialize preset configurations from JSON file"""
        self.presets = {}
        preset_file = Path("presets.json")

        # Default presets
        default_presets = {
            "Quality": {
                "Width": 1920,
                "Height": 1080,
                "BinningHorizontal": "1",
                "BinningVertical": "1",
                "ExposureTime": 1000,
                "Gain": 0,
                "PixelFormat": "Mono10p",
                "SensorReadoutMode": "Normal",
            },
            "Speed": {
                "Width": 320,
                "Height": 240,
                "BinningHorizontal": "1",
                "BinningVertical": "1",
                "ExposureTime": 100,
                "Gain": 0,
                "PixelFormat": "Mono8",
                "SensorReadoutMode": "Fast",
            },
            "Balanced": {
                "Width": 640,
                "Height": 480,
                "BinningHorizontal": "1",
                "BinningVertical": "1",
                "ExposureTime": 500,
                "Gain": 0,
                "PixelFormat": "Mono8",
                "SensorReadoutMode": "Normal",
            },
            "waterfall": {
                "Width": 128,
                "Height": 8,
                "BinningHorizontal": "1",
                "BinningVertical": "1",
                "ExposureTime": 10,
                "Gain": 0,
                "PixelFormat": "Mono8",
                "SensorReadoutMode": "Fast",
            },
        }

        if preset_file.exists():
            try:
                with open(preset_file, "r") as f:
                    self.presets = json.load(f)
                    log.info("Loaded presets from file")
            except Exception as e:
                log.error(f"Failed to load presets: {e}")
                self.presets = default_presets
        else:
            self.presets = default_presets
            self._save_presets_to_file()

        for preset in self.presets.keys():
            self.preset_combo.addItem(preset)

    def _save_presets_to_file(self):
        """Save all presets to JSON file"""
        try:
            with open("presets.json", "w") as f:
                json.dump(self.presets, f, indent=2)
            log.debug("Saved presets to file")
        except Exception as e:
            log.error(f"Failed to save presets: {e}")

    def save_preset(self):
        """Save current settings as named preset"""
        preset_name = self.preset_name_input.text().strip()
        if not preset_name:
            log.warning("Please enter a preset name")
            return

        # Get current values from widgets
        preset = {
            "Width": self.roi_width.value(),
            "Height": self.roi_height.value(),
            "OffsetX": self.roi_offset_x.value(),
            "OffsetY": self.roi_offset_y.value(),
            "BinningHorizontal": self.binning_horizontal.currentText(),
            "BinningVertical": self.binning_vertical.currentText(),
            "ExposureTime": self.exposure.value(),
            "Gain": self.gain.value(),
            "PixelFormat": self.pixel_format.currentText(),
            "SensorReadoutMode": self.sensor_mode.currentText(),
        }

        # Save to presets dict
        self.presets[preset_name] = preset

        # Save to file
        self._save_presets_to_file()

        # Update combo box if new preset
        if self.preset_combo.findText(preset_name) < 0:
            self.preset_combo.addItem(preset_name)
            # Re-sort items
            items = [
                self.preset_combo.itemText(i) for i in range(self.preset_combo.count())
            ]
            items.sort()
            self.preset_combo.clear()
            self.preset_combo.addItems(items)

        # Clear input field
        self.preset_name_input.clear()
        log.info(f"Saved preset: {preset_name}")

    def init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        layout = QVBoxLayout()

        # Connection controls
        conn_group = QGroupBox("Connection")
        conn_layout = QVBoxLayout()

        # First row: Camera selection and load defaults checkbox
        select_layout = QHBoxLayout()
        self.camera_combo = QComboBox()
        self.camera_combo.addItem("Detecting...")
        select_layout.addWidget(self.camera_combo, 1)
        self.btn_refresh = QPushButton("Refresh")
        select_layout.addWidget(self.btn_refresh)
        self.load_defaults_check = QCheckBox("Defaults")
        self.load_defaults_check.setChecked(True)
        select_layout.addWidget(self.load_defaults_check)

        # Second row: Connect and Disconnect buttons
        button_layout = QHBoxLayout()
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        button_layout.addWidget(self.btn_connect)
        button_layout.addWidget(self.btn_disconnect)

        conn_layout.addLayout(select_layout)
        conn_layout.addLayout(button_layout)
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # Preset controls
        preset_group = QGroupBox("Presets")
        preset_layout = QFormLayout()

        # First row: select preset and apply button
        preset_select_layout = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(sorted(self.presets.keys()))
        self.btn_apply_preset = QPushButton("Apply Preset")
        self.btn_apply_preset.clicked.connect(self.apply_preset)
        preset_select_layout.addWidget(self.preset_combo)
        preset_select_layout.addWidget(self.btn_apply_preset)

        # Second row: preset name and save button
        preset_save_layout = QHBoxLayout()
        self.preset_name_input = QLineEdit()
        self.preset_name_input.setPlaceholderText("Enter preset name...")
        self.btn_save_preset = QPushButton("Save as Preset")
        self.btn_save_preset.clicked.connect(self.save_preset)
        preset_save_layout.addWidget(self.preset_name_input)
        preset_save_layout.addWidget(self.btn_save_preset)

        preset_layout.addRow("Select:", preset_select_layout)
        preset_layout.addRow("Name:", preset_save_layout)
        preset_group.setLayout(preset_layout)
        layout.addWidget(preset_group)

        # ROI settings
        roi_group = QGroupBox("ROI")
        roi_layout = QFormLayout()

        self.roi_width = QSpinBox()
        self.roi_width.setRange(16, 4096)
        self.roi_width.setValue(640)

        self.roi_height = QSpinBox()
        self.roi_height.setRange(16, 3072)
        self.roi_height.setValue(480)

        self.roi_offset_x = QSpinBox()
        self.roi_offset_x.setRange(0, 4096)

        self.roi_offset_y = QSpinBox()
        self.roi_offset_y.setRange(0, 3072)

        self.binning_horizontal = QComboBox()
        self.binning_horizontal.addItems(["1", "2", "3", "4"])

        self.binning_vertical = QComboBox()
        self.binning_vertical.addItems(["1", "2", "3", "4"])

        roi_layout.addRow("Width:", self.roi_width)
        roi_layout.addRow("Height:", self.roi_height)
        roi_layout.addRow("Offset X:", self.roi_offset_x)
        roi_layout.addRow("Offset Y:", self.roi_offset_y)
        roi_layout.addRow("Binning H:", self.binning_horizontal)
        roi_layout.addRow("Binning V:", self.binning_vertical)

        ruler_layout = QHBoxLayout()
        ruler_layout.addWidget(QLabel("Rulers:"))
        self.ruler_v_check = QCheckBox("V")
        self.ruler_h_check = QCheckBox("H")
        self.ruler_radial_check = QCheckBox("Radial")
        self.ruler_v_check.toggled.connect(self._on_ruler_changed)
        self.ruler_h_check.toggled.connect(self._on_ruler_changed)
        self.ruler_radial_check.toggled.connect(self._on_ruler_changed)
        ruler_layout.addWidget(self.ruler_v_check)
        ruler_layout.addWidget(self.ruler_h_check)
        ruler_layout.addWidget(self.ruler_radial_check)
        ruler_layout.addStretch()

        roi_layout.addRow("Rulers:", ruler_layout)

        # Add transform controls
        transform_layout = QHBoxLayout()
        transform_layout.addWidget(QLabel("Flip:"))
        self.flip_x_check = QCheckBox("X")
        self.flip_y_check = QCheckBox("Y")
        transform_layout.addWidget(self.flip_x_check)
        transform_layout.addWidget(self.flip_y_check)
        transform_layout.addWidget(QLabel("Rotate:"))
        self.rotation_spin = QComboBox()
        self.rotation_spin.addItems(["0", "90", "180", "270"])
        transform_layout.addWidget(self.rotation_spin)
        transform_layout.addStretch()

        roi_layout.addRow("Transform:", transform_layout)

        # Connect transform signals
        self.flip_x_check.toggled.connect(self._on_transform_changed)
        self.flip_y_check.toggled.connect(self._on_transform_changed)
        self.rotation_spin.currentIndexChanged.connect(self._on_transform_changed)

        roi_group.setLayout(roi_layout)
        layout.addWidget(roi_group)

        # Acquisition settings
        acq_group = QGroupBox("Acquisition")
        acq_layout = QFormLayout()

        self.exposure = QDoubleSpinBox()
        self.exposure.setRange(10, 1000000)
        self.exposure.setValue(150)
        self.exposure.setSuffix(" μs")

        self.gain = QDoubleSpinBox()
        self.gain.setRange(0, 48)
        self.gain.setValue(0)

        self.pixel_format = QComboBox()
        self.pixel_format.addItems(["Mono8", "Mono10", "Mono10p"])

        self.sensor_mode = QComboBox()
        self.sensor_mode.addItems(["Normal", "Fast"])

        acq_layout.addRow("Exposure:", self.exposure)
        acq_layout.addRow("Gain:", self.gain)
        acq_layout.addRow("Pixel Format:", self.pixel_format)
        acq_layout.addRow("Sensor Mode:", self.sensor_mode)

        acq_group.setLayout(acq_layout)
        layout.addWidget(acq_group)

        # Frame Rate Control
        framerate_group = QGroupBox("Frame Rate Control")
        framerate_layout = QFormLayout()

        self.framerate_enable = QCheckBox("Enable Frame Rate Limit")
        self.framerate = QDoubleSpinBox()
        self.framerate.setRange(1, 100000)
        self.framerate.setValue(30)
        self.framerate.setSuffix(" Hz")
        self.framerate.setEnabled(False)
        self.framerate_enable.toggled.connect(self.framerate.setEnabled)

        self.throughput_enable = QCheckBox("Enable Throughput Limit")
        self.throughput_limit = QDoubleSpinBox()
        self.throughput_limit.setRange(1, 1000)
        self.throughput_limit.setValue(125)
        self.throughput_limit.setSuffix(" Mbps")
        self.throughput_limit.setEnabled(False)
        self.throughput_enable.toggled.connect(self.throughput_limit.setEnabled)

        framerate_layout.addRow(self.framerate_enable)
        framerate_layout.addRow("Frame Rate:", self.framerate)
        framerate_layout.addRow(self.throughput_enable)
        framerate_layout.addRow("Throughput:", self.throughput_limit)

        framerate_group.setLayout(framerate_layout)
        layout.addWidget(framerate_group)

        # Capture settings (renamed from Output)
        capture_group = QGroupBox("Capture")
        capture_layout = QFormLayout()

        # Mode selection
        self.capture_mode = QComboBox()
        self.capture_mode.addItems(["ROI Capture", "Waterfall"])
        self.capture_mode.currentTextChanged.connect(self._on_mode_changed)
        capture_layout.addRow("Mode:", self.capture_mode)

        # waterfall settings (initially hidden)
        self.waterfall_lines = QSpinBox()
        self.waterfall_lines.setRange(100, 2000)
        self.waterfall_lines.setValue(500)  # Reduced from 2000 for better performance
        self.waterfall_lines_label = QLabel("Buffer Lines:")
        capture_layout.addRow(self.waterfall_lines_label, self.waterfall_lines)
        self.waterfall_lines.setVisible(False)
        self.waterfall_lines_label.setVisible(False)

        self.deshear_enable = QCheckBox("Apply Deshear")
        self.deshear_enable.setVisible(False)
        capture_layout.addRow("", self.deshear_enable)

        deshear_params_layout = QHBoxLayout()
        self.deshear_angle = QDoubleSpinBox()
        self.deshear_angle.setRange(0, 90)
        self.deshear_angle.setValue(0)
        self.deshear_angle.setSuffix("°")

        self.deshear_px_um = QDoubleSpinBox()
        self.deshear_px_um.setRange(0.1, 100)
        self.deshear_px_um.setValue(3.8)
        self.deshear_px_um.setSuffix(" µm/px")
        self.deshear_px_um.setDecimals(2)

        deshear_params_layout.addWidget(QLabel("Angle:"))
        deshear_params_layout.addWidget(self.deshear_angle)
        deshear_params_layout.addWidget(QLabel("Scale:"))
        deshear_params_layout.addWidget(self.deshear_px_um)
        deshear_params_layout.addStretch()

        self.deshear_params_widget = QWidget()
        self.deshear_params_widget.setLayout(deshear_params_layout)
        self.deshear_params_widget.setVisible(False)
        capture_layout.addRow("", self.deshear_params_widget)

        # Connect deshear enable to show/hide params
        self.deshear_enable.toggled.connect(self.deshear_params_widget.setVisible)

        self.output_path = QLineEdit("./output")
        self.image_prefix = QLineEdit("img")
        self.video_prefix = QLineEdit("vid")

        capture_layout.addRow("Path:", self.output_path)
        capture_layout.addRow("Image Prefix:", self.image_prefix)
        capture_layout.addRow("Video Prefix:", self.video_prefix)

        self.video_fps = QDoubleSpinBox()
        self.video_fps.setRange(1, 120)
        self.video_fps.setValue(24)
        self.video_fps.setSuffix(" fps")
        self.video_fps_label = QLabel("Video FPS:")
        capture_layout.addRow(self.video_fps_label, self.video_fps)

        self.preview_off = QCheckBox("Disable preview during recording")
        self.preview_off.setChecked(True)
        capture_layout.addRow("", self.preview_off)

        self.limit_frames_enable = QCheckBox("Limit frames")
        self.limit_frames = QSpinBox()
        self.limit_frames.setRange(1, 1000000)
        self.limit_frames.setValue(1000)
        self.limit_frames.setEnabled(False)
        self.limit_frames_enable.toggled.connect(self.limit_frames.setEnabled)

        self.limit_time_enable = QCheckBox("Limit time")
        self.limit_time = QDoubleSpinBox()
        self.limit_time.setRange(0.1, 3600)
        self.limit_time.setValue(10)
        self.limit_time.setSuffix(" s")
        self.limit_time.setEnabled(False)
        self.limit_time_enable.toggled.connect(self.limit_time.setEnabled)

        capture_layout.addRow(self.limit_frames_enable)
        capture_layout.addRow("Max frames:", self.limit_frames)
        capture_layout.addRow(self.limit_time_enable)
        capture_layout.addRow("Max time:", self.limit_time)

        capture_group.setLayout(capture_layout)
        layout.addWidget(capture_group)

        # Apply button
        self.btn_apply = QPushButton("Apply Settings")
        self.btn_apply.clicked.connect(self.settings_changed.emit)
        layout.addWidget(self.btn_apply)

        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def _on_mode_changed(self, mode: str):
        """Handle capture mode change"""
        is_waterfall = mode == "Waterfall"

        # Show/hide waterfall-specific settings
        self.waterfall_lines.setVisible(is_waterfall)
        self.waterfall_lines_label.setVisible(is_waterfall)

        self.deshear_enable.setVisible(is_waterfall)
        if not is_waterfall:
            self.deshear_params_widget.setVisible(False)
        else:
            self.deshear_params_widget.setVisible(self.deshear_enable.isChecked())

        # Hide video FPS for waterfall mode
        self.video_fps.setVisible(not is_waterfall)
        self.video_fps_label.setVisible(not is_waterfall)

        # Update frame limit label
        if is_waterfall:
            self.limit_frames_enable.setText("Limit lines")
        else:
            self.limit_frames_enable.setText("Limit frames")

        self.mode_changed.emit(mode)
        log.info(f"Capture mode changed to: {mode}")

    def _on_transform_changed(self):
        """Handle transform settings change"""
        self.transform_changed.emit(
            self.flip_x_check.isChecked(),
            self.flip_y_check.isChecked(),
            int(self.rotation_spin.currentText()),
        )

    def _on_ruler_changed(self):
        """Handle ruler checkbox changes"""
        self.ruler_changed.emit(
            self.ruler_v_check.isChecked(),
            self.ruler_h_check.isChecked(),
            self.ruler_radial_check.isChecked(),
        )

    def apply_preset(self):
        """Apply selected preset"""
        preset_name = self.preset_combo.currentText()
        if preset_name in self.presets:
            preset = self.presets[preset_name]
            for param_name, value in preset.items():
                self.set_parameter_value(param_name, value)
            log.info(f"Applied preset: {preset_name}")
            self.settings_changed.emit()

    def update_parameter_limits(
        self, param_name: str, min_val=None, max_val=None, inc=None, options=None
    ):
        """Update parameter limits/options from app.py"""
        widget_map = {
            "Width": self.roi_width,
            "Height": self.roi_height,
            "OffsetX": self.roi_offset_x,
            "OffsetY": self.roi_offset_y,
            "ExposureTime": self.exposure,
            "Gain": self.gain,
            "AcquisitionFrameRate": self.framerate,
        }

        if param_name in widget_map:
            widget = widget_map[param_name]
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                if min_val is not None and max_val is not None:
                    widget.setRange(min_val, max_val)
                if inc is not None:
                    widget.setSingleStep(inc)

        if param_name == "PixelFormat" and options:
            self.pixel_format.clear()
            self.pixel_format.addItems(options)
        elif param_name == "SensorReadoutMode" and options:
            self.sensor_mode.clear()
            self.sensor_mode.addItems(options)

    def set_parameter_value(self, param_name: str, value):
        """Set a parameter value from app.py"""
        widget_map = {
            "Width": self.roi_width,
            "Height": self.roi_height,
            "OffsetX": self.roi_offset_x,
            "OffsetY": self.roi_offset_y,
            "ExposureTime": self.exposure,
            "Gain": self.gain,
            "BinningHorizontal": self.binning_horizontal,
            "BinningVertical": self.binning_vertical,
            "PixelFormat": self.pixel_format,
            "SensorReadoutMode": self.sensor_mode,
        }

        if param_name in widget_map:
            widget = widget_map[param_name]
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(value)
            elif isinstance(widget, QComboBox):
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)

    def disable_parameter(self, param_name: str):
        """Disable a parameter that doesn't exist in camera"""
        widget_map = {
            "SensorReadoutMode": self.sensor_mode,
            "BinningHorizontal": self.binning_horizontal,
            "BinningVertical": self.binning_vertical,
            "AcquisitionFrameRate": (self.framerate_enable, self.framerate),
            "DeviceLinkThroughputLimit": (
                self.throughput_enable,
                self.throughput_limit,
            ),
        }

        if param_name in widget_map:
            widget = widget_map[param_name]
            if isinstance(widget, tuple):
                for w in widget:
                    w.setEnabled(False)
                    w.setToolTip(f"{param_name} not supported by this camera")
            else:
                widget.setEnabled(False)
                widget.setToolTip(f"{param_name} not supported by this camera")
            log.debug(f"GUI - Disabled {param_name} - not available in camera")

    def get_settings(self) -> dict:
        """Get all settings as dictionary"""
        return {
            "roi": {
                "width": self.roi_width.value(),
                "height": self.roi_height.value(),
                "offset_x": self.roi_offset_x.value(),
                "offset_y": self.roi_offset_y.value(),
                "binning_h": int(self.binning_horizontal.currentText())
                if self.binning_horizontal.isEnabled()
                else 1,
                "binning_v": int(self.binning_vertical.currentText())
                if self.binning_vertical.isEnabled()
                else 1,
            },
            "acquisition": {
                "exposure": self.exposure.value(),
                "gain": self.gain.value(),
                "pixel_format": self.pixel_format.currentText(),
                "sensor_mode": self.sensor_mode.currentText()
                if self.sensor_mode.isEnabled()
                else None,
            },
            "framerate": {
                "enabled": self.framerate_enable.isChecked()
                and self.framerate_enable.isEnabled(),
                "fps": self.framerate.value(),
                "throughput_enabled": self.throughput_enable.isChecked()
                and self.throughput_enable.isEnabled(),
                "throughput_limit": self.throughput_limit.value(),
            },
            "capture": {  # Renamed from 'output'
                "mode": self.capture_mode.currentText(),
                "waterfall_lines": self.waterfall_lines.value(),
                "path": self.output_path.text(),
                "image_prefix": self.image_prefix.text(),
                "video_prefix": self.video_prefix.text(),
                "video_fps": self.video_fps.value(),
                "preview_off": self.preview_off.isChecked(),
                "limit_frames": self.limit_frames.value()
                if self.limit_frames_enable.isChecked()
                else None,
                "limit_time": self.limit_time.value()
                if self.limit_time_enable.isChecked()
                else None,
                "deshear_enabled": self.deshear_enable.isChecked()
                if self.deshear_enable.isVisible()
                else False,
                "deshear_angle": self.deshear_angle.value(),
                "deshear_px_um": self.deshear_px_um.value(),
            },
            "transform": {
                "flip_x": self.flip_x_check.isChecked(),
                "flip_y": self.flip_y_check.isChecked(),
                "rotation": int(self.rotation_spin.currentText()),
            },
        }


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

        # Left: preview (expandable)
        layout.addWidget(self.preview, 3)

        # Right: settings + log (fixed width)
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
