"""Main application - all logic here"""
import sys
import time
import logging
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QPixmap
import numpy as np

from camera import Camera
from gui import MainWindow
from video_writer import VideoWriter
from config import Config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger("pylonguy")

class CameraThread(QThread):
    """Thread for continuous frame grabbing - optimized for high speed"""
    frame_signal = pyqtSignal(np.ndarray)
    stopped_signal = pyqtSignal()
    stats_signal = pyqtSignal(int, float)  # frames, fps

    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.running = False
        self.recording = False
        self.writer = None
        self.frame_count = 0
        self.record_start_time = 0
        self.max_frames = None
        self.max_time = None
        self.display_interval = 30  # Show every Nth frame when recording
        self.last_stats_time = 0
        self.stats_update_interval = 0.1  # Update stats every 100ms

    def run(self):
        self.running = True
        frame_counter = 0

        while self.running:
            frame = self.camera.grab_frame()
            if frame is not None:
                frame_counter += 1

                if self.recording and self.writer:
                    # ALWAYS write frame when recording (no skipping for recording)
                    if self.writer.write(frame):
                        self.frame_count += 1

                        # Emit stats periodically (not every frame)
                        current_time = time.time()
                        if current_time - self.last_stats_time > self.stats_update_interval:
                            elapsed = current_time - self.record_start_time
                            fps = self.frame_count / max(0.001, elapsed)
                            self.stats_signal.emit(self.frame_count, fps)
                            self.last_stats_time = current_time

                        # Check limits
                        if self.max_frames and self.frame_count >= self.max_frames:
                            log.info(f"Reached frame limit: {self.max_frames}")
                            self.stopped_signal.emit()
                            self.recording = False
                            break

                        if self.max_time:
                            elapsed = current_time - self.record_start_time
                            if elapsed >= self.max_time:
                                log.info(f"Reached time limit: {self.max_time}s")
                                self.stopped_signal.emit()
                                self.recording = False
                                break

                    # Only emit frame for display occasionally when recording at high speed
                    if frame_counter % self.display_interval == 0:
                        self.frame_signal.emit(frame)
                else:
                    # When not recording, show every frame for smooth preview
                    self.frame_signal.emit(frame)
            else:
                self.msleep(10)  # Shorter sleep for higher responsiveness

    def stop(self):
        self.running = False
        if self.writer:
            self.writer.stop()
            self.writer = None
        self.wait()

    def start_recording(self, writer, max_frames=None, max_time=None):
        import time
        self.writer = writer
        self.frame_count = 0
        self.max_frames = max_frames
        self.max_time = max_time
        self.record_start_time = time.time()
        self.last_stats_time = time.time()

        # Adjust display interval based on expected frame rate
        # For high-speed recording, show fewer frames
        w, h, _, _ = self.camera.get_roi()
        if w <= 256 and h <= 256:  # Small ROI = likely high speed
            self.display_interval = 100  # Show every 100th frame
        elif w <= 640 and h <= 480:
            self.display_interval = 50
        else:
            self.display_interval = 30

        if self.writer.start():
            self.recording = True
            return True
        return False

    def stop_recording(self):
        self.recording = False
        frames = self.frame_count
        if self.writer:
            self.writer.stop()
            self.writer = None
        self.display_interval = 1  # Reset to show every frame
        return frames

class App:
    def __init__(self):
        self.camera = Camera()
        self.config = Config()
        self.thread = None
        self.last_frame = None

        # Create GUI
        self.window = MainWindow()

        # Connect signals
        self.window.preview.btn_live.clicked.connect(self.toggle_live)
        self.window.preview.btn_capture.clicked.connect(self.capture)
        self.window.preview.btn_record.clicked.connect(self.toggle_record)

        self.window.settings.btn_connect.clicked.connect(self.connect_camera)
        self.window.settings.btn_disconnect.clicked.connect(self.disconnect_camera)
        self.window.settings.btn_apply.clicked.connect(self.apply_settings)

        # Status timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(100)  # Update 10 times per second

        # Cleanup on close
        self.window.closeEvent = self.cleanup_on_close

        # Logging to GUI
        class GuiLogHandler(logging.Handler):
            def __init__(self, widget):
                super().__init__()
                self.widget = widget
            def emit(self, record):
                self.widget.add(self.format(record))

        handler = GuiLogHandler(self.window.log)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', '%H:%M:%S'))
        log.addHandler(handler)

        log.info("Application started")

    def connect_camera(self):
        """Connect to camera"""
        if self.camera.open():
            # Get current ROI
            w, h, ox, oy = self.camera.get_roi()
            self.window.settings.width.setValue(w)
            self.window.settings.height.setValue(h)
            self.window.settings.offset_x.setValue(ox)
            self.window.settings.offset_y.setValue(oy)

            log.info(f"Connected - ROI: {w}x{h} @ ({ox},{oy})")
        else:
            log.error("Failed to connect camera")

    def disconnect_camera(self):
        """Disconnect camera"""
        self.stop_live()
        self.camera.close()
        log.info("Disconnected")

    def apply_settings(self):
        """Apply settings to camera"""
        # Update config
        self.config.width = self.window.settings.width.value()
        self.config.height = self.window.settings.height.value()
        self.config.offset_x = self.window.settings.offset_x.value()
        self.config.offset_y = self.window.settings.offset_y.value()
        self.config.exposure = self.window.settings.exposure.value()
        self.config.gain = self.window.settings.gain.value()
        self.config.sensor_mode = self.window.settings.sensor_mode.currentText()
        self.config.framerate_enable = self.window.settings.framerate_enable.isChecked()
        self.config.framerate = self.window.settings.framerate.value()
        self.config.video_fps = self.window.settings.video_fps.value()

        # Recording limits
        if self.window.settings.limit_frames_enable.isChecked():
            self.config.limit_frames = self.window.settings.limit_frames.value()
        else:
            self.config.limit_frames = None

        if self.window.settings.limit_time_enable.isChecked():
            self.config.limit_time = self.window.settings.limit_time.value()
        else:
            self.config.limit_time = None

        # Apply to camera
        self.camera.set_roi(
            self.config.width,
            self.config.height,
            self.config.offset_x,
            self.config.offset_y
        )
        self.camera.set_exposure(self.config.exposure)
        self.camera.set_gain(self.config.gain)
        self.camera.set_sensor_mode(self.config.sensor_mode)
        self.camera.set_framerate(self.config.framerate_enable, self.config.framerate)

        log.info(f"Applied - ROI: {self.config.width}x{self.config.height}")

    def toggle_live(self):
        """Toggle live preview"""
        if self.thread:
            self.stop_live()
        else:
            self.start_live()

    def update_recording_stats(self, frames, fps):
        """Update recording statistics without updating display"""
        # This replaces the constant status updates during recording
        status_parts = []

        # Camera ROI
        if self.camera.device:
            w, h, _, _ = self.camera.get_roi()
            status_parts.append(f"ROI: {w}x{h}")

        # Recording stats
        status_parts.append(f"REC: {frames} frames @ {fps:.1f} fps")

        self.window.preview.status.setText(" | ".join(status_parts))

    def start_live(self):
        """Start live preview"""
        if not self.camera.device:
            log.error("Camera not connected")
            return

        self.thread = CameraThread(self.camera)
        self.thread.frame_signal.connect(self.display_frame)
        self.thread.stopped_signal.connect(self.on_recording_stopped)
        self.thread.stats_signal.connect(self.update_recording_stats)  # Add this line
        self.thread.start()

        self.window.preview.btn_live.setText("Stop Live")
        log.info("Live started")

    def stop_live(self):
        """Stop live preview"""
        if self.thread:
            # Stop recording first if active
            if self.thread.recording:
                self.stop_recording()

            self.thread.stop()
            self.thread = None

        self.window.preview.btn_live.setText("Start Live")
        log.info("Live stopped")

    def display_frame(self, frame):
        """Display frame in preview"""
        self.last_frame = frame
        self.window.preview.show_frame(frame)

    def capture(self):
        """Capture current frame"""
        frame = self.last_frame
        if frame is None and self.camera.device:
            frame = self.camera.grab_frame()

        if frame is not None:
            # Save as PNG
            h, w = frame.shape[:2]

            # Convert to 8-bit if needed
            if frame.dtype == np.uint16:
                frame = (frame >> 8).astype(np.uint8)

            # Create QImage and save
            if len(frame.shape) == 2:
                img = QImage(frame.data, w, h, w, QImage.Format_Grayscale8)
            else:
                img = QImage(frame.data, w, h, w * 3, QImage.Format_RGB888)

            path = self.config.get_image_path()
            if img.save(path):
                log.info(f"Captured: {path}")
            else:
                log.error("Failed to save image")
        else:
            log.error("No frame available")

    def toggle_record(self):
        """Toggle recording"""
        if self.thread and self.thread.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        """Start recording"""
        if not self.thread:
            self.start_live()

        if self.thread:
            # Get current ROI
            w, h, _, _ = self.camera.get_roi()

            # Create writer
            path = self.config.get_video_path()
            writer = VideoWriter(path, w, h, self.config.video_fps)

            # Start with limits if set
            if self.thread.start_recording(writer, self.config.limit_frames, self.config.limit_time):
                self.window.preview.btn_record.setText("Stop Recording")
                log.info(f"Recording: {path} ({w}x{h} @ {self.config.video_fps}fps)")
                if self.config.limit_frames:
                    log.info(f"Frame limit: {self.config.limit_frames}")
                if self.config.limit_time:
                    log.info(f"Time limit: {self.config.limit_time}s")
            else:
                log.error("Failed to start recording")

    def stop_recording(self):
        """Stop recording"""
        if self.thread:
            frames = self.thread.stop_recording()
            self.window.preview.btn_record.setText("Record")
            log.info(f"Recorded {frames} frames")

    def on_recording_stopped(self):
        """Handler for when recording stops automatically due to limits"""
        # Update button text
        self.window.preview.btn_record.setText("Record")

        # Log that recording stopped
        if self.thread and hasattr(self.thread, 'frame_count'):
            frames = self.thread.frame_count
            log.info(f"Recording auto-stopped: {frames} frames recorded")
        else:
            log.info("Recording auto-stopped")

    def update_status(self):
        """Update status bar"""
        # Skip during high-speed recording (stats are updated separately)
        if self.thread and self.thread.recording:
            return  # Stats are updated by stats_signal

        status_parts = []

        # Camera ROI
        if self.camera.device:
            w, h, _, _ = self.camera.get_roi()
            status_parts.append(f"ROI: {w}x{h}")
        else:
            status_parts.append("Not connected")

        # Live status
        if self.thread and not self.thread.recording:
            status_parts.append("Live")

        # Selection info
        if self.window.preview.selection:
            r = self.window.preview.selection
            status_parts.append(f"Selection: {r.width()}x{r.height()}")

        self.window.preview.status.setText(" | ".join(status_parts))

    def cleanup_on_close(self, event):
        """Clean up when closing"""
        self.stop_live()
        self.disconnect_camera()
        event.accept()

    def run(self):
        """Run application"""
        self.window.show()

def main():
    app = QApplication(sys.argv)
    pylon_app = App()
    pylon_app.run()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
