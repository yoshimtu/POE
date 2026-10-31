"""Bounded off-thread affine raster cache; moving frames only blit the result."""
from concurrent.futures import ThreadPoolExecutor
import math

from PySide6.QtCore import QRect,QRectF,QPointF
from PySide6.QtGui import QImage,QPainter,QTransform

RASTER_SCALE=1.25

def prepare_terrain(image,linear,rect):
    output=QImage(math.ceil(rect.width()*RASTER_SCALE),math.ceil(rect.height()*RASTER_SCALE),QImage.Format.Format_ARGB32_Premultiplied)
    output.fill(0)
    painter=QPainter(output)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setTransform(QTransform(*(value*RASTER_SCALE for value in linear),-rect.x()*RASTER_SCALE,-rect.y()*RASTER_SCALE))
    painter.drawImage(QPointF(0,0),image)
    painter.end()
    return output


class TerrainRasterCache:
    def __init__(self,defer=False):
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='terrain-raster')
        self.ready=None;self.pending=None;self.generation=0;self.closed=False
        self.defer=defer

    def clear(self):
        if self.ready is not None or self.pending is not None:
            self.generation+=1;self.ready=None
            if self.pending and(self.pending[0].done()or self.pending[0].cancel()):self.pending=None

    def paint(self,painter,image,transform,clip):
        if self.closed or not clip or not transform.isAffine():return False
        linear=tuple(round(v,12)for v in (transform.m11(),transform.m12(),transform.m21(),transform.m22()))
        key=(image.cacheKey(),linear)
        if self.ready and self.ready[0]!=key:self.ready=None
        if self.pending and self.pending[0].done():
            future,pending_key,rect,generation=self.pending;self.pending=None
            try:prepared=future.result()
            except Exception:prepared=None
            if prepared is not None and generation==self.generation and pending_key==key:
                self.ready=(key,rect,prepared)
        wanted=QRectF(*clip).translated(-transform.dx(),-transform.dy())
        ready=self.ready
        covered=bool(ready and QRectF(ready[1]).contains(wanted))
        refill=not covered or not QRectF(ready[1]).contains(wanted.adjusted(-64,-64,64,64))
        if refill and self.pending is None:
            margin=192;step=128
            rect=QRect(math.floor(wanted.x()/step)*step-margin,
                       math.floor(wanted.y()/step)*step-margin,
                       math.ceil(wanted.width())+2*margin+step,
                       math.ceil(wanted.height())+2*margin+step)
            # Two patches (ready and in flight) are the maximum retained. Very
            # large viewports fall back to the existing direct renderer.
            if 0<math.ceil(rect.width()*RASTER_SCALE)*math.ceil(rect.height()*RASTER_SCALE)<=8_000_000:
                future=self.pool.submit(prepare_terrain,image,linear,rect)
                self.pending=(future,key,rect,self.generation)
        if not covered:
            if not(self.defer and self.pending):return False
            if not ready:return True
        # A modest supersampled raster keeps Qt's smooth scaling path active.
        # Its 1:1 image-translation shortcut rounds fractional positions, which
        # would turn smooth map samples back into whole-pixel stepping.
        painter.drawImage(QRectF(ready[1].x()+transform.dx(),ready[1].y()+transform.dy(),
                                ready[1].width(),ready[1].height()),ready[2],
                          QRectF(0,0,ready[1].width()*RASTER_SCALE,ready[1].height()*RASTER_SCALE))
        return True

    def close(self):
        self.closed=True;self.clear();self.pool.shutdown(wait=False,cancel_futures=True)
