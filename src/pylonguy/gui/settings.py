"""Preview widget - Camera display with zero-copy rendering"""

from PyQt5.QtCore import Qt, pyqtSignal, QRect, pyqtSlot
from PyQt5.QtWidgets import *
import json
from pathlib import Path
import logging

log = logging.getLogger("pylonguy")


class SettingsWidget(QWidget):
    """Settings panel with all controls"""

    camera_settings_changed = pyqtSignal()

    mode_changed = pyqtSignal(str)
    transform_changed = pyqtSignal(bool, bool, int)  # flip_x, flip_y, rotation
    ruler_changed = pyqtSignal(bool, bool, bool)  # ruler v, h, radial

    def __init__(self):
        super().__init__()
        self.presets = {}
        self._applying_preset = False
        self.init_ui()
        self.init_presets()

    def init_presets(self):
        """Initialize preset configurations from JSON file"""
        self.presets = {}
        preset_file = Path("presets.json")

        # Default presets (fallback if file doesn't exist)
        default_presets = {
            "Default": {
                "Width": 640,
                "Height": 480,
                "BinningHorizontal": "1",
                "BinningVertical": "1",
                "ExposureTime": 500,
                "Gain": 0,
                "PixelFormat": "Mono8",
                "SensorReadoutMode": "Fast",
            },
            "HighSpeed": {
                "Width": 256,
                "Height": 128,
                "BinningHorizontal": "1",
                "BinningVertical": "1",
                "ExposureTime": 50,
                "Gain": 5,
                "PixelFormat": "Mono8",
                "SensorReadoutMode": "Fast",
            },
            "FullFrame": {
                "Width": 1920,
                "Height": 1080,
                "BinningHorizontal": "1",
                "BinningVertical": "1",
                "ExposureTime": 5000,
                "Gain": 0,
                "PixelFormat": "Mono10p",
                "SensorReadoutMode": "Normal",
            },
            "Microfluidics": {
                "Width": 512,
                "Height": 256,
                "BinningHorizontal": "1",
                "BinningVertical": "1",
                "ExposureTime": 200,
                "Gain": 2,
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

        # Add presets to combo, ensuring "Default" is first
        if "Default" in self.presets:
            self.preset_combo.addItem("Default")
        for preset in self.presets.keys():
            if preset != "Default":
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
        self.auto_apply_check = QCheckBox("Auto-apply")
        self.auto_apply_check.setChecked(True)
        select_layout.addWidget(self.auto_apply_check)

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

        # Waterfall settings (initially hidden)
        self.waterfall_lines = QSpinBox()
        self.waterfall_lines.setRange(100, 2000)
        self.waterfall_lines.setValue(500)
        self.waterfall_lines_label = QLabel("Buffer Lines:")
        capture_layout.addRow(self.waterfall_lines_label, self.waterfall_lines)
        self.waterfall_lines.setVisible(False)
        self.waterfall_lines_label.setVisible(False)

        # Capture settings
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
        self._connect_settings()

        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def _connect_settings(self):
        """Connect only ROI, Acquisition, and Frame Rate controls"""
        # ROI section
        self.roi_width.valueChanged.connect(self._emit_if_not_preset)
        self.roi_height.valueChanged.connect(self._emit_if_not_preset)
        self.roi_offset_x.valueChanged.connect(self._emit_if_not_preset)
        self.roi_offset_y.valueChanged.connect(self._emit_if_not_preset)
        self.binning_horizontal.currentIndexChanged.connect(self._emit_if_not_preset)
        self.binning_vertical.currentIndexChanged.connect(self._emit_if_not_preset)

        # Acquisition section
        self.exposure.valueChanged.connect(self._emit_if_not_preset)
        self.gain.valueChanged.connect(self._emit_if_not_preset)
        self.pixel_format.currentTextChanged.connect(self._emit_if_not_preset)
        self.sensor_mode.currentTextChanged.connect(self._emit_if_not_preset)

        # Frame Rate Control section
        self.framerate_enable.toggled.connect(self._emit_if_not_preset)
        self.framerate.valueChanged.connect(self._emit_if_not_preset)
        self.throughput_enable.toggled.connect(self._emit_if_not_preset)
        self.throughput_limit.valueChanged.connect(self._emit_if_not_preset)

    def _emit_if_not_preset(self):
        """Only emit if not applying preset"""
        if not self._applying_preset:
            self.camera_settings_changed.emit()

    def setLocked(self, locked: bool):
        """Lock all controls during recording"""
        self.setEnabled(not locked)

    def _on_mode_changed(self, mode: str):
        """Handle capture mode change"""
        self.mode_changed.emit(mode)

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
            self._applying_preset = True

            preset = self.presets[preset_name]
            for param_name, value in preset.items():
                self.set_parameter_value(param_name, value)

            self._applying_preset = False

            log.info(f"Applied preset: {preset_name}")
            self.camera_settings_changed.emit()

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
            "capture": {
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
            },
            "transform": {
                "flip_x": self.flip_x_check.isChecked(),
                "flip_y": self.flip_y_check.isChecked(),
                "rotation": int(self.rotation_spin.currentText()),
            },
        }
