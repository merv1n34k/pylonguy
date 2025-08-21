"""Main application - entry point and app logic"""
import sys
import time
import logging
import numpy as np
from pathlib import Path
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
            # Update GUI with current settings
            w, h, ox, oy = self.camera.get_roi()
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
        self.camera.set_framerate(acq['framerate_enable'], acq['framerate'])

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

            # Generate filename
            settings = self.window.settings.get_settings()
            base_path = settings['output']['path']

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

    def stop_recording(self):
        """Stop video recording"""
        if self.thread:
            frames = self.thread.stop_recording()
            self.window.preview.btn_record.setText("Record")

            # Always restore full preview after recording
            self.thread.set_preview_options(True, 1)

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

    def _on_recording_stopped(self):
        """Handle auto-stop of recording"""
        self.stop_recording()
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
