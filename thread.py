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

        # Preview settings
        self.preview_enabled = True
        self.preview_nth = 1
        self.frame_counter = 0

    def run(self):
        """Simple acquisition loop"""
        self.running = True
        self.frame_counter = 0
        self.last_stats_time = time.time()

        log.info("Acquisition thread started")

        # Start camera grabbing
        self.camera.start_grabbing()

        while self.running:
            # Grab frame - ONE method
            frame = self.camera.grab_frame()

            if frame is not None:
                self.frame_counter += 1

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
                if self._should_show_preview():
                    # Must copy for GUI thread safety
                    self.frame_ready.emit(frame.copy())

                # Update stats periodically (every 0.5 seconds)
                if self._should_update_stats():
                    self._update_stats()
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
            if hasattr(self.writer, 'stop'):
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

    def set_preview_options(self, enabled: bool, nth: int):
        """Configure preview behavior"""
        self.preview_enabled = enabled
        self.preview_nth = max(1, nth)
        log.info(f"Preview: {'on' if enabled else 'off'}, every {self.preview_nth} frame(s)")

    def _should_show_preview(self) -> bool:
        """Check if current frame should be shown in preview"""
        if not self.preview_enabled:
            return False

        # Show every Nth frame
        return self.frame_counter % self.preview_nth == 0

    def _should_update_stats(self) -> bool:
        """Check if stats should be updated"""
        current_time = time.time()
        if current_time - self.last_stats_time >= 0.5:  # Update every 500ms
            self.last_stats_time = current_time
            return True
        return False

    def _update_stats(self):
        """Update statistics using camera's ResultingFrameRate"""
        stats = {
            'recording': self.recording,
            'frames': self.frame_count if self.recording else 0,
            'fps': self.camera.get_resulting_framerate(),  # Use camera's actual FPS
            'elapsed': 0
        }

        if self.recording and self.start_time:
            stats['elapsed'] = time.time() - self.start_time

        self.stats_update.emit(stats)

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
