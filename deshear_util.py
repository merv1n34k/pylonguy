"""Deshearing utility functions"""

import numpy as np


def shift_row_linear(row: np.ndarray, shift_px: float, bg_val: int = 255) -> np.ndarray:
    """Subpixel 1D shift with linear interpolation"""
    w = row.shape[0]
    x = np.arange(w, dtype=np.float32)
    x_src = x - np.float32(shift_px)
    x_src_clipped = np.clip(x_src, 0.0, float(w - 1))
    out = np.interp(x, x_src_clipped, row.astype(np.float32))
    out[(x_src < 0.0) | (x_src > (w - 1))] = float(bg_val)
    return out.astype(np.uint8)


def deshear_array(
    array: np.ndarray, angle_deg: float, px_um: float, dy_um: float
) -> np.ndarray:
    """Deshear waterfall array"""
    import math

    h, w = array.shape
    tan_theta = math.tan(math.radians(angle_deg))
    shift_per_line_px = (tan_theta * dy_um) / px_um

    out = np.empty_like(array)
    for i in range(h):
        shift_px = i * shift_per_line_px
        out[i, :] = shift_row_linear(array[i, :], shift_px)

    return out
