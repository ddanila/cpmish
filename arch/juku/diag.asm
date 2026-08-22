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
        jz      show_usage
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
        jmp     show_usage

select_test:
        ani     05fh            ; accept upper/lower-case selector names
        cpi     'C'
        jz      run_cpu
        cpi     'M'
        jz      run_memory
        cpi     'R'
        jz      select_ram_test
        cpi     'A'
        jz      select_a_test
        cpi     'S'
        jz      run_checksum
        cpi     'H'
        jz      show_usage
        cpi     '?'
        jz      show_usage
        lxi     d,unknown_selector
        call    print_string
show_usage:
        lxi     d,usage
        jmp     print_string

select_ram_test:
        inx     h
        mov     a,m
        ani     05fh
        cpi     'E'             ; RET; bare R or RAM selects the suite
        jz      run_retention
        jmp     run_ram_suite

select_a_test:
        inx     h
        mov     a,m
        ani     05fh
        cpi     'D'             ; ADDR rather than ALL
        jz      run_address
        jmp     run_all

run_all:
        call    run_cpu_sub
        call    run_ram_suite_sub
        jmp     run_checksum

run_cpu:
        call    run_cpu_sub
        ret

run_cpu_sub:
        lxi     d,cpu_label
        call    print_string
        call    diag_cpu_test
        jmp     print_result

run_ram_suite:
        call    run_ram_suite_sub
        ret

run_ram_suite_sub:
        call    run_memory_sub
        call    run_address_sub
        jmp     run_retention_sub

run_memory:
        call    run_memory_sub
        ret

run_memory_sub:
        lxi     d,memory_label
        call    print_string
        lxi     h,test_buffer
        lxi     d,test_buffer_end
        call    diag_memory_test
        jmp     print_result

run_address:
        call    run_address_sub
        ret

run_address_sub:
        lxi     d,address_label
        call    print_string
        lxi     h,test_buffer
        mvi     a,8             ; A0..A7 within the private 256-byte page
        call    diag_memory_address_test
        jmp     print_result

run_retention:
        call    run_retention_sub
        ret

run_retention_sub:
        lxi     d,retention_label
        call    print_string
        lxi     h,test_buffer
        lxi     b,0ffffh        ; caller-owned hold, twice, while raster runs
        call    diag_memory_retention_test
        jmp     print_result

run_checksum:
        lxi     d,checksum_label
        call    print_string
        lxi     h,checksum_fixture
        lxi     d,checksum_fixture_end
        call    diag_checksum8
        xri     078h            ; sum(00h..0Fh)
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
        db      13,10,'Juku Diag 0.5',13,10
        db      'Shared non-destructive 8080 diagnostics.',13,10,'$'
usage:
        db      'Usage: DIAG [CPU|MEM|ADDR|RET|RAM|SUM|ALL|HELP]',13,10,'$'
unknown_selector:
        db      'Unknown diagnostic selector.',13,10,'$'
cpu_label:
        db      'CPU: $'
memory_label:
        db      'RAM data: $'
address_label:
        db      'RAM address: $'
retention_label:
        db      'RAM retention: $'
checksum_label:
        db      'Checksum: $'
passed:
        db      'PASS',13,10,'$'
failed:
        db      'FAIL mask $'
newline:
        db      13,10,'$'

        include "cpu.asm"
        include "memory.asm"
        include "memory-address.asm"
        include "memory-retention.asm"
        include "checksum.asm"

checksum_fixture:
        db      00h,01h,02h,03h,04h,05h,06h,07h
        db      08h,09h,0ah,0bh,0ch,0dh,0eh,0fh
checksum_fixture_end:

; Deliberately private storage: testing it cannot overwrite CP/M, this program,
; its stack, or the transient program command tail. The returned A byte is the
; accumulated stuck/mismatching data-bit mask.
test_buffer:
        ds      256
test_buffer_end:

        end     start
