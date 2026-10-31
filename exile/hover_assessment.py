"""Hovered rare assessment UI. Never copies text or sends game input."""
from functools import lru_cache
import re

from PySide6.QtCore import Qt, QRect,QTimer,Signal,QEvent
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QScrollArea,QSizeGrip,QLayout

from exile.items import item_from_hover,rate_rare
from exile.theme import panel_frame
from exile.platform import alt_down
from PySide6.QtGui import QPainter


def hotkey_parts(text):
    parts=[p.strip().upper()for p in text.split('+')]
    modifiers={'ALT':1,'CTRL':2,'CONTROL':2,'SHIFT':4}
    if not parts or not parts[-1]:raise ValueError('Enter a shortcut such as Alt+F.')
    flags=0
    for part in parts[:-1]:
        if part not in modifiers:raise ValueError('Use Alt, Ctrl or Shift with a letter, number or F1–F12.')
        flags|=modifiers[part]
    key=parts[-1]
    if len(key)==1 and key in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':vk=ord(key)
    elif re.fullmatch(r'F(?:[1-9]|1[0-2])',key):vk=0x70+int(key[1:])-1
    else:raise ValueError('Use a letter, number or F1–F12 for the shortcut.')
    if not flags:raise ValueError('Include Alt, Ctrl or Shift so ordinary game keys are not intercepted.')
    return flags|0x4000,vk


@lru_cache(maxsize=128)
def assess_hover(name,base,metadata,links,sockets,rows,archetype):
    item=item_from_hover(dict(name=name,base=base,metadata=metadata,links=links,sockets=sockets,tooltip_rows=rows))
    return item,rate_rare(item,archetype)


def assess_data(data,archetype):
    return assess_hover(data['name'],data['base'],data.get('metadata',''),data.get('links',0),
                        data.get('sockets',0),tuple(data.get('tooltip_rows',[])),archetype)


def panel_position(client,tooltip,width,height):
    x,y,w,h=tooltip
    right=x+w+10;left=x-width-10
    px=right if right+width<=client.width()else left if left>=0 else max(0,client.width()-width-8)
    py=max(4,min(y,client.height()-height-4))
    return client.x()+round(max(0,px)),client.y()+round(py)


class HoverAssessment(QWidget):
    size_saved=Signal(str,int,int)
    feedback=Signal(str)
    archetype_selected=Signal(str)
    def __init__(self):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|
            Qt.WindowType.Tool|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet('QWidget {background:transparent;color:#ddd1b7;font-family:"Segoe UI";font-size:11px;} '
            'QLabel {background:transparent;} QPushButton {padding:2px 6px;}')
        self.setObjectName('rareAssessment')
        self.setStyleSheet(self.styleSheet()+'#rareAssessment {border:1px solid #746448;}')
        layout=QVBoxLayout(self);layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint);layout.setContentsMargins(12,10,12,10);layout.setSpacing(7)
        header=QHBoxLayout();self.title=QLabel();self.title.setStyleSheet('color:#e0c594;font-family:Georgia;font-size:13px;');header.addWidget(self.title,1)
        self.close_button=QPushButton('×');self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.clicked.connect(self.dismiss);header.addWidget(self.close_button)
        layout.addLayout(header);self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.body=QLabel();self.body.setWordWrap(True);self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop);self.scroll.setWidget(self.body);layout.addWidget(self.scroll)
        self.hint=QLabel();self.hint.setWordWrap(True);self.hint.setStyleSheet('color:#988c77;font-size:10px;');layout.addWidget(self.hint)
        self.feedback_notice=QLabel();self.feedback_notice.setStyleSheet('color:#d6bd8b;');self.feedback_notice.hide();layout.addWidget(self.feedback_notice)
        self.feedback_timer=QTimer(self);self.feedback_timer.setSingleShot(True);self.feedback_timer.timeout.connect(self.feedback_notice.hide)
        self.feedback_context=None
        from exile.assessment_controls import controls
        self.feedback_buttons,self.build_button=controls(layout,self.feedback,self.archetype_selected)
        self.expanded=False;self.locked=False;self.pinned=None;self.dismissed=None;self.identity=None;self.signature=None
        self.last_hover=None;self.last_hover_time=0;self.last_hover_area=None
        self.setMinimumSize(60,32)
        self.grip=AssessmentGrip(self);self.grip.setFixedSize(18,18)
        self.grip.hide()
        for child in self.findChildren(QWidget):child.installEventFilter(self)
        self.edit_timer=QTimer(self);self.edit_timer.timeout.connect(self.update_pin_state);self.edit_timer.start(20)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'grip'):self.grip.move(self.width()-18,self.height()-18);self.grip.raise_()

    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);panel_frame(painter,self.rect())

    def eventFilter(self,watched,event):
        if self.expanded and event.type()==QEvent.Type.MouseButtonPress:
            self.locked=True;self.close_button.show();self.signature=None
        return super().eventFilter(watched,event)

    def update_pin_state(self):
        held=alt_down()
        self.grip.setVisible(self.isVisible() and self.expanded and held)
        if self.expanded and not self.locked and not held:self.dismiss()

    def mousePressEvent(self,event):
        if self.expanded:
            self.locked=True;self.close_button.show();self.signature=None
        super().mousePressEvent(event)

    def dismiss(self):
        self.locked=False;self.dismissed=None;self.expanded=False;self.pinned=None;self.signature=None;self.feedback_context=None;self.hide()

    def feedback_saved(self,message):
        self.feedback_notice.setText(message);self.feedback_notice.show();self.feedback_timer.start(2200)

    def nativeEvent(self,event_type,message):
        import os
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            msg=wintypes.MSG.from_address(int(message))
            if msg.message==0x21:return True,3  # WM_MOUSEACTIVATE: keep game focus
        return super().nativeEvent(event_type,message)

    def expand(self,data,settings):
        self.expanded=True;self.locked=False;self.pinned=dict(data);self.dismissed=None;self.signature=None

    def clear(self):
        self.locked=False;self.expanded=False;self.pinned=None;self.dismissed=None;self.signature=None;self.hide()
        self.last_hover=None;self.last_hover_time=0;self.last_hover_area=None
        self.feedback_context=None;self.feedback_timer.stop();self.feedback_notice.hide()

    def recent_hover(self,snapshot):
        import time
        area=(snapshot.area_id,getattr(snapshot,'instance_key',None))
        if self.last_hover_area==area and time.monotonic()-self.last_hover_time<=.35:
            return self.last_hover
        return None

    def present(self,window,snapshot,plugin):
        if not plugin or not plugin.enabled or not plugin.settings.get('rare_enabled',True):
            self.clear();return
        if snapshot.source!='live'or not snapshot.fresh():self.hide();return
        if not snapshot.in_game or snapshot.loading:self.clear();return
        if not window.foreground and not self.locked and not self.build_button.menu().isVisible():self.hide();return
        if not self.expanded and snapshot.hovered_item and snapshot.hovered_item.get('assessment_supported')is False:
            self.clear();return
        if snapshot.hovered_item:
            self.last_hover=dict(snapshot.hovered_item);self.last_hover_time=snapshot.captured_at
            self.last_hover_area=(snapshot.area_id,getattr(snapshot,'instance_key',None))
        if self.pinned and self.pinned.get('_area')!=(snapshot.area_id,getattr(snapshot,'instance_key',None)):
            self.clear()
        data=self.pinned if self.expanded else snapshot.hovered_item or (
            self.last_hover if (self.underMouse()or self.build_button.menu().isVisible())and self.last_hover_area==(snapshot.area_id,getattr(snapshot,'instance_key',None))else self.recent_hover(snapshot))
        if not data or(not self.expanded and plugin.settings['rare_mode']!='Always on'):
            self.hide();return
        self.identity=(data['entity'],data['name'])
        if self.identity==self.dismissed:self.hide();return
        settings=plugin.settings
        try:item,rating=assess_data(data,settings['archetype'])
        except(ValueError,KeyError):self.hide();return
        key=(repr(data),settings['archetype'],self.expanded,settings['rare_hotkey'],settings.get('rare_feedback',True),settings.get('assessment_detail','Simple'),self.locked)
        if key!=self.signature:
            from html import escape
            self.signature=key
            self.feedback_timer.stop();self.feedback_notice.hide()
            self.feedback_context=dict(item=item,rating=rating,preference=settings['archetype'],source='hover',
                                       metadata=data.get('metadata',''),tooltip_rows=tuple(data.get('tooltip_rows',())))
            score=rating.get('score');quality=f'{score:g}/10 quality'if score is not None else'Unrated · review'
            self.title.setText(item.name+'  ·  '+quality)
            coverage=len(rating.get('evaluated',[]))-len(rating['unknown'])
            self.summary.setText(f'{item.base} · {coverage}/{len(item.mods)} modifiers evaluated'+
                (f' · {item.links} links / {item.sockets} sockets'if item.sockets else''))
            details=[]
            assessment=rating.get('assessment',{})
            if assessment:details.append(('<b>Best fit:</b> 'if assessment['selection']=='Automatic'else'<b>Selected profile:</b> ')+escape(assessment['best_fit']))
            crafting=rating.get('crafting',{})
            if crafting.get('open_prefixes')is not None:
                details.append(f"<b>Crafting space:</b> {crafting['open_prefixes']} prefixes / {crafting['open_suffixes']} suffixes open · +{crafting['bonus']:g}")
            for note in rating.get('link_notes',[]):details.append('<b style="color:#e2c990">'+escape(note)+'</b>')
            for metric,value in rating.get('metrics',{}).items():details.append(escape(f'{metric}: {value:g}'))
            synergy=[r.removeprefix('Synergy: ')for r in rating['reasons']if r.startswith('Synergy: ')]
            if synergy:details.append('<b>Works together</b><br>'+ '<br>'.join('• '+escape(line) for line in synergy))
            if self.expanded:
                detailed=settings.get('assessment_detail','Simple')=='Detailed'
                if detailed:
                    affix=rating.get('affix_score');details.append(f'<b>Affix quality:</b> {affix:g}/10'if affix is not None else'<b>Affix quality:</b> unrated')
                if assessment and detailed:
                    details.append(f"1 base + {assessment['base_points']:.2f} modifiers + {assessment['coherence_bonus']:.2f} synergy + {assessment['tier_bonus']:.2f} coherent T1/T2 rolls"+
                                   (' · capped at 10'if assessment['uncapped_score']>10 else''))
                for row in rating.get('evaluated',[]):
                    strength=row['strength'];tier=f" · T{row['tier']}"if row.get('tier')else''
                    roll=row.get('roll_position');roll_note=f' · {round(roll*100)}% within base tier’s roll range'if roll is not None else''
                    detailed=settings.get('assessment_detail','Simple')=='Detailed'
                    effect=(f"{round(strength*100)}% of reference · {row['impact']}"if strength is not None else'Not scored · review this modifier')
                    points=('+%.2f points'%row.get('contribution',0)) if strength is not None else 'Not scored'
                    heading=escape(row['mod']+(tier if not detailed else ''))
                    block='<table width="100%"><tr><td><b>'+heading+'</b></td><td align="right" style="color:#d7bf91">'+escape(points)+'</td></tr></table>'
                    if detailed:block+='<span style="color:#a39680">'+escape(row['category']+tier+roll_note+' · '+effect)+'</span>'
                    details.append(block)
                for special in item.special_mods:details.append(escape(special['source']+': '+special['mod'])+' · context only')
            else:
                strongest=sorted((r for r in rating.get('evaluated',[])if r['strength']is not None and r['impact']!='No score increase'),key=lambda r:r.get('contribution',r['strength']),reverse=True)[:3]
                for r in strongest:
                    tier=f" · T{r['tier']}" if r.get('tier') else ''
                    points=f"+{r.get('contribution',0):.2f} points"
                    details.append('<table width="100%"><tr><td><b>'+escape(r['mod']+tier)+'</b></td><td align="right" style="color:#d7bf91">'+escape(points)+'</td></tr></table>')
            if rating['unknown']:details.append('<b style="color:#e1b77e">'+str(len(rating['unknown']))+' unrecognized modifier(s)—review before discarding.</b>')
            if not details:details=['No supported modifiers. Review the item manually.']
            self.body.setText('<hr style="color:#554632">'.join(details))
            self.hint.setText(('Pinned · × closes' if self.locked else 'Hold Alt · click to pin') if self.expanded else settings['rare_hotkey']+' for breakdown')
            for button in self.feedback_buttons:button.setVisible(settings.get('rare_feedback',True))
            self.build_button.setVisible(True)
            self.close_button.setVisible(self.expanded and self.locked)
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput,False)
            mode='expanded'if self.expanded else'compact'
            size=settings.get('assessment_sizes',{}).get(mode)or [460 if self.expanded else 310,min(580,190+len(details)*44)if self.expanded else min(310,140+len(details)*24)]
            self.resize(*size);self.grip.setVisible(self.expanded and alt_down())
        ratio=self.screen().devicePixelRatio()if self.screen()else 1
        client=QRect(round(window.x/ratio),round(window.y/ratio),round(window.width/ratio),round(window.height/ratio))
        rect=tuple(value/ratio for value in data['tooltip_rect'])
        self.move(*panel_position(client,rect,self.width(),self.height()))
        if not self.isVisible():self.show();self.raise_()


class AssessmentGrip(QSizeGrip):
    def mousePressEvent(self,event):
        if alt_down():super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if alt_down():super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        owner=self.parentWidget()
        owner.size_saved.emit('expanded'if owner.expanded else'compact',owner.width(),owner.height())
