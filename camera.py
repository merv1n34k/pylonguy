"""Camera module - simplified parameter interface for Basler cameras"""
import numpy as np
from pypylon import pylon
from typing import Optional, Tuple, Dict, Any
import logging

log = logging.getLogger("pylonguy")

class Camera:
    """Basler camera wrapper with clean parameter interface"""

    def __init__(self):
        self.device = None
        self._is_grabbing = False
        self._max_buffers = 50

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

            # Basic optimization settings
            self._apply_initial_settings()

            log.info(f"Camera opened: {model} (S/N: {serial})")
            return True
        except Exception as e:
            log.error(f"Failed to open camera: {e}")
            return False

    def _apply_initial_settings(self):
        """Apply initial optimization settings"""
        try:
            # Maximize packet size for GigE cameras
            if self.is_parameter_available('GevSCPSPacketSize'):
                self.set_parameter('GevSCPSPacketSize', 9000)  # Try jumbo frames

            # Set maximum number of buffers
            if self.is_parameter_available('MaxNumBuffer'):
                self.set_parameter('MaxNumBuffer', self._max_buffers)

            # Disable auto features for consistent performance
            for auto_feature in ['ExposureAuto', 'GainAuto', 'BalanceWhiteAuto']:
                if self.is_parameter_available(auto_feature):
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

    def configure_camera(self, config_func):
        """Execute configuration function with proper locking"""
        if not self.device:
            return False

        was_grabbing = self._is_grabbing

        try:
            # Stop grabbing if active
            if self._is_grabbing:
                self.stop_grabbing()

            # Execute configuration function
            result = config_func()

            # Restart grabbing if it was active
            if was_grabbing:
                self.start_grabbing()

            return result

        except Exception as e:
            log.error(f"Configuration failed: {e}")
            if was_grabbing:
                try:
                    self.start_grabbing()
                except:
                    pass
            return False

    # ============= General Parameter Access =============

    def set_parameter(self, param_name: str, value: Any) -> bool:
        """General setter for any camera parameter"""
        def apply():
            try:
                param = getattr(self.device, param_name)
                if hasattr(param, 'SetValue'):
                    # Check if parameter is writable
                    if hasattr(param, 'IsWritable') and not param.IsWritable():
                        log.warning(f"Parameter {param_name} is not writable")
                        return False
                    param.SetValue(value)
                    log.debug(f"Set {param_name} = {value}")
                    return True
            except Exception as e:
                log.error(f"Failed to set {param_name}: {e}")
                return False

        return self.configure_camera(apply)

    def get_parameter(self, param_name: str) -> Any:
        """General getter for any camera parameter"""
        try:
            param = getattr(self.device, param_name)
            if hasattr(param, 'GetValue'):
                return param.GetValue()
        except Exception as e:
            log.debug(f"Could not get {param_name}: {e}")
        return None

    def get_parameter_limits(self, param_name: str) -> Dict[str, Any]:
        """Get min/max/increment for a parameter"""
        try:
            param = getattr(self.device, param_name)
            limits = {}
            if hasattr(param, 'GetMin'):
                limits['min'] = param.GetMin()
            if hasattr(param, 'GetMax'):
                limits['max'] = param.GetMax()
            if hasattr(param, 'GetInc'):
                limits['inc'] = param.GetInc()
            return limits
        except:
            return {}

    def is_parameter_available(self, param_name: str) -> bool:
        """Check if parameter exists and is readable"""
        try:
            param = getattr(self.device, param_name, None)
            if param is None:
                return False
            if hasattr(param, 'IsReadable'):
                return param.IsReadable()
            return True
        except:
            return False

    # ============= Specific Parameter Setters =============

    def set_roi(self, width: int, height: int, offset_x: int = 0, offset_y: int = 0) -> bool:
        """Set region of interest"""
        def apply():
            try:
                # Get increments for proper alignment
                width_inc = self.get_parameter_limits('Width').get('inc', 1)
                height_inc = self.get_parameter_limits('Height').get('inc', 1)
                offset_inc = self.get_parameter_limits('OffsetX').get('inc', 1)

                # Align values to increments
                w = (width // width_inc) * width_inc
                h = (height // height_inc) * height_inc
                ox = (offset_x // offset_inc) * offset_inc
                oy = (offset_y // offset_inc) * offset_inc

                # Apply in correct order: reset offsets first
                self.device.OffsetX.SetValue(0)
                self.device.OffsetY.SetValue(0)

                # Set size
                self.device.Width.SetValue(w)
                self.device.Height.SetValue(h)

                # Set offsets
                self.device.OffsetX.SetValue(ox)
                self.device.OffsetY.SetValue(oy)

                log.info(f"ROI set: {w}x{h}+{ox}+{oy}")
                return True
            except Exception as e:
                log.error(f"Failed to set ROI: {e}")
                return False

        return self.configure_camera(apply)

    def set_exposure(self, microseconds: float) -> bool:
        """Set exposure time in microseconds"""
        def apply():
            try:
                # Try modern property name first
                if self.is_parameter_available('ExposureTime'):
                    limits = self.get_parameter_limits('ExposureTime')
                    value = max(limits.get('min', 0), min(microseconds, limits.get('max', 1000000)))
                    self.device.ExposureTime.SetValue(value)
                elif self.is_parameter_available('ExposureTimeAbs'):
                    limits = self.get_parameter_limits('ExposureTimeAbs')
                    value = max(limits.get('min', 0), min(microseconds, limits.get('max', 1000000)))
                    self.device.ExposureTimeAbs.SetValue(value)
                else:
                    return False

                log.info(f"Exposure set: {value:.1f} μs")
                return True
            except Exception as e:
                log.error(f"Failed to set exposure: {e}")
                return False

        return self.configure_camera(apply)

    def set_gain(self, gain: float) -> bool:
        """Set camera gain"""
        def apply():
            try:
                if self.is_parameter_available('Gain'):
                    limits = self.get_parameter_limits('Gain')
                    value = max(limits.get('min', 0), min(gain, limits.get('max', 48)))
                    self.device.Gain.SetValue(value)
                elif self.is_parameter_available('GainRaw'):
                    limits = self.get_parameter_limits('GainRaw')
                    value = int(max(limits.get('min', 0), min(gain, limits.get('max', 255))))
                    self.device.GainRaw.SetValue(value)
                else:
                    return False

                log.info(f"Gain set: {value}")
                return True
            except Exception as e:
                log.error(f"Failed to set gain: {e}")
                return False

        return self.configure_camera(apply)

    def set_binning(self, horizontal: int = 1, vertical: int = 1) -> bool:
        """Set binning (1 = no binning)"""
        def apply():
            try:
                success = True
                if self.is_parameter_available('BinningHorizontal'):
                    self.device.BinningHorizontal.SetValue(horizontal)
                else:
                    success = False

                if self.is_parameter_available('BinningVertical'):
                    self.device.BinningVertical.SetValue(vertical)
                else:
                    success = False

                if success:
                    log.info(f"Binning set: {horizontal}x{vertical}")
                return success
            except Exception as e:
                log.error(f"Failed to set binning: {e}")
                return False

        return self.configure_camera(apply)

    def set_pixel_format(self, format: str) -> bool:
        """Set pixel format (Mono8, Mono10, Mono10p)"""
        if format not in ['Mono8', 'Mono10', 'Mono10p']:
            log.error(f"Invalid pixel format: {format}")
            return False

        return self.set_parameter('PixelFormat', format)

    def set_sensor_readout_mode(self, mode: str) -> bool:
        """Set sensor readout mode (Normal/Fast)"""
        if not self.is_parameter_available('SensorReadoutMode'):
            log.debug("SensorReadoutMode not available")
            return True  # Not an error if not available

        return self.set_parameter('SensorReadoutMode', mode)

    def set_acquisition_framerate(self, enabled: bool, fps: Optional[float] = None) -> bool:
        """Enable/disable acquisition frame rate limit"""
        def apply():
            try:
                if self.is_parameter_available('AcquisitionFrameRateEnable'):
                    self.device.AcquisitionFrameRateEnable.SetValue(enabled)

                    if enabled and fps is not None and self.is_parameter_available('AcquisitionFrameRate'):
                        limits = self.get_parameter_limits('AcquisitionFrameRate')
                        value = max(limits.get('min', 1), min(fps, limits.get('max', 1000)))
                        self.device.AcquisitionFrameRate.SetValue(value)
                        log.info(f"Frame rate limit: {value:.1f} Hz")
                    elif not enabled:
                        log.info("Frame rate limit disabled")

                    return True
                return False
            except Exception as e:
                log.error(f"Failed to set frame rate: {e}")
                return False

        return self.configure_camera(apply)

    def set_device_link_throughput(self, enabled: bool, limit_mbps: Optional[float] = None) -> bool:
        """Enable/disable device link throughput limit"""
        def apply():
            try:
                if self.is_parameter_available('DeviceLinkThroughputLimitMode'):
                    mode = 'On' if enabled else 'Off'
                    self.device.DeviceLinkThroughputLimitMode.SetValue(mode)

                    if enabled and limit_mbps is not None and self.is_parameter_available('DeviceLinkThroughputLimit'):
                        # Convert Mbps to bps
                        limit_bps = int(limit_mbps * 1000000)
                        self.device.DeviceLinkThroughputLimit.SetValue(limit_bps)
                        log.info(f"Throughput limit: {limit_mbps:.1f} Mbps")
                    elif not enabled:
                        log.info("Throughput limit disabled")

                    return True
                return False
            except Exception as e:
                log.error(f"Failed to set throughput limit: {e}")
                return False

        return self.configure_camera(apply)

    # ============= Getters =============

    def get_roi(self) -> Tuple[int, int, int, int]:
        """Get current ROI (width, height, offset_x, offset_y)"""
        if not self.device:
            return 640, 480, 0, 0

        try:
            return (
                self.get_parameter('Width') or 640,
                self.get_parameter('Height') or 480,
                self.get_parameter('OffsetX') or 0,
                self.get_parameter('OffsetY') or 0
            )
        except:
            return 640, 480, 0, 0

    def get_resulting_framerate(self) -> float:
        """Get actual resulting frame rate from camera"""
        if self.is_parameter_available('ResultingFrameRate'):
            fps = self.get_parameter('ResultingFrameRate')
            return fps if fps is not None else 0.0
        return 0.0

    # ============= Acquisition Control =============

    def start_grabbing(self):
        """Start continuous frame acquisition"""
        if not self.device or self._is_grabbing:
            return

        try:
            # Use OneByOne strategy for consistent frame delivery
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
                # Get array without copy for speed
                frame = result.GetArray()
                result.Release()
                return frame
            elif result:
                result.Release()

            return None
        except:
            return None
