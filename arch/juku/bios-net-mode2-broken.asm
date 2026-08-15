; Test-only reconstruction of the pre-fix network handoff.
;
; Never use this image on hardware.  It deliberately leaves NetBios interrupt
; services attached while CP/M starts so cosim can retain the historical
; CS00014 failure as a negative regression.
NETWORK equ     1
NETWORK19200 equ 1
BROKEN_NET_HANDOFF equ 1
        include "bios.asm"
