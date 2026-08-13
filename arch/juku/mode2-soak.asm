; Monitorless sustained Janet-disk verification at 19,200 baud / PIT mode 2.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; Create an 8 KiB file on network A:, read every record back, verify every
; byte, erase the temporary file, and report a short raw marker to the host.
; A successful run then plays the physical-bench-proven smoke phrase, giving
; a monitorless operator an audible PASS indication.

BDOS            equ     0005h
USARTDATA       equ     008h
USARTCTL        equ     009h

F_DELETE        equ     19
F_READSEQ       equ     20
F_WRITESEQ      equ     21
F_MAKE          equ     22
F_SETDMA        equ     26
F_OPEN          equ     15
F_CLOSE         equ     16

RECORDS         equ     64              ; 64 * 128 = 8 KiB each direction

        org     0100h

start:
        lxi     sp,stack_top
        lxi     d,dma
        mvi     c,F_SETDMA
        call    BDOS

        call    reset_fcb
        lxi     d,fcb
        mvi     c,F_DELETE               ; remove a stale interrupted run
        call    BDOS
        call    reset_fcb
        lxi     d,fcb
        mvi     c,F_MAKE
        call    BDOS
        inr     a                         ; FF -> 00 only on failure
        jz      failed

        xra     a
        sta     record
write_loop:
        call    fill_record
        lxi     d,fcb
        mvi     c,F_WRITESEQ
        call    BDOS
        ora     a
        jnz     failed_close
        lda     record
        inr     a
        sta     record
        cpi     RECORDS
        jnz     write_loop
        call    close_file
        jnz     failed

        call    reset_fcb
        lxi     d,fcb
        mvi     c,F_OPEN
        call    BDOS
        inr     a
        jz      failed
        xra     a
        sta     record
read_loop:
        lxi     d,fcb
        mvi     c,F_READSEQ
        call    BDOS
        ora     a
        jnz     failed_close
        call    verify_record
        jnz     failed_close
        lda     record
        inr     a
        sta     record
        cpi     RECORDS
        jnz     read_loop
        call    close_file
        jnz     failed

        call    reset_fcb
        lxi     d,fcb
        mvi     c,F_DELETE
        call    BDOS
        inr     a
        jz      failed

        lxi     h,pass_marker
        mvi     b,PASS_MARKER_LEN
        call    send_marker
        call    smoke_play
        ret

failed_close:
        call    close_file
failed:
        lxi     h,fail_marker
        mvi     b,FAIL_MARKER_LEN
        call    send_marker
failed_halt:
        hlt                               ; no success tune on failure
        jmp     failed_halt

close_file:
        lxi     d,fcb
        mvi     c,F_CLOSE
        call    BDOS
        inr     a
        jz      close_failed              ; CP/M returned FF
        xra     a                         ; success: return Z
        ret
close_failed:
        mvi     a,1
        ora     a                         ; failure: return NZ
        ret

; Restore the fixed drive/name/type and zero all extent/record state.
reset_fcb:
        lxi     h,fcb_template
        lxi     d,fcb
        mvi     b,36
reset_fcb_loop:
        mov     a,m
        stax    d
        inx     h
        inx     d
        dcr     b
        jnz     reset_fcb_loop
        ret

; Pattern byte = record number XOR byte offset XOR A5h. It exercises every
; data bit and changes both within and between the 128-byte disk records.
fill_record:
        lxi     h,dma
        mvi     b,128
        mvi     c,0
fill_loop:
        lda     record
        xra     c
        xri     0a5h
        mov     m,a
        inx     h
        inr     c
        dcr     b
        jnz     fill_loop
        ret

verify_record:
        lxi     h,dma
        mvi     b,128
        mvi     c,0
verify_loop:
        lda     record
        xra     c
        xri     0a5h
        cmp     m
        rnz
        inx     h
        inr     c
        dcr     b
        jnz     verify_loop
        xra     a                         ; verified: return Z
        ret

; HL=marker, B=length. The network BIOS normally leaves the half-duplex
; transmitter disabled between disk turns, so explicitly acquire and release
; it. The fixed drain exceeds one 8O1 character at 19,200 baud.
send_marker:
        mvi     a,035h
        out     USARTCTL
send_marker_loop:
        in      USARTCTL
        ani     1
        jz      send_marker_loop
        mov     a,m
        out     USARTDATA
        inx     h
        dcr     b
        jnz     send_marker_loop
        lxi     d,400
send_marker_drain:
        dcx     d
        mov     a,d
        ora     e
        jnz     send_marker_drain
        mvi     a,034h
        out     USARTCTL
        ret

pass_marker:    db      'M2PASS!'
PASS_MARKER_LEN equ     $-pass_marker
fail_marker:    db      'M2FAIL!'
FAIL_MARKER_LEN equ     $-fail_marker

fcb_template:
        db      0                       ; default drive A:
        db      'M2SOAK  ','DAT'
        ds      24,0
fcb:    ds      36,0
record: db      0
dma:    ds      128,0
        ds      64,0
stack_top:

        include "smoke-player.asm"
        include "smoke-table.asm"

        end     start
