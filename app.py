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
        self.frame_display_count = 0
        self.current_selection = None
        self.recording_base_path = None

        # Connect signals
        self._connect_signals()

        # Setup GUI logging
        self._setup_logging()

        # Status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(100)  # 10 Hz update

        # FPS update timer (separate for camera's ResultingFrameRate)
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._update_fps)
        self.fps_timer.start(500)  # 2 Hz update

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
            # Update GUI with camera capabilities
            self.window.settings.update_from_camera(self.camera)

            # Get current settings from camera
            w, h, ox, oy = self.camera.get_roi()

            # Update buttons
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

        # Store preview state and stop if running
        was_live = False
        was_recording = False

        if self.thread and self.thread.isRunning():
            was_live = True
            if self.thread.recording:
                was_recording = True
                log.warning("Cannot apply settings while recording. Please stop recording first.")
                return

            # Stop preview temporarily
            log.info("Stopping preview to apply settings...")
            self.stop_live()
            # Small delay to ensure thread fully stops
            time.sleep(0.1)

        try:
            settings = self.window.settings.get_settings()

            # Apply ROI and binning
            roi = settings['roi']
            self.camera.set_roi(roi['width'], roi['height'], roi['offset_x'], roi['offset_y'])
            self.camera.set_binning(roi['binning_h'], roi['binning_v'])

            # Apply acquisition settings
            acq = settings['acquisition']
            self.camera.set_exposure(acq['exposure'])
            self.camera.set_gain(acq['gain'])
            self.camera.set_pixel_format(acq['pixel_format'])
            self.camera.set_sensor_readout_mode(acq['sensor_mode'])

            # Apply frame rate controls
            fr = settings['framerate']
            self.camera.set_acquisition_framerate(fr['enabled'], fr['target_fps'] if fr['enabled'] else None)
            self.camera.set_device_link_throughput(fr['throughput_enabled'],
                                               fr['throughput_limit'] if fr['throughput_enabled'] else None)

            # Update area display if pixel size changed
            self.window.preview._update_areas()

            log.info("Settings applied successfully")

        except Exception as e:
            log.error(f"Failed to apply settings: {e}")

        finally:
            # Restart preview if it was running
            if was_live:
                log.info("Restarting preview...")
                time.sleep(0.1)  # Small delay before restarting
                self.start_live()

    def _update_fps(self):
        """Update FPS display from camera's ResultingFrameRate"""
        if self.camera.device and self.thread and self.thread.isRunning():
            fps = self.camera.get_resulting_framerate()
            self.window.settings.update_fps_display(fps)

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
        self.thread.set_preview_options(True, 1)

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

        path = f"{self.recording_base_path}_stats.csv"
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['time', 'frame_count', 'fps'])

                frame_count = recording_stats['frame_count']

                if 'frame_times' in recording_stats and recording_stats['frame_times']:
                    times = recording_stats['frame_times']

                    for i, time_val in enumerate(times):
                        frame_num = i + 1
                        fps_val = frame_num / time_val if time_val > 0 else 0.0
                        writer.writerow([f'{time_val:.6f}', frame_num, f'{fps_val:.2f}'])

                elif frame_count > 0:
                    elapsed_time = recording_stats['elapsed_time']
                    if elapsed_time > 0:
                        avg_fps = frame_count / elapsed_time
                        time_interval = 1.0 / avg_fps if avg_fps > 0 else 0.1

                        for i in range(frame_count):
                            time_val = i * time_interval
                            frame_num = i + 1
                            fps_val = frame_num / time_val if time_val > 0 else 0.0
                            writer.writerow([f'{time_val:.6f}', frame_num, f'{fps_val:.2f}'])
                else:
                    writer.writerow([0.0, 0, 0.0])

            log.info(f"Raw stats saved: {path}")

        except Exception as e:
            log.error(f"Failed to create raw stats: {e}")

    def create_settings_report(self, recording_stats):
        """Create CSV report with parameter-value pairs"""
        if not self.recording_base_path:
            log.warning("No recording base path available for settings report")
            return

        settings = self.window.settings.get_settings()
        path = f"{self.recording_base_path}_settings.csv"
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
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
                writer.writerow(['Pixel Format', acq['pixel_format']])
                writer.writerow(['Sensor Mode', acq['sensor_mode']])
                writer.writerow(['Binning H', settings['roi']['binning_h']])
                writer.writerow(['Binning V', settings['roi']['binning_v']])

                # Frame rate settings
                fr = settings['framerate']
                if fr['enabled']:
                    writer.writerow(['Frame Rate Limit', f"{fr['target_fps']} Hz"])
                else:
                    writer.writerow(['Frame Rate Limit', 'Disabled'])

                if fr['throughput_enabled']:
                    writer.writerow(['Throughput Limit', f"{fr['throughput_limit']} Mbps"])
                else:
                    writer.writerow(['Throughput Limit', 'Disabled'])

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
                'frame_times': getattr(self.thread, 'frame_times', [])
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
    app.setStyle('Fusion')

    pylon_app = PylonApp()
    pylon_app.run()

    # Cleanup on exit
    app.aboutToQuit.connect(lambda: pylon_app.disconnect_camera())

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
