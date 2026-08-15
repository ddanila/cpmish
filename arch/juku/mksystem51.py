#!/usr/bin/env python3
"""Package the relocated 51K Juku resident image in an extended SYSGEN file."""

from pathlib import Path
import sys


PREFIX_SIZE = 4 * 128
SYSTEM_SIZE = 60 * 128             # B000h..CDFFh
FILE_SIZE = 10 * 1024
MAGIC = b"JUKU51\x1a\x00"


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} MEMORY OUTPUT")

    memory = Path(sys.argv[1]).read_bytes()
    if len(memory) > SYSTEM_SIZE:
        raise SystemExit(
            f"resident image is {len(memory)} bytes; limit is {SYSTEM_SIZE}"
        )

    output = bytearray([0xE5]) * FILE_SIZE
    output[:len(MAGIC)] = MAGIC
    output[PREFIX_SIZE:PREFIX_SIZE + SYSTEM_SIZE] = bytes(SYSTEM_SIZE)
    output[PREFIX_SIZE:PREFIX_SIZE + len(memory)] = memory
    Path(sys.argv[2]).write_bytes(output)


if __name__ == "__main__":
    main()
