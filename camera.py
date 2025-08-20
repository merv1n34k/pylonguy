"""Minimal camera wrapper - only essential operations"""
import numpy as np
from pypylon import pylon
from typing import Optional
import logging

log = logging.getLogger("pylonguy")

class Camera:
    def __init__(self):
        self.device = None

    def open(self) -> bool:
        """Open first available camera"""
        try:
            tlf = pylon.TlFactory.GetInstance()
            devices = tlf.EnumerateDevices()
            if not devices:
                return False

            self.device = pylon.InstantCamera(tlf.CreateDevice(devices[0]))
            self.device.Open()

            self.device.DeviceLinkThroughputLimitMode.SetValue("Off")
            return True
        except:
            return False

    def close(self):
        """Close camera"""
        if self.device:
            try:
                if self.device.IsGrabbing():
                    self.device.StopGrabbing()
                if self.device.IsOpen():
                    self.device.Close()
            except:
                pass
            self.device = None

    def start_grabbing(self):
        """Start continuous grabbing with optimized settings for high speed"""
        if self.device and not self.device.IsGrabbing():
            # Use OneByOne strategy for recording to ensure no frames are dropped
            # LatestImageOnly can drop frames which is fine for preview but not recording
            self.device.StartGrabbing(pylon.GrabStrategy_OneByOne)

    def stop_grabbing(self):
        """Stop grabbing"""
        if self.device and self.device.IsGrabbing():
            self.device.StopGrabbing()

    def grab_frame(self) -> Optional[np.ndarray]:
        """Grab single raw frame - optimized version"""
        if not self.device:
            return None

        try:
            if not self.device.IsGrabbing():
                self.start_grabbing()

            # Reduced timeout for faster response
            result = self.device.RetrieveResult(100, pylon.TimeoutHandling_Return)
            if result and result.GrabSucceeded():
                # CRITICAL: Avoid copy for high-speed recording
                # Use GetArray() instead of Array for zero-copy access
                # Only copy if we need to keep the frame beyond the result lifetime
                arr = result.GetArray()  # Zero-copy numpy array

                # For recording, we immediately write, so we can use zero-copy
                # For display, we need a copy since result will be released
                if hasattr(self, '_recording_mode') and self._recording_mode:
                    # Return view for recording (faster)
                    frame = arr
                else:
                    # Return copy for display (safer)
                    frame = arr.copy()

                result.Release()
                return frame
            if result:
                result.Release()
        except Exception as e:
            pass
        return None

    def set_high_speed_mode(self, enable: bool):
        """Enable optimizations for high-speed recording"""
        if not self.device:
            return

        self._recording_mode = enable

        try:
            # Optimize camera for high-speed capture
            if enable:
                # Disable all auto features for consistent high speed
                if hasattr(self.device, 'ExposureAuto'):
                    self.device.ExposureAuto.Value = 'Off'
                if hasattr(self.device, 'GainAuto'):
                    self.device.GainAuto.Value = 'Off'

                # Enable frame burst mode if available
                if hasattr(self.device, 'AcquisitionBurstFrameCount'):
                    self.device.AcquisitionBurstFrameCount.Value = 100  # Grab in bursts

                # Optimize packet size for GigE cameras
                if hasattr(self.device, 'GevSCPSPacketSize'):
                    try:
                        # Use jumbo frames if supported
                        self.device.GevSCPSPacketSize.Value = 9000
                    except:
                        pass

                # Increase stream buffer count for high-speed
                if hasattr(self.device, 'MaxNumBuffer'):
                    self.device.MaxNumBuffer.Value = 50  # More buffers for high speed

        except Exception as e:
            log.warning(f"Could not fully optimize for high speed: {e}")

    def set_roi(self, width: int, height: int, offset_x: int = 0, offset_y: int = 0):
        """Set camera ROI"""
        if not self.device:
            return

        try:
            # Stop grabbing to change ROI
            was_grabbing = self.device.IsGrabbing()
            if was_grabbing:
                self.stop_grabbing()

            # Reset offsets to allow maximum width/height
            if hasattr(self.device, 'OffsetX'):
                self.device.OffsetX.Value = 0
            if hasattr(self.device, 'OffsetY'):
                self.device.OffsetY.Value = 0

            # Set dimensions
            if hasattr(self.device, 'Width'):
                self.device.Width.Value = width
            if hasattr(self.device, 'Height'):
                self.device.Height.Value = height

            # Set offsets
            if hasattr(self.device, 'OffsetX'):
                self.device.OffsetX.Value = offset_x
            if hasattr(self.device, 'OffsetY'):
                self.device.OffsetY.Value = offset_y

            if was_grabbing:
                self.start_grabbing()
        except:
            pass

    def get_roi(self) -> tuple:
        """Get current ROI (width, height, offset_x, offset_y)"""
        if not self.device:
            return 640, 480, 0, 0

        try:
            w = self.device.Width.Value if hasattr(self.device, 'Width') else 640
            h = self.device.Height.Value if hasattr(self.device, 'Height') else 480
            ox = self.device.OffsetX.Value if hasattr(self.device, 'OffsetX') else 0
            oy = self.device.OffsetY.Value if hasattr(self.device, 'OffsetY') else 0
            return (w, h, ox, oy)
        except:
            return 640, 480, 0, 0

    def set_exposure(self, microseconds: float):
        """Set exposure time"""
        if self.device:
            try:
                # Try to set exposure auto off first
                if hasattr(self.device, 'ExposureAuto'):
                    try:
                        self.device.ExposureAuto.Value = 'Off'
                    except:
                        pass

                # Try different exposure parameter names
                if hasattr(self.device, 'ExposureTime'):
                    self.device.ExposureTime.Value = microseconds
                elif hasattr(self.device, 'ExposureTimeAbs'):
                    self.device.ExposureTimeAbs.Value = microseconds
            except:
                pass

    def set_gain(self, gain: float):
        """Set gain"""
        if self.device:
            try:
                # Try to set gain auto off first
                if hasattr(self.device, 'GainAuto'):
                    try:
                        self.device.GainAuto.Value = 'Off'
                    except:
                        pass

                # Try different gain parameter names
                if hasattr(self.device, 'Gain'):
                    self.device.Gain.Value = gain
                elif hasattr(self.device, 'GainRaw'):
                    self.device.GainRaw.Value = int(gain)
            except:
                pass

    def set_sensor_mode(self, mode: str):
        """Set sensor readout mode (Normal/Fast)"""
        if self.device:
            try:
                if hasattr(self.device, 'SensorReadoutMode'):
                    self.device.SensorReadoutMode.Value = mode
            except:
                pass

    def set_framerate(self, enable: bool, fps: float = 30.0):
        """Set acquisition framerate"""
        if self.device:
            try:
                # Enable/disable framerate control
                if hasattr(self.device, 'AcquisitionFrameRateEnable'):
                    self.device.AcquisitionFrameRateEnable.Value = enable

                # Set framerate if enabled
                if enable:
                    if hasattr(self.device, 'AcquisitionFrameRate'):
                        self.device.AcquisitionFrameRate.Value = fps
                    elif hasattr(self.device, 'AcquisitionFrameRateAbs'):
                        self.device.AcquisitionFrameRateAbs.Value = fps
            except:
                pass
