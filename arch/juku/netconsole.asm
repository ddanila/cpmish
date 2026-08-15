; Optional remote CP/M console multiplexed over the resident Janet USART.
;
; N4 capability negotiation enables this module. Local screen and keyboard
; remain authoritative. Output is mirrored with one bounded transaction per
; character; status polls are rate-limited while idle. A missing/broken host
; disables mirroring and polling until a later status call reprobes it.

        cseg
        public  NCENA
        public  NCSTAT
        public  NCIN
        public  NCOUT

USARTDATA      equ     008h
USARTCTL       equ     009h
NC_POLL        equ     020h
NC_OUT         equ     021h

NCENA: mvi     a,1
        sta     NCPRES
        sta     NCEN
        sta     NCBACK         ; poll on the first remote status call
        xra     a
        sta     NCHAVE
        ret

; Return FFh when a remote byte is cached, otherwise zero. Preserve BC/DE/HL.
NCSTAT:
        push    b
        push    d
        push    h
        lda     NCHAVE
        ora     a
        jnz     NCSTRET
        lda     NCPRES
        ora     a
        jz      NCSTZERO
        lda     NCEN
        ora     a
        jz      NCSTDISABLED
        lda     NCBACK
        dcr     a
        sta     NCBACK
        jnz     NCSTZERO
        mvi     a,64           ; idle floor poll, not one turn per CONST
        sta     NCBACK
        jmp     NCSTPOLL
NCSTDISABLED:
        lda     NCBACK
        dcr     a
        sta     NCBACK
        jnz     NCSTZERO
NCSTPOLL:
        xra     a
        sta     NCARG
        mvi     a,NC_POLL
        call    NCCALL
        lda     NCHAVE
        ora     a
        jnz     NCSTRET
NCSTZERO:
        xra     a
NCSTRET:
        pop     h
        pop     d
        pop     b
        ret

; Consume the cached remote byte. Caller first checks NCSTAT.
NCIN:  lda     NCKEY
        push    psw
        xra     a
        sta     NCHAVE
        pop     psw
        ret

; Mirror A when enabled. Host loss is deliberately invisible to CONOUT.
NCOUT: push    psw
        push    b
        push    d
        push    h
        sta     NCARG
        lda     NCEN
        ora     a
        jz      NCOUTDONE
        mvi     a,NC_OUT
        call    NCCALL
NCOUTDONE:
        pop     h
        pop     d
        pop     b
        pop     psw
        ret

; A=operation, NCARG=argument. Return zero for a valid status 0/2 response.
NCCALL:sta     NCOP
        lda     NCSEQ
        inr     a
        sta     NCSEQ
        mvi     a,035h
        out     USARTCTL       ; TxEN + RxE + error reset + RTS
        mvi     b,0
        mvi     a,'J'
        call    NCSEND
        mvi     a,'D'
        call    NCSEND
        lda     NCOP
        call    NCSEND
        lda     NCSEQ
        call    NCSEND
        lda     NCARG
        call    NCSEND
        xra     a
        call    NCSEND
        xra     a
        call    NCSEND
        xra     a
        call    NCSEND
        mov     a,b
        call    NCTX

        lxi     d,400
NCDRAIN:
        dcx     d
        mov     a,d
        ora     e
        jnz     NCDRAIN
        mvi     a,034h
        out     USARTCTL       ; release the half-duplex transmitter

NCSYNC:call    NCRX
        jc      NCFAIL
        cpi     'D'
        jnz     NCSYNC
        mvi     b,'D'
        call    NCRX
        jc      NCFAIL
        mov     c,a
        xra     b
        mov     b,a
        mov     a,c
        cpi     'J'
        jnz     NCSYNC
        call    NCRXC
        jc      NCFAIL
        mov     c,a
        lda     NCSEQ
        cmp     c
        jnz     NCFAIL
        call    NCRXC
        jc      NCFAIL
        sta     NCSTATUS
        cpi     2
        jnz     NCNOKEY
        call    NCRXC
        jc      NCFAIL
        sta     NCKEY
        mvi     a,0ffh
        sta     NCHAVE
NCNOKEY:
        call    NCRX
        jc      NCFAIL
        cmp     b
        jnz     NCFAIL
        lda     NCSTATUS
        ora     a
        jz      NCSUCCESS
        cpi     2
        jnz     NCFAIL
NCSUCCESS:
        mvi     a,1
        sta     NCEN
        xra     a
        ret

NCFAIL:xra     a
        sta     NCEN
        sta     NCHAVE
        sta     NCBACK         ; underflow gives 256 local CONST calls
        mvi     a,1
        ret

NCSEND:mov     c,a
        xra     b
        mov     b,a
        mov     a,c
NCTX:  mov     c,a
NCTX1: in      USARTCTL
        ani     1
        jz      NCTX1
        mov     a,c
        out     USARTDATA
        ret

; Short console wait: roughly one eighth of the disk byte timeout.
NCRX:  push    b
        lxi     b,8192
NCRX1: in      USARTCTL
        ani     2
        jnz     NCRX2
        dcx     b
        mov     a,b
        ora     c
        jnz     NCRX1
        pop     b
        stc
        ret
NCRX2: in      USARTDATA
        pop     b
        ora     a
        ret
NCRXC:call    NCRX
        rc
        mov     c,a
        xra     b
        mov     b,a
        mov     a,c
        ora     a
        ret

NCEN:  db      0
NCPRES:db      0
NCBACK:db      0
NCHAVE:db      0
NCKEY: db      0
NCSEQ: db      0
NCOP:  db      0
NCARG: db      0
NCSTATUS:db    0
