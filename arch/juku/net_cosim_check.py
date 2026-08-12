#!/usr/bin/env python3
"""Prove diskless CP/M boot, reads, and writes through Janet/USART."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import pty
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
FLAT = ROOT / ".obj" / "arch" / "juku" / "+flatdiskimage" / \
    "arch" / "juku" / "+flatdiskimage.img"
sys.path.insert(0, str(COSIM / "tools"))

from janet_disk_server import serve_disk  # noqa: E402
from janet_netboot import serve as serve_boot  # noqa: E402


EXPECTED_VRAM = {
    "DIR": "ac9f882392a81cc9d882d3f7247931e4ec16922afb515a7a30d092606f5af78a",
    "SAVE 1 TEST.COM": "32f3be5276bdef7d8444efdee6e41ad9fd5e7819dcfe6b29428efc168c90b0e7",
}


def run_case(trace: Path, work: Path, command: str) -> tuple[bytearray, dict[str, int]]:
    case = work / command.split()[0].lower()
    case.mkdir()
    system = case / "system.bin"
    shutil.copyfile(SYSTEM, system)
    seed_command(system, command)
    volume = bytearray(FLAT.read_bytes())
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
    require(digest == EXPECTED_VRAM[command],
            f"{command}: VRAM SHA256 {digest} does not match")
    require(result.get("reads", 0) >= 34, f"{command}: too few network reads")
    print(
        f"{command}: PASS (reads={result.get('reads', 0)}, "
        f"writes={result.get('writes', 0)}, retries={result.get('retries', 0)}, "
        f"VRAM={digest[:12]})"
    )
    return volume, result


def main() -> None:
    require(SYSTEM.is_file() and FLAT.is_file(),
            "build juku-net-system.bin and juku.img first")
    with tempfile.TemporaryDirectory(prefix="cpmish-juku-net.") as name:
        work = Path(name)
        trace = work / "trace"
        build_trace(trace)
        run_case(trace, work, "DIR")
        volume, result = run_case(trace, work, "SAVE 1 TEST.COM")
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
    print("JUKU-NET-COSIM-CHECK: PASS")


if __name__ == "__main__":
    main()
