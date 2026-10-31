"""Bounded executable-only disassembly for independent offset research."""
from pathlib import Path
import argparse
import bisect
import re
import struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from live_research import pe_sections

parser=argparse.ArgumentParser()
parser.add_argument("rva",type=lambda x:int(x,0))
parser.add_argument("--length",type=int,default=180)
parser.add_argument("--xrefs",action="store_true")
parser.add_argument("--function",action="store_true")
args=parser.parse_args()
data=Path(r"D:\SteamLibrary\steamapps\common\Path of Exile\PathOfExileSteam.exe").read_bytes()
base,sections=pe_sections(data)
def raw(rva):
    for _,v,p,s in sections:
        if v<=rva<v+s:return p+rva-v
    raise ValueError("RVA outside sections")
pdata=next(s for s in sections if s[0]==".pdata")
functions=[]
for offset in range(pdata[2],pdata[2]+pdata[3]-11,12):
    start,end,_=struct.unpack_from("<III",data,offset)
    if start and start<end:functions.append((start,end))
functions.sort()
starts=[entry[0] for entry in functions]
def containing(address):
    index=bisect.bisect_right(starts,address)-1
    return functions[index] if index>=0 and address<functions[index][1] else (address,address+args.length)
if args.xrefs:
    text=next(s for s in sections if s[0]==".text")
    code=data[text[2]:text[2]+text[3]]
    for match in re.finditer(rb"[\x48\x4c][\x8d\x8b\x89][\x05\x0d\x15\x1d\x25\x2d\x35\x3d](....)",code,re.S):
        address=text[1]+match.start()
        if address+7+struct.unpack("<i",match[1])[0]==args.rva:
            print("RIP-MEM",hex(address),"function",*[hex(x) for x in containing(address)])
    for match in re.finditer(rb"\xe8(....)",code,re.S):
        address=text[1]+match.start()
        if address+5+struct.unpack("<i",match[1])[0]==args.rva:
            print("CALL",hex(address),"function",*[hex(x) for x in containing(address)])
else:
    start,end=containing(args.rva) if args.function else (args.rva,args.rva+args.length)
    end=min(end,start+min(args.length,32768))
    print("FUNCTION",hex(start),hex(end))
    for instruction in Cs(CS_ARCH_X86,CS_MODE_64).disasm(data[raw(start):raw(start)+end-start],start):
        print(hex(instruction.address),instruction.mnemonic,instruction.op_str)
