"""Thread module - camera acquisition thread with waterfall support"""

from PyQt5.QtCore import QThread, pyqtSignal
from threading import Event
import numpy as np
import time
import logging

log = logging.getLogger("pylonguy")


class CameraThread(QThread):
    """Camera acquisition thread with waterfall support"""

    # Signals
    frame_ready = pyqtSignal(np.ndarray)
    stats_update = pyqtSignal(dict)
    recording_stopped = pyqtSignal()

    def __init__(self, camera, waterfall_mode: bool = False):
        super().__init__()
        self.camera = camera
        self.waterfall_mode = waterfall_mode
        self._stop_event = Event()
        self._recording_event = Event()
        self._frame_pending = Event()
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
        self._stop_event.clear()
        self.last_stats_time = time.time()

        log.debug(
            f"Thread - Acquisition thread started (waterfall_mode={self.waterfall_mode})"
        )

        # Start with LatestImageOnly for lag-free preview
        self.camera.start_grabbing(latest_only=True)

        while not self._stop_event.is_set():
            frame = self.camera.grab_frame()

            if frame is not None:
                # Handle recording
                if self._recording_event.is_set() and self.writer:
                    if self.writer.write(frame):
                        self.frame_count += 1

                        # Check limits periodically (every 100 frames/lines)
                        if self.frame_count % 100 == 0:
                            if self._check_limits():
                                self.recording_stopped.emit()
                                self.stop_recording()
                                break

                if self.preview_enabled and not self._frame_pending.is_set():
                    self._frame_pending.set()
                    self.frame_ready.emit(frame)

                # Update stats periodically
                current_time = time.time()
                if current_time - self.last_stats_time >= 0.2:
                    self.last_stats_time = current_time
                    recording = self._recording_event.is_set()
                    stats = {
                        "recording": recording,
                        "frames": self.frame_count if recording else 0,
                        "elapsed": current_time - self.start_time
                        if recording
                        else 0,
                    }
                    self.stats_update.emit(stats)
            else:
                # Small sleep if no frame available
                self.msleep(1)

        self.camera.stop_grabbing()
        log.debug("Thread - Acquisition thread stopped")

    def start_recording(self, writer, max_frames=None, max_time=None):
        """Start recording with given writer"""
        self.writer = writer
        self.max_frames = max_frames
        self.max_time = max_time
        self.frame_count = 0
        self.start_time = time.time()

        if self.writer.start():
            # Switch to OneByOne strategy to preserve all frames
            self.camera.stop_grabbing()
            self.camera.start_grabbing(latest_only=False)

            self._recording_event.set()
            log.debug(
                f"Thread - Recording started ({'waterfall' if self.waterfall_mode else 'frames'})"
            )
            return True

        log.error("Failed to start writer")
        return False

    def stop_recording(self):
        """Stop recording and return frame/line count"""
        frames = self.frame_count
        self._recording_event.clear()

        if self.writer:
            result = self.writer.stop()
            if isinstance(result, str) and result:
                if self.waterfall_mode:
                    log.info(f"Waterfall saved: {result}")
                else:
                    log.info(f"Video saved: {result}")
            self.writer = None

        # Switch back to LatestImageOnly for lag-free preview
        if not self._stop_event.is_set():
            self.camera.stop_grabbing()
            self.camera.start_grabbing(latest_only=True)

        log.debug(
            f"Thread - Recording stopped: {frames} {'lines' if self.waterfall_mode else 'frames'}"
        )
        return frames

    def stop(self):
        """Stop acquisition thread"""
        self._stop_event.set()
        if self._recording_event.is_set():
            self.stop_recording()
        self.wait()

    @property
    def recording(self) -> bool:
        """Thread-safe recording state check"""
        return self._recording_event.is_set()

    def set_preview_enabled(self, enabled: bool):
        """Enable or disable preview"""
        self.preview_enabled = enabled
        log.debug(f"Preview: {'enabled' if enabled else 'disabled'}")

    def frame_processed(self):
        """Called by main thread after frame is displayed"""
        self._frame_pending.clear()

    def _check_limits(self) -> bool:
        """Check if recording limits reached"""
        if self.max_frames and self.frame_count >= self.max_frames:
            log.debug(
                f"Thread - {'Line' if self.waterfall_mode else 'Frame'} limit reached: {self.max_frames}"
            )
            return True

        if self.max_time:
            elapsed = time.time() - self.start_time
            if elapsed >= self.max_time:
                log.debug(f"Thread - Time limit reached: {self.max_time}s")
                return True

        return False
