; Monitorless network-boot success indicator for Juku CP/M.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; This transient is intentionally silent on the console. Loading and running
; it from A: proves that the resident network BIOS can find and read a COM
; file after the stock ROM bootstrap. D57 channel 0 remains the Janet UART
; baud clock; this program touches only channel 1, which drives the speaker.

        org     0100h

start:
        call    smoke_play
        ret

; The player and physical-CS00015-proven phrase are shared with Jukuravi so
; the two monitorless tests cannot silently acquire different behavior.
        include "smoke-player.asm"
        include "smoke-table.asm"

        end     start
