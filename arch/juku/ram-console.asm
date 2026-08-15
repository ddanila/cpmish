; Minimal 40x24 bitmap console for the separately relocated 51K RAM BIOS.
;
; Output is BIOS-owned, but input deliberately remains on the proven RomBios
; path.  Code executes below D800h.  Framebuffer reads require memory mode 3;
; every operation therefore excludes interrupts, selects all-RAM, and restores
; the normal mode-1 ROM window before returning.

MODEPORT        equ     006h
VRAM            equ     0d800h
ROWBYTES        equ     400             ; 40 columns * 10 scanlines
SCREENBYTES     equ     9600            ; 40 * 24 * 10
SCROLLBYTES     equ     9200            ; retain rows 1..23

RAMCONINIT:
        xra     a
        sta     RAMCOL
        sta     RAMROW
        sta     RAMESC
        call    RAMVIDEO
        lxi     h,VRAM
        lxi     b,SCREENBYTES
        call    RAMCLEAR
        jmp     RAMNORMAL

; A = character. Preserve every caller-visible register.
RAMCONOUT:
        push    psw
        push    b
        push    d
        push    h
        mov     e,a

        lda     RAMESC
        ora     a
        jz      RAMNOESC
        xra     a
        sta     RAMESC
        mov     a,e
        cpi     'L'
        cz      RAMCONINIT
        jmp     RAMOUTDONE

RAMNOESC:
        mov     a,e
        cpi     01bh
        jnz     RAMNOTESC
        mvi     a,1
        sta     RAMESC
        jmp     RAMOUTDONE
RAMNOTESC:
        cpi     0dh
        jnz     RAMNOTCR
        xra     a
        sta     RAMCOL
        jmp     RAMOUTDONE
RAMNOTCR:
        cpi     0ah
        jnz     RAMNOTLF
        call    RAMNEWLINE
        jmp     RAMOUTDONE
RAMNOTLF:
        cpi     08h
        jnz     RAMPRINTABLE
        lda     RAMCOL
        ora     a
        jz      RAMOUTDONE
        dcr     a
        sta     RAMCOL
        jmp     RAMOUTDONE

RAMPRINTABLE:
        cpi     020h
        jc      RAMOUTDONE
RAMCHAROK:
        ; Font pointer = RAMFONT + (character - 20h) * 8.
        mov     a,e
        sui     020h
        mov     l,a
        mvi     h,0
        dad     h
        dad     h
        dad     h
        lxi     d,RAMFONT
        dad     d
        push    h

        ; Cell address = VRAM + row*400 + column.
        lxi     h,VRAM
        lda     RAMROW
        mov     b,a
        lxi     d,ROWBYTES
RAMROWADDR:
        mov     a,b
        ora     a
        jz      RAMROWREADY
        dad     d
        dcr     b
        jmp     RAMROWADDR
RAMROWREADY:
        lda     RAMCOL
        mov     e,a
        mvi     d,0
        dad     d
        pop     d                       ; DE = eight font rows

        call    RAMVIDEO
        mvi     m,0                     ; blank scanline above glyph
        lxi     b,40
        dad     b
        mvi     b,8
RAMGLYPH:
        ldax    d
        mov     m,a
        inx     d
        push    b
        lxi     b,40
        dad     b
        pop     b
        dcr     b
        jnz     RAMGLYPH
        mvi     m,0                     ; blank scanline below glyph
        call    RAMNORMAL

        lda     RAMCOL
        inr     a
        cpi     40
        jc      RAMSAVECOL
        xra     a
        sta     RAMCOL
        call    RAMNEWLINE
        jmp     RAMOUTDONE
RAMSAVECOL:
        sta     RAMCOL

RAMOUTDONE:
        pop     h
        pop     d
        pop     b
        pop     psw
        ret

RAMNEWLINE:
        lda     RAMROW
        inr     a
        cpi     24
        jc      RAMSAVEROW
        call    RAMSCROLL
        mvi     a,23
RAMSAVEROW:
        sta     RAMROW
        ret

RAMSCROLL:
        call    RAMVIDEO
        lxi     h,VRAM
        lxi     d,VRAM+ROWBYTES
        lxi     b,SCROLLBYTES
RAMCOPY:
        ldax    d
        mov     m,a
        inx     d
        inx     h
        dcx     b
        mov     a,b
        ora     c
        jnz     RAMCOPY
        lxi     b,ROWBYTES
        call    RAMCLEAR
        jmp     RAMNORMAL

; Fill BC bytes at HL with zero.
RAMCLEAR:
RAMCLEAR1:
        mvi     m,0
        inx     h
        dcx     b
        mov     a,b
        ora     c
        jnz     RAMCLEAR1
        ret

RAMVIDEO:
        di
        in      MODEPORT
        ani     0fch
        ori     3
        out     MODEPORT
        ret

RAMNORMAL:
        in      MODEPORT
        ani     0fch
        ori     1
        out     MODEPORT
        ei
        ret

RAMCOL: db      0
RAMROW: db      0
RAMESC: db      0

        include "ram-console-font.asm"
