; Independent 51K RAM BIOS with CRC-protected three-record NetDisk v3.
NETWORK equ     1
NETWORK19200 equ 1
; Keep the v2 reply decoder linked for negotiated N2 fallback.
NETWORKV2 equ   1
NETWORKV3 equ   1
NETWORKCONSOLE equ 1
RAMCONSOLE equ  1
RAMKEYBOARD equ 1
        include "bios.asm"
