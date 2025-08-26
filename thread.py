"""Thread module - simplified acquisition thread"""
from PyQt5.QtCore import QThread, pyqtSignal
import numpy as np
import time
import logging

log = logging.getLogger("pylonguy")

class CameraThread(QThread):
    """Simple camera acquisition thread"""

    # Signals
    frame_ready = pyqtSignal(np.ndarray)  # For preview
    stats_update = pyqtSignal(dict)  # For status display
    recording_stopped = pyqtSignal()  # Auto-stop signal

    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.running = False
        self.recording = False
        self.writer = None

        # Stats
        self.frame_count = 0
        self.start_time = 0
        self.last_stats_time = 0

        # Limits
        self.max_frames = None
        self.max_time = None

        # Preview setting
        self.preview_enabled = True

    def run(self):
        """Simple acquisition loop"""
        self.running = True
        self.last_stats_time = time.time()

        log.info("Acquisition thread started")

        # Start camera grabbing
        self.camera.start_grabbing()

        while self.running:
            # Grab frame - ONE method
            frame = self.camera.grab_frame()

            if frame is not None:
                # Handle recording
                if self.recording and self.writer:
                    if self.writer.write(frame):
                        self.frame_count += 1

                        # Check limits periodically (every 100 frames)
                        if self.frame_count % 100 == 0:
                            if self._check_limits():
                                self.recording_stopped.emit()
                                self.stop_recording()
                                break

                # Handle preview
                if self.preview_enabled:
                    # Must copy for GUI thread safety
                    self.frame_ready.emit(frame.copy())

                # Update stats periodically (every 0.5 seconds)
                current_time = time.time()
                if current_time - self.last_stats_time >= 0.5:
                    self.last_stats_time = current_time
                    stats = {
                        'recording': self.recording,
                        'frames': self.frame_count if self.recording else 0,
                        'elapsed': current_time - self.start_time if self.recording else 0
                    }
                    self.stats_update.emit(stats)
            else:
                # Small sleep if no frame available
                self.msleep(1)

        # Stop grabbing when thread ends
        self.camera.stop_grabbing()
        log.info("Acquisition thread stopped")

    def start_recording(self, writer, max_frames=None, max_time=None):
        """Start recording with given writer"""
        self.writer = writer
        self.max_frames = max_frames
        self.max_time = max_time
        self.frame_count = 0
        self.start_time = time.time()

        if self.writer.start():
            self.recording = True
            log.info("Recording started")
            return True

        log.error("Failed to start writer")
        return False

    def stop_recording(self):
        """Stop recording and return frame count"""
        frames = self.frame_count
        self.recording = False

        if self.writer:
            result = self.writer.stop()
            if isinstance(result, str) and result:
                log.info(f"Video saved: {result}")
            self.writer = None

        log.info(f"Recording stopped: {frames} frames")
        return frames

    def stop(self):
        """Stop acquisition thread"""
        self.running = False
        if self.recording:
            self.stop_recording()
        self.wait()

    def set_preview_enabled(self, enabled: bool):
        """Enable or disable preview"""
        self.preview_enabled = enabled
        log.info(f"Preview: {'enabled' if enabled else 'disabled'}")

    def _check_limits(self) -> bool:
        """Check if recording limits reached"""
        if self.max_frames and self.frame_count >= self.max_frames:
            log.info(f"Frame limit reached: {self.max_frames}")
            return True

        if self.max_time:
            elapsed = time.time() - self.start_time
            if elapsed >= self.max_time:
                log.info(f"Time limit reached: {self.max_time}s")
                return True

        return False
