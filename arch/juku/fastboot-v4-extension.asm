; Negotiated-rate streaming extension for Fast stage v4.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; Entry is at proven 19200/8O1. The host and target perform a bidirectional
; probe at nominal 28800: D57 mode 2/count 43 and D11 x1 produce about 28622
; baud, a -0.62% mismatch. If the probe ACK is absent or malformed, the target
; returns to 19200 and repeatedly advertises the fallback until acknowledged.

USARTDATA       equ     008h
USARTCTL        equ     009h
PITCOUNT0       equ     018h
PITCTL          equ     01bh

DESTINATION     equ     0b400h
ENTRY           equ     0ca00h
SYSTEM_SIZE     equ     01a00h
PROTOCOL_VERSION equ    4

        org     0300h

start:
        mvi     d,'R'                   ; request negotiated-rate command
        mvi     c,2
        call    send_control

wait_command:
        call    rx
        cpi     'J'
        jnz     wait_command
        call    rx
        cpi     'F'
        jnz     wait_command
        call    rx
        cpi     PROTOCOL_VERSION
        jnz     wait_command
        call    rx
        cpi     1
        jnz     wait_command
        call    rx
        cpi     'J' xor 'F' xor PROTOCOL_VERSION xor 1
        jnz     wait_command

        call    drain                   ; release the 19200 command bytes
        call    set_fast
        mvi     a,1
        sta     rate_flag
        call    send_probe
        call    receive_probe_ack
        jnc     stream_session

        ; The high-rate bidirectional probe failed. Return to the proven rate
        ; and keep probing there so a host which was listening at 28800 can
        ; switch back without racing a one-shot fallback marker.
        call    set_slow
        xra     a
        sta     rate_flag
fallback_probe:
        call    send_probe
        call    receive_probe_ack
        jc      fallback_probe

stream_session:
        call    send_stream_ready

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
        lxi     d,0
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
        jnz     stream_session
        call    rx
        cmp     e
        jnz     stream_session

        call    send_success_three
        call    drain
        call    set_slow                ; resident NETROM2 always uses 19200
        jmp     ENTRY

; Return carry clear only for J,K,04,rate,xor received within bounded time.
receive_probe_ack:
        lda     rate_flag
        ora     a
        lxi     h,slow_ack_frame
        jz      ack_selected
        lxi     h,fast_ack_frame
ack_selected:
        mvi     c,5
ack_byte:
        mov     e,m
        call    rx_timed
        jc      probe_bad
        cmp     e
        jnz     probe_bad
        inx     h
        dcr     c
        jnz     ack_byte
        ora     a                       ; clear carry
        ret
probe_bad:
        stc
        ret

; About 0.2 seconds at the measured CS00015 CPU rate when no byte arrives.
rx_timed:
        mvi     d,32
rx_outer:
        mvi     b,0
rx_poll:
        in      USARTCTL
        ani     2
        jnz     rx_timed_ready
        dcr     b
        jnz     rx_poll
        dcr     d
        jnz     rx_outer
        stc
        ret
rx_timed_ready:
        in      USARTDATA
        ora     a
        ret

send_probe:
        lda     rate_flag
        mov     c,a
        mvi     d,'Q'
        jmp     send_control

send_stream_ready:
        lda     rate_flag
        mov     c,a
        mvi     d,'R'

send_control:
        mvi     a,'J'
        call    tx
        mov     a,d
        call    tx
        mvi     a,PROTOCOL_VERSION
        call    tx
        mov     a,c
        call    tx
        mov     a,d
        xra     c
        xri     'J' xor PROTOCOL_VERSION
        jmp     tx

send_success_three:
        mvi     d,'A'
        mvi     c,0
        mvi     b,3
success_repeat:
        call    send_control
        dcr     b
        jnz     success_repeat
        ret

set_fast:
        mvi     b,043h                  ; 1.230769 MHz / 43 = 28622.5
        mvi     e,05dh                  ; x1/8O1
        jmp     set_rate

set_slow:
        mvi     b,4                     ; 19200 x16
        mvi     e,05eh                  ; x16/8O1
set_rate:
        mvi     a,015h
        out     PITCTL
        mov     a,b
        out     PITCOUNT0
reset_usart:
        xra     a
        out     USARTCTL
        out     USARTCTL
        out     USARTCTL
        mvi     a,040h
        out     USARTCTL
        mov     a,e
        out     USARTCTL
        mvi     a,035h
        out     USARTCTL
        in      USARTDATA
        ret

drain:
        ; About 56 ms on CS00015: enough for the host's exact-rate ioctls
        ; after tcdrain, and enough for all repeated success bytes to leave.
        lxi     b,4000
drain_loop:
        dcx     b
        mov     a,b
        ora     c
        jnz     drain_loop
        ret

; CRC-16/IBM reflected polynomial A001h, initial 0000h. Input A, CRC DE.
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

fast_ack_frame:
        db      'J','K',PROTOCOL_VERSION,1
        db      'J' xor 'K' xor PROTOCOL_VERSION xor 1
slow_ack_frame:
        db      'J','K',PROTOCOL_VERSION,0
        db      'J' xor 'K' xor PROTOCOL_VERSION
rate_flag:
        db      0

extension_end:
        .if     extension_end-0300h > 384
        .error  "Fastboot v4 extension exceeds three records"
        .endif
