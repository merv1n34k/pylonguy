"""Camera module - handles all camera I/O operations"""
import numpy as np
from pypylon import pylon
from typing import Optional, Tuple
import logging
import time

log = logging.getLogger("pylonguy")

class Camera:
    """Basler camera wrapper with proper settings handling"""

    def __init__(self):
        self.device = None
        self._is_grabbing = False

    def open(self) -> bool:
        """Open first available camera"""
        try:
            tlf = pylon.TlFactory.GetInstance()
            devices = tlf.EnumerateDevices()
            if not devices:
                log.error("No cameras found")
                return False

            log.info(f"Found {len(devices)} camera(s)")

            self.device = pylon.InstantCamera(tlf.CreateDevice(devices[0]))
            self.device.Open()

            # Get device info
            device_info = self.device.GetDeviceInfo()
            model = device_info.GetModelName()
            serial = device_info.GetSerialNumber()

            log.info(f"Camera opened: {model} (S/N: {serial})")
            return True
        except Exception as e:
            log.error(f"Failed to open camera: {e}")
            return False

    def close(self):
        """Close camera connection"""
        if self.device:
            try:
                self.stop_grabbing()
                if self.device.IsOpen():
                    self.device.Close()
                log.info("Camera closed")
            except:
                pass
            self.device = None

    def start_grabbing(self):
        """Start continuous frame acquisition"""
        if not self.device or self._is_grabbing:
            return

        try:
            # Start grabbing with latest image strategy
            self.device.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            self._is_grabbing = True
        except Exception as e:
            log.error(f"Failed to start grabbing: {e}")
            self._is_grabbing = False

    def stop_grabbing(self):
        """Stop frame acquisition"""
        if not self.device or not self._is_grabbing:
            return

        try:
            if self.device.IsGrabbing():
                self.device.StopGrabbing()
            self._is_grabbing = False
        except Exception as e:
            log.error(f"Failed to stop grabbing: {e}")
            self._is_grabbing = False

    def grab_frame(self) -> Optional[np.ndarray]:
        """Grab single frame"""
        if not self.device:
            return None

        try:
            # Ensure we're grabbing
            if not self._is_grabbing:
                self.start_grabbing()

            # Check camera is actually grabbing
            if not self.device.IsGrabbing():
                self._is_grabbing = False
                self.start_grabbing()

                if not self.device.IsGrabbing():
                    return None

            # Retrieve frame
            result = self.device.RetrieveResult(200, pylon.TimeoutHandling_Return)
            if result and result.GrabSucceeded():
                frame = result.Array.copy()
                result.Release()
                return frame
            elif result:
                result.Release()
            return None
        except:
            return None

    def configure_camera(self, config_func):
        """Execute configuration function with proper locking"""
        if not self.device:
            return False

        was_grabbing = self._is_grabbing

        try:
            # Stop grabbing if active
            if self._is_grabbing or self.device.IsGrabbing():
                self.stop_grabbing()

            # Execute the Basler lock sequence
            # 1. Stop acquisition
            if hasattr(self.device, 'AcquisitionStop'):
                try:
                    self.device.AcquisitionStop.Execute()
                except:
                    pass

            # 2. Unlock parameters
            if hasattr(self.device, 'TLParamsLocked'):
                try:
                    self.device.TLParamsLocked.SetValue(False)
                except:
                    pass

            # 3. Execute configuration function
            result = config_func()

            # 4. Lock parameters
            if hasattr(self.device, 'TLParamsLocked'):
                try:
                    self.device.TLParamsLocked.SetValue(True)
                except:
                    pass

            # 5. Start acquisition
            if hasattr(self.device, 'AcquisitionStart'):
                try:
                    self.device.AcquisitionStart.Execute()
                except:
                    pass

            # Restart grabbing if it was active
            if was_grabbing:
                self.start_grabbing()

            return result

        except Exception as e:
            log.error(f"Configuration failed: {e}")
            # Try to restore grabbing state
            if was_grabbing:
                try:
                    self.start_grabbing()
                except:
                    pass
            return False

    def set_roi(self, width: int, height: int, offset_x: int = 0, offset_y: int = 0) -> bool:
        """Set region of interest"""
        if not self.device:
            return False

        def apply_roi():
            try:
                # Get increment values
                width_inc = self.device.Width.GetInc() if hasattr(self.device.Width, 'GetInc') else 1
                height_inc = self.device.Height.GetInc() if hasattr(self.device.Height, 'GetInc') else 1
                offset_inc = self.device.OffsetX.GetInc() if hasattr(self.device.OffsetX, 'GetInc') else 1

                # Round to valid increments
                w = int(width / width_inc) * width_inc
                h = int(height / height_inc) * height_inc
                ox = int(offset_x / offset_inc) * offset_inc
                oy = int(offset_y / offset_inc) * offset_inc

                # Get limits
                width_max = self.device.Width.GetMax()
                height_max = self.device.Height.GetMax()
                width_min = self.device.Width.GetMin()
                height_min = self.device.Height.GetMin()

                # Clamp to valid range
                w = max(width_min, min(w, width_max))
                h = max(height_min, min(h, height_max))

                # Apply ROI settings in correct order
                self.device.OffsetX.SetValue(0)
                self.device.OffsetY.SetValue(0)
                self.device.Width.SetValue(w)
                self.device.Height.SetValue(h)

                # Set offsets
                max_offset_x = width_max - w
                max_offset_y = height_max - h
                ox = min(ox, max_offset_x)
                oy = min(oy, max_offset_y)
                self.device.OffsetX.SetValue(ox)
                self.device.OffsetY.SetValue(oy)

                log.info(f"ROI set: {w}x{h}+{ox}+{oy}")
                return True
            except Exception as e:
                log.error(f"Failed to set ROI: {e}")
                return False

        return self.configure_camera(apply_roi)

    def get_roi(self) -> Tuple[int, int, int, int]:
        """Get current ROI (width, height, offset_x, offset_y)"""
        if not self.device:
            return 640, 480, 0, 0

        try:
            return (
                self.device.Width.GetValue(),
                self.device.Height.GetValue(),
                self.device.OffsetX.GetValue(),
                self.device.OffsetY.GetValue()
            )
        except:
            return 640, 480, 0, 0

    def set_exposure(self, microseconds: float) -> bool:
        """Set exposure time in microseconds"""
        if not self.device:
            return False

        def apply_exposure():
            try:
                # Disable auto exposure
                if hasattr(self.device, 'ExposureAuto'):
                    self.device.ExposureAuto.SetValue('Off')

                # Try modern property name first
                try:
                    min_exp = self.device.ExposureTime.GetMin()
                    max_exp = self.device.ExposureTime.GetMax()
                    microseconds_clamped = max(min_exp, min(microseconds, max_exp))
                    self.device.ExposureTime.SetValue(microseconds_clamped)
                    log.info(f"Exposure set: {microseconds_clamped:.1f} μs")
                    return True
                except:
                    # Fall back to older property name
                    min_exp = self.device.ExposureTimeAbs.GetMin()
                    max_exp = self.device.ExposureTimeAbs.GetMax()
                    microseconds_clamped = max(min_exp, min(microseconds, max_exp))
                    self.device.ExposureTimeAbs.SetValue(microseconds_clamped)
                    log.info(f"Exposure set: {microseconds_clamped:.1f} μs")
                    return True
            except Exception as e:
                log.error(f"Failed to set exposure: {e}")
                return False

        return self.configure_camera(apply_exposure)

    def set_gain(self, gain: float) -> bool:
        """Set camera gain"""
        if not self.device:
            return False

        def apply_gain():
            try:
                # Disable auto gain
                if hasattr(self.device, 'GainAuto'):
                    self.device.GainAuto.SetValue('Off')

                # Try modern property name first
                try:
                    min_gain = self.device.Gain.GetMin()
                    max_gain = self.device.Gain.GetMax()
                    gain_clamped = max(min_gain, min(gain, max_gain))
                    self.device.Gain.SetValue(gain_clamped)
                    log.info(f"Gain set: {gain_clamped}")
                    return True
                except:
                    # Fall back to raw gain
                    min_gain = self.device.GainRaw.GetMin()
                    max_gain = self.device.GainRaw.GetMax()
                    gain_clamped = int(max(min_gain, min(gain, max_gain)))
                    self.device.GainRaw.SetValue(gain_clamped)
                    log.info(f"Gain set: {gain_clamped}")
                    return True
            except Exception as e:
                log.error(f"Failed to set gain: {e}")
                return False

        return self.configure_camera(apply_gain)

    def set_sensor_mode(self, mode: str) -> bool:
        """Set sensor readout mode if supported"""
        if not self.device:
            return False

        def apply_sensor_mode():
            try:
                if hasattr(self.device, 'SensorReadoutMode'):
                    self.device.SensorReadoutMode.SetValue(mode)
                    log.info(f"Sensor mode set: {mode}")
                return True
            except:
                log.debug("Sensor mode not supported")
                return True  # Not an error

        return self.configure_camera(apply_sensor_mode)

    def set_framerate(self, enable: bool, fps: float = 30.0) -> bool:
        """Set acquisition framerate limit"""
        if not self.device:
            return False

        def apply_framerate():
            try:
                if hasattr(self.device, 'AcquisitionFrameRateEnable'):
                    self.device.AcquisitionFrameRateEnable.SetValue(enable)
                    if enable and hasattr(self.device, 'AcquisitionFrameRate'):
                        min_fps = self.device.AcquisitionFrameRate.GetMin()
                        max_fps = self.device.AcquisitionFrameRate.GetMax()
                        fps_clamped = max(min_fps, min(fps, max_fps))
                        self.device.AcquisitionFrameRate.SetValue(fps_clamped)
                        log.info(f"Framerate limit: {fps_clamped} Hz")
                    elif not enable:
                        log.info("Framerate limit disabled")
                return True
            except:
                log.debug("Framerate control not supported")
                return True

        return self.configure_camera(apply_framerate)
