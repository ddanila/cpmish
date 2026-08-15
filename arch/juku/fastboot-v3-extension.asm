; Strong-CRC streaming extension for Fast stages v3, v5-v7, and v14.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; The one-record core installs this at 0300h after selecting 19200. V3/v5
; receive the fixed 6656-byte resident system directly; v6/v7/v14 authenticate
; and expand one length-bounded ZX0 stream. V7 embeds its immutable length and
; CRC in the authenticated extension. V14 combines that deterministic,
; receive-before-decode path with overlap-safe marker parsing and an explicit
; payload-ready acknowledgement. A bad stream restarts and is retransmitted in
; full. The compact byte-wise CRC transform is adapted from Aram Perez, IEEE
; Micro, June 1983, pp. 41-50.

USARTDATA       equ     008h
USARTCTL        equ     009h

.ifdef FASTBOOT_CPM3
DESTINATION     equ     07000h
ENTRY           equ     09c00h
SYSTEM_SIZE     equ     04000h
.else
.ifdef FASTBOOT_RAMBIOS
DESTINATION     equ     0b000h
ENTRY           equ     0c600h
SYSTEM_SIZE     equ     02080h
.else
DESTINATION     equ     0b400h
ENTRY           equ     0ca00h
SYSTEM_SIZE     equ     01a00h
.endif
.endif
.ifdef FASTBOOT_ZX0
COMPRESSED      equ     04000h
COMPRESSED_LIMIT equ    01800h
.ifdef FASTBOOT_TIGHT
.ifdef FASTBOOT_V15
PROTOCOL_VERSION equ    15
rx              equ     0173h
.else
.ifdef FASTBOOT_V14
PROTOCOL_VERSION equ    14
rx              equ     0173h
.else
PROTOCOL_VERSION equ    7
rx              equ     016eh
.endif
.endif
.else
PROTOCOL_VERSION equ    6
.endif
.else
.ifdef FASTBOOT_8N1
PROTOCOL_VERSION equ    5
.else
PROTOCOL_VERSION equ    3
.endif
.endif

        org     0300h

session:
        call    send_ready

.ifdef FASTBOOT_ZX0
        ; V6 packet: 'J','Z', length-hi, length-lo, ZX0 data, CRC-hi, CRC-lo.
        ; V7 packet: 'J','Z', ZX0 data; fixed length/CRC live in the extension.
        ; The CRC authenticates the compressed representation; a valid
        ; deterministic stream therefore authenticates its output too.
find_j:
        call    rx
        cpi     'J'
        jnz     find_j
find_z:
        call    rx
        cpi     'Z'
.ifdef FASTBOOT_STREAM_ACK
        jz      stream_header
        cpi     'J'                    ; preserve an overlapping first byte
        jz      find_z
        jmp     find_j
stream_header:
.else
        jnz     find_j
.endif

.ifdef FASTBOOT_TIGHT
        ; V7's authenticated extension embeds the exact payload length and
        ; expected CRC, removing four variable header/trailer bytes and their
        ; parser while retaining retry-safe JZ resynchronisation.
        ; The builder patches this immediate after compression.
        lxi     b,0a55ah
.ifdef FASTBOOT_STREAM_ACK
        ; Confirm only after the fixed count is live. The host sends no body
        ; byte before this acknowledgement, so reception cannot race setup.
        mvi     a,0c6h
        call    tx
.endif
.else
        call    rx
        mov     b,a
        cpi     COMPRESSED_LIMIT/256    ; reject > 6143 bytes
        jnc     session
        call    rx
        mov     c,a
        mov     a,b
        ora     c                       ; reject zero length
        jz      session
.endif

        lxi     h,COMPRESSED
        lxi     d,0                     ; CRC-16/IBM initial value
receive_system:
        call    rx
        mov     m,a
        inx     h
        call    crc_byte_fast
        dcx     b
        mov     a,b
        ora     c
        jnz     receive_system
.ifdef FASTBOOT_TIGHT
        ; The builder patches these two immediates with the expected CRC.
        mvi     a,0a5h
        cmp     d
        jnz     session
        mvi     a,05ah
        cmp     e
        jnz     session
.else
        call    rx
        cmp     d
        jnz     session
        call    rx
        cmp     e
        jnz     session
.endif

        lxi     d,COMPRESSED
        lxi     b,DESTINATION
        call    dzx0
.else
        ; Stream packet: 'J','S', 6656 data bytes, CRC-hi, CRC-lo.
find_j:
        call    rx
        cpi     'J'
        jnz     find_j
        call    rx
        cpi     'S'
        jnz     find_j

        lxi     h,DESTINATION
        lxi     b,SYSTEM_SIZE
        lxi     d,0                     ; CRC-16/IBM initial value
receive_system:
        call    rx
        mov     m,a
        inx     h
        call    crc_byte_fast
        dcx     b
        mov     a,b
        ora     c
        jnz     receive_system
        call    rx
        cmp     d
        jnz     session
        call    rx
        cmp     e
        jnz     session
.endif

        call    send_success_three

        ; Let all three success frames leave D11 before CP/M reinitialises it.
.ifdef FASTBOOT_TIGHT
drain:
        dcr     b
        jnz     drain
.else
        lxi     b,1200
drain:
        dcx     b
        mov     a,b
        ora     c
        jnz     drain
.endif
.ifdef FASTBOOT_8N1
.ifndef FASTBOOT_TIGHT
        call    restore_8o1
.endif
.endif
        jmp     ENTRY

.ifdef FASTBOOT_ZX0
; ZX0 classic-format Intel 8080 decoder by Ivan Gorodetsky, based on the ZX0
; Z80 decoder by Einar Saukas. v7 (2022-04-30), 92-byte forward variant.
; Input: DE = compressed source; BC = decompressed destination.
dzx0:
        lxi     h,0ffffh
        push    h
        inx     h
        mvi     a,080h
dzx0_literals:
        call    dzx0_elias
        call    dzx0_ldir
        jc      dzx0_new_offset
        call    dzx0_elias
dzx0_copy:
        xchg
        xthl
        push    h
        dad     b
        xchg
        call    dzx0_ldir
        xchg
        pop     h
        xthl
        xchg
        jnc     dzx0_literals
dzx0_new_offset:
        call    dzx0_elias
        mov     h,a
        pop     psw
        xra     a
        sub     l
        rz
        push    h
        rar
        mov     h,a
        ldax    d
        rar
        mov     l,a
        inx     d
        xthl
        mov     a,h
        lxi     h,1
        cnc     dzx0_elias_backtrack
        inx     h
        jmp     dzx0_copy
dzx0_elias:
        inr     l
dzx0_elias_loop:
        add     a
        jnz     dzx0_elias_skip
        ldax    d
        inx     d
        ral
dzx0_elias_skip:
        rc
dzx0_elias_backtrack:
        dad     h
        add     a
        jnc     dzx0_elias_loop
        jmp     dzx0_elias
dzx0_ldir:
        push    psw
dzx0_ldir1:
        ldax    d
        stax    b
        inx     d
        inx     b
        dcx     h
        mov     a,h
        ora     l
        jnz     dzx0_ldir1
        pop     psw
        add     a
        ret
.endif

.ifdef FASTBOOT_8N1
.ifndef FASTBOOT_TIGHT
; NETROM2 and the host-backed disk remain at the proven 19200/8O1 framing.
restore_8o1:
        xra     a
        out     USARTCTL
        out     USARTCTL
        out     USARTCTL
        mvi     a,040h
        out     USARTCTL
        mvi     a,05eh
        out     USARTCTL
        mvi     a,035h
        out     USARTCTL
        in      USARTDATA
        ret
.endif
.endif

; CRC-16/IBM reflected polynomial A001h, initial 0000h. Input byte A, CRC DE.
; HL is preserved so this can run directly in the receive/store loop.
crc_byte_fast:
        push    h
        xra     e
        mov     l,a
        add     a
        push    psw
        xra     l
        mov     l,a
        pop     psw
        mvi     a,0
        jpe     crc_parity_even
        mvi     a,3
crc_parity_even:
        jnc     crc_no_carry
        xri     2
crc_no_carry:
        mov     h,a
        rar
        dad     h
        dad     h
        dad     h
        dad     h
        dad     h
        dad     h
        ora     l
        xra     d
        mov     e,a
        mov     d,h
        pop     h
        ret

send_ready:
        lxi     h,ready_frame
        mvi     b,5
        jmp     send_frame

send_success_three:
        mvi     c,3
success_repeat:
.ifndef FASTBOOT_TIGHT
        push    b
.endif
        lxi     h,success_frame
        mvi     b,5
        call    send_frame
.ifndef FASTBOOT_TIGHT
        pop     b
.endif
        dcr     c
        jnz     success_repeat
        ret

send_frame:
        mov     a,m
        call    tx
        inx     h
        dcr     b
        jnz     send_frame
        ret

tx:
        mov     e,a
tx_wait:
        in      USARTCTL
        ani     1
        jz      tx_wait
        mov     a,e
        out     USARTDATA
        ret

.ifndef FASTBOOT_TIGHT
rx:
        in      USARTCTL
        ani     2
        jz      rx
        in      USARTDATA
        ret
.endif

ready_frame:
        db      'J','R',PROTOCOL_VERSION,1
        db      'J' xor 'R' xor PROTOCOL_VERSION xor 1
success_frame:
        db      'J','A',0,0,'J' xor 'A'

extension_end:
.ifdef FASTBOOT_ZX0
.ifdef FASTBOOT_TIGHT
.ifdef FASTBOOT_V15
        .if     extension_end-0300h > 640
        .error  "Fastboot v15 extension exceeds five records"
        .endif
.else
.ifdef FASTBOOT_V14
        .if     extension_end-0300h > 640
        .error  "Fastboot v14 extension exceeds five records"
        .endif
.else
        .if     extension_end-0300h > 256
        .error  "Fastboot v7 extension exceeds two records"
        .endif
.endif
.endif
.else
        .if     extension_end-0300h > 384
        .error  "Fastboot v6 extension exceeds three records"
        .endif
.endif
.else
        .if     extension_end-0300h > 256
        .error  "Fastboot v3 extension exceeds two records"
        .endif
.endif
