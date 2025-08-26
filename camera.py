"""Camera module - I/O and control"""
import numpy as np
from pypylon import pylon
from typing import Optional, Dict, Any, List
import logging

log = logging.getLogger("pylonguy")

class Camera:
    """Basler camera wrapper with clean parameter interface"""

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

            # Custom initial settings
            self.init_settings()

            log.info(f"Camera opened: {model} (S/N: {serial})")
            return True
        except Exception as e:
            log.error(f"Failed to open camera: {e}")
            return False

    def init_settings(self):
        """Apply initial optimization settings"""
        try:
            self.device.UserSetSelector.Value = "Default"
            self.device.UserSetLoad.Execute()

            self.set_parameter('DeviceLinkThroughputLimitMode', 'Off')
            self.set_parameter('MaxNumBuffer', 50)

            # Disable auto features for consistent performance
            for auto_feature in ['ExposureAuto', 'GainAuto', 'BalanceWhiteAuto']:
                self.set_parameter(auto_feature, 'Off')

            log.info("Initial camera settings applied")
        except Exception as e:
            log.warning(f"Could not apply all initial settings: {e}")

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

    def set_parameter(self, param_name: str, value: Any) -> bool:
        """General setter for any camera parameter"""
        try:
            if hasattr(self.device, param_name):
                param = getattr(self.device, param_name)
                if hasattr(param, 'SetValue'):
                    param.SetValue(value)
                    log.debug(f"Set {param_name} = {value}")
                    return True
        except Exception as e:
            log.error(f"Failed to set {param_name}: {e}")
        return False

    def get_parameter(self, param_name: str) -> Dict:
        """General getter for any camera parameter - returns dict with value and limits"""
        result = {}
        try:
            if hasattr(self.device, param_name):
                param = getattr(self.device, param_name)
                if hasattr(param, 'Value'):
                    result['value'] = param.Value
                if hasattr(param, 'Min'):
                    result['min'] = param.Min
                if hasattr(param, 'Max'):
                    result['max'] = param.Max
                if hasattr(param, 'Inc'):
                    result['inc'] = param.Inc
                if hasattr(param, 'Symbolics'):
                    result['symbolics'] = param.Symbolics
        except Exception as e:
            log.debug(f"Could not get {param_name}: {e}")
        return result

    def apply_settings(self, settings: Dict) -> bool:
        """Apply multiple settings at once"""
        if not self.device or settings is None:
            return False

        was_grabbing = self._is_grabbing

        try:
            # Stop grabbing if active
            if self._is_grabbing:
                self.stop_grabbing()

            # Apply all settings
            for k, v in settings.items():
                self.set_parameter(k, v)

        except Exception as e:
            log.error(f"Configuration failed: {e}")
            return False

        finally:
            # Restart grabbing if it was active
            if was_grabbing:
                try:
                    self.start_grabbing()
                except:
                    pass
            return True

    def get_settings(self, params: List[str]) -> Dict:
        """Get multiple parameters at once"""
        if not self.device or params is None:
            return {}

        result = {}
        try:
            for param in params:
                result[param] = self.get_parameter(param)
        except Exception as e:
            log.error(f"Could not get settings: {e}")
        return result

    def start_grabbing(self):
        """Start continuous frame acquisition"""
        if not self.device or self._is_grabbing:
            return

        try:
            self.device.StartGrabbing(pylon.GrabStrategy_OneByOne)
            self._is_grabbing = True
            log.info("Started grabbing")
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
            log.info("Stopped grabbing")
        except Exception as e:
            log.error(f"Failed to stop grabbing: {e}")
            self._is_grabbing = False

    def grab_frame(self, timeout_ms: int = 5) -> Optional[np.ndarray]:
        """Grab single frame - optimized for speed"""
        if not self.device:
            return None

        try:
            # Ensure we're grabbing
            if not self._is_grabbing:
                self.start_grabbing()

            if not self.device.IsGrabbing():
                return None

            # Retrieve frame with minimal timeout
            result = self.device.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)

            if result and result.GrabSucceeded():
                frame = result.GetArray()
                result.Release()
                return frame
            elif result:
                result.Release()

            return None
        except:
            return None

    def get_resulting_framerate(self) -> float:
        """Get actual resulting frame rate from camera with fallbacks"""
        # Try ResultingFrameRate first
        param = self.get_parameter('ResultingFrameRate')
        if param and 'value' in param:
            return param.get('value', 0.0)

        # Try ResultingFrameRateAbs as fallback
        param = self.get_parameter('ResultingFrameRateAbs')
        if param and 'value' in param:
            return param.get('value', 0.0)

        # Return 0 if neither exists - app will estimate
        return 0.0
