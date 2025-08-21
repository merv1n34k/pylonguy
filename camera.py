"""Camera module - handles all camera I/O operations"""
import numpy as np
from pypylon import pylon
from typing import Optional, Tuple
import logging

log = logging.getLogger("pylonguy")

class Camera:
    """Basler camera wrapper with optimized settings"""

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

            self.device = pylon.InstantCamera(tlf.CreateDevice(devices[0]))
            self.device.Open()

            # Optimize for speed
            self._optimize_settings()

            log.info(f"Camera opened: {self.device.GetDeviceInfo().GetModelName()}")
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
        if self.device and not self._is_grabbing:
            self.device.StartGrabbing(pylon.GrabStrategy_OneByOne)
            self._is_grabbing = True

    def stop_grabbing(self):
        """Stop frame acquisition"""
        if self.device and self._is_grabbing:
            self.device.StopGrabbing()
            self._is_grabbing = False

    def grab_frame(self) -> Optional[np.ndarray]:
        """Grab single frame"""
        if not self.device:
            return None

        try:
            if not self._is_grabbing:
                self.start_grabbing()

            result = self.device.RetrieveResult(100, pylon.TimeoutHandling_Return)
            if result and result.GrabSucceeded():
                frame = result.Array.copy()  # Always copy for safety
                result.Release()
                return frame
            if result:
                result.Release()
        except:
            pass
        return None

    def set_roi(self, width: int, height: int, offset_x: int = 0, offset_y: int = 0) -> bool:
        """Set region of interest"""
        if not self.device:
            return False

        try:
            was_grabbing = self._is_grabbing
            if was_grabbing:
                self.stop_grabbing()

            # Reset offsets first
            self.device.OffsetX.Value = 0
            self.device.OffsetY.Value = 0

            # Set new dimensions
            self.device.Width.Value = width
            self.device.Height.Value = height
            self.device.OffsetX.Value = offset_x
            self.device.OffsetY.Value = offset_y

            if was_grabbing:
                self.start_grabbing()

            log.info(f"ROI set: {width}x{height}+{offset_x}+{offset_y}")
            return True
        except Exception as e:
            log.error(f"Failed to set ROI: {e}")
            return False

    def get_roi(self) -> Tuple[int, int, int, int]:
        """Get current ROI (width, height, offset_x, offset_y)"""
        if not self.device:
            return 640, 480, 0, 0

        try:
            return (
                self.device.Width.Value,
                self.device.Height.Value,
                self.device.OffsetX.Value,
                self.device.OffsetY.Value
            )
        except:
            return 640, 480, 0, 0

    def set_exposure(self, microseconds: float) -> bool:
        """Set exposure time in microseconds"""
        if not self.device:
            return False

        try:
            # Disable auto exposure
            if hasattr(self.device, 'ExposureAuto'):
                self.device.ExposureAuto.Value = 'Off'

            # Set exposure
            if hasattr(self.device, 'ExposureTime'):
                self.device.ExposureTime.Value = microseconds
            elif hasattr(self.device, 'ExposureTimeAbs'):
                self.device.ExposureTimeAbs.Value = microseconds

            log.info(f"Exposure set: {microseconds:.1f} μs")
            return True
        except Exception as e:
            log.error(f"Failed to set exposure: {e}")
            return False

    def set_gain(self, gain: float) -> bool:
        """Set camera gain"""
        if not self.device:
            return False

        try:
            # Disable auto gain
            if hasattr(self.device, 'GainAuto'):
                self.device.GainAuto.Value = 'Off'

            # Set gain
            if hasattr(self.device, 'Gain'):
                self.device.Gain.Value = gain
            elif hasattr(self.device, 'GainRaw'):
                self.device.GainRaw.Value = int(gain)

            log.info(f"Gain set: {gain}")
            return True
        except Exception as e:
            log.error(f"Failed to set gain: {e}")
            return False

    def set_framerate(self, enable: bool, fps: float = 30.0) -> bool:
        """Set acquisition framerate limit"""
        if not self.device:
            return False

        try:
            if hasattr(self.device, 'AcquisitionFrameRateEnable'):
                self.device.AcquisitionFrameRateEnable.Value = enable

            if enable and hasattr(self.device, 'AcquisitionFrameRate'):
                self.device.AcquisitionFrameRate.Value = fps
                log.info(f"Framerate limit: {fps} Hz")
            elif not enable:
                log.info("Framerate limit disabled")

            return True
        except Exception as e:
            log.error(f"Failed to set framerate: {e}")
            return False

    def _optimize_settings(self):
        """Optimize camera for high-speed capture"""
        if not self.device:
            return

        try:
            # Maximize bandwidth for GigE
            if hasattr(self.device, 'DeviceLinkThroughputLimitMode'):
                self.device.DeviceLinkThroughputLimitMode.Value = 'Off'

            # Use jumbo frames if available
            if hasattr(self.device, 'GevSCPSPacketSize'):
                try:
                    self.device.GevSCPSPacketSize.Value = 9000
                except:
                    self.device.GevSCPSPacketSize.Value = 1500

            # Increase buffer count
            if hasattr(self.device, 'MaxNumBuffer'):
                self.device.MaxNumBuffer.Value = 50

            log.info("Camera optimized for high-speed capture")
        except Exception as e:
            log.warning(f"Could not fully optimize camera: {e}")
