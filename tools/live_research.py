"""Read-only structural probes. Never persists arbitrary memory or character data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exile.platform import ReadMemory, game_window, process_path


def pe_sections(data):
    offset = struct.unpack_from("<I", data, 0x3c)[0]
    count = struct.unpack_from("<H", data, offset + 6)[0]
    optional = offset + 24
    size = struct.unpack_from("<H", data, offset + 20)[0]
    base = struct.unpack_from("<Q", data, optional + 24)[0]
    sections = []
    for i in range(count):
        start = optional + size + i * 40
        virtual_size, rva, raw_size, raw = struct.unpack_from("<IIII", data, start + 8)
        sections.append((data[start:start+8].split(bytes([0]))[0].decode(),rva,raw,raw_size))
    return base, sections


def analyze(executable):
    data = executable.read_bytes()
    base, sections = pe_sections(data)
    def raw_to_rva(raw):
        for _,rva,start,size in sections:
            if start <= raw < start+size:
                return rva+raw-start
        raise ValueError("Offset outside sections")
    def rva_to_raw(address):
        for _,rva,start,size in sections:
            if rva <= address < rva+size:
                return start+address-rva
        raise ValueError("RVA outside file")
    probes = []
    for match in re.finditer(rb"\.\?AV[^\x00]{1,350}\x00", data):
        name = match[0][:-1].decode("ascii",errors="replace")
        if "InGameState@States@@" in name:
            descriptor = raw_to_rva(match.start()-16)
            probes.append({"kind":"state-callback-type", "name":name,"descriptor_rva":descriptor})
    text = next(s for s in sections if s[0]==".text")
    code = data[text[2]:text[2]+text[3]]
    targets = {p["descriptor_rva"]:p for p in probes}
    for match in re.finditer(rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d](....)",code,re.S):
        rva = text[1]+match.start()
        target = rva+7+struct.unpack("<i",match[1])[0]
        if target in targets:
            targets[target].setdefault("code_xrefs",[]).append(rva)
    for probe in probes:
        for xref in probe.get("code_xrefs",[]):
            # MSVC std::function type-erasure table: copy, move, invoke,
            # target_type, delete, target. Verify the first three are code.
            for match in re.finditer(re.escape(struct.pack("<Q",base+xref)),data):
                if match.start()<24:
                    continue
                entries=struct.unpack_from("<QQQ",data,match.start()-24)
                if all(base+text[1]<=entry<base+text[1]+text[3] for entry in entries):
                    probe.setdefault("callback_vtable_rvas",[]).append(raw_to_rva(match.start()-24))
    # Life's component-name constructor emits a short 'Life' literal and a
    # vtable assignment. Candidate tables are checked before live scanning.
    life = []
    for match in re.finditer(b"Life",code):
        window = code[max(0,match.start()-100):match.start()]
        for lea in re.finditer(rb"\x48\x8d\x05(....)\x48\x89[\x01\x03]",window,re.S):
            rva=text[1]+max(0,match.start()-100)+lea.start()
            target=rva+7+struct.unpack("<i",lea[1])[0]
            try:
                raw=rva_to_raw(target)
                functions=struct.unpack_from("<QQQ",data,raw)
                if all(base+text[1] <= f < base+text[1]+text[3] for f in functions):
                    life.append({"vtable_rva":target,"constructor_rva":rva})
            except (ValueError,struct.error):
                pass
    return {"preferred_base":base,"sections":sections,"state_callbacks":probes,"life_vtables":life}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--scan-private",action="store_true")
    parser.add_argument("--max-seconds",type=int,default=35)
    parser.add_argument("--skip-mb",type=int,default=0)
    parser.add_argument("--max-region-mb",type=int,default=0)
    parser.add_argument("--vtable-rva",action="append",type=lambda value:int(value,0),default=[])
    args=parser.parse_args()
    window=game_window()
    if not window.pid:
        raise SystemExit("PoE is not running")
    executable=Path(process_path(window.pid))
    report=analyze(executable)
    with ReadMemory(window.pid) as memory:
        image=memory.main_image()
        regions=list(memory.regions())
        report.update({"pid":window.pid,"main_image":image,"readable_regions":len(regions),
                       "private_readable_bytes":sum(size for _,size,_,kind in regions if kind==0x20000),
                       "validated":False})
        if args.scan_private:
            needles={struct.pack("<Q",image+v):p["name"] for p in report["state_callbacks"]
                     for v in p.get("callback_vtable_rvas",[])}
            needles.update({struct.pack("<Q",image+v):f"native-vtable-{v:#x}" for v in args.vtable_rva})
            pattern=re.compile(b"|".join(re.escape(needle) for needle in needles)) if needles else None
            found=[]
            start=time.monotonic()
            scanned=0
            skipped=0
            last_address=0
            complete=True
            for address,size,protect,kind in regions:
                if kind!=0x20000 or not protect & 0xcc:
                    continue
                if args.max_region_mb and size>args.max_region_mb*1024*1024:
                    continue
                for offset in range(0,size,4*1024*1024):
                    count=min(4*1024*1024,size-offset)
                    if skipped<args.skip_mb*1024*1024:
                        skipped+=count
                        continue
                    if time.monotonic()-start>args.max_seconds:
                        complete=False
                        break
                    last_address=address+offset
                    try:
                        block=memory.read(address+offset,count)
                    except OSError:
                        continue
                    scanned+=len(block)
                    if pattern:
                        for match in pattern.finditer(block):
                            if (address+offset+match.start())%8:
                                continue
                            object_address=address+offset+match.start()
                            found.append({"address":object_address,"type":needles[match[0]]})
                if not complete:
                    break
            report.update({"callback_objects":found[:200],"scan_complete":complete,
                           "scanned_bytes":scanned,"last_address":last_address,
                           "scan_seconds":round(time.monotonic()-start,2)})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({key:report[key] for key in ("readable_regions","state_callbacks","life_vtables",
                      "callback_objects","scan_complete","scanned_bytes","scan_seconds") if key in report},indent=2))


if __name__=="__main__":main()
