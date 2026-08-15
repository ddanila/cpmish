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
    name="bios-net-mode2-broken",
    src="./bios-net-mode2-broken.asm",
    deps=["include/cpm.lib", "./bios.asm"],
)
zmac(
    name="bios-net-v2",
    src="./bios-net-v2.asm",
    deps=["include/cpm.lib", "./bios.asm"],
)
zmac(
    name="bios-net-v2-ramout",
    src="./bios-net-v2-ramout.asm",
    deps=[
        "include/cpm.lib", "./bios.asm", "third_party/juku-common/platform/ram-console.asm",
        "third_party/juku-common/platform/ram-console-font.asm",
    ],
)
zmac(
    name="bios-net-v2-rambio",
    src="./bios-net-v2-rambio.asm",
    deps=[
        "include/cpm.lib", "./bios.asm", "third_party/juku-common/platform/ram-console.asm",
        "third_party/juku-common/platform/ram-console-font.asm",
    ],
)
zmac(
    name="ram-keyboard",
    src="third_party/juku-common/platform/ram-keyboard.asm",
)
zmac(
    name="bios-net-v3-rambio",
    src="./bios-net-v3-rambio.asm",
    deps=[
        "include/cpm.lib", "./bios.asm", "third_party/juku-common/platform/ram-console.asm",
        "third_party/juku-common/platform/ram-console-font.asm",
    ],
)
zmac(name="netdisk-v3", src="third_party/juku-common/platform/netdisk-v3.asm")
zmac(name="netconsole", src="third_party/juku-common/platform/netconsole.asm")
zmac(
    name="diag",
    src="./diag.asm",
    deps=[
        "third_party/juku-common/diag/cpu.asm",
        "third_party/juku-common/diag/memory.asm",
        "third_party/juku-common/diag/memory-address.asm",
        "third_party/juku-common/diag/memory-retention.asm",
        "third_party/juku-common/diag/checksum.asm",
    ],
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
    name="readbench",
    src="./readbench.asm",
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
    src="third_party/juku-common/transport/fastboot-core.asm",
    relocatable=False,
)
zmac(
    name="fastboot-v3-extension",
    src="third_party/juku-common/transport/fastboot-extension.asm",
    relocatable=False,
)
zmac(
    name="fastboot-v5-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=["FASTBOOT_8N1"],
    relocatable=False,
)
zmac(
    name="fastboot-v5-extension",
    src="third_party/juku-common/transport/fastboot-extension.asm",
    defines=["FASTBOOT_8N1"],
    relocatable=False,
)
zmac(
    name="fastboot-v6-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=["FASTBOOT_8N1", "FASTBOOT_ZX0"],
    relocatable=False,
)
zmac(
    name="fastboot-v6-extension",
    src="third_party/juku-common/transport/fastboot-extension.asm",
    defines=["FASTBOOT_8N1", "FASTBOOT_ZX0"],
    relocatable=False,
)
zmac(
    name="fastboot-v7-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=["FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_TIGHT"],
    relocatable=False,
)
zmac(
    name="fastboot-v7-extension",
    src="third_party/juku-common/transport/fastboot-extension.asm",
    defines=["FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_TIGHT"],
    relocatable=False,
)
zmac(
    name="fastboot-v8-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=["FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_STREAM"],
    relocatable=False,
)
zmac(
    name="fastboot-v8-extension",
    src="./fastboot-v8-extension.asm",
    relocatable=False,
)
zmac(
    name="fastboot-v9-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=[
        "FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_STREAM", "FASTBOOT_V9",
        "FASTBOOT_EXACT",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-v9-extension",
    src="./fastboot-v8-extension.asm",
    defines=["FASTBOOT_POLL_MARKERS"],
    relocatable=False,
)
zmac(
    name="fastboot-v10-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=[
        "FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_STREAM", "FASTBOOT_V10",
        "FASTBOOT_EXACT",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-v10-extension",
    src="./fastboot-v8-extension.asm",
    defines=["FASTBOOT_POLL_MARKERS", "FASTBOOT_V10", "FASTBOOT_WAIT_INPUT"],
    relocatable=False,
)
zmac(
    name="fastboot-v11-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=[
        "FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_STREAM", "FASTBOOT_V11",
        "FASTBOOT_EXACT", "FASTBOOT_EXT_ACK",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-v11-extension",
    src="./fastboot-v8-extension.asm",
    defines=["FASTBOOT_POLL_MARKERS", "FASTBOOT_V11", "FASTBOOT_WAIT_INPUT"],
    relocatable=False,
)
zmac(
    name="fastboot-v12-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=[
        "FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_STREAM", "FASTBOOT_V12",
        "FASTBOOT_EXACT", "FASTBOOT_EXT_ACK", "FASTBOOT_PROBE_SYNC",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-v12-extension",
    src="./fastboot-v8-extension.asm",
    defines=["FASTBOOT_POLL_MARKERS", "FASTBOOT_V12", "FASTBOOT_WAIT_INPUT"],
    relocatable=False,
)
zmac(
    name="fastboot-v13-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=[
        "FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_STREAM", "FASTBOOT_V13",
        "FASTBOOT_EXACT", "FASTBOOT_EXT_ACK", "FASTBOOT_PROBE_SYNC",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-v13-extension",
    src="./fastboot-v8-extension.asm",
    defines=[
        "FASTBOOT_POLL_MARKERS", "FASTBOOT_V13", "FASTBOOT_WAIT_INPUT",
        "FASTBOOT_STREAM_ACK",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-v14-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=[
        "FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_STREAM", "FASTBOOT_V14",
        "FASTBOOT_EXACT", "FASTBOOT_EXT_ACK", "FASTBOOT_PROBE_SYNC",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-v14-extension",
    src="third_party/juku-common/transport/fastboot-extension.asm",
    defines=[
        "FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_TIGHT", "FASTBOOT_V14",
        "FASTBOOT_STREAM_ACK",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-v15-core",
    src="third_party/juku-common/transport/fastboot-core.asm",
    defines=[
        "FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_STREAM", "FASTBOOT_V15",
        "FASTBOOT_EXACT", "FASTBOOT_EXT_ACK", "FASTBOOT_PROBE_SYNC",
    ],
    relocatable=False,
)
zmac(
    name="fastboot-v15-extension",
    src="third_party/juku-common/transport/fastboot-extension.asm",
    defines=[
        "FASTBOOT_8N1", "FASTBOOT_ZX0", "FASTBOOT_TIGHT", "FASTBOOT_V15",
        "FASTBOOT_STREAM_ACK", "FASTBOOT_RAMBIOS",
    ],
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
ld80(
    name="memory-net-mode2-broken",
    address=CBASE,
    objs={
        CBASE: ["third_party/dr/ccp+ccp-juku"],
        FBASE: ["third_party/dr/bdos"],
        BBASE: [".+bios-net-mode2-broken"],
    },
)
ld80(
    name="memory-net-v2",
    address=CBASE,
    objs={
        CBASE: ["third_party/dr/ccp+ccp-juku"],
        FBASE: ["third_party/dr/bdos"],
        BBASE: [".+bios-net-v2"],
    },
)
ld80(
    name="memory-net-v2-ramout",
    address=0xB000,
    objs={
        0xB000: ["third_party/dr/ccp+ccp-juku"],
        0xB800: ["third_party/dr/bdos"],
        0xC600: [".+bios-net-v2-ramout"],
    },
)
ld80(
    name="memory-net-v2-rambio",
    address=0xB000,
    objs={
        0xB000: ["third_party/dr/ccp+ccp-juku"],
        0xB800: ["third_party/dr/bdos"],
        0xC600: [".+bios-net-v2-rambio"],
        0xCF00: [".+ram-keyboard"],
    },
)
ld80(
    name="memory-net-v3-rambio",
    address=0xB000,
    objs={
        0xB000: ["third_party/dr/ccp+ccp-juku"],
        0xB800: ["third_party/dr/bdos"],
        0xC600: [".+bios-net-v3-rambio"],
        0xCF00: [".+ram-keyboard"],
        0xD210: [".+netdisk-v3"],
        0xD480: [".+netconsole"],
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
    name="systemfile-net-mode2-broken",
    ins=[".+memory-net-mode2-broken"],
    outs=["=juku-net-mode2-broken-system.bin"],
    commands=[
        "python3 arch/juku/mksystem.py {ins[0]} {outs[0]}",
    ],
    label="JUKUNETMODE2BROKENSYSTEM",
)
simplerule(
    name="systemfile-net-v2",
    ins=[".+memory-net-v2"],
    outs=["=juku-net-v2-system.bin"],
    commands=[
        "python3 arch/juku/mksystem.py {ins[0]} {outs[0]}",
    ],
    label="JUKUNETV2SYSTEM",
)
simplerule(
    name="systemfile-net-v2-ramout",
    ins=[".+memory-net-v2-ramout"],
    outs=["=juku-net-v2-ramout-system.bin"],
    commands=[
        "python3 arch/juku/mksystem51.py {ins[0]} {outs[0]}",
    ],
    label="JUKUNETV2RAMOUTSYSTEM",
)
simplerule(
    name="systemfile-net-v2-rambio",
    ins=[".+memory-net-v2-rambio"],
    outs=["=juku-net-v2-rambio-system.bin"],
    commands=[
        "python3 arch/juku/mksystemram.py {ins[0]} {outs[0]}",
    ],
    label="JUKUNETV2RAMBIOSYSTEM",
)
simplerule(
    name="systemfile-net-v3-rambio",
    ins=[".+memory-net-v3-rambio"],
    outs=["=juku-net-v3-rambio-system.bin"],
    commands=[
        "python3 arch/juku/mksystemram.py --max-size 0x2600 "
        "{ins[0]} {outs[0]}",
    ],
    label="JUKUNETV3RAMBIOSYSTEM",
)
simplerule(
    name="fastboot-v6-bin",
    ins=[
        ".+fastboot-v6-core",
        ".+fastboot-v6-extension",
        ".+systemfile-net-mode2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v6.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v6.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV6",
)
simplerule(
    name="fastboot-v7-bin",
    ins=[
        ".+fastboot-v7-core",
        ".+fastboot-v7-extension",
        ".+systemfile-net-mode2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v7.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v7.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV7",
)
simplerule(
    name="fastboot-v8-bin",
    ins=[
        ".+fastboot-v8-core",
        ".+fastboot-v8-extension",
        ".+systemfile-net-mode2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v8.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v8.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV8",
)
simplerule(
    name="fastboot-v9-bin",
    ins=[
        ".+fastboot-v9-core",
        ".+fastboot-v9-extension",
        ".+systemfile-net-mode2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v9.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v9.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV9",
)
simplerule(
    name="fastboot-v10-bin",
    ins=[
        ".+fastboot-v10-core",
        ".+fastboot-v10-extension",
        ".+systemfile-net-mode2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v10.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v9.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV10",
)
simplerule(
    name="fastboot-v11-bin",
    ins=[
        ".+fastboot-v11-core",
        ".+fastboot-v11-extension",
        ".+systemfile-net-mode2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v11.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v9.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV11",
)
simplerule(
    name="fastboot-v12-bin",
    ins=[
        ".+fastboot-v12-core",
        ".+fastboot-v12-extension",
        ".+systemfile-net-mode2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v12.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v9.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV12",
)
simplerule(
    name="fastboot-v13-bin",
    ins=[
        ".+fastboot-v13-core",
        ".+fastboot-v13-extension",
        ".+systemfile-net-mode2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v13.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v9.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV13",
)
simplerule(
    name="fastboot-v14-bin",
    ins=[
        ".+fastboot-v14-core",
        ".+fastboot-v14-extension",
        ".+systemfile-net-mode2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v14.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v9.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV14",
)
simplerule(
    name="fastboot-v14-netdisk-v2-bin",
    ins=[
        ".+fastboot-v14-core",
        ".+fastboot-v14-extension",
        ".+systemfile-net-v2",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v14-netdisk-v2.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v9.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV14NETDISKV2",
)
simplerule(
    name="fastboot-v15-rambio-bin",
    ins=[
        ".+fastboot-v15-core",
        ".+fastboot-v15-extension",
        ".+systemfile-net-v2-rambio",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v15-rambio.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v9.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV15RAMBIO",
)
simplerule(
    name="fastboot-v15-netdisk-v3-bin",
    ins=[
        ".+fastboot-v15-core",
        ".+fastboot-v15-extension",
        ".+systemfile-net-v3-rambio",
        "third_party/zx0+zx0",
    ],
    outs=["=juku-fastboot-v15-netdisk-v3.bin"],
    commands=[
        "python3 arch/juku/build_fastboot_v9.py "
        "{ins[0]} {ins[1]} {ins[2]} {ins[3]} {outs[0]}",
    ],
    label="JUKUFASTBOOTV15NETDISKV3",
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

net_v2_diskimage = diskimage(
    name="net-v2-diskimage",
    format="juku386",
    bootfile=".+systemfile-net-v2",
    size=409600,
    map={
        "readme.txt": readme,
        "asm.com": "cpmtools+asm",
        "copy.com": "cpmtools+copy",
        "dump.com": "cpmtools+dump",
        "diag.com": ".+diag",
        "rdbench.com": ".+readbench",
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
        "rdbench.com": ".+readbench",
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
    name="net-v2-volume",
    ins=[net_v2_diskimage],
    outs=["=juku-net-v2.img"],
    commands=["cp {ins[0]} {outs[0]}"],
    label="JUKUNETV2VOLUME",
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
