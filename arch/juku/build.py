from build.ab import simplerule
from build.cpm import diskimage
from third_party.ld80.build import ld80
from third_party.zmac.build import zmac
from utils.build import unix2cpm


CBASE = 0xB400
FBASE = 0xBC00
BBASE = 0xCA00
zmac(
    name="bios",
    src="./bios.asm",
    deps=["include/cpm.lib"],
)
zmac(
    name="bios-net",
    src="./bios-net.asm",
    deps=["include/cpm.lib", "./bios.asm"],
)
zmac(
    name="bios-net-mode2",
    src="./bios-net-mode2.asm",
    deps=["include/cpm.lib", "./bios.asm"],
)
zmac(
    name="diag",
    src="./diag.asm",
    deps=["third_party/juku-common/diag/memory.asm"],
    relocatable=False,
)
zmac(
    name="smoke",
    src="./smoke.asm",
    deps=[
        "third_party/juku-common/music/smoke-player.asm",
        "third_party/juku-common/music/smoke-table.asm",
    ],
    relocatable=False,
)
zmac(
    name="baudtest",
    src="./baudtest.asm",
    relocatable=False,
)
zmac(
    name="baudtest-9600",
    src="./baudtest.asm",
    defines=["TEST9600"],
    relocatable=False,
)
zmac(
    name="baudtest-8n1",
    src="./baudtest.asm",
    defines=["TEST8N1"],
    relocatable=False,
)
zmac(
    name="baudtest-ladder",
    src="./baudtest.asm",
    defines=["TESTLADDER"],
    relocatable=False,
)
zmac(
    name="baudtest2",
    src="./baudtest2.asm",
    relocatable=False,
)
zmac(
    name="mode2-soak",
    src="./mode2-soak.asm",
    deps=[
        "third_party/juku-common/music/smoke-player.asm",
        "third_party/juku-common/music/smoke-table.asm",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-stage1",
    src="./fastboot-stage1.asm",
    relocatable=False,
)
zmac(
    name="fastboot-v2",
    src="./fastboot-stage1.asm",
    defines=["FASTBOOT_V2"],
    relocatable=False,
)
zmac(
    name="fastboot-v3-core",
    src="./fastboot-v3-core.asm",
    relocatable=False,
)
zmac(
    name="fastboot-v3-extension",
    src="./fastboot-v3-extension.asm",
    relocatable=False,
)
zmac(
    name="fastboot-v5-core",
    src="./fastboot-v3-core.asm",
    defines=["FASTBOOT_8N1"],
    relocatable=False,
)
zmac(
    name="fastboot-v5-extension",
    src="./fastboot-v3-extension.asm",
    defines=["FASTBOOT_8N1"],
    relocatable=False,
)
zmac(
    name="fastboot-v4-core",
    src="./fastboot-v4-core.asm",
    relocatable=False,
)
zmac(
    name="fastboot-v4-extension",
    src="./fastboot-v4-extension.asm",
    relocatable=False,
)

simplerule(
    name="fastboot-stage1-bin",
    ins=[".+fastboot-stage1"],
    outs=["=juku-fastboot-stage1.bin"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUFASTBOOTSTAGE1",
)
simplerule(
    name="fastboot-v2-bin",
    ins=[".+fastboot-v2"],
    outs=["=juku-fastboot-v2.bin"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUFASTBOOTV2",
)
simplerule(
    name="fastboot-v3-bin",
    ins=[".+fastboot-v3-core", ".+fastboot-v3-extension"],
    outs=["=juku-fastboot-v3.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v3.py {ins[0]} {ins[1]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV3",
)
simplerule(
    name="fastboot-v4-bin",
    ins=[".+fastboot-v4-core", ".+fastboot-v4-extension"],
    outs=["=juku-fastboot-v4.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v4.py {ins[0]} {ins[1]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV4",
)
simplerule(
    name="fastboot-v5-bin",
    ins=[".+fastboot-v5-core", ".+fastboot-v5-extension"],
    outs=["=juku-fastboot-v5.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v5.py {ins[0]} {ins[1]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV5",
)

# The established 52K EKDOS layout: CCP=B400, BDOS base=BC00 (entry BC06),
# BIOS=CA00. The final 1 KiB is the initialized BIOS budget; scratch storage
# above it exists in RAM but does not have to be loaded from the system track.
ld80(
    name="memory",
    address=CBASE,
    objs={
        CBASE: ["third_party/dr/ccp+ccp-juku"],
        FBASE: ["third_party/dr/bdos"],
        BBASE: [".+bios"],
    },
)
ld80(
    name="memory-net",
    address=CBASE,
    objs={
        CBASE: ["third_party/dr/ccp+ccp-juku"],
        FBASE: ["third_party/dr/bdos"],
        BBASE: [".+bios-net"],
    },
)
ld80(
    name="memory-net-mode2",
    address=CBASE,
    objs={
        CBASE: ["third_party/dr/ccp+ccp-juku"],
        FBASE: ["third_party/dr/bdos"],
        BBASE: [".+bios-net-mode2"],
    },
)

# Juku's preserved SYSGEN files reserve 512 bytes before the 52 resident
# 128-byte records. Keep the complete 10 KiB boot-track region so the result
# works both with physical disk images and the Janet network wrapper.
simplerule(
    name="systemfile",
    ins=[".+memory"],
    outs=["=juku-system.bin"],
    commands=[
        "python3 arch/juku/mksystem.py {ins[0]} {outs[0]}",
    ],
    label="JUKUSYSTEM",
)
simplerule(
    name="systemfile-net",
    ins=[".+memory-net"],
    outs=["=juku-net-system.bin"],
    commands=[
        "python3 arch/juku/mksystem.py {ins[0]} {outs[0]}",
    ],
    label="JUKUNETSYSTEM",
)
simplerule(
    name="systemfile-net-mode2",
    ins=[".+memory-net-mode2"],
    outs=["=juku-net-mode2-system.bin"],
    commands=[
        "python3 arch/juku/mksystem.py {ins[0]} {outs[0]}",
    ],
    label="JUKUNETMODE2SYSTEM",
)
simplerule(
    name="systemfile-net-smoke",
    ins=[".+memory-net"],
    outs=["=juku-net-smoke-system.bin"],
    commands=[
        "python3 arch/juku/mksystem.py {ins[0]} {outs[0]} SMOKE",
    ],
    label="JUKUNETSMOKESYSTEM",
)
simplerule(
    name="systemfile-net-baudtest",
    ins=[".+memory-net"],
    outs=["=juku-net-baudtest-system.bin"],
    commands=[
        "python3 arch/juku/mksystem.py {ins[0]} {outs[0]} BAUDTEST",
    ],
    label="JUKUNETBAUDTESTSYSTEM",
)
simplerule(
    name="systemfile-net-baudtest2",
    ins=[".+memory-net"],
    outs=["=juku-net-baudtest2-system.bin"],
    commands=[
        "python3 arch/juku/mksystem.py {ins[0]} {outs[0]} BAUDTST2",
    ],
    label="JUKUNETBAUDTEST2SYSTEM",
)
simplerule(
    name="systemfile-net-mode2-soak",
    ins=[".+memory-net-mode2"],
    outs=["=juku-net-mode2-soak-system.bin"],
    commands=[
        "python3 arch/juku/mksystem.py {ins[0]} {outs[0]} M2SOAK",
    ],
    label="JUKUNETMODE2SOAKSYSTEM",
)

readme = unix2cpm(name="readme", src="README.md")

flatdiskimage = diskimage(
    name="flatdiskimage",
    format="juku386",
    bootfile=".+systemfile",
    size=409600,
    map={
        "readme.txt": readme,
        "asm.com": "cpmtools+asm",
        "copy.com": "cpmtools+copy",
        "dump.com": "cpmtools+dump",
        "diag.com": ".+diag",
        "stat.com": "cpmtools+stat",
        "submit.com": "cpmtools+submit",
    },
)

net_mode2_diskimage = diskimage(
    name="net-mode2-diskimage",
    format="juku386",
    bootfile=".+systemfile-net-mode2",
    size=409600,
    map={
        "readme.txt": readme,
        "asm.com": "cpmtools+asm",
        "copy.com": "cpmtools+copy",
        "dump.com": "cpmtools+dump",
        "diag.com": ".+diag",
        "stat.com": "cpmtools+stat",
        "submit.com": "cpmtools+submit",
    },
)

net_smoke_diskimage = diskimage(
    name="net-smoke-diskimage",
    format="juku386",
    bootfile=".+systemfile-net-smoke",
    size=409600,
    map={
        "baudtest.com": ".+baudtest",
        "smoke.com": ".+smoke",
    },
)
net_baudtest_9600_diskimage = diskimage(
    name="net-baudtest-9600-diskimage",
    format="juku386",
    bootfile=".+systemfile-net-baudtest",
    size=409600,
    map={
        "baudtest.com": ".+baudtest-9600",
    },
)
net_baudtest_8n1_diskimage = diskimage(
    name="net-baudtest-8n1-diskimage",
    format="juku386",
    bootfile=".+systemfile-net-baudtest",
    size=409600,
    map={
        "baudtest.com": ".+baudtest-8n1",
    },
)
net_baudtest_ladder_diskimage = diskimage(
    name="net-baudtest-ladder-diskimage",
    format="juku386",
    bootfile=".+systemfile-net-baudtest",
    size=409600,
    map={
        "baudtest.com": ".+baudtest-ladder",
    },
)
net_baudtest2_diskimage = diskimage(
    name="net-baudtest2-diskimage",
    format="juku386",
    bootfile=".+systemfile-net-baudtest2",
    size=409600,
    map={
        "baudtst2.com": ".+baudtest2",
    },
)
net_mode2_soak_diskimage = diskimage(
    name="net-mode2-soak-diskimage",
    format="juku386",
    bootfile=".+systemfile-net-mode2-soak",
    size=409600,
    map={
        "m2soak.com": ".+mode2-soak",
    },
)
simplerule(
    name="net-baudtest-9600-volume",
    ins=[net_baudtest_9600_diskimage],
    outs=["=juku-net-baudtest-9600.img"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUNETBAUDTEST9600VOLUME",
)
simplerule(
    name="net-baudtest-8n1-volume",
    ins=[net_baudtest_8n1_diskimage],
    outs=["=juku-net-baudtest-8n1.img"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUNETBAUDTEST8N1VOLUME",
)
simplerule(
    name="net-baudtest-ladder-volume",
    ins=[net_baudtest_ladder_diskimage],
    outs=["=juku-net-baudtest-ladder.img"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUNETBAUDTESTLADDERVOLUME",
)
simplerule(
    name="net-baudtest2-volume",
    ins=[net_baudtest2_diskimage],
    outs=["=juku-net-baudtest2.img"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUNETBAUDTEST2VOLUME",
)
simplerule(
    name="net-mode2-volume",
    ins=[net_mode2_diskimage],
    outs=["=juku-net-mode2.img"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUNETMODE2VOLUME",
)
simplerule(
    name="net-mode2-soak-volume",
    ins=[net_mode2_soak_diskimage],
    outs=["=juku-net-mode2-soak.img"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUNETMODE2SOAKVOLUME",
)
simplerule(
    name="net-smoke-volume",
    ins=[net_smoke_diskimage],
    outs=["=juku-net-smoke.img"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUNETSMOKEVOLUME",
)

# Raw Juku captures are cylinder/head interleaved. The bootable 386K CP/M
# volume is side 0; keep side 1 erased for a future independent volume.
simplerule(
    name="diskimage",
    ins=[".+systemfile", flatdiskimage],
    deps=["./mksides.py", "./check.py"],
    outs=["=juku.img"],
    commands=[
        "python3 arch/juku/mksides.py {ins[1]} {outs[0]}",
        "python3 arch/juku/check.py {ins[0]} {ins[1]} {outs[0]}",
    ],
    label="JUKUDISK",
)
