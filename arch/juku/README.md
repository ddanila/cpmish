# Juku port

This branch carries the Juku E5101/E5104 port of CP/Mish. The target CPU is
the Intel 8080-compatible KR580VM80A, so every resident component and every
program included in the default image must be usable without Z80-only
instructions.

## Repository policy

The `ddanila/cpmish` fork uses two long-lived branches:

- `master` is an unmodified, fast-forward mirror of
  `davidgiven/cpmish:master`.
- `juku` contains this port and all Juku-specific documentation and tests.

Published `juku` history is not rebased. To incorporate upstream work,
fast-forward `master` from the `upstream` remote and merge `master` into
`juku`:

```sh
git fetch upstream
git switch master
git merge --ff-only upstream/master
git push origin master
git switch juku
git merge master
git push origin juku
```

Do not commit Juku changes to `master` and do not force-push either published
branch. The local `upstream` remote is fetch-only; all published work goes to
`github.com/ddanila` through `origin`.

## Build prerequisites

On Debian/Ubuntu, install the native build tools with:

```sh
sudo apt install build-essential flex bison cpmtools libz80ex-dev \
    libreadline-dev lua5.4 lua-posix pkg-config cmake ninja-build
```

On macOS with Homebrew, install the native build tools with:

```sh
brew install make cpmtools flex bison readline lua@5.4 pkgconf cmake ninja
```

Use `gmake` on macOS; Homebrew installs GNU Make under that name. The build
selects a portable parallel-job count on both Linux and macOS, so an explicit
`-j$(nproc)` is unnecessary.

CP/Mish also needs the Amsterdam Compiler Kit (ACK) with its `cpm` platform.
Install it under the user prefix so that `~/.local/bin/ack` and the matching
platform files remain together:

```sh
git clone https://github.com/davidgiven/ack.git ack
cd ack
# Edit Makefile and change `PLATS = all` to `PLATS = cpm`.
make PREFIX="$HOME/.local" install
```

On macOS, invoke the final command with `gmake` and use a Python version newer
than the system Python if the ACK checkout requires it.

The initial Juku branch point is upstream commit
`d70c643a5db24007ad6533f92b701fd714a99b7f`. A clean `make` at
that commit builds all eight upstream disk images successfully with ACK's
CP/M target, `cpmtools` 2.23, and `libz80ex` 1.1.21.

## Current implementation

The first CP/M 2.2 bring-up system is now built entirely from source. It uses:

- Digital Research's Intel 8080 CCP at `B400h`;
- Digital Research's Intel 8080 BDOS at `BC00h`, entry `BC06h`;
- the Juku BIOS at `CA00h`;
- the Ekta 3.7 public monitor vectors for console and floppy I/O; and
- two 386K floppy drives, A and B. A RAM disk is deliberately not part of the
  first bring-up system.

All three resident components are assembled in zmac's Intel 8080 mode. The
Digital Research sources additionally use its DRI source-dialect mode. This
avoids the Z80-only ZCPR1/ZSDOS default during hardware bring-up.

The vendored CCP transcription had eight latent separator errors: intended
statements followed semicolons and therefore became comments in zmac's DRI
mode. The Juku branch restores the documented statements, including the
filename scan loop, wildcard count, intrinsic-table bound, and numeric-parser
steps. Without these repairs, commands were read correctly but only the first
filename character reached the FCB (`DIR` became `D`), after which intrinsic
lookup could loop forever. The image check rejects statement separators hidden
in CCP comments so this class of error cannot silently return.

Build the Juku outputs from the repository root:

```sh
make juku-system.bin juku.img
```

The disk also contains `DIAG.COM`, a CP/M wrapper around the shared
non-destructive RAM cell test from the pinned `juku-common` submodule. It tests
private scratch storage, restores every byte, and reports `PASS` or `FAIL`.
Initialize dependencies after cloning with:

```sh
git submodule update --init --recursive
```

The outputs are:

- `juku-system.bin`: the established 10 KiB JUKUSYS/SYSGEN format, suitable
  for Janet network loading;
- `juku.img`: an 800 KiB, double-sided raw image accepted by the Juku emulator
  and physical-disk tooling. Side 0 contains the bootable 386K volume; side 1
  is erased and reserved for a future independent volume.

The disk layout has one easily missed distinction. CP/M's 386K volume is 80
tracks on one side, with 10 physical 512-byte sectors per track. Raw Juku disk
captures are ordered by cylinder and then head. Consequently the volume's
second logical track starts at raw offset `2800h`, and the directory starts at
`5000h`, not at `2800h`. `mksides.py` performs this conversion explicitly.
The zero-based cpmtools skew table `0,2,4,6,8,1,3,5,7,9` is the 512-byte
equivalent of the BIOS's 40-entry 128-byte `TRANS` table.

`check.py`, run automatically while making `juku.img`, verifies the system
container, BIOS placement, system tracks, side interleave, erased second side,
and the expected files through cpmtools.

With the sibling `8080-cosim` checkout on its `master` branch, run the complete
software integration check with:

```sh
make juku-cosim-check
```

Set `JUKU_COSIM_ROOT` only if that checkout is not at `../8080-cosim`. The
check builds the C simulator, cold-boots the image through stock Ekta 3.7,
runs `DIR`, runs transient `STAT` and returns through warm boot, then executes
`SAVE 1 TEST.COM` on a disposable writable copy. It requires the expected
`A>` screen after every case and extracts the resulting 256-byte file through
cpmtools. No source disk image is modified.

## Validation

On 2026-08-12 the generated raw image booted through the unmodified Ekta 3.7
ROM in `8080-cosim`. The run followed the monitor's `TDD` boot path, performed
10,752 WD1793 data-register reads, executed the new CCP/BDOS/BIOS, rendered the
`52K CP/Mish-Juku 2.2` banner, and reached an `A>` prompt.

The repeatable integration check also passes filesystem `DIR`, transient
`STAT`, warm boot back to `A>`, and a persistent `SAVE 1 TEST.COM`. The saved
file survives the emulator close and extracts as 256 bytes. This validates the
CCP parser, BDOS filesystem, BIOS sector translation, RomBios deblocking and
write cache, and emulator write path together. Janet network boot and physical
machine tests remain the next validation stages.

The Juku CCP also adds a deterministic built-in `VER` command. It reports the
CP/Mish Juku 2.2 8080 build, preserves the original Digital Research CCP
attribution, and credits the port and its development tooling without embedding
a host-clock timestamp that would make otherwise identical images differ. Its
source-controlled build date is updated deliberately when the Juku system
identity changes.

## Port plan

1. ~~Add a reproducible, strictly 8080-compatible Juku CP/M 2.2 system as the
   bring-up baseline.~~
2. ~~Validate filesystem reads/writes, console input, transient commands, and
   warm boot in `8080-cosim`.~~
3. Validate `juku-system.bin` through the existing Janet serial-network
   bootstrap and add the cross-repository regression.
4. Test the image on CS00015, first through Janet and then from physical media.
5. Add optional RAM-disk support after the floppy-backed baseline is stable.
6. Reuse the proven hardware layer for a nonbanked CP/M Plus 3.1 port.

## Diskless network mode

The network target is not merely a way to load the resident system. It is a
Juku with no local floppy drive whose A: volume remains attached to the host
for the whole CP/M session. The local-floppy image stays available as the
reference build and as a way to isolate network faults from filesystem faults.

The implemented mode is deliberately two-stage:

1. Stock Ekta 3.7 NetBios loads `juku-net-system.bin` using Janet 1.2 at its proven
   divisor 8 setting: nominal 9600 baud, 8 data bits, odd parity, one stop.
2. The network BIOS takes over the same D11 8251/D57 channel-0 path, retains
   divisor 8 for nominal 9,600 baud, and exposes a host-backed drive A.

BIOS requests use CP/M's native 128-byte record size. Each transaction carries
an operation, sequence number, drive, 16-bit track, logical sector, payload
when writing, and checksum. Replies echo the sequence and status; malformed or
out-of-sequence replies restart the request, and duplicate writes are
idempotent on the host. The host uses the existing flat 400 KiB volume layout,
not WD1793 commands or raw double-sided offsets.

Build and test both variants with:

```sh
make juku-system.bin juku.img juku-net-system.bin \
    juku-net-smoke-system.bin juku-net-smoke.img \
    juku-net-baudtest-system.bin juku-net-baudtest-9600.img
make juku-cosim-check
make juku-net-cosim-check
```

`juku-net-system.bin` is the diskless network image. The network regression
boots it through stock Janet with no FDC image attached to cosim, retains D57
divisor 8, runs `DIR` using 34 remote reads, and runs a writable `SAVE 1
TEST.COM` session using 38 reads and four writes. Both sessions have zero
protocol retries, reach the framebuffer `A>` oracle, and the saved host volume
reopens through cpmtools with a 256-byte `TEST.COM`.

### Monitorless CS00015 network smoke test

`juku-net-smoke-system.bin` and `juku-net-smoke.img` are a matched, read-only
bench pair. The system image has the Digital Research CCP initial-command field
set to `SMOKE`. The small flat network volume contains only `SMOKE.COM`. On
boot, CP/M therefore searches the host-backed A:, reads the transient through
the resident network BIOS, and starts it without keyboard or monitor input.

`SMOKE.COM` calls the readable Intel 8080 player and tune shared with Jukuravi
in `third_party/juku-common/music/`. It plays the same twelve-note, four-bar,
112 BPM phrase already proven on physical CS00015. The player uses only D57
channel 1; the Janet USART clock remains on independent channel 0. Hearing the
complete phrase proves this chain:

```text
Ekta ROM -> Janet bootstrap at 9600 -> CP/M network BIOS at 9600
         -> remote A: directory lookup -> remote SMOKE.COM reads -> execution
```

The automated cosim regression boots this exact pair with no FDC attached. It
requires the 9600 resident takeover, remote disk reads, transient execution at
`0100h`, all 60 expected speaker PIT writes, the exact twelve divisors, and
note-onset timing on the 112 BPM grid before CP/M returns to `A>`.

For the monitorless physical test, start the server before powering or resetting
the Juku:

```sh
../8080-cosim/tools/janet_disk_server.py /dev/ttyUSB0 \
    juku-net-smoke-system.bin juku-net-smoke.img
```

Then type `TN0201` with no Enter at the ROM prompt. No CP/M command is needed.
The host uses 9600 baud, 8 data bits, odd parity, one stop bit throughout. The phrase starts only
after the network volume has been attached and `SMOKE.COM` has been fetched.
If it returns to the unseen `A>` prompt, it remains silent after one phrase.

For physical use, first extract/copy the generated flat volume (the 400 KiB
`+flatdiskimage.img` build artifact) to a convenient working path. Start:

```sh
../8080-cosim/tools/janet_disk_server.py /dev/ttyUSB0 \
    juku-net-system.bin juku-flat.img --writable
```

Then type `TN0201` with no Enter at the Juku ROM prompt. The server bootstraps
at 9600/8O1, retains that rate, repeatedly emits the
`NR` resident-ready marker until the BIOS synchronizes, and then serves A:.
Without `--writable`, write requests return a CP/M disk error and the host image
is unchanged.

Physical CS00015 has completed this full network-disk smoke path at 9600. The
separate automatic BAUDTEST switches rates only after a 9600 marker, announces
readiness at the test rate, and runs eleven independently recoverable
host-to-Juku cases: unpaced payloads of 1, 2, 4, 8, 16, 32, 64, and 133 bytes,
then 133 bytes paced at 0.75, 1.25, and 2.0 ms. Every case starts from a reset
8251, has a bounded inter-byte timeout, reports its received count,
mismatches, checksum state, and PE/OE/FE flags, and waits for an ACK before the
next case. It then checks one continuous 133-byte Juku-to-host packet and
restores 9600. Partial JSON is saved after every case, so a mid-run cable or
power loss preserves the completed evidence.

The exact sweep passes at 9600 and 19,200 in cosim with a wire-rate 8251 model
that latches real one-byte receive overrun. It also passes with character time
scaled to a conservative 1.5 MHz CPU, below CS00015's measured approximately
1.70 MHz execution rate. A negative control deliberately truncates the
unpaced 133-byte case: that case reports timeout while every later paced case,
the reverse packet, and the 9600 return still pass. This proves that foreground
polling has sufficient modeled throughput and that the bench test will not
wedge on its first lost byte.

The 2026-08-12 recoverable physical sweep on CS00015 received the target's
`BRD!`, then passed exact unpaced host-to-Juku payloads of 1, 2, 4, and 16
bytes. The 8, 32, 64, and 133-byte cases stopped after clean prefixes of 7, 9,
12, and 6 bytes, with no mismatches and no 8251 PE/OE/FE flags. A continuous
133-byte Juku-to-host packet passed exactly, while its following single-byte
ACK was not received. This proves that 19,200 and the 8O1 framing work for
short traffic in both directions, but the physical receiver becomes silent at
a history-dependent point until a complete 8251 reset.

That BAUDTEST build unnecessarily rewrote the 8251 command `34h` after every
clean receive. The revised test no longer touches the command register per byte
and preserves errors for the report. Its physical pacing path also uses
`tcdrain(3)` before sleeping, so requested gaps reach the wire rather than
merely separating host `write(2)` calls.

The revised physical run rejected both candidate explanations. Only its
two-byte unpaced case passed; even 133-byte cases with 0.75, 1.25, and 2.0 ms
wire gaps failed after 0, 0, and 2 payload bytes. There were again no
mismatches or PE/OE/FE flags, the reverse 133-byte packet passed, and the final
host ACK failed. The problem is therefore not target polling throughput or the
per-byte command writes. It is now localized to the direction-specific
high-speed receive boundary: external converter/cable integrity, D104
К170УП2 receiver and its supplies/threshold controls, D104.13-to-D11.3, or the
D11 receive half. The stable resident-disk default remains 9600.

CS00014 (Janet source station 09) provides the independent control. It passed
every BAUDTEST case at 9600, including unpaced and paced 133-byte transfers in
both directions, with zero errors. At 19,200 it reproduced the receive-only
failure while sending the reverse 133-byte packet exactly. Adding the same
CALL/RET recovery gap used between every original EktaSoft 8251 control write
did not change the failure. The common CP2102/MAX/cable chain separately works
with DOSRAVI at 57,600, but that is 8N1 rather than Janet's 8O1. A 19,200 8N1
BAUDTEST was therefore used as the parity-specific discriminator.

The 19,200/8N1 discriminator also failed in the same direction. Its first one-
and two-byte frames passed, proving both ends applied 8N1, but longer
host-to-Juku traffic stopped after short clean prefixes; Juku-to-host 133 bytes
still passed exactly. Parity is ruled out.

The first single-boot rate ladder attempted D57 x16 divisors 7, 6, and 5
(approximately 10,989, 12,821, and 15,385 baud). It never reached a test case:
the classic CP2102 accepted and echoed each requested integer through its USB
control request but put the first request into its 14,400-baud hardware bucket,
corrupting the target's `BRD!` marker identically on two attempts. Linux
`termios2/BOTHER` likewise reported the driver's substituted rates. This is a
host-adapter limitation, not CS00014 evidence.

The usable one-boot ladder instead selects CP2102-native 14,400, 16,000, and
19,200 baud. D57 stays in the stock LSB-only BCD mode with divisors 85, 77,
and 64; the 8251 switches from x16 to its documented x1 asynchronous mode,
giving target rates 14,479.6 (+0.55%), 15,984.0 (-0.10%), and 19,230.8
(+0.16%). Each rate runs the same eleven receive cases and reverse 133-byte
packet before the test restores 9600/x16. This changes the 8251 sampling mode,
so it is a rate-boundary discriminator rather than a pure x16 comparison.

CS00014 reached the 14,400/x1 stage and sent its `BRD!` marker and reverse
133-byte frame correctly. The one-byte host frame passed; the correct two- and
four-byte frames carried PE (`08h`), after which frame synchronization was
lost. The run never reached 16,000 or 19,200. This is evidence that x1 is a
poor operating mode for this physical asynchronous path, not a rate threshold.
The partial capture is `cs00014-baudtest-ladder-supported.json`.

A replacement external serial cable then repeated the decisive controls. At
9600/8O1 every one of the eleven host-to-Juku cases, the reverse 133-byte
packet, and the final ACK passed with zero errors
(`cs00014-baudtest-9600-cable-control.json`). At 19,200/x16/8O1 the one-byte
case passed, all longer receive cases stopped after short clean prefixes, the
reverse 133-byte packet passed, and the final ACK failed
(`cs00014-baudtest-19200-x16-new-cable.json`). The result is therefore not
specific to the first cable.

An attempted 19,200/x64 discriminator is deliberately not shipped as a test
image. It retained EktaSoft's D57 mode-3 programming and used divisor 1; the
8253 specifies a minimum count of 2 in modes 2 and 3, so that setup cannot
generate a valid periodic clock. Physical CS00014 returned four zero bytes
instead of `BRD!`, and no cases ran. The simulator had incorrectly accepted
the divisor and was fixed to reject this boundary. Consequently that bench
attempt says nothing about the receiver, and the x64 variant was removed.

The next session is measurement-led rather than another framing sweep. With
the same BAUDTEST image, capture X3.4/D104.4 and D104.13/D11.3 concurrently at
9600 and 19,200, then capture D57.10 and D11.25 at divisors 8 and 4. Also
measure D104 pins 15 (+5 V), 16 (+12 V), and the four threshold-control pins.
This separates input amplitude/grounding, D104 conversion, the TTL RxD node,
and the D11 receive clock before any IC is condemned. The full evidence,
expected waveforms, decision tree, and lower-priority follow-ups are maintained
in `../../../8080-cosim/docs/juku-serial-19200-investigation.md` in a side-by-side
checkout. Until those captures exist, 9600/8O1 remains the only supported
physical resident-disk rate.

For the corrected monitorless CS00015 rate test (station 08), run:

```sh
../8080-cosim/tools/janet_baud_test.py --client 8 --server 2 \
    --result cs00015-baudtest-19200-revised.json /dev/ttyUSB0 \
    juku-net-baudtest-system.bin juku-net-smoke.img
```

Then reset and type `TN0201` without Enter. No ROM change or CP/M command is
needed. On failure, leave the machine on until the sweep completes: the JSON
records the clean burst envelope, pacing threshold, receive count, checksum,
and 8251 error bits. A completely silent server still leaves the ordinary
network BIOS in its polled receive loop; a bounded transaction timeout remains
a separate resident-BIOS robustness improvement.

The CP/Mish default ZCPR1/ZSDOS pair is not the bring-up kernel: ZSDOS states
that it requires a Z80, and ZCPR1 emits Z80-only opcodes. The first Juku build
will use the 8080-compatible Digital Research CCP and BDOS sources already
vendored in CP/Mish. We can later port selected newer functionality without
making the hardware bring-up depend on it.
