export ACKCFLAGS = -O3
export OBJ = .obj

.PHONY: all
all: +all

.PHONY: juku-cosim-check
juku-cosim-check: juku.img
	python3 arch/juku/cosim_check.py

TARGETS = +all
include build/ab.mk
