; NetDisk v3 read-ahead client for the independent Juku RAM BIOS.
;
; Replies carry up to three translated CP/M records, a bounded encoding per
; record, and CRC-16/IBM over the complete DJ body. The cache occupies only
; reclaimed RomBios workspace and is never used by the frozen RomBios builds.

        cseg
        public  N3READ
        public  N3INV
        public  N3ENA
        extrn   NRWDISK

USARTDATA      equ     008h
USARTCTL       equ     009h
.ifdef CPM3ADAPTER
SEKDSK         equ     0b11ah
SEKTRK         equ     0b11bh
SEKSEC         equ     0b11dh
MEMADR         equ     0b12eh
.else
SEKDSK         equ     0d61ah
SEKTRK         equ     0d61bh
SEKSEC         equ     0d61dh
MEMADR         equ     0d62eh
.endif
DKRD           equ     011h
DKRC           equ     013h
DKRA           equ     014h

.ifdef CPM3ADAPTER
CACHE          equ     0b280h
.else
CACHE          equ     0d080h
.endif
SLOTSIZE       equ     131

N3ENA: sta     N3MODE
N3INV: xra     a
        sta     N3COUNT
        ret

N3READ:
        lda     N3MODE
        cpi     3
        jz      N3LOOK
        cpi     2
        mvi     a,DKRC
        jz      NRWDISK
        mvi     a,DKRD
        jmp     NRWDISK

; Search all cached track/sector keys before asking the host again.
N3LOOK: lda     N3COUNT
        ora     a
        jz      N3MISS
        mov     b,a
        lda     N3DRIVE
        mov     c,a
        lda     SEKDSK
        cmp     c
        jnz     N3MISS
        lxi     h,CACHE
N3LK1: lda     SEKTRK
        cmp     m
        jnz     N3NEXT
        inx     h
        lda     SEKTRK+1
        cmp     m
        dcx     h
        jnz     N3NEXT
        inx     h
        inx     h
        lda     SEKSEC
        cmp     m
        dcx     h
        dcx     h
        jz      N3COPY
N3NEXT:lxi     d,SLOTSIZE
        dad     d
        dcr     b
        jnz     N3LK1

N3MISS:
        lda     N3SEQ
        inr     a
        sta     N3SEQ
        mvi     a,3
        sta     N3TRIES
N3RETRY:
        mvi     a,035h
        out     USARTCTL
        mvi     b,0
        mvi     a,'J'
        call    N3SEND
        mvi     a,'D'
        call    N3SEND
        mvi     a,DKRA
        call    N3SEND
        lda     N3SEQ
        call    N3SEND
        lda     SEKDSK
        call    N3SEND
        lda     SEKTRK
        call    N3SEND
        lda     SEKTRK+1
        call    N3SEND
        lda     SEKSEC
        call    N3SEND
        mov     a,b
        call    N3TX
        lxi     b,400
N3DRAIN:
        dcx     b
        mov     a,b
        ora     c
        jnz     N3DRAIN
        mvi     a,034h
        out     USARTCTL

N3SYNC:call    N3RX
        jc      N3BAD
        cpi     'D'
        jnz     N3SYNC
        call    N3RX
        jc      N3BAD
        cpi     'J'
        jnz     N3SYNC
        lxi     d,0
        mvi     a,'D'
        call    N3CRC
        mvi     a,'J'
        call    N3CRC
        call    N3RXC
        jc      N3BAD
        mov     c,a
        lda     N3SEQ
        cmp     c
        jnz     N3BAD
        call    N3RXC
        jc      N3BAD
        sta     N3STATUS
        call    N3RXC
        jc      N3BAD
        ora     a
        jz      N3END
        cpi     4
        jnc     N3BAD
        sta     N3COUNT
        mov     c,a
        lxi     h,CACHE
N3REC: call    N3RXC
        jc      N3BAD
        mov     m,a
        inx     h
        call    N3RXC
        jc      N3BAD
        mov     m,a
        inx     h
        call    N3RXC
        jc      N3BAD
        mov     m,a
        inx     h
        call    N3RXC
        jc      N3BAD
        ora     a
        jz      N3RAW
        dcr     a
        jz      N3FILLRX
        dcr     a
        jz      N3E5
        dcr     a
        jnz     N3BAD
        call    N3RXC
        jc      N3BAD
        cpi     128
        jnc     N3BAD
        sta     N3PREFIX
        mov     b,a
N3PREF:mov     a,b
        ora     a
        jz      N3PREEND
        call    N3RXC
        jc      N3BAD
        mov     m,a
        inx     h
        dcr     b
        jmp     N3PREF
N3PREEND:
        call    N3RXC
        jc      N3BAD
        mov     b,a
        lda     N3PREFIX
        cma
        adi     129
        sta     N3LEFT
        jmp     N3FIL1

N3RAW: mvi     b,128
N3RAW1:call    N3RXC
        jc      N3BAD
        mov     m,a
        inx     h
        dcr     b
        jnz     N3RAW1
        jmp     N3RDN
N3FILLRX:
        call    N3RXC
        jc      N3BAD
        jmp     N3FILL
N3E5:  mvi     a,0e5h
N3FILL:mov     b,a
        mvi     a,128
        sta     N3LEFT
N3FIL1:mov     m,b
        inx     h
        lda     N3LEFT
        dcr     a
        sta     N3LEFT
        jnz     N3FIL1
N3RDN: dcr     c
        jnz     N3REC

N3END: call    N3RX
        jc      N3BAD
        cmp     d
        jnz     N3BAD
        call    N3RX
        jc      N3BAD
        cmp     e
        jnz     N3BAD
        lda     N3STATUS
        ora     a
        jnz     N3ERROR
        lda     SEKDSK
        sta     N3DRIVE
        lxi     h,CACHE
N3COPY:inx     h
        inx     h
        inx     h
        xchg
        lhld    MEMADR
        xchg
        mvi     b,128
N3CP1: mov     a,m
        stax    d
        inx     h
        inx     d
        dcr     b
        jnz     N3CP1
        xra     a
        ret
N3ERROR:
        call    N3INV
        mvi     a,1
        ret

N3BAD: lda     N3TRIES
        dcr     a
        sta     N3TRIES
        jnz     N3RETRY
        jmp     N3ERROR

N3SEND:mov     c,a
        xra     b
        mov     b,a
        mov     a,c
N3TX:  mov     c,a
N3TX1: in      USARTCTL
        ani     1
        jz      N3TX1
        mov     a,c
        out     USARTDATA
        ret
N3RX:  push    b
        lxi     b,0            ; 65536 status polls, about one second
N3RX1: in      USARTCTL
        ani     2
        jnz     N3RX2
        dcx     b
        mov     a,b
        ora     c
        jnz     N3RX1
        pop     b
        stc
        ret
N3RX2:
        in      USARTDATA
        pop     b
        ora     a              ; return data with carry clear
        ret
N3RXC: call    N3RX
        rc
        push    psw
        call    N3CRC
        pop     psw
        ret

; CRC-16/IBM, input byte A and running CRC DE; preserves HL.
N3CRC: push    h
        xra     e
        mov     l,a
        add     a
        push    psw
        xra     l
        mov     l,a
        pop     psw
        mvi     a,0
        jpe     N3CPE
        mvi     a,3
N3CPE: jnc     N3CNC
        xri     2
N3CNC: mov     h,a
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

N3MODE: db      1
N3SEQ:  db      0
N3COUNT:db      0
N3DRIVE:db      0
N3STATUS:db     0
N3LEFT: db      0
N3PREFIX:db     0
N3TRIES:db      0
        end
