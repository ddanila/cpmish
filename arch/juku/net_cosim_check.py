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
import termios
import tty

from cosim_check import build_trace, require, seed_command


ROOT = Path(__file__).resolve().parents[2]
COSIM = Path(os.environ.get("JUKU_COSIM_ROOT", ROOT.parent / "8080-cosim"))
ROM = COSIM / "roms" / "ekta37.bin"
DIRECT_ROM = COSIM / "spinoffs" / "jukuravi" / "remix" / "ekta4402.bin"
SYSTEM = ROOT / "juku-net-system.bin"
MODE2_SYSTEM = ROOT / "juku-net-mode2-system.bin"
BROKEN_MODE2_SYSTEM = ROOT / "juku-net-mode2-broken-system.bin"
MODE2_FLAT = ROOT / "juku-net-mode2.img"
NETDISK_V2_SYSTEM = ROOT / "juku-net-v2-system.bin"
RAMOUT_SYSTEM = ROOT / "juku-net-v2-ramout-system.bin"
RAMBIOS_SYSTEM = ROOT / "juku-net-v2-rambio-system.bin"
RAMBIOS_V3_SYSTEM = ROOT / "juku-net-v3-rambio-system.bin"
COMMON_TOOLS = ROOT / "third_party" / "juku-common" / "tools"
sys.path.insert(0, str(COMMON_TOOLS))
from ram_console_oracle import (  # noqa: E402
    load_assembly as load_console_assembly_font,
    load_reference as load_console_reference_font,
    render_transcript as render_source_console,
)
NETDISK_V2_FLAT = ROOT / "juku-net-v2.img"
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
FASTBOOT_V6 = ROOT / "juku-fastboot-v6.bin"
FASTBOOT_V7 = ROOT / "juku-fastboot-v7.bin"
FASTBOOT_V8 = ROOT / "juku-fastboot-v8.bin"
FASTBOOT_V9 = ROOT / "juku-fastboot-v9.bin"
FASTBOOT_V10 = ROOT / "juku-fastboot-v10.bin"
FASTBOOT_V11 = ROOT / "juku-fastboot-v11.bin"
FASTBOOT_V12 = ROOT / "juku-fastboot-v12.bin"
FASTBOOT_V13 = ROOT / "juku-fastboot-v13.bin"
FASTBOOT_V14 = ROOT / "juku-fastboot-v14.bin"
FASTBOOT_V14_NETDISK_V2 = ROOT / "juku-fastboot-v14-netdisk-v2.bin"
FASTBOOT_V15_RAMBIOS = ROOT / "juku-fastboot-v15-rambio.bin"
FASTBOOT_V15_NETDISK_V3 = ROOT / "juku-fastboot-v15-netdisk-v3.bin"
DIAG_COM = ROOT / ".obj" / "arch" / "juku" / "+diag" / "diag.cim"
FLAT = ROOT / ".obj" / "arch" / "juku" / "+flatdiskimage" / \
    "arch" / "juku" / "+flatdiskimage.img"
sys.path.insert(0, str(COSIM / "tests" / "fixtures"))

from legacy_janet_disk_server import (  # noqa: E402
    boot_with_recovery,
    juku_image_to_volume,
    serve_disk,
)
from legacy_janet_fastboot import serve_fast  # noqa: E402
from legacy_janet_netboot import serve as serve_boot  # noqa: E402


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
FASTBOOT_BYTE_CYCLES = 884
FASTBOOT_V7_TAIL_CYCLES = 1_010_204
FASTBOOT_V8_TAIL_CYCLES = 203_037
FASTBOOT_V8_MARKER_GAP_CYCLES = 3_400


def parse_state(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text().splitlines()
        if "=" in line
    )


def run_fastboot_case(
    trace: Path, work: Path, *, version: int, faults: bool,
    force_rate_fallback: bool = False,
    low_latency_guards: bool = False,
    cpu_hz: int = 1_700_000,
    rx_irq_delay: bool = False,
) -> None:
    """Run the real stage-1 code through stock Janet and the bulk protocol."""
    suffix = "fallback" if force_rate_fallback else \
        ("faults" if faults else "clean")
    if low_latency_guards:
        suffix += "-low-latency"
    if cpu_hz != 1_700_000:
        suffix += f"-{cpu_hz}hz"
    if rx_irq_delay:
        suffix += "-rx-irq-delay"
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
        JUKU_USART_PIT_CPU_HZ=str(cpu_hz),
        JUKU_TRACE_BANK="0",
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="TN0201",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
        JUKU_STOP_PC="0xC600" if version == 15 else "0xCA00",
        JUKU_CHECKPOINT_PREFIX=str(checkpoint),
    )
    if rx_irq_delay:
        # Defer one interrupt for more than two 19,200-baud characters after
        # the bulk stream begins. V13 must detect the resulting overrun and
        # recover; V14's polling receive path must remain unaffected.
        environment["JUKU_USART_FAULT"] = \
            "rx_irq_delay_once_after:900:2000"

    def inject(sequence: int, attempt: int, packet: bytes) -> bytes:
        if version in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
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
        if version in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
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

    def inject_extension_header(
        _attempt: int, probe: int, packet: bytes,
    ) -> bytes:
        # Model the physical rate-transition boundary by delivering only A5
        # from the first V12 header. The next zero/A5/3A probe must release
        # the overlap-safe core parser without sending any extension body.
        return packet[:1] \
            if version in (12, 13, 14, 15) and probe == 0 else packet

    def inject_stream_header(
        _attempt: int, probe: int, packet: bytes,
    ) -> bytes:
        return packet[:1] if version in (13, 14, 15) and probe == 0 else packet

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
                    6: FASTBOOT_V6,
                    7: FASTBOOT_V7,
                    8: FASTBOOT_V8,
                    9: FASTBOOT_V9,
                    10: FASTBOOT_V10,
                    11: FASTBOOT_V11,
                    12: FASTBOOT_V12,
                    13: FASTBOOT_V13,
                    14: FASTBOOT_V14,
                    15: FASTBOOT_V15_RAMBIOS,
                }[version].read_bytes(),
                (RAMBIOS_SYSTEM if version == 15 else MODE2_SYSTEM).read_bytes(),
                stock_timeout=120,
                reply_timeout=0.75 if version == 3 else 3,
                verbose=os.environ.get("JUKU_COSIM_VERBOSE") == "1",
                configure_rate=False, block_filter=inject,
                reply_filter=receive_reply,
                extension_filter=inject_extension,
                extension_header_filter=inject_extension_header,
                stream_header_filter=inject_stream_header,
                rate_probe_filter=filter_rate_probe,
                compact_stock_execute=(version in (
                    8, 9, 10, 11, 12, 13, 14, 15,
                )),
                low_latency_guards=low_latency_guards,
            )
            process.wait(timeout=20)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            os.close(master)

    require(process.returncode == 0,
            f"fastboot faults={faults}: cosim exited {process.returncode}")
    state = parse_state(checkpoint.with_suffix(".state"))
    ram = checkpoint.with_suffix(".ram").read_bytes()
    if version == 15:
        expected = RAMBIOS_SYSTEM.read_bytes()[0x0200:]
        expected_start = 0xB000
        expected_pc = "C600"
    else:
        expected = MODE2_SYSTEM.read_bytes()[0x0200:0x1C00]
        expected_start = 0xB400
        expected_pc = "CA00"
    require(state.get("pc") == expected_pc,
            "fastboot did not reach CP/M entry")
    require(state.get("port_18", "").split(",", 1)[0] == "last:04",
            "fastboot did not select D57 count 4")
    require(state.get("port_1B", "").split(",", 1)[0] == "last:15",
            "fastboot did not select D57 mode 2")
    require(ram[expected_start:expected_start + len(expected)] == expected,
            "fastboot installed system is not byte-exact")
    if rx_irq_delay:
        require(
            state.get("usart_rx_irq_delay_once_fired") == "1",
            "requested USART Rx IRQ delay did not fire",
        )
    if version in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
        expected_artifact = {
            3: 384,
            4: 512,
            5: 384,
            6: 5342,
            7: 5218,
            8: 5602,
            9: 5518,
            10: 5570,
            11: 5570,
            12: 5570,
            13: 5582,
            14: 5229,
            15: 6375,
        }[version]
        expected_extension = {
            4: 384,
            6: 384,
            8: 640,
            9: 556,
            10: 608,
            11: 608,
            12: 608,
            13: 620,
            14: 267,
            15: 267,
        }.get(version, 256)
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
    if version in (8, 9, 10, 11, 12, 13, 14, 15):
        require(
            result["stock_sent_frames"] ==
            14 + 2 * result["stock_ack_09"]
            and result["stock_compact_execute"] == 1
            and result["stock_execute_service_bytes"] == 1,
            f"fastboot v{version} compact stock execute changed: {result}",
        )
    if low_latency_guards:
        require(
            version in (9, 10, 11, 12, 13, 14, 15)
            and result["low_latency_guards"] == 1
            and result["turnaround_guard_ms"] == 20
            and result["stock_handoff"] == "tcdrain"
            and result["stock_handoff_guard_ms"] == 30
            and result["success_guard_ms"] == 10,
            f"fastboot low-latency policy changed: {result}",
        )
    if faults:
        expected_retries = 2 \
            if version in (
                3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
            ) else 3
        require(result["retries"] == expected_retries,
                f"corruption/loss retry count is {result['retries']}")
        if version in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
            require(result["extension_retries"] == 1,
                    f"corrupt v{version} extension was not retried once")
    else:
        expected_clean_retries = 1 \
            if rx_irq_delay and version == 13 else 0
        require(
            result["retries"] == expected_clean_retries,
            f"clean fastboot retry count is {result['retries']}, expected "
            f"{expected_clean_retries}",
        )
        if version in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
            require(result["extension_retries"] == 0,
                    f"clean v{version} extension unexpectedly retried")
    if version in (11, 12, 13, 14, 15):
        expected_header_acks = 2 if faults else 1
        require(
            result["extension_header_acks"] == expected_header_acks,
            f"v{version} core-header ACK count differs: {result}",
        )
        if version in (12, 13, 14, 15):
            require(
                result["extension_header_probes"] == 2 * expected_header_acks,
                f"v{version} partial extension-header recovery changed: "
                f"{result}",
            )
    if version in (13, 14, 15):
        expected_stream_acks = 2 \
            if faults or (rx_irq_delay and version == 13) else 1
        expected_stream_probes = 2 * expected_stream_acks
        require(
            result["stream_header_acks"] == expected_stream_acks
            and (
                result["stream_header_probes"] >= expected_stream_probes
                if rx_irq_delay and version == 13
                else result["stream_header_probes"] == expected_stream_probes
            ),
            f"v{version} partial stream-header recovery changed: {result}",
        )
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
    if version in (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
        require(result["transfer_baud"] == 19200,
                f"v{version} transfer baud is {result['transfer_baud']}")
        require(result["transfer_framing"] == "8N1",
                f"v{version} framing is {result['transfer_framing']}")
        expected_mode = "4E" if version in (
            7, 8, 9, 10, 11, 12, 13, 14, 15,
        ) else "5E"
        require(state.get("usart_mode") == expected_mode,
                f"v{version} handoff USART mode is not {expected_mode}")
        log = (case / "stderr.txt").read_text()
        require("x16 mode=4E" in log,
                f"v{version} did not exercise 19200/8N1 in the USART model")
    if version in (6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
        expected_stream = 5972 if version == 15 else 4826
        require(result["stream_bytes"] == expected_stream,
                f"v{version} compressed stream is "
                f"{result['stream_bytes']} bytes")
    timing_detail = ""
    if version in (8, 9, 10, 11, 12, 13) and not faults \
            and not rx_irq_delay \
            and cpu_hz == 1_700_000:
        last_rx_cycle = int(state["usart_rx_next_cyc"]) - \
            FASTBOOT_BYTE_CYCLES
        tail_cycles = int(state["cyc"]) - last_rx_cycle
        extension_bytes = {
            8: 640, 9: 556, 10: 608, 11: 608, 12: 608, 13: 620,
        }[version]
        modeled_cost = (
            tail_cycles
            + (extension_bytes - 256) * FASTBOOT_BYTE_CYCLES
            + FASTBOOT_V8_MARKER_GAP_CYCLES
        )
        require(modeled_cost < FASTBOOT_V7_TAIL_CYCLES,
                f"fastboot v{version} no longer beats the v7 timing model")
        gain_ms = (
            FASTBOOT_V7_TAIL_CYCLES - modeled_cost
        ) / 1700
        timing_detail = (
            f", tail={tail_cycles}cyc, modeled-v7-gain={gain_ms:.0f}ms"
        )
        if version in (9, 10, 11, 12, 13):
            v8_cost = (
                FASTBOOT_V8_TAIL_CYCLES
                + (640 - 256) * FASTBOOT_BYTE_CYCLES
                + FASTBOOT_V8_MARKER_GAP_CYCLES
            )
            v8_gain_ms = (v8_cost - modeled_cost) / 1700
            require(v8_gain_ms > 0,
                    f"fastboot v{version} no longer beats v8: "
                    f"tail={tail_cycles}, cost={modeled_cost}, "
                    f"v8-cost={v8_cost}")
            timing_detail += f", modeled-v8-gain={v8_gain_ms:.0f}ms"
    bulk_detail = (
        f"1x{result['stream_bytes']} "
        f"{'ZX0 ' if version in (6, 7, 8, 9, 10, 11, 12, 13, 14, 15) else ''}stream"
        if version in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
        else f"{result['blocks']}x512"
    )
    rate_detail = f"rate={result['transfer_baud']}, " \
        if version == 4 else ""
    print(
        f"FASTBOOT V{version} {'FAULTS' if faults else 'CLEAN'}"
        f"{' LOW-LATENCY' if low_latency_guards else ''}: PASS "
        f"(stage={result['stage_bytes']} bytes/"
        f"{result['stock_sent_frames']} stock frames, "
        f"bulk={bulk_detail}, {rate_detail}"
        f"retries={result['retries']}"
        f"{f', cpu={cpu_hz}Hz' if cpu_hz != 1_700_000 else ''}"
        f"{', one-shot-rx-irq-delay' if rx_irq_delay else ''}"
        f"{timing_detail})"
    )


def run_fastboot_disk_case(
    trace: Path, work: Path, version: int, *, low_latency_guards: bool = False,
    netdisk_v3: bool = False,
    command: bytes = b"DIR",
    diag_cpu_fault: bool = False,
    drop_replies: int = 0,
    remote_console: bool = False,
    remote_console_drop_replies: int = 0,
    direct_core: bool = False,
) -> None:
    """Prove a compact fastboot's handoff through prompt and network DIR."""
    require(version in (7, 8, 9, 10, 11, 12, 13, 14, 15),
            f"unsupported compact fastboot v{version}")
    require(not direct_core or (version == 15 and netdisk_v3),
            "direct ROM core test requires V15/NetDisk v3")
    require(not direct_core or DIRECT_ROM.is_file(),
            f"direct fastboot ROM is missing: {DIRECT_ROM}")
    case = work / (
        f"fastboot-v{version}-network-dir"
        + ("-netdisk-v3" if netdisk_v3 else "")
        + ("-" + command.decode("ascii").lower().replace(" ", "-")
           if command != b"DIR" else "")
        + ("-cpu-a12-fault" if diag_cpu_fault else "")
        + (f"-drop-{drop_replies}-replies" if drop_replies else "")
        + ("-remote-console" if remote_console else "")
        + ("-direct-rom" if direct_core else "")
        + (f"-drop-{remote_console_drop_replies}" if
           remote_console_drop_replies else "")
        + ("-low-latency" if low_latency_guards else "")
    )
    case.mkdir()
    master, slave = pty.openpty()
    tty.setraw(slave)
    console_master, console_slave = pty.openpty()
    tty.setraw(console_slave)
    environment = os.environ.copy()
    if version == 15:
        resident = (
            RAMBIOS_V3_SYSTEM if netdisk_v3 else RAMBIOS_SYSTEM
        ).read_bytes()[512:]
        conout_vector = 0xC60C - 0xB000
        require(resident[conout_vector] == 0xC3,
                "V15 RAM BIOS CONOUT vector is not a JMP")
        conout_pc = int.from_bytes(
            resident[conout_vector + 1:conout_vector + 3], "little",
        )
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_CONSOLE_PTY=os.ttyname(console_slave),
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ="1700000",
        JUKU_TRACE_BANK="1" if version == 15 else "0",
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="N" if direct_core else
        ("TN0201" if version == 15 else "TN0201|"),
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
        JUKU_CHECKPOINT_PREFIX=str(case / "final"),
    )
    if diag_cpu_fault:
        require(version == 15 and command == b"DIAG CPU",
                "the controlled CPU fault requires V15 DIAG CPU")
        diagnostic = DIAG_COM.read_bytes()
        pair_signature = bytes.fromhex("01 ff 0f 03 78 fe 10")
        failure_signature = bytes.fromhex("3e 02 c9")
        pair_offset = diagnostic.find(pair_signature)
        failure_offset = diagnostic.find(failure_signature, pair_offset)
        require(pair_offset >= 0 and failure_offset >= 0,
                "cannot locate shared CPU pair test/failure return")
        environment.update(
            JUKU_CPU_A12_INCREMENT_FAULT_ARM_PC=f"0x{0x100 + pair_offset:04X}",
            JUKU_CPU_A12_INCREMENT_FAULT_ARM_BANK_MODE="3",
            JUKU_CPU_A12_INCREMENT_FAULT_DISARM_PC=(
                f"0x{0x100 + failure_offset:04X}"
            ),
        )
    if version == 15:
        environment.update(
            JUKU_CONSOLE_OUT_PC=f"0x{conout_pc:04X}",
            JUKU_CONSOLE_OUT_REGISTER="C",
        )
    volume = bytearray(
        (NETDISK_V2_FLAT if version == 15 else MODE2_FLAT).read_bytes(),
    )
    stats: dict[str, int] = {}
    errors: list[BaseException] = []
    remote_input = bytearray()
    remote_output = bytearray()
    drop_state = {"enabled": False, "count": 0}
    console_drop_state = {"enabled": False, "count": 0}

    def disk_reply_filter(_attempt: int, reply: bytes) -> bytes:
        if drop_state["enabled"] and drop_state["count"] < drop_replies:
            drop_state["count"] += 1
            return b""
        return reply

    def console_reply_filter(
        _attempt: int, _operation: int, reply: bytes,
    ) -> bytes:
        if console_drop_state["enabled"] and \
                console_drop_state["count"] < remote_console_drop_replies:
            console_drop_state["count"] += 1
            return b""
        return reply

    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(DIRECT_ROM if direct_core else ROM),
             "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        os.close(console_slave)
        try:
            result = serve_fast(
                master,
                {7: FASTBOOT_V7, 8: FASTBOOT_V8, 9: FASTBOOT_V9,
                 10: FASTBOOT_V10, 11: FASTBOOT_V11,
                 12: FASTBOOT_V12, 13: FASTBOOT_V13,
                 14: FASTBOOT_V14,
                 15: FASTBOOT_V15_NETDISK_V3 if netdisk_v3 else
                 FASTBOOT_V15_RAMBIOS}[
                    version
                ].read_bytes(),
                (RAMBIOS_V3_SYSTEM if netdisk_v3 else
                 RAMBIOS_SYSTEM if version == 15 else MODE2_SYSTEM).read_bytes(),
                stock_timeout=120, reply_timeout=8, verbose=False,
                configure_rate=False,
                compact_stock_execute=not direct_core and (version in (
                    8, 9, 10, 11, 12, 13, 14, 15,
                )),
                low_latency_guards=low_latency_guards,
                direct_core=direct_core,
            )

            def disk_worker() -> None:
                try:
                    serve_disk(
                        master, volume, timeout=180, idle_timeout=None,
                        verbose=False, stats=stats,
                        protocol_version=3 if netdisk_v3 else 2,
                        reply_filter=disk_reply_filter if drop_replies else None,
                        console_protocol=remote_console,
                        console_input=remote_input if remote_console else None,
                        console_output=remote_output if remote_console else None,
                        console_reply_filter=(
                            console_reply_filter
                            if remote_console_drop_replies else None
                        ),
                    )
                except BaseException as error:
                    errors.append(error)

            worker = threading.Thread(target=disk_worker)
            worker.start()
            first = read_console_until(
                console_master, b"A>", 30 if remote_console else 120,
            )
            if remote_console:
                require(version == 15 and netdisk_v3 and not drop_replies,
                        "remote console requires clean V15/NetDisk v3")
                remote_input.extend(command + b"\r")
                console_drop_state["enabled"] = True
            elif drop_replies:
                drop_state["enabled"] = True
            if not remote_console:
                os.write(console_master, command + b"\r")
            if remote_console:
                failed = recovered = b""
                second = read_console_until(console_master, b"A>", 120)
                os.write(console_master, b"DIR\r")
                third = read_console_until(console_master, b"A>", 120)
            elif drop_replies:
                failed = read_console_until(console_master, b"Bad Sector", 120)
                # Any non-Ctrl-C response tells CP/M 2.2 to return from its
                # permanent-error handler. The modeled matrix has Return but
                # no synthetic Control modifier, so use Return here.
                os.write(console_master, b"\r")
                recovered = read_console_until(console_master, b"A>", 120)
                os.write(console_master, command + b"\r")
                second = read_console_until(console_master, b"A>", 120)
                third = b""
            else:
                failed = recovered = b""
                second = read_console_until(console_master, b"A>", 120)
                third = b""
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
            (case / "disk-stats.json").write_text(
                json.dumps(stats, indent=2, sort_keys=True) + "\n"
            )

    require(process.returncode in (-15, 0),
            f"fastboot v{version} network DIR cosim did not exit cleanly")
    require(result["protocol_version"] == version and result["retries"] == 0,
            f"fastboot v{version} network handoff retried: {result}")
    if direct_core:
        require(
            result["direct_core"] == 1 and
            result["stock_sent_frames"] == 0 and
            result["stock_sent_bytes"] == 0,
            f"direct ROM path unexpectedly used stock Janet: {result}",
        )
    require(b"CP/Mish 2.2 Juku" in first and
            command.split()[0] in second,
            f"fastboot v{version} did not reach prompt/{command!r}: "
            f"{first!r} {second!r}")
    if remote_console:
        remote_transcript = bytes(remote_output)
        local_transcript = first + second + third
        (case / "remote-console.bin").write_bytes(remote_transcript)
        remote_difference = next(
            (index for index, pair in enumerate(zip(
                remote_transcript, local_transcript,
            )) if pair[0] != pair[1]),
            None,
        )
        require(
            b"CP/Mish 2.2 Juku" in second and b"DIR" in third and
            not remote_input and
            remote_transcript == local_transcript and
            stats.get("console_input_bytes") == len(command) + 1 and
            stats.get("console_output_bytes") == len(remote_output),
            "remote/local console transcript or counters differ: "
            f"input={remote_input!r} output={len(remote_output)} "
            f"transcript={len(local_transcript)} first={remote_difference} "
            f"stats={stats}",
        )
        require(
            console_drop_state["count"] == remote_console_drop_replies and
            stats.get("dropped_replies") == remote_console_drop_replies,
            f"remote-console loss injection differs: "
            f"drop={console_drop_state} stats={stats}",
        )
    if drop_replies:
        require(
            b"Bdos Err On A: Bad Sector" in failed and
            drop_state["count"] == drop_replies and
            stats.get("dropped_replies") == drop_replies,
            f"bounded disk timeout/reconnect path differs: "
            f"failed={failed!r} drop={drop_state} stats={stats}",
        )
    if command == b"DIR":
        require(stats.get("read_records", 0) >= 34,
                f"fastboot v{version} DIR issued too few reads: {stats}")
        if netdisk_v3 and not drop_replies:
            require(stats.get("reads", 0) <= 13,
                    f"fastboot NetDisk v3 did not use read-ahead: {stats}")
    elif command == b"DIAG ALL":
        require(
            all(label in second for label in (
                b"CPU: PASS",
                b"RAM data: PASS",
                b"RAM address: PASS",
                b"RAM retention: PASS",
                b"Checksum: PASS",
            )),
                f"shared DIAG clean result differs: {second!r}")
    elif command == b"DIAG CPU" and diag_cpu_fault:
        require(b"CPU: FAIL mask 02" in second,
                f"shared DIAG missed D1/A12 fault: {second!r}")
    require(all(isinstance(error, OSError) for error in errors),
            f"fastboot v{version} disk server failed: {errors!r}")
    state = parse_state((case / "final.state"))
    if diag_cpu_fault:
        require(
            state.get("cpu_a12_increment_fault_arm_fired") == "1" and
            state.get("cpu_a12_increment_fault_disarm_fired") == "1" and
            state.get("cpu_a12_increment_fault") == "0",
            f"controlled CPU fault did not arm/disarm cleanly: {state}",
        )
    final_ram = (case / "final.ram").read_bytes()
    require(final_ram[0xD79F:0xD7A4] == bytes.fromhex("e3 22 56 d4 e1"),
            f"fastboot v{version} did not preserve RomBios dispatcher")
    log = (case / "stderr.txt").read_text()
    if version == 15:
        require(state.get("mode") == "3" and state.get("pic_mask") == "FF",
                "V15 RAM BIOS did not retain all-RAM mode with IRQs masked")
        require(state.get("video_modx_mode") == "1" and
                state.get("video_stride") == "50" and
                state.get("video_lines") == "192",
                "V15 RAM BIOS did not select modeled MODX 400x192 timing")
        require(state.get("usart_mode") == "5E",
                "V15 RAM BIOS did not select its 19200/8O1 disk framing")
        require("x16 mode=4E" in log and "x16 mode=5E" in log,
                "V15 did not exercise its 8N1-to-BIOS-8O1 transition")
        require("[BANK] mode 1 -> 3" in log and
                "[BANK] mode 3 -> 1" not in log.split(
                    "[BANK] mode 1 -> 3", 1,
                )[1], "V15 returned to a firmware ROM view after takeover")
        require(all(final_ram[address] == 0xC9
                    for address in (0xD773, 0xD777, 0xD78F)),
                "V15 RAM BIOS left a NetBios service vector installed")
        vram = final_ram[0xD800:0xD800 + 9600]
        expected_vram = render_ram_console(
            first + failed + recovered + second + third,
        )
        (case / "console.bin").write_bytes(
            first + failed + recovered + second + third,
        )
        (case / "expected-vram.bin").write_bytes(expected_vram)
        differing = next(
            (index for index, pair in enumerate(zip(vram, expected_vram))
             if pair[0] != pair[1]),
            None,
        )
        require(
            vram == expected_vram,
            "V15 framebuffer differs from its console transcript: "
            f"first={differing} actual="
            f"{hashlib.sha256(vram).hexdigest()[:12]} expected="
            f"{hashlib.sha256(expected_vram).hexdigest()[:12]}",
        )
        bios_detail = (
            "RAM BIOS NetDisk v3/all-RAM" if netdisk_v3 else
            "RAM BIOS 8O1/all-RAM"
        )
    else:
        require(state.get("usart_mode") == "5E",
                f"CP/M BIOS did not restore 19200/8O1 after v{version} handoff")
        require("x16 mode=4E" in log and "x16 mode=5E" in log,
                f"v{version} did not exercise its 8N1-to-BIOS-8O1 transition")
        bios_detail = "BIOS 8O1"
    print(
        f"FASTBOOT V{version} NETWORK {command.decode('ascii')}"
        f"{' DIRECT-ROM' if direct_core else ''}"
        f"{' LOW-LATENCY' if low_latency_guards else ''}: PASS "
        f"(reads={stats['reads']}, retries={stats['retries']}, {bios_detail})"
    )


def run_fastboot_reset_recovery_case(trace: Path, work: Path) -> None:
    """Reset V15 mid-stream and prove fresh stock-request rediscovery."""
    case = work / "fastboot-v15-reset-recovery"
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
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="TN0201",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
        JUKU_RESET_AFTER_USART_RX="900",
        JUKU_STOP_PC="0xC600",
        JUKU_CHECKPOINT_PREFIX=str(checkpoint),
    )
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        try:
            def attempt() -> dict[str, object]:
                return serve_fast(
                    master, FASTBOOT_V15_RAMBIOS.read_bytes(),
                    RAMBIOS_SYSTEM.read_bytes(),
                    stock_timeout=30, reply_timeout=0.3, retries=1,
                    verbose=False, configure_rate=False,
                    compact_stock_execute=True,
                )

            boot = boot_with_recovery(
                attempt,
                prepare_retry=lambda: termios.tcflush(
                    master, termios.TCIOFLUSH,
                ),
                max_restarts=2,
                verbose=False,
            )
            process.wait(timeout=20)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            os.close(master)

    require(process.returncode == 0,
            "V15 reset-recovery cosim did not reach its second handoff")
    require(boot.get("boot_restarts") == 1,
            f"V15 reset recovery count differs: {boot}")
    state = parse_state(checkpoint.with_suffix(".state"))
    ram = checkpoint.with_suffix(".ram").read_bytes()
    expected = RAMBIOS_SYSTEM.read_bytes()[512:]
    require(state.get("pc") == "C600" and
            ram[0xB000:0xB000 + len(expected)] == expected,
            "V15 reset recovery did not install the second image byte-exactly")
    log = (case / "stderr.txt").read_text()
    require(log.count("[RESET] one-shot board reset") == 1,
            "V15 reset fault did not fire exactly once")
    print(
        "FASTBOOT V15 RESET RECOVERY: PASS "
        "(mid-stream reset; fresh stock request; byte-exact second handoff)"
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


def render_ram_console(transcript: bytes) -> bytes:
    """Render from the independent human-readable source glyphs."""
    return render_source_console(transcript)


def read_console_for(fd: int, duration: float) -> bytes:
    """Collect all console output during a fixed diagnostic interval."""
    import select

    result = bytearray()
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.05)
        if not ready:
            continue
        try:
            result.extend(os.read(fd, 4096))
        except OSError:
            break
    return bytes(result)


def read_console_prompt(fd: int, timeout: float) -> bytes:
    """Read through the final idle A> prompt, ignoring A> inside file text."""
    import select

    result = bytearray()
    deadline = time.monotonic() + timeout
    prompt_seen_at: float | None = None
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if ready:
            try:
                incoming = os.read(fd, 4096)
            except OSError:
                continue
            result.extend(incoming)
            if b"A>" in result:
                prompt_seen_at = time.monotonic()
        elif prompt_seen_at is not None and \
                time.monotonic() - prompt_seen_at >= 0.5:
            return bytes(result)
    raise TimeoutError(f"console did not settle at A>; transcript={bytes(result)!r}")


def run_netdisk_benchmark(
    trace: Path, work: Path, *, netdisk_v2: bool,
    host_protocol: int | None = None,
    command_list: tuple[str, ...] = ("DIR", "TYPE README.TXT", "RDBENCH"),
) -> dict[str, object]:
    """Measure console-heavy and no-console commands plus their wire cost."""
    if host_protocol is None:
        host_protocol = 2 if netdisk_v2 else 1
    label = "v2-legacy-fallback" if netdisk_v2 and host_protocol == 1 else \
        ("v2-compact" if netdisk_v2 else "v1-record")
    case = work / f"netdisk-benchmark-{label}"
    case.mkdir()
    system_path = NETDISK_V2_SYSTEM if netdisk_v2 else MODE2_SYSTEM
    volume_path = NETDISK_V2_FLAT if netdisk_v2 else MODE2_FLAT
    stage_path = FASTBOOT_V14_NETDISK_V2 if netdisk_v2 else FASTBOOT_V14
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
        JUKU_TRACE_BANK="0",
        JUKU_DISABLE_SETTLE="1",
        JUKU_KEYS="TN0201|",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
    )
    volume = bytearray(volume_path.read_bytes())
    stats: dict[str, int] = {}
    errors: list[BaseException] = []
    commands: dict[str, dict[str, float | int]] = {}
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
                master, stage_path.read_bytes(), system_path.read_bytes(),
                stock_timeout=120, reply_timeout=8, verbose=False,
                configure_rate=False, compact_stock_execute=True,
            )

            def disk_worker() -> None:
                try:
                    serve_disk(
                        master, volume, timeout=300, idle_timeout=None,
                        verbose=False, stats=stats,
                        protocol_version=host_protocol,
                    )
                except BaseException as error:
                    errors.append(error)

            worker = threading.Thread(target=disk_worker)
            disk_started = time.monotonic()
            worker.start()
            initial = read_console_prompt(console_master, 120)
            boot_elapsed = time.monotonic() - disk_started
            require(b"CP/Mish 2.2 Juku" in initial,
                    f"{label}: boot prompt missing")
            boot_request_bytes = stats.get("request_wire_bytes", 0)
            boot_reply_bytes = stats.get("reply_wire_bytes", 0)
            boot_requests = stats.get("reads", 0)
            boot_disk = {
                "simulator_elapsed_seconds": boot_elapsed,
                "read_requests": boot_requests,
                "records_transferred": stats.get("read_records", 0),
                "wire_bytes": boot_request_bytes + boot_reply_bytes,
                "modeled_wire_seconds":
                    (boot_request_bytes + boot_reply_bytes) * 11 / 19200
                    + boot_requests * 0.002,
                "compact_records": stats.get("compact_records", 0),
                "compact_bytes_saved": stats.get("compact_bytes_saved", 0),
            }
            for command in command_list:
                before = dict(stats)
                started = time.monotonic()
                os.write(console_master, command.encode("ascii") + b"\r")
                transcript = read_console_prompt(console_master, 180)
                elapsed = time.monotonic() - started
                require(command.encode("ascii").split()[0] in transcript,
                        f"{label}: {command} was not echoed")
                if command == "TYPE README.TXT":
                    require(
                        b"See `third_party/dr/COPYING.md` for more" in transcript
                        and b"information." in transcript,
                        f"{label}: TYPE stopped before README.TXT EOF; "
                        f"bytes={len(transcript)}, tail={transcript[-160:]!r}",
                    )
                request_bytes = stats.get("request_wire_bytes", 0) - \
                    before.get("request_wire_bytes", 0)
                reply_bytes = stats.get("reply_wire_bytes", 0) - \
                    before.get("reply_wire_bytes", 0)
                requests = stats.get("reads", 0) - before.get("reads", 0)
                records = stats.get("read_records", 0) - \
                    before.get("read_records", 0)
                # 8O1 is 11 wire bits per character. Include the configured
                # 2 ms half-duplex guard for each request.
                wire_seconds = (request_bytes + reply_bytes) * 11 / 19200 + \
                    requests * 0.002
                commands[command] = {
                    "simulator_elapsed_seconds": elapsed,
                    "read_requests": requests,
                    "records_transferred": records,
                    "wire_bytes": request_bytes + reply_bytes,
                    "modeled_wire_seconds": wire_seconds,
                    "console_bytes": len(transcript),
                    "compact_records": stats.get("compact_records", 0)
                    - before.get("compact_records", 0),
                    "compact_bytes_saved": stats.get("compact_bytes_saved", 0)
                    - before.get("compact_bytes_saved", 0),
                }
                if command == "RDBENCH":
                    require(records >= 70,
                            f"{label}: RDBENCH did not read README.TXT: "
                            f"{commands[command]}")
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
    require(boot["protocol_version"] == 14 and boot["retries"] == 0,
            f"{label}: V14 bootstrap differs: {boot}")
    require(all(isinstance(error, OSError) for error in errors),
            f"{label}: disk server failed: {errors!r}")
    result: dict[str, object] = {
        "schema": "juku-netdisk-benchmark-v1",
        "variant": label,
        "cpu_hz": 1_700_000,
        "baud": 19200,
        "framing": "8O1",
        "host_protocol": host_protocol,
        "boot_disk": boot_disk,
        "commands": commands,
    }
    (case / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"NETDISK {label}: PASS ({commands})")
    return result


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


def run_broken_handoff_case(trace: Path, work: Path) -> None:
    """Require the reconstructed pre-fix handoff to lose keyboard input."""
    case = work / "broken-handoff"
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
        JUKU_KEYS="TN0201|",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
        JUKU_CHECKPOINT_PREFIX=str(case / "final"),
    )
    volume = bytearray(MODE2_FLAT.read_bytes())
    stats: dict[str, int] = {}
    disk_error: list[BaseException] = []
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        os.close(console_slave)
        try:
            serve_boot(
                master, BROKEN_MODE2_SYSTEM.read_bytes(), timeout=120,
                verbose=False,
            )

            def disk_worker() -> None:
                try:
                    serve_disk(
                        master, volume, timeout=60, idle_timeout=None,
                        verbose=False, stats=stats,
                    )
                except BaseException as error:
                    disk_error.append(error)

            worker = threading.Thread(target=disk_worker)
            worker.start()
            first = read_console_until(console_master, b"A>", 120)
            reads_before = stats.get("reads", 0)
            os.write(console_master, b"DIR\r")
            after = read_console_for(console_master, 3.0)
        finally:
            process.terminate()
            process.wait(timeout=5)
            os.close(master)
            if "worker" in locals():
                worker.join(timeout=3)
            os.close(console_master)

    require(b"CP/Mish 2.2 Juku" in first,
            "broken handoff did not reach the same initial CP/M prompt")
    require(after == b"",
            f"broken handoff unexpectedly serviced keyboard input: {after!r}")
    require(stats.get("reads", 0) == reads_before,
            "broken handoff unexpectedly issued DIR disk reads")
    require(all(isinstance(error, OSError) for error in disk_error),
            f"broken handoff disk server failed unexpectedly: {disk_error!r}")
    final_ram = (case / "final.ram").read_bytes()
    require(final_ram[0xD79F:0xD7A4] == bytes.fromhex("e3 22 56 d4 e1"),
            "broken handoff unexpectedly changed D79F")
    require(any(final_ram[address] != 0xC9
                for address in (0xD773, 0xD777, 0xD78F)),
            "broken handoff did not retain a NetBios service vector")
    print(
        "Historical NetBios handoff failure: REPRODUCED "
        f"(initial prompt reached; DIR ignored; reads stayed at {reads_before})"
    )


def run_ram_output_case(
    trace: Path, work: Path, *, ram_keyboard: bool = False,
    netdisk_v3: bool = False, netdisk_v3_fault: str | None = None,
    host_protocol: int | None = None,
) -> None:
    """Boot relocated RAM output with RomBios or RAM-owned matrix input."""
    if host_protocol is None:
        host_protocol = 3 if netdisk_v3 else 2
    case = work / (
        f"ram-bios-v3-fault-{netdisk_v3_fault}" if netdisk_v3_fault else
        f"ram-bios-v3-fallback-v{host_protocol}" if
        netdisk_v3 and host_protocol != 3 else
        "ram-bios-v3" if netdisk_v3 else
        "ram-bios" if ram_keyboard else "ram-output"
    )
    case.mkdir()
    system_source = RAMBIOS_V3_SYSTEM if netdisk_v3 else \
        RAMBIOS_SYSTEM if ram_keyboard else RAMOUT_SYSTEM
    container = system_source.read_bytes()
    resident = container[512:] if ram_keyboard else container[512:512 + 7680]
    if ram_keyboard:
        expected_size = 0x2600 if netdisk_v3 else 0x2080
        require(container[:8] == b"JUKURM1\x1a" and
                container[8:12] == bytes.fromhex("00 b0 00 c6") and
                len(resident) == expected_size,
                f"RAM BIOS resident size differs from {expected_size}")
    conout_vector = 0xC60C - 0xB000
    require(resident[conout_vector] == 0xC3,
            "RAM output BIOS CONOUT vector is not a JMP")
    conout_pc = int.from_bytes(
        resident[conout_vector + 1:conout_vector + 3], "little",
    )
    master, slave = pty.openpty()
    tty.setraw(slave)
    console_master, console_slave = pty.openpty()
    tty.setraw(console_slave)
    environment = os.environ.copy()
    environment.update(
        JUKU_USART_PTY=os.ttyname(slave),
        JUKU_CONSOLE_PTY=os.ttyname(console_slave),
        # Hook the JMP target, not merely the public vector: the cold-start
        # banner calls CONOUT internally and must enter the pixel oracle too.
        JUKU_CONSOLE_OUT_PC=f"0x{conout_pc:04X}",
        JUKU_CONSOLE_OUT_REGISTER="C",
        JUKU_USART_TRANSFER_CYCLES="64",
        JUKU_USART_BYTE_CYCLES="2300",
        JUKU_USART_PIT_CLOCK="1",
        JUKU_USART_PIT_CPU_HZ="1700000",
        JUKU_DISABLE_SETTLE="1",
        JUKU_TRACE_BANK="1",
        # The firmware-specific framebuffer prompt oracle cannot recognize the
        # intentionally different RAM font. Host input is appended only after
        # this test has observed A> through the character hook, so no marker is
        # needed here.
        JUKU_KEYS="TN0201",
        JUKU_KEY_HOLD_FRAMES="6",
        JUKU_KEY_GAP_FRAMES="8",
        JUKU_CHECKPOINT_PREFIX=str(case / "final"),
    )
    volume = bytearray(NETDISK_V2_FLAT.read_bytes())
    stats: dict[str, int] = {}
    disk_error: list[BaseException] = []
    with (case / "stdout.txt").open("w") as stdout, \
            (case / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            [str(trace), str(ROM), "1000000000000", "0", "100000"],
            cwd=case, env=environment, stdout=stdout, stderr=stderr,
        )
        os.close(slave)
        os.close(console_slave)
        try:
            boot = serve_boot(
                master, container, timeout=120,
                verbose=False,
            )

            def disk_worker() -> None:
                try:
                    def corrupt_first_crc(attempt: int, reply: bytes) -> bytes:
                        if attempt != 1 or netdisk_v3_fault is None:
                            return reply
                        damaged = bytearray(reply)
                        if netdisk_v3_fault == "crc":
                            damaged[-1] ^= 1
                        elif netdisk_v3_fault == "payload":
                            damaged[12] ^= 1
                        elif netdisk_v3_fault == "kind":
                            damaged[8] ^= 0x80
                        else:
                            raise ValueError(
                                f"unknown NetDisk v3 fault "
                                f"{netdisk_v3_fault!r}"
                            )
                        return bytes(damaged)

                    serve_disk(
                        master, volume, timeout=180, idle_timeout=None,
                        verbose=os.environ.get("JUKU_COSIM_VERBOSE") == "1",
                        stats=stats,
                        protocol_version=host_protocol,
                        reply_filter=corrupt_first_crc,
                    )
                except BaseException as error:
                    disk_error.append(error)

            worker = threading.Thread(target=disk_worker)
            worker.start()
            first = read_console_until(console_master, b"A>", 120)
            os.write(console_master, b"DIR\r")
            second = read_console_until(console_master, b"A>", 120)
            # The character hook fires at the public BIOS vector, before the
            # renderer has consumed C.  Let the final prompt finish drawing
            # before termination writes the framebuffer checkpoint.
            time.sleep(0.1)
        finally:
            process.terminate()
            process.wait(timeout=5)
            os.close(master)
            if "worker" in locals():
                worker.join(timeout=3)
            os.close(console_master)

    expected_boot_bytes = 128 + len(resident)
    require(boot["image_bytes"] == expected_boot_bytes,
            f"RAM staging size changed: {boot['image_bytes']}, expected "
            f"{expected_boot_bytes}")
    require(b"A>" in first and b"DIR" in second,
            f"RAM output console transcript is incomplete: {first + second!r}")
    require(stats.get("read_records", 0) >= 34,
            f"RAM output DIR issued too few reads: {stats}; "
            f"transcript={first + second!r}")
    if netdisk_v3 and host_protocol == 3:
        require(stats.get("reads", 0) <= 13 and
                stats.get("read_ahead_records", 0) >= 34,
                f"NetDisk v3 did not amortize DIR reads: {stats}")
        require(stats.get("v3_prefix", 0) and
                stats.get("v3_deleted", 0),
                f"NetDisk v3 bounded encodings were not exercised: {stats}")
        require(stats.get("retries", 0) == int(netdisk_v3_fault is not None),
                f"NetDisk v3 CRC retry count differs: {stats}")
    elif netdisk_v3:
        require(stats.get("reads", 0) >= 34 and
                stats.get("read_ahead_records", 0) == 0 and
                stats.get("retries", 0) == 0,
                f"NetDisk v3 fallback to v{host_protocol} differs: {stats}")
    require(all(isinstance(error, OSError) for error in disk_error),
            f"RAM output disk server failed: {disk_error!r}")
    log = (case / "stderr.txt").read_text()
    require("[BANK] mode 1 -> 3" in log,
            "RAM output never selected all-RAM mode 3")
    final_ram = (case / "final.ram").read_bytes()
    require(final_ram[0xD79F:0xD7A4] == bytes.fromhex("e3 22 56 d4 e1"),
            "RAM output modified the RomBios dispatcher")
    require(all(final_ram[address] == 0xC9
                for address in (0xD773, 0xD777, 0xD78F)),
            "RAM output left a NetBios service vector installed")
    state = parse_state(case / "final.state")
    require(state.get("video_modx_mode") == "1" and
            state.get("video_stride") == "50" and
            state.get("video_lines") == "192",
            "RAM console did not select modeled MODX 400x192 timing")
    if ram_keyboard:
        require(state.get("mode") == "3" and state.get("pic_mask") == "FF",
                "RAM BIOS did not retain all-RAM mode with every IRQ masked: "
                f"mode={state.get('mode')} mask={state.get('pic_mask')}")
        require("[BANK] mode 3 -> 1" not in log.split(
            "[BANK] mode 1 -> 3", 1,
        )[1], "RAM BIOS returned to a firmware ROM view after takeover")
    else:
        require(state.get("mode") == "1" and "[BANK] mode 3 -> 1" in log,
                "RAM-output Stage 1 did not restore the RomBios view")
    vram = final_ram[0xD800:0xD800 + 9600]
    digest = hashlib.sha256(vram).hexdigest()
    expected_vram = render_ram_console(first + second)
    mismatches = [
        index
        for index, (actual, expected) in enumerate(zip(vram, expected_vram))
        if actual != expected
    ]
    require(vram == expected_vram,
            "RAM output framebuffer differs from its console transcript: "
            f"{len(mismatches)} bytes, first offsets={mismatches[:12]}, "
            "first values="
            f"{[(i, vram[i], expected_vram[i]) for i in mismatches[:12]]}, "
            f"transcript={(first + second)!r}")
    print(
        f"51K staged {'RAM BIOS v3' if netdisk_v3 else 'RAM BIOS' if ram_keyboard else 'RAM output'}: PASS "
        f"({'polled RAM' if ram_keyboard else 'RomBios'} keyboard DIR; "
        f"host=v{host_protocol}; "
        f"reads={stats.get('reads', 0)}; "
        f"retries={stats.get('retries', 0)}; "
        f"VRAM={digest[:12]})"
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
    require(
        load_console_assembly_font() == load_console_reference_font(),
        "generated RAM console font differs from its source reference",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baudtest-only", action="store_true")
    parser.add_argument("--keyboard-only", action="store_true")
    parser.add_argument("--fastboot-only", action="store_true")
    parser.add_argument("--fastboot-v15-only", action="store_true")
    parser.add_argument("--netdisk-benchmark-only", action="store_true")
    parser.add_argument("--ram-output-only", action="store_true")
    parser.add_argument("--ram-bios-only", action="store_true")
    parser.add_argument("--netdisk-v3-only", action="store_true")
    parser.add_argument("--game-disk", type=Path,
                        help="physical 800 KiB .JUK image for native B: test")
    args = parser.parse_args()
    required_images = (
        ((RAMBIOS_V3_SYSTEM if args.netdisk_v3_only else
          RAMBIOS_SYSTEM if args.ram_bios_only else RAMOUT_SYSTEM),
         NETDISK_V2_FLAT,
         *((FASTBOOT_V15_NETDISK_V3,) if args.netdisk_v3_only else ()))
        if args.ram_output_only or args.ram_bios_only or
        args.netdisk_v3_only else (
            SYSTEM, FLAT, SMOKE_SYSTEM, SMOKE_FLAT,
            MODE2_SYSTEM, BROKEN_MODE2_SYSTEM, MODE2_FLAT,
            NETDISK_V2_SYSTEM, RAMOUT_SYSTEM, RAMBIOS_SYSTEM,
            RAMBIOS_V3_SYSTEM,
            NETDISK_V2_FLAT,
            BAUDTEST_SYSTEM, BAUDTEST_9600_FLAT, BAUDTEST_8N1_FLAT,
            BAUDTEST_LADDER_FLAT, BAUDTEST2_SYSTEM, BAUDTEST2_FLAT,
            MODE2_SOAK_SYSTEM, MODE2_SOAK_FLAT,
            FASTBOOT_STAGE1, FASTBOOT_V2, FASTBOOT_V3, FASTBOOT_V4,
            FASTBOOT_V5,
            FASTBOOT_V6, FASTBOOT_V7, FASTBOOT_V8, FASTBOOT_V9, FASTBOOT_V10,
            FASTBOOT_V11,
            FASTBOOT_V12,
            FASTBOOT_V13,
            FASTBOOT_V14,
            FASTBOOT_V14_NETDISK_V2,
            FASTBOOT_V15_RAMBIOS,
            FASTBOOT_V15_NETDISK_V3,
        )
    )
    require(
        all(path.is_file() for path in required_images),
        "build the normal, smoke, and baud-test network images first",
    )
    with tempfile.TemporaryDirectory(prefix="cpmish-juku-net.") as name:
        work = Path(name)
        trace = work / "trace"
        build_trace(trace)
        if args.netdisk_benchmark_only:
            baseline = run_netdisk_benchmark(trace, work, netdisk_v2=False)
            improved = run_netdisk_benchmark(trace, work, netdisk_v2=True)
            fallback = run_netdisk_benchmark(
                trace, work, netdisk_v2=True, host_protocol=1,
                command_list=("DIR",),
            )
            evidence = {
                "schema": "juku-netdisk-comparison-v1",
                "baseline": baseline,
                "improved": improved,
                "legacy_fallback": fallback,
            }
            output = ROOT / "juku-netdisk-benchmark.json"
            output.write_text(json.dumps(evidence, indent=2) + "\n")
            print(f"JUKU-NETDISK-BENCHMARK: PASS ({output})")
            return
        if args.fastboot_v15_only:
            run_fastboot_case(trace, work, version=15, faults=False)
            run_fastboot_case(trace, work, version=15, faults=True)
            run_fastboot_case(
                trace, work, version=15, faults=False, rx_irq_delay=True,
            )
            run_fastboot_reset_recovery_case(trace, work)
            run_fastboot_disk_case(trace, work, 15)
            run_fastboot_disk_case(
                trace, work, 15, netdisk_v3=True, direct_core=True,
            )
            print("JUKU-FASTBOOT-V15-COSIM-CHECK: PASS")
            return
        if args.fastboot_only:
            for version in (
                1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
            ):
                run_fastboot_case(trace, work, version=version, faults=False)
                run_fastboot_case(trace, work, version=version, faults=True)
            run_fastboot_disk_case(trace, work, 7)
            run_fastboot_disk_case(trace, work, 8)
            run_fastboot_disk_case(trace, work, 9)
            run_fastboot_disk_case(trace, work, 10)
            run_fastboot_disk_case(trace, work, 11)
            run_fastboot_disk_case(trace, work, 12)
            run_fastboot_disk_case(trace, work, 13)
            run_fastboot_disk_case(trace, work, 14)
            run_fastboot_disk_case(trace, work, 15)
            run_fastboot_case(
                trace, work, version=9, faults=False,
                low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=9, faults=True,
                low_latency_guards=True,
            )
            run_fastboot_disk_case(
                trace, work, 9, low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=10, faults=False,
                low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=10, faults=True,
                low_latency_guards=True,
            )
            run_fastboot_disk_case(
                trace, work, 10, low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=11, faults=False,
                low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=11, faults=True,
                low_latency_guards=True,
            )
            run_fastboot_disk_case(
                trace, work, 11, low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=12, faults=False,
                low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=12, faults=True,
                low_latency_guards=True,
            )
            run_fastboot_disk_case(
                trace, work, 12, low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=13, faults=False,
                low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=13, faults=True,
                low_latency_guards=True,
            )
            run_fastboot_disk_case(
                trace, work, 13, low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=14, faults=False,
                low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=14, faults=True,
                low_latency_guards=True,
            )
            run_fastboot_disk_case(
                trace, work, 14, low_latency_guards=True,
            )
            run_fastboot_case(
                trace, work, version=10, faults=False, cpu_hz=3_400_000,
            )
            run_fastboot_case(
                trace, work, version=11, faults=False, cpu_hz=3_400_000,
            )
            run_fastboot_case(
                trace, work, version=12, faults=False, cpu_hz=3_400_000,
            )
            run_fastboot_case(
                trace, work, version=13, faults=False, cpu_hz=3_400_000,
            )
            run_fastboot_case(
                trace, work, version=14, faults=False, cpu_hz=3_400_000,
            )
            run_fastboot_case(
                trace, work, version=13, faults=False, rx_irq_delay=True,
            )
            run_fastboot_case(
                trace, work, version=14, faults=False, rx_irq_delay=True,
            )
            run_fastboot_case(
                trace, work, version=15, faults=False, rx_irq_delay=True,
            )
            run_fastboot_reset_recovery_case(trace, work)
            run_fastboot_case(
                trace, work, version=4, faults=False,
                force_rate_fallback=True,
            )
            print("JUKU-FASTBOOT-COSIM-CHECK: PASS")
            return
        if args.keyboard_only:
            run_broken_handoff_case(trace, work)
            run_mode2_keyboard_case(trace, work)
            if args.game_disk:
                run_native_drive_b_case(trace, work, args.game_disk)
            return
        if args.ram_output_only:
            run_ram_output_case(trace, work)
            return
        if args.ram_bios_only:
            run_ram_output_case(trace, work, ram_keyboard=True)
            return
        if args.netdisk_v3_only:
            run_ram_output_case(
                trace, work, ram_keyboard=True, netdisk_v3=True,
            )
            run_ram_output_case(
                trace, work, ram_keyboard=True, netdisk_v3=True,
                netdisk_v3_fault="crc",
            )
            run_ram_output_case(
                trace, work, ram_keyboard=True, netdisk_v3=True,
                netdisk_v3_fault="payload",
            )
            run_ram_output_case(
                trace, work, ram_keyboard=True, netdisk_v3=True,
                netdisk_v3_fault="kind",
            )
            run_ram_output_case(
                trace, work, ram_keyboard=True, netdisk_v3=True,
                host_protocol=2,
            )
            run_ram_output_case(
                trace, work, ram_keyboard=True, netdisk_v3=True,
                host_protocol=1,
            )
            run_fastboot_disk_case(trace, work, 15, netdisk_v3=True)
            run_fastboot_disk_case(
                trace, work, 15, netdisk_v3=True, command=b"DIAG ALL",
            )
            run_fastboot_disk_case(
                trace, work, 15, netdisk_v3=True, command=b"DIAG CPU",
                diag_cpu_fault=True,
            )
            run_fastboot_disk_case(
                trace, work, 15, netdisk_v3=True,
                command=b"TYPE README.TXT", drop_replies=3,
            )
            run_fastboot_disk_case(
                trace, work, 15, netdisk_v3=True, command=b"VER",
                remote_console=True,
            )
            run_fastboot_disk_case(
                trace, work, 15, netdisk_v3=True, command=b"VER",
                remote_console=True, remote_console_drop_replies=1,
            )
            print("JUKU-NETDISK-V3-COSIM-CHECK: PASS")
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
        run_broken_handoff_case(trace, work)
        run_ram_output_case(trace, work)
        run_ram_output_case(trace, work, ram_keyboard=True)
        run_ram_output_case(
            trace, work, ram_keyboard=True, netdisk_v3=True,
        )
        run_ram_output_case(
            trace, work, ram_keyboard=True, netdisk_v3=True,
            netdisk_v3_fault="crc",
        )
        run_ram_output_case(
            trace, work, ram_keyboard=True, netdisk_v3=True,
            netdisk_v3_fault="payload",
        )
        run_ram_output_case(
            trace, work, ram_keyboard=True, netdisk_v3=True,
            netdisk_v3_fault="kind",
        )
        run_ram_output_case(
            trace, work, ram_keyboard=True, netdisk_v3=True,
            host_protocol=2,
        )
        run_ram_output_case(
            trace, work, ram_keyboard=True, netdisk_v3=True,
            host_protocol=1,
        )
        run_fastboot_disk_case(trace, work, 15, netdisk_v3=True)
        run_fastboot_disk_case(
            trace, work, 15, netdisk_v3=True, command=b"DIAG ALL",
        )
        run_fastboot_disk_case(
            trace, work, 15, netdisk_v3=True, command=b"DIAG CPU",
            diag_cpu_fault=True,
        )
        run_fastboot_disk_case(
            trace, work, 15, netdisk_v3=True,
            command=b"TYPE README.TXT", drop_replies=3,
        )
        run_fastboot_disk_case(
            trace, work, 15, netdisk_v3=True, command=b"VER",
            remote_console=True,
        )
        run_fastboot_disk_case(
            trace, work, 15, netdisk_v3=True, command=b"VER",
            remote_console=True, remote_console_drop_replies=1,
        )
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
        for version in (
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
        ):
            run_fastboot_case(trace, work, version=version, faults=False)
            run_fastboot_case(trace, work, version=version, faults=True)
        run_fastboot_disk_case(trace, work, 7)
        run_fastboot_disk_case(trace, work, 8)
        run_fastboot_disk_case(trace, work, 9)
        run_fastboot_disk_case(trace, work, 10)
        run_fastboot_disk_case(trace, work, 11)
        run_fastboot_disk_case(trace, work, 12)
        run_fastboot_disk_case(trace, work, 13)
        run_fastboot_disk_case(trace, work, 14)
        run_fastboot_disk_case(trace, work, 15)
        run_fastboot_case(
            trace, work, version=9, faults=False,
            low_latency_guards=True,
        )
        run_fastboot_case(
            trace, work, version=9, faults=True,
            low_latency_guards=True,
        )
        run_fastboot_disk_case(trace, work, 9, low_latency_guards=True)
        run_fastboot_case(
            trace, work, version=10, faults=False,
            low_latency_guards=True,
        )
        run_fastboot_case(
            trace, work, version=10, faults=True,
            low_latency_guards=True,
        )
        run_fastboot_disk_case(trace, work, 10, low_latency_guards=True)
        run_fastboot_case(
            trace, work, version=11, faults=False,
            low_latency_guards=True,
        )
        run_fastboot_case(
            trace, work, version=11, faults=True,
            low_latency_guards=True,
        )
        run_fastboot_disk_case(trace, work, 11, low_latency_guards=True)
        run_fastboot_case(
            trace, work, version=12, faults=False,
            low_latency_guards=True,
        )
        run_fastboot_case(
            trace, work, version=12, faults=True,
            low_latency_guards=True,
        )
        run_fastboot_disk_case(trace, work, 12, low_latency_guards=True)
        run_fastboot_case(
            trace, work, version=13, faults=False,
            low_latency_guards=True,
        )
        run_fastboot_case(
            trace, work, version=13, faults=True,
            low_latency_guards=True,
        )
        run_fastboot_disk_case(trace, work, 13, low_latency_guards=True)
        run_fastboot_case(
            trace, work, version=14, faults=False,
            low_latency_guards=True,
        )
        run_fastboot_case(
            trace, work, version=14, faults=True,
            low_latency_guards=True,
        )
        run_fastboot_disk_case(trace, work, 14, low_latency_guards=True)
        run_fastboot_case(
            trace, work, version=10, faults=False, cpu_hz=3_400_000,
        )
        run_fastboot_case(
            trace, work, version=11, faults=False, cpu_hz=3_400_000,
        )
        run_fastboot_case(
            trace, work, version=12, faults=False, cpu_hz=3_400_000,
        )
        run_fastboot_case(
            trace, work, version=13, faults=False, cpu_hz=3_400_000,
        )
        run_fastboot_case(
            trace, work, version=14, faults=False, cpu_hz=3_400_000,
        )
        run_fastboot_case(
            trace, work, version=13, faults=False, rx_irq_delay=True,
        )
        run_fastboot_case(
            trace, work, version=14, faults=False, rx_irq_delay=True,
        )
        run_fastboot_case(
            trace, work, version=4, faults=False,
            force_rate_fallback=True,
        )
    print("JUKU-NET-COSIM-CHECK: PASS")


if __name__ == "__main__":
    main()
