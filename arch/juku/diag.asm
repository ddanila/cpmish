; CP/M wrapper for the shared Juku RAM diagnostic.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.

BDOS            equ     5
PRINT           equ     9

        org     0100h

start:
        lxi     d,banner
        mvi     c,PRINT
        call    BDOS

        lxi     h,test_buffer
        lxi     d,test_buffer_end
        call    diag_memory_test
        ora     a
        jnz     failed

        lxi     d,passed
        jmp     report

failed:
        lxi     d,failed_message

report:
        mvi     c,PRINT
        call    BDOS
        ret

banner:
        db      13,10,'JUKU DIAG 0.1',13,10
        db      'Shared non-destructive RAM cell test: $'
passed:
        db      'PASS',13,10,'$'
failed_message:
        db      'FAIL',13,10,'$'

        include "memory.asm"

; Deliberately private storage: testing it cannot overwrite CP/M, this program,
; its stack, or the transient program command tail.
test_buffer:
        ds      256
test_buffer_end:

        end     start
