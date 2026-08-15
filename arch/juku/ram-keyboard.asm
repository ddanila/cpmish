; Polled Juku keyboard for the RAM-owned BIOS.
;
; D26 port A selects one of the fifteen matrix columns. Port B returns the
; 74148 row code plus the dedicated active-low SHIFT and CTRL contacts. This
; implementation deliberately needs no RomBios state and no frame interrupt.

        cseg
        public  RKINIT
        public  RKSTAT
        public  RKIN

KEYCOLPORT      equ     004h
KEYROWPORT      equ     005h

RKINIT:
        xra     a
        sta     RAMKEYDOWN
        sta     RAMKEYREADY
        sta     RAMKEYCHAR
        ret

; Return FFh if a translated key is pending, zero otherwise. A physical key
; must be released before another press is accepted, which supplies the
; debounce/one-character semantics CP/M expects from repeated CONST calls.
RKSTAT:
        lda     RAMKEYREADY
        ora     a
        jz      RAMKEYNEW
        mvi     a,0ffh
        ret
RAMKEYNEW:
        call    RAMKEYSCAN
        mov     e,a
        lda     RAMKEYDOWN
        ora     a
        jz      RAMKEYUP
        mov     a,e
        ora     a
        jnz     RAMKEYNONE
        sta     RAMKEYDOWN
        ret
RAMKEYUP:
        mov     a,e
        ora     a
        rz
        sta     RAMKEYCHAR
        mvi     a,1
        sta     RAMKEYDOWN
        sta     RAMKEYREADY
        mvi     a,0ffh
        ret
RAMKEYNONE:
        xra     a
        ret

RKIN:
        call    RKSTAT
        ora     a
        jz      RKIN
        xra     a
        sta     RAMKEYREADY
        lda     RAMKEYCHAR
        ret

; Scan all columns and return one ASCII/control byte, or zero for no supported
; contact. The table is indexed as column*6 plus the drawing's encoder input.
RAMKEYSCAN:
        push    b
        push    d
        push    h
        mvi     b,0
RAMKEYCOL:
        mov     a,b
        out     KEYCOLPORT
        in      KEYROWPORT
        mov     c,a
        ani     00fh
        cpi     00fh
        jnz     RAMKEYFOUND
        inr     b
        mov     a,b
        cpi     15
        jc      RAMKEYCOL
        xra     a
        jmp     RAMKEYDONE

RAMKEYFOUND:
        ; HL = column*6.
        mov     l,b
        mvi     h,0
        dad     h
        mov     d,h
        mov     e,l
        dad     h
        dad     d

        ; Encoded low nibble is 0Eh,0Ch,...,04h for rows 0..5.
        mov     a,c
        cma
        ani     00eh
        rrc
        mov     e,a
        mvi     d,0
        dad     d
        lxi     d,RAMKEYTABLE
        dad     d
        mov     b,m
        mov     a,b
        ora     a
        jz      RAMKEYDONE

        ; CTRL turns ASCII letters into CP/M control codes.
        mov     a,c
        ani     080h
        jnz     RAMKEYSHIFT
        mov     a,b
        ani     05fh
        cpi     'A'
        jc      RAMKEYBASE
        cpi     'Z'+1
        jnc     RAMKEYBASE
        ani     01fh
        jmp     RAMKEYDONE

RAMKEYSHIFT:
        mov     a,c
        ani     040h
        jnz     RAMKEYBASE
        mov     a,b
        cpi     'a'
        jc      RAMKEYSHIFTPUNCT
        cpi     'z'+1
        jnc     RAMKEYSHIFTPUNCT
        sui     020h
        jmp     RAMKEYDONE
RAMKEYSHIFTPUNCT:
        lxi     h,RAMKEYSHIFTS
RAMKEYSHIFT1:
        mov     a,m
        ora     a
        jz      RAMKEYBASE
        cmp     b
        inx     h
        jz      RAMKEYSHIFTED
        inx     h
        jmp     RAMKEYSHIFT1
RAMKEYSHIFTED:
        mov     a,m
        jmp     RAMKEYDONE
RAMKEYBASE:
        mov     a,b
RAMKEYDONE:
        pop     h
        pop     d
        pop     b
        ret

; Rows are encoder inputs 0..5 (factory rows 5,4,6,2,1,3).
RAMKEYTABLE:
        db      0,'n',0,'y','6','h'
        db      0,'x',0,'w','2','s'
        db      0,'v',0,'r','4','f'
        db      0,0,0,09h,01bh,0
        db      0,'b',0,'t','5','g'
        db      0,'z',0,'q','1','a'
        db      0,'c',0,'e','3','d'
        db      0,'m',0,'u','7','j'
        db      0,0,07fh,']',0,0dh
        db      0,0,0,'[',0,0
        db      0,0,0,0,0,':'
        db      0,';',020h,05ch,'-',0
        db      0,'/',0,'p','0',0
        db      0,'.',08h,'o','9','l'
        db      0,',',0,'i','8','k'

; Interleaved unshifted/shifted punctuation pairs, zero terminated.
RAMKEYSHIFTS:
        db      '0','_','1','!','2',022h,'3','#','4','$'
        db      '5','%','6','&','7',027h,'8','(','9',')'
        db      '.','>',',','<','/','?',';','+','-','='
        db      ':','*',05ch,'^',0

RAMKEYDOWN:     db      0
RAMKEYREADY:    db      0
RAMKEYCHAR:     db      0

        end
