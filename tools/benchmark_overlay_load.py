"""Compare identical crowded icon frames before/after batching; no game input."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,time,statistics,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter
from exile.model import Mark
import exile.overlay as drawing

app=QApplication([])
marks=[Mark('dot',20+(i*19)%1850,30+(i*13)%980,size=2,value=.9,clip=(0,0,1920,1080),
    payload=dict(icon='poe2:RareMonsterAlive',icon_tint='#dc6464',icon_minimum=8,icon_scale=100))for i in range(5000)]
marks += [Mark('bar',20+(i*39)%1850,30+(i*27)%980,size=70,value=.75)for i in range(200)]
batch=drawing.batch_dots;report={}
for name,fn in [('unbatched',lambda marks:iter(marks)),('batched',batch)]:
    drawing.batch_dots=fn;samples=[]
    image=QImage(1920,1080,QImage.Format.Format_ARGB32_Premultiplied)
    for i in range(31):
        image.fill(0);p=QPainter(image);start=time.perf_counter();drawing.paint_marks(p,marks);p.end()
        if i:samples.append((time.perf_counter()-start)*1000)
    ordered=sorted(samples);report[name]=dict(median_ms=round(statistics.median(samples),2),p95_ms=round(ordered[int((len(ordered)-1)*.95)],2))
drawing.batch_dots=batch
report['icons']=5000;report['bars']=200
Path('.reference/overlay-load-benchmark.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
