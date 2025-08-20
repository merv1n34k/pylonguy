import subprocess
import os
import logging
import numpy as np

log = logging.getLogger("pylon_gui")

class VideoWriter:
    def __init__(self, output_path: str, width: int, height: int,
                 fps: float = 24.0, pixel_format: str = None):
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.pixel_format = pixel_format or "Mono8"
        self.process = None

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    def start(self) -> bool:
        """Start FFmpeg process"""
        if self.process:
            self.stop()

        try:
            # Map camera format to FFmpeg format
            ffmpeg_fmt = self.get_ffmpeg_format()

            cmd = [
                "ffmpeg",
                "-y",  # Overwrite
                "-f", "rawvideo",
                "-pix_fmt", ffmpeg_fmt,
                "-s", f"{self.width}x{self.height}",
                "-r", str(self.fps),
                "-i", "-",  # stdin
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                self.output_path
            ]

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                bufsize=10**8
            )

            # Check if started
            if self.process.poll() is not None:
                stderr = self.process.stderr.read()
                log.error(f"FFmpeg failed: {stderr.decode('utf-8', errors='ignore')[:200]}")
                self.process = None
                return False

            log.info(f"Recording: {self.width}x{self.height} @ {self.fps}fps")
            log.info(f"Format: {self.pixel_format} -> {ffmpeg_fmt}")
            return True

        except FileNotFoundError:
            log.error("FFmpeg not found. Install FFmpeg and add to PATH")
            return False
        except Exception as e:
            log.error(f"Failed to start recording: {e}")
            return False

    def get_ffmpeg_format(self):
        """Map camera pixel format to FFmpeg format"""
        # Simple mapping for common formats
        if "Mono16" in self.pixel_format:
            return "gray16le"
        elif "Mono12" in self.pixel_format:
            return "gray16le"  # 12-bit as 16-bit
        elif "Mono10" in self.pixel_format:
            return "gray16le"  # 10-bit as 16-bit
        elif "Mono8" in self.pixel_format:
            return "gray"
        elif "BGR" in self.pixel_format:
            return "bgr24"
        elif "RGB" in self.pixel_format:
            return "rgb24"
        elif "Bayer" in self.pixel_format:
            # Try to determine Bayer pattern
            if "RG" in self.pixel_format:
                return "bayer_rggb8"
            elif "GR" in self.pixel_format:
                return "bayer_grbg8"
            elif "GB" in self.pixel_format:
                return "bayer_gbrg8"
            elif "BG" in self.pixel_format:
                return "bayer_bggr8"
            return "bayer_rggb8"  # Default Bayer
        else:
            log.warning(f"Unknown format {self.pixel_format}, using grayscale")
            return "gray"

    def write_frame(self, frame):
        """Write raw frame to video"""
        if not self.process or not self.process.stdin:
            return False

        try:
            # Check if pipe is open
            if self.process.stdin.closed:
                return False

            # Handle bit depth conversion if needed
            write_frame = frame
            if "10" in self.pixel_format or "12" in self.pixel_format or "16" in self.pixel_format:
                # Ensure 16-bit for high bit depth formats
                if frame.dtype != np.uint16:
                    # If it's packed 10/12-bit in uint8, unpack it
                    if frame.dtype == np.uint8 and ("10p" in self.pixel_format or "12p" in self.pixel_format):
                        # Simple unpacking - treat as 16-bit
                        write_frame = np.frombuffer(frame.tobytes(), dtype=np.uint16).reshape(frame.shape[:2])
                    else:
                        write_frame = frame.astype(np.uint16)

            self.process.stdin.write(write_frame.tobytes())
            self.process.stdin.flush()
            return True

        except BrokenPipeError:
            log.warning("FFmpeg pipe broken")
            return False
        except Exception as e:
            log.error(f"Write error: {e}")
            return False

    def stop(self):
        """Stop recording"""
        if not self.process:
            return

        try:
            # Close stdin
            if self.process.stdin and not self.process.stdin.closed:
                try:
                    self.process.stdin.close()
                except:
                    pass

            # Wait for FFmpeg
            if self.process.poll() is None:
                try:
                    self.process.wait(timeout=5)
                    log.info(f"Recording saved: {self.output_path}")
                except subprocess.TimeoutExpired:
                    log.warning("FFmpeg timeout, terminating...")
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except:
                        self.process.kill()
        except Exception as e:
            log.error(f"Stop error: {e}")
        finally:
            self.process = None

    def is_recording(self) -> bool:
        return self.process is not None and self.process.poll() is None
