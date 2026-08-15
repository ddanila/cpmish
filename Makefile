export ACKCFLAGS = -O3
export OBJ = .obj

.PHONY: all
all: +all

.PHONY: juku-cosim-check
juku-cosim-check: juku.img
	python3 arch/juku/cosim_check.py

.PHONY: juku-net-cosim-check
juku-net-cosim-check: juku-net-system.bin juku-net-smoke-system.bin \
		juku-net-mode2-broken-system.bin \
		juku-net-mode2-system.bin juku-net-mode2.img \
		juku-net-baudtest-system.bin juku-net-smoke.img \
		juku-net-baudtest-9600.img juku-net-baudtest-8n1.img \
		juku-net-baudtest-ladder.img juku-net-baudtest2-system.bin \
		juku-net-baudtest2.img juku-net-mode2-soak-system.bin \
		juku-net-mode2-soak.img juku-fastboot-stage1.bin \
		juku-fastboot-v2.bin juku-fastboot-v3.bin juku-fastboot-v4.bin \
		juku-fastboot-v5.bin juku-fastboot-v6.bin juku-fastboot-v7.bin \
		juku-fastboot-v8.bin juku-fastboot-v9.bin juku-fastboot-v10.bin \
		juku-fastboot-v11.bin juku-fastboot-v12.bin juku-fastboot-v13.bin \
		juku-fastboot-v14.bin juku-fastboot-v14-netdisk-v2.bin \
		juku-fastboot-v15-rambio.bin \
		juku-net-v2-system.bin juku-net-v2-ramout-system.bin \
		juku-net-v2-rambio-system.bin \
		juku-net-v2.img juku.img
	python3 arch/juku/net_cosim_check.py

.PHONY: juku-fastboot-cosim-check
juku-fastboot-cosim-check: juku-fastboot-stage1.bin juku-fastboot-v2.bin \
		juku-fastboot-v3.bin juku-fastboot-v4.bin \
		juku-fastboot-v5.bin juku-fastboot-v6.bin juku-fastboot-v7.bin \
		juku-fastboot-v8.bin juku-fastboot-v9.bin juku-fastboot-v10.bin \
		juku-fastboot-v11.bin \
		juku-fastboot-v12.bin \
		juku-fastboot-v13.bin \
		juku-fastboot-v14.bin \
		juku-fastboot-v14-netdisk-v2.bin \
		juku-fastboot-v15-rambio.bin \
		juku-net-mode2-system.bin
	python3 arch/juku/net_cosim_check.py --fastboot-only

.PHONY: juku-fastboot-v15-cosim-check
juku-fastboot-v15-cosim-check: juku-fastboot-v15-rambio.bin \
		juku-net-v2-rambio-system.bin juku-net-v2.img
	python3 arch/juku/net_cosim_check.py --fastboot-v15-only

.PHONY: juku-cpm3-cosim-check
juku-cpm3-cosim-check: juku-cpm3-system.bin \
		juku-fastboot-v15-cpm3.bin juku-cpm3.img
	python3 arch/juku/cpm3_cosim_check.py

.PHONY: juku-netdisk-benchmark
juku-netdisk-benchmark: juku-fastboot-v14.bin \
		juku-fastboot-v14-netdisk-v2.bin juku-net-mode2-system.bin \
		juku-net-mode2.img juku-net-v2-system.bin juku-net-v2.img
	python3 arch/juku/net_cosim_check.py --netdisk-benchmark-only

.PHONY: juku-ram-output-cosim-check
juku-ram-output-cosim-check: juku-net-v2-ramout-system.bin juku-net-v2.img
	python3 arch/juku/net_cosim_check.py --ram-output-only

.PHONY: juku-ram-bios-cosim-check
juku-ram-bios-cosim-check: juku-net-v2-rambio-system.bin juku-net-v2.img
	python3 arch/juku/net_cosim_check.py --ram-bios-only

.PHONY: juku-netdisk-v3-cosim-check
juku-netdisk-v3-cosim-check: juku-net-v3-rambio-system.bin \
	juku-fastboot-v15-netdisk-v3.bin juku-net-v2.img
	python3 arch/juku/net_cosim_check.py --netdisk-v3-only

TARGETS = +all
include build/ab.mk
