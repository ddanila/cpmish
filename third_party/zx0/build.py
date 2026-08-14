from build.c import cprogram


cprogram(
    name="zx0",
    srcs=[
        "./zx0.c",
        "./optimize.c",
        "./compress.c",
        "./memory.c",
        "./zx0.h",
    ],
    cflags=["-Wno-sign-compare"],
)
