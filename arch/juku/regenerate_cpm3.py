#!/usr/bin/env python3
"""Regenerate the checked-in non-banked Juku CPM3.SYS image."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

import pexpect


ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "third_party" / "cpm3"


def tool(directory: Path, name: str) -> Path:
    for candidate in (directory / name.lower(), directory / name.upper()):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{name} is missing from {directory}")


def dos_text(source: Path, destination: Path) -> None:
    text = source.read_text().replace("\r\n", "\n").replace("\r", "\n")
    destination.write_bytes(text.replace("\n", "\r\n").encode("ascii"))


def run(command: list[str], work: Path) -> None:
    subprocess.run(command, cwd=work, check=True)


def generate(zxcc: Path, work: Path) -> None:
    child = pexpect.spawn(
        str(zxcc), ["GENCPM.COM"], cwd=str(work), encoding="latin1",
        timeout=15,
    )
    answers = (
        ("Use GENCPM.DAT", "Y"),
        ("Create a new", "N"),
        ("Display Load Map", ""),
        ("console columns", ""),
        ("lines in console", ""),
        ("Backspace", ""),
        ("Rubout", ""),
        ("default drive", ""),
        ("Top page", "9F"),
        ("Bank switched", ""),
        ("Accept new", ""),
    )
    transcript = ""
    for prompt, answer in answers:
        child.expect(prompt)
        transcript += child.before + child.after
        child.sendline(answer)
    child.expect(pexpect.EOF)
    transcript += child.before
    print(transcript)
    if "BIOS3    SPR  9C00H  0400H" not in transcript or \
            "BDOS3    SPR  7D00H  1F00H" not in transcript:
        raise RuntimeError("GENCPM produced an unexpected non-banked map")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zxcc", type=Path, required=True)
    parser.add_argument(
        "--tools", type=Path, required=True,
        help="directory containing RMAC.COM, LINK.COM, and GENCPM.COM",
    )
    parser.add_argument(
        "--output", type=Path, default=INPUTS / "cpm3.sys",
    )
    args = parser.parse_args()
    zxcc = args.zxcc.resolve()
    if not zxcc.is_file():
        raise FileNotFoundError(zxcc)

    with tempfile.TemporaryDirectory(prefix="cpmish-cpm3-build.") as name:
        work = Path(name)
        for filename in ("bdos3.spr", "gencpm.dat"):
            shutil.copy2(INPUTS / filename, work / filename)
        for filename in ("RMAC.COM", "LINK.COM", "GENCPM.COM"):
            shutil.copy2(tool(args.tools, filename), work / filename)
        dos_text(ROOT / "arch" / "juku" / "cpm3-bios.asm", work / "jbios.asm")
        dos_text(INPUTS / "scb.asm", work / "scb.asm")
        run([str(zxcc), "RMAC.COM", "jbios"], work)
        run([str(zxcc), "RMAC.COM", "scb"], work)
        run([str(zxcc), "LINK.COM", "bios3[os]=jbios,scb"], work)
        generate(zxcc, work)
        result = (work / "cpm3.sys").read_bytes()

    if result[:6] != bytes.fromhex("a0 23 00 00 00 9c") or len(result) != 9216:
        raise RuntimeError("generated CPM3.SYS has an unexpected header")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    print(f"wrote {args.output} ({len(result)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
