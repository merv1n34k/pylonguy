"""Settings widget - Camera controls and presets"""

import dropletui as ui
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout,
    QComboBox, QSpinBox, QDoubleSpinBox,
    QScrollArea,
)
import json
import re
from pathlib import Path
import logging

from ..constants import (
    MAX_OFFSET_X,
    MAX_OFFSET_Y,
    MIN_ROI_WIDTH,
    MIN_ROI_HEIGHT,
    OFFSET_SLIDER_STEP,
)

log = logging.getLogger("pylonguy")


class SettingsWidget(QWidget):
    """Settings panel with all controls"""

    camera_settings_changed = Signal()
    offset_x_changed = Signal(int)
    offset_y_changed = Signal(int)

    mode_changed = Signal(str)
    transform_changed = Signal(bool, bool, int)  # flip_x, flip_y, rotation
    ruler_changed = Signal(bool, bool, bool)  # ruler v, h, radial

    def __init__(self):
        super().__init__()
        self.presets = {}
        self._applying_preset = False
        self.init_ui()
        self._init_param_widgets()
        self.init_presets()

    def _init_param_widgets(self):
        """Initialize parameter-to-widget mapping after UI creation."""
        self._param_widgets = {
            "Width": self.roi_width,
            "Height": self.roi_height,
            "OffsetX": self.roi_offset_x,
            "OffsetY": self.roi_offset_y,
            "ExposureTime": self.exposure,
            "Gain": self.gain,
            "AcquisitionFrameRate": self.framerate,
            "BinningHorizontal": self.binning_horizontal,
            "BinningVertical": self.binning_vertical,
            "PixelFormat": self.pixel_format,
            "SensorReadoutMode": self.sensor_mode,
        }
        # Widgets that need special handling for disable (tuples)
        self._param_widgets_disable = {
            "SensorReadoutMode": self.sensor_mode,
            "BinningHorizontal": self.binning_horizontal,
            "BinningVertical": self.binning_vertical,
            "AcquisitionFrameRate": (self.framerate_enable, self.framerate),
            "DeviceLinkThroughputLimit": (self.throughput_enable, self.throughput_limit),
        }

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

    def _is_valid_preset_name(self, name: str) -> bool:
        """Validate preset name (alphanumeric, spaces, hyphens, max 50 chars)."""
        if not name or len(name) > 50:
            return False
        return bool(re.match(r'^[\w\s-]+$', name))

    def save_preset(self):
        """Save current settings as named preset"""
        preset_name = self.preset_name_input.text().strip()
        if not preset_name:
            log.warning("Please enter a preset name")
            return

        if not self._is_valid_preset_name(preset_name):
            log.warning("Invalid preset name. Use letters, numbers, spaces, hyphens.")
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
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        layout = QVBoxLayout()

        # Connection controls
        conn_group, conn_layout = ui.section("Connection")

        self.camera_combo = ui.combo_box(["Detecting..."])
        self.btn_refresh = ui.button("Refresh")
        self.auto_apply_check = ui.check_box("Auto-apply", checked=True)

        self.btn_connect = ui.button("Connect", variant="success")
        self.btn_disconnect = ui.button("Disconnect", variant="danger")

        conn_layout.addWidget(
            ui.field_row(self.camera_combo, self.btn_refresh, self.auto_apply_check)
        )
        conn_layout.addWidget(
            ui.button_row(self.btn_connect, self.btn_disconnect, align="left")
        )
        layout.addWidget(conn_group)

        # Preset controls
        preset_group = ui.form_panel("Presets", [])
        preset_layout = preset_group.layout()

        self.preset_combo = ui.combo_box()
        self.preset_combo.addItems(sorted(self.presets.keys()))
        self.btn_apply_preset = ui.button("Apply Preset", variant="primary")
        self.btn_apply_preset.clicked.connect(self.apply_preset)

        self.preset_name_input = ui.line_edit(placeholder="Enter preset name...")
        self.btn_save_preset = ui.button("Save as Preset")
        self.btn_save_preset.clicked.connect(self.save_preset)

        preset_layout.addRow("Select:", ui.field_row(self.preset_combo, self.btn_apply_preset))
        preset_layout.addRow("Name:", ui.field_row(self.preset_name_input, self.btn_save_preset))
        layout.addWidget(preset_group)

        # ROI settings
        roi_group = ui.form_panel("ROI", [])
        roi_layout = roi_group.layout()

        self.roi_width = ui.int_box(minimum=MIN_ROI_WIDTH, maximum=MAX_OFFSET_X, value=640)

        self.roi_height = ui.int_box(minimum=MIN_ROI_HEIGHT, maximum=MAX_OFFSET_Y, value=480)

        self.roi_offset_x = ui.int_box(minimum=0, maximum=MAX_OFFSET_X)

        self.roi_offset_y = ui.int_box(minimum=0, maximum=MAX_OFFSET_Y)

        self.binning_horizontal = ui.combo_box(["1", "2", "3", "4"])

        self.binning_vertical = ui.combo_box(["1", "2", "3", "4"])

        # Offset sliders
        self.offset_x_slider = ui.slider(
            maximum=MAX_OFFSET_X,
            step=OFFSET_SLIDER_STEP,
            page_step=OFFSET_SLIDER_STEP,
        )
        self.offset_x_slider.valueChanged.connect(self.offset_x_changed.emit)

        self.offset_y_slider = ui.slider(
            maximum=MAX_OFFSET_Y,
            step=OFFSET_SLIDER_STEP,
            page_step=OFFSET_SLIDER_STEP,
        )
        self.offset_y_slider.valueChanged.connect(self.offset_y_changed.emit)

        roi_layout.addRow("Width:", self.roi_width)
        roi_layout.addRow("Height:", self.roi_height)
        roi_layout.addRow("Offset X:", self.roi_offset_x)
        roi_layout.addRow("Slide X:", self.offset_x_slider)
        roi_layout.addRow("Offset Y:", self.roi_offset_y)
        roi_layout.addRow("Slide Y:", self.offset_y_slider)
        roi_layout.addRow("Binning H:", self.binning_horizontal)
        roi_layout.addRow("Binning V:", self.binning_vertical)

        self.ruler_v_check = ui.check_box("V")
        self.ruler_h_check = ui.check_box("H")
        self.ruler_radial_check = ui.check_box("Radial")
        self.ruler_v_check.toggled.connect(self._on_ruler_changed)
        self.ruler_h_check.toggled.connect(self._on_ruler_changed)
        self.ruler_radial_check.toggled.connect(self._on_ruler_changed)

        roi_layout.addRow(
            "Rulers:",
            ui.field_row(self.ruler_v_check, self.ruler_h_check, self.ruler_radial_check),
        )

        # Add transform controls
        self.flip_x_check = ui.check_box("X")
        self.flip_y_check = ui.check_box("Y")
        self.rotation_spin = ui.combo_box(["0", "90", "180", "270"])

        roi_layout.addRow(
            "Transform:",
            ui.field_row(
                ui.status_label("Flip:", kind="muted"),
                self.flip_x_check,
                self.flip_y_check,
                ui.status_label("Rotate:", kind="muted"),
                self.rotation_spin,
            ),
        )

        # Connect transform signals
        self.flip_x_check.toggled.connect(self._on_transform_changed)
        self.flip_y_check.toggled.connect(self._on_transform_changed)
        self.rotation_spin.currentIndexChanged.connect(self._on_transform_changed)

        layout.addWidget(roi_group)

        # Acquisition settings
        acq_group = ui.form_panel("Acquisition", [])
        acq_layout = acq_group.layout()

        self.exposure = ui.double_box(minimum=10, maximum=1000000, value=150, suffix=" μs")

        self.gain = ui.double_box(minimum=0, maximum=48, value=0)

        self.pixel_format = ui.combo_box(["Mono8", "Mono10", "Mono10p"])

        self.sensor_mode = ui.combo_box(["Normal", "Fast"])

        acq_layout.addRow("Exposure:", self.exposure)
        acq_layout.addRow("Gain:", self.gain)
        acq_layout.addRow("Pixel Format:", self.pixel_format)
        acq_layout.addRow("Sensor Mode:", self.sensor_mode)

        layout.addWidget(acq_group)

        # Frame Rate Control
        framerate_group = ui.form_panel("Frame Rate Control", [])
        framerate_layout = framerate_group.layout()

        self.framerate_enable = ui.check_box("Enable Frame Rate Limit")
        self.framerate = ui.double_box(minimum=1, maximum=100000, value=30, suffix=" Hz")
        self.framerate.setEnabled(False)
        self.framerate_enable.toggled.connect(self.framerate.setEnabled)

        self.throughput_enable = ui.check_box("Enable Throughput Limit")
        self.throughput_limit = ui.double_box(minimum=1, maximum=1000, value=125, suffix=" Mbps")
        self.throughput_limit.setEnabled(False)
        self.throughput_enable.toggled.connect(self.throughput_limit.setEnabled)

        framerate_layout.addRow(self.framerate_enable)
        framerate_layout.addRow("Frame Rate:", self.framerate)
        framerate_layout.addRow(self.throughput_enable)
        framerate_layout.addRow("Throughput:", self.throughput_limit)

        layout.addWidget(framerate_group)

        # Capture settings (renamed from Output)
        capture_group = ui.form_panel("Capture", [])
        capture_layout = capture_group.layout()

        # Mode selection
        self.capture_mode = ui.combo_box(["ROI Capture", "Waterfall"])
        self.capture_mode.currentTextChanged.connect(self._on_mode_changed)
        capture_layout.addRow("Mode:", self.capture_mode)

        # Capture settings
        self.output_path = ui.line_edit("./output")
        self.image_prefix = ui.line_edit("img")
        self.video_prefix = ui.line_edit("vid")

        capture_layout.addRow("Path:", self.output_path)
        capture_layout.addRow("Image Prefix:", self.image_prefix)
        capture_layout.addRow("Video Prefix:", self.video_prefix)

        self.video_fps = ui.double_box(minimum=1, maximum=120, value=24, suffix=" fps")
        self.video_fps_label = ui.status_label("Video FPS:", kind="muted", small=False)
        capture_layout.addRow(self.video_fps_label, self.video_fps)

        self.preview_off = ui.check_box("Disable preview during recording", checked=True)
        capture_layout.addRow("", self.preview_off)

        self.limit_frames_enable = ui.check_box("Limit frames")
        self.limit_frames = ui.int_box(minimum=1, maximum=1000000, value=1000)
        self.limit_frames.setEnabled(False)
        self.limit_frames_enable.toggled.connect(self.limit_frames.setEnabled)

        self.limit_time_enable = ui.check_box("Limit time")
        self.limit_time = ui.double_box(minimum=0.1, maximum=3600, value=10, suffix=" s")
        self.limit_time.setEnabled(False)
        self.limit_time_enable.toggled.connect(self.limit_time.setEnabled)

        capture_layout.addRow(self.limit_frames_enable)
        capture_layout.addRow("Max frames:", self.limit_frames)
        capture_layout.addRow(self.limit_time_enable)
        capture_layout.addRow("Max time:", self.limit_time)

        layout.addWidget(capture_group)

        # Apply button
        self._connect_settings()

        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)

        main_layout = QVBoxLayout()
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
        if param_name in self._param_widgets:
            widget = self._param_widgets[param_name]
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
        if param_name in self._param_widgets:
            widget = self._param_widgets[param_name]
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(value)
            elif isinstance(widget, QComboBox):
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)

    def disable_parameter(self, param_name: str):
        """Disable a parameter that doesn't exist in camera"""
        if param_name in self._param_widgets_disable:
            widget = self._param_widgets_disable[param_name]
            if isinstance(widget, tuple):
                for w in widget:
                    w.setEnabled(False)
                    w.setToolTip(f"{param_name} not supported by this camera")
            else:
                widget.setEnabled(False)
                widget.setToolTip(f"{param_name} not supported by this camera")
            log.debug(f"UI - Disabled {param_name} - not available in camera")

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
