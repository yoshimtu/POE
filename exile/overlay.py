from __future__ import annotations

from itertools import groupby
import logging
import time

from PySide6.QtCore import Qt, QPointF, QRectF, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QWidget

from exile.model import Mark
from exile.route_legend import paint_legend,legend_height
from exile.preload_panel import paint_preloads
from exile.map_icons import icon_image
from exile.wealth_panel import paint_item_price,paint_wealth
from exile.terrain_raster import TerrainRasterCache


def batch_dots(marks):
    """Batch consecutive identical filled circles; preserve draw order and opacity."""
    def style(mark):
        if mark.kind=='dot'and not mark.text and isinstance(mark.payload,dict)and mark.payload.get('icon'):
            return ('icon',mark.color,mark.size,mark.value,mark.clip,tuple(sorted(mark.payload.items())))
        if mark.kind=='dot' and not mark.text and isinstance(mark.payload,dict) and mark.payload.get('filled',True) and not mark.payload.get('icon'):
            return mark.color,mark.size,mark.value,mark.clip,mark.payload.get('width',1)
        return id(mark)
    for key,run in groupby(marks,key=style):
        group=list(run)
        if isinstance(key,tuple) and len(group)>1:
            first=group[0]
            yield Mark('icon_batch'if key[0]=='icon'else'dot_batch',first.x,first.y,color=first.color,size=first.size,value=first.value,
                       clip=first.clip,payload=first.payload,points=[(m.x,m.y)for m in group])
        else:yield from group


def paint_marks(p: QPainter, marks: list[Mark],terrain_cache=None):
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setFont(QFont("Segoe UI", 10))
    for mark in batch_dots(marks):
        p.save()
        if mark.clip:
            p.setClipRect(QRectF(*mark.clip))
        color = QColor(mark.color)
        p.setPen(QPen(color, 2))
        p.setBrush(color)
        x, y, size = mark.x, mark.y, mark.size
        if mark.kind == 'terrain' and mark.payload is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            image = mark.payload
            source = QPolygonF([QPointF(0, 0), QPointF(image.width(), 0), QPointF(image.width(), image.height()), QPointF(0, image.height())])
            destination = QPolygonF([QPointF(*point) for point in mark.points])
            transform = QTransform.quadToQuad(source, destination)
            if transform is not None:
                screen_transform = p.transform()
                p.setOpacity(mark.value)
                if terrain_cache is None or not terrain_cache.paint(p,image,transform,mark.clip):
                    p.setTransform(transform, True)
                    p.drawImage(QPointF(0, 0), image)
                if mark.exclusion:
                    mask, origin = mark.exclusion
                    p.setTransform(screen_transform)
                    p.setOpacity(1)
                    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
                    p.drawImage(QPointF(*origin), mask)
        elif mark.kind in ('preload_panel','uptime_panel'):
            payload=mark.payload
            paint_preloads(p,x,y,payload['rows'],payload['settings'],payload.get('overflow',0))
        elif mark.kind=='item_price'and mark.points:
            paint_item_price(p,QRectF(x,y,*mark.points[0]),mark.text,mark.color,(mark.payload or{}).get('font',10))
        elif mark.kind=='wealth_panel':
            paint_wealth(p,x,y,mark.payload['sections'],mark.payload['settings'])
        elif mark.kind == "tile":
            color.setAlphaF(max(0, min(1, mark.value)))
            width, height = mark.points[0]
            p.fillRect(QRectF(x, y, width, height), color)
        elif mark.kind=='dot_batch':
            p.setOpacity(mark.value)
            p.setPen(QPen(color,mark.size*2+mark.payload.get('width',1),Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            p.drawPoints(QPolygonF([QPointF(*point)for point in mark.points]))
        elif mark.kind in ('dot','icon_batch'):
            payload=mark.payload if isinstance(mark.payload,dict)else{}
            diameter=max(payload.get('icon_minimum',12),mark.size*4)*payload.get('icon_scale',100)/100
            image=icon_image(payload['icon'],round(diameter,2),round(p.device().devicePixelRatioF(),2),payload.get('icon_tint',''))if payload.get('icon')else None
            if image is not None and not image.isNull():
                p.setOpacity(mark.value)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                for px,py in (mark.points if mark.kind=='icon_batch'else[(x,y)]):
                    p.drawImage(QRectF(px-diameter/2,py-diameter/2,diameter,diameter),image)
                if mark.text:p.drawText(QPointF(x+diameter/2+5,y+4),mark.text)
                p.restore()
                continue
            if isinstance(mark.payload, dict):
                p.setOpacity(mark.value)
                p.setPen(QPen(color, mark.payload.get('width', 1)))
                p.setBrush(color if mark.payload.get('filled', True) else Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x, y), size, size)
            if mark.text:
                p.drawText(QPointF(x + size + 5, y + 4), mark.text)
        elif mark.kind == "ring":
            fill = QColor(color)
            fill.setAlpha(35)
            p.setBrush(fill)
            p.drawEllipse(QPointF(x, y), size, size)
            p.drawText(QPointF(x - size, y - size - 8), mark.text)
        elif mark.kind == "path":
            p.setBrush(Qt.BrushStyle.NoBrush)
            if isinstance(mark.payload,dict) and mark.payload.get('ground_route'):
                p.setOpacity(mark.value)
                p.setPen(QPen(color,mark.size,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            p.drawPolyline(QPolygonF([QPointF(px, py) for px, py in mark.points]))
            if mark.points:
                px, py = mark.points[-1]
                p.drawText(QPointF(px + 8, py), mark.text)
        elif mark.kind == 'route_legend':
            settings=mark.payload['settings'];rows=mark.payload['rows']
            width=settings['legend_width']
            paint_legend(p,QRect(900-width-18,18,width,legend_height(rows,settings)),rows,settings)
        elif mark.kind == "slot" and mark.points:
            width, height = mark.points[0]
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(x + 1, y + 1, width - 2, height - 2))
        elif mark.kind == "price" and mark.points:
            width, height = mark.points[0]
            p.save()
            font = QFont("Segoe UI", 8)
            p.setFont(font)
            box = QRectF(x, y + height - 16, width, 16)
            # Fit every digit rather than replacing the value with an ellipsis.
            while p.fontMetrics().horizontalAdvance(mark.text) > width - 2 and font.pointSizeF() > 5:
                font.setPointSizeF(font.pointSizeF() - .5)
                p.setFont(font)
            required = p.fontMetrics().horizontalAdvance(mark.text) + 4
            if required > width:
                box.setWidth(required)
            p.setClipRect(box)
            p.fillRect(box, QColor(14, 16, 21, 225))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, mark.text)
            p.restore()
        elif mark.kind == "bar":
            height = mark.payload.get('height', 6) if isinstance(mark.payload, dict) else 6
            p.fillRect(QRectF(x - size / 2 - 1, y - 1, size + 2, height + 2), QColor("#111319"))
            p.fillRect(QRectF(x - size / 2, y, size * max(0, min(1, mark.value)), height), color)
            p.drawText(QPointF(x - size / 2, y - 7), mark.text)
        elif mark.kind in ("text", "label"):
            rect = p.fontMetrics().boundingRect(mark.text)
            p.fillRect(QRectF(x - 5, y - rect.height(), rect.width() + 12, rect.height() + 7), QColor(14, 16, 21, 215))
            p.drawText(QPointF(x, y), mark.text)
        p.restore()


class Overlay(QWidget):
    def __init__(self):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput |
                 Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.marks = []
        self.terrain_cache=TerrainRasterCache(defer=True)

    def present(self, window, marks):
        if not any(mark.kind=='terrain'for mark in marks):self.terrain_cache.clear()
        if not window.foreground or window.width <= 0 or window.height <= 0 or not marks:
            self.hide()
            return
        # Platform coordinates are physical pixels; Qt's geometry uses DIPs.
        screen = self.screen()
        ratio = screen.devicePixelRatio() if screen else 1
        geometry = QRect(round(window.x / ratio), round(window.y / ratio),
                         round(window.width / ratio), round(window.height / ratio))
        if geometry != self.geometry():
            self.setGeometry(geometry)
        self.coordinate_ratio = ratio
        self.marks = marks
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, _):
        started=time.perf_counter()
        p = QPainter(self)
        # Explicitly clear the translucent backing store. Moving/dead markers
        # must not survive as pixels from a preceding frame.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        ratio = getattr(self, "coordinate_ratio", 1)
        p.scale(1 / ratio, 1 / ratio)
        paint_marks(p, self.marks,self.terrain_cache)
        p.end()
        elapsed=(time.perf_counter()-started)*1000
        samples=getattr(self,'paint_samples',[]);samples.append(elapsed);self.paint_samples=samples[-1200:]
        if time.monotonic()-getattr(self,'paint_log_at',0)>10:
            self.paint_log_at=time.monotonic();ordered=sorted(self.paint_samples)
            logging.info('Overlay paint: p50=%.1f p95=%.1f max=%.1f ms; marks=%d',
                ordered[len(ordered)//2],ordered[min(len(ordered)-1,int(len(ordered)*.95))],max(ordered),len(self.marks))
            self.paint_samples=[]

    def closeEvent(self,event):
        self.terrain_cache.close()
        super().closeEvent(event)


class PreviewCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.marks = []
        self.setMinimumSize(600, 440)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101319"))
        p.setPen(QPen(QColor("#1a1f28"), 1))
        for x in range(0, self.width(), 32):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 32):
            p.drawLine(0, y, self.width(), y)
        p.scale(self.width() / 900, self.height() / 650)
        paint_marks(p, self.marks)
        p.setPen(QColor("#8f98a8"))
        p.setFont(QFont("Segoe UI", 12))
        p.drawText(QPointF(30, 38), "SYNTHETIC PREVIEW  /  No live game data or input")
        if not self.marks:
            p.drawText(QPointF(70, 290), "Enable a visual module to preview it here.")
