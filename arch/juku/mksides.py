#!/usr/bin/env python3
"""Pack one flat 386K CP/M volume into a raw double-sided Juku image."""

from pathlib import Path
import sys


TRACK_SIZE = 10 * 512
TRACKS = 80
SIDE_SIZE = TRACKS * TRACK_SIZE
IMAGE_SIZE = 2 * SIDE_SIZE


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} FLAT-SIDE OUTPUT")

    source = Path(sys.argv[1]).read_bytes()
    if len(source) != SIDE_SIZE:
        raise SystemExit(
            f"flat Juku side is {len(source)} bytes; expected {SIDE_SIZE}"
        )

    output = bytearray([0xE5]) * IMAGE_SIZE
    for cylinder in range(TRACKS):
        source_offset = cylinder * TRACK_SIZE
        output_offset = cylinder * 2 * TRACK_SIZE
        output[output_offset : output_offset + TRACK_SIZE] = source[
            source_offset : source_offset + TRACK_SIZE
        ]

    Path(sys.argv[2]).write_bytes(output)


if __name__ == "__main__":
    main()
