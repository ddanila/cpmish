#!/usr/bin/env python3
"""Prove diskless CP/M boot, reads, and writes through Janet/USART."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tty

from cosim_check import build_trace, require, seed_command


ROOT = Path(__file__).resolve().parents[2]
COSIM = Path(os.environ.get("JUKU_COSIM_ROOT", ROOT.parent / "8080-cosim"))
ROM = COSIM / "roms" / "ekta37.bin"
SYSTEM = ROOT / "juku-net-system.bin"
SMOKE_SYSTEM = ROOT / "juku-net-smoke-system.bin"
SMOKE_FLAT = ROOT / "juku-net-smoke.img"
BAUDTEST_SYSTEM = ROOT / "juku-net-baudtest-system.bin"
BAUDTEST_9600_FLAT = ROOT / "juku-net-baudtest-9600.img"
BAUDTEST_8N1_FLAT = ROOT / "juku-net-baudtest-8n1.img"
BAUDTEST_LADDER_FLAT = ROOT / "juku-net-baudtest-ladder.img"
BAUDTEST2_SYSTEM = ROOT / "juku-net-baudtest2-system.bin"
BAUDTEST2_FLAT = ROOT / "juku-net-baudtest2.img"
MODE2_SOAK_SYSTEM = ROOT / "juku-net-mode2-soak-system.bin"
MODE2_SOAK_FLAT = ROOT / "juku-net-mode2-soak.img"
FLAT = ROOT / ".obj" / "arch" / "juku" / "+flatdiskimage" / \
    "arch" / "juku" / "+flatdiskimage.img"
sys.path.insert(0, str(COSIM / "tools"))

from janet_disk_server import serve_disk  # noqa: E402
from janet_netboot import serve as serve_boot  # noqa: E402


EXPECTED_VRAM = {
    "DIR": "6d481b078a839616465594bb578023cda44f46b7da1c46534848c3e13b7a7d37",
    "SAVE 1 TEST.COM": "9b6c436386759dae43250166339e70b6de78771932b188e78b5495592de86db6",
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
    require("D57 divisor=8 ->" in log,
            f"{command}: stock 9600 baud phase was not observed")
    require("D57 divisor=4 ->" not in log,
            f"{command}: unexpected 19200 baud takeover was observed")
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


def run_mode2_soak_case(trace: Path, work: Path) -> None:
    """Exercise the physical experiment image at 19,200/mode 2."""
    case = work / "mode2-soak"
    case.mkdir()
    master, slave = pty.openpty()
    tty.setraw(slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ="1700000",
        JUKU_DISABLE_SETTLE="1",
        JUKU_TRACE_BANK="0",
        # Cosim intentionally models the keyboard configuration bank open,
        # so exercise NetBios's N=/S= fallback. Configured physical machines
        # such as CS00014 need only T,N.
        JUKU_KEYS="TN0201",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
    )
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        host = subprocess.run(
            [
                sys.executable,
                str(COSIM / "tools" / "janet_mode2_soak.py"),
                "--no-termios", "--client", "1",
                "--result", str(case / "result.json"),
                f"fd:{master}", str(MODE2_SOAK_SYSTEM), str(MODE2_SOAK_FLAT),
            ],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=180, pass_fds=(master,),
        )
        time.sleep(0.05)
        process.terminate()
        process.wait(timeout=5)
        os.close(master)
    require(host.returncode == 0, f"mode-2 soak host failed:\n{host.stdout}")
    result = json.loads((case / "result.json").read_text())
    require(result["status"] == "complete" and result["pass"] is True,
            f"mode-2 soak did not complete: {result}")
    require(result["disk"]["writes"] >= 64,
            f"mode-2 soak issued too few writes: {result}")
    require(result["disk"]["reads"] >= 64,
            f"mode-2 soak issued too few reads: {result}")
    log = (case / "stderr.txt").read_text()
    require("D57 divisor=8" in log and "D57 divisor=4" in log,
            "mode-2 soak did not switch from 9600 bootstrap to 19,200")
    print(
        "Monitorless 19,200/mode-2 soak: PASS "
        f"(reads={result['disk']['reads']}, writes={result['disk']['writes']}; "
        "8 KiB byte-verified; success marker received)"
    )


def run_baudtest_case(
    trace: Path, work: Path, *, test_baud: int, volume_source: Path,
    test_parity: str = "odd", truncate_case: int | None = None,
) -> None:
    """Run the exact automatic live-rate utility against the ideal USART model."""
    suffix = "" if truncate_case is None else f"-truncate-{truncate_case}"
    case = work / f"baudtest-{test_baud}-{test_parity}{suffix}"
    case.mkdir()
    master, slave = pty.openpty()
    tty.setraw(slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ=os.environ.get(
            "JUKU_BAUDTEST_CPU_HZ", "1700000"
        ),
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="TN0201",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
    )
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        host_command = [
            sys.executable, str(COSIM / "tools" / "janet_baud_test.py"),
            "--no-resume", "--no-termios",
            "--test-baud", str(test_baud),
            "--test-parity", test_parity,
            "--result", str(case / "result.json"),
            f"fd:{master}", str(BAUDTEST_SYSTEM), str(volume_source),
        ]
        try:
            host_environment = os.environ.copy()
            if truncate_case is not None:
                host_environment["JUKU_BAUDTEST_TRUNCATE_CASE"] = str(
                    truncate_case
                )
            host = subprocess.run(
                host_command, cwd=ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, timeout=120,
                pass_fds=(master,), env=host_environment,
            )
        except subprocess.TimeoutExpired as error:
            output = error.stdout or b""
            if isinstance(output, bytes):
                output = output.decode(errors="replace")
            raise AssertionError(f"BAUDTEST host timed out:\n{output}") from error
        time.sleep(0.05)
        process.terminate()
        process.wait(timeout=5)
        os.close(master)
    expected_returncode = 0 if truncate_case is None else 1
    if host.returncode != expected_returncode:
        io_tail = [
            line for line in (case / "stderr.txt").read_text().splitlines()
            if "port=0x08" in line or "port=0x09" in line
            or "D57 divisor=" in line
        ][-120:]
        require(False, f"BAUDTEST host exit {host.returncode}, expected "
                f"{expected_returncode}:\n{host.stdout}\n"
                f"Final USART trace:\n" + "\n".join(io_tail))
    result = json.loads((case / "result.json").read_text())
    receive_cases = result["host_to_juku"]
    require(len(receive_cases) == 11,
            f"BAUDTEST case count failed: {receive_cases}")
    if truncate_case is None:
        require(result["pass"] is True and
                all(row["pass"] is True for row in receive_cases),
                f"BAUDTEST receive sweep failed: {receive_cases}")
    else:
        failed = receive_cases[truncate_case]
        require(result["pass"] is False and failed["pass"] is False and
                failed["protocol"] == 1 and
                all(row["pass"] is True
                    for index, row in enumerate(receive_cases)
                    if index != truncate_case) and
                result["juku_to_host"]["packet_ok"] is True and
                result["return_handshake"] == "440121",
                f"BAUDTEST did not recover from truncation: {result}")
    log = (case / "stderr.txt").read_text()
    expected_divisor = 4 if test_baud == 19200 else 8
    cpu_hz = int(os.environ.get("JUKU_BAUDTEST_CPU_HZ", "1700000"), 0)
    expected_cycles = cpu_hz * 11 * 16 * expected_divisor * 13 // 16_000_000
    require(
        f"D57 divisor={expected_divisor} -> byte_cycles={expected_cycles} "
        "x16" in log,
        f"BAUDTEST did not exercise nominal {test_baud}",
    )
    restore_cycles = cpu_hz * 11 * 16 * 8 * 13 // 16_000_000
    require(f"D57 divisor=8 -> byte_cycles={restore_cycles}" in log,
            "BAUDTEST did not restore nominal 9600")
    if truncate_case is None:
        print(
            f"Bidirectional BAUDTEST: PASS "
            f"(unpaced 1..133 + paced 133 host bytes; "
            f"133 reverse bytes at nominal {test_baud})"
        )
    else:
        print(
            f"Recoverable BAUDTEST: PASS (case {truncate_case} truncated; "
            f"later cases and 9600 return survived)"
        )


def run_baudtest_ladder_case(trace: Path, work: Path) -> None:
    """Run the single-boot CP2102-native x1-rate ladder end to end."""
    case = work / "baudtest-ladder"
    case.mkdir()
    master, slave = pty.openpty()
    tty.setraw(slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ="1700000",
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="TN0201",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
    )
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        host = subprocess.run(
            [
                sys.executable,
                str(COSIM / "tools" / "janet_baud_ladder.py"),
                "--no-termios", "--result", str(case / "result.json"),
                f"fd:{master}", str(BAUDTEST_SYSTEM),
                str(BAUDTEST_LADDER_FLAT),
            ],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=180, pass_fds=(master,),
        )
        time.sleep(0.05)
        process.terminate()
        process.wait(timeout=5)
        os.close(master)
    require(host.returncode == 0,
            f"BAUDTEST ladder host failed:\n{host.stdout}")
    result = json.loads((case / "result.json").read_text())
    rates = result["rates"]
    require(
        result["pass"] is True and
        [row["divisor"] for row in rates] == [85, 77, 64] and
        [row["host_baud"] for row in rates] == [14400, 16000, 19200] and
        all(row["clock_factor"] == 1 for row in rates) and
        all(len(row["host_to_juku"]) == 11 and row["pass"] is True
            for row in rates),
        f"BAUDTEST ladder result failed: {result}",
    )
    log = (case / "stderr.txt").read_text()
    require(
        all(f"D57 divisor={divisor} ->" in log for divisor in (85, 77, 64))
        and all(f"x1 mode=5D" in line for line in [
            next((candidate for candidate in log.splitlines()
                  if f"D57 divisor={divisor} ->" in candidate
                  and "mode=5D" in candidate), "")
            for divisor in (85, 77, 64)
        ])
        and "D57 divisor=8 ->" in log,
        "BAUDTEST ladder did not exercise x1 divisors 85/77/64 and restore 8",
    )
    print(
        "Bidirectional BAUDTEST ladder: PASS "
        "(single boot; 14400/16000/19200 at 8251 x1; "
        "11 cases each; restore 9600/x16)"
    )


def run_baudtest2_case(
    trace: Path, work: Path, *, truncate_case: int | None = None,
) -> None:
    """Run the resilient pattern/history/clock-shape matrix end to end."""
    suffix = "" if truncate_case is None else f"-truncate-{truncate_case}"
    case = work / f"baudtest2{suffix}"
    case.mkdir()
    master, slave = pty.openpty()
    tty.setraw(slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ="1700000",
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="TN0201",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
    )
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        host_environment = os.environ.copy()
        if truncate_case is not None:
            host_environment["JUKU_BAUDTEST2_TRUNCATE"] = str(truncate_case)
        host = subprocess.run(
            [
                sys.executable,
                str(COSIM / "tools" / "janet_baud_test2.py"),
                "--no-termios", "--result", str(case / "result.json"),
                f"fd:{master}", str(BAUDTEST2_SYSTEM), str(BAUDTEST2_FLAT),
            ],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=240, pass_fds=(master,), env=host_environment,
        )
        time.sleep(0.05)
        process.terminate()
        process.wait(timeout=5)
        os.close(master)
    require(host.returncode == 0, f"BAUDTEST2 host failed:\n{host.stdout}")
    result = json.loads((case / "result.json").read_text())
    reports = result["cases"]
    require(
        result["status"] == "complete" and result["restored_9600"] is True
        and len(reports) == 68
        and [sum(row["stage"] == stage for row in reports)
             for stage in range(3)] == [59, 3, 6]
        and (
            (truncate_case is None and result["pass"] is True
             and all(row["pass"] is True for row in reports))
            or (truncate_case is not None and result["pass"] is False
                and reports[truncate_case]["pass"] is False
                and reports[truncate_case]["protocol"] == 1
                and all(row["pass"] is True
                        for index, row in enumerate(reports)
                        if index != truncate_case))
        ),
        f"BAUDTEST2 matrix failed: {result}",
    )
    log = (case / "stderr.txt").read_text()
    require(
        "D57 divisor=4" in log and "x16 mode=5E" in log
        and "D57 divisor=2" in log and "x64 mode=5F" in log
        and "D57 divisor=8" in log,
        "BAUDTEST2 did not exercise 19200/x16, valid 9600/x64, and restore",
    )
    if truncate_case is None:
        print(
            "Resilient BAUDTEST2: PASS (68 cases; pattern/repetition/idle/"
            "preamble/chunking + x64/9600 + mode-2/19200; restored 9600)"
        )
    else:
        print(
            f"Resilient BAUDTEST2 recovery: PASS (case {truncate_case} "
            "truncated; remaining matrix completed; restored 9600)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baudtest-only", action="store_true")
    args = parser.parse_args()
    require(
        all(path.is_file() for path in (
            SYSTEM, FLAT, SMOKE_SYSTEM, SMOKE_FLAT,
            BAUDTEST_SYSTEM, BAUDTEST_9600_FLAT, BAUDTEST_8N1_FLAT,
            BAUDTEST_LADDER_FLAT, BAUDTEST2_SYSTEM, BAUDTEST2_FLAT,
            MODE2_SOAK_SYSTEM, MODE2_SOAK_FLAT,
        )),
        "build the normal, smoke, and baud-test network images first",
    )
    with tempfile.TemporaryDirectory(prefix="cpmish-juku-net.") as name:
        work = Path(name)
        trace = work / "trace"
        build_trace(trace)
        if args.baudtest_only:
            run_baudtest_case(
                trace, work, test_baud=9600,
                volume_source=BAUDTEST_9600_FLAT,
            )
            run_baudtest_case(
                trace, work, test_baud=19200, volume_source=SMOKE_FLAT,
            )
            run_baudtest_case(
                trace, work, test_baud=19200, test_parity="none",
                volume_source=BAUDTEST_8N1_FLAT,
            )
            run_baudtest_case(
                trace, work, test_baud=19200, volume_source=SMOKE_FLAT,
                truncate_case=7,
            )
            run_baudtest_ladder_case(trace, work)
            run_baudtest2_case(trace, work)
            run_baudtest2_case(trace, work, truncate_case=7)
            print("JUKU-NET-BAUDTEST-CHECK: PASS")
            return
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
        run_mode2_soak_case(trace, work)
        run_baudtest_case(
            trace, work, test_baud=9600,
            volume_source=BAUDTEST_9600_FLAT,
        )
        run_baudtest_case(
            trace, work, test_baud=19200, volume_source=SMOKE_FLAT,
        )
        run_baudtest_case(
            trace, work, test_baud=19200, test_parity="none",
            volume_source=BAUDTEST_8N1_FLAT,
        )
        run_baudtest_case(
            trace, work, test_baud=19200, volume_source=SMOKE_FLAT,
            truncate_case=7,
        )
        run_baudtest_ladder_case(trace, work)
        run_baudtest2_case(trace, work)
        run_baudtest2_case(trace, work, truncate_case=7)
    print("JUKU-NET-COSIM-CHECK: PASS")


if __name__ == "__main__":
    main()
