#!/usr/bin/env python3
"""Build the self-contained 19200/8N1 ZX0 Fast stage v6 bundle."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

CORE_SIZE = 128
EXTENSION_SIZE = 384
SYSTEM_PREFIX = 512
SYSTEM_SIZE = 6656
COMPRESSED_LIMIT = 0x1800
MAGIC = b"JFV6"
PAYLOAD_MAGIC = b"Z0"


def crc16_ibm(data: bytes, initial: int = 0) -> int:
    crc = initial
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("core", type=Path)
    parser.add_argument("extension", type=Path)
    parser.add_argument("system", type=Path)
    parser.add_argument("compressor", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    core = args.core.read_bytes()
    extension = args.extension.read_bytes()
    system_image = args.system.read_bytes()
    if core[3:7] != MAGIC or core[7:9] != b"\x01\x03":
        raise ValueError("fastboot v6 core metadata is missing or malformed")
    if len(core) > CORE_SIZE:
        raise ValueError(f"fastboot v6 core is {len(core)} bytes, limit {CORE_SIZE}")
    if len(extension) > EXTENSION_SIZE:
        raise ValueError(
            f"fastboot v6 extension is {len(extension)} bytes, "
            f"limit {EXTENSION_SIZE}"
        )
    if len(system_image) != 10240 or \
            system_image[:SYSTEM_PREFIX] != bytes((0xE5,)) * SYSTEM_PREFIX:
        raise ValueError("fastboot v6 requires a 10 KiB JUKUSYS system image")
    system = system_image[SYSTEM_PREFIX:SYSTEM_PREFIX + SYSTEM_SIZE]

    with tempfile.TemporaryDirectory(prefix="juku-fastboot-v6-") as directory:
        raw_path = Path(directory) / "system.bin"
        compressed_path = Path(directory) / "system.zx0"
        raw_path.write_bytes(system)
        subprocess.run(
            [
                str(args.compressor), "-f", "-c",
                str(raw_path), str(compressed_path),
            ],
            check=True,
        )
        compressed = compressed_path.read_bytes()

    if not compressed or len(compressed) >= COMPRESSED_LIMIT:
        raise ValueError(
            f"fastboot v6 compressed system is {len(compressed)} bytes, "
            f"limit {COMPRESSED_LIMIT - 1}"
        )
    system_crc = crc16_ibm(system)
    bundle = (
        core.ljust(CORE_SIZE, b"\0")
        + extension.ljust(EXTENSION_SIZE, b"\0")
        + PAYLOAD_MAGIC
        + system_crc.to_bytes(2, "big")
        + compressed
    )
    args.output.write_bytes(bundle)
    print(
        f"Fastboot v6 bundle: core={len(core)}/{CORE_SIZE}, "
        f"extension={len(extension)}/{EXTENSION_SIZE}, "
        f"system={SYSTEM_SIZE}->{len(compressed)}, "
        f"CRC16/IBM={system_crc:04X}, total={len(bundle)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
