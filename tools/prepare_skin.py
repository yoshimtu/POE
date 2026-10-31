"""Extract runtime sprites from the original imagegen artwork; no generated labels."""
from pathlib import Path
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QPainter,QPen,QColor,QPolygonF

ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'skin'

def main():
    panel = QImage(str(ROOT / 'panel-source.png'))
    assert not panel.isNull()
    panel.scaled(768, 512, Qt.AspectRatioMode.IgnoreAspectRatio,
                 Qt.TransformationMode.SmoothTransformation).save(str(ROOT / 'panel.png'))
    panel.copy(180, 180, 640, 640).save(str(ROOT / 'texture.png'))
    controls = QImage(str(ROOT / 'controls-source.png'))
    # The generated atlas has interior frames; these bounds extract those frames,
    # excluding the sheet's gutters. Coordinates refer to the 1536x1024 source.
    rows = [('button', (20, 54, 476, 178)), ('row', (8, 315, 498, 161)),
            ('field', (22, 565, 470, 136)), ('tab', (16, 782, 484, 205))]
    for name, (x, y, width, height) in rows:
        for col, state in enumerate(('normal', 'active', 'pressed')):
            sprite = controls.copy(round((x + col * 512) * controls.width() / 1536),
                round(y * controls.height() / 1024), round(width * controls.width() / 1536),
                round(height * controls.height() / 1024))
            sprite.scaled(238, 84, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation).save(str(ROOT / f'{name}-{state}.png'))
    icons = QImage(str(ROOT / 'icons-source.png'))
    names = ('modules', 'workshop', 'history', 'search', 'map', 'routes', 'radar',
             'alerts', 'stash', 'hazards', 'hourglass', 'cog')
    for i, name in enumerate(names):
        x0, x1 = round(i % 4 * icons.width() / 4), round((i % 4 + 1) * icons.width() / 4)
        y0, y1 = round(i // 4 * icons.height() / 3), round((i // 4 + 1) * icons.height() / 3)
        icons.copy(x0, y0, x1-x0, y1-y0).save(str(ROOT / f'icon-{name}.png'))
    # State marks stay pixel-perfect and readable at small sizes over the skin.
    box=QImage(str(ROOT/'field-normal.png')).scaled(32,32)
    p=QPainter(box);p.setPen(QPen(QColor('#9d8256'),2));p.drawRect(2,2,27,27);p.end()
    box.save(str(ROOT/'check-off.png'))
    p=QPainter(box);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(5,5,22,22,QColor('#a38b58'))
    p.setPen(QPen(QColor('#211c13'),4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    p.drawLine(QPointF(8,16),QPointF(14,22));p.drawLine(QPointF(14,22),QPointF(25,9));p.end()
    box.save(str(ROOT/'check-on.png'))
    for name,points in [('down',[(3,5),(13,5),(8,10)]),('up',[(3,10),(13,10),(8,5)])]:
        image=QImage(16,16,QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
        p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#bca681'))
        p.drawPolygon(QPolygonF([QPointF(*point)for point in points]));p.end()
        image.save(str(ROOT/f'arrow-{name}.png'))

if __name__ == '__main__':
    main()
