"""Render actual widgets with isolated settings, no reader polling or game input."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys
from pathlib import Path
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage,QPainter,QColor,QFontDatabase,QFont
import exile.app as ui
from exile.route_legend import paint_legend
from exile.wealth_panel import paint_wealth
from exile.preload_panel import paint_preloads

app=QApplication([])
app.setStyle('Fusion')
for name in ('georgia.ttf','segoeui.ttf','seguisym.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
app.setStyleSheet(ui.STYLE)
with tempfile.TemporaryDirectory()as tmp:
    ui.data_root=lambda:Path(tmp)
    w=ui.MainWindow();w.timer.stop();w.show();app.processEvents()
    w.status_label.setText('Waiting for Path of Exile')
    w.notice.setText('Modules start off. Your settings stay saved.')
    w.grab().save('preview-waymark-skinned.png')
    for name in ('radar','pricing','routes'):
        w.select_module(next(p for p in w.manager.plugins if p.id==name));app.processEvents()
        w.grab().save(f'.reference/skin-{name}.png')
    w.navigate(1);app.processEvents();w.grab().save('.reference/skin-workshop.png')
    canvas=QImage(1040,360,QImage.Format.Format_ARGB32_Premultiplied);canvas.fill(QColor('#242722'))
    p=QPainter(canvas)
    font=QFont('Georgia');font.setPixelSize(16);p.setFont(font);p.setPen(QColor('#e1d4b9'))
    p.drawText(24,30,'Waymark · actual overlay panels with sample data')
    paint_legend(p,QRectF(24,52,270,103),[
        dict(name='Arena',color='#79b5db',status=''),dict(name='The Western Forest',color='#c6a3d6',status='')],dict(legend_font=12,legend_opacity=95))
    paint_wealth(p,318,52,[dict(title='Inventory',total_label='12.4d',unknown=0,top=[
        dict(name='Divine Orb',quantity=12,price_label='12d'),dict(name='Chaos Orb',quantity=100,price_label='100c'),
        dict(name='Vaal Orb',quantity=30,price_label='18c')])],dict(summary_width=340,summary_font=12,summary_opacity=95))
    paint_preloads(p,682,52,[dict(label='Diviner’s Strongbox',color='#dbc38b',evidence='Seen'),
        dict(label='Expedition',color='#b0c9b0',evidence='Preload'),dict(label='Breach',color='#b39bd2',evidence='Seen')],
        dict(width=334,font_size=12,opacity=95))
    p.end();canvas.save('preview-waymark-skinned-overlays.png')
    w.close();app.processEvents()
