#!/usr/bin/env python3
"""Build the self-describing negotiated-rate Fast stage v4 bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

CORE_SIZE = 128
EXTENSION_SIZE = 384
MAGIC = b"JFV4"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("core", type=Path)
    parser.add_argument("extension", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    core = args.core.read_bytes()
    extension = args.extension.read_bytes()
    if core[3:7] != MAGIC or core[7:9] != b"\x01\x03":
        raise ValueError("fastboot v4 core metadata is missing or malformed")
    if len(core) > CORE_SIZE:
        raise ValueError(f"fastboot v4 core is {len(core)} bytes, limit {CORE_SIZE}")
    if len(extension) > EXTENSION_SIZE:
        raise ValueError(
            f"fastboot v4 extension is {len(extension)} bytes, "
            f"limit {EXTENSION_SIZE}"
        )
    bundle = core.ljust(CORE_SIZE, b"\0") + \
        extension.ljust(EXTENSION_SIZE, b"\0")
    args.output.write_bytes(bundle)
    print(
        f"Fastboot v4 bundle: core={len(core)}/{CORE_SIZE}, "
        f"extension={len(extension)}/{EXTENSION_SIZE}, total={len(bundle)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
