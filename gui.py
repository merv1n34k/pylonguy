"""GUI module - user interface elements"""
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QPen
from PyQt5.QtWidgets import *
import numpy as np
import logging
import json
from pathlib import Path

log = logging.getLogger("pylonguy")

class PreviewWidget(QWidget):
    """Camera preview with status display and selection tool"""

    # Signal for selection changes
    selection_changed = pyqtSignal(object)  # Emits QRect or None

    def __init__(self):
        super().__init__()
        # Initialize status data first
        self.status_data = {
            'fps': 0,
            'frames': 0,
            'live': False,
            'roi': '---',
            'selection': '---',
            'camera_area': '---',
            'selection_area': ''
        }

        # Selection tool variables
        self.current_pixmap = None
        self.selection_rect = None
        self.selecting = False
        self.select_start = None
        self.mouse_pos = None
        self.image_rect = None  # Store where image is displayed
        self.original_frame_size = None  # Store original frame dimensions

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Preview display
        self.display = QLabel("No Camera")
        self.display.setFixedSize(800, 600)
        self.display.setStyleSheet("background: black; color: white; font-size: 20px;")
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setMouseTracking(True)  # Enable mouse tracking
        self.display.installEventFilter(self)  # Install event filter for mouse events
        layout.addWidget(self.display)

        # Status bar with fixed labels (two lines)
        self.status = QLabel(self._get_status_text())
        self.status.setStyleSheet("background: #333; color: white; padding: 8px 5px; font-size: 10pt; line-height: 1.3;")
        self.status.setMinimumHeight(60)  # Make taller for two lines with padding
        layout.addWidget(self.status)

        # Control buttons
        button_layout = QHBoxLayout()
        self.btn_live = QPushButton("Start Live")
        self.btn_capture = QPushButton("Capture")
        self.btn_record = QPushButton("Record")
        self.btn_clear_selection = QPushButton("Clear Selection")
        self.btn_clear_selection.clicked.connect(self.clear_selection)
        self.btn_clear_selection.setToolTip("Clear selection (Esc)")
        self.btn_roi_from_selection = QPushButton("ROI from Selection")
        self.btn_roi_from_selection.clicked.connect(self._roi_from_selection)
        self.btn_roi_from_selection.setEnabled(False)
        self.btn_roi_from_selection.setToolTip("Set camera ROI to selection area (R)")

        button_layout.addWidget(self.btn_live)
        button_layout.addWidget(self.btn_capture)
        button_layout.addWidget(self.btn_record)
        button_layout.addWidget(self.btn_clear_selection)
        button_layout.addWidget(self.btn_roi_from_selection)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Set focus policy to receive keyboard events
        self.setFocusPolicy(Qt.StrongFocus)

    def show_frame(self, frame: np.ndarray):
        """Display frame in preview"""
        if frame is None:
            return

        h, w = frame.shape[:2]
        self.original_frame_size = (w, h)  # Store original dimensions

        # Convert to 8-bit if needed
        if frame.dtype == np.uint16:
            frame = (frame >> 8).astype(np.uint8)

        # Create QImage
        if len(frame.shape) == 2:  # Grayscale
            # Ensure frame is contiguous
            if not frame.flags['C_CONTIGUOUS']:
                frame = np.ascontiguousarray(frame)
            img = QImage(frame.data, w, h, w, QImage.Format_Grayscale8)
        else:  # Color
            if not frame.flags['C_CONTIGUOUS']:
                frame = np.ascontiguousarray(frame)
            img = QImage(frame.data, w, h, w * 3, QImage.Format_RGB888)

        # Create pixmap and scale
        pixmap = QPixmap.fromImage(img)
        if pixmap.isNull():
            log.error("Failed to create pixmap from frame")
            return

        # Store current pixmap for selection overlay
        self.current_pixmap = pixmap.scaled(
            self.display.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # Calculate image position for selection mapping
        self.image_rect = self._calculate_image_rect()

        # Update areas
        self._update_areas()

        # Update display with selection overlay if needed
        self._update_display()

    def update_status(self, **kwargs):
        """Update status bar values"""
        self.status_data.update(kwargs)
        self.status.setText(self._get_status_text())

    def _get_status_text(self):
        """Generate status text with fixed labels"""
        d = self.status_data
        # First line: FPS, Frames, Live, ROI, Selection position
        line1 = (
            f"FPS: {d.get('fps', 0):6.1f} | "
            f"Frames: {d.get('frames', 0):8d} | "
            f"Live: {str(d.get('live', False)):5s} | "
            f"ROI: {d.get('roi', '---'):12s} | "
            f"Selection: {d.get('selection', '---'):25s}"
        )

        # Second line: Camera area and selection area (if exists)
        line2 = f"Camera: {d.get('camera_area', '---')}"
        if d.get('selection_area'):
            line2 += f" | Selection: {d.get('selection_area')}"

        return f"{line1}\n{line2}"

    def _calculate_image_rect(self) -> QRect:
        """Calculate where the scaled image is positioned in the display widget"""
        if not self.current_pixmap:
            return QRect()

        # Get display and image sizes
        display_size = self.display.size()
        img_size = self.current_pixmap.size()

        # Calculate position (centered)
        x = (display_size.width() - img_size.width()) // 2
        y = (display_size.height() - img_size.height()) // 2

        return QRect(x, y, img_size.width(), img_size.height())

    def _update_display(self):
        """Update display with current frame and selection overlay"""
        if not self.current_pixmap:
            return

        # Create a copy for drawing
        display_pixmap = QPixmap(self.display.size())
        display_pixmap.fill(Qt.black)

        painter = QPainter(display_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw the scaled image
        if self.image_rect:
            painter.drawPixmap(self.image_rect, self.current_pixmap)

        # Draw selection rectangle if exists
        if self.selection_rect or (self.selecting and self.select_start and self.mouse_pos):
            # Set up selection style with dashed line
            pen = QPen(QColor(0, 180, 255), 2, Qt.DashLine)
            pen.setDashPattern([5, 3])
            painter.setPen(pen)
            painter.setBrush(QColor(0, 120, 255, 30))

            if self.selection_rect:
                painter.drawRect(self.selection_rect)

                # Draw corner handles
                self._draw_selection_handles(painter, self.selection_rect)

            elif self.selecting and self.select_start and self.mouse_pos:
                # Draw temporary selection while dragging
                temp_rect = QRect(self.select_start, self.mouse_pos).normalized()
                painter.drawRect(temp_rect)

        painter.end()
        self.display.setPixmap(display_pixmap)

    def _draw_selection_handles(self, painter, rect):
        """Draw resize handles at selection corners"""
        handle_size = 6
        handle_color = QColor(0, 180, 255)
        painter.setBrush(handle_color)
        painter.setPen(QPen(handle_color, 1))

        # Corner positions
        corners = [
            rect.topLeft(),
            rect.topRight(),
            rect.bottomLeft(),
            rect.bottomRight()
        ]

        for corner in corners:
            painter.drawEllipse(corner, handle_size, handle_size)

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key_Escape:
            # Clear selection
            self.clear_selection()
        elif event.key() == Qt.Key_R and self.selection_rect:
            # Set ROI from selection
            self._roi_from_selection()
        elif event.key() == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
            # Capture frame (handled by parent app)
            if hasattr(self, 'btn_capture'):
                self.btn_capture.click()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """Handle mouse events for selection tool"""
        if obj != self.display or not self.image_rect:
            return super().eventFilter(obj, event)

        if event.type() == event.MouseMove:
            self.mouse_pos = event.pos()
            if self.selecting:
                self._update_display()
                # Update selection dimensions in status
                if self.select_start:
                    temp_rect = QRect(self.select_start, self.mouse_pos).normalized()
                    self._update_selection_status(temp_rect)

        elif event.type() == event.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                # Only start selection if click is within image area
                if self.image_rect.contains(event.pos()):
                    self.select_start = event.pos()
                    self.selecting = True
                    self.selection_rect = None
            elif event.button() == Qt.RightButton:
                # Show context menu if we have a selection
                if self.selection_rect and self.selection_rect.contains(event.pos()):
                    self._show_selection_menu(event.pos())

        elif event.type() == event.MouseButtonRelease:
            if event.button() == Qt.LeftButton and self.selecting:
                self.selecting = False
                if self.select_start and self.mouse_pos and self.select_start != self.mouse_pos:
                    # Create final selection rectangle
                    self.selection_rect = QRect(self.select_start, self.mouse_pos).normalized()

                    # Constrain to image bounds
                    self.selection_rect = self.selection_rect.intersected(self.image_rect)

                    if self.selection_rect.isValid():
                        self._update_selection_status(self.selection_rect)
                        # Emit selection changed signal with pixel coordinates
                        pixel_rect = self._map_to_frame_coords(self.selection_rect)
                        self.selection_changed.emit(pixel_rect)
                    else:
                        self.clear_selection()
                else:
                    self.clear_selection()

                self._update_display()

        return super().eventFilter(obj, event)

    def _show_selection_menu(self, pos):
        """Show context menu for selection"""
        menu = QMenu(self)

        # Add actions
        action_roi = menu.addAction("Set as ROI")
        action_roi.triggered.connect(self._roi_from_selection)

        action_capture = menu.addAction("Capture Selection")
        action_capture.triggered.connect(lambda: self.btn_capture.click())

        menu.addSeparator()

        action_clear = menu.addAction("Clear Selection")
        action_clear.triggered.connect(self.clear_selection)

        # Show menu at cursor position
        menu.exec_(self.display.mapToGlobal(pos))

    def _map_to_frame_coords(self, display_rect: QRect) -> QRect:
        """Map display coordinates to original frame pixel coordinates"""
        if not self.image_rect or not self.original_frame_size:
            return QRect()

        # Calculate relative position within the image
        rel_x = display_rect.x() - self.image_rect.x()
        rel_y = display_rect.y() - self.image_rect.y()

        # Calculate scale factors
        scale_x = self.original_frame_size[0] / self.image_rect.width()
        scale_y = self.original_frame_size[1] / self.image_rect.height()

        # Map to original frame coordinates
        frame_x = int(rel_x * scale_x)
        frame_y = int(rel_y * scale_y)
        frame_w = int(display_rect.width() * scale_x)
        frame_h = int(display_rect.height() * scale_y)

        return QRect(frame_x, frame_y, frame_w, frame_h)

    def _update_selection_status(self, display_rect: QRect):
        """Update status bar with selection information"""
        if display_rect and display_rect.isValid():
            # Map to frame coordinates
            frame_rect = self._map_to_frame_coords(display_rect)
            if frame_rect.isValid():
                # Calculate dimensions
                width_px = frame_rect.width()
                height_px = frame_rect.height()
                x_px = frame_rect.x()
                y_px = frame_rect.y()

                # Format selection string - include position
                selection_str = f"{width_px}×{height_px}px @({x_px},{y_px})"
                self.update_status(selection=selection_str)

                # Update areas (both camera and selection)
                self._update_areas()
                self.btn_roi_from_selection.setEnabled(True)
        else:
            self.update_status(selection='---', selection_area='')
            self._update_areas()
            self.btn_roi_from_selection.setEnabled(False)

    def _update_areas(self):
        """Update both camera area and selection area displays"""
        # Get pixel size from settings
        px_to_um = 1.0
        main_window = self.window() if hasattr(self, 'window') else None
        if not main_window:
            parent = self.parent()
            while parent:
                if isinstance(parent, MainWindow):
                    main_window = parent
                    break
                parent = parent.parent()

        if main_window and hasattr(main_window, 'settings'):
            px_to_um = main_window.settings.px_to_um.value()

        # Update camera area
        if self.original_frame_size:
            width_px, height_px = self.original_frame_size
            area_px2 = width_px * height_px

            if px_to_um != 1.0:
                area_um2 = area_px2 * (px_to_um ** 2)
                if area_um2 < 1e6:
                    camera_area_str = f"{area_px2:,} px² ({area_um2:.1f} μm²)"
                else:
                    camera_area_str = f"{area_px2:,} px² ({area_um2/1e6:.3f} mm²)"
            else:
                camera_area_str = f"{area_px2:,} px²"

            self.update_status(camera_area=camera_area_str)
        else:
            self.update_status(camera_area='---')

        # Update selection area if exists
        if self.selection_rect and self.selection_rect.isValid():
            frame_rect = self._map_to_frame_coords(self.selection_rect)
            if frame_rect.isValid():
                width_px = frame_rect.width()
                height_px = frame_rect.height()
                area_px2 = width_px * height_px

                if px_to_um != 1.0:
                    area_um2 = area_px2 * (px_to_um ** 2)
                    if area_um2 < 1e6:
                        selection_area_str = f"{area_px2:,} px² ({area_um2:.1f} μm²)"
                    else:
                        selection_area_str = f"{area_px2:,} px² ({area_um2/1e6:.3f} mm²)"
                else:
                    selection_area_str = f"{area_px2:,} px²"

                self.update_status(selection_area=selection_area_str)
        else:
            self.update_status(selection_area='')

    def clear_selection(self):
        """Clear the current selection"""
        self.selection_rect = None
        self.selecting = False
        self.select_start = None
        self.mouse_pos = None
        self.update_status(selection='---', selection_area='')
        self._update_areas()  # Update camera area
        self.btn_roi_from_selection.setEnabled(False)
        self.selection_changed.emit(None)
        self._update_display()

    def _roi_from_selection(self):
        """Set ROI from current selection"""
        selection = self.get_selection()
        if selection and selection.isValid():
            # Find settings widget through parent chain
            main_window = self.window() if hasattr(self, 'window') else None
            if not main_window:
                # Try to find through parent widgets
                parent = self.parent()
                while parent:
                    if isinstance(parent, MainWindow):
                        main_window = parent
                        break
                    parent = parent.parent()

            if main_window and hasattr(main_window, 'settings'):
                settings = main_window.settings
                settings.roi_width.setValue(selection.width())
                settings.roi_height.setValue(selection.height())
                settings.roi_offset_x.setValue(selection.x())
                settings.roi_offset_y.setValue(selection.y())
                log.info(f"ROI set from selection: {selection.width()}x{selection.height()}+{selection.x()}+{selection.y()}")

                # Trigger settings changed signal to auto-apply
                settings.settings_changed.emit()

            # Clear selection after applying
            self.clear_selection()

    def get_selection(self) -> QRect:
        """Get current selection in frame pixel coordinates"""
        if self.selection_rect and self.selection_rect.isValid():
            return self._map_to_frame_coords(self.selection_rect)
        return QRect()

    def show_message(self, message: str):
        """Show message in display area"""
        self.display.setPixmap(QPixmap())  # Clear any existing pixmap
        self.display.setText(message)
        self.display.setAlignment(Qt.AlignCenter)
        self.current_pixmap = None
        self.image_rect = None
        self.original_frame_size = None
        # Clear selection variables directly to avoid multiple updates
        self.selection_rect = None
        self.selecting = False
        self.select_start = None
        self.mouse_pos = None
        self.btn_roi_from_selection.setEnabled(False)
        self.selection_changed.emit(None)
        # Update status
        self.update_status(selection='---', camera_area='---', selection_area='')


class SettingsWidget(QWidget):
    """Settings panel with all controls and presets"""

    # Signals
    settings_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_presets()

    def init_presets(self):
        """Initialize preset configurations"""
        # Presets defined in GUI, not camera
        self.presets = {
            'quality': {
                'roi_width': 1920,
                'roi_height': 1080,
                'binning_h': 1,
                'binning_v': 1,
                'exposure': 1000,
                'gain': 0,
                'pixel_format': 'Mono10p',
                'sensor_readout_mode': 'Normal',
                'acquisition_framerate_enable': False,
                'throughput_limit_enable': False
            },
            'speed': {
                'roi_width': 320,
                'roi_height': 240,
                'binning_h': 2,
                'binning_v': 2,
                'exposure': 100,
                'gain': 10,
                'pixel_format': 'Mono8',
                'sensor_readout_mode': 'Fast',
                'acquisition_framerate_enable': False,
                'throughput_limit_enable': False
            },
            'balanced': {
                'roi_width': 640,
                'roi_height': 480,
                'binning_h': 1,
                'binning_v': 1,
                'exposure': 500,
                'gain': 5,
                'pixel_format': 'Mono8',
                'sensor_readout_mode': 'Normal',
                'acquisition_framerate_enable': False,
                'throughput_limit_enable': False
            }
        }

        # Load custom presets from JSON file if exists
        self.load_custom_presets()

    def load_custom_presets(self):
        """Load custom presets from JSON file"""
        preset_file = Path("./presets.json")
        if preset_file.exists():
            try:
                with open(preset_file, 'r') as f:
                    custom_presets = json.load(f)
                    if 'custom' in custom_presets:
                        self.presets['custom'] = custom_presets['custom']
                        log.info("Loaded custom preset")
            except Exception as e:
                log.error(f"Failed to load custom presets: {e}")

    def save_presets_to_file(self):
        """Save custom preset to JSON file"""
        preset_file = Path("./presets.json")
        try:
            with open(preset_file, 'w') as f:
                json.dump({'custom': self.presets.get('custom', {})}, f, indent=2)
            log.info("Saved custom preset")
        except Exception as e:
            log.error(f"Failed to save custom preset: {e}")

    def apply_preset(self, preset_name=None):
        """Apply preset values to GUI widgets"""
        if preset_name is None:
            preset_name = self.preset_combo.currentText()

        if preset_name not in self.presets:
            log.warning(f"Preset '{preset_name}' not found")
            return

        preset = self.presets[preset_name]

        # Apply values to widgets
        for key, value in preset.items():
            # Map preset keys to widget names
            widget_map = {
                'roi_width': self.roi_width,
                'roi_height': self.roi_height,
                'roi_offset_x': self.roi_offset_x,
                'roi_offset_y': self.roi_offset_y,
                'binning_h': self.binning_horizontal,
                'binning_v': self.binning_vertical,
                'exposure': self.exposure,
                'gain': self.gain,
                'pixel_format': self.pixel_format,
                'sensor_readout_mode': self.sensor_mode,
                'acquisition_framerate_enable': self.framerate_enable,
                'acquisition_framerate': self.framerate,
                'throughput_limit_enable': self.throughput_enable,
                'throughput_limit': self.throughput_limit
            }

            widget = widget_map.get(key)
            if widget:
                if isinstance(widget, QSpinBox) or isinstance(widget, QDoubleSpinBox):
                    widget.setValue(value)
                elif isinstance(widget, QComboBox):
                    index = widget.findText(str(value))
                    if index >= 0:
                        widget.setCurrentIndex(index)
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(value)

        log.info(f"Applied preset: {preset_name}")
        # Emit signal to apply to camera
        self.settings_changed.emit()

    def save_custom_preset(self):
        """Save current settings as custom preset"""
        # Get current values from widgets
        custom = {
            'roi_width': self.roi_width.value(),
            'roi_height': self.roi_height.value(),
            'roi_offset_x': self.roi_offset_x.value(),
            'roi_offset_y': self.roi_offset_y.value(),
            'binning_h': int(self.binning_horizontal.currentText()),
            'binning_v': int(self.binning_vertical.currentText()),
            'exposure': self.exposure.value(),
            'gain': self.gain.value(),
            'pixel_format': self.pixel_format.currentText(),
            'sensor_readout_mode': self.sensor_mode.currentText(),
            'acquisition_framerate_enable': self.framerate_enable.isChecked(),
            'acquisition_framerate': self.framerate.value(),
            'throughput_limit_enable': self.throughput_enable.isChecked(),
            'throughput_limit': self.throughput_limit.value()
        }

        # Save as custom preset
        self.presets['custom'] = custom

        # Save to file
        self.save_presets_to_file()

        # Update combo box if custom not already there
        if self.preset_combo.findText('Custom') < 0:
            self.preset_combo.addItem('Custom')

        log.info("Saved current settings as custom preset")

    def init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout()

        # Connection controls
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        conn_layout.addWidget(self.btn_connect)
        conn_layout.addWidget(self.btn_disconnect)
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # Preset controls (at the top for easy access)
        preset_group = QGroupBox("Presets")
        preset_layout = QFormLayout()

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(['quality', 'balanced', 'speed'])

        preset_buttons = QHBoxLayout()
        self.btn_apply_preset = QPushButton("Apply")
        self.btn_apply_preset.clicked.connect(lambda: self.apply_preset())
        self.btn_save_custom = QPushButton("Save as Custom")
        self.btn_save_custom.clicked.connect(self.save_custom_preset)
        preset_buttons.addWidget(self.btn_apply_preset)
        preset_buttons.addWidget(self.btn_save_custom)

        preset_layout.addRow("Select Preset:", self.preset_combo)
        preset_layout.addRow(preset_buttons)
        preset_group.setLayout(preset_layout)
        layout.addWidget(preset_group)

        # ROI settings with binning
        roi_group = QGroupBox("ROI & Binning")
        roi_layout = QFormLayout()

        self.roi_width = QSpinBox()
        self.roi_width.setRange(16, 4096)
        self.roi_width.setValue(640)
        self.roi_width.setSingleStep(16)

        self.roi_height = QSpinBox()
        self.roi_height.setRange(16, 3072)
        self.roi_height.setValue(480)
        self.roi_height.setSingleStep(16)

        self.roi_offset_x = QSpinBox()
        self.roi_offset_x.setRange(0, 4096)
        self.roi_offset_x.setValue(0)

        self.roi_offset_y = QSpinBox()
        self.roi_offset_y.setRange(0, 3072)
        self.roi_offset_y.setValue(0)

        # Binning controls
        self.binning_horizontal = QComboBox()
        self.binning_horizontal.addItems(['1', '2', '3', '4'])

        self.binning_vertical = QComboBox()
        self.binning_vertical.addItems(['1', '2', '3', '4'])

        self.px_to_um = QDoubleSpinBox()
        self.px_to_um.setRange(0.01, 1000)
        self.px_to_um.setValue(1.0)
        self.px_to_um.setSuffix(" μm/px")
        self.px_to_um.setDecimals(3)

        roi_layout.addRow("Width (px):", self.roi_width)
        roi_layout.addRow("Height (px):", self.roi_height)
        roi_layout.addRow("Offset X:", self.roi_offset_x)
        roi_layout.addRow("Offset Y:", self.roi_offset_y)
        roi_layout.addRow("Binning H:", self.binning_horizontal)
        roi_layout.addRow("Binning V:", self.binning_vertical)
        roi_layout.addRow("Pixel Size:", self.px_to_um)

        # Connect pixel size changes to update preview area
        self.px_to_um.valueChanged.connect(self._update_preview_area)

        roi_group.setLayout(roi_layout)
        layout.addWidget(roi_group)

        # Acquisition settings
        acq_group = QGroupBox("Acquisition")
        acq_layout = QFormLayout()

        self.exposure = QDoubleSpinBox()
        self.exposure.setRange(10, 1000000)
        self.exposure.setValue(1000)
        self.exposure.setSuffix(" μs")

        self.gain = QDoubleSpinBox()
        self.gain.setRange(0, 48)
        self.gain.setValue(0)

        # Pixel format
        self.pixel_format = QComboBox()
        self.pixel_format.addItems(['Mono8', 'Mono10', 'Mono10p'])

        # Sensor readout mode
        self.sensor_mode = QComboBox()
        self.sensor_mode.addItems(['Normal', 'Fast'])

        acq_layout.addRow("Exposure:", self.exposure)
        acq_layout.addRow("Gain:", self.gain)
        acq_layout.addRow("Pixel Format:", self.pixel_format)
        acq_layout.addRow("Sensor Mode:", self.sensor_mode)

        acq_group.setLayout(acq_layout)
        layout.addWidget(acq_group)

        # Frame Rate Control
        framerate_group = QGroupBox("Frame Rate Control")
        framerate_layout = QFormLayout()

        # Acquisition frame rate control
        self.framerate_enable = QCheckBox("Limit Frame Rate")
        self.framerate = QDoubleSpinBox()
        self.framerate.setRange(1, 10000)
        self.framerate.setValue(30)
        self.framerate.setSuffix(" Hz")
        self.framerate.setEnabled(False)
        self.framerate_enable.toggled.connect(self.framerate.setEnabled)

        # Throughput limit control
        self.throughput_enable = QCheckBox("Limit Throughput")
        self.throughput_limit = QDoubleSpinBox()
        self.throughput_limit.setRange(1, 1000)
        self.throughput_limit.setValue(125)
        self.throughput_limit.setSuffix(" Mbps")
        self.throughput_limit.setEnabled(False)
        self.throughput_enable.toggled.connect(self.throughput_limit.setEnabled)

        # Current FPS display
        self.current_fps_label = QLabel("Current FPS: ---")
        self.current_fps_label.setStyleSheet("font-weight: bold; color: green;")

        framerate_layout.addRow(self.framerate_enable)
        framerate_layout.addRow("Target FPS:", self.framerate)
        framerate_layout.addRow(self.throughput_enable)
        framerate_layout.addRow("Limit (Mbps):", self.throughput_limit)
        framerate_layout.addRow(self.current_fps_label)

        framerate_group.setLayout(framerate_layout)
        layout.addWidget(framerate_group)

        # Output settings
        out_group = QGroupBox("Output")
        out_layout = QFormLayout()

        self.output_path = QLineEdit("./output/video")
        self.append_timestamp = QCheckBox("Append timestamp")
        self.append_timestamp.setChecked(True)

        self.video_fps = QDoubleSpinBox()
        self.video_fps.setRange(1, 120)
        self.video_fps.setValue(24)
        self.video_fps.setSuffix(" fps")

        out_layout.addRow("Path:", self.output_path)
        out_layout.addRow("", self.append_timestamp)
        out_layout.addRow("Video FPS:", self.video_fps)

        out_group.setLayout(out_layout)
        layout.addWidget(out_group)

        # Recording settings
        rec_group = QGroupBox("Recording")
        rec_layout = QFormLayout()

        # Recording mode
        self.recording_mode = QComboBox()
        self.recording_mode.addItems(["Real-time", "Frame Dump"])

        # Keep frames option (only for Frame Dump mode)
        self.keep_frames = QCheckBox("Keep frame files after conversion")
        self.keep_frames.setEnabled(False)
        self.recording_mode.currentTextChanged.connect(
            lambda mode: self.keep_frames.setEnabled(mode == "Frame Dump")
        )

        # Report options
        self.export_raw_stats = QCheckBox("Export raw stats CSV")
        self.export_raw_stats.setChecked(True)
        self.export_settings = QCheckBox("Export settings CSV")
        self.export_settings.setChecked(False)

        # Limits
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

        rec_layout.addRow("Mode:", self.recording_mode)
        rec_layout.addRow("", self.keep_frames)
        rec_layout.addRow("", self.export_raw_stats)
        rec_layout.addRow("", self.export_settings)
        rec_layout.addRow("", self.limit_frames_enable)
        rec_layout.addRow("Max frames:", self.limit_frames)
        rec_layout.addRow("", self.limit_time_enable)
        rec_layout.addRow("Max time:", self.limit_time)

        rec_group.setLayout(rec_layout)
        layout.addWidget(rec_group)

        # Preview settings
        prev_group = QGroupBox("Preview")
        prev_layout = QFormLayout()

        self.preview_off = QCheckBox("Turn off during recording")
        self.preview_off.setChecked(True)

        self.preview_nth = QSpinBox()
        self.preview_nth.setRange(1, 1000)
        self.preview_nth.setValue(10)
        self.preview_nth.setEnabled(False)

        self.preview_off.toggled.connect(lambda checked: self.preview_nth.setEnabled(not checked))

        prev_layout.addRow("", self.preview_off)
        prev_layout.addRow("Show every Nth frame:", self.preview_nth)

        prev_group.setLayout(prev_layout)
        layout.addWidget(prev_group)

        # Apply button
        self.btn_apply = QPushButton("Apply Settings")
        self.btn_apply.clicked.connect(self.settings_changed.emit)
        layout.addWidget(self.btn_apply)

        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)

        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def update_from_camera(self, camera):
        """Update widget limits and availability from camera"""
        if not camera or not camera.device:
            return

        # Update ROI limits
        for param_name, widget in [
            ('Width', self.roi_width),
            ('Height', self.roi_height),
            ('OffsetX', self.roi_offset_x),
            ('OffsetY', self.roi_offset_y)
        ]:
            limits = camera.get_parameter_limits(param_name)
            if limits:
                if 'min' in limits and 'max' in limits:
                    widget.setRange(limits['min'], limits['max'])
                if 'inc' in limits:
                    widget.setSingleStep(limits['inc'])

        # Update exposure limits
        limits = camera.get_parameter_limits('ExposureTime')
        if not limits:
            limits = camera.get_parameter_limits('ExposureTimeAbs')
        if limits:
            if 'min' in limits and 'max' in limits:
                self.exposure.setRange(limits['min'], limits['max'])

        # Update gain limits
        limits = camera.get_parameter_limits('Gain')
        if not limits:
            limits = camera.get_parameter_limits('GainRaw')
        if limits:
            if 'min' in limits and 'max' in limits:
                self.gain.setRange(limits['min'], limits['max'])

        # Update frame rate limits
        limits = camera.get_parameter_limits('AcquisitionFrameRate')
        if limits:
            if 'min' in limits and 'max' in limits:
                self.framerate.setRange(limits['min'], limits['max'])

        # Check feature availability
        if not camera.is_parameter_available('BinningHorizontal'):
            self.binning_horizontal.setEnabled(False)
            self.binning_horizontal.setToolTip("Not supported by this camera")

        if not camera.is_parameter_available('BinningVertical'):
            self.binning_vertical.setEnabled(False)
            self.binning_vertical.setToolTip("Not supported by this camera")

        if not camera.is_parameter_available('SensorReadoutMode'):
            self.sensor_mode.setEnabled(False)
            self.sensor_mode.setToolTip("Not supported by this camera")

        if not camera.is_parameter_available('AcquisitionFrameRateEnable'):
            self.framerate_enable.setEnabled(False)
            self.framerate.setEnabled(False)
            self.framerate_enable.setToolTip("Not supported by this camera")

        if not camera.is_parameter_available('DeviceLinkThroughputLimitMode'):
            self.throughput_enable.setEnabled(False)
            self.throughput_limit.setEnabled(False)
            self.throughput_enable.setToolTip("Not supported by this camera")

        # Get current values from camera
        w, h, ox, oy = camera.get_roi()
        self.roi_width.setValue(w)
        self.roi_height.setValue(h)
        self.roi_offset_x.setValue(ox)
        self.roi_offset_y.setValue(oy)

        log.info("Updated GUI from camera capabilities")

    def update_fps_display(self, fps: float):
        """Update the current FPS display"""
        self.current_fps_label.setText(f"Current FPS: {fps:.1f}")

    def _update_preview_area(self):
        """Update preview area display when pixel size changes"""
        # Find preview widget and update its area display
        main_window = self.window() if hasattr(self, 'window') else None
        if not main_window:
            parent = self.parent()
            while parent:
                if isinstance(parent, MainWindow):
                    main_window = parent
                    break
                parent = parent.parent()

        if main_window and hasattr(main_window, 'preview'):
            main_window.preview._update_areas()

    def get_settings(self) -> dict:
        """Get all settings as dictionary"""
        return {
            'roi': {
                'width': self.roi_width.value(),
                'height': self.roi_height.value(),
                'offset_x': self.roi_offset_x.value(),
                'offset_y': self.roi_offset_y.value(),
                'binning_h': int(self.binning_horizontal.currentText()),
                'binning_v': int(self.binning_vertical.currentText()),
                'px_to_um': self.px_to_um.value()
            },
            'acquisition': {
                'exposure': self.exposure.value(),
                'gain': self.gain.value(),
                'pixel_format': self.pixel_format.currentText(),
                'sensor_mode': self.sensor_mode.currentText()
            },
            'framerate': {
                'enabled': self.framerate_enable.isChecked(),
                'target_fps': self.framerate.value(),
                'throughput_enabled': self.throughput_enable.isChecked(),
                'throughput_limit': self.throughput_limit.value()
            },
            'output': {
                'path': self.output_path.text(),
                'append_timestamp': self.append_timestamp.isChecked(),
                'video_fps': self.video_fps.value()
            },
            'recording': {
                'mode': self.recording_mode.currentText(),
                'keep_frames': self.keep_frames.isChecked(),
                'export_raw_stats': self.export_raw_stats.isChecked(),
                'export_settings': self.export_settings.isChecked(),
                'limit_frames': self.limit_frames.value() if self.limit_frames_enable.isChecked() else None,
                'limit_time': self.limit_time.value() if self.limit_time_enable.isChecked() else None
            },
            'preview': {
                'off_during_recording': self.preview_off.isChecked(),
                'nth_frame': self.preview_nth.value()
            }
        }
class LogWidget(QWidget):
    """Log display widget"""

    # Signal for thread-safe text updates
    append_text = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Log"))

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        layout.addWidget(self.log)

        self.setLayout(layout)

        # Connect signal for thread-safe updates
        self.append_text.connect(self._append_text_safe)

    def add(self, message: str):
        """Add message to log (thread-safe)"""
        self.append_text.emit(message)

    def _append_text_safe(self, message: str):
        """Actually append text (called in GUI thread)"""
        try:
            self.log.append(message)
            # Auto-scroll to bottom
            scrollbar = self.log.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except:
            # Handle any Qt errors silently
            pass


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("PylonGuy")
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
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.settings, 3)
        right_layout.addWidget(self.log, 1)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        layout.addWidget(right_widget, 1)

        central.setLayout(layout)
        self.setCentralWidget(central)
