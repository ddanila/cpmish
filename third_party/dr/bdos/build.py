from third_party.zmac.build import zmac


# Original Digital Research CP/M 2.2 BDOS. Its first six bytes precede the
# public entry point, matching the conventional FBASE+6 low-memory vector.
zmac(name="bdos", src="./os3bdos.asm", dri=True)
