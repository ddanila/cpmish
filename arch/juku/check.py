#!/usr/bin/env python3
"""Structural checks for the Juku system, flat volume, and raw image."""

from pathlib import Path
import subprocess
import sys


PREFIX_SIZE = 4 * 128
SYSTEM_SIZE = 52 * 128
SYSTEM_FILE_SIZE = 10 * 1024
TRACK_SIZE = 10 * 512
TRACKS = 80
SIDE_SIZE = TRACKS * TRACK_SIZE
IMAGE_SIZE = 2 * SIDE_SIZE
CBASE = 0xB400
BBASE = 0xCA00
ROOT = Path(__file__).resolve().parents[2]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(f"usage: {sys.argv[0]} SYSTEM FLAT-SIDE RAW-IMAGE")

    system_path, flat_path, raw_path = map(Path, sys.argv[1:])
    system = system_path.read_bytes()
    flat = flat_path.read_bytes()
    raw = raw_path.read_bytes()

    require(len(system) == SYSTEM_FILE_SIZE, "system file is not 10 KiB")
    require(system[:PREFIX_SIZE] == bytes([0xE5]) * PREFIX_SIZE,
            "system file lacks its four-record E5 prefix")
    require(system[PREFIX_SIZE] == 0xC3, "CCP entry is not a JMP")
    bios = PREFIX_SIZE + BBASE - CBASE
    require(system[bios] == 0xC3, "BIOS entry is not a JMP")
    require(system[PREFIX_SIZE + SYSTEM_SIZE:] ==
            bytes([0xE5]) * (SYSTEM_FILE_SIZE - PREFIX_SIZE - SYSTEM_SIZE),
            "system allocation tail is not erased")

    require(len(flat) == SIDE_SIZE, "flat volume is not 400 KiB")
    require(flat[:SYSTEM_FILE_SIZE] == system,
            "flat volume does not contain the system-track file")
    require(len(raw) == IMAGE_SIZE, "raw image is not 800 KiB")

    recovered = bytearray()
    side1_erased = True
    for cylinder in range(TRACKS):
        offset = cylinder * 2 * TRACK_SIZE
        recovered.extend(raw[offset : offset + TRACK_SIZE])
        side1_erased &= (
            raw[offset + TRACK_SIZE : offset + 2 * TRACK_SIZE]
            == bytes([0xE5]) * TRACK_SIZE
        )
    require(bytes(recovered) == flat, "raw side 0 does not round-trip")
    require(side1_erased, "raw side 1 is not erased")

    listing = subprocess.run(
        ["cpmls", "-f", "juku386", str(flat_path)],
        check=True,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.lower()
    for filename in ("readme.txt", "asm.com", "copy.com", "dump.com",
                     "stat.com", "submit.com"):
        require(filename in listing, f"{filename} is absent from the volume")


if __name__ == "__main__":
    main()
