#!/usr/bin/env python3
"""Build the exact-length interrupt-fed ZX0 Fast stage v9 bundle."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from build_fastboot_v8 import crc16_ibm, patch_unique

CORE_SIZE = 128
SYSTEM_PREFIX = 512
SYSTEM_SIZE = 6656
COMPRESSED_LIMIT = 0x1800
MAGIC = b"JFV9"
PAYLOAD_MAGIC = b"Z9"
EXTENSION_LENGTH_SENTINEL = bytes.fromhex("01 5A A5")
LENGTH_SENTINEL = bytes.fromhex("21 5A A5 22")
CRC_HIGH_SENTINEL = bytes.fromhex("FE A5 C2")
CRC_LOW_SENTINEL = bytes.fromhex("00 FE 5A C2")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("core", type=Path)
    parser.add_argument("extension", type=Path)
    parser.add_argument("system", type=Path)
    parser.add_argument("compressor", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    core = bytearray(args.core.read_bytes())
    extension = bytearray(args.extension.read_bytes())
    system_image = args.system.read_bytes()
    if core[3:7] != MAGIC or core[7:11] != b"\x01\x00\x5a\xa5":
        raise ValueError("fastboot v9 core metadata is missing or malformed")
    if len(core) > CORE_SIZE:
        raise ValueError(
            f"fastboot v9 core is {len(core)} bytes, limit {CORE_SIZE}"
        )
    if not 256 <= len(extension) <= 0xFFFF:
        raise ValueError(
            f"fastboot v9 extension has invalid size {len(extension)}"
        )
    if len(system_image) != 10240 or \
            system_image[:SYSTEM_PREFIX] != bytes((0xE5,)) * SYSTEM_PREFIX:
        raise ValueError("fastboot v9 requires a 10 KiB JUKUSYS system image")
    system = system_image[SYSTEM_PREFIX:SYSTEM_PREFIX + SYSTEM_SIZE]

    extension_size = len(extension)
    core[9:11] = extension_size.to_bytes(2, "little")
    patch_unique(
        core, EXTENSION_LENGTH_SENTINEL, 1,
        extension_size.to_bytes(2, "little"), "extension length",
    )

    with tempfile.TemporaryDirectory(prefix="juku-fastboot-v9-") as directory:
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
            f"fastboot v9 compressed system is {len(compressed)} bytes, "
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
    bundle = bytes(core).ljust(CORE_SIZE, b"\0") + bytes(extension) + \
        descriptor + compressed
    args.output.write_bytes(bundle)
    print(
        f"Fastboot v9 bundle: core={len(core)}/{CORE_SIZE}, "
        f"extension={len(extension)} exact bytes, "
        f"system={SYSTEM_SIZE}->{len(compressed)}, "
        f"compressed CRC16/IBM={compressed_crc:04X}, "
        f"system CRC16/IBM={system_crc:04X}, total={len(bundle)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
