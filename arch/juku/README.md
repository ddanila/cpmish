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

## Port plan

1. Add a reproducible, strictly 8080-compatible Juku CP/M 2.2 system as the
   bring-up baseline.
2. Implement console, floppy, warm boot, and optional RAM-disk support using
   the documented Juku ROM interfaces and EKDOS 2.30 disk geometry.
3. Generate both a physical Juku disk image and a Janet network-boot image.
4. Test console, filesystem, warm boot, and existing Juku applications in
   `8080-cosim`, then on CS00015.
5. Reuse the proven hardware layer for a nonbanked CP/M Plus 3.1 port.

The CP/Mish default ZCPR1/ZSDOS pair is not the bring-up kernel: ZSDOS states
that it requires a Z80, and ZCPR1 emits Z80-only opcodes. The first Juku build
will use the 8080-compatible Digital Research CCP and BDOS sources already
vendored in CP/Mish. We can later port selected newer functionality without
making the hardware bring-up depend on it.
