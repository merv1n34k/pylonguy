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

    @staticmethod
    def enumerate_cameras() -> list:
        """Get list of available cameras"""
        try:
            tlf = pylon.TlFactory.GetInstance()
            devices = tlf.EnumerateDevices()
            camera_list = []
            for device in devices:
                try:
                    model = device.GetModelName()
                    serial = device.GetSerialNumber()
                    camera_list.append(f"{model} ({serial})")
                except Exception:
                    camera_list.append("Unknown Camera")
            return camera_list
        except Exception as e:
            log.debug(f"Camera enumeration failed: {e}")
            return []

    def open(self, camera_index: int = 0, apply_defaults: bool = True) -> bool:
        """Open camera by index with optional default settings"""
        try:
            tlf = pylon.TlFactory.GetInstance()
            devices = tlf.EnumerateDevices()
            if not devices:
                log.error("No cameras found")
                return False

            if camera_index >= len(devices):
                log.error(f"Camera index {camera_index} not available")
                return False

            log.debug(f"Camera - Found {len(devices)} camera(s)")

            self.device = pylon.InstantCamera(tlf.CreateDevice(devices[camera_index]))
            self.device.Open()

            # Get device info
            device_info = self.device.GetDeviceInfo()
            model = device_info.GetModelName()
            serial = device_info.GetSerialNumber()

            # Apply initial settings only if requested
            if apply_defaults:
                self.init_settings()

            log.debug(f"Camera - Camera opened: {model} (S/N: {serial})")
            return True
        except Exception as e:
            log.error(f"Failed to open camera: {e}")
            return False

    def init_settings(self):
        """Apply initial optimization settings"""
        try:
            self.device.UserSetSelector.Value = "Default"
            self.device.UserSetLoad.Execute()

            self.set_parameter("DeviceLinkThroughputLimitMode", "Off")
            self.set_parameter("MaxNumBuffer", 50)

            # Disable auto features for consistent performance
            for auto_feature in ["ExposureAuto", "GainAuto", "BalanceWhiteAuto"]:
                try:
                    self.set_parameter(auto_feature, "Off")
                except Exception as e:
                    log.debug(f"Camera - Could not set {auto_feature}: {e}")

            log.debug("Initial camera settings applied")
        except Exception as e:
            log.warning(f"Could not apply all initial settings: {e}")

    def close(self):
        """Close camera connection"""
        if self.device:
            try:
                self.stop_grabbing()
                if self.device.IsOpen():
                    self.device.Close()
                log.debug("Camera - Camera closed")
            except Exception as e:
                log.debug(f"Camera - Error during close: {e}")
            self.device = None

    def set_parameter(self, param_name: str, value: Any) -> bool:
        """General setter for any camera parameter"""
        try:
            if hasattr(self.device, param_name):
                param = getattr(self.device, param_name)
                if hasattr(param, "SetValue"):
                    param.SetValue(value)
                    log.debug(f"Camera - Set {param_name} = {value}")
                    return True
        except Exception as e:
            log.debug(f"Camera - Failed to set {param_name}: {e}")
        return False

    def get_parameter(self, param_name: str, value_only=False) -> Dict:
        """
        General getter for any camera parameter
        returns dict with value and limits
        """
        result = {}
        try:
            if hasattr(self.device, param_name):
                param = getattr(self.device, param_name)
                if hasattr(param, "Value"):
                    result["value"] = param.Value
                    if value_only:
                        return result
                if hasattr(param, "Min"):
                    result["min"] = param.Min
                if hasattr(param, "Max"):
                    result["max"] = param.Max
                if hasattr(param, "Inc"):
                    result["inc"] = param.Inc
                if hasattr(param, "Symbolics"):
                    result["symbolics"] = param.Symbolics
        except Exception as e:
            # log.debug(f"Camera - Could not get {param_name}: {e}")
            pass
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
                except Exception as e:
                    log.debug(f"Camera - Could not restart grabbing: {e}")
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

    def start_grabbing(self, latest_only: bool = True):
        """Start continuous frame acquisition

        Args:
            latest_only: If True, use LatestImageOnly strategy (better for preview).
                        If False, use OneByOne strategy (preserves all frames for recording).
        """
        if not self.device:
            return

        # Check actual device state to avoid race conditions
        if self.device.IsGrabbing():
            self._is_grabbing = True
            return

        try:
            strategy = (
                pylon.GrabStrategy_LatestImageOnly
                if latest_only
                else pylon.GrabStrategy_OneByOne
            )
            self.device.StartGrabbing(strategy)
            self._is_grabbing = True
            log.debug(f"Camera - Started grabbing (latest_only={latest_only})")
        except Exception as e:
            log.error(f"Failed to start grabbing: {e}")
            self._is_grabbing = False

    def stop_grabbing(self):
        """Stop frame acquisition"""
        if not self.device:
            return

        try:
            # Always check actual device state
            if self.device.IsGrabbing():
                self.device.StopGrabbing()
                log.debug("Camera - Stopped grabbing")
            self._is_grabbing = False
        except Exception as e:
            log.error(f"Failed to stop grabbing: {e}")
            self._is_grabbing = False

    def grab_frame(self, timeout_ms: int = 5) -> Optional[np.ndarray]:
        """Grab single frame"""
        if not self.device or not self.device.IsGrabbing():
            return None

        try:

            # Retrieve frame with minimal timeout
            result = self.device.RetrieveResult(
                timeout_ms, pylon.TimeoutHandling_Return
            )

            if result and result.GrabSucceeded():
                frame = result.GetArray()
                result.Release()
                return frame
            elif result:
                result.Release()

            return None
        except Exception:
            return None

    def get_resulting_framerate(self) -> float:
        """Get actual resulting frame rate from camera with fallbacks"""
        param = self.get_parameter("ResultingFrameRate", True)
        if param and "value" in param:
            return param.get("value", 0.0)

        param = self.get_parameter("ResultingFrameRateAbs", True)
        if param and "value" in param:
            return param.get("value", 0.0)

        # Return 0 so app will estimate fps
        return 0.0
