; Juku E5101/E5104 CP/Mish BIOS
; Copyright (c) 2026 Daniel Danilov
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; Strict Intel 8080 source. Hardware access is delegated to the public
; RomBios vectors used by EKDOS 2.30 and Bootstrap 4.x.

        maclib  cpm

        cseg
label   BBASE

; Public CP/M 2.2 BIOS jump table.
        jmp     BOOT
        jmp     WBOOT
        jmp     CONST
        jmp     CONIN
        jmp     CONOUT
        jmp     LIST
        jmp     EMPTY
        jmp     EMPTY
        jmp     HOME
        jmp     SELDSK
        jmp     SETTRK
        jmp     SETSEC
        jmp     SETDMA
        jmp     READ
        jmp     WRITE
        jmp     EMPTY
        jmp     SECTRAN

; RomBios and monitor ABI.
RWFLOPPY       equ     0ff59h
CONSTA         equ     0ff98h
RDCHR          equ     0ffd3h
WRCHR          equ     0ffd9h
PRINTCH        equ     0ffeeh
BDOSADDR       equ     0ff64h
CONCW          equ     0ffb4h

; RomBios floppy work area.
TYP            equ     0d600h
ERRC           equ     TYP+9
TYPEA          equ     TYP+10
TYPEB          equ     TYP+11
SIZEA          equ     TYP+12
SIZEB          equ     TYP+13
RATEA          equ     TYP+14
RATEB          equ     TYP+15
SIZE           equ     TYP+16
RATE           equ     TYP+17
FBI            equ     TYP+26
SEKDSK         equ     FBI
SEKTRK         equ     FBI+1
SEKSEC         equ     FBI+3
HSTACT         equ     FBI+9
HSTWRT         equ     FBI+10
RCOUNT         equ     FBI+16
MEMADR         equ     FBI+20

DKRD           equ     011h
DKWR           equ     012h

; Cold start. Bootstrap has already loaded the resident image.
BOOT:
        lxi     sp,0100h

        ; Publish the BDOS address through the RomBios-owned pointer.
        lhld    BDOSADDR
        lxi     d,FBASE+6
        mov     m,e
        inx     h
        mov     m,d

        ; Configure two 80-track 386K drives exactly as EKDOS 2.30 does.
        xra     a
        sta     TYP
        sta     TYPEA
        sta     TYPEB
        mvi     a,80
        sta     SIZEA
        sta     SIZEB
        sta     SIZE
        mvi     a,1
        sta     RATEA
        sta     RATEB
        sta     RATE

        xra     a
        sta     CDISK
        sta     HSTACT
        sta     HSTWRT

        call    PRINT
        db      01bh,'L'
        db      '52K CP/Mish-Juku 2.2',13,10
        db      'A:, B: - 386K floppy',13,10,10,0
        jmp     GOCPM

; Resident CCP is outside the TPA and remains valid, so warm boot does not
; depend on the system tracks of the currently inserted disk.
WBOOT:
        lxi     sp,0100h
        xra     a
        sta     HSTACT
        sta     HSTWRT

GOCPM:
        mvi     a,0c3h
        sta     0000h
        lxi     h,BBASE+3
        shld    0001h
        sta     0005h
        lxi     h,FBASE+6
        shld    0006h

        lxi     b,0080h
        call    SETDMA

        ; Tell the monitor that CP/M owns the console path.
        lhld    CONCW
        mvi     m,0

        lda     CDISK
        mov     c,a
        call    SELDSK
        jmp     CBASE

; Monitor calls can alter registers and use their own working stack. This
; trampoline follows the calling discipline observed in EKDOS 2.30 while
; preserving the caller's DE and HL.
ROMCALL:
        shld    SAVEHL
        xchg
        xthl
        mov     e,m
        inx     h
        mov     d,m
        inx     h
        xchg
        shld    FUNCTION+1
        xchg
        xthl
        xchg
        lxi     h,0
        dad     sp
        shld    SAVESP
        lxi     sp,ROMSTACK
FUNCTION:
        call    0000h
        lhld    SAVESP
        sphl
        lhld    SAVEHL
        ret

CONST:
        call    ROMCALL
        dw      CONSTA
        ret

CONIN:
        call    ROMCALL
        dw      RDCHR
        ret

CONOUT:
        mov     a,c
        call    ROMCALL
        dw      WRCHR
        ret

LIST:
        mov     a,c
        call    ROMCALL
        dw      PRINTCH
        ret

EMPTY:
        xra     a
        ret

HOME:
        lda     HSTWRT
        ora     a
        jnz     HOME1
        xra     a
        sta     HSTACT
HOME1:
        mvi     c,0
        jmp     SETTRK

SELDSK:
        lxi     h,0
        mov     a,c
        cpi     2
        rnc

        sta     SEKDSK
        ora     a
        lda     TYPEA
        jz      SELTYPE
        lda     TYPEB
SELTYPE:
        sta     TYP

        mov     l,c
        mvi     h,0
        dad     h
        dad     h
        dad     h
        dad     h
        lxi     d,DPH0
        dad     d
        ret

SETTRK:
        mov     a,c
        sta     SEKTRK
        ret

SETSEC:
        mov     a,c
        sta     SEKSEC
        ret

SETDMA:
        mov     l,c
        mov     h,b
        shld    MEMADR
        ret

READ:
        mvi     a,DKRD
        jmp     RWDISK

WRITE:
        mvi     a,DKWR

RWDISK:
        sta     REQUEST
        mvi     a,1
        sta     RCOUNT
        lda     REQUEST
        call    ROMCALL
        dw      RWFLOPPY
        lda     ERRC
        ora     a
        rz
        mvi     a,1
        ret

SECTRAN:
        xchg
        dad     b
        mov     a,h
        ora     a
        rz
        mov     l,m
        mvi     h,0
        ret

PRINT:
        pop     h
PRINT1:
        mov     a,m
        inx     h
        ora     a
        jz      PRINT2
        mov     c,a
        push    h
        call    CONOUT
        pop     h
        jmp     PRINT1
PRINT2:
        pchl

; Juku's 10 physical 512-byte sectors are exposed as 40 CP/M records.
TRANS:
        db      1,2,3,4,9,10,11,12
        db      17,18,19,20,25,26,27,28
        db      33,34,35,36,5,6,7,8
        db      13,14,15,16,21,22,23,24
        db      29,30,31,32,37,38,39,40

TRANS1:
        db      1,2,3,4,9,10,11,12
        db      17,18,19,20,25,26,27,28
        db      33,34,35,36,5,6,7,8
        db      13,14,15,16,21,22,23,24
        db      29,30,31,32,37,38,39,40

DPH0:   dw      TRANS,0,0,0,DIRBUF,DPB0,CHK0,ALLOC0
DPH1:   dw      TRANS1,0,0,0,DIRBUF,DPB0,CHK1,ALLOC1

; One 80-track side, 10 x 512 bytes, two reserved tracks, 2K blocks.
DPB0:   dw      40
        db      4,15,1
        dw      0c2h
        dw      127
        db      0c0h,0
        dw      32
        dw      2

REQUEST: db     0
SAVEHL:  dw     0
SAVESP:  dw     0

; The monitor trampoline's private stack lies below the resident CCP and above
; the monitor's D600 work area. It is never part of a transient program.
ROMSTACK equ    0d2fch

; BDOS scratch space is intentionally outside the initialized 1 KiB BIOS
; image, matching the established EKDOS memory map.
DIRBUF   equ    BBASE+8*128
ALLOC0   equ    DIRBUF+128
ALLOC1   equ    ALLOC0+32
CHK0     equ    ALLOC1+32
CHK1     equ    CHK0+32

        end
