#!/usr/bin/env python3
"""
Convert .wtf (waterfall) files to PNG images
Maintains backward compatibility with .kmg (kymograph) files

Usage:
    python wtf2png.py input.wtf                # Creates input.png
    python wtf2png.py input.wtf output.png      # Specify output name
    python wtf2png.py input.wtf --lines 480     # Split into multiple PNGs with 480 lines each
    python wtf2png.py *.wtf                     # Convert multiple files
    python wtf2png.py legacy.kmg                # Still works with old .kmg files
"""

import argparse
import numpy as np
from pathlib import Path
from PIL import Image
import sys


def read_waterfall_file(file_path: Path):
    """
    Read .wtf or .kmg file with embedded header and return as numpy array
    Supports WTF1, WTFDSR (legacy), and KMG1 headers for backward compatibility
    """
    with open(file_path, "rb") as f:
        # Read header
        header = f.read(6)

        if len(header) < 6:
            raise ValueError("Invalid file")

        magic = header[:4]

        if magic == b"WTFD":  # Legacy WTFDSR format
            f.seek(0)
            header = f.read(9)
            if header[:6] == b"WTFDSR":
                file_type = "waterfall (legacy deshear format)"
                width = int.from_bytes(header[6:8], "little")
            else:
                raise ValueError("Invalid WTFDSR header")
        elif magic == b"WTF1":
            file_type = "waterfall"
            width = int.from_bytes(header[4:6], "little")
        elif magic == b"KMG1":
            file_type = "kymograph (legacy)"
            width = int.from_bytes(header[4:6], "little")
        else:
            raise ValueError(f"Invalid header: {magic}")

        # Read data
        data = f.read()

    # Calculate dimensions
    total_pixels = len(data)
    lines = total_pixels // width

    if total_pixels % width != 0:
        print(f"Warning: Data size not evenly divisible by width {width}")

    # Reshape to 2D array
    array = np.frombuffer(data, dtype=np.uint8, count=lines * width)
    array = array.reshape((lines, width))

    print(f"Loaded {file_type}: {lines} lines × {width} pixels")

    return array


def save_png(array: np.ndarray, output_path: Path):
    """Save numpy array as PNG"""
    image = Image.fromarray(array, mode="L")
    image.save(output_path, "PNG")
    print(f"Saved: {output_path}")


def convert_file(
    input_path: Path,
    output_path: Path = None,
    max_lines: int = None,
):
    """Convert a single .wtf or .kmg file to PNG(s)"""
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return False

    try:
        # Read waterfall/kymograph
        array = read_waterfall_file(input_path)
        total_lines = array.shape[0]

        # If no line limit specified, save as single file
        if max_lines is None or total_lines <= max_lines:
            if output_path is None:
                output_path = input_path.with_suffix(".png")
            save_png(array, output_path)
        else:
            # Split into multiple files
            num_files = (total_lines + max_lines - 1) // max_lines  # Ceiling division
            print(
                f"Splitting into {num_files} files of up to {max_lines} lines each..."
            )

            base_name = output_path.stem if output_path else input_path.stem
            base_dir = output_path.parent if output_path else input_path.parent

            for i in range(num_files):
                start_line = i * max_lines
                end_line = min((i + 1) * max_lines, total_lines)

                # Extract chunk
                chunk = array[start_line:end_line, :]

                # Generate filename with zero-padded index
                chunk_path = base_dir / f"{base_name}_{i + 1:04d}.png"

                save_png(chunk, chunk_path)
                print(f"  Chunk {i + 1}/{num_files}: lines {start_line + 1}-{end_line}")

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Convert .wtf (waterfall) or .kmg (kymograph) files to PNG images"
    )

    parser.add_argument("input", nargs="+", help="Input .wtf or .kmg file(s)")
    parser.add_argument("output", nargs="?", help="Output PNG file (optional)")
    parser.add_argument(
        "--lines", "-l", type=int, help="Max lines per PNG (splits into multiple files)"
    )

    args = parser.parse_args()

    # Handle input files
    input_files = []
    for pattern in args.input:
        if "*" in pattern:
            # Support both .wtf and .kmg extensions
            wtf_files = list(Path(".").glob(pattern.replace("*", "*.wtf")))
            kmg_files = list(Path(".").glob(pattern.replace("*", "*.kmg")))
            input_files.extend(wtf_files)
            input_files.extend(kmg_files)
            # Also check if pattern matches directly
            direct_matches = list(Path(".").glob(pattern))
            for match in direct_matches:
                if match not in input_files:
                    input_files.append(match)
        else:
            input_files.append(Path(pattern))

    if not input_files:
        print("Error: No input files found")
        sys.exit(1)

    # Convert single file with specified output
    if len(input_files) == 1 and args.output and not args.lines:
        # Single file, output specified, no splitting
        convert_file(input_files[0], Path(args.output), args.lines)
    else:
        # Multiple files or splitting mode
        if args.output and len(input_files) > 1:
            print("Warning: Output name ignored for multiple files")

        for input_file in input_files:
            if input_file.suffix.lower() in [".wtf", ".kmg"]:
                print(f"\nConverting: {input_file}")
                convert_file(input_file, None, args.lines)


if __name__ == "__main__":
    main()
