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
log = logging.getLogger("pylon_gui")

class CameraThread(QThread):
    """Thread for continuous frame grabbing"""
    frame_signal = pyqtSignal(np.ndarray)

    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.running = False
        self.recording = False
        self.writer = None
        self.frame_count = 0
        self.record_start_time = 0

    def run(self):
        self.running = True
        while self.running:
            frame = self.camera.grab_frame()
            if frame is not None:
                # Emit frame for display
                self.frame_signal.emit(frame)

                # Write to video if recording
                if self.recording and self.writer:
                    if self.writer.write(frame):
                        self.frame_count += 1
            else:
                self.msleep(30)

    def stop(self):
        self.running = False
        if self.writer:
            self.writer.stop()
            self.writer = None
        self.wait()

    def start_recording(self, writer):
        import time
        self.writer = writer
        self.frame_count = 0
        self.record_start_time = time.time()
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
        self.config.video_fps = self.window.settings.video_fps.value()

        # Apply to camera
        self.camera.set_roi(
            self.config.width,
            self.config.height,
            self.config.offset_x,
            self.config.offset_y
        )
        self.camera.set_exposure(self.config.exposure)
        self.camera.set_gain(self.config.gain)

        log.info(f"Applied - ROI: {self.config.width}x{self.config.height}")

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
        self.thread.frame_signal.connect(self.display_frame)
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

            if self.thread.start_recording(writer):
                self.window.preview.btn_record.setText("Stop Recording")
                log.info(f"Recording: {path} ({w}x{h} @ {self.config.video_fps}fps)")
            else:
                log.error("Failed to start recording")

    def stop_recording(self):
        """Stop recording"""
        if self.thread:
            frames = self.thread.stop_recording()
            self.window.preview.btn_record.setText("Record")
            log.info(f"Recorded {frames} frames")

    def update_status(self):
        """Update status bar"""
        status_parts = []

        # Camera ROI
        if self.camera.device:
            w, h, _, _ = self.camera.get_roi()
            status_parts.append(f"ROI: {w}x{h}")
        else:
            status_parts.append("Not connected")

        # Live/Recording status
        if self.thread:
            if self.thread.recording:
                elapsed = time.time() - self.thread.record_start_time
                fps = self.thread.frame_count / max(0.1, elapsed)
                status_parts.append(f"REC: {self.thread.frame_count} frames @ {fps:.1f} fps")
            else:
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
