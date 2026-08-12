#!/usr/bin/env python3
"""Package a linked Juku resident image as a 10 KiB SYSGEN artifact."""

from pathlib import Path
import sys


PREFIX_SIZE = 4 * 128
SYSTEM_SIZE = 52 * 128
FILE_SIZE = 10 * 1024


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} MEMORY OUTPUT")

    memory = Path(sys.argv[1]).read_bytes()
    if len(memory) > SYSTEM_SIZE:
        raise SystemExit(
            f"resident image is {len(memory)} bytes; limit is {SYSTEM_SIZE}"
        )

    output = bytearray([0xE5]) * FILE_SIZE
    output[PREFIX_SIZE : PREFIX_SIZE + SYSTEM_SIZE] = bytes(SYSTEM_SIZE)
    output[PREFIX_SIZE : PREFIX_SIZE + len(memory)] = memory
    Path(sys.argv[2]).write_bytes(output)


if __name__ == "__main__":
    main()
