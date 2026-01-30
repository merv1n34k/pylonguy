"""Main application - entry point and app logic"""

import sys
import signal
import shutil
import time
import logging
import numpy as np
from pathlib import Path
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QImage, QTransform
from PyQt5.QtGui import QIcon

from .camera import Camera
from .gui import MainWindow
from .thread import CameraThread
from .worker import VideoWorker, WaterfallWorker

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pylonguy")


class PylonApp:
    """Main application controller"""

    def __init__(self, missing_deps=None):
        self.camera = Camera()
        self.thread = None
        self.window = MainWindow()
        self.last_frame = None
        self.current_selection = None
        self.gui_handler = None
        self.waterfall_mode = False
        self.saved_roi_height = None  # Store height when entering waterfall mode
        self.timeout = 0.05
        self.missing_deps = missing_deps or []

        # FPS estimation variables
        self.fps_frame_count = 0
        self.fps_start_time = None
        self.estimated_fps = 0.0

        self._connect_signals()
        self._setup_logging()
        self._update_camera_list()

        # Disable recording if ffmpeg is missing
        if "ffmpeg" in self.missing_deps:
            self.window.preview.btn_record.setEnabled(False)
            self.window.preview.btn_record.setToolTip(
                "Recording disabled: ffmpeg not found"
            )

        # Status update timer for FPS
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._update_fps)
        self.fps_timer.start(200)

        log.info("Application started")

    def _connect_signals(self):
        """Connect GUI signals"""
        self.window.settings.btn_connect.clicked.connect(self.connect_camera)
        self.window.settings.btn_disconnect.clicked.connect(self.disconnect_camera)
        self.window.settings.btn_refresh.clicked.connect(self._update_camera_list)
        self.window.settings.mode_changed.connect(self._on_mode_changed)
        self.window.settings.transform_changed.connect(self._on_transform_changed)
        self.window.settings.ruler_changed.connect(self._on_ruler_changed)
        self.window.settings.camera_settings_changed.connect(self.apply_camera_settings)

        self.window.preview.btn_live.clicked.connect(self.toggle_live)
        self.window.preview.btn_capture.clicked.connect(self.capture_frame)
        self.window.preview.btn_record.clicked.connect(self.toggle_recording)
        self.window.preview.selection_changed.connect(self._on_selection_changed)
        self.window.preview.offset_x_changed.connect(self._on_offset_x_changed)
        self.window.preview.offset_y_changed.connect(self._on_offset_y_changed)

        # Connect log level change
        self.window.log.level_combo.currentTextChanged.connect(
            self._on_log_level_changed
        )

    def _update_camera_list(self):
        """Update camera list in combo box"""
        current_selection = self.window.settings.camera_combo.currentText()
        cameras = Camera.enumerate_cameras()
        self.window.settings.camera_combo.clear()
        if cameras:
            self.window.settings.camera_combo.addItems(cameras)
            # Try to restore previous selection
            index = self.window.settings.camera_combo.findText(current_selection)
            if index >= 0:
                self.window.settings.camera_combo.setCurrentIndex(index)
        else:
            self.window.settings.camera_combo.addItem("No cameras detected")
        log.info(f"Camera list refreshed: {len(cameras)} camera(s) found")

    def _setup_logging(self):
        """Route logging to GUI"""

        class GuiLogHandler(logging.Handler):
            def __init__(self, widget):
                super().__init__()
                self.widget = widget

            def emit(self, record):
                msg = self.format(record)
                self.widget.add(msg)

        self.gui_handler = GuiLogHandler(self.window.log)
        self.gui_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S")
        )
        self.gui_handler.setLevel(logging.INFO)
        log.addHandler(self.gui_handler)
        log.setLevel(logging.INFO)

    def _on_log_level_changed(self, level_text):
        """Handle log level change from GUI"""
        level_map = {"DEBUG": logging.DEBUG, "INFO": logging.INFO}

        level = level_map.get(level_text, logging.INFO)

        # Update both logger and handler levels
        log.setLevel(level)
        if self.gui_handler:
            self.gui_handler.setLevel(level)

        log.info(f"Log level changed to {level_text}")

    def _on_mode_changed(self, mode: str):
        """Handle capture mode change completely"""
        entering_waterfall = mode == "Waterfall"

        # Set mode flag first
        self.waterfall_mode = entering_waterfall

        # Handle height locking
        if entering_waterfall:
            # Save current height if not already 1
            current_height = self.window.settings.roi_height.value()
            if current_height > 1:
                self.saved_roi_height = current_height

            # Set and lock height
            self.window.settings.roi_height.blockSignals(True)
            self.window.settings.roi_height.setValue(1)
            self.window.settings.roi_height.setEnabled(False)
        else:
            # Restore height
            self.window.settings.roi_height.setEnabled(True)
            if hasattr(self, "saved_roi_height") and self.saved_roi_height:
                self.window.settings.roi_height.setValue(self.saved_roi_height)
                self.window.settings.roi_height.blockSignals(False)
                self.saved_roi_height = None

        # Update UI visibility
        settings = self.window.settings
        settings.waterfall_lines.setVisible(entering_waterfall)
        settings.waterfall_lines_label.setVisible(entering_waterfall)
        settings.video_fps.setVisible(not entering_waterfall)
        settings.video_fps_label.setVisible(not entering_waterfall)

        # Update labels
        if entering_waterfall:
            settings.limit_frames_enable.setText("Limit lines")
        else:
            settings.limit_frames_enable.setText("Limit frames")

        # Update preview widget
        if entering_waterfall:
            settings_dict = self.window.settings.get_settings()
            self.window.preview.set_waterfall_mode(
                True,
                settings_dict["roi"]["width"],
                settings_dict["capture"]["waterfall_lines"],
            )
        else:
            self.window.preview.set_waterfall_mode(False)

        # Apply camera settings if connected
        if self.camera.device:
            self.apply_camera_settings()

        log.info(f"Mode changed to: {mode}")

    def _on_transform_changed(self, flip_x: bool, flip_y: bool, rotation: int):
        """Handle transform settings change"""
        self.window.preview.set_transform(flip_x, flip_y, rotation)

    def _on_ruler_changed(self, v: bool, h: bool, radial: bool):
        """Handle ruler mode changes"""
        self.window.preview.set_rulers(v, h, radial)

    def _update_fps(self):
        """Update FPS display from camera or estimation"""
        if self.camera.device and self.thread and self.thread.isRunning():
            # Try to get FPS from camera
            fps = self.camera.get_resulting_framerate()

            # If camera doesn't provide FPS, estimate it
            if fps == 0.0:
                # Calculate FPS from frame count and elapsed time
                if self.fps_start_time:
                    elapsed = time.time() - self.fps_start_time
                    if elapsed > 0:
                        self.estimated_fps = self.fps_frame_count / elapsed
                        fps = self.estimated_fps

                        # Reset counter every 5 seconds to get fresh estimates
                        if elapsed > 5.0:
                            self.fps_frame_count = 0
                            self.fps_start_time = time.time()

            self.window.preview.update_status(fps=fps)

    def _display_frame(self, frame):
        """Display frame in preview"""
        if frame is not None:
            self.last_frame = frame

            # Check if waterfall needs reinitialization
            if not self.window.preview.show_frame(frame):
                if self.waterfall_mode:
                    log.debug("Reinitializing waterfall buffer due to width change")
                    settings = self.window.settings.get_settings()
                    # Get actual width from frame
                    width = frame.shape[1] if len(frame.shape) == 2 else len(frame)
                    self.window.preview.set_waterfall_mode(
                        True, width, settings["capture"]["waterfall_lines"]
                    )

            # Count frames for FPS estimation
            if self.fps_start_time is None:
                self.fps_start_time = time.time()
                self.fps_frame_count = 0
            else:
                self.fps_frame_count += 1

            # Signal thread that frame was processed
            if self.thread:
                self.thread.frame_processed()

    def _apply_transform_to_frame(self, frame: np.ndarray) -> np.ndarray:
        """Apply transform settings to frame for capture"""
        settings = self.window.settings.get_settings()
        transform = settings["transform"]

        if (
            not transform["flip_x"]
            and not transform["flip_y"]
            and transform["rotation"] == 0
        ):
            return frame

        result = frame.copy()

        # Apply flips
        if transform["flip_x"]:
            result = np.fliplr(result)
        if transform["flip_y"]:
            result = np.flipud(result)

        # Apply rotation
        if transform["rotation"] != 0:
            angle = transform["rotation"]
            k = (angle % 360) // 90
            result = np.rot90(result, k)

        return result

    def start_live(self):
        """Start live preview"""
        if not self.camera.device:
            log.error("Camera not connected")
            return

        # Reset FPS estimation
        self.fps_frame_count = 0
        self.fps_start_time = None
        self.estimated_fps = 0.0

        self.thread = CameraThread(self.camera, waterfall_mode=self.waterfall_mode)
        self.thread.frame_ready.connect(self._display_frame)
        self.thread.stats_update.connect(self._update_stats)
        self.thread.recording_stopped.connect(self._on_recording_stopped)

        self.thread.set_preview_enabled(True)
        self.thread.start()

        self.window.preview.btn_live.setText("Stop Live")
        log.debug(
            "Live preview started"
            + (" (Waterfall mode)" if self.waterfall_mode else "")
        )

    def stop_live(self):
        """Stop live preview"""
        if self.thread:
            self.thread.stop()
            self.thread = None

        # Reset FPS estimation
        self.fps_frame_count = 0
        self.fps_start_time = None
        self.estimated_fps = 0.0

        self.window.preview.btn_live.setText("Start Live")
        self.window.preview.update_status(fps=0, recording=False, frames=0, elapsed=0)
        self.window.preview.show_message("No Camera")
        log.debug("Live preview stopped")

    def connect_camera(self):
        """Connect to camera with optional defaults"""
        camera_index = self.window.settings.camera_combo.currentIndex()
        if (
            camera_index < 0
            or self.window.settings.camera_combo.currentText() == "No cameras detected"
        ):
            log.error("No camera selected")
            return

        if self.camera.open(camera_index, apply_defaults=True):
            # Update GUI parameter limits from camera
            params_to_update = [
                "Width",
                "Height",
                "ExposureTime",
                "Gain",
                "AcquisitionFrameRate",
            ]

            for param in params_to_update:
                info = self.camera.get_parameter(param)
                if info:
                    self.window.settings.update_parameter_limits(
                        param, info.get("min"), info.get("max"), info.get("inc")
                    )
                    if "value" in info:
                        self.window.settings.set_parameter_value(param, info["value"])

            # Check for availability of optional parameters
            optional_params = [
                "SensorReadoutMode",
                "BinningHorizontal",
                "BinningVertical",
                "AcquisitionFrameRate",
                "DeviceLinkThroughputLimit",
            ]

            for param in optional_params:
                info = self.camera.get_parameter(param)
                if not info or "value" not in info:
                    self.window.settings.disable_parameter(param)
                else:
                    if param == "SensorReadoutMode" and "symbolics" in info:
                        self.window.settings.update_parameter_limits(
                            param, options=info["symbolics"]
                        )

            # Check for pixel format options
            pf_info = self.camera.get_parameter("PixelFormat")
            if pf_info and "symbolics" in pf_info:
                options = [fmt for fmt in pf_info["symbolics"]]
                if options:
                    self.window.settings.update_parameter_limits(
                        "PixelFormat", options=options
                    )

            # Update slider ranges based on camera capabilities
            offset_x_info = self.camera.get_parameter("OffsetX")
            offset_y_info = self.camera.get_parameter("OffsetY")
            if offset_x_info:
                self.window.preview.offset_x_slider.setRange(
                    offset_x_info.get("min", 0), 4096
                )
                self.window.preview.offset_x_slider.setValue(
                    offset_x_info.get("value", 0)
                )
            if offset_y_info:
                self.window.preview.offset_y_slider.setRange(
                    offset_y_info.get("min", 0), 3072
                )
                self.window.preview.offset_y_slider.setValue(
                    offset_y_info.get("value", 0)
                )

            self.window.settings.btn_connect.setEnabled(False)
            self.window.settings.btn_disconnect.setEnabled(True)

            # Auto-apply selected preset if checkbox is ticked
            if self.window.settings.auto_apply_check.isChecked():
                self.window.settings.apply_preset()
                self.apply_camera_settings()

            if self.waterfall_mode:
                self.camera.set_parameter("Height", 1)
                self.window.settings.roi_height.setValue(1)
                h_info = {"value": 1}
            else:
                h_info = self.camera.get_parameter("Height")

            # Get current ROI
            w_info = self.camera.get_parameter("Width")
            if w_info and h_info:
                w = w_info.get("value", 640)
                h = h_info.get("value", 480)
                self.window.preview.update_status(roi=f" {w}x{h} ")
                log.info(f"Camera connected: {w}x{h}")
        else:
            log.error("Failed to connect camera")

    def disconnect_camera(self):
        """Disconnect camera"""
        self.stop_live()
        self.camera.close()

        self.window.settings.btn_connect.setEnabled(True)
        self.window.settings.btn_disconnect.setEnabled(False)

        log.info("Camera disconnected")

    def apply_camera_settings(self):
        """Apply settings to camera"""
        if not self.camera.device:
            log.warning("Camera not connected")
            return

        # Stop preview if running
        was_live = False
        if self.thread and self.thread.isRunning():
            if self.thread.recording:
                log.warning("Cannot apply settings while recording")
                return
            was_live = True
            self.stop_live()
            time.sleep(self.timeout)

        try:
            settings = self.window.settings.get_settings()

            # Build camera settings dict
            cam_settings = {}

            # ROI settings - handle in correct order
            if settings["roi"]["offset_x"] != 0 or settings["roi"]["offset_y"] != 0:
                self.camera.set_parameter("OffsetX", 0)
                self.camera.set_parameter("OffsetY", 0)

            cam_settings["Width"] = settings["roi"]["width"]
            cam_settings["Height"] = (
                1 if self.waterfall_mode else settings["roi"]["height"]
            )
            cam_settings["OffsetX"] = settings["roi"]["offset_x"]
            cam_settings["OffsetY"] = settings["roi"]["offset_y"]

            # Only apply binning if supported
            if self.window.settings.binning_horizontal.isEnabled():
                cam_settings["BinningHorizontal"] = settings["roi"]["binning_h"]
                cam_settings["BinningVertical"] = settings["roi"]["binning_v"]

            # Acquisition settings
            cam_settings["ExposureTime"] = settings["acquisition"]["exposure"]
            cam_settings["Gain"] = settings["acquisition"]["gain"]
            cam_settings["PixelFormat"] = settings["acquisition"]["pixel_format"]

            # Only apply sensor mode if supported
            if (
                settings["acquisition"]["sensor_mode"]
                and self.window.settings.sensor_mode.isEnabled()
            ):
                cam_settings["SensorReadoutMode"] = settings["acquisition"][
                    "sensor_mode"
                ]

            # Frame rate settings - only if supported
            if self.window.settings.framerate_enable.isEnabled():
                if settings["framerate"]["enabled"]:
                    cam_settings["AcquisitionFrameRateEnable"] = True
                    cam_settings["AcquisitionFrameRate"] = settings["framerate"]["fps"]
                else:
                    cam_settings["AcquisitionFrameRateEnable"] = False

            # Throughput settings - only if supported
            if self.window.settings.throughput_enable.isEnabled():
                if settings["framerate"]["throughput_enabled"]:
                    cam_settings["DeviceLinkThroughputLimitMode"] = "On"
                    cam_settings["DeviceLinkThroughputLimit"] = int(
                        settings["framerate"]["throughput_limit"] * 1000000
                    )
                else:
                    cam_settings["DeviceLinkThroughputLimitMode"] = "Off"

            # Apply all settings
            self.camera.apply_settings(cam_settings)

            # Update ROI display
            self.window.preview.update_status(
                roi=f" {settings['roi']['width']}x{settings['roi']['height']} "
            )

            # Update waterfall buffer if in waterfall mode
            if self.waterfall_mode:
                self.window.preview.set_waterfall_mode(
                    True,
                    settings["roi"]["width"],
                    settings["capture"]["waterfall_lines"],
                )

            log.debug("Camera settings applied")

        except Exception as e:
            log.error(f"Failed to apply settings: {e}")

        finally:
            if was_live:
                time.sleep(self.timeout)
                self.start_live()

    def toggle_live(self):
        """Toggle live preview"""
        if self.thread:
            self.stop_live()
        else:
            self.start_live()

    def capture_frame(self):
        """Capture single frame or waterfall with transforms applied"""
        if self.waterfall_mode:
            # Capture from waterfall buffer
            frame = self.window.preview.get_waterfall_buffer()
            if frame is None:
                log.error("No waterfall buffer available")
                return
        else:
            # Normal frame capture
            frame = self.last_frame
            if frame is None and self.camera.device:
                frame = self.camera.grab_frame()

        if frame is not None:
            settings = self.window.settings.get_settings()
            base_path = settings["capture"]["path"]
            img_prefix = settings["capture"]["image_prefix"]

            # Apply transforms for image capture
            frame = self._apply_transform_to_frame(frame)

            # Handle selection
            selection = self.window.preview.get_selection()
            suffix = ""
            if selection and selection.isValid():
                x = max(0, selection.x())
                y = max(0, selection.y())
                w = min(selection.width(), frame.shape[1] - x)
                h = min(selection.height(), frame.shape[0] - y)

                if w > 0 and h > 0:
                    frame = frame[y : y + h, x : x + w]
                    suffix = "_sel"
                    log.info(f"Captured selection: {w}x{h}+{x}+{y}")

            # Generate filename with mandatory timestamp
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if self.waterfall_mode:
                suffix += "_waterfall"
            path = f"{base_path}/{img_prefix}{suffix}_{timestamp}.png"
            Path(path).parent.mkdir(parents=True, exist_ok=True)

            # Save frame
            h, w = frame.shape[:2]
            if frame.dtype == np.uint16:
                frame = (frame >> 8).astype(np.uint8)

            if not frame.flags["C_CONTIGUOUS"]:
                frame = np.ascontiguousarray(frame)

            if len(frame.shape) == 2:
                img = QImage(frame.data, w, h, w, QImage.Format_Grayscale8)
            else:
                img = QImage(frame.data, w, h, w * 3, QImage.Format_RGB888)

            if img.save(path):
                log.info(
                    f"{'Waterfall' if self.waterfall_mode else 'Frame'} captured: {path}"
                )
                if (
                    settings["transform"]["flip_x"]
                    or settings["transform"]["flip_y"]
                    or settings["transform"]["rotation"] != 0
                ):
                    log.info("(Transform applied to saved image)")
            else:
                log.error("Failed to save frame")
        else:
            log.error("No frame available")

    def toggle_recording(self):
        """Toggle recording"""
        if self.thread and self.thread.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        """Start recording (frames or waterfall)"""
        if not self.thread:
            log.error("Start live preview first")
            return

        settings = self.window.settings.get_settings()

        self.window.settings.setLocked(True)

        # Configure preview
        if settings["capture"]["preview_off"]:
            self.thread.set_preview_enabled(False)
            if self.waterfall_mode:
                self.window.preview.show_message(
                    "Recording Waterfall...\n(Preview disabled)"
                )
            else:
                self.window.preview.show_message("Recording...\n(Preview disabled)")

        # Create base output directory if needed
        base_path = Path(settings["capture"]["path"])
        base_path.mkdir(parents=True, exist_ok=True)

        # Get ROI for dimensions
        w = self.camera.get_parameter("Width").get("value", 640)
        h = self.camera.get_parameter("Height").get("value", 480)

        if self.waterfall_mode:
            settings = self.window.settings.get_settings()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            waterfall_path = (
                base_path / f"{settings['capture']['video_prefix']}_{timestamp}.wtf"
            )

            worker = WaterfallWorker(str(waterfall_path), w)
        else:
            # Create unique frames subdirectory for video
            timestamp = time.strftime("%Y%m%d_%H%M%S_%f")[:-3]
            frames_dir = base_path / f"raw_{timestamp}"

            worker = VideoWorker(
                str(frames_dir), w, h, settings["capture"]["video_fps"]
            )

        # Start recording with limits
        max_frames = settings["capture"]["limit_frames"]
        max_time = settings["capture"]["limit_time"]

        if self.thread.start_recording(worker, max_frames, max_time):
            self.window.preview.btn_record.setText("Stop Recording")
            if self.waterfall_mode:
                log.info(
                    f"Waterfall recording started: {worker.output_path if hasattr(worker, 'output_path') else 'waterfall'}"
                )
            else:
                log.info(f"Recording started: {frames_dir}")
        else:
            log.error("Failed to start recording")

    def stop_recording(self):
        """Stop recording"""
        if self.thread:
            frames = self.thread.stop_recording()
            self.window.preview.btn_record.setText("Record")

            self.window.settings.setLocked(False)

            # Re-enable preview
            self.thread.set_preview_enabled(True)

            if self.waterfall_mode:
                log.info(f"Waterfall recording stopped: {frames} lines")
            else:
                log.info(f"Recording stopped: {frames} frames")

    def _update_stats(self, stats):
        """Update recording statistics"""
        self.window.preview.update_status(
            recording=stats["recording"],
            frames=stats["frames"],
            elapsed=stats["elapsed"],
        )

    def _on_selection_changed(self, rect):
        """Handle selection changes"""
        self.current_selection = rect

    def _on_offset_x_changed(self, value):
        """Handle X offset slider change"""
        if self.camera.device:
            # Update camera immediately
            self.camera.set_parameter("OffsetX", value)
            # Update settings widget to stay in sync
            self.window.settings.roi_offset_x.setValue(value)

    def _on_offset_y_changed(self, value):
        """Handle Y offset slider change"""
        if self.camera.device:
            # Update camera immediately
            self.camera.set_parameter("OffsetY", value)
            # Update settings widget to stay in sync
            self.window.settings.roi_offset_y.setValue(value)

    def _on_recording_stopped(self):
        """Handle auto-stop of recording"""
        self.stop_recording()
        log.info("Recording auto-stopped (limit reached)")

    def run(self):
        """Show window and start application"""
        self.window.show()
        self.window.settings.btn_disconnect.setEnabled(False)


def check_dependencies():
    """Check for required external dependencies. Returns list of missing deps."""
    missing = []

    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")

    return missing


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("PylonGuy")
    app.setApplicationDisplayName("PylonGuy")
    app.setStyle("Fusion")

    # Set application icon
    icon_path = Path(__file__).parent / "assets" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Check dependencies before starting
    missing = check_dependencies()
    if missing:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Missing Dependencies")
        msg.setText(f"Required dependencies not found: {', '.join(missing)}")
        msg.setInformativeText(
            "Video recording will not work without ffmpeg.\n\n"
            "Install ffmpeg and ensure it's in your PATH."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

    pylon_app = PylonApp(missing_deps=missing)
    pylon_app.run()

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    # Timer to allow Python to process signals during Qt event loop
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(100)

    app.aboutToQuit.connect(lambda: pylon_app.disconnect_camera())

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
