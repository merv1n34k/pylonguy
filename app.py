"""Main application - entry point and app logic"""
import sys
import time
import logging
import numpy as np
import csv
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from camera import Camera
from gui import MainWindow
from thread import CameraThread
from worker import VideoWriter, FrameDumper

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger("pylonguy")

class PylonApp:
    """Main application controller"""

    def __init__(self):
        self.camera = Camera()
        self.thread = None
        self.window = MainWindow()
        self.last_frame = None
        self.frame_display_count = 0  # Debug counter
        self.current_selection = None  # Store current selection
        self.recording_base_path = None  # Store recording path for report

        # Connect signals
        self._connect_signals()

        # Setup GUI logging
        self._setup_logging()

        # Status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(100)  # 10 Hz update

        log.info("Application started")

    def _connect_signals(self):
        """Connect GUI signals to handlers"""
        # Connection
        self.window.settings.btn_connect.clicked.connect(self.connect_camera)
        self.window.settings.btn_disconnect.clicked.connect(self.disconnect_camera)

        # Settings
        self.window.settings.settings_changed.connect(self.apply_settings)

        # Preview controls
        self.window.preview.btn_live.clicked.connect(self.toggle_live)
        self.window.preview.btn_capture.clicked.connect(self.capture_frame)
        self.window.preview.btn_record.clicked.connect(self.toggle_recording)

        # Selection
        self.window.preview.selection_changed.connect(self._on_selection_changed)

    def _setup_logging(self):
        """Route logging to GUI"""
        class GuiLogHandler(logging.Handler):
            def __init__(self, widget):
                super().__init__()
                self.widget = widget

            def emit(self, record):
                msg = self.format(record)
                self.widget.add(msg)

        handler = GuiLogHandler(self.window.log)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', '%H:%M:%S'))
        log.addHandler(handler)

    def connect_camera(self):
        """Connect to camera"""
        if self.camera.open():
            # Update GUI with current settings and camera limits
            w, h, ox, oy = self.camera.get_roi()

            # Get camera limits if available
            if self.camera.device:
                try:
                    # Update ROI limits based on camera
                    try:
                        width_min = self.camera.device.Width.GetMin()
                        width_max = self.camera.device.Width.GetMax()
                        width_inc = self.camera.device.Width.GetInc()
                        self.window.settings.roi_width.setRange(width_min, width_max)
                        self.window.settings.roi_width.setSingleStep(width_inc)
                    except:
                        log.debug("Could not get width limits")

                    try:
                        height_min = self.camera.device.Height.GetMin()
                        height_max = self.camera.device.Height.GetMax()
                        height_inc = self.camera.device.Height.GetInc()
                        self.window.settings.roi_height.setRange(height_min, height_max)
                        self.window.settings.roi_height.setSingleStep(height_inc)
                    except:
                        log.debug("Could not get height limits")

                    # Update offset ranges
                    try:
                        offset_x_max = self.camera.device.OffsetX.GetMax()
                        offset_x_inc = self.camera.device.OffsetX.GetInc()
                        self.window.settings.roi_offset_x.setRange(0, offset_x_max)
                        self.window.settings.roi_offset_x.setSingleStep(offset_x_inc)
                    except:
                        log.debug("Could not get offset X limits")

                    try:
                        offset_y_max = self.camera.device.OffsetY.GetMax()
                        offset_y_inc = self.camera.device.OffsetY.GetInc()
                        self.window.settings.roi_offset_y.setRange(0, offset_y_max)
                        self.window.settings.roi_offset_y.setSingleStep(offset_y_inc)
                    except:
                        log.debug("Could not get offset Y limits")

                    # Update exposure limits and current value
                    try:
                        exp_min = self.camera.device.ExposureTime.GetMin()
                        exp_max = self.camera.device.ExposureTime.GetMax()
                        self.window.settings.exposure.setRange(exp_min, exp_max)
                        current_exp = self.camera.device.ExposureTime.GetValue()
                        self.window.settings.exposure.setValue(current_exp)
                    except:
                        # Try older property name
                        try:
                            exp_min = self.camera.device.ExposureTimeAbs.GetMin()
                            exp_max = self.camera.device.ExposureTimeAbs.GetMax()
                            self.window.settings.exposure.setRange(exp_min, exp_max)
                            current_exp = self.camera.device.ExposureTimeAbs.GetValue()
                            self.window.settings.exposure.setValue(current_exp)
                        except:
                            pass

                    # Update gain limits and current value
                    try:
                        gain_min = self.camera.device.Gain.GetMin()
                        gain_max = self.camera.device.Gain.GetMax()
                        self.window.settings.gain.setRange(gain_min, gain_max)
                        current_gain = self.camera.device.Gain.GetValue()
                        self.window.settings.gain.setValue(current_gain)
                    except:
                        # Try raw gain property
                        try:
                            gain_min = self.camera.device.GainRaw.GetMin()
                            gain_max = self.camera.device.GainRaw.GetMax()
                            self.window.settings.gain.setRange(gain_min, gain_max)
                            current_gain = self.camera.device.GainRaw.GetValue()
                            self.window.settings.gain.setValue(current_gain)
                        except:
                            pass

                    # Get current sensor mode if available
                    try:
                        # Clear and check if sensor mode is supported
                        self.window.settings.sensor_mode.clear()

                        # Try to access the feature
                        current_mode = self.camera.device.SensorReadoutMode.GetValue()

                        # If we get here, it's supported - get available modes
                        try:
                            modes = self.camera.device.SensorReadoutMode.GetSymbolics()
                            for mode in modes:
                                self.window.settings.sensor_mode.addItem(mode)
                        except:
                            # GetSymbolics not available, use current value as hint
                            if 'Fast' in current_mode or 'fast' in current_mode:
                                self.window.settings.sensor_mode.addItems(["Normal", "Fast"])
                            else:
                                self.window.settings.sensor_mode.addItems(["Normal", "Fast"])

                        # Set current mode
                        idx = self.window.settings.sensor_mode.findText(current_mode)
                        if idx >= 0:
                            self.window.settings.sensor_mode.setCurrentIndex(idx)
                    except (AttributeError, Exception):
                        # Feature not supported - keep default options but disable
                        self.window.settings.sensor_mode.addItems(["Normal", "Fast"])
                        self.window.settings.sensor_mode.setEnabled(False)
                        self.window.settings.sensor_mode.setToolTip("Not supported by this camera")

                    # Check framerate settings
                    try:
                        is_enabled = self.camera.device.AcquisitionFrameRateEnable.GetValue()
                        self.window.settings.framerate_enable.setChecked(is_enabled)

                        if is_enabled:
                            current_fps = self.camera.device.AcquisitionFrameRate.GetValue()
                            self.window.settings.framerate.setValue(current_fps)
                    except:
                        # Camera may not support framerate control
                        pass

                except Exception as e:
                    log.warning(f"Could not update GUI limits from camera: {e}")

            # Set current values
            self.window.settings.roi_width.setValue(w)
            self.window.settings.roi_height.setValue(h)
            self.window.settings.roi_offset_x.setValue(ox)
            self.window.settings.roi_offset_y.setValue(oy)

            self.window.settings.btn_connect.setEnabled(False)
            self.window.settings.btn_disconnect.setEnabled(True)

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

    def apply_settings(self):
        """Apply settings to camera"""
        if not self.camera.device:
            log.warning("Camera not connected")
            return

        settings = self.window.settings.get_settings()

        # Apply ROI
        roi = settings['roi']
        self.camera.set_roi(roi['width'], roi['height'], roi['offset_x'], roi['offset_y'])

        # Apply acquisition settings
        acq = settings['acquisition']
        self.camera.set_exposure(acq['exposure'])
        self.camera.set_gain(acq['gain'])
        self.camera.set_sensor_mode(acq['sensor_mode'])
        self.camera.set_framerate(acq['framerate_enable'], acq['framerate'])

        # Update area display if pixel size changed
        self.window.preview._update_areas()

        log.info("Settings applied")

    def toggle_live(self):
        """Toggle live preview"""
        if self.thread:
            self.stop_live()
        else:
            self.start_live()

    def start_live(self):
        """Start live preview"""
        if not self.camera.device:
            log.error("Camera not connected")
            return

        self.thread = CameraThread(self.camera)

        # Connect thread signals
        self.thread.frame_ready.connect(self._display_frame)
        self.thread.stats_update.connect(self._update_stats)
        self.thread.recording_stopped.connect(self._on_recording_stopped)

        # Start with preview enabled
        self.thread.set_preview_options(True, 1)  # Show every frame initially

        self.thread.start()

        self.window.preview.btn_live.setText("Stop Live")
        self.window.preview.update_status(live=True)
        log.info("Live preview started")

    def stop_live(self):
        """Stop live preview"""
        if self.thread:
            self.thread.stop()
            self.thread = None

        self.window.preview.btn_live.setText("Start Live")
        self.window.preview.update_status(live=False, fps=0, frames=0)
        self.window.preview.show_message("No Camera")
        log.info("Live preview stopped")

    def capture_frame(self):
        """Capture single frame (full or selection)"""
        frame = self.last_frame
        if frame is None and self.camera.device:
            frame = self.camera.grab_frame()

        if frame is not None:
            # Check if we should crop to selection
            selection = self.window.preview.get_selection()
            capture_type = "full"

            if selection and selection.isValid():
                # Crop frame to selection
                x = max(0, selection.x())
                y = max(0, selection.y())
                w = min(selection.width(), frame.shape[1] - x)
                h = min(selection.height(), frame.shape[0] - y)

                if w > 0 and h > 0:
                    frame = frame[y:y+h, x:x+w]
                    capture_type = "selection"
                    log.info(f"Cropping to selection: {w}x{h}+{x}+{y}")

            # Generate filename with "img" prefix
            settings = self.window.settings.get_settings()
            base_path = settings['output']['path']

            # Replace "video" with "img" in path if present
            if "video" in base_path:
                base_path = base_path.replace("video", "img")
            else:
                base_path = f"./output/img"

            if settings['output']['append_timestamp']:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                if capture_type == "selection":
                    path = f"{base_path}_selection_{timestamp}.png"
                else:
                    path = f"{base_path}_{timestamp}.png"
            else:
                if capture_type == "selection":
                    path = f"{base_path}_selection.png"
                else:
                    path = f"{base_path}.png"

            # Ensure directory exists
            Path(path).parent.mkdir(parents=True, exist_ok=True)

            # Save using Qt
            from PyQt5.QtGui import QImage
            h, w = frame.shape[:2]

            if frame.dtype == np.uint16:
                frame = (frame >> 8).astype(np.uint8)

            # Ensure frame is contiguous
            if not frame.flags['C_CONTIGUOUS']:
                frame = np.ascontiguousarray(frame)

            if len(frame.shape) == 2:
                img = QImage(frame.data, w, h, w, QImage.Format_Grayscale8)
            else:
                img = QImage(frame.data, w, h, w * 3, QImage.Format_RGB888)

            if img.save(path):
                log.info(f"Frame captured ({capture_type}): {path}")
            else:
                log.error("Failed to save frame")
        else:
            log.error("No frame available")

    def create_raw_stats_report(self, recording_stats):
        """Create CSV with time, frame count, and calculated fps columns"""
        if not self.recording_base_path:
            log.warning("No recording base path available for raw stats")
            return

        # Use same base path as recording with _stats suffix
        path = f"{self.recording_base_path}_stats.csv"

        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)

                # Write header
                writer.writerow(['time', 'frame_count', 'fps'])

                frame_count = recording_stats['frame_count']

                # Use actual frame timestamps if available
                if 'frame_times' in recording_stats and recording_stats['frame_times']:
                    times = recording_stats['frame_times']
                    
                    for i, time_val in enumerate(times):
                        frame_num = i + 1
                        
                        # Calculate FPS as frame_count / elapsed_time
                        if time_val > 0:
                            fps_val = frame_num / time_val
                        else:
                            fps_val = 0.0
                        
                        writer.writerow([f'{time_val:.6f}', frame_num, f'{fps_val:.2f}'])
                        
                elif frame_count > 0:
                    # Generate evenly spaced time points based on average FPS
                    elapsed_time = recording_stats['elapsed_time']
                    if elapsed_time > 0:
                        avg_fps = frame_count / elapsed_time
                        time_interval = 1.0 / avg_fps if avg_fps > 0 else 0.1
                        
                        for i in range(frame_count):
                            time_val = i * time_interval
                            frame_num = i + 1
                            
                            # Calculate FPS as frame_count / elapsed_time at this point
                            if time_val > 0:
                                fps_val = frame_num / time_val
                            else:
                                fps_val = 0.0 if i == 0 else avg_fps
                            
                            writer.writerow([f'{time_val:.6f}', frame_num, f'{fps_val:.2f}'])
                else:
                    # Empty recording - write single row with zeros
                    writer.writerow([0.0, 0, 0.0])

            log.info(f"Raw stats saved: {path}")

        except Exception as e:
            log.error(f"Failed to create raw stats: {e}")

    def create_settings_report(self, recording_stats):
        """Create CSV report with parameter-value pairs (no section headers)"""
        if not self.recording_base_path:
            log.warning("No recording base path available for settings report")
            return

        settings = self.window.settings.get_settings()

        # Use same base path as recording with _settings suffix
        path = f"{self.recording_base_path}_settings.csv"

        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)

                # Write header
                writer.writerow(['Parameter', 'Value'])
                
                # General info
                writer.writerow(['Report Generated', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                writer.writerow(['Recording Path', self.recording_base_path])
                
                # Recording stats
                writer.writerow(['Frame Count', recording_stats['frame_count']])
                writer.writerow(['Duration (s)', f"{recording_stats['elapsed_time']:.2f}"])
                fps = recording_stats['frame_count'] / recording_stats['elapsed_time'] if recording_stats['elapsed_time'] > 0 else 0
                writer.writerow(['Average FPS', f'{fps:.2f}'])
                
                # Camera ROI
                if self.camera.device:
                    w, h, ox, oy = self.camera.get_roi()
                    writer.writerow(['ROI Width', w])
                    writer.writerow(['ROI Height', h])
                    writer.writerow(['ROI Offset X', ox])
                    writer.writerow(['ROI Offset Y', oy])
                    
                    # Camera area
                    area_px2 = w * h
                    px_to_um = settings['roi']['px_to_um']
                    writer.writerow(['Camera Area (px²)', area_px2])
                    if px_to_um != 1.0:
                        area_um2 = area_px2 * (px_to_um ** 2)
                        writer.writerow(['Camera Area (μm²)', f'{area_um2:.2f}'])
                
                # Acquisition settings
                acq = settings['acquisition']
                writer.writerow(['Exposure (μs)', acq['exposure']])
                writer.writerow(['Gain', acq['gain']])
                writer.writerow(['Sensor Mode', acq['sensor_mode']])
                writer.writerow(['Framerate Limit', f"{acq['framerate']} Hz" if acq['framerate_enable'] else 'Disabled'])
                writer.writerow(['Pixel Size (μm/px)', settings['roi']['px_to_um']])
                
                # Recording settings
                rec = settings['recording']
                writer.writerow(['Recording Mode', rec['mode']])
                writer.writerow(['Video FPS', settings['output']['video_fps']])
                if rec['mode'] == "Frame Dump":
                    writer.writerow(['Keep Frames', rec['keep_frames']])
                writer.writerow(['Frame Limit', rec['limit_frames'] if rec['limit_frames'] else 'None'])
                writer.writerow(['Time Limit (s)', rec['limit_time'] if rec['limit_time'] else 'None'])

            log.info(f"Settings report saved: {path}")

        except Exception as e:
            log.error(f"Failed to create settings report: {e}")

    def _on_selection_changed(self, rect):
        """Handle selection changes"""
        if rect and rect.isValid():
            self.current_selection = rect
            log.debug(f"Selection changed: {rect.width()}x{rect.height()}+{rect.x()}+{rect.y()}")
        else:
            self.current_selection = None
            log.debug("Selection cleared")

    def toggle_recording(self):
        """Toggle video recording"""
        if self.thread and self.thread.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        """Start video recording"""
        if not self.thread:
            log.error("Live preview not started. Please start live preview first.")
            return

        settings = self.window.settings.get_settings()

        # Get ROI for video dimensions
        w, h, _, _ = self.camera.get_roi()

        # Generate output path
        base_path = settings['output']['path']
        if settings['output']['append_timestamp']:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            base_path = f"{base_path}_{timestamp}"

        # Store base path for report
        self.recording_base_path = base_path

        # Create writer based on mode
        if settings['recording']['mode'] == "Frame Dump":
            keep_frames = settings['recording'].get('keep_frames', False)
            writer = FrameDumper(
                f"{base_path}_frames",
                w, h,
                settings['output']['video_fps'],
                keep_frames=keep_frames
            )
            log.info(f"Using frame dump mode (keep frames: {keep_frames})")
        else:
            writer = VideoWriter(f"{base_path}.mp4", w, h, settings['output']['video_fps'])
            log.info("Using real-time video mode")

        # Update preview settings for recording
        if settings['preview']['off_during_recording']:
            self.thread.set_preview_options(False, 1)
            self.window.preview.show_message("Recording...\n(Preview disabled)")
        else:
            self.thread.set_preview_options(True, settings['preview']['nth_frame'])

        # Start recording
        if self.thread.start_recording(
            writer,
            settings['recording']['limit_frames'],
            settings['recording']['limit_time']
        ):
            self.window.preview.btn_record.setText("Stop Recording")
            log.info(f"Recording started: {base_path}")
        else:
            log.error("Failed to start recording")

    def stop_recording(self, auto_stopped=False):
        """Stop video recording"""
        if self.thread:
            # Store recording stats before stopping
            recording_stats = {
                'frame_count': self.thread.frame_count,
                'elapsed_time': time.time() - self.thread.start_time if self.thread.start_time else 0,
                'start_time': self.thread.start_time,
                'frame_times': getattr(self.thread, 'frame_times', [])  # Get frame times if available
            }

            frames = self.thread.stop_recording()
            self.window.preview.btn_record.setText("Record")

            # Always restore full preview after recording
            self.thread.set_preview_options(True, 1)

            # Create reports based on settings
            if self.recording_base_path:
                settings = self.window.settings.get_settings()
                if settings['recording'].get('export_raw_stats', False):
                    self.create_raw_stats_report(recording_stats)
                if settings['recording'].get('export_settings', False):
                    self.create_settings_report(recording_stats)

            log.info(f"Recording stopped: {frames} frames")

    def _display_frame(self, frame):
        """Display frame in preview"""
        if frame is None:
            log.warning("Received None frame for display")
            return

        self.last_frame = frame
        self.frame_display_count += 1
        self.window.preview.show_frame(frame)

    def _update_stats(self, stats):
        """Update recording statistics"""
        self.window.preview.update_status(
            fps=stats['fps'],
            frames=stats['frames']
        )

    def _update_status(self):
        """Update status display"""
        if self.camera.device:
            w, h, _, _ = self.camera.get_roi()
            self.window.preview.update_status(roi=f"{w}x{h}")

            # Update camera area if the ROI changed
            if self.window.preview.original_frame_size != (w, h):
                self.window.preview.original_frame_size = (w, h)
                self.window.preview._update_areas()

    def _on_recording_stopped(self):
        """Handle auto-stop of recording"""
        self.stop_recording(auto_stopped=True)
        log.info("Recording auto-stopped (limit reached)")

    def run(self):
        """Show window and start application"""
        self.window.show()

        # Set initial button states
        self.window.settings.btn_disconnect.setEnabled(False)

def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern look

    pylon_app = PylonApp()
    pylon_app.run()

    # Cleanup on exit
    app.aboutToQuit.connect(lambda: pylon_app.disconnect_camera())

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
