; No-console sequential-read benchmark for the network disk path.
; It opens README.TXT and reads every 128-byte record into a private DMA area.

BDOS    equ     0005h

        org     0100h
        lxi     d,FCB
        mvi     c,15           ; OPEN
        call    BDOS
        inr     a
        rz                     ; FFh: file not found
        lxi     d,BUFFER
        mvi     c,26           ; SET DMA
        call    BDOS
READNEXT:
        lxi     d,FCB
        mvi     c,20           ; READ SEQUENTIAL
        call    BDOS
        ora     a
        jz      READNEXT
        ret

FCB:    db      0
        db      'README  TXT'
        ds      24,0
BUFFER: ds      128,0
        end
