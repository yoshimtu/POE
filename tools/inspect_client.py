"""Offline PE inspection for independent profile development.

Produces research candidates, never enables a profile or touches game memory.
The 2022 public root signature is used only as an explicitly historical probe:
https://github.com/Qvin0000/ExileApi/blob/master/Core/PoEMemory/Offsets.cs
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct


def inspect(executable: Path) -> dict:
    data = executable.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("Not a Windows executable")
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Invalid PE signature")
    machine, count = struct.unpack_from("<HH", data, pe + 4)
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic != 0x20b or machine != 0x8664:
        raise ValueError("Expected the x64 game executable")
    image_base = struct.unpack_from("<Q", data, optional + 24)[0]
    section_table = optional + optional_size
    sections = []
    for i in range(count):
        start = section_table + 40 * i
        name = data[start:start + 8].split(b"\0", 1)[0].decode(errors="replace")
        virtual_size, rva, size, raw = struct.unpack_from("<IIII", data, start + 8)
        flags = struct.unpack_from("<I", data, start + 36)[0]
        sections.append(dict(name=name, rva=rva, raw=raw, size=size, virtual_size=virtual_size, flags=flags))

    def rva_for_raw(offset):
        for section in sections:
            if section["raw"] <= offset < section["raw"] + section["size"]:
                return section["rva"] + offset - section["raw"]
        return None

    names = ("InGameState", "IngameState", "GameState", "AreaLoadingState", "LoginState", "SelectCharacterState")
    strings = {}
    for name in names:
        for encoding in ("ascii", "utf-16-le"):
            needle = name.encode(encoding) + (b"\0" if encoding == "ascii" else b"\0\0")
            for match in re.finditer(re.escape(needle), data):
                rva = rva_for_raw(match.start())
                if rva is not None:
                    strings[rva] = {"name": name, "encoding": encoding, "rva": hex(rva)}
    xrefs = []
    historical = []
    # LEA reg,[RIP+disp32]. References locate constructors/registration sites,
    # but do not by themselves establish live global roots or field layouts.
    lea = re.compile(rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d](....)", re.S)
    old_root = bytes.fromhex("48 83 ec 50 48 c7 44 24")
    for section in sections:
        if not section["flags"] & 0x20000000:
            continue
        code = data[section["raw"]:section["raw"] + section["size"]]
        for match in lea.finditer(code):
            rva = section["rva"] + match.start()
            target = rva + 7 + struct.unpack("<i", match[1])[0]
            if target in strings:
                xrefs.append({"instruction_rva": hex(rva), "target": strings[target]})
        for match in re.finditer(re.escape(old_root), code):
            # Full historical mask, not just the short prefix.
            offset = match.start()
            tail = code[offset:offset + 39]
            if len(tail) == 39 and tail[13:17] == bytes.fromhex("48 89 9c 24") and tail[21:28] == bytes.fromhex("48 8b f9 33 ed 48 39") and tail[32:35] == bytes.fromhex("01 0f 85"):
                rva = section["rva"] + offset
                target = rva + 33 + struct.unpack_from("<i", tail, 29)[0]
                historical.append({"instruction_rva": hex(rva), "candidate_root_rva": hex(target)})
    return {"exe": str(executable), "sha256": hashlib.sha256(data).hexdigest(),
            "image_base": hex(image_base), "sections": sections,
            "state_strings": list(strings.values()), "state_string_xrefs": xrefs,
            "historical_root_signature_matches": historical,
            "validated": False,
            "limitations": "Static candidates only. Does not establish live roots, entity/component layouts, terrain decoding or current-build compatibility."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = inspect(args.executable)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"State strings: {len(report['state_strings'])}; xrefs: {len(report['state_string_xrefs'])}; historical root matches: {len(report['historical_root_signature_matches'])}. Not validated.")
