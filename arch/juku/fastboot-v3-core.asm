; One-record stock-Janet core for Fast stage v3.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; The bundle builder pads this executable to exactly one 128-byte Janet
; record and appends a separately assembled padded extension.  Only the
; first record travels through the stock 9600 protocol.  This core switches
; D57/D11 to proven 19200/8O1, receives the extension at 0300h, protects it
; with Fletcher-16, and enters it.  A malformed transfer is ignored; the host
; retransmission supplies enough bytes for the fixed-length receiver to
; finish, reject, and resynchronise without growing a timeout into the core.

USARTDATA       equ     008h
USARTCTL        equ     009h
PITCOUNT0       equ     018h
PITCTL          equ     01bh
PICMASK         equ     001h
PICSHADOW       equ     0d454h

EXTENSION       equ     0300h
.ifdef FASTBOOT_STREAM
EXTENSION_SIZE  equ     0280h
.else
.ifdef FASTBOOT_TIGHT
EXTENSION_SIZE  equ     0100h
.else
.ifdef FASTBOOT_ZX0
EXTENSION_SIZE  equ     0180h
.else
EXTENSION_SIZE  equ     0100h
.endif
.endif
.endif

        org     0100h

        ; Self-describing bundle metadata.  Host tooling transfers one core
        ; record and finds the padded extension described by the metadata.
        jmp     start
.ifdef FASTBOOT_STREAM
        db      'J','F','V','8'
.else
.ifdef FASTBOOT_TIGHT
        db      'J','F','V','7'
.else
.ifdef FASTBOOT_ZX0
        db      'J','F','V','6'
.else
.ifdef FASTBOOT_8N1
        db      'J','F','V','5'
.else
        db      'J','F','V','3'
.endif
.endif
.endif
.endif
        db      1                       ; core records
        db      EXTENSION_SIZE/128      ; extension records

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

        ; Canonical D11 reset, then x16/8O1 (v3) or 8N1 (v5).
        xra     a
        out     USARTCTL
        out     USARTCTL
        out     USARTCTL
        mvi     a,040h
        out     USARTCTL
.ifdef FASTBOOT_8N1
        mvi     a,04eh
.else
        mvi     a,05eh
.endif
        out     USARTCTL
        mvi     a,035h
        out     USARTCTL
        in      USARTDATA

session:
        ; Extension packet: A5h, 3Ah, 256 bytes, Fletcher sum1, sum2.
find_first:
        call    rx
        cpi     0a5h
        jnz     find_first
        call    rx
        cpi     03ah
        jnz     find_first

        lxi     h,EXTENSION
.ifdef FASTBOOT_ZX0
        lxi     b,EXTENSION_SIZE
.else
        mvi     b,0                     ; 256 iterations by wraparound
.endif
        xra     a
        mov     d,a                     ; Fletcher sum2
        mov     e,a                     ; Fletcher sum1
receive_extension:
        call    rx
        mov     m,a
        inx     h
        add     e                       ; modulo-255 end-around carry
        aci     0
        mov     e,a
        add     d
        aci     0
        mov     d,a
.ifdef FASTBOOT_ZX0
        dcx     b
        mov     a,b
        ora     c
.else
        dcr     b
.endif
        jnz     receive_extension
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
        ; The bundle contract and cosim assert this at build time too.
        .if     core_end-0100h > 128
        .error  "Fastboot v3 core exceeds one Janet record"
        .endif
