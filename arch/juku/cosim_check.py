#!/usr/bin/env python3
"""Exercise the Juku CP/M image through the sibling 8080-cosim checkout."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
COSIM = Path(os.environ.get("JUKU_COSIM_ROOT", ROOT.parent / "8080-cosim"))
IMAGE = ROOT / "juku.img"
ROM = COSIM / "roms" / "ekta37.bin"
TRACK_SIZE = 10 * 512
TRACKS = 80
EXPECTED_VRAM = {
    "VER": "1ed8eb6710aa6c3189454110de5555c0b1b8de7328ef0777576fd21181f6e889",
    "DIR": "468ba5ff06e4dd63cfa8c1bc9a8214e3226a33ec40ea211d61e7649e6a3ba20c",
    "DIAG": "c90bf6be3ddf357efde10870c17713ca751ef0c4c57f28e9037d7c1d90e49718",
    "STAT": "9582fa7204ac14a7ca5c5d55f91dd164fe34fc234bda57eaa2aa77e154d4bce8",
    "SAVE 1 TEST.COM": "e3fa93fc3b0f513631a00d47be64e956a36d39c4c77d89f9f6b200fb65a0e9ae",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def build_trace(output: Path) -> None:
    sources = [
        COSIM / "cosim" / name
        for name in ("trace.c", "i8080.c", "juk_disk.c", "juku_fdc.c")
    ]
    require(ROM.is_file() and all(path.is_file() for path in sources),
            f"8080-cosim checkout is incomplete at {COSIM}")
    subprocess.run(
        [os.environ.get("CC", "cc"), "-O2", "-Wall", "-Wextra",
         "-o", str(output), *(str(path) for path in sources)],
        check=True,
    )


def seed_command(path: Path, command: str) -> None:
    data = bytearray(path.read_bytes())
    encoded = command.encode("ascii")
    # The DRI CCP accepts an initial command at CBASE+7. The system payload
    # starts after the 512-byte JUKUSYS prefix on raw cylinder 0, side 0.
    data[519] = len(encoded)
    data[520:520 + len(encoded) + 1] = encoded + b"\0"
    path.write_bytes(data)


def extract_side0(raw_path: Path, flat_path: Path) -> None:
    raw = raw_path.read_bytes()
    flat = b"".join(
        raw[cylinder * 2 * TRACK_SIZE:(cylinder * 2 + 1) * TRACK_SIZE]
        for cylinder in range(TRACKS)
    )
    flat_path.write_bytes(flat)


def run_case(trace: Path, work: Path, command: str) -> Path:
    case = work / command.split()[0].lower()
    case.mkdir()
    disk = case / "juku.img"
    shutil.copyfile(IMAGE, disk)
    seed_command(disk, command)
    environment = os.environ.copy()
    environment.update(
        JUKU_DISK=str(disk),
        JUKU_KEYS="TDD",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
    )
    if command.startswith("SAVE "):
        environment["JUKU_DISK_WRITABLE"] = "1"
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        subprocess.run(
            [str(trace), str(ROM), "300000000", "0", "200000"],
            check=True,
            cwd=case,
            env=environment,
            stdout=stdout,
            stderr=stderr,
        )
    vram = (case / "vram.bin").read_bytes()
    digest = hashlib.sha256(vram).hexdigest()
    require(digest == EXPECTED_VRAM[command],
            f"{command}: VRAM SHA256 {digest} does not match the prompt oracle")
    print(f"{command}: PASS (A> prompt VRAM {digest[:12]})")
    return disk


def main() -> None:
    require(IMAGE.is_file(), "juku.img is missing; build it first")
    with tempfile.TemporaryDirectory(prefix="cpmish-juku-cosim.") as name:
        work = Path(name)
        trace = work / "trace"
        build_trace(trace)
        run_case(trace, work, "VER")
        run_case(trace, work, "DIR")
        run_case(trace, work, "DIAG")
        run_case(trace, work, "STAT")
        saved = run_case(trace, work, "SAVE 1 TEST.COM")

        flat = work / "saved-side0.img"
        extracted = work / "test.com"
        extract_side0(saved, flat)
        listing = subprocess.run(
            ["cpmls", "-f", "juku386", str(flat)],
            check=True,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.lower()
        require("test.com" in listing, "SAVE did not create TEST.COM")
        subprocess.run(
            ["cpmcp", "-f", "juku386", str(flat), "0:TEST.COM", str(extracted)],
            check=True,
            cwd=ROOT,
        )
        require(extracted.stat().st_size == 256,
                f"TEST.COM is {extracted.stat().st_size} bytes, expected 256")
        print("SAVE persistence: PASS (TEST.COM is readable and 256 bytes)")

    print("JUKU-COSIM-CHECK: PASS")


if __name__ == "__main__":
    main()
