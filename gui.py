import sys
import logging
import time
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import *
import numpy as np

from camera import Camera
from video_writer import VideoWriter
from config import Config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("pylon_gui")

def frame_to_8bit(frame, pixel_format=""):
    """Convert frame to 8-bit for display/saving"""
    if frame.dtype == np.uint16:
        if "10" in pixel_format:
            return (frame >> 2).astype(np.uint8)  # 10-bit to 8-bit
        elif "12" in pixel_format:
            return (frame >> 4).astype(np.uint8)  # 12-bit to 8-bit
        else:
            return (frame >> 8).astype(np.uint8)  # 16-bit to 8-bit
    return frame

class CameraThread(QThread):
    frame_ready = pyqtSignal(np.ndarray)
    fps_update = pyqtSignal(float, int)  # fps, total_frames

    def __init__(self, camera: Camera):
        super().__init__()
        self.camera = camera
        self.running = False
        self.writer = None
        self.recording = False
        self.frame_count = 0
        self.fps = 0.0
        self.last_fps_time = 0
        self.last_fps_count = 0
        self.record_start_time = 0
        self.max_frames = None
        self.max_seconds = None

    def run(self):
        self.running = True
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.last_fps_count = 0

        while self.running:
            # Grab single raw frame
            frame = self.camera.grab_frame(1000)

            if frame is not None:
                # Emit frame for preview
                self.frame_ready.emit(frame)

                # Write to video if recording
                if self.recording and self.writer:
                    if self.writer.write_frame(frame):
                        self.frame_count += 1

                        # Check recording limits
                        if self.max_frames and self.frame_count >= self.max_frames:
                            log.info(f"Recording limit reached: {self.max_frames} frames")
                            self.running = False
                            break

                        if self.max_seconds:
                            elapsed = time.time() - self.record_start_time
                            if elapsed >= self.max_seconds:
                                log.info(f"Recording time limit reached: {self.max_seconds} seconds")
                                self.running = False
                                break

                # Calculate FPS (always, not just when recording)
                current_time = time.time()
                time_diff = current_time - self.last_fps_time
                if time_diff >= 1.0:
                    if self.recording:
                        frames_diff = self.frame_count - self.last_fps_count
                        self.fps = frames_diff / time_diff
                        self.last_fps_count = self.frame_count
                        self.fps_update.emit(self.fps, self.frame_count)
                    self.last_fps_time = current_time
            else:
                self.msleep(30)

    def stop(self):
        self.running = False
        if self.recording and self.writer:
            try:
                self.writer.stop()
            except:
                pass
            self.writer = None
            self.recording = False
        self.wait(2000)

    def start_recording(self, writer: VideoWriter, max_frames=None, max_seconds=None):
        self.writer = writer
        self.frame_count = 0
        self.max_frames = max_frames
        self.max_seconds = max_seconds
        self.record_start_time = time.time()

        if self.writer and self.writer.start():
            self.recording = True
            log.info("Recording started in thread")
        else:
            log.error("Failed to start video writer")
            self.recording = False
            self.writer = None

    def stop_recording(self) -> int:
        frames = self.frame_count
        self.recording = False

        if self.writer:
            try:
                self.writer.stop()
            except Exception as e:
                log.error(f"Error stopping writer: {e}")
            self.writer = None

        return frames

class PreviewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.pixmap = None
        self.selection_rect = None
        self.selection_start = None
        self.selection_end = None
        self.mouse_pos = QPoint(0, 0)
        self.image_offset = QPoint(0, 0)
        self.camera_size = None  # Actual ROI dimensions (width x height from settings)
        self.scale_factor = 1.0
        self.dragging = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Display area - fixed size for stability
        self.display = QLabel("No Camera Connected")
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setFixedSize(800, 600)
        self.display.setStyleSheet("border: none; background: #000;")
        self.display.setMouseTracking(True)
        self.display.installEventFilter(self)
        layout.addWidget(self.display)

        # Status caption with dark background
        self.status_label = QLabel("Camera: Not connected | Position: (0, 0)")
        self.status_label.setStyleSheet("""
            padding: 5px;
            background: #2b2b2b;
            color: #ffffff;
            font-size: 12px;
        """)
        layout.addWidget(self.status_label)

        # Control buttons
        button_layout = QHBoxLayout()

        self.btn_live = QPushButton("Start Live")
        self.btn_live.setCheckable(True)
        button_layout.addWidget(self.btn_live)

        self.btn_capture = QPushButton("Capture")
        button_layout.addWidget(self.btn_capture)

        self.btn_record = QPushButton("Record")
        self.btn_record.setCheckable(True)
        button_layout.addWidget(self.btn_record)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def set_camera_size(self, width, height):
        """Set actual camera ROI dimensions"""
        if width and height:
            self.camera_size = (width, height)
        else:
            self.camera_size = None
        self.update_status()

    def eventFilter(self, source, event):
        if source != self.display:
            return super().eventFilter(source, event)

        event_type = event.type()
        if event_type == event.MouseMove:
            self.handle_mouse_move(event.pos(), event.buttons() == Qt.LeftButton)
        elif event_type == event.MouseButtonPress and event.button() == Qt.LeftButton:
            self.handle_mouse_press(event.pos())
        elif event_type == event.MouseButtonRelease and event.button() == Qt.LeftButton:
            self.handle_mouse_release(event.pos())

        return super().eventFilter(source, event)

    def handle_mouse_move(self, pos, is_dragging):
        """Handle mouse movement and dragging"""
        self.update_mouse_position(pos)
        if is_dragging and self.selection_start:
            self.dragging = True
            self.selection_end = self.to_camera_coords(pos)
            self.redraw()
            if self.selection_end:
                self.update_temp_selection_status()

    def handle_mouse_press(self, pos):
        """Start new selection"""
        self.selection_rect = None
        self.selection_end = None
        self.selection_start = self.to_camera_coords(pos)
        self.dragging = True
        self.redraw()

    def handle_mouse_release(self, pos):
        """Finalize or clear selection"""
        if not self.selection_start or not self.dragging:
            return

        self.selection_end = self.to_camera_coords(pos)
        self.dragging = False

        if self.selection_start != self.selection_end:
            # Create selection rectangle
            x1, y1 = self.selection_start.x(), self.selection_start.y()
            x2, y2 = self.selection_end.x(), self.selection_end.y()
            self.selection_rect = QRect(
                min(x1, x2), min(y1, y2),
                abs(x2 - x1), abs(y2 - y1)
            )
        else:
            # Single click - clear selection
            self.selection_rect = None
            self.selection_start = None
            self.selection_end = None

        self.redraw()
        self.update_status()

    def update_mouse_position(self, display_pos):
        """Update mouse position in camera coordinates"""
        if not self.camera_size or not self.pixmap:
            return

        # Get position relative to displayed image
        rel_x = display_pos.x() - self.image_offset.x()
        rel_y = display_pos.y() - self.image_offset.y()

        # Check if mouse is over the image
        scaled_width = self.pixmap.width() * self.scale_factor
        scaled_height = self.pixmap.height() * self.scale_factor

        if 0 <= rel_x <= scaled_width and 0 <= rel_y <= scaled_height:
            # Convert to camera ROI coordinates
            cam_x = int(rel_x / self.scale_factor)
            cam_y = int(rel_y / self.scale_factor)

            # Clamp to ROI bounds
            cam_x = max(0, min(cam_x, self.camera_size[0] - 1))
            cam_y = max(0, min(cam_y, self.camera_size[1] - 1))

            self.mouse_pos = QPoint(cam_x, cam_y)
            self.update_status()

    def to_camera_coords(self, display_pos):
        """Convert display position to camera ROI coordinates"""
        if not self.camera_size or not self.pixmap:
            return QPoint(0, 0)

        # Get position relative to displayed image
        rel_x = display_pos.x() - self.image_offset.x()
        rel_y = display_pos.y() - self.image_offset.y()

        # Convert to camera coordinates
        cam_x = int(rel_x / self.scale_factor)
        cam_y = int(rel_y / self.scale_factor)

        # Clamp to ROI bounds
        cam_x = max(0, min(cam_x, self.camera_size[0] - 1))
        cam_y = max(0, min(cam_y, self.camera_size[1] - 1))

        return QPoint(cam_x, cam_y)

    def update_frame(self, pixmap: QPixmap):
        """Update displayed frame - pixmap dimensions should match camera ROI"""
        self.pixmap = pixmap
        # The pixmap dimensions ARE the camera ROI dimensions
        if not self.camera_size:
            self.camera_size = (pixmap.width(), pixmap.height())
        self.redraw()

    def redraw(self):
        """Redraw the display with current frame and selection"""
        if not self.pixmap:
            return

        self.redraw_with_selection()

    def redraw_with_selection(self):
        """Redraw with selection overlay"""
        # Scale pixmap to maximum size that fits in display
        display_size = self.display.size()
        scaled = self.pixmap.scaled(display_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.scale_factor = scaled.width() / float(self.pixmap.width())

        # Calculate offset for centering
        self.image_offset = QPoint(
            (display_size.width() - scaled.width()) // 2,
            (display_size.height() - scaled.height()) // 2
        )

        # Create display pixmap
        display_pixmap = QPixmap(display_size)
        display_pixmap.fill(Qt.black)

        painter = QPainter(display_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(self.image_offset, scaled)

        # Draw selection overlay
        self.draw_selection(painter)

        painter.end()
        self.display.setPixmap(display_pixmap)

    def draw_selection(self, painter):
        """Draw selection rectangle on the painter"""
        if not (self.selection_rect or (self.selection_start and self.selection_end and self.dragging)):
            return

        # Semi-transparent blue fill
        painter.setBrush(QColor(0, 120, 255, 115))  # Alpha ~0.45
        painter.setPen(Qt.NoPen)

        if self.selection_rect and not self.dragging:
            # Draw finalized selection
            rect = self.scale_rect_to_display(self.selection_rect)
            painter.drawRect(rect)
        elif self.selection_start and self.selection_end and self.dragging:
            # Draw temporary selection during drag
            rect = self.create_temp_rect()
            painter.drawRect(self.scale_rect_to_display(rect))

    def scale_rect_to_display(self, rect):
        """Convert camera coordinates rectangle to display coordinates"""
        return QRect(
            int(rect.x() * self.scale_factor + self.image_offset.x()),
            int(rect.y() * self.scale_factor + self.image_offset.y()),
            int(rect.width() * self.scale_factor),
            int(rect.height() * self.scale_factor)
        )

    def create_temp_rect(self):
        """Create temporary rectangle from selection points"""
        if not self.selection_start or not self.selection_end:
            return QRect()
        x1, y1 = self.selection_start.x(), self.selection_start.y()
        x2, y2 = self.selection_end.x(), self.selection_end.y()
        return QRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

    def update_status(self, fps=None, frames=None):
        """Update status bar text"""
        parts = []

        # Camera info
        if self.camera_size:
            parts.append(f"ROI: {self.camera_size[0]}x{self.camera_size[1]}")
        else:
            parts.append("Camera: Not connected")

        # Mouse position
        parts.append(f"Pos: ({self.mouse_pos.x()}, {self.mouse_pos.y()})")

        # Selection info
        if self.selection_rect:
            area = self.selection_rect.width() * self.selection_rect.height()
            parts.append(f"Sel: {self.selection_rect.width()}x{self.selection_rect.height()} ({area:,} px²)")

        # Recording info
        if fps is not None and frames is not None:
            parts.append(f"REC: {fps:.1f} fps, {frames} frames")

        self.status_label.setText(" | ".join(parts))

    def update_temp_selection_status(self):
        """Update status during selection drag"""
        if not self.selection_start or not self.selection_end:
            return

        rect = self.create_temp_rect()
        area = rect.width() * rect.height()

        parts = []
        if self.camera_size:
            parts.append(f"ROI: {self.camera_size[0]}x{self.camera_size[1]}")
        else:
            parts.append("Camera: Not connected")
        parts.append(f"Pos: ({self.mouse_pos.x()}, {self.mouse_pos.y()})")
        parts.append(f"Selecting: {rect.width()}x{rect.height()} ({area:,} px²)")

        self.status_label.setText(" | ".join(parts))

class SettingsWidget(QWidget):
    def __init__(self, config: Config, camera: Camera):
        super().__init__()
        self.config = config
        self.camera = camera
        self.init_ui()

    def init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout()

        # Connection Section
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        conn_layout.addWidget(self.btn_connect)
        conn_layout.addWidget(self.btn_disconnect)
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # Geometry Section
        geom_group = QGroupBox("Geometry")
        geom_layout = QFormLayout()

        self.width_spin = QSpinBox()
        self.width_spin.setRange(160, 4096)
        self.width_spin.setValue(self.config.width)
        geom_layout.addRow("Width:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(120, 3072)
        self.height_spin.setValue(self.config.height)
        geom_layout.addRow("Height:", self.height_spin)

        self.offset_x_spin = QSpinBox()
        self.offset_x_spin.setRange(0, 4096)
        self.offset_x_spin.setValue(self.config.offset_x)
        geom_layout.addRow("Offset X:", self.offset_x_spin)

        self.offset_y_spin = QSpinBox()
        self.offset_y_spin.setRange(0, 3072)
        self.offset_y_spin.setValue(self.config.offset_y)
        geom_layout.addRow("Offset Y:", self.offset_y_spin)

        geom_group.setLayout(geom_layout)
        layout.addWidget(geom_group)

        # Acquisition Section
        acq_group = QGroupBox("Acquisition")
        acq_layout = QFormLayout()

        self.exposure_spin = QDoubleSpinBox()
        self.exposure_spin.setRange(10, 1000000)
        self.exposure_spin.setValue(self.config.exposure)
        self.exposure_spin.setSuffix(" μs")
        acq_layout.addRow("Exposure:", self.exposure_spin)

        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(0, 48)
        self.gain_spin.setValue(self.config.gain)
        self.gain_spin.setSuffix(" dB")
        acq_layout.addRow("Gain:", self.gain_spin)

        self.sensor_mode_combo = QComboBox()
        self.sensor_mode_combo.addItems(["Normal", "Fast"])
        self.sensor_mode_combo.setCurrentText(self.config.sensor_readout_mode)
        acq_layout.addRow("Sensor Readout Mode:", self.sensor_mode_combo)

        self.framerate_enable_check = QCheckBox("Enable")
        self.framerate_enable_check.setChecked(self.config.acquisition_framerate_enable)
        self.framerate_spin = QDoubleSpinBox()
        self.framerate_spin.setRange(1, 1000)
        self.framerate_spin.setValue(self.config.acquisition_framerate)
        self.framerate_spin.setSuffix(" Hz")
        framerate_widget = QWidget()
        framerate_layout = QHBoxLayout()
        framerate_layout.setContentsMargins(0, 0, 0, 0)
        framerate_layout.addWidget(self.framerate_enable_check)
        framerate_layout.addWidget(self.framerate_spin)
        framerate_widget.setLayout(framerate_layout)
        acq_layout.addRow("Acquisition Framerate:", framerate_widget)

        acq_group.setLayout(acq_layout)
        layout.addWidget(acq_group)

        # Output Section
        output_group = QGroupBox("Output")
        output_layout = QFormLayout()

        self.images_path = QLineEdit(self.config.images_dir)
        images_btn = QPushButton("Browse...")
        images_btn.clicked.connect(lambda: self.browse_folder(self.images_path))
        images_widget = QWidget()
        images_hlayout = QHBoxLayout()
        images_hlayout.setContentsMargins(0, 0, 0, 0)
        images_hlayout.addWidget(self.images_path)
        images_hlayout.addWidget(images_btn)
        images_widget.setLayout(images_hlayout)
        output_layout.addRow("Images:", images_widget)

        self.videos_path = QLineEdit(self.config.videos_dir)
        videos_btn = QPushButton("Browse...")
        videos_btn.clicked.connect(lambda: self.browse_folder(self.videos_path))
        videos_widget = QWidget()
        videos_hlayout = QHBoxLayout()
        videos_hlayout.setContentsMargins(0, 0, 0, 0)
        videos_hlayout.addWidget(self.videos_path)
        videos_hlayout.addWidget(videos_btn)
        videos_widget.setLayout(videos_hlayout)
        output_layout.addRow("Videos:", videos_widget)

        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(self.config.video_fps)
        self.fps_spin.setSuffix(" fps")
        output_layout.addRow("Video FPS:", self.fps_spin)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Recording Limits Section
        limits_group = QGroupBox("Recording Limits (Optional)")
        limits_layout = QFormLayout()

        self.limit_frames_check = QCheckBox("Limit frames")
        self.limit_frames_spin = QSpinBox()
        self.limit_frames_spin.setRange(1, 1000000)
        self.limit_frames_spin.setValue(self.config.record_limit_frames or 1000)
        self.limit_frames_spin.setEnabled(False)
        self.limit_frames_check.toggled.connect(self.limit_frames_spin.setEnabled)
        frames_widget = QWidget()
        frames_layout = QHBoxLayout()
        frames_layout.setContentsMargins(0, 0, 0, 0)
        frames_layout.addWidget(self.limit_frames_check)
        frames_layout.addWidget(self.limit_frames_spin)
        frames_widget.setLayout(frames_layout)
        limits_layout.addRow("Max Frames:", frames_widget)

        self.limit_seconds_check = QCheckBox("Limit time")
        self.limit_seconds_spin = QDoubleSpinBox()
        self.limit_seconds_spin.setRange(0.1, 3600)
        self.limit_seconds_spin.setValue(self.config.record_limit_seconds or 10.0)
        self.limit_seconds_spin.setSuffix(" s")
        self.limit_seconds_spin.setEnabled(False)
        self.limit_seconds_check.toggled.connect(self.limit_seconds_spin.setEnabled)
        seconds_widget = QWidget()
        seconds_layout = QHBoxLayout()
        seconds_layout.setContentsMargins(0, 0, 0, 0)
        seconds_layout.addWidget(self.limit_seconds_check)
        seconds_layout.addWidget(self.limit_seconds_spin)
        seconds_widget.setLayout(seconds_layout)
        limits_layout.addRow("Max Time:", seconds_widget)

        limits_group.setLayout(limits_layout)
        layout.addWidget(limits_group)

        # Apply button
        self.btn_apply = QPushButton("Apply Settings")
        layout.addWidget(self.btn_apply)

        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)

        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def browse_folder(self, line_edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory", line_edit.text())
        if folder:
            line_edit.setText(folder)

    def update_config(self):
        self.config.width = self.width_spin.value()
        self.config.height = self.height_spin.value()
        self.config.offset_x = self.offset_x_spin.value()
        self.config.offset_y = self.offset_y_spin.value()
        self.config.exposure = self.exposure_spin.value()
        self.config.gain = self.gain_spin.value()
        self.config.sensor_readout_mode = self.sensor_mode_combo.currentText()
        self.config.acquisition_framerate_enable = self.framerate_enable_check.isChecked()
        self.config.acquisition_framerate = self.framerate_spin.value()
        self.config.images_dir = self.images_path.text()
        self.config.videos_dir = self.videos_path.text()
        self.config.video_fps = self.fps_spin.value()

        # Recording limits
        self.config.record_limit_frames = self.limit_frames_spin.value() if self.limit_frames_check.isChecked() else None
        self.config.record_limit_seconds = self.limit_seconds_spin.value() if self.limit_seconds_check.isChecked() else None

    def update_limits_from_camera(self):
        """Update spin box limits based on actual camera capabilities"""
        if not self.camera.is_connected():
            return

        # Get sensor dimensions to set ROI limits
        sensor_width_min, sensor_width_max, _ = self.camera.get_parameter_range("Width")
        sensor_height_min, sensor_height_max, _ = self.camera.get_parameter_range("Height")

        if sensor_width_max and sensor_height_max:
            # Width/Height limits depend on offsets
            self.width_spin.setRange(sensor_width_min or 16, sensor_width_max)
            self.height_spin.setRange(sensor_height_min or 16, sensor_height_max)

            # Offset limits
            self.offset_x_spin.setRange(0, sensor_width_max - sensor_width_min)
            self.offset_y_spin.setRange(0, sensor_height_max - sensor_height_min)

            log.info(f"Sensor size: {sensor_width_max}x{sensor_height_max}")

        # Update exposure limits
        min_exp, max_exp, _ = self.camera.get_parameter_range("ExposureTime")
        if min_exp is not None and max_exp is not None:
            self.exposure_spin.setRange(min_exp, max_exp)
            # Validate current value
            current = self.camera.validate_and_get_default("ExposureTime", self.config.exposure)
            self.exposure_spin.setValue(current)
            log.info(f"Exposure range: {min_exp} - {max_exp} μs")

        # Update gain limits
        min_gain, max_gain, _ = self.camera.get_parameter_range("Gain")
        if min_gain is not None and max_gain is not None:
            self.gain_spin.setRange(min_gain, max_gain)
            current = self.camera.validate_and_get_default("Gain", self.config.gain)
            self.gain_spin.setValue(current)
            log.info(f"Gain range: {min_gain} - {max_gain} dB")

        # Update sensor readout modes
        modes = self.camera.get_enum_values("SensorReadoutMode")
        if modes:
            self.sensor_mode_combo.clear()
            self.sensor_mode_combo.addItems(modes)
            if self.config.sensor_readout_mode in modes:
                self.sensor_mode_combo.setCurrentText(self.config.sensor_readout_mode)

        # Update framerate limits
        min_fps, max_fps, _ = self.camera.get_parameter_range("AcquisitionFrameRate")
        if min_fps is not None and max_fps is not None:
            self.framerate_spin.setRange(min_fps, max_fps)
            current = self.camera.validate_and_get_default("AcquisitionFrameRate", self.config.acquisition_framerate)
            self.framerate_spin.setValue(current)
            log.info(f"Framerate range: {min_fps} - {max_fps} Hz")

        # Connect offset changes to update width/height limits
        self.offset_x_spin.valueChanged.connect(self.update_roi_limits)
        self.offset_y_spin.valueChanged.connect(self.update_roi_limits)

    def update_roi_limits(self):
        """Update width/height limits based on current offset values"""
        if not self.camera.is_connected():
            return

        # Get sensor max dimensions
        _, sensor_width_max, _ = self.camera.get_parameter_range("Width")
        _, sensor_height_max, _ = self.camera.get_parameter_range("Height")

        if sensor_width_max and sensor_height_max:
            # Maximum width = sensor width - offset X
            max_width = sensor_width_max - self.offset_x_spin.value()
            self.width_spin.setMaximum(max_width)
            if self.width_spin.value() > max_width:
                self.width_spin.setValue(max_width)

            # Maximum height = sensor height - offset Y
            max_height = sensor_height_max - self.offset_y_spin.value()
            self.height_spin.setMaximum(max_height)
            if self.height_spin.value() > max_height:
                self.height_spin.setValue(max_height)

class LogWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        label = QLabel("Log")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        layout.addWidget(self.log_text)

        self.setLayout(layout)

    def add_log(self, message: str):
        self.log_text.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.camera = Camera()
        self.config = Config()
        self.camera_thread = None
        self.recording = False
        self.last_frame = None

        self.init_ui()
        self.setup_logging()

    def init_ui(self):
        self.setWindowTitle("Pylon Camera GUI")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout
        main_layout = QHBoxLayout()

        # Left side - Preview
        self.preview = PreviewWidget()
        main_layout.addWidget(self.preview, 2)

        # Right side - Settings and Log
        right_layout = QVBoxLayout()

        self.settings = SettingsWidget(self.config, self.camera)
        right_layout.addWidget(self.settings, 3)

        self.log_widget = LogWidget()
        right_layout.addWidget(self.log_widget, 1)

        main_layout.addLayout(right_layout, 1)
        central.setLayout(main_layout)

        # Connect signals
        self.preview.btn_live.clicked.connect(self.toggle_live)
        self.preview.btn_capture.clicked.connect(self.capture_image)
        self.preview.btn_record.clicked.connect(self.toggle_recording)

        self.settings.btn_connect.clicked.connect(self.connect_camera)
        self.settings.btn_disconnect.clicked.connect(self.disconnect_camera)
        self.settings.btn_apply.clicked.connect(self.apply_settings)

    def setup_logging(self):
        # Custom log handler to display in GUI
        class GuiLogHandler(logging.Handler):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback

            def emit(self, record):
                msg = self.format(record)
                self.callback(msg)

        handler = GuiLogHandler(self.log_widget.add_log)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s',
                                              datefmt='%H:%M:%S'))
        log.addHandler(handler)

        log.info("Application started")

    def connect_camera(self):
        if self.camera.connect():
            # Get actual ROI dimensions from camera
            width = self.camera.get_parameter("Width", self.config.width)
            height = self.camera.get_parameter("Height", self.config.height)
            pixel_format = self.camera.get_pixel_format()

            self.preview.set_camera_size(width, height)
            self.settings.update_limits_from_camera()

            self.preview.display.setText("Camera Connected - Press 'Start Live' to begin")
            log.info(f"Connected - ROI: {width}x{height}, Format: {pixel_format}")
        else:
            log.error("Failed to connect camera")

    def disconnect_camera(self):
        self.stop_live()
        self.camera.disconnect()
        self.preview.display.setText("No Camera Connected")
        self.preview.display.setPixmap(QPixmap())
        self.preview.set_camera_size(None, None)  # Clear camera size

    def apply_settings(self):
        self.settings.update_config()

        if not self.camera.is_connected():
            log.warning("Camera not connected - settings saved")
            return

        # Apply ROI settings
        self.camera.set_parameter("Width", self.config.width)
        self.camera.set_parameter("Height", self.config.height)
        self.camera.set_parameter("OffsetX", self.config.offset_x)
        self.camera.set_parameter("OffsetY", self.config.offset_y)

        # Get actual ROI after applying
        actual_width = self.camera.get_parameter("Width", self.config.width)
        actual_height = self.camera.get_parameter("Height", self.config.height)
        self.preview.set_camera_size(actual_width, actual_height)

        # Apply other settings
        self.camera.set_parameter("ExposureTime", self.config.exposure)
        self.camera.set_parameter("Gain", self.config.gain)
        self.camera.set_enum_parameter("SensorReadoutMode", self.config.sensor_readout_mode)

        # Framerate
        if self.config.acquisition_framerate_enable:
            self.camera.set_parameter("AcquisitionFrameRateEnable", True)
            self.camera.set_parameter("AcquisitionFrameRate", self.config.acquisition_framerate)
        else:
            self.camera.set_parameter("AcquisitionFrameRateEnable", False)

        log.info(f"Settings applied - ROI: {actual_width}x{actual_height}")

    def toggle_live(self):
        if self.preview.btn_live.isChecked():
            self.start_live()
        else:
            self.stop_live()

    def start_live(self):
        if not self.camera.is_connected():
            log.error("Camera not connected")
            self.preview.btn_live.setChecked(False)
            return

        # Get actual ROI dimensions
        width = self.camera.get_parameter("Width", self.config.width)
        height = self.camera.get_parameter("Height", self.config.height)
        self.preview.set_camera_size(width, height)

        self.camera_thread = CameraThread(self.camera)
        self.camera_thread.frame_ready.connect(self.display_frame)
        self.camera_thread.fps_update.connect(self.update_recording_status)
        self.camera_thread.start()

        self.preview.btn_live.setText("Stop Live")
        log.info(f"Live started - ROI: {width}x{height}")

    def stop_live(self):
        if self.recording:
            self.toggle_recording()

        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread = None

        self.preview.btn_live.setText("Start Live")
        self.preview.btn_live.setChecked(False)
        self.preview.update_status()  # Clear any status
        log.info("Live preview stopped")

    def display_frame(self, frame: np.ndarray):
        """Convert raw camera frame to QImage and display"""
        self.last_frame = frame

        # Get camera info
        pixel_format = self.camera.get_pixel_format() if self.camera.is_connected() else ""
        height, width = frame.shape[:2] if len(frame.shape) >= 2 else (480, 640)

        # Convert to 8-bit for display
        frame_8bit = frame_to_8bit(frame, pixel_format)

        # Create QImage
        if len(frame_8bit.shape) == 2:
            # Grayscale
            qimage = QImage(frame_8bit.data, width, height, width, QImage.Format_Grayscale8)
        elif len(frame_8bit.shape) == 3:
            # Color
            bytes_per_line = 3 * width
            if "BGR" in pixel_format:
                qimage = QImage(frame_8bit.data, width, height, bytes_per_line, QImage.Format_BGR888)
                qimage = qimage.rgbSwapped()
            else:
                qimage = QImage(frame_8bit.data, width, height, bytes_per_line, QImage.Format_RGB888)
        else:
            return

        # Display
        self.preview.update_frame(QPixmap.fromImage(qimage))

    def capture_image(self):
        """Capture and save current frame"""
        if not self.camera.is_connected():
            log.error("Camera not connected")
            return

        # Get raw frame
        frame = self.last_frame if self.last_frame is not None else self.camera.grab_frame()

        if frame is not None:
            # Get camera info
            pixel_format = self.camera.get_pixel_format()
            height, width = frame.shape[:2]

            # Convert to 8-bit for saving
            frame_8bit = frame_to_8bit(frame, pixel_format)

            # Create QImage
            if len(frame_8bit.shape) == 2:
                # Grayscale
                qimage = QImage(frame_8bit.data, width, height, width, QImage.Format_Grayscale8)
            elif len(frame_8bit.shape) == 3:
                # Color
                bytes_per_line = 3 * width
                if "BGR" in pixel_format:
                    qimage = QImage(frame_8bit.data, width, height, bytes_per_line, QImage.Format_BGR888)
                    qimage = qimage.rgbSwapped()
                else:
                    qimage = QImage(frame_8bit.data, width, height, bytes_per_line, QImage.Format_RGB888)
            else:
                log.error(f"Unknown frame shape: {frame_8bit.shape}")
                return

            # Save
            path = self.config.get_image_path()
            if qimage.save(path, "PNG", 100):
                log.info(f"Saved: {path} ({width}x{height} {pixel_format})")
            else:
                log.error("Failed to save image")
        else:
            log.error("No frame available")

    def toggle_recording(self):
        if not self.preview.btn_record.isChecked():
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if not self.camera.is_connected():
            log.error("Camera not connected")
            self.preview.btn_record.setChecked(False)
            return

        # Start live if not running
        if not self.camera_thread:
            self.start_live()
            self.preview.btn_live.setChecked(True)

        # Get camera info
        width, height = self.camera.get_size()
        pixel_format = self.camera.get_pixel_format()
        video_path = self.config.get_video_path()

        # Create writer
        writer = VideoWriter(video_path, width, height, self.config.video_fps, pixel_format)

        # Start recording
        self.camera_thread.start_recording(
            writer,
            self.config.record_limit_frames,
            self.config.record_limit_seconds
        )

        if self.camera_thread.recording:
            self.recording = True
            self.preview.btn_record.setText("Stop Recording")
            log.info(f"Recording: {width}x{height} {pixel_format} @ {self.config.video_fps}fps")
            if self.config.record_limit_frames:
                log.info(f"Limit: {self.config.record_limit_frames} frames")
            if self.config.record_limit_seconds:
                log.info(f"Limit: {self.config.record_limit_seconds} seconds")
        else:
            self.recording = False
            self.preview.btn_record.setChecked(False)
            log.error("Failed to start recording")

    def stop_recording(self):
        if self.camera_thread:
            frames = self.camera_thread.stop_recording()
            if frames > 0:
                duration = frames / self.config.video_fps if self.config.video_fps > 0 else 0
                log.info(f"Stopped: {frames} frames = {duration:.1f}s video")
            else:
                log.warning("No frames recorded")

        self.recording = False
        self.preview.btn_record.setText("Record")
        self.preview.btn_record.setChecked(False)
        self.preview.update_status()  # Clear recording status

    def update_recording_status(self, fps, frames):
        """Update preview status with recording info"""
        self.preview.update_status(fps, frames)

        # Auto-stop if limits reached and thread stopped
        if self.camera_thread and not self.camera_thread.running and self.recording:
            self.stop_recording()

    def closeEvent(self, event):
        self.stop_live()
        self.disconnect_camera()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
