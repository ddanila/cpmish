; Interrupt-fed streaming ZX0 extension for Fast stages v8/v9.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; D11 RxRDY reaches D10/PIC IR2 and RomBios dispatches service 2 through the
; writable service path. A fixed linear producer/consumer buffer lets ZX0
; expansion overlap the 19200/8N1 wire transfer without a ring-capacity bound.
; CRC, exact compressed/decompressed lengths, a hard output fence, and retry
; resynchronisation still gate execution of the downloaded resident system.

USARTDATA       equ     008h
USARTCTL        equ     009h
PICCTL          equ     000h
PICMASK         equ     001h
PICSHADOW       equ     0d454h
ROM_DISPATCH    equ     0d79fh

DESTINATION     equ     0b400h
DESTINATION_END equ     0ce00h
ENTRY           equ     0ca00h
COMPRESSED      equ     04000h
RING            equ     00700h
.ifdef FASTBOOT_POLL_MARKERS
.ifdef FASTBOOT_V13
PROTOCOL_VERSION equ    13
CORE_RX          equ    0173h
.else
.ifdef FASTBOOT_V12
PROTOCOL_VERSION equ    12
CORE_RX          equ    0173h
.else
.ifdef FASTBOOT_V11
PROTOCOL_VERSION equ    11
CORE_RX          equ    0172h
.else
.ifdef FASTBOOT_V10
PROTOCOL_VERSION equ    10
.else
PROTOCOL_VERSION equ    9
.endif
.endif
.endif
.endif
.ifndef FASTBOOT_V11
.ifndef FASTBOOT_V12
.ifndef FASTBOOT_V13
CORE_RX          equ    016eh
.endif
.endif
.endif
.else
PROTOCOL_VERSION equ    8
.endif

        org     0300h

start:
        di
        lxi     sp,0b3f0h
        ; RomBios's general dispatcher is too costly at one byte per ~884
        ; CPU cycles. Preserve its first three bytes and temporarily replace
        ; them with a jump to our single-source IR2 trampoline.
        lhld    ROM_DISPATCH
        shld    saved_dispatch
        lda     ROM_DISPATCH+2
        sta     saved_dispatch+2
        mvi     a,0c3h
        sta     ROM_DISPATCH
        lxi     h,irq_dispatch
        shld    ROM_DISPATCH+1
.ifdef FASTBOOT_POLL_MARKERS
        mvi     a,020h                 ; retire stock Janet's active IR2 turn
        out     PICCTL
        mvi     a,0ffh                 ; poll markers; IRQs only carry payload
.else
        call    reset_idle
        mvi     a,020h                 ; retire stock Janet's active IR2 turn
        out     PICCTL
        mvi     a,0fbh                 ; unmask only D11 RxRDY / IR2
.endif
        out     PICMASK
        sta     PICSHADOW
.ifndef FASTBOOT_POLL_MARKERS
        ei
.endif

session:
.ifndef FASTBOOT_POLL_MARKERS
        call    reset_idle
.endif
        call    send_ready

find_j:
.ifdef FASTBOOT_POLL_MARKERS
        call    CORE_RX
.else
        call    marker_get
.endif
        cpi     'J'
        jnz     find_j
find_z:
.ifdef FASTBOOT_POLL_MARKERS
        call    CORE_RX
.else
        call    marker_get
.endif
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

        ; The builder patches the immutable compressed length.  Arm CRC and
        ; byte accounting before the first payload character can arrive.
.ifdef FASTBOOT_POLL_MARKERS
        ; Polling clears D11 RxRDY but leaves the masked PIC request latched.
        ; Let one ISR consume that stale copy while input_left is still zero;
        ; the host's 2 ms post-JZ gap keeps payload bytes out of this window.
        mvi     a,0fbh
        out     PICMASK
        sta     PICSHADOW
        ei
        nop
.endif
        di
        lxi     h,0a55ah
        shld    input_left
        xra     a
        sta     crc_value
        sta     crc_value+1
        sta     receive_failed
        lxi     h,COMPRESSED
        shld    input_write
.ifndef FASTBOOT_POLL_MARKERS
        inr     a
        sta     payload_active
.endif
        lxi     h,0
        dad     sp
        shld    saved_sp
.ifdef FASTBOOT_STREAM_ACK
        mvi     a,0c6h                 ; payload state is armed and ready
        out     USARTDATA
.endif
        ei

wait_lead:
        lda     receive_failed
        ora     a
        jnz     abort_stream
        lda     input_write+1
        cpi     041h                    ; 256 bytes buffered at 4100h
        jc      wait_lead
        lxi     d,COMPRESSED
        lxi     b,DESTINATION
        call    dzx0

        ; Success requires exact output/input boundaries, no USART fault, and
        ; the fixed stream CRC.
        mov     a,b
        cpi     DESTINATION_END/256
        jnz     abort_stream
        mov     a,c
        ora     a
        jnz     abort_stream
finish_wait:
        lda     receive_failed
        ora     a
        jnz     finish_abort
        di
        lhld    input_left
        mov     a,h
        ora     l
        jz      finish_received
        ei
        jmp     finish_wait
finish_received:
        lhld    input_write
        mov     a,h
        cmp     d
        jnz     finish_abort
        mov     a,l
        cmp     e
        jnz     finish_abort
        lda     receive_failed
        ora     a
        jnz     finish_abort
        lda     crc_value+1
        cpi     0a5h                    ; patched expected CRC high byte
        jnz     finish_abort
        lda     crc_value
        nop                             ; unique builder patch sentinel
        cpi     05ah                    ; patched expected CRC low byte
        jnz     finish_abort

        mvi     a,0ffh
        out     PICMASK
        sta     PICSHADOW
        lhld    saved_dispatch
        shld    ROM_DISPATCH
        lda     saved_dispatch+2
        sta     ROM_DISPATCH+2
        call    send_success_three
success_drain:
        dcr     b                       ; B=0 after the final success frame
        jnz     success_drain
        jmp     ENTRY

finish_abort:
        ei
abort_stream:
        ; A decoder can be several return addresses deep.  Restore the known
        ; session stack, drain the rest of this fixed stream under interrupts,
        ; then emit a fresh ready marker so a complete retry can resynchronise.
        lhld    saved_sp
        sphl
abort_drain:
        di
        lhld    input_left
        mov     a,h
        ora     l
        ei
        jnz     abort_drain
.ifdef FASTBOOT_POLL_MARKERS
        di
        mvi     a,0ffh
        out     PICMASK
        sta     PICSHADOW
.endif
        jmp     session

.ifndef FASTBOOT_POLL_MARKERS
reset_idle:
        di
        xra     a
        sta     ring_head
        sta     ring_tail
        sta     payload_active
        ei
        ret

; Wait for a marker byte.  Idle garbage is ring-buffered but does not affect
; payload length or CRC.  The critical section prevents a false-full race with
; an Rx interrupt advancing the head while the mainline advances the tail.
marker_get:
        push    h
marker_wait:
        di
        lda     ring_tail
        mov     l,a
        lda     ring_head
        cmp     l
        jnz     marker_have
        ei
        jmp     marker_wait
marker_have:
        mvi     h,RING/256
        mov     a,m
        push    psw
        lda     ring_tail
        inr     a
        sta     ring_tail
        pop     psw
        ei
        pop     h
        ret
.endif

; Return one compressed byte in A and advance DE. The fixed 256-byte lead,
; exact final DE, CRC, and clean/fault cosim keep this native fast path safe.
stream_get:
.ifdef FASTBOOT_WAIT_INPUT
        mov     a,e
        ora     a
        jnz     stream_get_have
stream_get_wait:
        lda     input_write+1
        cmp     d
        jnz     stream_get_have
        lda     input_left
        ora     a
        jnz     stream_get_wait
        lda     input_left+1
        ora     a
        jnz     stream_get_wait
stream_get_have:
.endif
        ldax    d
        inx     d
        ret

; Service-2 handler. Preserve the interrupted decoder completely. During a
; payload, every received byte decrements the fixed count and is appended to
; the reserved 4000h buffer.
rx_isr:
        push    psw
        push    b
        push    d
        push    h
        in      USARTCTL
        mov     b,a
        in      USARTDATA
        mov     c,a
        mov     a,b
        ani     038h
        jz      rx_error_done
.ifndef FASTBOOT_POLL_MARKERS
        lda     payload_active
        ora     a
        jz      rx_reset_error
.endif
        mvi     a,1
        sta     receive_failed
rx_reset_error:
        mvi     a,035h
        out     USARTCTL
rx_error_done:
.ifndef FASTBOOT_POLL_MARKERS
        lda     payload_active
        ora     a
        jz      rx_store
.endif
        lhld    input_left
        mov     a,h
        ora     l
        jz      rx_exit
        dcx     h
        shld    input_left
        lhld    crc_value
        xchg
        mov     a,c
        call    crc_byte_fast
        xchg
        shld    crc_value
        lhld    input_write
        mov     m,c
        inx     h
        shld    input_write
        jmp     rx_exit
.ifndef FASTBOOT_POLL_MARKERS
rx_store:
        lda     ring_head
        mov     e,a
        inr     a
        mov     d,a
        lda     ring_tail
        cmp     d
        jz      rx_full
        mvi     h,RING/256
        mov     l,e
        mov     m,c
        mov     a,d
        sta     ring_head
        jmp     rx_exit
rx_full:
        ; Harmless idle garbage is discarded; marker_get normally consumes it
        ; substantially faster than the wire can fill this page.
.endif
rx_exit:
        mvi     a,020h
        out     PICCTL
        pop     h
        pop     d
        pop     b
        pop     psw
        ret

; The 8259 executes CALL FEC8h; that vector executes CALL D79Fh. Discard the
; latter call's FECBh return, retain the actual interrupted PC, and bypass the
; much larger RomBios multi-service dispatcher for this one-source session.
irq_dispatch:
        shld    irq_saved_h
        pop     h
        call    rx_isr
        lhld    irq_saved_h
        ei
        ret

; Streaming adaptation of Ivan Gorodetsky's 8080 ZX0 classic decoder. Literal
; bytes use stream_get; match copies continue reading the already produced
; output. Every write checks the exclusive CE00h boundary.
dzx0:
        lxi     h,0ffffh
        push    h
        inx     h
        mvi     a,080h
dzx0_literals:
        call    dzx0_elias
        call    dzx0_stream_ldir
        jc      dzx0_new_offset
        call    dzx0_elias
dzx0_copy:
        xchg
        xthl
        push    h
        dad     b
        xchg
        call    dzx0_match_ldir
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
        push    psw                    ; preserve offset carry across getter
        call    stream_get
        mov     l,a
        pop     psw
        mov     a,l
        rar
        mov     l,a
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
        call    stream_get
        stc                             ; 80h+80h refill carries into RAL
        ral
dzx0_elias_skip:
        rc
dzx0_elias_backtrack:
        dad     h
        add     a
        jnc     dzx0_elias_loop
        jmp     dzx0_elias
dzx0_stream_ldir:
        push    psw
dzx0_stream_loop:
        mov     a,b
        cpi     DESTINATION_END/256
        jnc     abort_stream
.ifdef FASTBOOT_WAIT_INPUT
        mov     a,e
        ora     a
        jnz     dzx0_stream_have
dzx0_stream_wait:
        lda     input_write+1
        cmp     d
        jnz     dzx0_stream_have
        lda     input_left
        ora     a
        jnz     dzx0_stream_wait
        lda     input_left+1
        ora     a
        jnz     dzx0_stream_wait
dzx0_stream_have:
.endif
        ldax    d
        stax    b
        inx     d
        inx     b
        dcx     h
        mov     a,h
        ora     l
        jnz     dzx0_stream_loop
        pop     psw
        add     a
        ret
dzx0_match_ldir:
        push    psw
dzx0_match_loop:
        mov     a,b
        cpi     DESTINATION_END/256
        jnc     abort_stream
        ldax    d
        stax    b
        inx     d
        inx     b
        dcx     h
        mov     a,h
        ora     l
        jnz     dzx0_match_loop
        pop     psw
        add     a
        ret

; CRC-16/IBM reflected polynomial A001h, initial 0000h. Input byte A, CRC DE.
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
        lxi     h,success_frame
        mvi     b,5
        call    send_frame
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

ready_frame:
        db      'J','R',PROTOCOL_VERSION,1
        db      'J' xor 'R' xor PROTOCOL_VERSION xor 1
success_frame:
        db      'J','A',0,0,'J' xor 'A'

.ifndef FASTBOOT_POLL_MARKERS
ring_head:      db      0
ring_tail:      db      0
.endif
input_left:     dw      0
crc_value:      dw      0
input_write:    dw      0
.ifndef FASTBOOT_POLL_MARKERS
payload_active: db      0
.endif
receive_failed: db      0
saved_sp:       dw      0
saved_dispatch: db      0,0,0
irq_saved_h:    dw      0

extension_end:
        .if     extension_end-0300h > 640
        .error  "Fastboot v8 extension exceeds five records"
        .endif
