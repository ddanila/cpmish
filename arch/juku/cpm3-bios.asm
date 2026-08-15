        title   'Juku nonbanked CP/M Plus 3.1 BIOS'

; Copyright (c) 2026 Daniel Danilov
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; CP/M Plus retains the standard first seventeen CP/M 2 BIOS calls.  This
; compact non-banked BIOS delegates those hardware operations to the tested
; adapter at A000h and implements only the CP/M 3 glue locally.

true            equ     0ffffh
jmpop           equ     0c3h
bdos            equ     0005h
ccp             equ     0100h
default$fcb     equ     005ch
adapter         equ     0a000h

; CP/M 2-compatible adapter vectors.
a$boot          equ     adapter+0
a$wboot         equ     adapter+3
a$const         equ     adapter+6
a$conin         equ     adapter+9
a$conout        equ     adapter+12
a$list          equ     adapter+15
a$auxout        equ     adapter+18
a$auxin         equ     adapter+21
a$home          equ     adapter+24
a$seldsk        equ     adapter+27
a$settrk        equ     adapter+30
a$setsec        equ     adapter+33
a$setdma        equ     adapter+36
a$read          equ     adapter+39
a$write         equ     adapter+42
a$listst        equ     adapter+45
a$sectrn        equ     adapter+48

        cseg
        extrn   @mxtpa

; CP/M Plus 32-entry BIOS jump table.
boot$entry:     jmp     boot
warm$entry:     jmp     wboot
                jmp     a$const
                jmp     a$conin
                jmp     a$conout
                jmp     a$list
                jmp     a$auxout
                jmp     a$auxin
                jmp     a$home
                jmp     seldsk
                jmp     a$settrk
                jmp     a$setsec
                jmp     a$setdma
                jmp     a$read
                jmp     a$write
                jmp     a$listst
                jmp     a$sectrn
                jmp     ready
                jmp     ready
                jmp     ready
                jmp     devtbl
                jmp     return
                jmp     drvtbl
                jmp     return
                jmp     success
                jmp     move
                jmp     return
                jmp     return
                jmp     return
                jmp     return
                jmp     wboot
                jmp     wboot

boot:
        lxi     sp,stack$top
        call    a$boot
        lxi     h,signon
        call    print
        jmp     load$ccp

wboot:
        lxi     sp,stack$top
load$ccp:
        call    set$jumps
        lxi     h,default$fcb
        mvi     b,36
clear$fcb:
        mvi     m,0
        inx     h
        dcr     b
        jnz     clear$fcb
        lxi     h,ccp$name
        lxi     d,default$fcb+1
        mvi     b,11
copy$name:
        mov     a,m
        stax    d
        inx     h
        inx     d
        dcr     b
        jnz     copy$name
        mvi     a,1
        sta     default$fcb
        lxi     d,default$fcb
        mvi     c,15
        call    bdos
        inr     a
        jz      ccp$error
        lxi     d,ccp
read$ccp:
        push    d
        mvi     c,26
        call    bdos
        lxi     d,default$fcb
        mvi     c,20
        call    bdos
        pop     d
        ora     a
        jnz     ccp$done
        lxi     h,128
        dad     d
        xchg
        jmp     read$ccp
ccp$done:
        cpi     1
        jnz     ccp$error
        jmp     ccp

ccp$error:
        lxi     d,ccp$msg
        mvi     c,9
        call    bdos
        mvi     c,1
        call    bdos
        jmp     wboot

set$jumps:
        mvi     a,jmpop
        sta     0000h
        sta     0005h
        lxi     h,warm$entry
        shld    0001h
        lhld    @mxtpa
        shld    0006h
        ret

; Return a static CP/M 3 XDPH.  Its I/O dispatch prefix calls the adapter's
; CP/M-compatible disk vectors, while CP/M Plus owns allocation state.
seldsk:
        lxi     h,0
        mov     a,c
        cpi     2
        rnc
        push    b
        push    d
        call    a$seldsk
        pop     d
        pop     b
        mov     a,c
        ora     a
        lxi     h,xdph0
        rz
        lxi     h,xdph1
        ret

ready:  mvi     a,true
return: ret
success:xra     a
        ret

print:  mov     a,m
        ora     a
        rz
        mov     c,a
        push    h
        call    a$conout
        pop     h
        inx     h
        jmp     print

signon: db      13,10,'CP/M Plus 3.1 Juku',13,10
        db      'NetDisk v3, 19200',13,10,10,0

devtbl: lxi     h,0ffffh
        ret
drvtbl: lxi     h,0fffeh
        ret

move:   ldax    d
        mov     m,a
        inx     d
        inx     h
        dcx     b
        mov     a,b
        ora     c
        jnz     move
        ret

ccp$name:       db      'CCP     COM'
ccp$msg:        db      13,10,'Juku CP/M Plus BIOS cannot load CCP.COM$'

; Prefix: WRITE, READ, LOGIN, INIT, relative drive, bank.  The XDPH begins at
; the translation pointer and has the CP/M 3 non-banked 25-byte layout.
                dw      a$write,a$read,return,return
                db      0,0
xdph0:          dw      trans,0,0,0,0,0,dpb0,csv0,alv0,bcb0,0ffffh,0
                db      0
                dw      a$write,a$read,return,return
                db      1,0
xdph1:          dw      trans,0,0,0,0,0,dpb1,csv1,alv1,bcb1,0ffffh,0
                db      0

; Juku's forty 128-byte logical records per track.
trans:  db      1,2,3,4,9,10,11,12
        db      17,18,19,20,25,26,27,28
        db      33,34,35,36,5,6,7,8
        db      13,14,15,16,21,22,23,24
        db      29,30,31,32,37,38,39,40

; A: 80 logical tracks, 2K blocks. B: native two-sided 160-track image,
; 4K blocks.  These are the already-qualified CP/Mish geometries.
dpb0:   dw      40
        db      4,15,1
        dw      0c2h,127
        db      0c0h,0
        dw      32,2
        db      0,0
dpb1:   dw      40
        db      5,31,3
        dw      196,127
        db      080h,0
        dw      32,2
        db      0,0

        dseg
csv0:   ds      32
csv1:   ds      32
alv0:   ds      32
alv1:   ds      32
dirbuf0:ds      128
dirbuf1:ds      128
; Non-banked directory BCB: drive FFh means no buffer currently assigned;
; bytes 10..11 are its 128-byte buffer address.
bcb0:   db      0ffh,0,0,0,0,0,0,0,0,0
        dw      dirbuf0
        db      0,0,0
bcb1:   db      0ffh,0,0,0,0,0,0,0,0,0
        dw      dirbuf1
        db      0,0,0
        ds      64
stack$top equ   $

        end
