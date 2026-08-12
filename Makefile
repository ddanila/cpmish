export ACKCFLAGS = -O3
export OBJ = .obj

.PHONY: all
all: +all

.PHONY: juku-cosim-check
juku-cosim-check: juku.img
	python3 arch/juku/cosim_check.py

.PHONY: juku-net-cosim-check
juku-net-cosim-check: juku-net-system.bin juku.img
	python3 arch/juku/net_cosim_check.py

TARGETS = +all
include build/ab.mk
