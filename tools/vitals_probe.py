"""Read-only search for user-confirmed displayed life/mana values.

Candidates require multiple nearby confirmed values and are not automatically
accepted as game structures. Saves addresses/field offsets only.
"""
from pathlib import Path
import argparse
import json
import struct
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from exile.platform import ReadMemory,game_window

parser=argparse.ArgumentParser()
parser.add_argument("--life",type=int,required=True)
parser.add_argument("--mana",type=int,required=True)
parser.add_argument("--usable-mana",type=int,required=True)
parser.add_argument("--output",type=Path,required=True)
parser.add_argument("--minimum",type=lambda x:int(x,0),default=0x10000)
parser.add_argument("--maximum",type=lambda x:int(x,0),default=0x7fffffffffff)
parser.add_argument("--seconds",type=int,default=30)
args=parser.parse_args()
life,mana,usable=[struct.pack('<i',v) for v in (args.life,args.mana,args.usable_mana)]
hits=[]; scanned=0;start=time.monotonic()
with ReadMemory(game_window().pid) as m:
    image=m.main_image()
    for a,size,protect,kind in m.regions():
        low,high=max(a,args.minimum),min(a+size,args.maximum)
        if low>=high or kind!=0x20000 or not protect & 0xcc:continue
        for offset in range(low,high,4*1024*1024):
            if time.monotonic()-start>args.seconds:break
            try:block=m.read(offset,min(4*1024*1024,high-offset))
            except OSError:continue
            scanned+=len(block)
            position=block.find(life)
            while position>=0:
                address=offset+position
                if address%4==0:
                    lo=max(0,position-192);hi=min(len(block),position+192)
                    near=block[lo:hi]
                    if mana in near and usable in near:
                        fields={}
                        for tag,needle in (("life",life),("mana",mana),("usable_mana",usable)):
                            found=[];index=near.find(needle)
                            while index>=0:
                                if (lo+index)%4==0:found.append(lo+index-position)
                                index=near.find(needle,index+1)
                            fields[tag]=found
                        headers=[]
                        for back in range(0,min(512,position)+1,8):
                            if position-back+8>len(block):continue
                            value=struct.unpack_from('<Q',block,position-back)[0]
                            if image<=value<image+0x5000000:
                                headers.append({"before_life":back,"vtable_rva":value-image})
                        hits.append({"life_address":address,"nearby_fields":fields,"headers":headers})
                position=block.find(life,position+4)
        if time.monotonic()-start>args.seconds:break
report={"candidates":hits[:1000],"total":len(hits),"bytes":scanned,"seconds":round(time.monotonic()-start,2)}
args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({**report,"candidates":hits[:12]},indent=2))
