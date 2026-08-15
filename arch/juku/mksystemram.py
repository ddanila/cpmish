#!/usr/bin/env python3
"""Package a self-describing Juku RAM-resident system image."""

from pathlib import Path
import sys


PREFIX_SIZE = 4 * 128
LOAD_ADDRESS = 0xB000
ENTRY_ADDRESS = 0xC600
MAGIC = b"JUKURM1\x1a"
# The independent BIOS may reclaim the first 128 bytes of the former RomBios
# workspace after interrupts are disabled, but must stop before D080h. Keeping
# this boundary explicit prevents a linked image from silently growing toward
# the framebuffer at D800h.
MAX_RESIDENT_SIZE = 0x2080


def crc16_ibm(data: bytes) -> int:
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} MEMORY OUTPUT")

    memory = Path(sys.argv[1]).read_bytes()
    if not memory or len(memory) > MAX_RESIDENT_SIZE:
        raise SystemExit(
            f"resident image is {len(memory)} bytes; limit is "
            f"{MAX_RESIDENT_SIZE} (ends at D080h)"
        )
    if len(memory) % 128:
        memory += bytes(128 - len(memory) % 128)
    if len(memory) > MAX_RESIDENT_SIZE:
        raise SystemExit("record padding would cross the D080h boundary")

    header = bytearray([0xE5]) * PREFIX_SIZE
    header[:8] = MAGIC
    header[8:10] = LOAD_ADDRESS.to_bytes(2, "little")
    header[10:12] = ENTRY_ADDRESS.to_bytes(2, "little")
    header[12:14] = len(memory).to_bytes(2, "little")
    header[14:16] = crc16_ibm(memory).to_bytes(2, "little")
    Path(sys.argv[2]).write_bytes(header + memory)


if __name__ == "__main__":
    main()
