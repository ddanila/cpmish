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
    },
)
