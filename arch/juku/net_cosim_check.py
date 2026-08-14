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
MODE2_SYSTEM = ROOT / "juku-net-mode2-system.bin"
MODE2_FLAT = ROOT / "juku-net-mode2.img"
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
FASTBOOT_STAGE1 = ROOT / "juku-fastboot-stage1.bin"
FASTBOOT_V2 = ROOT / "juku-fastboot-v2.bin"
FASTBOOT_V3 = ROOT / "juku-fastboot-v3.bin"
FASTBOOT_V4 = ROOT / "juku-fastboot-v4.bin"
FASTBOOT_V5 = ROOT / "juku-fastboot-v5.bin"
FLAT = ROOT / ".obj" / "arch" / "juku" / "+flatdiskimage" / \
    "arch" / "juku" / "+flatdiskimage.img"
sys.path.insert(0, str(COSIM / "tools"))

from janet_disk_server import juku_image_to_volume, serve_disk  # noqa: E402
from janet_fastboot import serve_fast  # noqa: E402
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


def parse_state(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text().splitlines()
        if "=" in line
    )


def run_fastboot_case(
    trace: Path, work: Path, *, version: int, faults: bool,
    force_rate_fallback: bool = False,
) -> None:
    """Run the real stage-1 code through stock Janet and the bulk protocol."""
    suffix = "fallback" if force_rate_fallback else \
        ("faults" if faults else "clean")
    case = work / f"fastboot-v{version}-{suffix}"
    case.mkdir()
    checkpoint = case / "checkpoint"
    master, slave = pty.openpty()
    tty.setraw(slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ="1700000",
        JUKU_TRACE_BANK="0",
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="TN0201",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
        JUKU_STOP_PC="0xCA00",
        JUKU_CHECKPOINT_PREFIX=str(checkpoint),
    )

    def inject(sequence: int, attempt: int, packet: bytes) -> bytes:
        if version in (3, 4, 5):
            if not faults:
                return packet
            if attempt == 0:
                damaged = bytearray(packet)
                damaged[100] ^= 1         # whole-stream CRC failure
                return bytes(damaged)
            if attempt == 1:
                return b""                # complete stream loss
            return packet
        if not faults or attempt:
            return packet
        if sequence == 2:
            damaged = bytearray(packet)
            damaged[100] ^= 1             # valid framing, invalid CRC
            return bytes(damaged)
        if sequence == 4:
            return b""                    # complete packet loss
        if sequence == 6:
            return packet + packet        # duplicate after a lost reply
        return packet

    lost_reply = False

    def receive_reply(
        sequence: int, attempt: int, _reply: tuple[int, int, int],
    ) -> bool:
        nonlocal lost_reply
        if version in (3, 4, 5):
            # The extension repeats its success frame three times. Lose the
            # first copy and prove that the host accepts a later copy without
            # needlessly retransmitting a stream to a target already in CP/M.
            success_sequence = 4 if version == 4 else 0
            if faults and sequence == success_sequence and attempt == 2 \
                    and not lost_reply:
                lost_reply = True
                return False
            return True
        # Lose one valid block ACK at the host. Its retransmit is a duplicate,
        # which the target must verify and ACK without advancing twice.
        return not (faults and sequence == 8 and attempt == 0)

    def inject_extension(attempt: int, packet: bytes) -> bytes:
        if not faults or attempt:
            return packet
        damaged = bytearray(packet)
        damaged[50] ^= 1                  # Fletcher check must reject it
        return bytes(damaged)

    def filter_rate_probe(rate_flag: int, packet: bytes) -> bytes:
        if force_rate_fallback and rate_flag == 1:
            return b""
        return packet

    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        try:
            result = serve_fast(
                master,
                {
                    1: FASTBOOT_STAGE1,
                    2: FASTBOOT_V2,
                    3: FASTBOOT_V3,
                    4: FASTBOOT_V4,
                    5: FASTBOOT_V5,
                }[version].read_bytes(),
                MODE2_SYSTEM.read_bytes(),
                stock_timeout=120,
                reply_timeout=0.75 if version == 3 else 3,
                verbose=False,
                configure_rate=False, block_filter=inject,
                reply_filter=receive_reply,
                extension_filter=inject_extension,
                rate_probe_filter=filter_rate_probe,
            )
            process.wait(timeout=20)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    require(process.returncode == 0,
            f"fastboot faults={faults}: cosim exited {process.returncode}")
    state = parse_state(checkpoint.with_suffix(".state"))
    ram = checkpoint.with_suffix(".ram").read_bytes()
    expected = MODE2_SYSTEM.read_bytes()[0x0200:0x1C00]
    require(state.get("pc") == "CA00", "fastboot did not reach CP/M entry")
    require(state.get("port_18", "").split(",", 1)[0] == "last:04",
            "fastboot did not select D57 count 4")
    require(state.get("port_1B", "").split(",", 1)[0] == "last:15",
            "fastboot did not select D57 mode 2")
    require(ram[0xB400:0xCE00] == expected,
            "fastboot installed system is not byte-exact")
    if version in (3, 4, 5):
        expected_artifact = 512 if version == 4 else 384
        expected_extension = 384 if version == 4 else 256
        require(
            result["stage_bytes"] == 128
            and result["artifact_bytes"] == expected_artifact
            and result["extension_bytes"] == expected_extension,
            f"fastboot v{version} sizes changed: {result}",
        )
    else:
        require(result["stage_bytes"] <= 640,
                f"fastboot stage grew to {result['stage_bytes']} bytes")
    require(result["protocol_version"] == version,
            f"fastboot v{version} negotiated v{result['protocol_version']}")
    if faults:
        expected_retries = 2 if version in (3, 4, 5) else 3
        require(result["retries"] == expected_retries,
                f"corruption/loss retry count is {result['retries']}")
        if version in (3, 4, 5):
            require(result["extension_retries"] == 1,
                    f"corrupt v{version} extension was not retried once")
    else:
        require(result["retries"] == 0,
                f"clean fastboot retried {result['retries']} times")
        if version in (3, 4, 5):
            require(result["extension_retries"] == 0,
                    f"clean v{version} extension unexpectedly retried")
    if version == 4:
        expected_baud = 19200 if force_rate_fallback else 28800
        require(result["transfer_baud"] == expected_baud,
                f"v4 transfer baud is {result['transfer_baud']}")
        require(result["rate_fallback"] == int(force_rate_fallback),
                f"v4 fallback result is {result['rate_fallback']}")
        if force_rate_fallback:
            require(
                result["rate_failure_stage"] ==
                "probe-ack-or-final-ready-not-received",
                f"v4 fallback leg is {result['rate_failure_stage']}",
            )
    if version == 5:
        require(result["transfer_baud"] == 19200,
                f"v5 transfer baud is {result['transfer_baud']}")
        require(result["transfer_framing"] == "8N1",
                f"v5 framing is {result['transfer_framing']}")
        require(state.get("usart_mode") == "5E",
                "v5 did not restore 8O1 before CP/M")
        log = (case / "stderr.txt").read_text()
        require("x16 mode=4E" in log,
                "v5 did not exercise 19200/8N1 in the USART model")
    bulk_detail = "1x6656 stream" if version in (3, 4, 5) else \
        f"{result['blocks']}x512"
    rate_detail = f"rate={result['transfer_baud']}, " \
        if version == 4 else ""
    print(
        f"FASTBOOT V{version} {'FAULTS' if faults else 'CLEAN'}: PASS "
        f"(stage={result['stage_bytes']} bytes/"
        f"{result['stock_sent_frames']} stock frames, "
        f"bulk={bulk_detail}, {rate_detail}"
        f"retries={result['retries']})"
    )

def read_console_until(fd: int, marker: bytes, timeout: float) -> bytes:
    """Read an emulator console PTY until marker or raise with its transcript."""
    import select

    result = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if not ready:
            continue
        try:
            incoming = os.read(fd, 4096)
        except OSError:
            continue
        result.extend(incoming)
        if marker in result:
            return bytes(result)
    raise TimeoutError(
        f"console did not emit {marker!r}; transcript={bytes(result)!r}"
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
    case_name: str | None = None,
    expected_mode2: bool = False,
) -> tuple[bytearray, dict[str, int], str]:
    case = work / (case_name or command.split()[0].lower())
    case.mkdir()
    system = case / "system.bin"
    shutil.copyfile(system_source, system)
    if seed:
        seed_command(system, command)
    volume = bytearray(volume_source.read_bytes())
    master, slave = pty.openpty()
    tty.setraw(slave)
    console_master, console_slave = pty.openpty()
    tty.setraw(console_slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_CONSOLE_PTY=os.ttyname(console_slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_TRACE_BANK="0",
        JUKU_DISABLE_SETTLE="1",
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
        os.close(console_slave)
        result: dict[str, int] = {}
        disk_error: list[BaseException] = []
        try:
            boot = serve_boot(master, system.read_bytes(), timeout=120,
                              verbose=False)

            def disk_worker() -> None:
                try:
                    result.update(serve_disk(
                        master, volume, writable=command.startswith("SAVE "),
                        timeout=60, idle_timeout=None,
                        verbose=False,
                        stats=result,
                    ))
                except BaseException as error:
                    disk_error.append(error)

            worker = threading.Thread(target=disk_worker)
            worker.start()
            console = read_console_until(console_master, b"A>", 60)
            # Let the emulator stop at its character-console prompt oracle so
            # it writes the framebuffer and ordinary completion diagnostics.
            time.sleep(0.1)
            process.terminate()
            process.wait(timeout=5)
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
            os.close(console_master)

    require(process.returncode in (-15, 0),
            f"{command}: cosim exited {process.returncode}")
    require(all(isinstance(error, OSError) for error in disk_error),
            f"{command}: disk server failed: {disk_error!r}")
    require(boot["image_bytes"] == 6784, f"{command}: bootstrap size changed")
    log = (case / "stderr.txt").read_text()
    require("JUKU disk image" not in log, f"{command}: local FDC media was attached")
    require("D57 divisor=8 ->" in log,
            f"{command}: stock 9600 baud phase was not observed")
    if expected_mode2:
        require("D57 divisor=4 ->" in log,
                f"{command}: 19200/mode-2 takeover was not observed")
    else:
        require("D57 divisor=4 ->" not in log,
                f"{command}: unexpected 19200 baud takeover was observed")
    require(b"CP/Mish 2.2 Juku" in console and b"A>" in console,
            f"{command}: character-console prompt oracle was not met")
    vram_path = case / "vram.bin"
    digest = hashlib.sha256(vram_path.read_bytes()).hexdigest() \
        if vram_path.exists() else "terminated-at-console-prompt"
    if command in EXPECTED_VRAM and not expected_mode2:
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
        # Do not start the interactive command while WRCHR is still drawing
        # the first prompt.  The matrix-level '|' marker waits for the prompt
        # glyph in VRAM, just as a human waits for the cursor before typing.
        JUKU_KEYS="TN0201|",
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


def run_mode2_keyboard_case(trace: Path, work: Path) -> None:
    """Boot normally, then type DIR through the RomBios keyboard path."""
    case = work / "mode2-keyboard"
    case.mkdir()
    master, slave = pty.openpty()
    tty.setraw(slave)
    console_master, console_slave = pty.openpty()
    tty.setraw(console_slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_CONSOLE_PTY=os.ttyname(console_slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ="1700000",
        JUKU_DISABLE_SETTLE="1",
        JUKU_TRACE_BANK="0",
        # Wait for the first prompt glyph before allowing appended PTY input
        # to reach the matrix, just as an operator waits for the cursor.
        JUKU_KEYS="TN0201|",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
        JUKU_CHECKPOINT_PREFIX=str(case / "final"),
    )
    volume = bytearray(MODE2_FLAT.read_bytes())
    stats: dict[str, int] = {}
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        os.close(console_slave)
        serve_boot(
            master, MODE2_SYSTEM.read_bytes(), timeout=120, verbose=False,
        )
        disk_error: list[BaseException] = []

        def disk_worker() -> None:
            try:
                serve_disk(
                    master, volume, timeout=180, idle_timeout=None,
                    verbose=False, stats=stats,
                )
            except BaseException as error:
                disk_error.append(error)

        worker = threading.Thread(target=disk_worker)
        worker.start()
        first = read_console_until(console_master, b"A>", 120)
        os.write(console_master, b"DIR\r")
        second = read_console_until(console_master, b"A>", 120)
        process.terminate()
        process.wait(timeout=5)
        os.close(master)
        worker.join(timeout=3)
        os.close(console_master)
    log = (case / "stderr.txt").read_text()
    require(process.returncode in (-15, 0),
            "mode-2 keyboard cosim did not exit cleanly")
    require(b"CP/Mish 2.2 Juku" in first and b"DIR" in second,
            f"mode-2 keyboard did not echo DIR through the matrix: {second!r}")
    require(all(isinstance(error, OSError) for error in disk_error),
            f"mode-2 keyboard disk server failed: {disk_error!r}")
    require(stats.get("reads", 0) >= 34,
            f"mode-2 keyboard DIR issued too few reads: {stats}")
    require("D57 divisor=4" in log,
            "mode-2 keyboard did not run with high-speed disk")
    final_ram = (case / "final.ram").read_bytes()
    final_state = dict(
        line.split("=", 1)
        for line in (case / "final.state").read_text().splitlines()
        if "=" in line
    )
    require(final_ram[0xD79F:0xD7A4] == bytes.fromhex("e3 22 56 d4 e1"),
            "mode-2 BIOS modified the RomBios interrupt dispatcher")
    require(all(final_ram[address] == 0xC9
                for address in (0xD773, 0xD777, 0xD78F)),
            "mode-2 BIOS left a NetBios service vector installed")
    require(final_ram[0xD454] == 0xDF and
            final_state.get("pic_mask") == "DF",
            "mode-2 BIOS PIC hardware/shadow state differs from EKDOS")
    print(
        "Physical-keyboard network CP/M: PASS "
        f"(DIR consumed; reads={stats.get('reads', 0)}; RomBios scan serviced)"
    )


def run_native_drive_b_case(trace: Path, work: Path, game_image: Path) -> None:
    """Select, list, and execute a program from a native two-sided B:."""
    case = work / "native-drive-b"
    case.mkdir()
    master, slave = pty.openpty()
    tty.setraw(slave)
    console_master, console_slave = pty.openpty()
    tty.setraw(console_slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_CONSOLE_PTY=os.ttyname(console_slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ="1700000",
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="TN0201|",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
    )
    drive_a = bytearray(MODE2_FLAT.read_bytes())
    drive_b = juku_image_to_volume(game_image.read_bytes())
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
        serve_boot(master, MODE2_SYSTEM.read_bytes(), timeout=120, verbose=False)

        def disk_worker() -> None:
            try:
                serve_disk(
                    master, drive_a, drive_b=drive_b, timeout=180,
                    idle_timeout=None, verbose=False, stats=stats,
                )
            except BaseException as error:
                errors.append(error)

        worker = threading.Thread(target=disk_worker)
        worker.start()
        read_console_until(console_master, b"A>", 120)
        os.write(console_master, b"B:\r")
        switched = read_console_until(console_master, b"B>", 30)
        os.write(console_master, b"DIR\r")
        listing = read_console_until(console_master, b"B>", 60)
        before_game = stats.get("reads_b", 0)
        os.write(console_master, b"TETRIS\r")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and stats.get("reads_b", 0) <= before_game:
            time.sleep(0.05)
        time.sleep(1)
        process.terminate()
        process.wait(timeout=5)
        os.close(master)
        worker.join(timeout=3)
        os.close(console_master)
    require(process.returncode in (-15, 0),
            "native B: cosim did not exit cleanly")
    require(b"B>" in switched and b"TETRIS" in listing.upper(),
            f"native B: selection/listing failed: {switched!r} {listing!r}")
    require(stats.get("reads_b", 0) > before_game,
            f"TETRIS.COM did not load from B: {stats}")
    require(stats.get("writes_b", 0) == 0,
            f"read-only game disk received a successful write: {stats}")
    require(all(isinstance(error, OSError) for error in errors),
            f"native B: server failed: {errors!r}")
    print(
        "Native network B: PASS "
        f"(DIR + TETRIS load; B reads={stats.get('reads_b', 0)}; read-only)"
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
    parser.add_argument("--keyboard-only", action="store_true")
    parser.add_argument("--fastboot-only", action="store_true")
    parser.add_argument("--game-disk", type=Path,
                        help="physical 800 KiB .JUK image for native B: test")
    args = parser.parse_args()
    require(
        all(path.is_file() for path in (
            SYSTEM, FLAT, SMOKE_SYSTEM, SMOKE_FLAT,
            MODE2_SYSTEM, MODE2_FLAT,
            BAUDTEST_SYSTEM, BAUDTEST_9600_FLAT, BAUDTEST_8N1_FLAT,
            BAUDTEST_LADDER_FLAT, BAUDTEST2_SYSTEM, BAUDTEST2_FLAT,
            MODE2_SOAK_SYSTEM, MODE2_SOAK_FLAT,
            FASTBOOT_STAGE1, FASTBOOT_V2, FASTBOOT_V3, FASTBOOT_V4,
            FASTBOOT_V5,
        )),
        "build the normal, smoke, and baud-test network images first",
    )
    with tempfile.TemporaryDirectory(prefix="cpmish-juku-net.") as name:
        work = Path(name)
        trace = work / "trace"
        build_trace(trace)
        if args.fastboot_only:
            for version in (1, 2, 3, 4, 5):
                run_fastboot_case(trace, work, version=version, faults=False)
                run_fastboot_case(trace, work, version=version, faults=True)
            run_fastboot_case(
                trace, work, version=4, faults=False,
                force_rate_fallback=True,
            )
            print("JUKU-FASTBOOT-COSIM-CHECK: PASS")
            return
        if args.keyboard_only:
            run_mode2_keyboard_case(trace, work)
            if args.game_disk:
                run_native_drive_b_case(trace, work, args.game_disk)
            return
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
        run_case(
            trace, work, "DIR", system_source=MODE2_SYSTEM,
            volume_source=MODE2_FLAT, case_name="dir-mode2",
            expected_mode2=True,
        )
        run_mode2_keyboard_case(trace, work)
        if args.game_disk:
            run_native_drive_b_case(trace, work, args.game_disk)
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
        for version in (1, 2, 3, 4, 5):
            run_fastboot_case(trace, work, version=version, faults=False)
            run_fastboot_case(trace, work, version=version, faults=True)
        run_fastboot_case(
            trace, work, version=4, faults=False,
            force_rate_fallback=True,
        )
    print("JUKU-NET-COSIM-CHECK: PASS")


if __name__ == "__main__":
    main()
