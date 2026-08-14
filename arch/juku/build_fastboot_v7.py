#!/usr/bin/env python3
"""Build the fixed-payload 19200/8N1 ZX0 Fast stage v7 bundle."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

CORE_SIZE = 128
EXTENSION_SIZE = 256
SYSTEM_PREFIX = 512
SYSTEM_SIZE = 6656
COMPRESSED_LIMIT = 0x1800
MAGIC = b"JFV7"
PAYLOAD_MAGIC = b"Z7"
LENGTH_SENTINEL = bytes.fromhex("01 5a a5")
CRC_HIGH_SENTINEL = bytes.fromhex("3e a5 ba")
CRC_LOW_SENTINEL = bytes.fromhex("3e 5a bb")
CORE_RX_OFFSET = 0x6E
CORE_RX = bytes.fromhex("db 09 e6 02 ca 6e 01 db 08 c9")


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
    extension = bytearray(args.extension.read_bytes())
    system_image = args.system.read_bytes()
    if core[3:7] != MAGIC or core[7:9] != b"\x01\x02":
        raise ValueError("fastboot v7 core metadata is missing or malformed")
    if core[CORE_RX_OFFSET:CORE_RX_OFFSET + len(CORE_RX)] != CORE_RX:
        raise ValueError("fastboot v7 core RX entry moved from 016Eh")
    if len(core) > CORE_SIZE:
        raise ValueError(f"fastboot v7 core is {len(core)} bytes, limit {CORE_SIZE}")
    if len(extension) > EXTENSION_SIZE:
        raise ValueError(
            f"fastboot v7 extension is {len(extension)} bytes, "
            f"limit {EXTENSION_SIZE}"
        )
    for name, sentinel in (
        ("length", LENGTH_SENTINEL),
        ("CRC high", CRC_HIGH_SENTINEL),
        ("CRC low", CRC_LOW_SENTINEL),
    ):
        if extension.count(sentinel) != 1:
            raise ValueError(
                f"fastboot v7 {name} sentinel is missing or ambiguous"
            )
    if len(system_image) != 10240 or \
            system_image[:SYSTEM_PREFIX] != bytes((0xE5,)) * SYSTEM_PREFIX:
        raise ValueError("fastboot v7 requires a 10 KiB JUKUSYS system image")
    system = system_image[SYSTEM_PREFIX:SYSTEM_PREFIX + SYSTEM_SIZE]

    with tempfile.TemporaryDirectory(prefix="juku-fastboot-v7-") as directory:
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
            f"fastboot v7 compressed system is {len(compressed)} bytes, "
            f"limit {COMPRESSED_LIMIT - 1}"
        )
    compressed_crc = crc16_ibm(compressed)
    length_offset = extension.index(LENGTH_SENTINEL) + 1
    extension[length_offset:length_offset + 2] = \
        len(compressed).to_bytes(2, "little")
    crc_high_offset = extension.index(CRC_HIGH_SENTINEL) + 1
    crc_low_offset = extension.index(CRC_LOW_SENTINEL) + 1
    extension[crc_high_offset] = compressed_crc >> 8
    extension[crc_low_offset] = compressed_crc & 0xFF
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
        f"Fastboot v7 bundle: core={len(core)}/{CORE_SIZE}, "
        f"extension={len(extension)}/{EXTENSION_SIZE}, "
        f"system={SYSTEM_SIZE}->{len(compressed)}, "
        f"compressed CRC16/IBM={compressed_crc:04X}, "
        f"system CRC16/IBM={system_crc:04X}, total={len(bundle)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
