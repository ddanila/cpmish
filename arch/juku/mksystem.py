#!/usr/bin/env python3
"""Package a linked Juku resident image as a 10 KiB SYSGEN artifact."""

from pathlib import Path
import sys


PREFIX_SIZE = 4 * 128
SYSTEM_SIZE = 52 * 128
FILE_SIZE = 10 * 1024


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit(f"usage: {sys.argv[0]} MEMORY OUTPUT [INITIAL-COMMAND]")

    memory = Path(sys.argv[1]).read_bytes()
    if len(memory) > SYSTEM_SIZE:
        raise SystemExit(
            f"resident image is {len(memory)} bytes; limit is {SYSTEM_SIZE}"
        )

    output = bytearray([0xE5]) * FILE_SIZE
    output[PREFIX_SIZE : PREFIX_SIZE + SYSTEM_SIZE] = bytes(SYSTEM_SIZE)
    output[PREFIX_SIZE : PREFIX_SIZE + len(memory)] = memory
    if len(sys.argv) == 4:
        try:
            command = sys.argv[3].encode("ascii")
        except UnicodeEncodeError as error:
            raise SystemExit("initial command must be ASCII") from error
        if not command or len(command) > 127:
            raise SystemExit("initial command must contain 1..127 bytes")
        # DRI CCP: CBASE+7 is the length and CBASE+8 the command buffer.
        output[PREFIX_SIZE + 7] = len(command)
        output[PREFIX_SIZE + 8 : PREFIX_SIZE + 8 + len(command)] = command
    Path(sys.argv[2]).write_bytes(output)


if __name__ == "__main__":
    main()
