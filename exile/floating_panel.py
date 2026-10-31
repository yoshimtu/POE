"""Draggable and freely resizable alert and uptime panels."""
from PySide6.QtCore import QRectF,Signal,Qt
from exile.route_legend import RouteLegend
from exile.preload_panel import paint_preloads,panel_height
from exile.model import Mark


class FloatingPanel(RouteLegend):
    excluded=Signal(str)
    def present(self,window,mark):
        if mark is None:
            self.hide();return
        payload=mark.payload;changed=getattr(self,'payload',None)!=payload;self.payload=payload
        settings=payload['settings'];width=settings.get('width',320)
        height=panel_height(payload['rows'],settings,payload.get('overflow',0))
        ratio=self.screen().devicePixelRatio()if self.screen()else 1
        size=settings.get('overlay_size')or [width,height]
        position=settings.get('overlay_position')or [mark.x/max(1,window.width/ratio-size[0]),mark.y/max(1,window.height/ratio-size[1])]
        translated=dict(legend_width=width,legend_size=size,legend_locked=settings.get('overlay_locked',False),
            legend_anchor='Custom position',legend_position=position)
        super().present(window,Mark('route_legend',0,0,payload=dict(rows=[dict(name=r['label'],color=r['color'],status='')for r in payload['rows']],settings=translated)))
        if changed:self.update()

    def paintEvent(self,event):
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import Qt
        p=QPainter(self);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(),Qt.GlobalColor.transparent);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        settings=dict(self.payload['settings'],width=self.width(),_panel_height=self.height())
        paint_preloads(p,0,0,self.payload['rows'],settings,self.payload.get('overflow',0),
            title='BUFF UPTIME'if self.payload.get('uptime')else'INSTANCE ALERTS')
        if self.editing and self.payload.get('uptime'):
            from PySide6.QtGui import QColor
            p.setPen(QColor('#dbc59f'))
            for index,row in enumerate(self.payload['rows']):
                p.drawText(QRectF(self.width()-27,29+index*(settings.get('font_size',12)+10),20,20),Qt.AlignmentFlag.AlignCenter,'×')
        self.paint_grip(p)

    def mousePressEvent(self,event):
        self.sync_edit()
        if self.editing and self.payload.get('uptime')and event.button()==Qt.MouseButton.LeftButton and event.position().x()>=self.width()-27:
            index=int((event.position().y()-29)//(self.payload['settings'].get('font_size',12)+10))
            if 0<=index<len(self.payload['rows']):
                self.excluded.emit(self.payload['rows'][index]['buff_key']);event.accept();return
        super().mousePressEvent(event)
