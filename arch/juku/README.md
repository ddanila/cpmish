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

CP/Mish also needs the Amsterdam Compiler Kit (ACK) with its `cpm` platform.
Install it under the user prefix so that `~/.local/bin/ack` and the matching
platform files remain together:

```sh
git clone https://github.com/davidgiven/ack.git ~/fun/ack
cd ~/fun/ack
sed -i 's/^PLATS = all$/PLATS = cpm/' Makefile
make PREFIX="$HOME/.local" install
```

The initial Juku branch point is upstream commit
`d70c643a5db24007ad6533f92b701fd714a99b7f`. A clean `make -j$(nproc)` at
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
make -j"$(nproc)" juku-system.bin juku.img
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

## Port plan

1. ~~Add a reproducible, strictly 8080-compatible Juku CP/M 2.2 system as the
   bring-up baseline.~~
2. ~~Validate filesystem reads/writes, console input, transient commands, and
   warm boot in `8080-cosim`.~~
3. Validate `juku-system.bin` through the existing Janet 19,200-baud network
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
2. The network BIOS takes over the same D11 8251/D57 channel-0 path, programs
   divisor 4 for nominal 19,200 baud, and exposes a host-backed drive A.

BIOS requests use CP/M's native 128-byte record size. Each transaction carries
an operation, sequence number, drive, 16-bit track, logical sector, payload
when writing, and checksum. Replies echo the sequence and status; malformed or
out-of-sequence replies restart the request, and duplicate writes are
idempotent on the host. The host uses the existing flat 400 KiB volume layout,
not WD1793 commands or raw double-sided offsets.

Build and test both variants with:

```sh
make -j"$(nproc)" juku-system.bin juku.img juku-net-system.bin
make juku-cosim-check
make juku-net-cosim-check
```

`juku-net-system.bin` is the diskless network image. The network regression
boots it through stock Janet with no FDC image attached to cosim, observes D57
divisor 8 then 4, runs `DIR` using 34 remote reads, and runs a writable `SAVE 1
TEST.COM` session using 38 reads and four writes. Both sessions have zero
protocol retries, reach the framebuffer `A>` oracle, and the saved host volume
reopens through cpmtools with a 256-byte `TEST.COM`.

For physical use, first extract/copy the generated flat volume (the 400 KiB
`+flatdiskimage.img` build artifact) to a convenient working path. Start:

```sh
../8080-cosim/tools/janet_disk_server.py /dev/ttyUSB0 \
    juku-net-system.bin juku-flat.img --writable
```

Then type `TN0201` with no Enter at the Juku ROM prompt. The server bootstraps
at 9600/8O1, switches its serial device to 19,200/8O1, repeatedly emits the
`NR` resident-ready marker until the BIOS synchronizes, and then serves A:.
Without `--writable`, write requests return a CP/M disk error and the host image
is unchanged.

The 19,200 rate is simulator-proven but is not yet a physical-machine claim.
It will be tried on CS00015. The D57 divisor is kept as one BIOS constant so
hardware experiments can fall back or explore faster rates without redesigning
the protocol. The first implementation retries checksum/sequence failures, but
a completely silent server still leaves the BIOS in its polled receive loop;
a bounded timeout is the next robustness improvement.

The CP/Mish default ZCPR1/ZSDOS pair is not the bring-up kernel: ZSDOS states
that it requires a Z80, and ZCPR1 emits Z80-only opcodes. The first Juku build
will use the 8080-compatible Digital Research CCP and BDOS sources already
vendored in CP/Mish. We can later port selected newer functionality without
making the hardware bring-up depend on it.
