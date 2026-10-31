"""Record native item-component vtable/name facts using a read-only reference tool.

The reference is a development cross-check only; neither it nor its DLLs is
loaded by Obsidian Exile. Never changes profile validation or input settings.
"""
from pathlib import Path
import argparse
import json
import re
import struct
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from exile.platform import ReadMemory,game_window
from exile.storage import write_json

parser=argparse.ArgumentParser()
parser.add_argument("--profile",type=Path,required=True)
parser.add_argument("--reference",type=Path,required=True)
parser.add_argument("--entity",action="append",type=lambda x:int(x,0),required=True)
args=parser.parse_args()
profile=json.loads(args.profile.read_text(encoding="utf-8"))
table=profile.setdefault("item_component_vtables",{})
ambiguous=profile.setdefault("ambiguous_item_vtables",{})
with ReadMemory(game_window().pid) as memory:
    base=memory.main_image()
    for entity in args.entity:
        output=subprocess.run(["dotnet",str(args.reference),"--as","Entity",hex(entity),"--only","CacheComp"],
                              capture_output=True,encoding="utf-8",errors="replace",timeout=20,check=True).stdout
        pairs=re.findall(r"\[([A-Za-z][A-Za-z0-9_]+), (\d+)\]",output)
        if not pairs:raise ValueError("Reference did not return component names")
        for name,pointer_text in pairs:
            pointer=int(pointer_text)
            vtable,owner=struct.unpack("<QQ",memory.read(pointer,16))
            if owner!=entity or not base<=vtable<base+profile["offsets"]["image_size"]:
                raise ValueError("Reference component failed native owner/vtable cross-check")
            key=hex(vtable-base)
            if key in ambiguous:
                ambiguous[key]=sorted(set(ambiguous[key]+[name]))
            elif key in table and table[key]!=name:
                ambiguous[key]=sorted([table.pop(key),name])
            else:
                table[key]=name
write_json(args.profile,profile)
print(f"Verified {len(table)} item-component type mappings; excluded {len(ambiguous)} ambiguous mappings. Runtime remains independent.")
