"""Preview widget - Camera display with zero-copy rendering"""

from PyQt5.QtCore import Qt, pyqtSignal, QRect, pyqtSlot
from PyQt5.QtGui import QImage, QPainter, QColor, QPen, QTransform, QFont
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSizePolicy,
)
import numpy as np
import logging

log = logging.getLogger("pylonguy")


class PreviewDisplay(QWidget):
    """Pure zero-copy frame display"""

    selection_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()

        # Frame data
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

        # Message display
        self.message = ""

        # Setup widget
        self.setMouseTracking(True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), Qt.black)
        self.setPalette(pal)

    def setFrame(self, frame: np.ndarray):
        """Frame update - returns False if buffer needs reinitialization"""
        if frame is None:
            return True

        if self.waterfall_mode and self.waterfall_buffer is not None:
            # Extract line from frame
            if len(frame.shape) == 2:
                line = frame[0, :].astype(np.uint8)
            elif len(frame.shape) == 1:
                line = frame.astype(np.uint8)
            else:
                return True

            # Check if width changed
            if len(line) != self.waterfall_buffer.shape[1]:
                log.debug(
                    f"Width mismatch: line={len(line)}, buffer={self.waterfall_buffer.shape[1]}"
                )
                self.waterfall_buffer = None
                self.waterfall_row = 0
                return False  # Signal reinit needed

            # Add to buffer
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
            # Normal mode
            if frame.dtype == np.uint16:
                frame = (frame >> 8).astype(np.uint8)
            self.current_frame = frame

        self.message = ""
        self.update()
        return True

    def showMessage(self, text: str):
        """Show text message"""
        self.message = text
        self.current_frame = None
        self.update()

    def paintEvent(self, event):
        """Frame painting"""
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
            # Create QImage wrapper every time
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

        # Display area
        self.display = PreviewDisplay()
        self.display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.display)

        # Controls area
        self.controls = PreviewControls()
        self.controls.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.controls.setMaximumHeight(150)
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
        return self.display.setFrame(frame)

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
