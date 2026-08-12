#!/usr/bin/env python3
"""Prove diskless CP/M boot, reads, and writes through Janet/USART."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import pty
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tty

from cosim_check import build_trace, require, seed_command


ROOT = Path(__file__).resolve().parents[2]
COSIM = Path(os.environ.get("JUKU_COSIM_ROOT", ROOT.parent / "8080-cosim"))
ROM = COSIM / "roms" / "ekta37.bin"
SYSTEM = ROOT / "juku-net-system.bin"
SMOKE_SYSTEM = ROOT / "juku-net-smoke-system.bin"
SMOKE_FLAT = ROOT / "juku-net-smoke.img"
FLAT = ROOT / ".obj" / "arch" / "juku" / "+flatdiskimage" / \
    "arch" / "juku" / "+flatdiskimage.img"
sys.path.insert(0, str(COSIM / "tools"))

from janet_disk_server import serve_disk  # noqa: E402
from janet_netboot import serve as serve_boot  # noqa: E402


EXPECTED_VRAM = {
    "DIR": "1ed29be4c31be50809396c73017b6b0733cbbde0322f49622e5500c2e44194df",
    "SAVE 1 TEST.COM": "32f3be5276bdef7d8444efdee6e41ad9fd5e7819dcfe6b29428efc168c90b0e7",
}
SMOKE_DIVISORS = (
    5102, 4290, 3822, 5102, 4290, 3608,
    3822, 5102, 4290, 3822, 4290, 5102,
)
SMOKE_TONE_UNITS = (1, 1, 2, 1, 1, 1, 2, 1, 1, 2, 1, 5)
SMOKE_GAP_UNITS = (1, 1, 1, 1, 1, 0, 2, 1, 1, 1, 1, 2)
EIGHTH_CYCLES = 2_000_000 * 60 / 112 / 2
TIMING_TOLERANCE_CYCLES = 2500
IO_PATTERN = re.compile(
    r"\[IOSEQ\] OUT port=0x(19|1B) value=0x([0-9A-F]{2}) "
    r"cyc=(\d+) pc=([0-9A-F]{4})"
)


def run_case(
    trace: Path,
    work: Path,
    command: str,
    *,
    system_source: Path = SYSTEM,
    volume_source: Path = FLAT,
    seed: bool = True,
    trace_io: bool = False,
) -> tuple[bytearray, dict[str, int], str]:
    case = work / command.split()[0].lower()
    case.mkdir()
    system = case / "system.bin"
    shutil.copyfile(system_source, system)
    if seed:
        seed_command(system, command)
    volume = bytearray(volume_source.read_bytes())
    master, slave = pty.openpty()
    tty.setraw(slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_TRACE_BANK="0",
        JUKU_DISABLE_SETTLE="1",
        JUKU_STOP_PROMPT_AFTER_USART_RX="13000",
        JUKU_KEYS="TN0201",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
    )
    if trace_io:
        environment["JUKU_TRACE_IO"] = "1"
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case,
            env=environment,
            stdout=stdout,
            stderr=stderr,
        )
        os.close(slave)
        result: dict[str, int] = {}
        disk_error: list[BaseException] = []
        try:
            boot = serve_boot(master, system.read_bytes(), timeout=120,
                              verbose=False)

            def disk_worker() -> None:
                try:
                    result.update(serve_disk(
                        master, volume, writable=command.startswith("SAVE "),
                        timeout=60, idle_timeout=None, verbose=False,
                        stats=result,
                    ))
                except BaseException as error:
                    disk_error.append(error)

            worker = threading.Thread(target=disk_worker)
            worker.start()
            process.wait(timeout=60)
            os.close(master)
            worker.join(timeout=3)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            try:
                os.close(master)
            except OSError:
                pass

    require(process.returncode == 0, f"{command}: cosim exited {process.returncode}")
    require(all(isinstance(error, OSError) for error in disk_error),
            f"{command}: disk server failed: {disk_error!r}")
    require(boot["image_bytes"] == 6784, f"{command}: bootstrap size changed")
    log = (case / "stderr.txt").read_text()
    require("JUKU disk image" not in log, f"{command}: local FDC media was attached")
    require("D57 divisor=8 -> byte_cycles=2300" in log,
            f"{command}: stock 9600 baud phase was not observed")
    require("D57 divisor=4 -> byte_cycles=1150" in log,
            f"{command}: 19200 baud takeover was not observed")
    require("stopped at A> prompt" in log, f"{command}: prompt oracle was not met")
    digest = hashlib.sha256((case / "vram.bin").read_bytes()).hexdigest()
    if command in EXPECTED_VRAM:
        require(digest == EXPECTED_VRAM[command],
                f"{command}: VRAM SHA256 {digest} does not match")
        require(result.get("reads", 0) >= 34,
                f"{command}: too few network reads")
    print(
        f"{command}: PASS (reads={result.get('reads', 0)}, "
        f"writes={result.get('writes', 0)}, retries={result.get('retries', 0)}, "
        f"VRAM={digest[:12]})"
    )
    return volume, result, log


def run_smoke_case(trace: Path, work: Path) -> None:
    _volume, result, log = run_case(
        trace,
        work,
        "SMOKE",
        system_source=SMOKE_SYSTEM,
        volume_source=SMOKE_FLAT,
        seed=False,
        trace_io=True,
    )
    require(result.get("reads", 0) >= 5,
            "SMOKE: remote COM lookup/load issued too few reads")

    outputs: list[tuple[int, int, int]] = []
    for line in log.splitlines():
        match = IO_PATTERN.search(line)
        if not match:
            continue
        port = int(match.group(1), 16)
        value = int(match.group(2), 16)
        cycle = int(match.group(3))
        pc = int(match.group(4), 16)
        if 0x0100 <= pc < 0x0180:
            outputs.append((port, value, cycle))

    expected_values: list[tuple[int, int]] = []
    for divisor in SMOKE_DIVISORS:
        expected_values.extend([
            (0x1B, 0x76),
            (0x19, divisor & 0xFF),
            (0x19, divisor >> 8),
            (0x1B, 0x50),
            (0x19, 0x01),
        ])
    require(
        [(port, value) for port, value, _cycle in outputs] == expected_values,
        f"SMOKE: speaker PIT sequence differs: {outputs!r}",
    )

    onsets = [outputs[index * 5][2] for index in range(len(SMOKE_DIVISORS))]
    for index, (first, second) in enumerate(zip(onsets, onsets[1:])):
        expected = (
            SMOKE_TONE_UNITS[index] + SMOKE_GAP_UNITS[index]
        ) * EIGHTH_CYCLES
        require(
            abs((second - first) - expected) <= TIMING_TOLERANCE_CYCLES,
            f"SMOKE: note {index + 1} onset delta {second - first} "
            f"differs from {expected:.1f} cycles",
        )
    print(
        "Monitorless SMOKE: PASS "
        "(auto-command; remote COM load; 12 notes; 4 bars; 112 BPM)"
    )


def main() -> None:
    require(
        all(path.is_file() for path in (SYSTEM, FLAT, SMOKE_SYSTEM, SMOKE_FLAT)),
        "build the normal and smoke network images first",
    )
    with tempfile.TemporaryDirectory(prefix="cpmish-juku-net.") as name:
        work = Path(name)
        trace = work / "trace"
        build_trace(trace)
        run_case(trace, work, "DIR")
        volume, result, _log = run_case(trace, work, "SAVE 1 TEST.COM")
        require(result.get("writes", 0) >= 2, "SAVE issued too few network writes")
        saved = work / "saved.img"
        extracted = work / "test.com"
        saved.write_bytes(volume)
        listing = subprocess.run(
            ["cpmls", "-f", "juku386", str(saved)], check=True,
            cwd=ROOT, stdout=subprocess.PIPE, text=True,
        ).stdout.lower()
        require("test.com" in listing, "remote SAVE did not create TEST.COM")
        subprocess.run(
            ["cpmcp", "-f", "juku386", str(saved), "0:TEST.COM", str(extracted)],
            check=True, cwd=ROOT,
        )
        require(extracted.stat().st_size == 256,
                f"remote TEST.COM is {extracted.stat().st_size} bytes")
        print("Remote persistence: PASS (TEST.COM is readable and 256 bytes)")
        run_smoke_case(trace, work)
    print("JUKU-NET-COSIM-CHECK: PASS")


if __name__ == "__main__":
    main()
