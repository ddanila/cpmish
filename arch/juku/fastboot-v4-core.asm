; One-record stock-Janet core for negotiated Fast stage v4.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; Stock Janet transfers only this 128-byte core. It selects the physically
; proven 19200/8O1 setting and authenticates a three-record extension at 0300h.
; The extension, not this size-constrained core, negotiates the faster rate.

USARTDATA       equ     008h
USARTCTL        equ     009h
PITCOUNT0       equ     018h
PITCTL          equ     01bh
PICMASK         equ     001h
PICSHADOW       equ     0d454h

EXTENSION       equ     0300h

        org     0100h

        jmp     start
        db      'J','F','V','4'
        db      1                       ; core records
        db      3                       ; extension records

start:
        di
        lxi     sp,0b3f0h
        mvi     a,0ffh
        out     PICMASK
        sta     PICSHADOW

        mvi     a,015h                  ; D57 ch0 mode 2, LSB, BCD
        out     PITCTL
        mvi     a,4
        out     PITCOUNT0

        xra     a
        out     USARTCTL
        out     USARTCTL
        out     USARTCTL
        mvi     a,040h
        out     USARTCTL
        mvi     a,05eh                  ; x16/8O1
        out     USARTCTL
        mvi     a,035h
        out     USARTCTL
        in      USARTDATA

session:
        ; Extension packet: A5h, 3Ah, 384 bytes, Fletcher sum1, sum2.
find_first:
        call    rx
        cpi     0a5h
        jnz     find_first
        call    rx
        cpi     03ah
        jnz     find_first

        lxi     h,EXTENSION
        mvi     c,3
        xra     a
        mov     d,a                     ; Fletcher sum2
        mov     e,a                     ; Fletcher sum1
receive_chunk:
        mvi     b,128
receive_extension:
        call    rx
        mov     m,a
        inx     h
        add     e
        aci     0
        mov     e,a
        add     d
        aci     0
        mov     d,a
        dcr     b
        jnz     receive_extension
        dcr     c
        jnz     receive_chunk
        call    rx
        cmp     e
        jnz     session
        call    rx
        cmp     d
        jnz     session
        jmp     EXTENSION

rx:
        in      USARTCTL
        ani     2
        jz      rx
        in      USARTDATA
        ret

core_end:
        .if     core_end-0100h > 128
        .error  "Fastboot v4 core exceeds one Janet record"
        .endif
