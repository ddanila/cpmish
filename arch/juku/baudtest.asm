; Recoverable live CP/M test of the Juku USART at a selected rate.
; Loaded from the working 9,600-baud network disk; no ROM or reset required.
;
; The host sends eleven independently framed cases. Every case starts from a
; freshly reset 8251 and has a bounded inter-byte timeout, so an overrun or a
; truncated burst produces an eight-byte report instead of wedging the test.

USARTDATA       equ     008h
USARTCTL        equ     009h
PITCOUNT0       equ     018h
.ifdef TEST9600
TEST_DIVISOR    equ     8
.else
TEST_DIVISOR    equ     4
.endif
.ifdef TESTLADDER
RATE_COUNT      equ     3
.endif
CASE_COUNT      equ     11

        org     0100h

start:
        di
        xra     a
        sta     current_case
        sta     ack_ok
.ifdef TESTLADDER
        sta     rate_index
.endif

        ; Finish the 9600-baud disk session before either endpoint changes.
        mvi     a,035h
        out     USARTCTL
        lxi     h,marker_9600
        mvi     d,4
        call    send_block
        call    tx_drain
        mvi     a,034h
        out     USARTCTL

        ; Give the host ample time to recognize B96! and change its tty rate.
        lxi     b,20000
host_switch_wait:
        dcx     b
        mov     a,b
        ora     c
        jnz     host_switch_wait
        call    init_test_rate

announce_ready:
        ; A byte-exact marker proves the Juku-to-host direction at this rate.
        mvi     a,035h
        out     USARTCTL
        lxi     h,marker_ready
        mvi     d,4
        call    send_block
        call    tx_drain
        mvi     a,034h
        out     USARTCTL

case_loop:
        ; Reset between cases.  This clears a buffered tail byte and all error
        ; latches after a failed burst, making every following case independent.
        call    init_test_rate
        mvi     a,035h
        out     USARTCTL
        mvi     a,'C'
        call    tx
        lda     current_case
        call    tx
        call    tx_drain
        mvi     a,034h
        out     USARTCTL

        xra     a
        sta     rx_expected
        sta     rx_count
        sta     rx_mismatch
        sta     rx_errors
        sta     rx_checksum_ok
        sta     rx_protocol
        sta     rx_xor

        ; Frame: A5, case, length, incrementing payload, whole-frame XOR.
        call    rx_timeout
        jc      receive_timeout
        cpi     0a5h
        jnz     receive_bad_sync
        sta     rx_xor

        call    rx_timeout
        jc      receive_timeout
        mov     c,a
        lda     current_case
        cmp     c
        jnz     receive_bad_case
        lda     rx_xor
        xra     c
        sta     rx_xor

        call    rx_timeout
        jc      receive_timeout
        ora     a
        jz      receive_bad_length
        sta     rx_expected
        mov     d,a
        mov     c,a
        lda     rx_xor
        xra     c
        sta     rx_xor
        mvi     e,0

receive_payload:
        call    rx_timeout
        jc      receive_timeout
        mov     c,a
        lda     rx_count
        inr     a
        sta     rx_count
        mov     a,c
        cmp     e
        jz      receive_match
        lda     rx_mismatch
        inr     a
        sta     rx_mismatch
receive_match:
        lda     rx_xor
        xra     c
        sta     rx_xor
        inr     e
        dcr     d
        jnz     receive_payload

        call    rx_timeout
        jc      receive_timeout
        mov     c,a
        lda     rx_xor
        cmp     c
        jnz     receive_report
        mvi     a,1
        sta     rx_checksum_ok
        jmp     receive_report

receive_timeout:
        mvi     a,1
        sta     rx_protocol
        jmp     receive_report
receive_bad_length:
        mvi     a,2
        sta     rx_protocol
        jmp     receive_report
receive_bad_case:
        mvi     a,3
        sta     rx_protocol
        jmp     receive_report
receive_bad_sync:
        mvi     a,4
        sta     rx_protocol

receive_report:
        ; Fixed report: 'R', case, expected, count, mismatches, 8251 errors,
        ; checksum-good, protocol status.  It is sent even after a timeout.
        mvi     a,035h
        out     USARTCTL
        mvi     a,'R'
        call    tx
        lda     current_case
        call    tx
        lda     rx_expected
        call    tx
        lda     rx_count
        call    tx
        lda     rx_mismatch
        call    tx
        lda     rx_errors
        call    tx
        lda     rx_checksum_ok
        call    tx
        lda     rx_protocol
        call    tx
        call    tx_drain
        mvi     a,034h
        out     USARTCTL

        ; The ACK also guarantees that the host has stopped transmitting before
        ; the receiver is reset for the next independent case.
        call    rx_timeout
        jc      case_advance
        cpi     0ach
        jnz     case_advance
        mvi     a,1
        sta     ack_ok
case_advance:
        lda     current_case
        inr     a
        sta     current_case
        cpi     CASE_COUNT
        jnz     case_loop

        ; Finish with one continuous 133-byte Juku-to-host frame.
        mvi     a,035h
        out     USARTCTL
        mvi     a,'J'
        call    tx
        mvi     a,085h
        call    tx
        mvi     a,'J'
        xri     085h
        sta     tx_xor
        mvi     d,133
        mvi     e,0
send_payload:
        mov     a,e
        mov     c,a
        lda     tx_xor
        xra     c
        sta     tx_xor
        mov     a,c
        call    tx
        inr     e
        dcr     d
        jnz     send_payload
        lda     tx_xor
        call    tx
        call    tx_drain
        mvi     a,034h
        out     USARTCTL

        xra     a
        sta     ack_ok
        call    rx_timeout
        jc      final_done
        cpi     0ach
        jnz     final_done
        mvi     a,1
        sta     ack_ok
final_done:
        mvi     a,035h
        out     USARTCTL
        mvi     a,'D'
        call    tx
        lda     ack_ok
        call    tx
        mvi     a,'!'
        call    tx
        call    tx_drain
        mvi     a,034h
        out     USARTCTL

.ifdef TESTLADDER
        lda     rate_index
        inr     a
        sta     rate_index
        cpi     RATE_COUNT
        jz      ladder_done
        xra     a
        sta     current_case
        sta     ack_ok
        ; The host receives D/ack/! at the old rate and switches immediately.
        ; This delay covers its termios2 update before the next-rate marker.
        lxi     b,20000
ladder_switch_wait:
        dcx     b
        mov     a,b
        ora     c
        jnz     ladder_switch_wait
        call    init_test_rate
        jmp     announce_ready
ladder_done:
.endif
        call    init_9600
        ret

send_block:
        mov     a,m
        call    tx
        inx     h
        dcr     d
        jnz     send_block
        ret

tx:
        mov     c,a
tx_wait:
        in      USARTCTL
        ani     1
        jz      tx_wait
        mov     a,c
        out     USARTDATA
        ret

tx_drain:
        lxi     b,1000          ; > one complete character at either rate
tx_drain_loop:
        dcx     b
        mov     a,b
        ora     c
        jnz     tx_drain_loop
        ret

rx_timeout:
        push    d
        lxi     b,02000h        ; bounded recovery after a truncated burst
rx_wait:
        in      USARTCTL
        mov     e,a
        ani     038h
        mov     d,a
        lda     rx_errors
        ora     d
        sta     rx_errors
        mov     a,e
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
        ; Do not rewrite command/ER after every clean byte. At 19,200 the next
        ; character has already started on a continuous stream; touching the
        ; real KR580VV51A control register in that window is unnecessary and
        ; was the only target action correlated with the physical receiver
        ; becoming silent until the next reset. Error flags stay latched for
        ; the report and the next case performs a complete 8251 reset.
        pop     d
        stc
        cmc
        ret

init_test_rate:
.ifdef TESTLADDER
        lda     rate_index
        mov     e,a
        mvi     d,0
        lxi     h,rate_divisors
        dad     d
        mov     a,m
.else
        mvi     a,TEST_DIVISOR
.endif
        out     PITCOUNT0
.ifdef TESTLADDER
        mvi     b,05dh          ; x1, 8 data, odd parity, one stop
.else
.ifdef TEST8N1
        mvi     b,04eh          ; x16, 8 data, no parity, one stop
.else
        mvi     b,05eh          ; x16, 8 data, odd parity, one stop
.endif
.endif
        jmp     init_usart
init_9600:
        mvi     a,8
        out     PITCOUNT0
        mvi     b,05eh          ; stock return is always 9600/8O1
init_usart:
        ; EktaSoft boot leaves D57 counter 0 in LSB-only BCD mode 3.  Its own
        ; NetBios changes rate with this same single count write.
        xra     a
        out     USARTCTL
        call    usart_control_gap
        out     USARTCTL
        call    usart_control_gap
        out     USARTCTL
        call    usart_control_gap
        mvi     a,040h
        out     USARTCTL
        call    usart_control_gap
        mov     a,b
        out     USARTCTL
        call    usart_control_gap
        mvi     a,034h
        out     USARTCTL
        call    usart_control_gap
        in      USARTDATA
        ret

usart_control_gap:
        ; Match EktaSoft 3.7 NET_USART_INIT exactly: every D11 control write
        ; at 34DCh..3500h is followed by CALL F522h, whose body is RET. The
        ; otherwise empty call provides 27 8080 cycles of recovery time. This
        ; matters as an A/B test because both physical boards failed after our
        ; formerly back-to-back clone reset/mode/command sequence.
        ret

marker_9600:
        db      'B96!'
marker_ready:
        db      'BRD!'
current_case:
        db      0
rx_expected:
        db      0
rx_count:
        db      0
rx_mismatch:
        db      0
rx_errors:
        db      0
rx_checksum_ok:
        db      0
rx_protocol:
        db      0
rx_xor:
        db      0
tx_xor:
        db      0
ack_ok:
        db      0
.ifdef TESTLADDER
rate_index:
        db      0
rate_divisors:
        ; D57 remains in the stock LSB-only BCD mode. These values select
        ; effective divisors 85, 77, and 64; the 8251 x1 mode makes the
        ; resulting line rates approximately 14,480, 15,984, and 19,231.
        db      085h,077h,064h
.endif

        end     start
