; Resilient, automatically loaded Juku receive-boundary diagnostic.
;
; The program is fetched from the proven 9600/8O1 resident network disk and
; then runs three self-contained stages.  Every case resets the 8251, announces
; a checksummed descriptor, searches for a framed host packet with a bounded
; timeout, and emits three copies of a checksummed report.  No host ACK is
; required, so a lost byte, report, host process, or cable cannot strand the
; machine at a diagnostic rate: the table eventually completes and restores
; stock 9600/x16/mode-3 operation.

USARTDATA       equ     008h
USARTCTL        equ     009h
PITCOUNT0       equ     018h
PITCTL          equ     01bh

PAT_INC         equ     0
PAT_ZERO        equ     1
PAT_FF          equ     2
PAT_55          equ     3
PAT_AA          equ     4
PAT_DEC         equ     5
PAT_WALK1       equ     6
PAT_WALK0       equ     7
PAT_PRBS        equ     8

        org     0100h

start:
        di
        ; Finish all network-disk traffic before changing either endpoint.
        call    init_stock
        call    tx_enable
        lxi     h,start_marker
        mvi     d,4
        call    send_block
        call    tx_drain
        call    tx_disable
        call    switch_wait

        ; Stage 0: the failing stock-clock-shape 19,200/x16 path.
        mvi     a,0
        sta     current_stage
        mvi     a,01fh          ; ch0, LSB, mode 3 alias, BCD
        out     PITCTL
        mvi     a,4
        out     PITCOUNT0
        mvi     a,05eh          ; x16, 8 data, odd parity, one stop
        sta     current_mode
        lxi     h,stage0_cases
        mvi     b,STAGE0_COUNT
        call    run_stage

        ; Stage 1: same nominal line rate as 9600, but x64/count-2 sampling.
        mvi     a,1
        call    announce_transition
        mvi     a,1
        sta     current_stage
        mvi     a,01fh
        out     PITCTL
        mvi     a,2
        out     PITCOUNT0
        mvi     a,05fh          ; x64, 8 data, odd parity, one stop
        sta     current_mode
        lxi     h,stage1_cases
        mvi     b,STAGE1_COUNT
        call    run_stage

        ; Stage 2: 19,200/x16 with 8253 mode 2 instead of symmetric mode 3.
        mvi     a,2
        call    announce_transition
        mvi     a,2
        sta     current_stage
        mvi     a,015h          ; ch0, LSB, mode 2, BCD
        out     PITCTL
        mvi     a,4
        out     PITCOUNT0
        mvi     a,05eh
        sta     current_mode
        lxi     h,stage2_cases
        mvi     b,STAGE2_COUNT
        call    run_stage

        ; Announce the final transition at 19,200, then always restore the
        ; exact stock mode-3/count-8/x16 configuration before returning.
        mvi     a,0ffh
        call    announce_transition
        call    init_stock
        call    tx_enable
        lxi     h,done_marker
        mvi     b,5
done_repeat:
        push    b
        lxi     h,done_marker
        mvi     d,4
        call    send_block
        pop     b
        dcr     b
        jnz     done_repeat
        call    tx_drain
        call    tx_disable
        ret

; A=next stage.  Send five checksummed end frames at the old rate, drain, and
; wait long enough for the host to reconfigure before the next stage speaks.
announce_transition:
        sta     next_stage
        call    tx_enable
        mvi     b,5
transition_repeat:
        push    b
        call    send_end_frame
        pop     b
        dcr     b
        jnz     transition_repeat
        call    tx_drain
        call    tx_disable
        call    switch_wait
        ret

; HL=seven-byte descriptor table, B=case count.
run_stage:
        shld    case_ptr
        mov     a,b
        sta     cases_left
        xra     a
        sta     current_case
stage_case_loop:
        lhld    case_ptr
        mov     a,m
        sta     case_length
        inx     h
        mov     a,m
        sta     case_pattern
        inx     h
        mov     a,m
        sta     case_idle
        inx     h
        mov     a,m
        sta     case_preamble
        inx     h
        mov     a,m
        sta     case_chunk
        inx     h
        mov     a,m
        sta     case_gap
        inx     h
        mov     a,m
        sta     case_repeat
        inx     h
        shld    case_ptr

        call    init_current
        ; Repeated outbound descriptors survive a lost host byte. The host
        ; deliberately waits for all copies before transmitting. Reinitialize
        ; once more afterward to discard any premature input or overrun.
        call    tx_enable
        mvi     b,3
ready_repeat:
        push    b
        call    send_ready_frame
        pop     b
        dcr     b
        jnz     ready_repeat
        call    tx_drain
        call    tx_disable
        call    init_current
        ; This final copy is the go-ahead: by the time the host receives it,
        ; the target is no longer going to reset or discard its receive byte.
        call    tx_enable
        call    send_ready_frame
        ; Do not add a fixed drain here. The host cannot receive the complete
        ; descriptor until its final checksum has left D11, and may begin its
        ; reply immediately. Enter the receive poll before that first byte.
        call    receive_case
        call    tx_enable
        mvi     b,3
report_repeat:
        push    b
        call    send_report_frame
        pop     b
        dcr     b
        jnz     report_repeat
        call    tx_drain
        call    tx_disable

        lda     current_case
        inr     a
        sta     current_case
        lda     cases_left
        dcr     a
        sta     cases_left
        jnz     stage_case_loop
        ret

receive_case:
        xra     a
        sta     rx_count
        sta     rx_mismatch
        sta     rx_errors
        sta     rx_discarded
        sta     rx_checksum_ok
        sta     rx_protocol
        sta     rx_xor
        sta     rx_final_status
        mvi     a,0ffh
        sta     rx_first_index
        sta     rx_first_expected
        sta     rx_first_actual

        ; Search for A5 rather than assuming stream alignment. Preamble bytes,
        ; a stale USB packet, or one corrupt byte cannot poison the next case.
receive_sync:
        call    rx_timeout
        jc      receive_timeout
        cpi     0a5h
        jz      receive_case_id
        lda     rx_discarded
        inr     a
        sta     rx_discarded
        jmp     receive_sync
receive_case_id:
        sta     rx_xor
        call    rx_timeout
        jc      receive_timeout
        mov     c,a
        lda     rx_xor
        xra     c
        sta     rx_xor
        lda     current_case
        cmp     c
        jnz     receive_bad_case
        call    rx_timeout
        jc      receive_timeout
        mov     c,a
        lda     rx_xor
        xra     c
        sta     rx_xor
        lda     case_length
        cmp     c
        jnz     receive_bad_length

        lda     case_length
        mov     d,a
        mvi     e,0
        mvi     a,0a5h
        sta     prbs_state
receive_payload:
        call    rx_timeout
        jc      receive_timeout
        mov     c,a
        lda     rx_xor
        xra     c
        sta     rx_xor
        push    b
        push    d
        call    expected_byte
        pop     d
        pop     b
        cmp     c
        jz      receive_match
        push    psw
        lda     rx_mismatch
        inr     a
        sta     rx_mismatch
        lda     rx_first_index
        cpi     0ffh
        jnz     receive_later_mismatch
        mov     a,e
        sta     rx_first_index
        pop     psw
        sta     rx_first_expected
        mov     a,c
        sta     rx_first_actual
        jmp     receive_match
receive_later_mismatch:
        pop     psw
receive_match:
        lda     rx_count
        inr     a
        sta     rx_count
        inr     e
        dcr     d
        jnz     receive_payload

        call    rx_timeout
        jc      receive_timeout
        mov     c,a
        lda     rx_xor
        cmp     c
        jnz     receive_done
        mvi     a,1
        sta     rx_checksum_ok
        jmp     receive_done
receive_timeout:
        mvi     a,1
        sta     rx_protocol
        jmp     receive_done
receive_bad_case:
        mvi     a,2
        sta     rx_protocol
        jmp     receive_done
receive_bad_length:
        mvi     a,3
        sta     rx_protocol
receive_done:
        in      USARTCTL
        sta     rx_final_status
        ani     038h
        mov     c,a
        lda     rx_errors
        ora     c
        sta     rx_errors
        ret

; E=index, return the expected pattern byte in A.
expected_byte:
        lda     case_pattern
        ora     a
        jz      expected_inc
        dcr     a
        jz      expected_zero
        dcr     a
        jz      expected_ff
        dcr     a
        jz      expected_55
        dcr     a
        jz      expected_aa
        dcr     a
        jz      expected_dec
        dcr     a
        jz      expected_walk1
        dcr     a
        jz      expected_walk0
        ; Deterministic right-shift PRBS, seed A5, feedback B8.
        lda     prbs_state
        mov     c,a
        ani     1
        mov     a,c
        rar
        jnc     expected_prbs_store
        xri     0b8h
expected_prbs_store:
        sta     prbs_state
        mov     a,c
        ret
expected_inc:
        mov     a,e
        ret
expected_zero:
        xra     a
        ret
expected_ff:
        mvi     a,0ffh
        ret
expected_55:
        mvi     a,055h
        ret
expected_aa:
        mvi     a,0aah
        ret
expected_dec:
        mov     a,e
        cma
        ret
expected_walk1:
        mov     a,e
        ani     7
        mov     c,a
        mvi     a,1
expected_shift1:
        dcr     c
        rm
        rlc
        jmp     expected_shift1
expected_walk0:
        call    expected_walk1
        cma
        ret

; Checksummed target frames use D5 3A and include their XOR as the final byte.
frame_begin:
        xra     a
        sta     tx_xor
        mvi     a,0d5h
        call    tx_frame_byte
        mvi     a,03ah
        jmp     tx_frame_byte
tx_frame_byte:
        mov     c,a
        lda     tx_xor
        xra     c
        sta     tx_xor
        mov     a,c
        jmp     tx
frame_end:
        lda     tx_xor
        jmp     tx

send_ready_frame:
        call    frame_begin
        mvi     a,'C'
        call    tx_frame_byte
        lda     current_stage
        call    tx_frame_byte
        lda     current_case
        call    tx_frame_byte
        lda     case_length
        call    tx_frame_byte
        lda     case_pattern
        call    tx_frame_byte
        lda     case_idle
        call    tx_frame_byte
        lda     case_preamble
        call    tx_frame_byte
        lda     case_chunk
        call    tx_frame_byte
        lda     case_gap
        call    tx_frame_byte
        lda     case_repeat
        call    tx_frame_byte
        jmp     frame_end

send_report_frame:
        call    frame_begin
        mvi     a,'R'
        call    tx_frame_byte
        lda     current_stage
        call    tx_frame_byte
        lda     current_case
        call    tx_frame_byte
        lda     case_length
        call    tx_frame_byte
        lda     rx_count
        call    tx_frame_byte
        lda     rx_mismatch
        call    tx_frame_byte
        lda     rx_first_index
        call    tx_frame_byte
        lda     rx_first_expected
        call    tx_frame_byte
        lda     rx_first_actual
        call    tx_frame_byte
        lda     rx_discarded
        call    tx_frame_byte
        lda     rx_errors
        call    tx_frame_byte
        lda     rx_final_status
        call    tx_frame_byte
        lda     rx_checksum_ok
        call    tx_frame_byte
        lda     rx_protocol
        call    tx_frame_byte
        jmp     frame_end

send_end_frame:
        call    frame_begin
        mvi     a,'E'
        call    tx_frame_byte
        lda     current_stage
        call    tx_frame_byte
        lda     next_stage
        call    tx_frame_byte
        jmp     frame_end

rx_timeout:
        push    d
        lxi     b,04000h
rx_wait:
        in      USARTCTL
        mov     e,a
        ani     038h
        mov     d,a
        lda     rx_errors
        ora     d
        sta     rx_errors
        mov     a,e
        sta     rx_final_status
        ani     2
        jnz     rx_ready
        dcx     b
        mov     a,b
        ora     c
        jnz     rx_wait
        pop     d
        stc
        ret
rx_ready:
        in      USARTDATA
        pop     d
        stc
        cmc
        ret

init_stock:
        mvi     a,01fh
        out     PITCTL
        mvi     a,8
        out     PITCOUNT0
        mvi     a,05eh
        sta     current_mode
init_current:
        xra     a
        out     USARTCTL
        call    control_gap
        out     USARTCTL
        call    control_gap
        out     USARTCTL
        call    control_gap
        mvi     a,040h
        out     USARTCTL
        call    control_gap
        lda     current_mode
        out     USARTCTL
        call    control_gap
        mvi     a,034h
        out     USARTCTL
        call    control_gap
        in      USARTDATA
        ret
control_gap:
        ret

tx_enable:
        mvi     a,035h
        out     USARTCTL
        ret
tx_disable:
        mvi     a,034h
        out     USARTCTL
        ret

tx:
        push    b
        push    d
        mov     e,a
        lxi     b,04000h
tx_wait:
        in      USARTCTL
        ani     1
        jnz     tx_ready
        dcx     b
        mov     a,b
        ora     c
        jnz     tx_wait
        pop     d
        pop     b               ; CTS/TxRDY loss cannot strand restoration
        ret
tx_ready:
        mov     a,e
        out     USARTDATA
        pop     d
        pop     b
        ret
send_block:
        mov     a,m
        call    tx
        inx     h
        dcr     d
        jnz     send_block
        ret
tx_drain:
        lxi     b,1200
tx_drain_loop:
        dcx     b
        mov     a,b
        ora     c
        jnz     tx_drain_loop
        ret
switch_wait:
        lxi     b,30000
switch_wait_loop:
        dcx     b
        mov     a,b
        ora     c
        jnz     switch_wait_loop
        ret

start_marker:   db      'B2S!'
done_marker:    db      'B2D!'

; Descriptor: length, pattern, idle-code, preamble-code, chunk, gap-ms, repeat.
stage0_cases:
        db 1,PAT_INC,0,0,0,0,0
        db 2,PAT_INC,0,0,0,0,0
        db 4,PAT_INC,0,0,0,0,0
        db 8,PAT_INC,0,0,0,0,0
        db 16,PAT_INC,0,0,0,0,0
        db 32,PAT_INC,0,0,0,0,0
        db 64,PAT_INC,0,0,0,0,0
        db 133,PAT_INC,0,0,0,0,0
        db 64,PAT_ZERO,0,0,0,0,0
        db 64,PAT_FF,0,0,0,0,0
        db 64,PAT_55,0,0,0,0,0
        db 64,PAT_AA,0,0,0,0,0
        db 64,PAT_DEC,0,0,0,0,0
        db 64,PAT_WALK1,0,0,0,0,0
        db 64,PAT_WALK0,0,0,0,0,0
        db 64,PAT_PRBS,0,0,0,0,0
        db 64,PAT_PRBS,0,0,0,0,1
        db 64,PAT_PRBS,0,0,0,0,2
        db 64,PAT_PRBS,0,0,0,0,3
        db 64,PAT_PRBS,0,0,0,0,4
        db 64,PAT_PRBS,0,0,0,0,5
        db 64,PAT_PRBS,0,0,0,0,6
        db 64,PAT_PRBS,0,0,0,0,7
        db 64,PAT_PRBS,0,0,0,0,8
        db 64,PAT_PRBS,0,0,0,0,9
        ; Exact prefix boundary: every length from 1 through 20 is exercised;
        ; 1,2,4,8,16 repeat the baseline intentionally for statistics.
        db 1,PAT_INC,0,0,0,0,10
        db 2,PAT_INC,0,0,0,0,10
        db 3,PAT_INC,0,0,0,0,10
        db 4,PAT_INC,0,0,0,0,10
        db 5,PAT_INC,0,0,0,0,10
        db 6,PAT_INC,0,0,0,0,10
        db 7,PAT_INC,0,0,0,0,10
        db 8,PAT_INC,0,0,0,0,10
        db 9,PAT_INC,0,0,0,0,10
        db 10,PAT_INC,0,0,0,0,10
        db 11,PAT_INC,0,0,0,0,10
        db 12,PAT_INC,0,0,0,0,10
        db 13,PAT_INC,0,0,0,0,10
        db 14,PAT_INC,0,0,0,0,10
        db 15,PAT_INC,0,0,0,0,10
        db 16,PAT_INC,0,0,0,0,10
        db 17,PAT_INC,0,0,0,0,10
        db 18,PAT_INC,0,0,0,0,10
        db 19,PAT_INC,0,0,0,0,10
        db 20,PAT_INC,0,0,0,0,10
        db 64,PAT_INC,1,0,0,0,0
        db 64,PAT_INC,2,0,0,0,0
        db 64,PAT_INC,3,0,0,0,0
        db 64,PAT_INC,4,0,0,0,0
        db 64,PAT_INC,5,0,0,0,0
        db 64,PAT_INC,0,1,0,0,0
        db 64,PAT_INC,0,2,0,0,0
        db 64,PAT_INC,0,3,0,0,0
        db 64,PAT_INC,0,4,0,0,0
        db 133,PAT_INC,0,0,8,1,0
        db 133,PAT_INC,0,0,16,1,0
        db 133,PAT_INC,0,0,32,1,0
        ; One byte per 100 ms. CPU overrun and inter-character settling are
        ; impossible explanations if this still loses a 20-byte frame.
        db 20,PAT_INC,0,0,1,100,0
        ; Host-only flag: send two stop bits. D11 remains in its ordinary
        ; one-stop receive mode, which accepts the longer mark interval.
        db 64,PAT_55,0,0,0,0,128
STAGE0_COUNT    equ     ($-stage0_cases)/7

stage1_cases:
        db 16,PAT_INC,0,0,0,0,0
        db 64,PAT_55,0,0,0,0,0
        db 133,PAT_PRBS,0,0,0,0,0
STAGE1_COUNT    equ     ($-stage1_cases)/7

stage2_cases:
        db 1,PAT_INC,0,0,0,0,0
        db 16,PAT_INC,0,0,0,0,0
        db 64,PAT_55,0,0,0,0,0
        db 64,PAT_PRBS,0,0,0,0,0
        db 133,PAT_INC,0,0,0,0,0
        db 133,PAT_PRBS,0,0,0,0,0
STAGE2_COUNT    equ     ($-stage2_cases)/7

current_stage: db 0
next_stage:    db 0
current_case:  db 0
current_mode:  db 05eh
cases_left:    db 0
case_ptr:      dw 0
case_length:   db 0
case_pattern:  db 0
case_idle:     db 0
case_preamble: db 0
case_chunk:    db 0
case_gap:      db 0
case_repeat:   db 0
rx_count:      db 0
rx_mismatch:   db 0
rx_first_index: db 0
rx_first_expected: db 0
rx_first_actual: db 0
rx_errors:     db 0
rx_discarded:  db 0
rx_checksum_ok: db 0
rx_protocol:   db 0
rx_final_status: db 0
rx_xor:        db 0
tx_xor:        db 0
prbs_state:    db 0

        end     start
