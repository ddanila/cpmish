; Stock-ROM-compatible high-speed Juku bootstrap stage.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; The unmodified Janet 1.2 ROM loads this program at 0100h/9600 baud.  It
; immediately takes exclusive ownership of D57 channel 0 and D11, switches to
; the physically proven 19200/8O1 mode-2/count-4 setting, and installs the
; fixed 52K CP/M resident image as thirteen independently retryable 512-byte
; blocks.  The code remains below B400h while the destination is B400h-CDFFh.

USARTDATA       equ     008h
USARTCTL        equ     009h
PITCOUNT0       equ     018h
PITCTL          equ     01bh
PICMASK         equ     001h
PICSHADOW       equ     0d454h

DESTINATION     equ     0b400h
ENTRY           equ     0ca00h
BLOCK_SIZE      equ     0200h
BLOCK_COUNT     equ     13
.ifdef FASTBOOT_V2
PROTOCOL_VERSION equ    2
.else
PROTOCOL_VERSION equ    1
.endif

        org     0100h

start:
        di
        lxi     sp,0b3f0h
        mvi     a,0ffh
        out     PICMASK
        sta     PICSHADOW

        ; D57 channel 0: LSB-only, BCD, mode 2, count 4.  This exact setting
        ; passed sustained bidirectional traffic on CS00014 and CS00015.
        mvi     a,015h
        out     PITCTL
        mvi     a,4
        out     PITCOUNT0
        call    init_usart

session:
        call    send_ready
        call    receive_header
        jc      session
        lxi     h,DESTINATION
        shld    next_address
        xra     a
        sta     next_sequence
.ifdef FASTBOOT_V2
        lxi     h,0ffffh
        shld    current_crc
        shld    previous_crc
.else
        mvi     a,BLOCK_COUNT
        sta     blocks_left
.endif
        mvi     a,0ffh
        mvi     c,0
        call    send_reply_three       ; header accepted despite one lost reply

block_loop:
        call    receive_block
        jc      block_loop
.ifdef FASTBOOT_V2
        lda     next_sequence
        cpi     BLOCK_COUNT
        jnz     block_loop

        ; V2 checkpoints the cumulative image CRC after every accepted block.
        ; The final guard is therefore constant-time rather than a second scan.
        lhld    current_crc
        mov     d,h
        mov     e,l
.else
        lda     blocks_left
        dcr     a
        sta     blocks_left
        jnz     block_loop

        ; A valid CRC on each block protects retries.  Recompute one CRC over
        ; the installed image as a final guard against address/state errors.
        lxi     h,DESTINATION
        lxi     b,BLOCK_SIZE*BLOCK_COUNT
        lxi     d,0ffffh
whole_crc_loop:
        mov     a,m
        inx     h
        call    crc_byte
        dcx     b
        mov     a,b
        ora     c
        jnz     whole_crc_loop
        lda     expected_crc_hi
        cmp     d
        jnz     whole_bad
        lda     expected_crc_lo
        cmp     e
        jnz     whole_bad
.endif

        mvi     a,BLOCK_COUNT
        mvi     c,0
        call    send_reply_three       ; protect the irreversible entry handoff
        jmp     ENTRY

whole_bad:
        mvi     a,BLOCK_COUNT
        mvi     c,2
        call    send_reply
        jmp     session

; Header: 'J','H',version,block-count=13,whole-crc-hi,whole-crc-lo,xor.
receive_header:
        mvi     b,'H'
        call    find_magic
        rc
        mvi     c,'J' xor 'H'
        call    receive_xor_byte
        rc
        cpi     PROTOCOL_VERSION
        stc
        rnz
        call    receive_xor_byte
        rc
        cpi     BLOCK_COUNT
        stc
        rnz
        call    receive_xor_byte
        rc
        sta     expected_crc_hi
        call    receive_xor_byte
        rc
        sta     expected_crc_lo
        call    rx_timeout
        rc
        cmp     c
        stc
        rnz
        ora     a                       ; clear carry
        ret

receive_xor_byte:
        call    rx_timeout
        rc
        mov     b,a
        xra     c
        mov     c,a
        mov     a,b
        ret

; Block: 'J','B',sequence,512 data bytes,CRC16-CCITT-hi,CRC-lo.
; A duplicate of the preceding valid block is verified in place and ACKed
; again without advancing state, making a lost target reply recoverable.
receive_block:
        mvi     b,'B'
        call    find_magic
        jc      block_timeout
        call    rx_timeout
        jc      block_timeout
        sta     packet_sequence
.ifndef FASTBOOT_V2
        lxi     d,0ffffh
        call    crc_byte
.endif

        lda     next_sequence
        mov     c,a
        lda     packet_sequence
        cmp     c
        jz      block_expected
        mov     b,a
        mov     a,c
        ora     a
        jz      block_unexpected
        dcr     a
        cmp     b
        jnz     block_unexpected
.ifdef FASTBOOT_V2
        call    load_previous_crc
.endif
        lhld    next_address
        dcr     h
        dcr     h
        mvi     a,1                    ; valid duplicate
        jmp     block_receive_data

block_expected:
.ifdef FASTBOOT_V2
        call    load_current_crc
.endif
        lhld    next_address
        xra     a                      ; expected block
        jmp     block_receive_data
block_unexpected:
.ifdef FASTBOOT_V2
        call    load_current_crc
.endif
        lhld    next_address           ; consume safely; retry overwrites it
        mvi     a,2
block_receive_data:
        sta     packet_kind
        lxi     b,BLOCK_SIZE
block_byte:
        call    rx_timeout
        jc      block_timeout
        mov     m,a
        inx     h
        call    crc_byte
        dcx     b
        mov     a,b
        ora     c
        jnz     block_byte
        call    rx_timeout
        jc      block_timeout
        cmp     d
        jnz     block_crc_bad
        call    rx_timeout
        jc      block_timeout
        cmp     e
        jnz     block_crc_bad

        lda     packet_kind
        ora     a
        jnz     block_not_expected
        shld    next_address
.ifdef FASTBOOT_V2
        lhld    current_crc
        shld    previous_crc
        mov     h,d
        mov     l,e
        shld    current_crc
.endif
        lda     next_sequence
        inr     a
        sta     next_sequence
        lda     packet_sequence
        mvi     c,0
        call    send_reply
        ora     a
        ret
block_not_expected:
        cpi     1
        jnz     block_protocol_bad
        lda     packet_sequence
        mvi     c,0
        call    send_reply
        stc
        ret
block_protocol_bad:
        lda     next_sequence
        mvi     c,3
        call    send_reply
        stc
        ret
block_crc_bad:
        lda     packet_sequence
        mvi     c,1
        call    send_reply
block_timeout:
        stc
        ret

.ifdef FASTBOOT_V2
load_current_crc:
        lhld    current_crc
        jmp     crc_hl_to_de
load_previous_crc:
        lhld    previous_crc
crc_hl_to_de:
        mov     d,h
        mov     e,l
        ret
.endif

; Search a timeout-bounded stream for 'J',B where B is supplied by caller.
find_magic:
find_j:
        call    rx_timeout
        rc
        cpi     'J'
        jnz     find_j
        call    rx_timeout
        rc
        cmp     b
        jnz     find_j
        ret

; CRC16-CCITT, polynomial 1021h, initial FFFFh.  Input byte A; CRC in DE.
; BC and HL are preserved so the routine can run directly in the copy loop.
crc_byte:
        xra     d
        mov     d,a
        push    b
        mvi     b,8
crc_bit:
        mov     a,e
        add     a
        mov     e,a
        mov     a,d
        ral
        mov     d,a
        jnc     crc_no_poly
        mov     a,d
        xri     010h
        mov     d,a
        mov     a,e
        xri     021h
        mov     e,a
crc_no_poly:
        dcr     b
        jnz     crc_bit
        pop     b
        ret

; Timeout is intentionally much longer than a character but finite, allowing
; the receiver to discard a truncated packet and search a later retransmit.
rx_timeout:
        push    b
        lxi     b,0ffffh
rx_wait:
        in      USARTCTL
        ani     2
        jnz     rx_ready
        dcx     b
        mov     a,b
        ora     c
        jnz     rx_wait
        pop     b
        stc
        ret
rx_ready:
        in      USARTDATA
        pop     b
        ora     a
        ret

init_usart:
        xra     a
        out     USARTCTL
        out     USARTCTL
        out     USARTCTL
        mvi     a,040h
        out     USARTCTL
        mvi     a,05eh                 ; x16, 8 data, odd parity, one stop
        out     USARTCTL
        mvi     a,034h                 ; receive enabled, transmitter off
        out     USARTCTL
        in      USARTDATA
        ret

send_ready:
        mvi     a,035h
        out     USARTCTL
        mvi     a,'J'
        call    tx
        mvi     a,'R'
        call    tx
        mvi     a,PROTOCOL_VERSION
        call    tx
        mvi     a,BLOCK_COUNT
        call    tx
        mvi     a,'J' xor 'R' xor PROTOCOL_VERSION xor BLOCK_COUNT
        call    tx
        jmp     tx_finish

; A=sequence, C=status. Reply: 'J','A',sequence,status,xor.
send_reply_three:
        mvi     l,3
send_reply_repeat:
        push    h
        push    b
        push    psw
        call    send_reply
        pop     psw
        pop     b
        pop     h
        dcr     l
        jnz     send_reply_repeat
        ret
send_reply:
        push    psw
        mvi     a,035h
        out     USARTCTL
        mvi     a,'J'
        call    tx
        mvi     a,'A'
        call    tx
        pop     psw
        call    tx
        mov     b,a
        mov     a,c
        call    tx
        xra     b
        xri     'J' xor 'A'
        call    tx
tx_finish:
        ; D11 TXEMPTY is not connected on Juku.  The conservative fixed drain
        ; is the same physically proven half-duplex technique as the BIOS.
        lxi     b,1200
tx_drain:
        dcx     b
        mov     a,b
        ora     c
        jnz     tx_drain
        mvi     a,034h
        out     USARTCTL
        ret

tx:
        push    b
        mov     c,a
tx_wait:
        in      USARTCTL
        ani     1
        jz      tx_wait
        mov     a,c
        out     USARTDATA
        pop     b
        ret

expected_crc_hi: db    0
expected_crc_lo: db    0
next_address:   dw      DESTINATION
next_sequence:  db      0
.ifdef FASTBOOT_V2
current_crc:    dw      0ffffh
previous_crc:   dw      0ffffh
.else
blocks_left:    db      BLOCK_COUNT
.endif
packet_sequence: db     0
packet_kind:    db      0
