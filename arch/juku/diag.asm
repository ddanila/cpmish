; CP/M front end for the shared, non-destructive Juku diagnostics.
; Copyright (c) 2026 Danila Sukharev
; Distributed under the 2-clause BSD license; see COPYING.cpmish.

BDOS            equ     5
CONOUT          equ     2
PRINT           equ     9
COMMAND_LENGTH  equ     080h
COMMAND_TEXT    equ     081h

        org     0100h

start:
        lxi     d,banner
        call    print_string

        lda     COMMAND_LENGTH
        ora     a
        jz      run_memory      ; preserve the original no-argument baseline
        mov     b,a
        lxi     h,COMMAND_TEXT
skip_space:
        mov     a,m
        cpi     ' '
        jz      skip_one
        cpi     9
        jnz     select_test
skip_one:
        inx     h
        dcr     b
        jnz     skip_space
        jmp     run_memory

select_test:
        ani     05fh            ; accept upper/lower-case selector names
        cpi     'C'
        jz      run_cpu
        cpi     'M'
        jz      run_memory
        cpi     'A'
        jz      run_all
        lxi     d,usage
        jmp     print_string

run_all:
        call    run_cpu_sub
        jmp     run_memory

run_cpu:
        call    run_cpu_sub
        ret

run_cpu_sub:
        lxi     d,cpu_label
        call    print_string
        call    diag_cpu_test
        jmp     print_result

run_memory:
        lxi     d,memory_label
        call    print_string
        lxi     h,test_buffer
        lxi     d,test_buffer_end
        call    diag_memory_test
        jmp     print_result

; A is zero for PASS or a structured failure-bit mask.
print_result:
        ora     a
        jnz     print_failure
        lxi     d,passed
        jmp     print_string
print_failure:
        push    psw
        lxi     d,failed
        call    print_string
        pop     psw
        call    print_hex
        lxi     d,newline
        jmp     print_string

print_string:
        mvi     c,PRINT
        call    BDOS
        ret

print_hex:
        push    psw
        rrc
        rrc
        rrc
        rrc
        ani     00fh
        call    print_nibble
        pop     psw
        ani     00fh
print_nibble:
        adi     '0'
        cpi     '9'+1
        jc      print_digit
        adi     'A'-'9'-1
print_digit:
        mov     e,a
        mvi     c,CONOUT
        call    BDOS
        ret

banner:
        db      13,10,'Juku Diag 0.3',13,10
        db      'Shared non-destructive 8080 diagnostics.',13,10
        db      'Usage: DIAG [CPU|MEM|ALL]',13,10
        db      'No argument keeps the private RAM test.',13,10,'$'
usage:
        db      'Unknown selector. Use CPU, MEM, or ALL.',13,10,'$'
cpu_label:
        db      'CPU: $'
memory_label:
        db      'RAM: $'
passed:
        db      'PASS',13,10,'$'
failed:
        db      'FAIL mask $'
newline:
        db      13,10,'$'

        include "cpu.asm"
        include "memory.asm"

; Deliberately private storage: testing it cannot overwrite CP/M, this program,
; its stack, or the transient program command tail. The returned A byte is the
; accumulated stuck/mismatching data-bit mask.
test_buffer:
        ds      256
test_buffer_end:

        end     start
