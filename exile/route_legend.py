from exile.theme import panel_frame
"""Small non-activating, draggable destination legend; only this box takes clicks."""
from PySide6.QtCore import Qt,QPoint,QRect,QRectF,QPointF,QLineF,Signal,QTimer
from exile.platform import alt_down
from PySide6.QtGui import QColor,QFont,QPainter,QPen
from PySide6.QtWidgets import QWidget


def legend_height(rows,settings):
    font=settings.get('legend_font',11)
    return 30+len(rows)*(font+10) if rows else 56


def paint_legend(p,rect,rows,settings):
    p.save()
    rect=QRectF(rect)
    background=QColor('#11110e');background.setAlpha(round(settings.get('legend_opacity',85)*2.55))
    p.setBrush(background);p.setPen(QPen(QColor('#74654c'),1))
    panel_frame(p,rect,settings.get('legend_opacity',85)/100)
    font=QFont('Georgia');font.setPixelSize(settings.get('legend_font',11));p.setFont(font)
    title='Routes · updating' if any(row.get('status') in ('Calculating…','Recalculating…') for row in rows) else 'Routes'
    p.setPen(QColor('#d9bd86'));p.drawText(QPointF(rect.left()+11,rect.top()+17),title)
    body=QFont('Segoe UI');body.setPixelSize(settings.get('legend_font',11));p.setFont(body)
    p.setPen(QPen(QColor('#9b8a6c'),1))
    if settings.get('_editing'):
        for offset in (0,4,8):p.drawLine(QLineF(rect.right()-24,rect.top()+10+offset,rect.right()-12,rect.top()+10+offset))
    y=rect.top()+35
    if not rows:
        p.setPen(QColor('#9b8e78'));p.drawText(QPointF(rect.left()+11,y),'No known destinations')
    for row in rows:
        p.setPen(QPen(QColor(row['color']),3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        p.drawLine(QLineF(rect.left()+11,y-4,rect.left()+23,y-4))
        p.setPen(QColor('#dce1e8'))
        text=p.fontMetrics().elidedText(row['name'],Qt.TextElideMode.ElideRight,max(1,int(rect.width()-44)))
        p.drawText(QPointF(rect.left()+32,y),text)
        y+=settings.get('legend_font',11)+10
        if row.get('status'):
            p.setPen(QColor('#8e99ab'));p.drawText(QPointF(rect.right()-16,y-settings.get('legend_font',11)-10),'·')
    p.restore()


class RouteLegend(QWidget):
    moved=Signal(float,float)
    resized=Signal(int,int)
    def __init__(self):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|
                         Qt.WindowType.Tool|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.rows=[];self.settings={};self.dragging=False;self.resizing=False;self.locked=False
        self.setMouseTracking(True)
        self.client=QRect()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.editing=False
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput,True)
        self.edit_timer=QTimer(self);self.edit_timer.timeout.connect(self.sync_edit);self.edit_timer.start(20)

    def sync_edit(self):
        editing=alt_down()and not self.locked
        if editing==self.editing:return
        if not editing and (self.dragging or self.resizing):
            if self.resizing:self.resized.emit(self.width(),self.height())
            self.moved.emit(*self.normalized_position());self.dragging=False;self.resizing=False
        self.editing=editing;visible=self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput,not editing)
        if visible:self.show()
        self.update()

    def present(self,window,mark):
        if mark is None or (not window.foreground and not self.dragging) or window.width<=0:
            self.hide();return
        payload=mark.payload;rows=payload['rows'];settings=payload['settings']
        locked=bool(settings.get('legend_locked'))
        self.locked=locked;self.sync_edit()
        ratio=self.screen().devicePixelRatio() if self.screen() else 1
        self.client=QRect(round(window.x/ratio),round(window.y/ratio),round(window.width/ratio),round(window.height/ratio))
        width,height=settings.get('legend_size')or [settings['legend_width'],legend_height(rows,settings)]
        if self.resizing:width,height=self.width(),self.height()
        if (self.width(),self.height())!=(width,height):self.resize(width,height)
        if not self.dragging and not self.resizing:
            available_x=max(0,self.client.width()-width);available_y=max(0,self.client.height()-height)
            position=settings.get('legend_position',[])
            if settings.get('legend_anchor')=='Custom position' and len(position)==2:
                x,y=round(available_x*max(0,min(1,position[0]))),round(available_y*max(0,min(1,position[1])))
            else:x,y=max(0,available_x-22),min(22,available_y)
            point=self.client.topLeft()+QPoint(x,y)
            if self.pos()!=point:self.move(point)
        changed=rows!=self.rows or settings!=self.settings
        self.rows,self.settings=rows,settings
        self.setToolTip('\n'.join(row['name']+(' — '+row['status'] if row.get('status') else '') for row in rows)+('\nDrag to move' if not locked else ''))
        if not self.isVisible():self.show()
        if changed:self.update()

    def paintEvent(self,_):
        painter=QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(),Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_legend(painter,self.rect(),self.rows,dict(self.settings,_editing=self.editing))
        self.paint_grip(painter)

    def resize_summary(self,width,height):
        width=max(60,min(round(width),max(60,self.client.right()-self.x()+1)))
        height=max(32,min(round(height),max(32,self.client.bottom()-self.y()+1)))
        self.resize(width,height);self.update()

    def paint_grip(self,painter):
        if self.editing:
            painter.setPen(QColor('#a28a60'))
            for inset in (5,9,13):painter.drawLine(self.width()-inset,self.height()-5,self.width()-5,self.height()-inset)

    def mousePressEvent(self,event):
        self.sync_edit()
        if event.button()==Qt.MouseButton.LeftButton and self.editing:
            if hasattr(self,'resize_summary')and event.position().x()>=self.width()-18 and event.position().y()>=self.height()-18:
                self.resizing=True;self.resize_origin=event.globalPosition().toPoint();self.resize_start=self.size();event.accept();return
            self.dragging=True;self.offset=event.globalPosition().toPoint()-self.pos();event.accept()

    def mouseMoveEvent(self,event):
        if self.resizing:
            delta=event.globalPosition().toPoint()-self.resize_origin
            self.resize_summary(self.resize_start.width()+delta.x(),self.resize_start.height()+delta.y());event.accept();return
        corner=hasattr(self,'resize_summary')and event.position().x()>=self.width()-18 and event.position().y()>=self.height()-18
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if corner and self.editing else Qt.CursorShape.SizeAllCursor)
        if self.dragging:
            point=event.globalPosition().toPoint()-self.offset
            x=max(self.client.left(),min(point.x(),self.client.left()+max(0,self.client.width()-self.width())))
            y=max(self.client.top(),min(point.y(),self.client.top()+max(0,self.client.height()-self.height())))
            self.move(x,y);event.accept()

    def mouseReleaseEvent(self,event):
        if self.resizing and event.button()==Qt.MouseButton.LeftButton:
            self.resizing=False
            self.resized.emit(self.width(),self.height())
            self.moved.emit(*self.normalized_position());event.accept();return
        if self.dragging and event.button()==Qt.MouseButton.LeftButton:
            self.dragging=False
            x=(self.x()-self.client.x())/max(1,self.client.width()-self.width())
            y=(self.y()-self.client.y())/max(1,self.client.height()-self.height())
            self.moved.emit(max(0,min(1,x)),max(0,min(1,y)));event.accept()

    def normalized_position(self):
        x=(self.x()-self.client.x())/max(1,self.client.width()-self.width())
        y=(self.y()-self.client.y())/max(1,self.client.height()-self.height())
        return max(0,min(1,x)),max(0,min(1,y))

    def hideEvent(self,event):
        self.dragging=False;self.resizing=False
        super().hideEvent(event)
