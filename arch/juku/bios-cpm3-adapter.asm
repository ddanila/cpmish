; CP/M 2-compatible hardware adapter used by the non-banked CP/M Plus BIOS.
; It retains the tested RAM console, keyboard and Janet NetDisk-v3 code at
; A000h, with runtime state above it at B000h and the CP/M 3 system below it.
CPM3ADAPTER equ 1
NETWORK equ     1
NETWORK19200 equ 1
NETWORKV2 equ   1
NETWORKV3 equ   1
NETWORKCONSOLE equ 1
RAMCONSOLE equ  1
RAMKEYBOARD equ 1
        include "bios.asm"
