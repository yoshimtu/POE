"""Waymark's iron, brass and ivory desktop/overlay presentation."""
import math
from functools import lru_cache
from PySide6.QtCore import Qt,QRectF,QPointF,QSize
from PySide6.QtGui import QColor,QPainter,QPen,QPixmap,QIcon,QFont,QPainterPath,QImage,QBrush
from PySide6.QtWidgets import QFrame,QHBoxLayout,QLabel,QPushButton,QWidget,QSizePolicy
from exile.storage import resource_root

INK='#10100f';BRASS='#77603c';IVORY='#e2d7bf';MUTED='#958b78'

def skin_path(name):
    return (resource_root() / 'assets' / 'skin' / name).as_posix()

@lru_cache(maxsize=48)
def skin_image(name):
    return QImage(skin_path(name))

def nine_slice(p, rect, source, inset=28, edge=18, center=True):
    """Keep the corners and grain sharp instead of stretching a whole screenshot."""
    r=QRectF(rect);w,h=source.width(),source.height()
    e=min(edge,r.width()/2,r.height()/2)
    xs=(0,inset,w-inset,w);ys=(0,inset,h-inset,h)
    dx=(r.left(),r.left()+e,r.right()-e,r.right());dy=(r.top(),r.top()+e,r.bottom()-e,r.bottom())
    for y in range(3):
        for x in range(3):
            if not center and x==y==1:continue
            p.drawImage(QRectF(dx[x],dy[y],dx[x+1]-dx[x],dy[y+1]-dy[y]),source,
                QRectF(xs[x],ys[y],xs[x+1]-xs[x],ys[y+1]-ys[y]))

@lru_cache(maxsize=24)
def panel_image(width,height):
    image=QImage(width,height,QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
    p=QPainter(image);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.fillRect(0,0,width,height,QBrush(skin_image('texture.png')))
    p.fillRect(0,0,width,height,QColor(8,9,9,95))
    p.setOpacity(.72)
    nine_slice(p,QRectF(0,0,width,height),skin_image('panel.png'),center=False)
    p.end();return image

def panel_frame(p,rect,opacity=1.,fill=True):
    r=QRectF(rect)
    if r.width()<=0 or r.height()<=0:return
    p.save();p.setOpacity(p.opacity()*max(0,min(1,opacity)))
    if fill:p.drawImage(r,panel_image(round(r.width()),round(r.height())))
    else:nine_slice(p,r,skin_image('panel.png'),center=False)
    p.restore()

class BrassFrame(QFrame):
    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self);panel_frame(p,self.rect())


class WindowFrame(BrassFrame):
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and not self.window().isMaximized():
            pos=event.position();edges=Qt.Edge(0)
            if pos.x()<7:edges|=Qt.Edge.LeftEdge
            if pos.x()>self.width()-7:edges|=Qt.Edge.RightEdge
            if pos.y()<7:edges|=Qt.Edge.TopEdge
            if pos.y()>self.height()-7:edges|=Qt.Edge.BottomEdge
            if edges and self.window().windowHandle():
                self.window().windowHandle().startSystemResize(edges);event.accept();return
        super().mousePressEvent(event)


class TitleBar(QWidget):
    def __init__(self,parent):
        super().__init__(parent);self.setFixedHeight(29)
        row=QHBoxLayout(self);row.setContentsMargins(7,0,0,0);row.setSpacing(4)
        icon=QLabel();icon.setPixmap(emblem(size=18).pixmap(18,18));row.addWidget(icon)
        text=QLabel('Waymark');text.setObjectName('windowTitle');row.addWidget(text);row.addStretch()
        for text,tip,fn in [('—','Minimize',parent.showMinimized),('□','Maximize / restore',self.toggle_maximized),('×','Close',parent.close)]:
            b=QPushButton(text);b.setObjectName('windowControl');b.setFixedSize(32,25)
            b.setToolTip(tip);b.setAccessibleName(tip);b.clicked.connect(fn);row.addWidget(b)

    def toggle_maximized(self):
        w=self.window();w.showNormal()if w.isMaximized()else w.showMaximized()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.toggle_maximized()


def emblem(name='compass',size=28):
    asset=skin_image('icon-'+name+'.png')
    if not asset.isNull():return QIcon(QPixmap.fromImage(asset))
    image=QPixmap(size,size);image.fill(Qt.GlobalColor.transparent)
    p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.scale(size/32,size/32)
    p.setPen(QPen(QColor('#bca277'),1.25));p.setBrush(Qt.BrushStyle.NoBrush)
    if name in ('compass','routes'):
        p.drawEllipse(QRectF(5,5,22,22));p.drawEllipse(QRectF(12,12,8,8))
        for a in range(0,360,45):
            x,y=math.cos(math.radians(a)),math.sin(math.radians(a))
            p.drawLine(QPointF(16+x*10,16+y*10),QPointF(16+x*15,16+y*15))
        path=QPainterPath();path.moveTo(16,3);path.lineTo(19,16);path.lineTo(16,29);path.lineTo(13,16);path.closeSubpath();p.drawPath(path)
    elif name in ('map','modules'):
        path=QPainterPath();path.moveTo(4,8);path.lineTo(12,5);path.lineTo(21,9);path.lineTo(28,5);path.lineTo(28,25);path.lineTo(21,28);path.lineTo(12,24);path.lineTo(4,27);path.closeSubpath();p.drawPath(path)
        p.drawLine(12,5,12,24);p.drawLine(21,9,21,28)
    elif name in ('search','stash'):
        p.drawEllipse(QRectF(5,4,17,17));p.drawLine(20,20,28,28)
    elif name in ('book','history','workshop'):
        p.drawRect(QRectF(6,4,20,24));p.drawLine(10,4,10,28)
        for y in (10,15,20):p.drawLine(14,y,22,y)
    elif name=='cog':
        p.drawEllipse(QRectF(9,9,14,14));p.drawEllipse(QRectF(13,13,6,6))
        for a in range(0,360,45):
            x,y=math.cos(math.radians(a)),math.sin(math.radians(a));p.drawLine(QPointF(16+x*7,16+y*7),QPointF(16+x*11,16+y*11))
    elif name=='alerts':
        path=QPainterPath();path.moveTo(7,23);path.lineTo(10,18);path.lineTo(10,12);path.cubicTo(10,4,22,4,22,12);path.lineTo(22,18);path.lineTo(25,23);path.closeSubpath();p.drawPath(path);p.drawEllipse(QRectF(14,25,4,3))
    elif name=='hourglass':
        p.drawLine(7,4,25,4);p.drawLine(7,28,25,28)
        path=QPainterPath();path.moveTo(10,4);path.lineTo(10,9);path.lineTo(22,23);path.lineTo(22,28);path.moveTo(22,4);path.lineTo(22,9);path.lineTo(10,23);path.lineTo(10,28);p.drawPath(path)
    else:
        path=QPainterPath();path.moveTo(16,3);path.lineTo(28,26);path.lineTo(4,26);path.closeSubpath();p.drawPath(path);p.drawLine(16,11,16,19);p.drawEllipse(QRectF(15,22,2,2))
    p.end();return QIcon(image)


def module_icon(identity):
    return emblem({'map_reveal':'map','routes':'routes','preload':'alerts','uptime':'hourglass',
                   'radar':'radar','pricing':'stash','hazards':'hazards','workshop':'workshop'}.get(identity,'history'))


def skin_stylesheet():
    """Real Qt controls using raster skins, retaining focus, keys and accessibility."""
    def image(name):return 'url("'+skin_path(name+'.png')+'")'
    def border(name):return f'border-image:{image(name)} 4 4 4 4 stretch stretch; border-width:4px;'
    return f'''
    * {{font-family:Georgia;font-size:12px;}}
    QWidget {{background:transparent;}}
    QMainWindow,QDialog {{background:#10100f;}}
    QLabel {{background:transparent;}}
    QLabel#title {{font-family:Georgia;font-size:20px;}}
    QLabel#windowTitle {{font-family:Georgia;font-size:12px;color:#d1c5af;}}
    QLabel#eyebrow {{font-family:Georgia;font-size:12px;letter-spacing:1px;color:#d1bd95;}}
    QLabel#muted {{font-family:'Segoe UI';font-size:11px;color:#a29a8b;}}
    QFrame#status {{background:transparent;border:0;border-top:1px solid #3d3426;}}
    QFrame#rail {{background:transparent;border:0;}}
    QFrame#card {{background-image:{image('texture')};border:1px solid #554631;}}
    QFrame#moduleRow {{background:transparent;border:0;border-bottom:1px solid #343024;}}
    QFrame#moduleRow[selected="true"] {{{border('row-active')}background:transparent;}}
    QPushButton {{{border('button-normal')}background:transparent;padding:3px 8px;font-family:Georgia;}}
    QPushButton:hover {{{border('button-active')}}}
    QPushButton:pressed {{{border('button-pressed')}}}
    QPushButton:focus {{color:#fff0cd;}}
    QPushButton:disabled {{{border('button-pressed')}color:#766e60;}}
    QPushButton#moduleSelect {{border:0;border-image:none;background:transparent;padding:3px 0;font-size:12px;}}
    QPushButton#nav {{border:0;border-image:none;background:transparent;padding:12px 6px;font-family:Georgia;font-size:11px;}}
    QPushButton#nav:checked {{{border('row-active')}color:#ead6ad;padding:8px 2px;}}
    QPushButton#cog {{{border('field-normal')}padding:0;}}
    QPushButton#windowControl {{border:0;border-image:none;background:transparent;padding:0;font:14px 'Segoe UI';}}
    QPushButton#windowControl:hover {{background:#392e21;}}
    QLineEdit,QTextEdit,QPlainTextEdit,QComboBox,QSpinBox {{{border('field-normal')}background:transparent;padding:2px 5px;min-height:18px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus {{{border('field-active')}}}
    QSpinBox {{max-width:150px;}}
    QComboBox {{min-width:125px;}}
    QComboBox::drop-down {{border:0;width:19px;}}
    QComboBox::down-arrow {{image:{image('arrow-down')};width:12px;height:12px;}}
    QSpinBox::up-button {{subcontrol-origin:border;subcontrol-position:top right;width:16px;border:0;}}
    QSpinBox::down-button {{subcontrol-origin:border;subcontrol-position:bottom right;width:16px;border:0;}}
    QSpinBox::up-arrow {{image:{image('arrow-up')};width:10px;height:10px;}}
    QSpinBox::down-arrow {{image:{image('arrow-down')};width:10px;height:10px;}}
    QScrollArea,QScrollArea > QWidget > QWidget {{background:transparent;border:0;}}
    QTabWidget::pane {{background:transparent;border:0;}}
    QTabBar::tab {{{border('tab-normal')}background:transparent;padding:4px 6px;font-size:11px;}}
    QTabBar::tab:selected {{{border('tab-active')}color:#efdbb8;}}
    QCheckBox {{spacing:6px;}}
    QCheckBox::indicator {{width:14px;height:14px;border:0;background:transparent;image:{image('check-off')};}}
    QCheckBox::indicator:checked {{border:0;background:transparent;image:{image('check-on')};}}
    QCheckBox::indicator:focus {{border:1px solid #cab486;}}
    QScrollBar:vertical {{background:transparent;width:6px;}}
    QScrollBar::handle:vertical {{background:#6b5941;min-height:30px;}}
    QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:transparent;}}
    QSlider::groove:horizontal {{height:2px;background:#5a4831;}}
    QSlider::sub-page:horizontal {{background:#ad895a;}}
    QSlider::handle:horizontal {{width:8px;margin:-3px 0;background:#c1a278;border:1px solid #705638;border-radius:4px;}}
    '''
