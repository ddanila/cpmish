#!/usr/bin/env python3
"""Combine a CP/M Plus SYS file and Juku adapter into a RAM image."""

from __future__ import annotations

import argparse
from pathlib import Path


PREFIX_SIZE = 512
LOAD_ADDRESS = 0x7000
ADAPTER_ADDRESS = 0xA000
ENTRY_ADDRESS = 0x9C00
END_ADDRESS = 0xB000
MAGIC = b"JUKURM1\x1a"


def crc16_ibm(data: bytes) -> int:
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def unpack_sys(data: bytes) -> tuple[bytearray, int]:
    if len(data) < 256 or len(data) % 128:
        raise ValueError("CPM3.SYS must contain complete 128-byte records")
    common_top, common_pages, bank_top, bank_pages = data[:4]
    entry = int.from_bytes(data[4:6], "little")
    if bank_top or bank_pages:
        raise ValueError("only a non-banked CPM3.SYS is supported")
    if entry != ENTRY_ADDRESS or common_top * 256 != ADAPTER_ADDRESS:
        raise ValueError("unexpected CP/M Plus entry or memory top")
    records = common_pages * 2
    payload = data[256:]
    if len(payload) != records * 128:
        raise ValueError("CPM3.SYS common length does not match its header")
    memory = bytearray(END_ADDRESS - LOAD_ADDRESS)
    for index in range(records):
        address = ADAPTER_ADDRESS - (index + 1) * 128
        offset = address - LOAD_ADDRESS
        memory[offset:offset + 128] = payload[index * 128:(index + 1) * 128]
    return memory, ADAPTER_ADDRESS - common_pages * 256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("adapter", type=Path)
    parser.add_argument("cpm3_sys", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    adapter = args.adapter.read_bytes()
    if not adapter or len(adapter) > 0x1000:
        raise ValueError("Juku CP/M Plus adapter must fit A000h..AFFFh")
    memory, system_base = unpack_sys(args.cpm3_sys.read_bytes())
    adapter_offset = ADAPTER_ADDRESS - LOAD_ADDRESS
    if any(memory[adapter_offset:adapter_offset + len(adapter)]):
        raise ValueError("CP/M Plus system overlaps the adapter window")
    memory[adapter_offset:adapter_offset + len(adapter)] = adapter

    header = bytearray([0xE5]) * PREFIX_SIZE
    header[:8] = MAGIC
    header[8:10] = LOAD_ADDRESS.to_bytes(2, "little")
    header[10:12] = ENTRY_ADDRESS.to_bytes(2, "little")
    header[12:14] = len(memory).to_bytes(2, "little")
    header[14:16] = crc16_ibm(memory).to_bytes(2, "little")
    args.output.write_bytes(header + memory)
    print(
        f"Juku CP/M Plus image: adapter={len(adapter)} bytes, "
        f"system={system_base:04X}h..{ADAPTER_ADDRESS - 1:04X}h, "
        f"adapter={ADAPTER_ADDRESS:04X}h.."
        f"{ADAPTER_ADDRESS + len(adapter) - 1:04X}h, "
        f"entry={ENTRY_ADDRESS:04X}h, CRC16/IBM={crc16_ibm(memory):04X}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
