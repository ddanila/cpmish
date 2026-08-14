; Strong-CRC streaming extension for Fast stage v3.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; The one-record core installs this at 0300h after selecting 19200/8O1.  The
; extension receives the fixed 6656-byte resident system as one stream.  A
; CRC-16/IBM polynomial check protects execution; a bad stream restarts and
; is retransmitted in full.  The compact byte-wise CRC transform is adapted
; from Aram Perez, IEEE Micro, June 1983, pp. 41-50.

USARTDATA       equ     008h
USARTCTL        equ     009h

DESTINATION     equ     0b400h
ENTRY           equ     0ca00h
SYSTEM_SIZE     equ     01a00h
PROTOCOL_VERSION equ    3

        org     0300h

session:
        call    send_ready

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

        call    send_success_three

        ; Let all three success frames leave D11 before CP/M reinitialises it.
        lxi     b,1200
drain:
        dcx     b
        mov     a,b
        ora     c
        jnz     drain
        jmp     ENTRY

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
        push    b
        lxi     h,success_frame
        mvi     b,5
        call    send_frame
        pop     b
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

rx:
        in      USARTCTL
        ani     2
        jz      rx
        in      USARTDATA
        ret

ready_frame:
        db      'J','R',PROTOCOL_VERSION,1
        db      'J' xor 'R' xor PROTOCOL_VERSION xor 1
success_frame:
        db      'J','A',0,0,'J' xor 'A'

extension_end:
        .if     extension_end-0300h > 256
        .error  "Fastboot v3 extension exceeds two records"
        .endif
