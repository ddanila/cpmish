from third_party.zmac.build import zmac


# Original Digital Research CP/M 2.2 CCP. Unlike CP/Mish's default ZCPR1,
# this source uses only Intel 8080 instructions.
zmac(name="ccp", src="./os2ccp.asm", dri=True)
zmac(name="ccp-juku", src="./os2ccp.asm", dri=True, defines=["JUKU"])
