"""Thread module - optimized for high-speed acquisition"""
from PyQt5.QtCore import QThread, pyqtSignal
import numpy as np
import time
import logging

log = logging.getLogger("pylonguy")

class CameraThread(QThread):
    """Camera acquisition thread optimized for 4kHz operation"""

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
        self.frame_times = []  # Store frame timestamps for raw stats

        # Performance tracking
        self.dropped_frames = 0
        self.last_frame_time = 0

        # Limits
        self.max_frames = None
        self.max_time = None

        # Preview settings
        self.preview_enabled = True
        self.preview_nth = 1
        self.frame_counter = 0

        # High-speed mode flag
        self.high_speed_mode = False

    def run(self):
        """Optimized acquisition loop for high-speed operation"""
        self.running = True
        self.frame_counter = 0

        # Determine if we need high-speed mode based on ROI
        w, h, _, _ = self.camera.get_roi()
        expected_fps = self._estimate_fps(w, h)
        self.high_speed_mode = expected_fps > 1000  # Above 1kHz, use high-speed mode

        if self.high_speed_mode:
            log.info(f"High-speed mode activated (expected {expected_fps:.0f} Hz)")
            self._run_high_speed()
        else:
            log.info(f"Normal mode (expected {expected_fps:.0f} Hz)")
            self._run_normal()

    def _estimate_fps(self, width, height):
        """Estimate expected FPS based on ROI size"""
        # Rough estimation based on pixel count
        # Adjust these values based on your camera model
        pixels = width * height
        if pixels <= 20480:  # 320x64
            return 4000
        elif pixels <= 307200:  # 640x480
            return 200
        else:
            return 100

    def _run_high_speed(self):
        """High-speed acquisition loop with minimal overhead"""
        # Start camera grabbing in high-speed mode
        self.camera.start_grabbing(high_speed=True)

        # Pre-allocate variables to avoid allocation in loop
        frame = None
        current_time = 0
        frame_time = 0
        stats_counter = 0

        # Use faster timer for high-speed
        if hasattr(time, 'perf_counter_ns'):
            # nanosecond precision if available
            get_time = lambda: time.perf_counter_ns() / 1e9
        else:
            get_time = time.perf_counter

        # Record start time with high precision
        self.start_time = get_time()
        self.last_stats_time = self.start_time

        while self.running:
            # Use zero-copy grab for maximum speed
            frame = self.camera.grab_frame_zero_copy()

            if frame is not None:
                self.frame_counter += 1

                # Handle recording with minimal overhead
                if self.recording and self.writer:
                    # Get precise timestamp BEFORE write
                    frame_time = get_time() - self.start_time

                    # Write frame (writer should handle copy internally if needed)
                    if self.writer.write(frame):
                        self.frame_count += 1
                        # Only store timestamp, not the frame
                        self.frame_times.append(frame_time)

                        # Check limits only every 100 frames to reduce overhead
                        if self.frame_count % 100 == 0:
                            if self._check_limits():
                                self.recording_stopped.emit()
                                self.stop_recording()
                                break
                    else:
                        self.dropped_frames += 1

                # Handle preview with minimal impact
                if not self.recording and self.preview_enabled:
                    # Only emit for preview when not recording in high-speed mode
                    if self.frame_counter % self.preview_nth == 0:
                        # Must copy here since we're passing to GUI thread
                        self.frame_ready.emit(frame.copy())

                # Update stats only every 1000 frames in high-speed mode
                stats_counter += 1
                if stats_counter >= 1000:
                    stats_counter = 0
                    current_time = get_time()
                    self._update_stats_fast(current_time)

            # No sleep in high-speed mode - run as fast as possible

    def _run_normal(self):
        """Normal acquisition loop for lower frame rates"""
        # Start camera grabbing in normal mode
        self.camera.start_grabbing(high_speed=False)

        while self.running:
            frame = self.camera.grab_frame()

            if frame is not None:
                self.frame_counter += 1

                # Handle recording
                if self.recording and self.writer:
                    if self.writer.write(frame):
                        self.frame_count += 1
                        # Store frame timestamp relative to start
                        if self.start_time:
                            self.frame_times.append(time.time() - self.start_time)

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
                self.msleep(10)  # Short sleep if no frame

    def start_recording(self, writer, max_frames=None, max_time=None):
        """Start recording with given writer"""
        self.writer = writer
        self.max_frames = max_frames
        self.max_time = max_time
        self.frame_count = 0
        self.dropped_frames = 0

        # Use high-precision timer for recording
        if hasattr(time, 'perf_counter'):
            self.start_time = time.perf_counter()
        else:
            self.start_time = time.time()

        self.frame_times = []  # Clear frame times for new recording

        if self.writer.start():
            self.recording = True
            log.info("Recording started")

            # Log transport stats at start for debugging
            if self.high_speed_mode:
                stats = self.camera.get_transport_layer_stats()
                if stats:
                    log.info(f"Transport layer stats at start: {stats}")

            return True
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

        # Log final stats for high-speed mode
        if self.high_speed_mode:
            stats = self.camera.get_transport_layer_stats()
            if stats:
                log.info(f"Transport layer stats at stop: {stats}")
            if self.dropped_frames > 0:
                log.warning(f"Dropped frames during recording: {self.dropped_frames}")

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

        # In high-speed mode, disable preview during recording for performance
        if self.high_speed_mode and self.recording:
            log.info("Preview disabled during high-speed recording for performance")
            self.preview_enabled = False
        else:
            log.info(f"Preview: {'on' if enabled else 'off'}, every {self.preview_nth} frame(s)")

    def _check_limits(self) -> bool:
        """Check if recording limits reached"""
        if self.max_frames and self.frame_count >= self.max_frames:
            log.info(f"Frame limit reached: {self.max_frames}")
            return True

        if self.max_time:
            if hasattr(time, 'perf_counter'):
                elapsed = time.perf_counter() - self.start_time
            else:
                elapsed = time.time() - self.start_time

            if elapsed >= self.max_time:
                log.info(f"Time limit reached: {self.max_time}s")
                return True

        return False

    def _update_stats(self):
        """Update statistics periodically (normal mode)"""
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

    def _update_stats_fast(self, current_time):
        """Update statistics for high-speed mode (less frequent)"""
        elapsed = current_time - self.start_time

        stats = {
            'recording': self.recording,
            'frames': self.frame_count if self.recording else 0,
            'fps': self.frame_count / elapsed if elapsed > 0 else 0,
            'elapsed': elapsed,
            'dropped': self.dropped_frames
        }

        self.stats_update.emit(stats)
        self.last_stats_time = current_time
