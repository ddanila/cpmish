#!/usr/bin/env python3
"""Build the interrupt-fed streaming ZX0 Fast stage v8 bundle."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

CORE_SIZE = 128
EXTENSION_SIZE = 640
SYSTEM_PREFIX = 512
SYSTEM_SIZE = 6656
COMPRESSED_LIMIT = 0x1800
MAGIC = b"JFV8"
PAYLOAD_MAGIC = b"Z8"
LENGTH_SENTINEL = bytes.fromhex("21 5a a5 22")
CRC_HIGH_SENTINEL = bytes.fromhex("fe a5 c2")
CRC_LOW_SENTINEL = bytes.fromhex("00 fe 5a c2")


def crc16_ibm(data: bytes, initial: int = 0) -> int:
    crc = initial
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def patch_unique(image: bytearray, sentinel: bytes, offset: int,
                 replacement: bytes, name: str) -> None:
    if image.count(sentinel) != 1:
        raise ValueError(f"fastboot v8 {name} sentinel is missing or ambiguous")
    start = image.index(sentinel) + offset
    image[start:start + len(replacement)] = replacement


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("core", type=Path)
    parser.add_argument("extension", type=Path)
    parser.add_argument("system", type=Path)
    parser.add_argument("compressor", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    core = args.core.read_bytes()
    extension = bytearray(args.extension.read_bytes())
    system_image = args.system.read_bytes()
    if core[3:7] != MAGIC or core[7:9] != b"\x01\x05":
        raise ValueError("fastboot v8 core metadata is missing or malformed")
    if len(core) > CORE_SIZE:
        raise ValueError(f"fastboot v8 core is {len(core)} bytes, limit {CORE_SIZE}")
    if len(extension) > EXTENSION_SIZE:
        raise ValueError(
            f"fastboot v8 extension is {len(extension)} bytes, "
            f"limit {EXTENSION_SIZE}"
        )
    if len(system_image) != 10240 or \
            system_image[:SYSTEM_PREFIX] != bytes((0xE5,)) * SYSTEM_PREFIX:
        raise ValueError("fastboot v8 requires a 10 KiB JUKUSYS system image")
    system = system_image[SYSTEM_PREFIX:SYSTEM_PREFIX + SYSTEM_SIZE]

    with tempfile.TemporaryDirectory(prefix="juku-fastboot-v8-") as directory:
        raw_path = Path(directory) / "system.bin"
        compressed_path = Path(directory) / "system.zx0"
        raw_path.write_bytes(system)
        subprocess.run(
            [str(args.compressor), "-f", "-c", str(raw_path),
             str(compressed_path)],
            check=True,
        )
        compressed = compressed_path.read_bytes()

    if len(compressed) < 0x100 or len(compressed) >= COMPRESSED_LIMIT:
        raise ValueError(
            f"fastboot v8 compressed system is {len(compressed)} bytes, "
            f"required range 256..{COMPRESSED_LIMIT - 1}"
        )
    compressed_crc = crc16_ibm(compressed)
    patch_unique(
        extension, LENGTH_SENTINEL, 1,
        len(compressed).to_bytes(2, "little"), "length",
    )
    patch_unique(
        extension, CRC_HIGH_SENTINEL, 1,
        bytes((compressed_crc >> 8,)), "CRC high",
    )
    patch_unique(
        extension, CRC_LOW_SENTINEL, 2,
        bytes((compressed_crc & 0xFF,)), "CRC low",
    )
    system_crc = crc16_ibm(system)
    descriptor = (
        PAYLOAD_MAGIC
        + system_crc.to_bytes(2, "big")
        + len(compressed).to_bytes(2, "big")
        + compressed_crc.to_bytes(2, "big")
    )
    bundle = (
        core.ljust(CORE_SIZE, b"\0")
        + bytes(extension).ljust(EXTENSION_SIZE, b"\0")
        + descriptor
        + compressed
    )
    args.output.write_bytes(bundle)
    print(
        f"Fastboot v8 bundle: core={len(core)}/{CORE_SIZE}, "
        f"extension={len(extension)}/{EXTENSION_SIZE}, "
        f"system={SYSTEM_SIZE}->{len(compressed)}, "
        f"compressed CRC16/IBM={compressed_crc:04X}, "
        f"system CRC16/IBM={system_crc:04X}, total={len(bundle)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
