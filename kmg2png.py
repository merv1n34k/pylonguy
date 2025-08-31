"""
Convert .kmg (kymograph) files to PNG images
"""

import argparse
import numpy as np
from pathlib import Path
from PIL import Image
import sys


def read_kmg(kmg_path: Path):
    """Read .kmg file with embedded header and return as numpy array"""
    with open(kmg_path, 'rb') as f:
        # Read header
        header = f.read(6)

        if len(header) < 6 or header[:4] != b'KMG1':
            print(f"Error: Invalid KMG file format (expected KMG1 header)")
            raise ValueError("Invalid KMG file")

        # Read width from header
        width = int.from_bytes(header[4:6], 'little')

        # Read the rest as data
        data = f.read()

    # Calculate dimensions
    total_pixels = len(data)
    lines = total_pixels // width

    if total_pixels % width != 0:
        print(f"Warning: Data size not evenly divisible by width {width}")

    # Reshape to 2D array
    array = np.frombuffer(data, dtype=np.uint8, count=lines * width)
    array = array.reshape((lines, width))

    print(f"Loaded: {lines} lines x {width} pixels")
    return array


def convert_file(input_path: Path, output_path: Path = None):
    """Convert a single .kmg file to PNG"""
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return False

    if output_path is None:
        output_path = input_path.with_suffix('.png')

    try:
        # Read kymograph
        array = read_kmg(input_path)

        # Save as PNG
        image = Image.fromarray(array)
        image.save(output_path, 'PNG')
        print(f"Saved: {output_path}")
        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Convert .kmg files to PNG images')
    parser.add_argument('input', nargs='+', help='Input .kmg file(s)')
    parser.add_argument('output', nargs='?', help='Output PNG file (optional)')

    args = parser.parse_args()

    # Handle input files
    input_files = []
    for pattern in args.input:
        if '*' in pattern:
            input_files.extend(Path('.').glob(pattern))
        else:
            input_files.append(Path(pattern))

    if not input_files:
        print("Error: No input files found")
        sys.exit(1)

    # Convert single file with specified output
    if len(input_files) == 1 and args.output:
        convert_file(input_files[0], Path(args.output))
    # Convert multiple files
    else:
        if args.output:
            print("Warning: Output name ignored for multiple files")

        for input_file in input_files:
            if input_file.suffix.lower() == '.kmg':
                print(f"Converting: {input_file}")
                convert_file(input_file)


if __name__ == '__main__':
    main()
