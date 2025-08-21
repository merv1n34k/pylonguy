"""Thread module - handles camera acquisition in separate thread"""
from PyQt5.QtCore import QThread, pyqtSignal
import numpy as np
import time
import logging

log = logging.getLogger("pylonguy")

class CameraThread(QThread):
    """Camera acquisition thread with recording support"""

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

        # Preview settings
        self.preview_enabled = True  # Default to enabled
        self.preview_nth = 1  # Show every frame by default
        self.frame_counter = 0

    def run(self):
        """Main acquisition loop"""
        self.running = True
        self.frame_counter = 0

        while self.running:
            frame = self.camera.grab_frame()

            if frame is not None:
                self.frame_counter += 1

                # Handle recording
                if self.recording and self.writer:
                    if self.writer.write(frame):
                        self.frame_count += 1

                        # Check limits
                        if self._check_limits():
                            self.recording_stopped.emit()
                            self.stop_recording()
                            break

                # Handle preview
                should_emit = False
                if not self.recording:
                    # Always show preview when not recording
                    should_emit = True
                elif self.preview_enabled:
                    # Show preview during recording based on nth frame setting
                    if self.frame_counter % self.preview_nth == 0:
                        should_emit = True

                if should_emit:
                    self.frame_ready.emit(frame)

                # Update stats periodically
                self._update_stats()

            else:
                self.msleep(1)  # Short sleep if no frame

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
        return False

    def stop_recording(self):
        """Stop recording and return frame count"""
        frames = self.frame_count
        self.recording = False

        if self.writer:
            if hasattr(self.writer, 'stop'):
                result = self.writer.stop()
                if isinstance(result, str) and result:  # FrameDumper returns path
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

    def set_preview_options(self, enabled: bool, nth: int):
        """Configure preview behavior"""
        self.preview_enabled = enabled
        self.preview_nth = max(1, nth)
        log.info(f"Preview: {'on' if enabled else 'off'}, every {self.preview_nth} frame(s)")

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

    def _update_stats(self):
        """Update statistics periodically"""
        current_time = time.time()
        if current_time - self.last_stats_time < 0.1:  # Update every 100ms
            return

        self.last_stats_time = current_time

        stats = {
            'recording': self.recording,
            'frames': self.frame_count if self.recording else 0,
            'fps': 0,
            'elapsed': 0
        }

        if self.recording and self.start_time:
            elapsed = current_time - self.start_time
            stats['elapsed'] = elapsed
            if elapsed > 0:
                stats['fps'] = self.frame_count / elapsed

        self.stats_update.emit(stats)
