from build.ab import export

export(
    name="all",
    items={
        "pn8510.img": "arch/brother/pn8510+diskimage",
        "pn8800.img": "arch/brother/pn8800+diskimage",
        "wp2450.img": "arch/brother/wp2450+diskimage",
        "lw30.img": "arch/brother/lw30+diskimage",
        "wp1.img": "arch/brother/wp1+diskimage",
        "kayproii.img": "arch/kayproii+diskimage",
        "nc200.img": "arch/nc200+diskimage",
        "nano-z80.img": "arch/nano-z80+diskimage",
        "juku.img": "arch/juku+diskimage",
        "juku-system.bin": "arch/juku+systemfile",
        "juku-net-system.bin": "arch/juku+systemfile-net",
        "juku-net-smoke-system.bin": "arch/juku+systemfile-net-smoke",
        "juku-net-baudtest-system.bin": "arch/juku+systemfile-net-baudtest",
        "juku-net-baudtest2-system.bin": "arch/juku+systemfile-net-baudtest2",
        "juku-net-mode2-soak-system.bin": "arch/juku+systemfile-net-mode2-soak",
        "juku-net-smoke.img": "arch/juku+net-smoke-volume",
        "juku-net-baudtest-9600.img": "arch/juku+net-baudtest-9600-volume",
        "juku-net-baudtest-8n1.img": "arch/juku+net-baudtest-8n1-volume",
        "juku-net-baudtest-ladder.img": "arch/juku+net-baudtest-ladder-volume",
        "juku-net-baudtest2.img": "arch/juku+net-baudtest2-volume",
        "juku-net-mode2-soak.img": "arch/juku+net-mode2-soak-volume",
    },
)
