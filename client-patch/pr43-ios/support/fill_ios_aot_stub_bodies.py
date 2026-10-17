"""Compiler-only type-correct return stubs; never linked as runtime implementations."""

def return_stub(name: str) -> bytes:
    if name == "void":
        return b"\x47"  # returnvoid
    if name == "Boolean":
        return b"\x27\x48"  # pushfalse; returnvalue
    if name in ("int", "uint"):
        return b"\x24\x00\x48"  # pushbyte 0; returnvalue
    if name == "Number":
        return b"\x28\x48"  # pushnan; returnvalue
    if name == "*":
        return b"\x21\x48"  # pushundefined; returnvalue
    return b"\x20\x48"  # pushnull; returnvalue
