"""Bounded read-only pointer-reference search; outputs addresses only."""
from pathlib import Path
import argparse
import json
import re
import struct
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from exile.platform import ReadMemory, game_window

parser=argparse.ArgumentParser()
parser.add_argument("target",type=lambda x:int(x,0),nargs="+")
parser.add_argument("--minimum",type=lambda x:int(x,0),required=True)
parser.add_argument("--maximum",type=lambda x:int(x,0),required=True)
parser.add_argument("--output",type=Path,required=True)
parser.add_argument("--seconds",type=int,default=25)
args=parser.parse_args()
needles={struct.pack("<Q",target):target for target in args.target}
pattern=re.compile(b"|".join(re.escape(n) for n in needles))
hits=[]
scanned=0
start=time.monotonic()
with ReadMemory(game_window().pid) as memory:
    image=memory.main_image()
    for address,size,protect,kind in memory.regions():
        lower,upper=max(address,args.minimum),min(address+size,args.maximum)
        if upper<=lower:
            continue
        for chunk in range(lower,upper,4*1024*1024):
            if time.monotonic()-start>args.seconds:break
            try:block=memory.read(chunk,min(4*1024*1024,upper-chunk))
            except OSError:continue
            scanned+=len(block)
            for match in pattern.finditer(block):
                hit=chunk+match.start()
                if hit%8==0:
                    entry={"address":hit,"target":needles[match[0]],"possible_owner_headers":[]}
                    # Common shared_ptr member layouts for research only.
                    for delta in (0,8,0x10,0x28,0x30,0x38,0x40,0x50):
                        try:
                            value=struct.unpack("<Q",memory.read(hit-delta,8))[0]
                            if image<=value<image+0x5000000:
                                entry["possible_owner_headers"].append({"member_offset":delta,"vtable_rva":value-image})
                        except OSError:pass
                    hits.append(entry)
        if time.monotonic()-start>args.seconds:break
report={"hits":hits[:10000],"total_hits":len(hits),"bytes":scanned,"seconds":round(time.monotonic()-start,2)}
args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps({**report,"hits":hits[:8]},indent=2))
