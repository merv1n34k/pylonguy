import numpy as np
from pypylon import pylon
from typing import Optional, Tuple, List
import logging

log = logging.getLogger("pylon_gui")

class Camera:
    def __init__(self):
        self.device = None

    def connect(self) -> bool:
        """Connect to first available camera"""
        try:
            tlf = pylon.TlFactory.GetInstance()
            devices = tlf.EnumerateDevices()
            if not devices:
                log.warning("No camera found")
                return False

            self.device = pylon.InstantCamera(tlf.CreateDevice(devices[0]))
            self.device.Open()
            log.info(f"Connected to {self.device.GetDeviceInfo().GetModelName()}")
            return True
        except Exception as e:
            log.error(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect camera"""
        if self.device:
            try:
                if self.device.IsGrabbing():
                    self.device.StopGrabbing()
                if self.device.IsOpen():
                    self.device.Close()
                log.info("Camera disconnected")
            except Exception as e:
                log.error(f"Disconnect error: {e}")
            finally:
                self.device = None

    def is_connected(self) -> bool:
        return self.device and self.device.IsOpen()

    def start_grabbing(self):
        if self.is_connected() and not self.device.IsGrabbing():
            self.device.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    def stop_grabbing(self):
        if self.device and self.device.IsGrabbing():
            self.device.StopGrabbing()

    def grab_frame(self, timeout_ms=1000) -> Optional[np.ndarray]:
        """Grab single raw frame from camera"""
        if not self.is_connected():
            return None

        try:
            self.start_grabbing()
            result = self.device.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)
            if result.GrabSucceeded():
                # Return raw array - no conversion
                arr = result.Array.copy()
                result.Release()
                return arr
            result.Release()
        except Exception as e:
            log.error(f"Grab failed: {e}")
        return None

    def get_pixel_format(self) -> str:
        """Get current pixel format"""
        if not self.is_connected():
            return "Unknown"
        try:
            return self.device.PixelFormat.ToString()
        except:
            return "Unknown"

    def get_size(self) -> Tuple[int, int]:
        """Get current ROI width and height"""
        if not self.is_connected():
            return 640, 480
        try:
            width = self.get_parameter("Width", 640)
            height = self.get_parameter("Height", 480)
            return int(width), int(height)
        except:
            return 640, 480

    def set_parameter(self, name: str, value):
        """Set camera parameter safely within limits"""
        if not self.is_connected():
            return

        try:
            param = getattr(self.device, name, None)
            if param is None or not param.IsWritable():
                return

            if hasattr(param, 'Min') and hasattr(param, 'Max'):
                value = max(param.Min, min(param.Max, value))
                if hasattr(param, 'Inc') and param.Inc > 0:
                    value = round(value / param.Inc) * param.Inc
                    value = max(param.Min, min(param.Max, value))

            param.Value = value
            log.info(f"Set {name} = {param.Value}")
        except Exception as e:
            log.debug(f"Cannot set {name}: {e}")

    def get_parameter(self, name: str, default=None):
        """Get camera parameter safely"""
        if not self.is_connected():
            return default
        try:
            param = getattr(self.device, name, None)
            if param and param.IsReadable():
                return param.Value
            return default
        except:
            return default

    def get_parameter_range(self, name: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Get min/max/increment for numeric parameter"""
        if not self.is_connected():
            return None, None, None
        try:
            param = getattr(self.device, name, None)
            if param and hasattr(param, 'Min') and hasattr(param, 'Max'):
                inc = param.Inc if hasattr(param, 'Inc') else None
                return param.Min, param.Max, inc
        except:
            pass
        return None, None, None

    def get_enum_values(self, name: str) -> List[str]:
        """Get available values for enum parameter"""
        if not self.is_connected():
            return []
        try:
            param = getattr(self.device, name, None)
            if param and hasattr(param, 'Symbolics'):
                return list(param.Symbolics)
        except:
            pass
        return []

    def set_enum_parameter(self, name: str, value: str):
        """Set enum parameter by string value"""
        if not self.is_connected():
            return

        try:
            param = getattr(self.device, name, None)
            if param and param.IsWritable():
                param.FromString(value)
                log.info(f"Set {name} = {value}")
        except Exception as e:
            log.debug(f"Cannot set enum {name}: {e}")

    def validate_and_get_default(self, name: str, default_value):
        """Get a valid default value within camera limits"""
        if not self.is_connected():
            return default_value

        min_val, max_val, inc = self.get_parameter_range(name)
        if min_val is not None and max_val is not None:
            value = max(min_val, min(max_val, default_value))
            if inc and inc > 0:
                value = round(value / inc) * inc
                value = max(min_val, min(max_val, value))
            return value
        return default_value
