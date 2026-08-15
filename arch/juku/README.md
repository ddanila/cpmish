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

### ACK on macOS/arm64: use the prepared fork branch

Verified 2026-08-13 on macOS 15 (arm64): ACK's Modula-2 front end `em_m2`
aborts with signal 5 wherever it is invoked, so any CP/M build target that
needs Modula-2 fails. This port is C only, so the fix is to drop Modula-2
from the `cpm` platform. Those changes live on a branch of our fork -- clone
it instead of upstream and no editing is needed:

```sh
git clone -b juku https://github.com/ddanila/ack.git ack
cd ack
gmake PREFIX="$HOME/.local" install
```

The branch (`ddanila/ack`, branch `juku`, commit `c7745fc`) carries
`PLATS = cpm` plus three build-file changes: skip `lang/m2/libm2` for the
`cpm` platform, give the CP/M examples a C-only program list, and reduce the
CP/M test sets to `core` (the `bugs` set has one `.mod` test). Every other
platform is untouched, and upstream is added as a fetch-only `upstream`
remote there.

The Pascal runtime is deliberately kept: only Modula-2 is broken, and the
platform's own `core` tests link `pascal.o`, so removing it fails with a
confusing `em_led: can't read .../pascal.o`.

### Submodules

The Juku targets need both submodules; a missing one fails late with a
confusing `No rule to make target
'third_party/juku-common/diag/memory.asm'`:

```sh
git submodule update --init --recursive
```

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

The disk also contains `DIAG.COM`, a CP/M wrapper around the shared diagnostic
cores from the pinned `juku-common` submodule. `DIAG CPU` checks the 8080
ALU/flags, rotates, DAA, register-pair increment/DAD, SP, and PUSH/POP paths;
`DIAG MEM` tests and restores a private 256-byte scratch page; and `DIAG ALL`
runs both. A zero failure mask is `PASS`; a failure prints the structured hex
mask. No argument preserves the original private-memory-test behavior.
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
3. ~~Validate `juku-system.bin` through the existing Janet serial-network
   bootstrap and add the cross-repository regression.~~
4. ~~Test the image on CS00015 through Janet; also qualify CS00014 and the
   native host-backed game disk.~~ Physical-floppy qualification remains
   separate from the network baseline.
5. Do not consume the stock machine's 51K TPA for a RAM disk: its single
   64 KiB RAM bank has no spare backing store. Host-backed A:/B: volumes cover
   the diskless use case. Revisit only for expanded-memory hardware or an
   explicitly TPA-reducing experiment.
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
    juku-net-baudtest-system.bin juku-net-baudtest-9600.img \
    juku-net-baudtest2-system.bin juku-net-baudtest2.img \
    juku-net-mode2-system.bin juku-net-mode2.img \
    juku-net-mode2-soak-system.bin juku-net-mode2-soak.img \
    juku-fastboot-stage1.bin juku-fastboot-v2.bin juku-fastboot-v3.bin \
    juku-fastboot-v4.bin juku-fastboot-v5.bin juku-fastboot-v6.bin \
    juku-fastboot-v7.bin juku-fastboot-v8.bin juku-fastboot-v9.bin \
    juku-fastboot-v10.bin juku-fastboot-v11.bin juku-fastboot-v12.bin \
    juku-fastboot-v13.bin juku-fastboot-v14.bin
make juku-cosim-check
make juku-net-cosim-check
make juku-fastboot-cosim-check
```

`juku-net-system.bin` is the diskless network image. The network regression
boots it through stock Janet with no FDC image attached to cosim, retains D57
divisor 8, runs `DIR` using 34 remote reads, and runs a writable `SAVE 1
TEST.COM` session using 38 reads and four writes. Both sessions have zero
protocol retries, reach the framebuffer `A>` oracle, and the saved host volume
reopens through cpmtools with a 256-byte `TEST.COM`.

`juku-net-mode2-system.bin` is the normal interactive high-speed counterpart:
it has no initial command, reaches the ordinary `A>` prompt, and keeps A:
attached at the CS00014-proven 19,200/8O1 PIT mode-2/count-4 setting.
`juku-net-mode2.img` carries the standard Juku utility set. For a physical
session, work on a copy so writes persist independently of rebuilds:

```sh
cp juku-net-mode2.img cs00014-netdisk.img
../8080-cosim/tools/janet_disk_server.py --disk-baud 19200 \
    --writable --timeout 86400 /dev/ttyUSB0 \
    juku-net-mode2-system.bin cs00014-netdisk.img
```

Then power/reset and type `TN` without Enter. The server learns the client and
destination station numbers from the first valid boot request, so no identity
options are normally needed. The stock ROM bootstrap remains at 9600; only the
resident CP/M disk protocol changes to the proven high-speed clock. The host
saves the working image when the session exits.

An unmodified stock ROM can now reach the same CP/M system substantially faster.
The frozen v1 baseline loads a 558-byte stage through Janet at 9600, then
transfers the 6656-byte resident image as thirteen CRC16-protected 512-byte
blocks at the proven 19200 mode-2/count-4 setting; the separately named later
variants below reduce the stock stage to one record and use streaming:

```sh
../8080-cosim/tools/janet_disk_server.py \
    --fast-stage1 juku-fastboot-stage1.bin --disk-baud 19200 \
    --writable --timeout 86400 /dev/ttyUSB0 \
    juku-net-mode2-system.bin cs00014-netdisk.img
```

This path is deliberately fixed-layout and single-client. Per-block retry,
stream resynchronization, duplicate handling, and a final whole-image CRC are
implemented. `make juku-fastboot-cosim-check` executes the real stage cleanly
and with injected corruption, complete packet loss, duplication, and one lost
target ACK, compares B400h-CDFFh byte-for-byte, and requires entry at CA00h.
Physical CS00015 then passed the complete path and reached the visible CP/M
prompt. Freeze its same-machine comparison as six named baselines:

| Baseline | First valid Janet request to first valid A: request | Frames in stock phase |
| --- | ---: | ---: |
| **Fast stage v6** | **6.214 s** | 18 |
| **Fast stage v5** | **6.551 s** | 18 |
| **Fast stage v3** | **6.915 s** | 18 |
| **Fast stage v2** | **12.999 s** | 42 |
| **Fast stage v1** | **17.508 s** | 42 |
| **Original stock 9600** | **73.873 s** | 330 |

Fast stage v6 used 2.21 s for the stock stage and 3.53 s for its 384-byte
extension, 4826-byte ZX0 stream, and decode. It saves 0.337 s (5.1%) over v5,
0.701 s (10.1%) over v3, and 67.659 s (91.6%, 11.89x) over stock. Fast stage
v5 used 2.23 s for the stock stage and 3.84 s for the 8N1 extension
plus stream, with zero retries. It saves 0.364 s (5.3%) over v3 and 67.322 s
(91.1%, 11.28x) over stock. Fast stage v2 used 8.00 s for the stock stage and
4.39 s for the bulk phase,
with zero retries. V1 used 7.99 s for the stock stage and 8.90 s for the bulk
phase, including one automatically recovered block-0 timeout. All six
baselines used the same image, volume, cable, host, and CS00015 and all reached
the prompt. V3 used 2.21 s for its one-record stock stage and 4.13 s for its
extension plus system stream, with zero retries. It is 1.88x faster than v2,
saving 6.084 s (46.8%), and 10.68x faster than stock, saving 66.958 s (90.6%).
V2 is 1.35x faster than v1, saving 4.509 s (25.8%), and 5.68x
faster than stock, saving 60.874 s (82.4%). Retain every label and result;
future optimizations are new variants. The original command above remains the
fallback after reset.

`juku-fastboot-stage1.bin` is the frozen **Fast stage v1** artifact. Its build
remains byte-exact at 558 bytes with SHA-256
`b600758acf2bc10a068b003caf29d8799be6fa35489af6e23b8277360d334646`.
`juku-fastboot-v2.bin` is the separate, physically proven 560-byte variant. V2 checkpoints a
cumulative image CRC after every block, retaining the prior checkpoint for
duplicate recovery, so the last block is also the final whole-image proof and
the 6656-byte second CRC scan disappears. The host recognizes the version from
the ready marker. Run v2 by substituting its filename in `--fast-stage1`.

The removed scan is 4,297,085 8080 cycles for this image, about 2.53 seconds at
CS00015's measured ~1.70 MHz. V2 also gives the repeated header ACK enough time
to release the half-duplex line, addressing v1's observed block-0 timeout. The
model predicted about 12.8 seconds; the physical CS00015 run measured 12.999
seconds with zero retries and reached the visible CP/M prompt.

`juku-fastboot-v3.bin` is the physically proven **Fast stage v3** artifact. It is
a self-describing 384-byte host artifact, but only its 128-byte executable core
travels through stock Janet at 9600 (one stock data record). The core changes
to proven 19200/8O1 and authenticates the remaining 256-byte extension with a
compact Fletcher guard. That extension receives the fixed 6656-byte system in
one stream, verifies CRC-16/IBM before entry, repeats its success reply three
times, and retries a bad stream in full. Clean and injected-fault cosim both
reach CA00h with B400h-CDFFh byte-exact; the fault case rejects a corrupted
extension, rejects a corrupted system, recovers from one wholly lost stream,
and tolerates a lost first success reply. Its physically tested SHA-256 is
`bf5104c3d7af271a52defa54acf7773daf032461ff303cc04f0fe4e5ba49b22a`.
Run it by substituting `juku-fastboot-v3.bin` in `--fast-stage1`; no ROM change
is required.

`juku-fastboot-v4.bin` is the separate **negotiated 28,800 desk candidate**.
The classic CP2102/AN205 rate table does not provide 25,600; Linux quantizes
that request to the next table entry, 28,800. V4 therefore pairs exact host
28,800 with D57 mode 2/count 43 and D11 x1, about 28,622.5 baud (-0.62%). Its
123-byte one-record core still loads the 381-byte extension at proven 19,200.
The extension requests and acknowledges a bidirectional fast-rate probe before
streaming. If the probe or exact host-rate setup fails, it restores 19,200 and
repeats an acknowledged fallback probe until both ends agree. Both ends return
to 19,200 before NETROM2 starts.

The 512-byte artifact has SHA-256
`15c016492e7a3ec8f8e1666b387ec1f1a74b7f932b087b1bd21a22bd9be0ab9e`.
Clean 28,800, corruption/loss/lost-reply, and forced 19,200 fallback cosim
paths all install B400h-CDFFh byte-exact and enter CA00h. V1-v3 artifacts stay
byte-identical. The expected first A: request is near 5.8 seconds on CS00015.
The attached Silicon Labs CP2102 (`10c4:ea60`) passed exact 28,800/8O1 Linux
`termios2` readback and restored 19,200/8O1 without sending target bytes.

The first physical CS00015 v4 run failed to negotiate 28,800 but proved the
fallback end to end. It restored 19,200, transferred the CRC-valid system with
zero extension/stream retries, reached the visible prompt, and issued the first
A: request at 9.199 seconds (3.77-second stock stage, 4.95-second bulk including
negotiation/fallback). That is 2.284 seconds slower than physical v3, so the
negotiated high-rate path is not a candidate default. The original host log
did not distinguish a lost
target-to-host fast probe from a lost host-to-target ACK/final-ready exchange;
host logging now records that boundary before any diagnostic repeat.

The project therefore freezes 19,200 mode-2/count-4 x16 as the optimization
clock. Its approximately 307.7 kHz D11 input is already near the documented
310 kHz x16 ceiling, the in-spec x1 alternative failed physically, and a
38,400/count-2 x16 experiment would be roughly two times over specification.
Further speed work stays at 19,200. V12 later measured 5.739 seconds on three
clean physical repeats. V13's acknowledged overlapping path booted five of
five times but retried the first stream in four. Three v14 runs were clean at
6.069-6.115 seconds with zero retries, making v14 the production fastboot
baseline. V5 remains the uncompressed control and V4 remains diagnostic
evidence, not a candidate default.

`juku-fastboot-v5.bin` is the physically proven **19,200/8N1 uncompressed
baseline**. It keeps
v3's mode-2/count-4 x16 clock and one-record layout, changes only the extension
and system-stream framing to D11 mode `4Eh`, then drains its success frames and
restores mode `5Eh` before NETROM2. The 384-byte bundle contains a 117-byte
core and 197-byte extension and has SHA-256
`8fa63db50daaf64f8da9025b443cbe0cb3802d985a4ba5c74630435953d628a4`.
Clean and injected-fault cosim passes exercise 8N1, compare all 6656 bytes, and
prove 8O1 restoration at CA00h. Physical CS00015 then completed with zero
extension/stream retries and issued its first A: request at **6.551 seconds**,
matching the 6.55-second prediction. The stock phase took 2.23 seconds and the
extension plus stream 3.84 seconds. This is 0.364 seconds (5.3%) faster than v3;
the prompt and a network `DIR` both worked. Retain byte-identical v3 as the 8O1
fallback.

`juku-fastboot-v6.bin` is the physically proven **19,200/8N1 + ZX0 fastest
variant**. Its stock-loaded core remains one 128-byte record. The core loads a
384-byte high-speed extension containing Ivan Gorodetsky's 92-byte Intel 8080
ZX0 decoder, and the extension receives a length-bounded 4826-byte
ZX0-classic stream protected by CRC-16/IBM. It authenticates the compressed
representation before decoding to B400h-CDFFh, restores 8O1, and enters CA00h;
a corrupt stream is never decoded.

The self-contained 5342-byte host artifact contains a 120-byte core padded to
128, a 313-byte extension padded to 384, a four-byte resident descriptor, and
the compressed payload. Its SHA-256 is
`74826eeb5e95feb6b9f1bed7d7b5957447166a7f3ac2722633e4cff7768babf0`.
The build vendors the BSD-3-Clause ZX0 v2.2 compressor and regenerates the
payload deterministically. The host verifies that the embedded original-image
CRC matches the supplied system image. Clean and injected-fault cosim paths
prove byte-exact decompression, compressed CRC rejection, complete-stream-loss
recovery, lost-success-reply recovery, and 8O1 restoration. Physical CS00015
then completed with zero retries and reached its first A: request at **6.214
seconds** (2.21-second stock phase, 3.53-second high-speed phase); the prompt
and network `DIR` worked. Run it by substituting `juku-fastboot-v6.bin` in
`--fast-stage1`. V3 and v5 remain byte-identical fallbacks.

`juku-fastboot-v7.bin` is the separate **fixed authenticated metadata
candidate**. It retains v6's one-record stock core, 19,200/8N1 path, 4826-byte
ZX0 payload, and authenticate-before-decode guarantee. The exact payload
length and CRC move into the Fletcher-protected extension; the extension reuses
the core's RX routine and lets CP/M's immediate `NETINIT` restore resident 8O1.
It therefore fits in 256 rather than 384 transferred bytes, and the stream
drops its redundant four-byte variable header/trailer.

The self-contained artifact is 5218 bytes: 128-byte core, 256-byte extension,
eight-byte host descriptor, and 4826-byte payload. Its simulation-qualified
SHA-256 is
`bc3897d6d79cfaafd4b747aecc60410b9b1eec6c9296565176c23f38c9677b88`.
The host validates the descriptor's system CRC, payload length, and payload CRC
before transfer. Clean and fault-injected cosim proves byte-exact installation,
corrupt extension/stream rejection, complete-loss retry, and lost-success-reply
recovery. A full continuation through the real BIOS proves the `4Eh` to `5Eh`
handoff, reaches `A>`, and completes `DIR` with 34 reads and zero retries.
The smaller extension/stream plus a safe 20 ms v7 handoff guard predict roughly
**6.09 seconds** to the first CS00015 A: request, about 0.129 seconds below v6.
On 2026-08-15 physical CS00015 then passed the complete v7 path: stock-ROM
bootstrap, 19,200 handoff, visible CP/M prompt, and network `DIR`. This
qualifies the implementation and its short handoff guard. The exact first-disk
timing was not retained. At that stage v6 therefore remained the fastest timed
baseline; later v12 repeats supersede that timing record. Run v7 by substituting
`juku-fastboot-v7.bin` in `--fast-stage1`.

`juku-fastboot-v8.bin` is the separate **interrupt-fed overlapping ZX0 desk
candidate**. It retains v7's one stock record, fixed 4826-byte payload,
CRC-16/IBM, 19,200/8N1 framing, hard CE00h output fence, retry markers, and
three success replies. Its 640-byte extension temporarily replaces the first
three bytes of the writable RomBios `D79Fh` dispatcher with a minimal IR2-only
trampoline, while saving those bytes verbatim. D11 RxRDY then appends the
authenticated stream at 4000h and updates its CRC inside the bounded ISR. Once
256 bytes are buffered, the native ZX0 decoder starts from 4000h while receive
continues. The host inserts a 2 ms gap after `JZ` so this producer handoff is
atomic. Before CP/M entry, v8 requires the exact compressed input pointer,
compressed length and CRC, exact B400h-CE00h output boundary, no USART error,
and restores the saved `D79Fh` bytes before masking the PIC and replying.

The self-contained artifact is 5602 bytes: 128-byte core, 640-byte extension,
eight-byte `Z8` descriptor, and the unchanged 4826-byte ZX0 payload. Its
simulation-qualified SHA-256 is
`ae89fef7dcce9d6ffd329e0862af9be16710c4b703ff9c0a3c444aa184c34c78`.
Clean and fault-injected cosim proves byte-exact installation, corrupted
extension/stream rejection, complete-loss retry, lost-success-reply recovery,
and full CP/M/network `DIR` operation. The latter performs 34 A: reads with
zero retries, restores D11 to BIOS mode `5Eh`, and asserts that `D79Fh` is
byte-exactly restored.

The pinned 1.70 MHz timing model measures v7 at 1,010,204 cycles (0.594 s) from
the final compressed byte to CA00h. V8 needs 203,037 cycles (0.119 s). After
charging v8 for its three additional 128-byte extension records (0.200 s at
the modeled 884 cycles/byte) and the 2 ms marker gap, the deterministic net
gain is **about 273 ms**. This projects roughly **5.82 s** to the first A:
request if the earlier v7 6.09-second estimate holds. Treat both numbers as
desk predictions: v8 still requires a logged CS00015 run, and v6's 6.214 s
remains the fastest exact physical timing. Run v8 by substituting
`juku-fastboot-v8.bin` in `--fast-stage1`.

For the fastest separately identifiable host policy, add
`--compact-stock-execute`. The native server's final execute service is `0Fh`
padded to 127 bytes across three fragments; the unmodified ROM also accepts
the canonical one-fragment `03 0F` form. This reduces a clean one-record stock
stage from 18 to 14 host frames and removes 154 serial bytes including line
turns, a 9600/8O1 wire floor of about 176 ms. Full clean/fault and CP/M `DIR`
cosim paths pass. The `06h` end descriptor and its full fixed descriptor could
not be removed or shortened and remain unchanged. V8 plus this policy projects
roughly **5.64 s**, pending a logged CS00015 run; ordinary stock boot retains
the captured padded execute form by default.

`juku-fastboot-v9.bin` is the separate **polled-marker, exact-extension
physical candidate**. It retains v8's interrupt-fed 4826-byte payload and
concurrent ZX0 decode, but polls the two-byte `JZ` marker through the core
receiver before unmasking IR2. It explicitly services the stale PIC request
left by the polled `Z` during the existing 2 ms host gap, then uses a
payload-only ISR without the idle ring or payload-state branches. Its core
publishes an exact 16-bit
extension length, so the 556-byte extension is no longer padded to 640 bytes.

The artifact is 5518 bytes with SHA-256
`7dd745e67ac400c22a229a796e77dd51239df793ec5375bf9ebc6bd8069de924`.
Clean/fault cosim and a full CP/M `DIR` continuation pass byte-exactly. V9 takes
78,667 cycles from the final compressed byte to CA00h, versus v8's 203,037;
including exact extension transfer it models **117 ms faster than v8** and
**390 ms faster than v7**. Together with compact stock execute this projects
about **5.52 s** to the first disk request. On 2026-08-15 physical CS00015
completed this exact v9 artifact with `--compact-stock-execute`, reached the
visible CP/M prompt, and completed network `DIR`. The run qualifies the
conservative-guard v9 path and compact execute on real hardware; it did not
retain an exact first-request timestamp, so 5.52 s remains a desk projection.
V8 and all earlier artifacts remain byte-identical.

A post-qualification instruction audit also showed why v9's payload ISR exit
jump is intentional. Removing it made the first overlapped decode fail despite
an exact compressed buffer and CRC; retry passed only after the complete input
was resident. The faster ISR returned enough cycles for the decoder to exhaust
the fixed 256-byte producer lead. A separate static-only rearrangement reduced
the bundle to 5505 bytes and passed cosim, but its roughly 6.8 ms wire saving
does not justify replacing the physically qualified hash. Any revisit should
use a newly named artifact and repeat the physical test.

The separately selected host policy `--fast-low-latency-guards` requires
`--compact-stock-execute` and leaves v9 byte-identical. It uses `tcdrain()`
instead of a blind 50 ms stock-output wait and reduces the post-success guard
to 10 ms, while retaining the 20 ms extension and stream guards. The success
guard still covers the three success frames plus target drain. Three repeated
clean runs, injected corruption/loss, and full network `DIR` pass in cosim.
The fixed wait reduction is 10 ms; draining compact execute can save up to
another 26 ms against the old blind wait. The resulting **about 5.48 s**
projection remains a physical timing candidate, not a measured claim.

A physical CS00015 threshold trial with a 5 ms extension guard recovered but
was slower: the extension and stream each retried once, the prompt and `DIR`
still worked, and the first disk request arrived at 10.167 s. The production
default therefore remains 20 ms. Host-side `--fast-extension-guard-ms` exists
only for explicitly named follow-up experiments.

V10-v14 preserve the earlier artifacts and replace timing assumptions with
explicit state transitions. V10's 608-byte extension bounds every ZX0 input read by the
interrupt-fed producer pointer, eliminating the fixed-lead decoder race. V11
adds a raw `C5` acknowledgement after the one-record core receives `A5 3A`.
Repeated CS00015 tests showed why acknowledgement must gate the body: two of
four v11 runs missed the first ACK, but the host sent the extension anyway and
then retried both extension and stream.

V12 uses an overlap-safe header parser and repeats only `00 A5 3A` until `C5`;
no extension body is sent beforehand. Four CS00015 runs had zero extension
retries. The first three reached the first disk request in 5.739, 5.740, and
5.739 seconds. The fourth required two probes and recovered exactly as
designed, then exposed the independent fixed 2 ms `JZ` payload-arm race and
retried that stream once (8.307 seconds total).

V13 makes `JZ` overlap-safe too. After length, CRC, receive-failure flag, input
pointer, saved stack, and IRQ state are initialized, the extension emits raw
`C6`; compressed bytes are withheld until that ACK. The 5582-byte artifact is
125/128 bytes of core, 620 bytes of exact extension, an eight-byte `ZD`
descriptor, and the unchanged 4826-byte payload. SHA-256 is
`7e4e5fcf821c6f16fd41349060650ad20361af4b8f1c77498fbf88488b6c38f9`.
Cosim deliberately truncates the first extension header to `A5` and the first
stream header to `J`, then proves resynchronization, corruption/loss recovery,
3.4 MHz operation, byte-exact RAM, prompt, and network `DIR`.

Five physical v13 boots all succeeded, but four first streams failed CRC and
passed only on complete retransmission. Those four runs also needed the second
extension-header probe; the sole one-probe run was stream-clean. The ideal
USART/PIC model does not fail spontaneously under normal or doubled CPU timing.
A one-shot fault that delays one RxRDY interrupt for over two character times
does reproduce one v13 overrun/retry and recovery. V13 is retained as important
evidence, not promoted as the default.

`juku-fastboot-v14.bin` is the **fully buffered deterministic production
baseline**.
It keeps the overlap-safe `A5 3A`/`C5` and `JZ`/`C6` handshakes but receives all
4826 compressed bytes at 4000h and verifies CRC16/IBM before starting ZX0.
This removes the interrupt-fed producer/decoder race from the bulk data path.
The artifact is 5229 bytes: 125/128 bytes of core, 267 exact extension bytes,
an eight-byte `ZE` descriptor, and the unchanged payload. SHA-256 is
`83fd401af727a3c8c85fbe94d3d5458c71675efd974a0a8734f99987b420980c`.
Clean, partial-header, injected corruption/loss, lost-reply, 3.4 MHz,
byte-exact, prompt, and network `DIR` cases pass. Under the same one-shot RxRDY
delay that forces v13 to retry, v14 remains retry-free. Three physical CS00015
runs reached the first disk request at 6.115, 6.100, and 6.069 seconds with no
extension or stream retry. The first two needed a second extension-header probe
and recovered cleanly. This qualifies v14 and freezes speed optimization here:
future changes need a functional, observability, or demonstrated reliability
benefit rather than a marginal best-case timing gain.

`juku-fastboot-v14-netdisk-v2.bin` is a separately named V14 payload with the
compact NetDisk v2 BIOS; the frozen `juku-fastboot-v14.bin` remains byte-exact.
The matching resident and volume are `juku-net-v2-system.bin` and
`juku-net-v2.img`. The 5273-byte bundle has SHA-256
`23fe0e156541717885d9fa76e9bd288724bdb633dfbcd8cf597e634d30a070a6`.
The host appends `N2` to its existing `NR` handoff marker.
The new BIOS then uses opcode 13h: ordinary records retain the exact v1 reply
size, uniform records carry one byte, and directory records containing four
deleted entries carry no data and expand to `E5` locally. Without `N2`, the
same BIOS falls back to opcode 11h; old BIOS images ignore `N2` and remain
compatible with the current server. Writes still use the proven synchronous
opcode 12h path.

The read-ahead alternative is rejected specifically for this frozen RomBios
layout. The fixed B400h-CDFFh resident image leaves only the audited
CF00h-CFFFh page before the monitor-owned D000h region, not the space that a
cache needs. NetDisk v2 therefore uses no undocumented RAM and does not reduce
the TPA. The independent RAM BIOS described below has a different ownership
boundary and can implement read-ahead safely.

`make juku-netdisk-benchmark` runs V14 twice against the same files. It proves
complete `DIR` and `TYPE README.TXT` transcripts, then runs `RDBENCH.COM`, a
no-console sequential reader for `README.TXT`. At 19,200/8O1 with the 2 ms
reply guard, the modeled initial 32-record directory scan falls from 2.667 to
0.483 seconds (82%), and `DIR` from 0.250 to 0.177 seconds (29%). Full `TYPE`
is byte-for-byte complete and unchanged at 5.918 seconds of disk wire time;
the console is its dominant visible cost. `RDBENCH` changes from 6.252 to
6.179 seconds because only its padding record compresses. Raw records never
grow on the wire.

Run the physical candidate without changing the ROM:

```sh
cd ~/fun/cpmish && make juku-fastboot-v14-netdisk-v2.bin \
    juku-net-v2-system.bin juku-net-v2.img
../8080-cosim/tools/janet_disk_server.py \
    --fast-stage1 juku-fastboot-v14-netdisk-v2.bin \
    --compact-stock-execute --fast-low-latency-guards --disk-baud 19200 \
    --writable --timeout 86400 /dev/ttyUSB0 \
    juku-net-v2-system.bin juku-net-v2.img
```

NetDisk protocol 2 is the server default; `--disk-protocol 1` explicitly
forces the legacy marker/path for fallback qualification. Cosim boots the v2
BIOS against that forced v1 host, reaches the prompt, and completes `DIR` with
the original one-record wire counts.

Three physical CS00015 NetDisk-v2 boots passed on 2026-08-15. All used one
extension probe and one stream probe, had zero retry, and reached the first
opcode-13h disk request at 6.116354, 6.116790, and 6.115778 seconds. The
first-to-last request timestamp span for the 32-record startup directory scan
was 0.771, 0.771, and 0.785 seconds; 30 records used the compact encoding.
`DIR` worked visibly. `RDBENCH` then loaded and read all of `README.TXT` in 75
requests with no retry or error: its complete request span was 6.426 seconds,
and the 70-record file-data portion spanned 6.13 seconds, approximately 1.4
KiB/s of useful payload. This physically qualifies v2 on CS00015 while keeping
V14's deterministic boot behavior.

The bench also exposed two independent usability facts. B: was intentionally
unattached; selecting it produced the expected status-one response, after
which Digital Research BDOS remained in `BDOS ERR ON B: SELECT` and ignored
Ctrl-C. RESET plus a fresh network boot was required. Also, this CS00015's
Space key did not register. Although `=` is a CCP filename delimiter,
`TYPE=README.TXT` cannot replace the intrinsic-command space because the CCP
does not consume that delimiter before parsing the argument. The no-console
reader therefore provided the physical whole-file proof; cosim continues to
prove the complete `TYPE README.TXT` transcript.

Raw evidence is retained in `cs00015-netdisk-v2-run1-20260815.json` through
`run3`, with the derived interactive record in
`cs00015-netdisk-v2-qualification-20260815.json`.

Stock frame tracing also rejects eager post-ACK sending. A normal one-record
request contains 36 client frames after the request, including 26 scans of
other stations. Sending the next fragment before the required directed poll
made the ROM discard/reject frames and increased host output from 14 to 44-58
frames. The captured Janet turn discipline remains intact.

The `NETROM2` BIOS also exposes B: using the original Juku double-sided
geometry: 160 logical tracks, 40 CP/M records per track, 4 KiB allocation
blocks, and about 784 KiB usable capacity. The host accepts a physical 800 KiB
`.JUK` image and converts its cylinder/head interleaving in memory; the source
game image remains unchanged and B: is read-only. A: retains the smaller 386K
geometry and is the only drive affected by `--writable`:

```sh
../8080-cosim/tools/janet_disk_server.py --disk-baud 19200 \
    --writable --drive-b /path/to/J3KGAME2.JUK --timeout 86400 \
    /dev/ttyUSB0 juku-net-mode2-system.bin cs00014-netdisk.img
```

At CP/M's `A>` prompt, enter `B:` and then `DIR`. The published Juku 3000
images are suitable unchanged:

- `J3KGAME2.JUK` (2025) is the strongest general-play default, with Arkanoid,
  Boulder Dash, Bomber Man, Robbo, Tetris, and Warp & Warp among its ports;
- `J3KGAME1.JUK` (2024) is the stronger historical Juku collection, including
  Indy, Zoo, Xonix, Space Attack, and the original graphical Tetris.

They are published by Juku 3000 / Elektroonikamuuseum as
[`J3KGAME1.JUK`](https://elektroonikamuuseum.ee/failid/juku/tarkvara/J3KGAME1.JUK)
and
[`J3KGAME2.JUK`](https://elektroonikamuuseum.ee/failid/juku/tarkvara/J3KGAME2.JUK).
The images are external inputs and are not copied into this repository.

Some programs have companion data/font files, need `MODX` for 80x24 display,
or require a mouse. Serving the complete native disk avoids silently omitting
those dependencies. The focused cosim regression uses the real 2025 image,
selects B:, lists it, loads `TETRIS.COM`, and observes 71 B: reads with no
successful B: write.

Physical CS00014 subsequently passed this `NETROM2` dual-drive setup on
2026-08-13: CP/Mish retained its network A: volume and successfully selected
and used the native `J3KGAME2.JUK` network B:. This closes the initial physical
validation gate for the 160-track DPB, host `.JUK` conversion, and drive-1
protocol path. B: remains intentionally read-only.

Physical CS00015 independently passed the same path on 2026-08-13. It reached
the CP/Mish prompt, listed A: with `DIR`, selected B:, listed the native game
disk with `DIR`, and started `TETRIS.COM` successfully. Together the CS00014
and CS00015 runs validate the complete interactive dual-network-drive path on
both available reference boards.

An initial 2026-08-13 CS00014 session reached the prompt and accepted `DIR`, but
did so very slowly and then filled the screen with vertical-line garbage. The
handoff audit found two independent software faults. NetBios can execute the downloaded
BIOS with an old USART interrupt pending, and its initialization has registered
RomBios service slots 2, 3, and 9. Slot 9 is reached from the ordinary frame
path, so masking only the USART PIC requests does not detach NetBios. An interim
BIOS-owned frame handler also incorrectly replaced `D79F`; that address is the
monitor's generic interrupt stack/memory-mode dispatcher, not a keyboard-vector
trampoline. Bypassing it accounts for the physical video corruption.

The corrected handoff executes `DI` as its first instruction, restores the
three NetBios service slots to their pre-NetBios `RET` entries at
`D773h/D777h/D78Fh`, leaves the RomBios `D79F` dispatcher and IR5 keyboard path
untouched, and updates both the PIC mask and its RomBios `D454h` shadow. Console
status/input/output are again the exact public RomBios calls used by EKDOS 2.30;
only Janet disk I/O is custom. The focused cosim regression boots, types `DIR`
through the physical matrix/RomBios path, completes 34 network reads, reaches a
second `A>` prompt, and asserts the dispatcher, service slots, and PIC
hardware/shadow state.

A fresh CS00014 bench run with the corrected `NETROM1` image then passed. The
stock-ROM bootstrap completed at 9600, CP/Mish switched A: to Janet at
19200/8O1, and the physical keyboard remained responsive. `DIR` completed,
`TYPE README.TXT` exercised sustained sequential disk reads and console output,
and `Ctrl-C` followed by another `DIR` exercised warm boot. The server completed
all requests through sequence `90` with status zero, and the screen remained
clean. This validates the EKDOS-style RomBios console path and corrected NetBios
handoff on real CS00014 hardware.

The pre-fix handoff is now retained as a deliberately broken, simulator-only
negative image. `juku-net-mode2-broken-system.bin` omits the early `DI`, leaves
the NetBios service registrations installed, and omits the coherent PIC
hardware/shadow transition. It must never be used on hardware. In cosim it
reaches the same initial `A>` prompt as the corrected image, but a matrix-typed
`DIR` produces no echo and no disk traffic: the read count remains at the 32
startup directory records. The corrected RomBios control consumes `DIR` and
reaches 35 reads in the immediately following run. The broken checkpoint keeps
the original `D79Fh` bytes, proving that stale NetBios services alone reproduce
the dead-keyboard failure; the historical interim overwrite of `D79Fh` was a
second, independent defect rather than a necessary cause of the input stall.
`make juku-net-cosim-check` and the quicker
`python3 arch/juku/net_cosim_check.py --keyboard-only` require both sides of
this A/B regression.

### RAM-console path

Keep the present 52K `B400h/BC00h/CA00h` RomBios image frozen as the physical
baseline. A RAM-console experiment must be a separately named artifact and
must not revive either historical handoff defect. In particular, it will keep
the corrected NetBios detach sequence and leave the firmware `D79Fh`
dispatcher untouched while any firmware interrupt service remains enabled.

There is not enough honest space to bolt a renderer onto the current layout.
The linked NetDisk-v2 resident image is 6593 of 6656 bytes, leaving 63 bytes in
the stock `B400h..CDFFh` payload. The audited `CF00h..CFFFh` page is only 256
bytes and is too small for a renderer plus a useful font. The planned RAM path
therefore uses a separate 51K layout shifted down by 1 KiB:

| component | RomBios baseline | RAM-console experiment |
| --- | ---: | ---: |
| CCP | `B400h` | `B000h` |
| BDOS | `BC00h` | `B800h` |
| BIOS | `CA00h` | `C600h` |
| exclusive upper boundary | `CE00h` | `CE00h` |

The smaller TPA buys 1024 resident bytes without trespassing into firmware
work RAM or the framebuffer. This is implemented first as the separately named,
experimental `juku-net-v2-ramout-system.bin`. Its legacy `JUKU51` marker tells
the host to send a 7,808-byte executable through the unmodified stock Janet loader:
a 128-byte `0100h` staging copier followed by the complete 7,680-byte resident
payload. The copier installs that payload at `B000h` and enters the relocated
BIOS at `C600h`. The established 52K artifact and its loading rules are
unchanged.

Stage 1 replaces only `CONOUT` with a 40x24 RAM renderer and retains the proven
RomBios `CONST`/`CONIN`, IR5 keyboard scan, and dispatcher. The renderer has an
8x8 public-domain font in a 10-scanline cell, handles CR/LF/backspace, wraps,
scrolls, and implements the `ESC L` clear used by cold boot. Code executes
below the mapped high-ROM window; framebuffer operations disable interrupts,
select all-RAM mode 3, and restore normal mode 1 before returning. Since the
retained RomBios frame service otherwise keeps painting its independently
tracked solid cursor into the new screen, cold boot first uses the documented
firmware `ESC 4` operation to hide that cursor.

`make juku-ram-output-cosim-check` now boots this exact image through stock
Janet, reaches the prompt, types and executes `DIR` through RomBios input, and
finishes with 35 network reads. It asserts the original `D79Fh` dispatcher,
detached NetBios service vectors, mode-3/mode-1 framebuffer brackets, and a
byte-exact framebuffer reference-rendered from the complete captured console
transcript. The pixel oracle caught both an initial clear-loop defect and the
stale firmware cursor; neither is accepted as harmless visual noise. This
Stage-1 artifact is simulator-proven but has not yet been tried on physical
hardware.

Stage 2 is now implemented as `juku-net-v2-rambio-system.bin`. It adds a
polled RAM keyboard matrix scanner and keeps the RAM framebuffer permanently
visible in memory mode 3. The scanner's row/column table is transcribed from
the factory keyboard drawing, includes Shift and Control translation, and
requires release before reporting another key. Cold boot masks every PIC
input, so this baseline needs no RomBios stack, interrupt dispatcher, keyboard
service, frame service, or mapped ROM after takeover. It deliberately leaves
`D79Fh` unchanged and restores the former NetBios service slots to `RET`.
The resident tail occupies `CF00h..D07Fh`. Those last 128 bytes reclaim the
first page of the former RomBios workspace only after the stock staging copier
has executed `DI`; no firmware code or interrupt can then observe it. The
container builder rejects any linked or padded image crossing `D080h`, leaving
`D080h..D7FFh` untouched and the framebuffer at `D800h` clear of code/data.

The new self-describing `JUKURM1` container records load address `B000h`, entry
`C600h`, padded resident length, and CRC16/IBM. The stock Janet host validates
those fields and CRC before building the `0100h` staging copier. The focused
`make juku-ram-bios-cosim-check` regression types `DIR` through the modeled
physical matrix, completes 35 NetDisk reads, compares all 9,600 framebuffer
bytes with an independent transcript renderer, and proves final mode 3, PIC
mask `FFh`, intact `D79Fh`, and detached firmware service vectors.

`juku-fastboot-v15-rambio.bin` carries the same RAM BIOS over the established
fully buffered V14 transport as protocol V15. Its 6,249-byte artifact contains
a 125/128-byte stock core, 267-byte extension, eight-byte `ZF` descriptor, and
a 5,846-byte ZX0 stream expanding to 8,320 bytes at `B000h`. The V15 core puts
its private stack below the compressed buffer; the simulator caught the first
draft overwriting a legacy `B3F0h` stack while expanding the larger image.
Clean transfer, corrupt/lost-stream recovery, delayed-Rx stress, byte-exact
installation, and complete prompt/`DIR` handoff now pass. The final checkpoint
again proves all-RAM mode, all IRQs masked, RAM keyboard input, framebuffer
output, and NetDisk v2 operation. Run the focused matrix with
`make juku-fastboot-v15-cosim-check`.

That matrix also resets the emulated board after byte 900 of the first V15
stream. The stock ROM starts again on the same serial connection, scripted
`TN` is replayed, and the host returns to 9600 request discovery after its
bounded failed exchange. A second V15 transfer then reaches `C600h` byte-exact.
The server permits three complete bootstrap rediscoveries by default, closing
the formerly open automated power-reset/restart case.

Stage 3 is the separately named `juku-net-v3-rambio-system.bin`, carried by
`juku-fastboot-v15-netdisk-v3.bin`. It keeps V15's deterministic transport and
the independent 51K RAM BIOS, but expands the resident through `D47Fh` and uses
the otherwise firmware-owned `D080h..D47Fh` region for three cached records,
the NetDisk-v3 client, and bounded receive/retry state. The added tail remains
well below the framebuffer at `D800h`; V14 and the original RAM-BIOS-v2
boundary are unchanged. This is safe only because cold start has executed
`DI`, masked every PIC input, selected permanent all-RAM mode 3, and detached
all RomBios services.

The larger BIOS also exposed a latent font/buffer collision: the final 14
bytes of the complete `20h..7Dh` font crossed `CE00h`, where the original CP/M
directory buffer could overwrite them. `DIAG ALL` made this visible because
its `|` glyph began correctly and ended with live directory bytes. V15 now
places its uninitialized directory/allocation/check buffers at `D500h..D5FFh`;
the other layouts keep their established addresses. Characters above the font
range render as `?` instead of indexing arbitrary RAM. The pixel oracle covers
the repaired final glyphs byte-for-byte.

The host advertises `NRN3`. Opcode 14h returns up to three records in exact
Juku translated-sector order and may cross a track boundary. Every record has
its track, sector, and one bounded encoding: raw 128 bytes, uniform fill,
deleted-directory fill, or literal prefix plus repeated tail byte. A
CRC16/IBM covers the complete `DJ` response body. Invalid CRC, sequence,
status, record count, or encoding causes the client to repeat the identical
request; writes invalidate the cache and retain the synchronous v1/v2 write
path. The server inserts a 4 ms guard between encoded record descriptors. The
cycle-accurate model showed why this is required: local 8080 fill expansion
takes longer than one wire character, and streaming the next descriptor
immediately can overrun D11's one-byte receive buffer.

Every receive byte now has a bounded 65,536-status-poll wait. A transaction
gets three exact attempts; exhaustion returns BIOS error 1 instead of hanging
CP/M forever. A later disk operation starts a new sequence and can recover
after the host reconnects. The simulator suppresses three complete replies
after a live prompt, observes `Bdos Err On A: Bad Sector`, answers the CP/M
error prompt, and then completes a fresh `DIR` with the same target process.

Negotiation is backward compatible. An `N2` host selects compact one-record
opcode 13h, while a legacy repeated `NR` selects raw opcode 11h. The focused
regression proves a complete prompt and `DIR` with all three hosts: v3 needs 12
requests for at least 35 records, while v2 and v1 each need 35. It also corrupts
the first v3 CRC and proves exactly one retry, then exercises stock Janet,
fastboot V15, byte-exact installation, all-RAM handoff, and v3 `DIR` end to end.
The same path runs `DIAG ALL` and proves both shared CPU and RAM cores. A
scoped emulator injection arms the former CS00015 D1/A12 increment fault only
while the register-pair test runs; `DIAG CPU` must report mask `02` and return
to CP/M, proving the negative path without damaging bootstrap.
Run it with `make juku-netdisk-v3-cosim-check`.

The current v3 fastboot artifact is 6,665 bytes: 125/128 bytes of core, 267
extension bytes, an eight-byte `ZF` descriptor, and a 6,262-byte ZX0 stream
expanding to 9,344 bytes. SHA-256 is
`62da7f352c7fab86b098ec51dbef27d1ee69a2e51219657281b82a1c9f72eaee`.
The V15 loader and host validator alone accept this larger stream below their
8 KiB compressed-buffer boundary; older V6-V14 limits remain frozen.

This is ready for a future physical RAM-BIOS/NetDisk-v3 experiment, but remains
simulator-qualified. Build and serve it with:

```sh
cd ~/fun/cpmish && make juku-fastboot-v15-netdisk-v3.bin \
    juku-net-v3-rambio-system.bin juku-net-v2.img
../8080-cosim/tools/janet_disk_server.py \
    --fast-stage1 juku-fastboot-v15-netdisk-v3.bin \
    --compact-stock-execute --fast-low-latency-guards \
    --disk-baud 19200 --disk-protocol 3 --writable --timeout 86400 \
    /dev/ttyUSB0 juku-net-v3-rambio-system.bin juku-net-v2.img
```

Both RAM artifacts remain simulator-proven experiments, not hardware-qualified
replacements for the frozen V14/RomBios path. The RomBios 52K path remains the
physical baseline throughout.

The native character generator displayed a printable Estonian glyph while the
control-key combination was entered. Preserve the working console baseline for
now; a future console/character-set study should determine whether selectable
native/English glyphs or caret notation is preferable. Verify the original
RomBios convention before changing control-character rendering.

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

Then type `TN` with no Enter at the ROM prompt. A configured physical Juku
takes its station identity from keyboard switch bank S21; use `TN0201` only if
the ROM actually falls through to its `N=` and `S=` prompts. No CP/M command
is needed.
The host uses 9600 baud, 8 data bits, odd parity, one stop bit throughout. The phrase starts only
after the network volume has been attached and `SMOKE.COM` has been fetched.
If it returns to the unseen `A>` prompt, it remains silent after one phrase.

For physical use, first extract/copy the generated flat volume (the 400 KiB
`+flatdiskimage.img` build artifact) to a convenient working path. Start:

```sh
../8080-cosim/tools/janet_disk_server.py /dev/ttyUSB0 \
    juku-net-system.bin juku-flat.img --writable
```

Then type `TN` with no Enter at the Juku ROM prompt (`TN0201` is only the
zero-configuration fallback). The server bootstraps
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

### Resilient BAUDTEST2

`BAUDTST2.COM` is the final software-only diagnostic before that scope work.
It is automatically fetched and started over the proven 9600/8O1 network path
and then runs 68 independently recoverable cases:

- the original increasing-length baseline and an exact 1-through-20 boundary
  hunt;
- 64-byte `00`, `FF`, `55`, `AA`, decrementing, walking-one, walking-zero,
  and deterministic PRBS patterns;
- ten identical PRBS repetitions, idle intervals through 20 ms, four
  preamble patterns, and 8/16/32-byte chunking;
- one byte every 100 ms, which excludes CPU overrun and inter-character
  settling if a failure remains inside a single character;
- a host two-stop-bit control, interpreted only as evidence that added mark
  time helps if it passes;
- a valid 9600/x64/count-2 stage; and
- a 19,200/x16/count-4 8253 mode-2 stage for comparison with stock mode 3.

The target starts with `DI` and performs no display, timer, or system service
inside the receive loop. Each case completely resets D11, announces a
checksummed descriptor repeatedly, searches for its `A5` frame instead of
assuming stream alignment, times out independently, and reports the final
status, cumulative PE/OE/FE, discarded pre-sync bytes, checksum state, and the
index/expected/actual values of the first mismatch. Reports and rate-transition
frames are checksummed and repeated. They require no acknowledgement, so a
lost byte, lost report, stopped host, or disconnected cable cannot strand the
target waiting at a diagnostic rate. After the finite table, it restores D57
mode 3/count 8 and D11 x16/8O1 before returning to CP/M.

Run it for station 09 (CS00014) with:

```sh
../8080-cosim/tools/janet_baud_test2.py --client 9 --server 2 \
    --result cs00014-baudtest2.json /dev/ttyUSB0 \
    juku-net-baudtest2-system.bin juku-net-baudtest2.img
```

Then reset and type `TN` without Enter. Use `TN0201` only if the ROM asks for
the network numbers; use `--client 8` for CS00015.
The JSON is rewritten after every report. On Linux the host also attempts
`TIOCGICOUNT`, retaining driver frame/parity/overrun deltas when the USB-serial
driver implements them; lack of those optional counters is not a test failure.
The complete timestamped session is simultaneously printed to the terminal and
written beside the JSON as `cs00014-baudtest2.log`; use `--log PATH` to select
another location. Stage transitions, overall `N/68` progress, complete case
parameters, payload/report waits, results, JSON checkpoints, counter support,
and final 9600 confirmation are all explicit in that log.

The corrected 2026-08-13 run on physical CS00014 completed all 68 cases and
restored 9600. Stock PIT mode 3/count 4 passed only four of 59 cases; failed
frames stopped after short clean prefixes without PE/OE/FE. The 9600/x64
control also failed. In contrast, every PIT mode 2/count 4 case passed at
19,200/x16, including unpaced 64-byte `55` and PRBS patterns and unpaced
133-byte incrementing and PRBS frames. This localizes the rate failure to the
D57-to-D11 receive-clock waveform/edge interpretation rather than serial-line
bandwidth, host pacing, parity, CPU service latency, or a generic D11 receive
failure.

### Monitorless 19,200/mode-2 network-disk soak

`juku-net-mode2-soak-system.bin` moves the resident network BIOS—not the stock
ROM bootstrap—to the physically proven D57 mode 2/count 4 clock. It remains a
separate experimental image; the supported normal network build stays at
9600/mode 3. Its initial `M2SOAK.COM` creates an 8 KiB file on host-backed A:,
writes 64 changing 128-byte patterns, closes and reopens it, reads and verifies
every byte, deletes the temporary file, and emits `M2PASS!`. It then plays the
smoke tune as a monitorless PASS indication. Any file or byte error emits
`M2FAIL!`, halts, and does not play the tune.

For CS00014 (station 09), run:

```sh
../8080-cosim/tools/janet_mode2_soak.py --client 9 --server 2 \
    --result cs00014-mode2-soak.json /dev/ttyUSB0 \
    juku-net-mode2-soak-system.bin juku-net-mode2-soak.img
```

Then power/reset the machine and type `TN` without Enter. The host bootstraps
at 9600/8O1, switches its own UART to 19,200 when the ROM load completes, and
serves a writable in-memory copy of the volume. Console output is timestamped
and duplicated to `cs00014-mode2-soak.log`; JSON is updated at the bootstrap,
disk, and final states. Success requires the target's marker, at least 64
writes, at least 64 reads, and the audible tune. The host restores its UART to
9600 on exit; resetting the Juku likewise restores the stock ROM setting.

Physical CS00014 passed this complete test on 2026-08-13. The stock bootstrap
loaded 6,784 bytes at 9600 with 161 positive acknowledgements and no rejects.
At 19,200/mode 2 the resident disk completed 108 reads and 67 writes with zero
retries, closed/reopened and byte-verified all 8 KiB, deleted the file, emitted
`M2PASS!`, and played the tune. Linux reported zero frame, parity, overrun,
buffer-overrun, and break counter deltas. The source volume hash remained
unchanged because the host served a writable in-memory copy.

The timestamped disk phase carried 22,400 bytes of aggregate 128-byte record
payload in approximately 16–17 seconds, about 1.3–1.4 kB/s. With 8O1 framing,
each read or write transaction consumes 142 wire bytes; including the current
2 ms reply guard, the protocol ceiling is about 1.54 kB/s. The measured result
is therefore roughly 86–91% of the present protocol limit. An isolated 8 KiB
sequential transfer should take about six seconds before directory overhead.
The slower part is still the stock bootstrap: its 6,784-byte image took about
81 seconds because Janet uses many small acknowledged turns. Boot-protocol
optimization is independent of the already-running resident disk.

### Boot-speed tracks

Preserve two distinctly named paths rather than replacing the archival one:

1. **Original stock 9600:** optimize the host server for the unmodified
   stock-ROM Janet protocol. Keep
   all five archived systems byte-exact and retain physical CS00014/CS00015
   compatibility while profiling and reducing avoidable host waits, poll
   latency, and USB-UART scheduling overhead. The CS00014 baseline is 6,784
   bytes in about 81 seconds, 334 transmitted frames, 161 positive ACKs, and
   zero rejects.
2. **Fast stage v1:** the first versioned bulk protocol is implemented. A
   558-byte stage-1 loader
   arrives through stock Janet at 9600, then the already proven 19,200/8O1
   mode-2/count-4 setting carries thirteen 512-byte CRC-protected blocks. This
   keeps the stock ROM usable without spending 81 seconds transferring the
   complete resident image through its chatty protocol. A custom ROM may enter
   the same bulk loader directly later.

The fixed single-client path has sequence fields, bounded retry and
resynchronization, duplicate handling, final whole-image verification, and a
fixed B400h/6656-byte/CA00h handoff. Compare ACK-per-block with a small window
and add compression only if the physical end-to-end benchmark improves. At
19,200 the 6,656-byte bulk wire minimum is about 3.8 seconds; target 4–6 seconds
for the bulk phase initially. Keep production fastboot at 19,200: the in-spec
x1 route failed physically and mode-2/count-2 x16 would exceed the USART clock
limit by about two times.
The high-speed path must always leave a clean fallback to stock 9600 Janet.

The physical v2 result changed the priority order: its five-record stock stage
took 8.00 seconds, while the whole high-speed bulk phase took only 4.39
seconds. The next distinct **Fast stage v3** experiment therefore uses one
stock 128-byte record only. That core selects proven 19200/mode 2, validates a
compact low-RAM extension sent at high speed, and transfers the fixed resident
system as one CRC-protected stream. A bad stream is retried in full. This
removes roughly four stock records (about 5.5 measured seconds) and twelve
block turnarounds while leaving v1/v2 unchanged as stronger fine-grained retry
baselines.

V3's system CRC uses the compact byte-wise 8080 method documented in the June
1983 IEEE Micro study; its table-free 43-byte implementation was measured
nearly four times faster than bit-at-a-time CRC. The original 25,600 proposal
is not usable with this classic CP2102 because its AN205 table quantizes the
request to 28,800. V4 instead uses D57 mode 2/count 43 and D11 x1 (about
28,622.5 baud, -0.62% against host 28,800). It retains 19,200 automatically if
the bidirectional rate probe fails. Count 3/x16 remains invalid because it
exceeds the КР580ВВ51А's documented 310 kHz x16 input-clock maximum. The
physical x1 negotiation also failed, so higher baud is retired pending new
electrical evidence.

Compression follows the uncompressed baselines. On the exact current
6656-byte image, ZX0 classic reaches 4826 bytes and its real 92-byte 8080
decoder takes 993,353 modeled cycles, or 0.584 seconds at CS00015's measured
1.70 MHz. At v7's actual 19200/8N1 framing, its stream plus decode takes about
3.098 seconds.

A post-v7 cycle audit also ran byte-exact Intel 8080 decoders for ZX1, ZX2,
LZ4, Exomizer P43/P47T4, and a conservative format-derived LZSA2 benchmark.
None beats ZX0 after both wire time and 128-byte extension padding are counted:
ZX2 is about 93 ms slower, LZ4 184 ms slower, ZX1 49 ms slower, ratio-mode
LZSA2 175 ms slower, and Exomizer at least 990 ms slower. LZSA2's former
external 8080 source repository has disappeared; an optimized replacement
that needs one extra extension record would have to finish below roughly
612,000 cycles merely to tie ZX0, versus 795,228 for the conservative passing
benchmark. The detailed measurements and source provenance are retained in
`8080-cosim/docs/janet-fastboot.md`.

ZX0 is therefore the fastest measured and layout-valid choice, not merely the
smallest-stream choice. V6 implements it and measured 6.214 seconds to the
first A: request on CS00015, with the visible prompt and `DIR` proven. This
beats v5 by 0.337 seconds and v3 by 0.701 seconds. V7 retains ZX0 while removing
one extension record and is physically qualified. Later v12 timing, v13
explicit handshakes, and v14's deterministic buffered control build on this
same ZX0 choice; prior variants remain unchanged.

V3 is now implemented: its assembled core is 117/128 bytes and extension is
172/256 bytes. Clean cosim loads only one stock data record, verifies
the extension and strong-CRC stream, installs all 6656 bytes byte-exact, and
enters CA00h. The injected-fault run also rejects a corrupt extension and
stream, recovers after total stream loss, and accepts the second of three
success replies when the first is lost. The later V15 reset regression resets
the target during transfer, rediscovers its fresh stock request, and completes
the retry on the same connection. The first physical CS00015 attempt
authenticated the extension, then
exposed the host's one-second USB serial write-room timeout while queuing the
long stream. Granting only that stream a ten-second stall allowance adds no
intentional delay. After reset, the second run reached the visible prompt with
18 stock frames, zero retries, a 2.21-second stage, a 4.13-second high-speed
phase, and the first valid A: request at 6.915 seconds. Broader qualification
still requires ten consecutive cold/warm boots on both CS00014 and CS00015
with timings, retries, and UART errors saved.

The regression runs all 68 ideal cases and a negative control that truncates
case 7. The truncated case times out, every later case still completes, and
the target restores 9600. Physical receive failures are diagnostic results and
therefore do not make the host command fail; host/protocol failures do.

The first CS00014 launch reached `B2S!` but the host stopped before case 0: its
optional Linux `TIOCGICOUNT` probe supplied a 19-int buffer for the 20-int
`serial_icounter_struct` ABI and Python rejected the kernel result. No physical
BAUDTEST2 case ran, so this is not board evidence. The host now uses the full
buffer, contains unsupported or malformed optional ioctls, and permanently
regresses that boundary before the physical retry.

For the corrected monitorless CS00015 rate test (station 08), run:

```sh
../8080-cosim/tools/janet_baud_test.py --client 8 --server 2 \
    --result cs00015-baudtest-19200-revised.json /dev/ttyUSB0 \
    juku-net-baudtest-system.bin juku-net-smoke.img
```

Then reset and type `TN` without Enter (`TN0201` only if prompted). No ROM
change or CP/M command is needed. On failure, leave the machine on until the sweep completes: the JSON
records the clean burst envelope, pacing threshold, receive count, checksum,
and 8251 error bits. A completely silent server still leaves the ordinary
network BIOS in its polled receive loop; a bounded transaction timeout remains
a separate resident-BIOS robustness improvement.

The CP/Mish default ZCPR1/ZSDOS pair is not the bring-up kernel: ZSDOS states
that it requires a Z80, and ZCPR1 emits Z80-only opcodes. The first Juku build
will use the 8080-compatible Digital Research CCP and BDOS sources already
vendored in CP/Mish. We can later port selected newer functionality without
making the hardware bring-up depend on it.
