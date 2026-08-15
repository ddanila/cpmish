; Juku E5101/E5104 CP/Mish BIOS
; Copyright (c) 2026 Danila Sukharev
; Developed with OpenAI GPT-5.6 Sol assistance.
; Distributed under the 2-clause BSD license; see COPYING.cpmish.
;
; Strict Intel 8080 source. Console and printer access use the same public
; RomBios vectors as EKDOS 2.30; only network disk I/O is BIOS-owned.

        maclib  cpm

        cseg
label   BBASE
        public  VERMSG
.ifdef RAMKEYBOARD
        extrn   RKINIT
        extrn   RKSTAT
        extrn   RKIN
.endif
.ifdef NETWORKV3
        extrn   N3READ
        extrn   N3INV
        extrn   N3ENA
.endif
.ifdef NETWORKCONSOLE
        extrn   NCENA
        extrn   NCSTAT
        extrn   NCIN
        extrn   NCOUT
.endif

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
.ifdef NETWORKV2
DKRC           equ     013h
.endif

.ifdef NETWORK
USARTDATA      equ     008h
USARTCTL       equ     009h
PIT3COUNT0     equ     018h
.ifdef NETWORK19200
PIT3CTL        equ     01bh
.endif
PICMASK        equ     001h
PICSHADOW      equ     0d454h
.endif

; Cold start. Bootstrap has already loaded the resident image.
BOOT:
.ifdef NETWORK
.ifndef BROKEN_NET_HANDOFF
        ; NetBios executes the resident image with its USART requests still
        ; installed and may have IR2 pending. Close that handoff window before
        ; touching the CP/M stack or workspace; NETINIT later establishes the
        ; selected RomBios-input or fully polled RAM-input interrupt policy.
        di
.endif
.endif
        lxi     sp,0100h

.ifndef RAMKEYBOARD
        ; Publish the BDOS address through the RomBios-owned pointer.
        lhld    BDOSADDR
        lxi     d,FBASE+6
        mov     m,e
        inx     h
        mov     m,d
.endif

        ; Configure the 80-track system volume.  Network B: uses the original
        ; two-sided 160-track geometry through its own DPH/DPB below.
        xra     a
        sta     TYP
        sta     TYPEA
.ifdef NETWORK
        sta     TYPEB
        sta     SEQUENCE
.ifdef NETWORKV2
        sta     NETV2
.endif
        call    NETINIT
.else
        sta     TYPEB
.endif
        mvi     a,80
        sta     SIZEA
.ifndef NETWORK
        sta     SIZEB
.endif
        sta     SIZE
        mvi     a,1
        sta     RATEA
.ifndef NETWORK
        sta     RATEB
.endif
        sta     RATE

.ifdef RAMCONSOLE
.ifndef RAMKEYBOARD
        ; RomBios still owns the frame/keyboard interrupt in Stage 1.  Hide
        ; its independently tracked cursor before the RAM renderer takes over
        ; or the ISR will keep painting a solid block at its stale position.
        mvi     a,01bh
        call    ROMCALL
        dw      WRCHR
        mvi     a,'4'
        call    ROMCALL
        dw      WRCHR
.endif
        call    RAMCONINIT
.endif
.ifdef RAMKEYBOARD
        call    RKINIT
.endif

        xra     a
        sta     CDISK
        sta     HSTACT
        sta     HSTWRT

        call    PRINT
        db      01bh,'L'
        db      0
        lxi     h,VERMSG
        call    PRINTSTR
.ifdef NETWORK
.ifdef NETWORKV2
        call    PRINT
        db      'A: Janet 386K, B: native 784K',13,10
.ifdef NETWORKV3
        db      '19200, NetDisk v3',13,10,10,0
.else
        db      '19200, NetDisk v2',13,10,10,0
.endif
.else
.ifdef NETWORK19200
        call    PRINT
        db      'A: Janet 386K, B: native 784K',13,10
        db      'Network 19200',13,10,10,0
.else
        call    PRINT
        db      'A: Janet 386K, B: native 784K',13,10,10,0
.endif
.endif
.else
        call    PRINT
        db      'A:, B: - 386K floppy',13,10,10,0
.endif
        jmp     GOCPM

VERMSG:
.ifdef RAMKEYBOARD
.ifdef NETWORKV3
        db      'CP/Mish 2.2 Juku RAM BIOS',13,10
        db      'NetDisk v3, read-ahead',13,10
        db      'GPT-5.6 Sol, Arvutimuuseum',13,10
        db      'Danila Sukharev',13,10,0
.else
        db      'CP/Mish 2.2 Juku RAM BIOS',13,10
        db      'NetDisk v2, polled console',13,10
        db      'GPT-5.6 Sol, Arvutimuuseum',13,10
        db      'Danila Sukharev',13,10,0
.endif
.else
.ifdef RAMCONSOLE
        db      'CP/Mish 2.2 Juku RAM output',13,10
        db      'NetDisk v2, 51K experiment',13,10
        db      'GPT-5.6 Sol, Arvutimuuseum',13,10
        db      'Danila Sukharev',13,10,0
.else
.ifdef NETWORKV2
        db      'CP/Mish 2.2 Juku NetDisk v2',13,10
        db      'GPT-5.6 Sol, Arvutimuuseum',13,10
        db      'Danila Sukharev',13,10,0
.else
        db      'CP/Mish 2.2 Juku NETROM2',13,10
        db      'GPT-5.6 Sol, Arvutimuuseum',13,10
        db      'Danila Sukharev',13,10,0
.endif
.endif
.endif

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

.ifndef RAMKEYBOARD
        ; Tell the monitor that CP/M owns the console path.
        lhld    CONCW
        mvi     m,0
.endif

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
.ifdef RAMKEYBOARD
.ifdef NETWORKCONSOLE
        call    NCSTAT
        ora     a
        rnz
.endif
        call    RKSTAT
.else
        call    ROMCALL
        dw      CONSTA
.endif
        ret

CONIN:
.ifdef RAMKEYBOARD
.ifdef NETWORKCONSOLE
CONINWAIT:
        call    NCSTAT
        ora     a
        jnz     CONINREMOTE
        call    RKSTAT
        ora     a
        jz      CONINWAIT
        call    RKIN
        ret
CONINREMOTE:
        call    NCIN
        ret
.else
        call    RKIN
.endif
.else
        call    ROMCALL
        dw      RDCHR
.endif
        ret

CONOUT:
        mov     a,c
.ifdef RAMCONSOLE
        call    RAMCONOUT
.ifdef NETWORKCONSOLE
        call    NCOUT
.endif
.else
        call    ROMCALL
        dw      WRCHR
.endif
        ret

LIST:
        mov     a,c
.ifdef RAMKEYBOARD
        call    RAMCONOUT
.else
        call    ROMCALL
        dw      PRINTCH
.endif
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
.ifdef NETWORK
        cpi     2
.else
        cpi     2
.endif
        rnc

        sta     SEKDSK
.ifdef NETWORK
        ora     a
        lda     TYPEA
        jz      SELTYPE
        lda     TYPEB
SELTYPE:
.else
        ora     a
        lda     TYPEA
        jz      SELTYPE
        lda     TYPEB
SELTYPE:
.endif
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
        mov     a,b
        sta     SEKTRK+1
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
.ifdef NETWORKV3
        call    N3READ
        ret
.else
.ifdef NETWORKV2
        lda     NETV2
        ora     a
        jz      NETV2SINGLE
        mvi     a,DKRC
        jmp     NETRWDISK
NETV2SINGLE:
        mvi     a,DKRD
        jmp     NETRWDISK
.else
        mvi     a,DKRD
.ifdef NETWORK
        jmp     NETRWDISK
.else
        jmp     RWDISK
.endif
.endif
.endif

WRITE:
.ifdef NETWORKV3
        call    N3INV
.endif
        mvi     a,DKWR

.ifdef NETWORK
NETRWDISK:
        public  NRWDISK
NRWDISK:
        sta     REQUEST
        lda     SEQUENCE
        inr     a
        sta     SEQUENCE
.ifdef NETWORKV3
        mvi     a,3
        sta     NETTRIES
.endif
NETRETRY:
.ifndef BROKEN_NET_HANDOFF
        di
        mvi     a,0ffh
        out     PICMASK
        sta     PICSHADOW
.endif
        mvi     a,035h
        out     USARTCTL      ; TxEN + RxE + error reset + RTS
        mvi     b,0
        mvi     a,'J'
        call    NETSEND
        mvi     a,'D'
        call    NETSEND
        lda     REQUEST
        call    NETSEND
        lda     SEQUENCE
        call    NETSEND
        lda     SEKDSK
        call    NETSEND
        lda     SEKTRK
        call    NETSEND
        lda     SEKTRK+1
        call    NETSEND
        lda     SEKSEC
        call    NETSEND
        lda     REQUEST
        cpi     DKWR
        jnz     NETHEADER
        lhld    MEMADR
        mvi     d,128
NETWRITE:
        mov     a,m
        call    NETSEND
        inx     h
        dcr     d
        jnz     NETWRITE
NETHEADER:
        mov     a,b
        call    NETTX

        ; The physical Janet interface is half-duplex. The stock NetBios
        ; clears TxEN before receiving and restores it only while talking.
        ; D11 TxEMPTY is unconnected on Juku, so wait longer than one 8O1
        ; character at 19,200 baud before disabling the transmitter. TxRDY
        ; alone only proves that the holding register has emptied.
        lxi     d,400
NETTXDRAIN:
        dcx     d
        mov     a,d
        ora     e
        jnz     NETTXDRAIN
        mvi     a,034h
        out     USARTCTL      ; receive enabled, transmitter released

NETSYNC:
        call    NETRX
.ifdef NETWORKV3
        jc      NETBAD
.endif
        cpi     'D'
        jnz     NETSYNC
        mvi     b,'D'
        call    NETRX
.ifdef NETWORKV3
        jc      NETBAD
.endif
        xri     'J'
        jnz     NETSYNC
        mov     a,b
        xri     'J'
        mov     b,a
        call    NETRX
.ifdef NETWORKV3
        jc      NETBAD
.endif
        mov     c,a
        xra     b
        mov     b,a
        lda     SEQUENCE
        cmp     c
.ifdef NETWORKV3
        jnz     NETBAD
.else
        jnz     NETRETRY
.endif
        call    NETRX
.ifdef NETWORKV3
        jc      NETBAD
.endif
        mov     c,a
        xra     b
        mov     b,a
        lda     REQUEST
        cpi     DKWR
        jz      NETCHECK
        lhld    MEMADR
.ifdef NETWORKV2
        lda     REQUEST
        cpi     DKRC
        jnz     NETREADRAW
        mov     a,c
        ora     a
        jz      NETREADRAW
        cpi     3
        mvi     e,0e5h
        jz      NETREADFILL
        cpi     2
        jnz     NETCHECK
        call    NETRX
.ifdef NETWORKV3
        jc      NETBAD
.endif
        mov     e,a
        xra     b
        mov     b,a
NETREADFILL:
        mvi     c,0
        mov     a,e
        mvi     d,128
NETFILL:
        mov     m,a
        inx     h
        dcr     d
        jnz     NETFILL
        jmp     NETCHECK
NETREADRAW:
.endif
        mvi     d,128
NETREAD:
        call    NETRX
.ifdef NETWORKV3
        jc      NETBAD
.endif
        mov     m,a
        xra     b
        mov     b,a
        inx     h
        dcr     d
        jnz     NETREAD
NETCHECK:
        call    NETRX
.ifdef NETWORKV3
        jc      NETBAD
.endif
        xra     b
.ifdef NETWORKV3
        jnz     NETBAD
.else
        jnz     NETRETRY
.endif
        mov     a,c
        ora     a
        jz      NETDONE
        mvi     a,1
.ifdef NETWORKV3
        jmp     NETDONE

; Bound a complete transaction to three attempts. Returning a BIOS disk error
; lets BDOS remain interactive; the next disk call starts a fresh sequence and
; can therefore recover after a host reconnect.
NETBAD:
        lda     NETTRIES
        dcr     a
        sta     NETTRIES
        jnz     NETRETRY
        mvi     a,1
.endif
NETDONE:
.ifndef BROKEN_NET_HANDOFF
        push    psw
.ifdef RAMKEYBOARD
        mvi     a,0ffh
.else
        mvi     a,0dfh
.endif
        out     PICMASK
        sta     PICSHADOW
        ei
        pop     psw
.endif
        ret

NETSEND:
        mov     c,a
        xra     b
        mov     b,a
        mov     a,c
NETTX:
        mov     c,a
NETTXWAIT:
        in      USARTCTL
        ani     1
        jz      NETTXWAIT
        mov     a,c
        out     USARTDATA
        ret

NETRX:
.ifdef NETWORKV3
        push    b
        lxi     b,0            ; 65536 status polls, about one second
NETRXWAIT:
        in      USARTCTL
        ani     2
        jnz     NETRXREADY
        dcx     b
        mov     a,b
        ora     c
        jnz     NETRXWAIT
        pop     b
        stc
        ret
NETRXREADY:
        in      USARTDATA
        pop     b
        ora     a              ; return data with carry clear
        ret
.else
        in      USARTCTL
        ani     2
        jz      NETRX
        in      USARTDATA
        ret
.endif

NETINIT:
        di
.ifdef NETWORK19200
        ; BAUDTEST2 proved this exact clock on physical CS00014: mode 2,
        ; BCD, LSB-only, count 4 gives the 8251 a reliable 19,200/x16 RxC.
        ; The sustained bidirectional disk soak also passes on CS00014. Keep
        ; it in a separate high-speed image until another board confirms it.
        mvi     a,015h
        out     PIT3CTL
        mvi     a,4
.else
        mvi     a,8
.endif
        out     PIT3COUNT0
        xra     a
        out     USARTCTL
        out     USARTCTL
        out     USARTCTL
        mvi     a,040h
        out     USARTCTL
        mvi     a,05eh
        out     USARTCTL
        mvi     a,034h
        out     USARTCTL      ; receive-only until NETRWDISK owns a Tx turn
        in      USARTDATA
NETREADY:
        call    NETRX
        cpi     'N'
        jnz     NETREADY
        call    NETRX
        cpi     'R'
        jnz     NETREADY
.ifdef NETWORKV3
        ; N4 selects v3 plus the optional remote console, N3 selects disk only,
        ; N2 selects compact single-record fallback, and repeated legacy NR
        ; leaves mode 1. The helper owns all four paths.
        mvi     c,1
        call    NETRX
        cpi     'N'
        jnz     NETV3DONE
        call    NETRX
.ifdef NETWORKCONSOLE
        cpi     '4'
        jz      NETV4MARK
.endif
        cpi     '3'
        jz      NETV3MARK
        cpi     '2'
        jnz     NETV3DONE
        mvi     c,2
        jmp     NETV3DONE
NETV3MARK:
        mvi     c,3
.ifdef NETWORKCONSOLE
        jmp     NETV3DONE
NETV4MARK:
        mvi     c,3
        call    NCENA
.endif
NETV3DONE:
        mov     a,c
        call    N3ENA
.else
.ifdef NETWORKV2
        ; A v2 host appends N2 to NR.  With a legacy host these reads consume
        ; its next repeated NR marker and fall back after about 20 ms.
        call    NETRX
        cpi     'N'
        jnz     NETCAPDONE
        call    NETRX
        cpi     '2'
        jnz     NETCAPDONE
        mvi     a,0ffh
        sta     NETV2
NETCAPDONE:
.endif
.endif
.ifndef BROKEN_NET_HANDOFF
        ; NET_USART_INIT registered handlers 2, 3 and 9 through RomBios FF89.
        ; Restore those three service-vector slots to their pre-NetBios RET
        ; entries. In particular, service 9 runs from the normal frame path,
        ; so masking IR2/IR3 alone does not detach NetBios from RomBios.
        mvi     a,0c9h
        sta     0d773h
        sta     0d777h
        sta     0d78fh
.ifdef RAMKEYBOARD
        ; The RAM BIOS polls the matrix and needs no firmware IRQ service.
        ; Mask every PIC input while retaining a coherent shadow for any
        ; subsequently inspected RomBios state.
        mvi     a,0ffh
.else
        ; Leave the monitor's D79F dispatcher and IR5 frame/keyboard service
        ; untouched, exactly as the normal EKDOS console path expects.
        mvi     a,0dfh
.endif
        out     PICMASK
        sta     PICSHADOW
        ei
.endif
        ret
.else
RWDISK:
        sta     REQUEST
        ; Match EKDOS's VIARV retry budget. Physical writes can require a
        ; retry after the controller's read-before-write/cache transition.
        mvi     a,10
        sta     RCOUNT
        lda     REQUEST
        call    ROMCALL
        dw      RWFLOPPY
        lda     ERRC
        ora     a
        rz
        mvi     a,1
        ret
.endif

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

; Print the zero-terminated string at HL without embedding it at the call site.
PRINTSTR:
        mov     a,m
        inx     h
        ora     a
        rz
        mov     c,a
        push    h
        call    CONOUT
        pop     h
        jmp     PRINTSTR

; Juku's 10 physical 512-byte sectors are exposed as 40 CP/M records.
TRANS:
        db      1,2,3,4,9,10,11,12
        db      17,18,19,20,25,26,27,28
        db      33,34,35,36,5,6,7,8
        db      13,14,15,16,21,22,23,24
        db      29,30,31,32,37,38,39,40

DPH0:   dw      TRANS,0,0,0,DIRBUF,DPB0,CHK0,ALLOC0
.ifdef NETWORK
DPH1:   dw      TRANS,0,0,0,DIRBUF,DPB1,CHK1,ALLOC1
.else
DPH1:   dw      TRANS,0,0,0,DIRBUF,DPB0,CHK1,ALLOC1
.endif

; One 80-track side, 10 x 512 bytes, two reserved tracks, 2K blocks.
DPB0:   dw      40
        db      4,15,1
        dw      0c2h
        dw      127
        db      0c0h,0
        dw      32
        dw      2

.ifdef NETWORK
; Original two-sided Juku game-disk geometry: 160 logical tracks, 4K blocks.
; DSM 196 and AL0 80h are the period EKDOS full-disk values.  The final
; half-block is the known Juku phantom boundary and is not allocated by the
; published game disks.
DPB1:   dw      40
        db      5,31,3
        dw      196
        dw      127
        db      080h,0
        dw      32
        dw      2
.endif

REQUEST: db     0
.ifdef NETWORK
SEQUENCE: db    0
.ifdef NETWORKV2
NETV2:   db     0
.endif
.ifdef NETWORKV3
NETTRIES:db     0
.endif
.endif

; These words must remain visible when a monitor call returns with the ROM
; overlay active. EKDOS therefore keeps them above the overlay window rather
; than inside the CA00h BIOS image.
SAVEHL   equ    0d2feh
SAVESP   equ    0d2fch
ROMSTACK equ    SAVESP
; BDOS scratch space is intentionally outside the initialized BIOS
; image, matching the established EKDOS memory map.
; Fixed outside both initialized resident layouts. This gives the relocated
; RAM-console BIOS its complete C600h..CDFFh window.
.ifdef NETWORKV3
; The complete 94-glyph RAM font now reaches just beyond CE00h. In permanent
; all-RAM mode, move the transient BDOS buffers above the NetDisk-v3 code so
; directory traffic cannot overwrite the final glyphs. This storage is runtime
; state, not part of the initialized container.
DIRBUF   equ    0d640h
.else
DIRBUF   equ    0ce00h
.endif
ALLOC0   equ    DIRBUF+128
ALLOC1   equ    ALLOC0+32
CHK0     equ    ALLOC1+32
CHK1     equ    CHK0+32

.ifdef RAMCONSOLE
        include "ram-console.asm"
.endif

        end
