from concurrent.futures import ThreadPoolExecutor
from PySide6.QtGui import QImage
from exile.model import Mark, Plugin
from exile.mapview import map_point, map_clip, outline_rows
from exile.terrain import height_correct_outline


def build_image(grid,heights,line_width,color_name):
    rows=outline_rows(grid,line_width)
    mask,origin=height_correct_outline(rows,heights)
    h,w=mask.shape;stride=(w+3)&~3
    pixels=b''.join(row.tobytes()+bytes(stride-w)for row in mask)
    indexed=QImage(pixels,w,h,stride,QImage.Format.Format_Indexed8).copy()
    color=0xb49c72 if color_name=='Muted gold'else 0xa6b0bd
    indexed.setColorTable([(alpha<<24)|color for alpha in range(256)])
    return indexed.convertToFormat(QImage.Format.Format_RGBA8888),origin


class MapReveal(Plugin):
    id, name, category = "map_reveal", "Full map reveal", "Navigation"
    description = "Thin terrain outlines aligned to PoE’s visible map or minimap."
    requires = {"terrain"}
    defaults = {"zoom": 100, "opacity": 55, "line_width": 2, "color": "Muted gold", "hide_native": True, "native_margin": 6,"refresh_rate":"120 fps"}
    fields = {"zoom": ("Alignment scale % (100 matches native map)", "int", 25, 300),
              "opacity": ("Outline opacity %", "int", 10, 90),
              "line_width": ("Outline width (terrain cells)", "int", 1, 4),
              "color": ("Outline color", "choice", ["Muted gold", "Soft grey"]),
              "hide_native": ("Hide added lines where PoE's map is already visible", "bool"),
              "native_margin": ("Native-line clearance (pixels)", "int", 2, 12),
              "refresh_rate":("Overlay drawing rate","choice",['60 fps','90 fps','120 fps','144 fps'])}

    def __init__(self):
        super().__init__()
        self.cache_key = None
        self.image = None
        self.image_origin = (0, 0)
        self.pool=None;self.pending=None;self.identity=None

    def tick(self, snapshot, ctx):
        if not snapshot.grid or (snapshot.source == 'live' and not snapshot.map_transform):
            return []
        height, width = len(snapshot.grid), len(snapshot.grid[0])
        if height > 8192 or width > 8192 or width * height > 32_000_000 or any(len(row) != width for row in snapshot.grid):
            raise ValueError("Invalid terrain dimensions")
        key = (id(snapshot.grid), id(snapshot.terrain_heights), self.settings['line_width'], self.settings['color'])
        if key != self.cache_key:
            if snapshot.source!='live':
                self.image,self.image_origin=build_image(snapshot.grid,snapshot.terrain_heights,self.settings['line_width'],self.settings['color']);self.cache_key=key
            else:
                identity=(id(snapshot.grid),id(snapshot.terrain_heights))
                if identity!=self.identity:self.image=None;self.identity=identity
                if self.pending and self.pending[0].done():
                    future,pending_key=self.pending;self.pending=None
                    image,origin=future.result()
                    if pending_key==key:self.image,self.image_origin,self.cache_key=image,origin,key
                if self.cache_key!=key and self.pending is None:
                    if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='map-outline')
                    self.pending=(self.pool.submit(build_image,snapshot.grid,snapshot.terrain_heights,self.settings['line_width'],self.settings['color']),key)
        if self.image is None:return []
        ox, oy = self.image_origin
        iw, ih = self.image.width(), self.image.height()
        corners = [map_point(snapshot, point, self.settings['zoom'], adjusted=True) for point in ((ox, oy), (ox + iw, oy), (ox + iw, oy + ih), (ox, oy + ih))]
        return [Mark('terrain', *corners[0], value=self.settings['opacity'] / 100,
                     points=corners, clip=map_clip(snapshot), payload=self.image,
                     exclusion=getattr(ctx, 'native_mask', lambda _s: None)(snapshot) if self.settings['hide_native'] else None)]

    def stop(self):
        if self.pending:self.pending[0].cancel()
        self.pending=None;self.cache_key=None;self.image=None;self.identity=None
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True);self.pool=None


def create_plugin():
    return MapReveal()
