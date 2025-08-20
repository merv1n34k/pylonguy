"""Minimal camera wrapper - only essential operations"""
import numpy as np
from pypylon import pylon
from typing import Optional
import logging

log = logging.getLogger("pylon_gui")

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
        """Start continuous grabbing"""
        if self.device and not self.device.IsGrabbing():
            self.device.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    def stop_grabbing(self):
        """Stop grabbing"""
        if self.device and self.device.IsGrabbing():
            self.device.StopGrabbing()

    def grab_frame(self) -> Optional[np.ndarray]:
        """Grab single raw frame"""
        if not self.device:
            return None

        try:
            if not self.device.IsGrabbing():
                self.start_grabbing()

            result = self.device.RetrieveResult(1000, pylon.TimeoutHandling_Return)
            if result.GrabSucceeded():
                arr = result.Array.copy()
                result.Release()
                return arr
            result.Release()
        except:
            pass
        return None

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
