#!/usr/bin/env python3
"""Boot non-banked CP/M Plus through Ekta4402 and exercise NetDisk."""

from __future__ import annotations

import os
from pathlib import Path
import pty
import subprocess
import sys
import tempfile
import threading
import time
import tty

from cosim_check import build_trace, require
from net_cosim_check import read_console_until


ROOT = Path(__file__).resolve().parents[2]
COSIM = Path(os.environ.get("JUKU_COSIM_ROOT", ROOT.parent / "8080-cosim"))
ROM = COSIM / "spinoffs" / "jukuravi" / "remix" / "ekta4402.bin"
SYSTEM = ROOT / "juku-cpm3-system.bin"
FASTBOOT = ROOT / "juku-fastboot-v15-cpm3.bin"
VOLUME = ROOT / "juku-cpm3.img"
sys.path.insert(0, str(COSIM / "tools"))

from janet_disk_server import serve_disk  # noqa: E402
from janet_fastboot import serve_fast  # noqa: E402


def run(trace: Path, work: Path) -> None:
    container = SYSTEM.read_bytes()
    require(
        container[:8] == b"JUKURM1\x1a"
        and container[8:16][:4] == bytes.fromhex("00 70 00 9c")
        and int.from_bytes(container[12:14], "little") == 0x4000,
        "CP/M Plus RAM container has an unexpected layout",
    )
    resident = container[512:]
    conout_vector = 0xA000 - 0x7000 + 0x000C
    require(resident[conout_vector] == 0xC3,
            "CP/M Plus adapter CONOUT vector is not a JMP")
    conout_pc = int.from_bytes(
        resident[conout_vector + 1:conout_vector + 3], "little",
    )

    case = work / "cpm3-direct"
    case.mkdir()
    master, slave = pty.openpty()
    tty.setraw(slave)
    console_master, console_slave = pty.openpty()
    tty.setraw(console_slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_CONSOLE_PTY=os.ttyname(console_slave),
        JUKU_CONSOLE_OUT_PC=f"0x{conout_pc:04X}",
        JUKU_CONSOLE_OUT_REGISTER="C",
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ="1700000",
        JUKU_TRACE_BANK="1",
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="N",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
        JUKU_CHECKPOINT_PREFIX=str(case / "final"),
    )
    volume = bytearray(VOLUME.read_bytes())
    stats: dict[str, int] = {}
    errors: list[BaseException] = []
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        os.close(console_slave)
        try:
            boot = serve_fast(
                master, FASTBOOT.read_bytes(), container,
                stock_timeout=120, reply_timeout=8, verbose=False,
                configure_rate=False, direct_core=True,
            )

            def disk_worker() -> None:
                try:
                    serve_disk(
                        master, volume, timeout=180, idle_timeout=None,
                        verbose=False, stats=stats, protocol_version=3,
                        resume=True,
                    )
                except BaseException as error:
                    errors.append(error)

            worker = threading.Thread(target=disk_worker)
            worker.start()
            first = read_console_until(
                console_master, b"A>",
                float(os.environ.get("JUKU_CPM3_PROMPT_TIMEOUT", "120")),
            )
            os.write(console_master, b"DIR\r")
            second = read_console_until(console_master, b"A>", 120)
            os.write(console_master, b"DIAG CPU\r")
            third = read_console_until(console_master, b"A>", 120)
            time.sleep(0.1)
            process.terminate()
            process.wait(timeout=5)
            os.close(master)
            worker.join(timeout=3)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            try:
                os.close(master)
            except OSError:
                pass
            os.close(console_master)

    require(boot["direct_core"] == 1 and boot["stock_sent_frames"] == 0,
            f"CP/M Plus did not use direct ROM fastboot: {boot}")
    require(b"CP/M Plus" in first or b"CP/M Version 3" in first,
            f"CP/M Plus banner is missing: {first!r}")
    require(b"DIR" in second and b"CCP" in second,
            f"CP/M Plus network DIR failed: {second!r}")
    require(b"DIAG CPU" in third and b"CPU: PASS" in third,
            f"CP/M Plus transient diagnostic failed: {third!r}")
    require(stats.get("reads", 0) >= 1,
            f"CP/M Plus issued no NetDisk reads: {stats}")
    require(all(isinstance(error, OSError) for error in errors),
            f"CP/M Plus disk server failed: {errors!r}")
    state = dict(
        line.split("=", 1)
        for line in (case / "final.state").read_text().splitlines()
        if "=" in line
    )
    require(state.get("mode") == "3" and state.get("pic_mask") == "FF",
            f"CP/M Plus did not retain the all-RAM state: {state}")
    require(state.get("usart_mode") == "5E",
            "CP/M Plus adapter did not select NetDisk 8O1 framing")
    print(
        "JUKU CP/M PLUS 3.1: PASS "
        f"(direct Ekta4402 boot, A>, DIR, DIAG CPU, reads={stats['reads']})"
    )


def main() -> None:
    for path in (ROM, SYSTEM, FASTBOOT, VOLUME):
        require(path.is_file(), f"build input is missing: {path}")
    retained = os.environ.get("JUKU_CPM3_WORK")
    if retained:
        work = Path(retained)
        work.mkdir(parents=True, exist_ok=True)
        trace = work / "trace"
        build_trace(trace)
        run(trace, work)
        return
    with tempfile.TemporaryDirectory(prefix="cpmish-juku-cpm3.") as name:
        work = Path(name)
        trace = work / "trace"
        build_trace(trace)
        run(trace, work)


if __name__ == "__main__":
    main()
