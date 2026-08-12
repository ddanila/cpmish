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

# The established 52K EKDOS layout: CCP=B400, BDOS base=BC00 (entry BC06),
# BIOS=CA00. The final 1 KiB is the initialized BIOS budget; scratch storage
# above it exists in RAM but does not have to be loaded from the system track.
ld80(
    name="memory",
    address=CBASE,
    objs={
        CBASE: ["third_party/dr/ccp"],
        FBASE: ["third_party/dr/bdos"],
        BBASE: [".+bios"],
    },
)
ld80(
    name="memory-net",
    address=CBASE,
    objs={
        CBASE: ["third_party/dr/ccp"],
        FBASE: ["third_party/dr/bdos"],
        BBASE: [".+bios-net"],
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
        "stat.com": "cpmtools+stat",
        "submit.com": "cpmtools+submit",
    },
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
