# Plan: CP/M console over the Janet serial link

Status: **FULL SIMULATOR BASELINE IMPLEMENTED, 2026-08-15; PHYSICAL
QUALIFICATION PENDING.** The V15/NetDisk-v3 RAM BIOS negotiates the optional
`N4` capability and multiplexes a remote console over the resident Janet
USART. `JUKU_CONSOLE_PTY` remains the emulator's independent local
screen/keyboard terminal and is used as the byte-exact comparison oracle.

## Why

A physical Juku needs its own screen and keyboard to be usable. With a
console multiplexed onto the existing serial link, a laptop terminal could
drive CS00014/CS00015 over the one cable that already carries the network
disk: no monitor, no keyboard, full session logs, and copy-paste into a
machine that never had it.

## What makes it feasible

`bios.asm` routes every console operation through three ROM calls, so the
entire change is confined to them:

| BIOS entry | RomBios baseline | N4 RAM BIOS |
| --- | --- | --- |
| `CONST` | `ROMCALL CONSTA` | rate-limited remote poll, then local matrix status |
| `CONIN` | `ROMCALL RDCHR` | multiplex remote and local nonblocking status |
| `CONOUT` | `ROMCALL WRCHR` | draw locally, then mirror when enabled |

The transport already exists: the network BIOS owns the 8251, and its disk
protocol carries an operation byte, sequence number, payload and checksum
with bounded retry. Console traffic is new message types on that protocol,
not a second link.

## Implemented decisions

1. **Polling cost.** `CONST` uses one remote turn per 64 local status calls,
   not one turn per spin. `CONIN` polls both remote and local nonblocking
   status so it never commits to a blocking local-only read while a remote key
   may arrive.
2. **Screen mirroring.** `CONOUT` always renders locally first, then mirrors
   the same byte. Local keyboard input remains active alongside remote input.
3. **Host absence.** A console receive has a short 8,192-status-poll bound.
   Failure disables mirroring immediately; local output continues. After 256
   local `CONST` calls the target reprobes, allowing reconnection without a
   reboot. Unsupported N3/v2/v1 hosts never enable the feature.
4. **Rate.** The feature uses the 19,200/8O1 mode-2/count-4 setting already
   proven by sustained disk operation on CS00014 and repeated fastboot/disk
   sessions on CS00015
   (`../../8080-cosim/docs/juku-serial-19200-investigation.md`).
5. **Interaction with netboot.** The console only exists once the resident
   network BIOS is running; the ROM's own boot dialogue stays on the Juku
   screen. That is acceptable, but it means a physical bring-up still needs
   the machine's keyboard for `TN`.

## Protocol and host use

`20h` polls for one byte and `21h` mirrors one output byte. They use the same
`JD` request, sequence, XOR checksum, exact-duplicate replay, transmitter
drain, and bounded response conventions as resident disk operations. An N4
host returns status 0 for no key, status 2 plus one byte for input, and status
1 when unsupported. Duplicate output requests are acknowledged without
printing the byte twice; duplicate polls replay the same consumed key.

The host exposes the feature only when explicitly requested:

```sh
../8080-cosim/tools/janet_disk_server.py \
  --disk-baud 19200 --disk-protocol 3 --console-pty /dev/pts/NN \
  --fast-stage1 juku-fastboot-v15-netdisk-v3.bin \
  --compact-stock-execute --fast-low-latency-guards \
  /dev/ttyUSB0 juku-net-v3-rambio-system.bin juku-net-v2.img
```

## Acceptance

Cosim proves remotely typed `VER`, then locally typed `DIR`, exact equality
between remote and local transcripts, zero disk retries, and complete
framebuffer equality. A second run drops the first remote-poll reply: the
target times out, disables the console, reprobes, consumes all four `VER`/CR
bytes after replies return, and completes local `DIR` without restarting.
The socket-level host test also proves N4 negotiation, key consumption, and
idempotent duplicate input/output handling.

Physical acceptance remains: measure typing latency and repeat disconnect /
reconnect on CS00014 and CS00015. This does not block the completed simulator
implementation.
