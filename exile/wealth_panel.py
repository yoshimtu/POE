from exile.theme import panel_frame
"""Small in-slot price badges and a compact container-value panel."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QFont,QColor,QPen,QImage,QFontMetrics
from functools import lru_cache
import math
from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QPainter
from exile.route_legend import RouteLegend


def _draw_item_price(p,rect,text,color,font_size=10):
    p.save();rect=QRectF(rect);rect.adjust(1,1,-1,-1)
    if rect.width()<8 or rect.height()<8:p.restore();return
    p.setClipRect(rect)
    font=QFont('Segoe UI');font.setPixelSize(font_size);p.setFont(font)
    while p.fontMetrics().horizontalAdvance(text)>rect.width()-4 and font.pixelSize()>7:
        font.setPixelSize(font.pixelSize()-1);p.setFont(font)
    lines=[text]
    if p.fontMetrics().horizontalAdvance(text)>rect.width()-4 and '–'in text:
        first,last=text.split('–',1);lines=[first,'–'+last]
    width=min(rect.width(),max(p.fontMetrics().horizontalAdvance(s)for s in lines)+4)
    height=min(rect.height(),(font.pixelSize()+2)*len(lines)+2)
    box=QRectF(rect.right()-width,rect.top(),width,height)
    p.fillRect(box,QColor(13,17,24,225));p.setPen(QColor(color))
    for index,line in enumerate(lines):
        p.drawText(QRectF(box.left()+1,box.top()+index*(font.pixelSize()+2),box.width()-2,font.pixelSize()+3),
            Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,line)
    p.restore()


@lru_cache(maxsize=128)
def _badge_image(width,height,text,color,font_size,ratio):
    image=QImage(max(1,math.ceil(width*ratio)),max(1,math.ceil(height*ratio)),QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio);image.fill(Qt.GlobalColor.transparent)
    painter=QPainter(image)
    _draw_item_price(painter,QRectF(0,0,width,height),text,color,font_size)
    painter.end()
    return image


def paint_item_price(p,rect,text,color,font_size=10):
    rect=QRectF(rect)
    if rect.width()*rect.height()>100000:
        _draw_item_price(p,rect,text,color,font_size);return
    ratio=p.device().devicePixelRatioF()
    image=_badge_image(round(rect.width(),2),round(rect.height(),2),text,color,font_size,ratio)
    p.save();p.setClipRect(rect);p.drawImage(rect.topLeft(),image);p.restore()


def section_height(section,font_size):
    return 34+len(section['top'])*(font_size+9)


def wealth_rows(section,size,width):
    font=QFont('Segoe UI');font.setPixelSize(size);metrics=QFontMetrics(font)
    result=[]
    for row in section['top']:
        name=row['name']+(f" ×{row['quantity']:,}"if row['quantity']>1 else '')
        price_width=metrics.horizontalAdvance(row['price_label'])+10
        available=max(35,width-price_width-36)
        bounds=metrics.boundingRect(QRectF(0,0,available,1000).toRect(),int(Qt.TextFlag.TextWordWrap|Qt.TextFlag.TextWrapAnywhere),name)
        result.append((name,price_width,available,max(size+9,bounds.height()+5)))
    return result


def compact_height(section,size,width):
    return 38+sum(row[3]for row in wealth_rows(section,size,width))


def paint_wealth(p,x,y,sections,settings):
    p.save();width=settings['summary_width'];size=settings['summary_font']
    height=settings.get('_panel_height')or sum(compact_height(s,size,width)for s in sections)
    background=QColor('#11110e');background.setAlpha(round(settings['summary_opacity']*2.55))
    rect=QRectF(x,y,width,height);p.setBrush(background);p.setPen(QPen(QColor('#746448'),1))
    panel_frame(p,rect,settings['summary_opacity']/100);p.setClipRect(rect.adjusted(2,2,-2,-2))
    top=y+8
    for index,section in enumerate(sections):
        if index:p.setPen(QColor('#453923'));p.drawLine(QPointF(x+12,top-3),QPointF(x+width-12,top-3))
        font=QFont('Georgia');font.setPixelSize(size);font.setBold(True);p.setFont(font)
        value=section['total_label'];value_width=p.fontMetrics().horizontalAdvance(value)+10
        inset=12 if settings.get('summary_locked')else 26
        if inset==26:
            p.setPen(QPen(QColor('#8f8169'),1))
            for offset in (0,3,6):p.drawLine(QPointF(x+11,top+7+offset),QPointF(x+17,top+7+offset))
        title=p.fontMetrics().elidedText(section['title'],Qt.TextElideMode.ElideRight,max(40,width-value_width-inset-18))
        p.setPen(QColor('#d6bd8b'));p.drawText(QRectF(x+inset,top,width-value_width-inset-12,22),Qt.AlignmentFlag.AlignVCenter,title)
        p.drawText(QRectF(x+width-value_width-12,top,value_width,22),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,value)
        top+=25;font.setFamily('Segoe UI');font.setBold(False);p.setFont(font)
        for row,(name,price_width,name_width,row_height) in zip(section['top'],wealth_rows(section,size,width)):
            price=row['price_label']
            p.setPen(QColor('#c9bda4'));p.drawText(QRectF(x+12,top,name_width,row_height),int(Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap|Qt.TextFlag.TextWrapAnywhere),name)
            p.setPen(QColor('#cfb781'));p.drawText(QRectF(x+width-price_width-12,top,price_width,size+7),
                Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,price)
            top+=row_height
        top+=8
    p.restore()


class WealthWindow(RouteLegend):
    """Independent, non-activating summary with persistent per-scope position."""
    def __init__(self,scope):
        super().__init__()
        self.scope=scope;self.sections=[];self.requested_size=None;self.base_settings={}

    def resize_summary(self,width,height):
        width=max(60,min(round(width),max(60,self.client.right()-self.x()+1)))
        height=max(32,min(round(height),max(32,self.client.bottom()-self.y()+1)))
        settings=dict(self.base_settings);size=settings['summary_font']
        self.requested_size=[width,height]
        settings.update(summary_width=width,summary_font=size,_panel_height=height)
        changed=self.settings!=settings or (self.width(),self.height())!=(width,height)
        self.settings=settings
        if (self.width(),self.height())!=(width,height):self.resize(width,height)
        if changed:self.update()

    def present_summary(self,window,section,settings,default_y):
        if section is None or (not window.foreground and not self.dragging)or window.width<=0:
            self.hide();return
        locked=bool(settings.get('summary_locked'))
        self.locked=locked;self.sync_edit()
        ratio=self.screen().devicePixelRatio()if self.screen()else 1
        self.client=QRect(round(window.x/ratio),round(window.y/ratio),round(window.width/ratio),round(window.height/ratio))
        previous=self.sections;self.sections=[section];self.base_settings=dict(settings)
        saved=settings.get('summary_sizes',{}).get(self.scope)
        if not self.resizing:
            size=saved if isinstance(saved,(list,tuple))and len(saved)==2 else [settings['summary_width'],compact_height(section,settings['summary_font'],settings['summary_width'])]
            self.resize_summary(*size)
        width,height=self.width(),self.height()
        if not self.dragging and not self.resizing:
            position=settings.get('summary_positions',{}).get(self.scope)
            if isinstance(position,(list,tuple))and len(position)==2:
                x,y=round(self.client.width()*position[0]),round(self.client.height()*position[1])
            else:
                x=(self.client.width()-width)//2 if settings['summary_anchor']=='Top centre'else settings['summary_x']
                y=default_y
            x=max(0,min(x,max(0,self.client.width()-width)));y=max(0,min(y,max(0,self.client.height()-height)))
            point=self.client.topLeft()+QPoint(x,y)
            if point!=self.pos():self.move(point)
        changed=previous!=[section]
        self.setToolTip('Drag to move · drag bottom-right corner to resize · size and position saved'if not locked else'Position and size locked · change in pricing settings')
        if not self.isVisible():self.show()
        if changed:self.update()

    def paintEvent(self,_):
        painter=QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(),Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.sections:paint_wealth(painter,0,0,self.sections,dict(self.settings,summary_locked=not self.editing))
        if self.editing:
            painter.setPen(QColor('#a28a60'))
            for inset in (5,9,13):painter.drawLine(self.width()-inset,self.height()-5,self.width()-5,self.height()-inset)

    def mouseReleaseEvent(self,event):
        if self.resizing:
            super().mouseReleaseEvent(event);return
        if self.dragging and event.button()==Qt.MouseButton.LeftButton:
            self.dragging=False
            # Normalize the top-left against the client, so changing top-three
            # row counts doesn't shift a saved position when the panel reopens.
            x=(self.x()-self.client.x())/max(1,self.client.width())
            y=(self.y()-self.client.y())/max(1,self.client.height())
            self.moved.emit(max(0,min(1,x)),max(0,min(1,y)));event.accept()

    def normalized_position(self):
        x=(self.x()-self.client.x())/max(1,self.client.width())
        y=(self.y()-self.client.y())/max(1,self.client.height())
        return max(0,min(1,x)),max(0,min(1,y))
