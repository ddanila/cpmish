# Plan: CP/M console over the Janet serial link

Status: **PLAN ONLY, 2026-08-13.** Nothing here is implemented. The
emulator-side alternative is already available and is what to use for manual
testing today: `JUKU_CONSOLE_PTY` in cosim plus
`../8080-cosim/tools/juku_run.py` give an attachable terminal without
touching firmware. This document describes the firmware feature that would
also work on real hardware.

## Why

A physical Juku needs its own screen and keyboard to be usable. With a
console multiplexed onto the existing serial link, a laptop terminal could
drive CS00014/CS00015 over the one cable that already carries the network
disk: no monitor, no keyboard, full session logs, and copy-paste into a
machine that never had it.

## What makes it feasible

`bios.asm` routes every console operation through three ROM calls, so the
entire change is confined to them:

| BIOS entry | today | with this plan |
| --- | --- | --- |
| `CONST` | `ROMCALL CONSTA` | ask the host whether a key is pending |
| `CONIN` | `ROMCALL RDCHR` | fetch one key from the host |
| `CONOUT` | `ROMCALL WRCHR` | send the character to the host (and optionally still draw it) |

The transport already exists: the network BIOS owns the 8251, and its disk
protocol carries an operation byte, sequence number, payload and checksum
with bounded retry. Console traffic is new message types on that protocol,
not a second link.

## Design questions to settle first

1. **Polling cost.** The Juku is always the initiator, and CCP calls `CONST`
   continuously. A round trip per idle poll would saturate the link. The
   likely answer is to piggyback a "key pending" flag on every disk reply and
   only spend a round trip when it is set, with a slow floor poll (say 20/s)
   when no disk traffic is flowing.
2. **Screen mirroring.** If `CONOUT` only goes to the host, a physical
   machine looks dead. Default should probably be both: draw locally *and*
   send, with a mode byte to disable one.
3. **Host absence.** If the host disappears mid-session the machine must not
   hang: `CONST` should fail closed (no key), `CONOUT` should time out and
   fall back to screen-only rather than block CP/M forever.
4. **Rate.** At 9600/8O1 a full 40x24 redraw is about a second. This feature
   wants the 19,200/8O1 mode-2/count-4 setting proven on CS00014; confirming
   it on CS00015 is a prerequisite, not a nicety
   (`../../8080-cosim/docs/juku-serial-19200-investigation.md`).
5. **Interaction with netboot.** The console only exists once the resident
   network BIOS is running; the ROM's own boot dialogue stays on the Juku
   screen. That is acceptable, but it means a physical bring-up still needs
   the machine's keyboard for `TN`.

## Smaller first step

**Output-only mirroring.** Add just the `CONOUT` message: the machine keeps
its own keyboard, and the host gains a live transcript of the session. That
sidesteps every polling question, is a handful of instructions in `CONOUT`,
and already delivers logging and remote observation. Input can follow once
the polling design is measured.

## Acceptance

Whatever lands must show, in cosim first and then on both physical machines:
typing latency measured (not guessed), a session that survives the host
disconnecting and reconnecting, no regression in the disk protocol's retry
counters, and the existing network regressions still byte-exact.
