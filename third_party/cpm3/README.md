# Digital Research CP/M Plus 3.1 inputs

The binary inputs in this directory come from John Elliott's Unix CP/M 3.1
release dated 2026-06-07:

- upstream: <https://www.seasip.info/Cpm/software/dri.html>
- archive: `cpm3bin_unix.zip`
- archive SHA-256:
  `ec24f6e1fa173d33bcd2555dfae8296471fc8ea144c72e8cbe2166971451da82`

`ccp.com`, `bdos3.spr`, and `gencpm.dat` are copied byte-for-byte from that
archive. `gencpm.dat` supplies the upstream non-banked defaults; the
regeneration script deliberately overrides its memory-top answer with `9Fh`.
`scb.asm` is copied from the matching `cpm3src_unix.zip` source archive
(SHA-256 `d90cda1f25112ace3b436c4054304ace423331caa1f034c44f26698728a9fdb7`).

`cpm3.sys` was generated from those inputs, the source-controlled Juku
`cpm3-bios.asm`, and the DRI RMAC/LINK/GENCPM tools with a non-banked 9Fh
memory top. The generated map is:

```
BIOS3.SPR  9C00h  0400h
BDOS3.SPR  7D00h  1F00h
```

This deliberately leaves `A000h..AFFFh` for the project-owned Juku hardware
adapter and `B000h..B409h` for its runtime state. It provides a conservative
31 KiB TPA baseline with no overlap; a later native CP/M 3 hardware BIOS can
reclaim that gap without changing the verified baseline.

Regenerate the checked-in SYS file with ZXCC and a directory containing the
DRI `RMAC.COM`, `LINK.COM`, and `GENCPM.COM` development tools:

```sh
arch/juku/regenerate_cpm3.py --zxcc /path/to/zxcc \
    --tools /path/to/cpm3-tools
```

The recipe converts both assembler sources to CP/M line endings, assembles the
Juku BIOS and standard SCB module, links `BIOS3.SPR`, answers GENCPM
deterministically, and rejects any map other than BIOS `9C00h`/BDOS `7D00h`.
The current output SHA-256 is
`60f9da29c77599a08639fdf3236205c5ba4431301d66dbb46b7f5dd22d206c1f`.

The Juku BIOS source is BSD-2-Clause project code. CP/M and its derivatives
are distributed under the current DRDOS grant reproduced in `LICENSE.md`.
