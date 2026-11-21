#!/usr/bin/env python3
"""Rename a shared library's SONAME in place.

The new name must not be longer than the old one: it is written over the old string in the dynamic string
table and padded with zero bytes, so no section or segment moves. (patchelf --set-soname moves .dynstr into a
new segment, which Android's linker then misreads: "cannot find ... from verneed".)
Usage: set_soname.py <library.so> <new soname>
"""
import struct, sys

path, new = sys.argv[1], sys.argv[2].encode()
d = bytearray(open(path, "rb").read())
assert d[:4] == b"\x7fELF" and d[4] == 2 and d[5] == 1, "64-bit little-endian ELF only"
phoff, = struct.unpack_from("<Q", d, 0x20)
phentsize, phnum = struct.unpack_from("<HH", d, 0x36)
loads, dyn = [], None
for i in range(phnum):
    p_type, _, p_offset, p_vaddr, _, p_filesz, _, _ = struct.unpack_from("<IIQQQQQQ", d, phoff + i * phentsize)
    if p_type == 1:
        loads.append((p_vaddr, p_offset, p_filesz))
    elif p_type == 2:
        dyn = (p_offset, p_filesz)
assert dyn, "no dynamic section"

def file_off(vaddr):
    for va, off, sz in loads:
        if va <= vaddr < va + sz:
            return off + vaddr - va
    raise SystemExit("address not in a loaded segment")

tags = {}
for k in range(dyn[1] // 16):
    tag, val = struct.unpack_from("<qQ", d, dyn[0] + 16 * k)
    if tag == 0:
        break
    tags.setdefault(tag, val)
strtab, soname = file_off(tags[5]), tags.get(14)
assert soname is not None, "library has no SONAME"
at = strtab + soname
old = bytes(d[at:d.index(b"\0", at)])
assert len(new) <= len(old), f"new name longer than {old.decode()}"
d[at:at + len(old)] = new + b"\0" * (len(old) - len(new))
open(path, "wb").write(d)
print(f"SONAME {old.decode()} -> {new.decode()}")
