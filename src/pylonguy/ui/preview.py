"""Preview widget - Camera display with zero-copy rendering"""

import dropletui as ui
from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
)
import numpy as np
import logging

log = logging.getLogger("pylonguy")


class PreviewDisplay(QWidget):
    """Pure zero-copy frame display"""

    selection_changed = Signal(object)

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

        self.setMouseTracking(True)

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
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        # Draw message if set
        if self.message:
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, self.message
            )
            return

        # Draw frame if available
        if self.current_frame is not None:
            # Create QImage wrapper every time
            h, w = self.current_frame.shape[:2]

            if len(self.current_frame.shape) == 2:
                # Grayscale
                qimage = QImage(
                    self.current_frame.data,
                    w,
                    h,
                    w,
                    QImage.Format.Format_Grayscale8,
                )
            else:
                # RGB
                qimage = QImage(
                    self.current_frame.data,
                    w,
                    h,
                    w * 3,
                    QImage.Format.Format_RGB888,
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
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
                painter.drawImage(offset_rect, scaled_image)
                painter.restore()
            else:
                # Scale and draw directly
                scaled_image = qimage.scaled(
                    self.frame_rect.width(),
                    self.frame_rect.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
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
            pen = QPen(QColor(0, 180, 255), 2, Qt.PenStyle.DashLine)
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
            painter.setPen(
                QPen(QColor(255, 255, 0, 180), 1, Qt.PenStyle.SolidLine)
            )

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
                        Qt.AlignmentFlag.AlignCenter,
                        label_text,
                    )
                    painter.setPen(QPen(QColor(255, 255, 0), 1))
                    painter.drawText(
                        int(x_label - 14),
                        int(y_label - 6),
                        28,
                        10,
                        Qt.AlignmentFlag.AlignCenter,
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
        if event.button() == Qt.MouseButton.LeftButton:
            self.select_start = event.position().toPoint()
            self.selecting = True
            self.selection_rect = None

    def mouseMoveEvent(self, event):
        """Track selection"""
        self.mouse_pos = event.position().toPoint()
        if self.selecting:
            self.update()

    def mouseReleaseEvent(self, event):
        """Finish selection"""
        if event.button() == Qt.MouseButton.LeftButton and self.selecting:
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
    """Preview control panel - status and buttons"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def _create_status_section(self, label_text: str, initial_value: str = "0"):
        """Create a dropletui metric readout and expose its labels."""
        widget = ui.metric_readout(label_text, initial_value, kind="success")
        layout = widget.layout()
        label = layout.itemAt(0).widget()
        value = layout.itemAt(1).widget()
        return widget, label, value

    def init_ui(self):
        layout = QVBoxLayout()

        # Status bar
        fps_widget, _, self.fps_value = self._create_status_section("FPS", "0.0")
        rec_widget, _, self.rec_status = self._create_status_section("REC", "OFF")
        frames_widget, self.frames_label, self.rec_frames = self._create_status_section("FRAMES", "0")
        time_widget, _, self.rec_time = self._create_status_section("TIME", "0.0s")
        roi_widget, _, self.roi_value = self._create_status_section("ROI", "---")
        sel_widget, _, self.sel_value = self._create_status_section("SEL", "None")

        status_widget = ui.hbox(
            fps_widget,
            rec_widget,
            frames_widget,
            time_widget,
            roi_widget,
            sel_widget,
        )
        layout.addWidget(status_widget)

        # Control buttons
        self.btn_live = ui.button("Start Live", flat=True)
        self.btn_capture = ui.button("Capture", flat=True)
        self.btn_record = ui.button("Record", flat=True)
        self.btn_clear_selection = ui.button("Clear Selection", flat=True)

        button_widget = ui.hbox(
            self.btn_live,
            self.btn_capture,
            self.btn_record,
            self.btn_clear_selection,
        )
        layout.addWidget(button_widget)

        self.setLayout(layout)

    def updateStatus(self, **kwargs):
        """Update status displays"""
        if "fps" in kwargs:
            self.fps_value.setText(f" {kwargs['fps']:.1f} ")

        if "recording" in kwargs:
            if kwargs["recording"]:
                self.rec_status.setText(" ON ")
            else:
                self.rec_status.setText(" OFF ")

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
    selection_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Display area
        self.display = PreviewDisplay()
        layout.addWidget(self.display, 1)

        # Controls area
        self.controls = PreviewControls()
        layout.addWidget(self.controls)

        # Connect internal signals
        self.display.selection_changed.connect(self._on_selection_changed)
        self.controls.btn_clear_selection.clicked.connect(self.clear_selection)

        # Create references for backward compatibility
        self.btn_live = self.controls.btn_live
        self.btn_capture = self.controls.btn_capture
        self.btn_record = self.controls.btn_record

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
