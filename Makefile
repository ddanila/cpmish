export ACKCFLAGS = -O3
export OBJ = .obj

.PHONY: all
all: +all

.PHONY: juku-cosim-check
juku-cosim-check: juku.img
	python3 arch/juku/cosim_check.py

.PHONY: juku-net-cosim-check
juku-net-cosim-check: juku-net-system.bin juku-net-smoke-system.bin \
		juku-net-baudtest-system.bin juku-net-smoke.img \
		juku-net-baudtest-9600.img juku-net-baudtest-8n1.img \
		juku-net-baudtest-ladder.img juku-net-baudtest2-system.bin \
		juku-net-baudtest2.img juku.img
	python3 arch/juku/net_cosim_check.py

TARGETS = +all
include build/ab.mk
