import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage,QPainter,QTransform,QColor

from exile.terrain_raster import TerrainRasterCache


def source_image():
    image=QImage(128,128,QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor('white'));painter.setPen(QColor('white'));painter.drawEllipse(QPointF(64,64),4,4);painter.end()
    return image


def render(cache,image,transform):
    output=QImage(320,240,QImage.Format.Format_ARGB32_Premultiplied);output.fill(0)
    painter=QPainter(output);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    used=cache.paint(painter,image,transform,(0,0,320,240))if cache else False
    if not used:painter.setTransform(transform);painter.drawImage(QPointF(0,0),image)
    painter.end();return output,used


def centroid(image):
    pixels=np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine())
    alpha=pixels[:,:image.width()*4].reshape(image.height(),image.width(),4)[:,:,3].astype(float)
    ys,xs=np.indices(alpha.shape)
    return float((xs*alpha).sum()/alpha.sum()),float((ys*alpha).sum()/alpha.sum())


@pytest.mark.parametrize('offset',[(140,30),(140.37,30.17),(141.9,32.8)])
def test_cached_affine_preserves_landmark_alignment_including_subpixel_motion(offset):
    cache=TerrainRasterCache();image=source_image();transform=QTransform(.9,.72,-.9,.72,*offset)
    try:
        direct,_=render(None,image,transform)
        first,used=render(cache,image,transform);assert not used
        cache.pending[0].result(timeout=2)
        cached,used=render(cache,image,transform);assert used
        assert centroid(cached)==pytest.approx(centroid(direct),abs=.25)
        moved=QTransform(.9,.72,-.9,.72,offset[0]+8.3,offset[1]-4.7)
        cached,used=render(cache,image,moved);assert used
        direct,_=render(None,image,moved)
        assert centroid(cached)==pytest.approx(centroid(direct),abs=.25)
    finally:cache.close()


def test_zoom_and_new_instance_images_do_not_reuse_an_old_raster():
    cache=TerrainRasterCache();image=source_image();transform=QTransform(.9,.72,-.9,.72,140,30)
    try:
        render(cache,image,transform);cache.pending[0].result(timeout=2)
        assert render(cache,image,transform)[1]
        zoomed=QTransform(1.1,.8,-1.1,.8,140,30)
        assert not render(cache,image,zoomed)[1]
        cache.pending[0].result(timeout=2)
        assert render(cache,image,zoomed)[1]
        replacement=source_image()
        assert replacement.cacheKey()!=image.cacheKey()
        assert not render(cache,replacement,zoomed)[1]
    finally:cache.close()


def test_cleared_pending_raster_is_rejected_and_large_requests_stay_bounded():
    cache=TerrainRasterCache();image=source_image();transform=QTransform(.9,.72,-.9,.72,140,30)
    try:
        render(cache,image,transform);cache.pending[0].result(timeout=2)
        cache.clear();assert cache.ready is None and cache.pending is None
        output=QImage(32,32,QImage.Format.Format_ARGB32_Premultiplied);output.fill(0)
        painter=QPainter(output)
        assert not cache.paint(painter,image,transform,(0,0,10000,10000))
        painter.end();assert cache.pending is None
    finally:cache.close()


def test_live_deferred_renderer_does_not_do_direct_work_on_cache_miss():
    cache=TerrainRasterCache(defer=True);image=source_image();transform=QTransform(.9,.72,-.9,.72,140,30)
    try:
        first,handled=render(cache,image,transform)
        assert handled and cache.pending is not None
        assert not np.frombuffer(first.constBits(),np.uint8).any()
        cache.pending[0].result(timeout=2)
        ready,handled=render(cache,image,transform)
        assert handled and np.frombuffer(ready.constBits(),np.uint8).any()
    finally:cache.close()
