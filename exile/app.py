from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from copy import copy
import json
import logging
import os
import re
import sys
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal,QSize
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut, QColor,QPainter,QIcon,QPixmap
from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QTextEdit, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QColorDialog, QTabWidget,QSlider,QSizePolicy,QMenu)

from exile.theme import BrassFrame,WindowFrame,TitleBar,emblem,module_icon,panel_frame,skin_stylesheet
from exile.backend import Backend
from exile.reader_process import ProcessLiveReader as LiveReader
from exile.visual import VisualReader
from exile.mapview import MapMotion, EntityMotion
from exile.native_map import NativeMapOverlap
from exile.assessment import AssessmentView
from exile.feedback import FeedbackHistory,FEEDBACK_LABELS
from exile.feedback_view import FeedbackView
from exile.connections import Connections
from exile.presentation import PresentationCache
from exile.platform import window_is_foreground
from exile.hover_assessment import HoverAssessment,hotkey_parts
from exile.economy import CATEGORIES, Economy
from exile.items import parse_item, rate_rare,item_text
from exile.prices import format_price
from exile.valuation import enrich_items,quote_key
from exile.model import Snapshot
from exile.overlay import Overlay, PreviewCanvas
from exile.route_legend import RouteLegend
from exile.floating_panel import FloatingPanel
from exile.wealth_panel import WealthWindow,section_height
from exile.plugins import PluginManager
from exile.preview import preview_snapshot
from exile.storage import data_root, read_json, resource_root, write_json

STYLE = """
* { font-family:'Segoe UI'; font-size:12px; color:#ded5c1; }
QMainWindow,QDialog,QWidget#root {background:#10100f;}
QFrame#masthead {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #201d17,stop:1 #11110f);}
QFrame#rail {background:#11110f;border-right:1px solid #493d29;}
QLabel#brand {font-family:'Georgia';font-size:35px;color:#e5d7b8;letter-spacing:4px;}
QLabel#title {font-family:'Georgia';font-size:24px;color:#e7dcc6;}
QLabel#subtitle,QLabel#muted {color:#9c9383;}
QLabel#eyebrow {font-family:'Georgia';color:#b69d6a;font-size:11px;letter-spacing:2px;}
QLabel#cardTitle {font-family:'Georgia';font-size:16px;color:#e1d4b9;}
QLabel#badge {color:#b09a71;font-size:10px;}
QFrame#card {background:#171612;border:1px solid #50432f;border-radius:0;}
QFrame#status {background:#141410;border-top:1px solid #393223;border-bottom:1px solid #393223;}
QFrame#moduleRow {background:#141410;border:1px solid transparent;border-bottom:1px solid #302b20;}
QFrame#moduleRow[selected="true"] {background:#242015;border:1px solid #79613b;}
QPushButton {background:#1d1b16;border:1px solid #574832;border-radius:1px;padding:7px 12px;color:#d5c6a7;}
QPushButton:hover {background:#2b2519;border-color:#ad8d50;}
QPushButton:disabled {color:#655f52;background:#151410;border-color:#302b22;}
QPushButton#nav {text-align:left;background:transparent;border:0;padding:17px 8px;color:#a89c86;}
QPushButton#nav:checked {background:#252015;color:#eddcb5;border-left:2px solid #b59a64;border-bottom:1px solid #635033;}
QPushButton#moduleSelect {text-align:left;background:transparent;border:0;padding:5px 1px;font-family:'Georgia';font-size:13px;}
QPushButton#gold {background:#40351f;border-color:#9a7e48;color:#ecdbb3;}
QPushButton#danger {background:#251714;border-color:#6c4236;color:#d2aa94;}
QPushButton#cog {padding:0;background:#1b1914;border:1px solid #645032;}
QCheckBox {spacing:8px;color:#c7bba2;}
QCheckBox::indicator {width:15px;height:15px;border:1px solid #786342;border-radius:0;background:#10100e;}
QCheckBox::indicator:checked {background:#b79a60;border:3px solid #46391f;}
QLineEdit,QTextEdit,QPlainTextEdit,QComboBox,QSpinBox {background:#10100e;border:1px solid #51432d;border-radius:1px;padding:7px;selection-background-color:#695332;color:#ddd1b7;}
QComboBox QAbstractItemView {background:#191711;selection-background-color:#4d3e24;}
QScrollArea {border:none;background:transparent;}
QScrollArea > QWidget > QWidget {background:#13120f;}
QScrollBar:vertical {background:#14130f;width:7px;margin:0;}
QScrollBar::handle:vertical {background:#625137;border-radius:0;min-height:28px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QTabWidget::pane {border:1px solid #4e412d;background:#14130f;}
QTabBar::tab {background:#1b1913;color:#a99c83;padding:9px 12px;border:1px solid #3b3223;}
QTabBar::tab:selected {color:#ebd8ac;background:#302819;border-bottom:2px solid #a68a52;}
QTableWidget {background:#15140f;alternate-background-color:#1b1812;gridline-color:#373021;border:1px solid #51422c;selection-background-color:#493c26;}
QHeaderView::section {background:#282217;color:#cbb78e;padding:7px;border:0;border-bottom:1px solid #655031;}
QToolTip {background:#221e15;color:#e1d1ae;border:1px solid #8f7447;padding:7px;}
"""
STYLE += skin_stylesheet()


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, action, name=None):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(action)
    return widget


class Signals(QObject):
    done = Signal(object, object)


class SettingsDialog(QDialog):
    def __init__(self, plugin, parent):
        super().__init__(parent)
        self.setWindowTitle(plugin.name + " · Settings")
        self.setMinimumWidth(490)
        self.plugin = plugin
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20,18,20,16);layout.setSpacing(12)
        heading=QHBoxLayout();icon=QLabel();icon.setPixmap(module_icon(plugin.id).pixmap(30,30));heading.addWidget(icon)
        heading.addWidget(label(plugin.name, "title"),1);layout.addLayout(heading)
        description=label(plugin.description, "muted", True);description.setStyleSheet('font-family:Georgia;font-size:11px;');layout.addWidget(description)
        self.controls = {}
        self.reset_wealth_positions=False
        if hasattr(plugin, 'radar_categories'):
            self.radar_tabs(layout)
        elif hasattr(plugin,'settings_groups'):
            self.grouped_tabs(layout)
        elif plugin.id=='map_reveal':
            self.map_settings(layout)
        else:
            form = QFormLayout()
            for key, field in plugin.fields.items():
                form.addRow(field[0], self.control(key))
            layout.addLayout(form)
            layout.addStretch(1)
        self.actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.actions.accepted.connect(self.accept)
        self.actions.rejected.connect(self.reject)
        layout.addWidget(self.actions)

    def map_settings(self,layout):
        for title,keys in [('Appearance',('color','opacity','line_width')),('Alignment',('zoom','hide_native','native_margin')),('Performance',('refresh_rate',))]:
            heading=label(title,'sectionTitle');heading.setStyleSheet('font-family:Georgia;color:#d5c09a;border-top:1px solid #57462e;padding-top:9px;')
            layout.addWidget(heading);form=QFormLayout();form.setVerticalSpacing(12)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for key in keys:
                control=self.control(key)
                names={'zoom':'Alignment scale','opacity':'Outline opacity','line_width':'Line thickness','color':'Outline color','hide_native':'Hide lines on explored terrain','native_margin':'Explored-line clearance','refresh_rate':'Drawing frame rate'}
                if key in ('opacity','line_width','zoom','native_margin'):
                    field=QWidget();field.setMaximumWidth(240);row=QHBoxLayout(field);row.setContentsMargins(0,0,0,0)
                    slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(control.minimum(),control.maximum());slider.setValue(control.value())
                    slider.setAccessibleName(names[key]);slider.valueChanged.connect(control.setValue);control.valueChanged.connect(slider.setValue)
                    control.setFixedWidth(66);control.setSuffix(' %'if key in ('opacity','zoom')else '')
                    row.addWidget(slider,1);row.addWidget(control);form.addRow(names[key],field)
                else:
                    if isinstance(control,QComboBox):control.setMaximumWidth(240)
                    form.addRow(names[key],control)
                control.setToolTip(self.plugin.fields[key][0]);control.setAccessibleName(names[key])
            layout.addLayout(form)
        layout.addStretch()

    def control(self, key):
        title, kind, *extra = self.plugin.fields[key]
        value = self.plugin.settings[key]
        if kind == 'bool':
            widget = QCheckBox()
            widget.setChecked(bool(value))
        elif kind == 'int':
            widget = QSpinBox()
            widget.setRange(extra[0], extra[1])
            widget.setValue(int(value))
        elif kind == 'choice':
            widget = QComboBox()
            widget.addItems(extra[0])
            widget.setCurrentText(str(value))
        elif kind == 'text':
            widget = QTextEdit()
            widget.setPlainText(str(value))
            widget.setMaximumHeight(130)
        elif kind == 'color':
            widget = QPushButton()
            def set_color(color):
                widget.setProperty('setting_color', color.name())
                widget.setText(color.name())
                text = '#151820' if color.lightness() > 140 else '#f4f4f4'
                widget.setStyleSheet(f'border-image:none;border:1px solid #796446;background:{color.name()}; color:{text}; padding:4px 8px;')
            def choose():
                color = QColorDialog.getColor(QColor(widget.property('setting_color')), self, title)
                if color.isValid():
                    set_color(color)
            set_color(QColor(value))
            widget.clicked.connect(choose)
        else:
            widget = QLineEdit(str(value))
        self.controls[key] = widget
        return widget

    def grouped_tabs(self,layout):
        self.resize(650,560)
        tabs=QTabWidget();layout.addWidget(tabs)
        for title,keys in self.plugin.settings_groups.items():
            page=QWidget();box=QVBoxLayout(page);form=QFormLayout()
            for key in keys:form.addRow(self.plugin.fields[key][0],self.control(key))
            box.addLayout(form)
            if self.plugin.id=='routes' and title=='Ground lines':
                box.addWidget(label('Balanced keeps the existing route for small savings. The nearby line still follows you every frame.', 'muted', True))
            if self.plugin.id=='preload' and title=='Strongboxes':
                box.addWidget(label('These switches select box types, such as Diviner’s and Arcanist’s. Unique strongboxes use known unique-specific assets. Ordinary boxes start off.', 'muted', True))
            if self.plugin.id=='preload' and title=='Mechanics':
                box.addWidget(label('Preload means matching resources were loaded. Seen means the object or monster was observed in this instance. Neither is a count of unopened encounters.', 'muted', True))
            if self.plugin.id=='pricing' and title=='Net worth':
                box.addWidget(label('Drag each live summary to move it. Positions save automatically and override the default placement.', 'muted', True))
                reset=QPushButton('Reset saved positions')
                def reset_positions():
                    self.reset_wealth_positions=True
                    self.wealth_reset_button.setText('Positions reset');self.accept()
                self.wealth_reset_button=reset;reset.clicked.connect(reset_positions)
                box.addWidget(reset)
            if self.plugin.id=='pricing' and title=='Assessment':
                box.addWidget(label('Hover an identified rare in PoE for its rating. The shortcut opens a larger, pinned breakdown in either display mode. Unknown modifiers need review; ratings are not market prices.', 'muted', True))
            box.addStretch()
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page)
            tabs.addTab(scroll,title)

    def radar_tabs(self, layout):
        self.resize(790, 670)
        self.setMinimumSize(700, 550)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        for title in ('Monsters', 'Health bars', 'Objects', 'Encounters', 'Display'):
            page = QWidget()
            box = QVBoxLayout(page)
            form = QFormLayout()
            keys = ({'Monsters': ['monsters'], 'Objects': ['objects', 'hide_used'],
                     'Health bars': [k for k in self.plugin.fields if k.startswith('health_')],
                     'Display': ['map_icons', 'icon_scale', 'refresh_rate', 'zoom', 'max_range', 'filled', 'circle_width', 'opacity']}.get(title, []))
            for key in keys:
                form.addRow(self.plugin.fields[key][0], self.control(key))
            box.addLayout(form)
            categories = [c for c in self.plugin.radar_categories if c[2] == title]
            if categories:
                table = QTableWidget(len(categories), 5)
                table.setHorizontalHeaderLabels(['Show', 'Category', 'Color', 'Size', 'Label'])
                table.verticalHeader().hide()
                table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                for column, width in ((0,48),(2,100),(3,96),(4,55)):
                    table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
                    table.setColumnWidth(column, width)
                for row, category in enumerate(categories):
                    key, name = category[:2]
                    table.setItem(row, 1, QTableWidgetItem(name))
                    for column, prefix in ((0,'show'),(2,'color'),(3,'size'),(4,'label')):
                        control = self.control(f'{prefix}_{key}')
                        if prefix == 'size':
                            control.setStyleSheet('QSpinBox {padding:3px 8px;}')
                            control.setFixedHeight(34)
                        table.setCellWidget(row, column, control)
                    table.setRowHeight(row, 44)
                box.addWidget(table)
            if title == 'Monsters':
                box.addWidget(label('Dead monsters are hidden. Allies and minions are off by default.', 'muted', True))
            if title == 'Encounters':
                box.addWidget(label('Markers show objects currently loaded by PoE. Object markers must be enabled on the Objects tab.', 'muted', True))
            if title == 'Objects':
                box.addWidget(label('Used shrines and opened chests are hidden. Waypoints, portals and area transitions remain visible.', 'muted', True))
            if title=='Display':box.addWidget(label('Normal and magic skulls use their monster colors. Other icons keep their original colors.', 'muted', True))
            if title in ('Health bars', 'Display'):
                box.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            tabs.addTab(scroll, title)

    def values(self):
        result = {}
        for key, widget in self.controls.items():
            if widget.property('setting_color') is not None: result[key] = widget.property('setting_color')
            elif isinstance(widget, QCheckBox): result[key] = widget.isChecked()
            elif isinstance(widget, QSpinBox): result[key] = widget.value()
            elif isinstance(widget, QComboBox): result[key] = widget.currentText()
            elif isinstance(widget, QTextEdit): result[key] = widget.toPlainText()
            else: result[key] = widget.text()
        if self.reset_wealth_positions:result['summary_positions']={}
        return result


class InlineSettings(SettingsDialog):
    saveRequested=Signal()
    resetRequested=Signal()
    def __init__(self,plugin,parent):
        super().__init__(plugin,parent)
        self.actions.hide()
        self.autosave_timer=QTimer(self);self.autosave_timer.setSingleShot(True)
        self.autosave_timer.timeout.connect(self.accept)
        for widget in self.controls.values():
            if isinstance(widget,QCheckBox):widget.toggled.connect(self.schedule_save)
            elif isinstance(widget,QSpinBox):widget.valueChanged.connect(self.schedule_save)
            elif isinstance(widget,QComboBox):widget.currentTextChanged.connect(self.schedule_save)
            elif isinstance(widget,QTextEdit):widget.textChanged.connect(self.schedule_save)
            elif isinstance(widget,QLineEdit):widget.editingFinished.connect(self.schedule_save)
            elif isinstance(widget,QPushButton):widget.clicked.connect(self.schedule_save)
    def schedule_save(self,*_):self.autosave_timer.start(200)
    def accept(self):self.saveRequested.emit()
    def reject(self):self.resetRequested.emit()
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);panel_frame(painter,self.rect())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root = resource_root()
        self.data = data_root()
        self.config_path = self.data / "settings.json"
        self.config = read_json(self.config_path, {})
        saved_plugins=dict(self.config.get('plugins',{}))
        if 'workshop'not in saved_plugins and ('workshop_enabled'in self.config or 'pricing'in saved_plugins):
            saved_plugins['workshop']={'enabled':self.config.get('workshop_enabled',True)}
        self.config.pop('workshop_enabled',None)
        self.manager = PluginManager(self.root / "plugins", saved_plugins)
        self.manager.discover()
        install = Path(self.config.get("installation", r"D:\SteamLibrary\steamapps\common\Path of Exile"))
        self.backend = Backend(self.root / "profiles", install)
        self.live_reader = LiveReader()
        self.visual_reader = VisualReader()
        self.map_motion = MapMotion()
        self.entity_motion = EntityMotion(delay=self.map_motion.delay)
        self.map_overlap = NativeMapOverlap()
        self.economy = Economy(self.data / "economy-cache")
        self.feedback_history=FeedbackHistory(self.data/'assessment-feedback.json')
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="economy")
        self.signals = Signals()
        self.signals.done.connect(self.worker_done)
        self.preview = False
        self.presentation=PresentationCache()
        self.snapshot = Snapshot()
        self.stash_estimates = {}
        self.currency_estimates = {}
        self.unique_quotes = {}
        self.prices_league = ''
        self.stash_pricing_pending = False
        self.stash_price_retry = 0
        self.stash_price_refresh_at=0
        self.stash_price_signature = None
        self.cards = {}
        self.overlay = Overlay()
        self.route_legend = RouteLegend()
        self.route_legend.moved.connect(self.save_route_legend)
        self.route_legend.resized.connect(lambda w,h:self.save_overlay_setting('routes','legend_size',[w,h]))
        self.floating_panels={identity:FloatingPanel()for identity in ('preload','uptime')}
        self.floating_panels['uptime'].excluded.connect(self.exclude_buff)
        for identity,panel in self.floating_panels.items():
            panel.moved.connect(lambda x,y,identity=identity:self.save_overlay_setting(identity,'overlay_position',[x,y]))
            panel.resized.connect(lambda w,h,identity=identity:self.save_overlay_setting(identity,'overlay_size',[w,h]))
        self.wealth_windows={scope:WealthWindow(scope)for scope in ('inventory','personal','guild')}
        for scope,window in self.wealth_windows.items():
            window.moved.connect(lambda x,y,scope=scope:self.save_wealth_position(scope,x,y))
            window.resized.connect(lambda width,height,scope=scope:self.save_wealth_size(scope,width,height))
        self.setWindowTitle("Waymark")
        self.setWindowIcon(emblem(size=48))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.resize(1040, 700)
        self.setMinimumSize(960, 640)
        geometry=self.config.get('window_geometry')
        if self.config.get('remember_window',True)and isinstance(geometry,list)and len(geometry)==4:
            x,y,w,h=map(int,geometry);screen=QApplication.primaryScreen().availableGeometry()
            self.resize(min(max(960,w),screen.width()),min(max(640,h),screen.height()))
            self.move(max(screen.left(),min(x,screen.right()-self.width()+1)),max(screen.top(),min(y,screen.bottom()-self.height()+1)))
        self.build_ui()
        self.refresh_cards()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        QShortcut(QKeySequence("F9"), self, self.panic)
        self.hotkey_registered = False
        self.rare_hotkey_registered=False
        self.rare_hotkey_signature=None
        self.hover_assessment=HoverAssessment()
        self.hover_assessment.size_saved.connect(self.save_assessment_size)
        self.hover_assessment.feedback.connect(lambda direction:self.record_assessment_feedback(direction,clicked=True))
        self.hover_assessment.archetype_selected.connect(self.choose_assessment_archetype)
        self.feedback_hotkeys=set()
        self.feedback_hotkey_active=None
        if os.name == "nt":
            import ctypes
            # Global panic key remains active when the game owns keyboard focus.
            self.hotkey_registered = bool(ctypes.windll.user32.RegisterHotKey(int(self.winId()), 1, 0x4000, 0x78))
        if not self.hotkey_registered:
            self.note("Global F9 unavailable; Stop all remains available in the app.")

    def build_ui(self):
        root = WindowFrame()
        root.setObjectName("root")
        self.setCentralWidget(root)
        shell=QVBoxLayout(root);shell.setContentsMargins(6,3,6,6);shell.setSpacing(1)
        shell.addWidget(TitleBar(self))
        outer = QHBoxLayout();shell.addLayout(outer,1)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        rail = BrassFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(132)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(7, 13, 7, 12);rail_layout.setSpacing(5)
        self.nav = []
        for index,(text,icon)in enumerate((('Modules','modules'),('Item workshop','workshop'),('Compatibility','cog'),('Stash search','search'),('Assessment history','history'),('Settings','cog'),('Connections','modules'))):
            nav=button({1:'Workshop',4:'History'}.get(index,text),lambda checked=False,i=index:self.navigate(i),'nav')
            nav.setIcon(emblem(icon));nav.setIconSize(QSize(22,22))
            nav.setToolTip(text)
            nav.setCheckable(True)
            self.nav.append(nav)
            rail_layout.addWidget(nav)
        rail_layout.addStretch()
        rail_layout.addWidget(button('Stop all · F9',self.panic,'danger'))
        rail_layout.addSpacing(10)
        rail_layout.addWidget(label("v0.1  ·  Waymark", "muted"))
        outer.addWidget(rail)
        content = QVBoxLayout()
        content.setContentsMargins(3,0,0,0)
        content.setSpacing(3)
        heading = QHBoxLayout()
        titles = QVBoxLayout()

        self.page_title = label("Modules", "title")
        titles.addWidget(self.page_title)
        self.subtitle = label("", "subtitle")
        self.subtitle.hide()
        heading.addLayout(titles)
        heading.addStretch()

        content.addLayout(heading)
        status = QFrame()
        status.setObjectName("status")
        status_row = QHBoxLayout(status)
        status_row.setContentsMargins(8,4,8,4)
        status_row.addWidget(label("●", "badge"))
        self.status_label = label("Checking installation…", "muted")
        status_row.addWidget(self.status_label, 1)
        self.counter = label("0 ACTIVE", "eyebrow")
        status_row.addWidget(self.counter)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.modules_page())
        self.pages.addWidget(self.items_page())
        self.canvas=PreviewCanvas();self.canvas.setParent(self);self.canvas.hide()
        self.pages.addWidget(self.compatibility_page())
        self.pages.addWidget(self.stash_page())
        self.feedback_view=FeedbackView(self.feedback_history,lambda value:QApplication.clipboard().setText(value),self.note)
        self.pages.addWidget(self.feedback_view)
        self.pages.addWidget(self.settings_page())
        self.connections=Connections(self);self.pages.addWidget(self.connections)
        content.addWidget(self.pages, 1)
        content.addWidget(status)
        self.notice = label("Ready. Add or remove module folders, then refresh the module list.", "muted", True)
        content.addWidget(self.notice)
        outer.addLayout(content, 1)
        self.navigate(0)

    def navigate(self, index):
        if index==1 and not self.workshop_enabled():index=0
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav): nav.setChecked(i == index)
        self.page_title.setText(("Modules", "Item workshop", "Compatibility", "Stash search","Assessment history","Settings","Connections")[index])
        self.page_title.setVisible(index!=0)

    def stash_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.stash_query = QLineEdit()
        self.stash_query.setPlaceholderText("Search item names, base types or tab names…")
        self.stash_query.textChanged.connect(self.refresh_stash)
        self.stash_scope=QPushButton('Tracked Stashes ▾')
        stored=self.config.get('stash_tracked_sources')
        self.stash_tracked=None if stored is None else {tuple(value) for value in stored if isinstance(value,list)}
        self.stash_hidden_tabs={tuple(value) for value in self.config.get('stash_hidden_tabs',[]) if isinstance(value,list)}
        self.stash_legacy_selected={tuple(value) for value in self.config.get('stash_search_filters',[]) if isinstance(value,list)} if 'stash_tracked_sources' not in self.config else set()
        self.stash_filter_menu=QMenu(self.stash_scope);self.stash_scope.setMenu(self.stash_filter_menu)
        self.stash_filter_menu.aboutToShow.connect(self.build_stash_filter_menu)
        row=QHBoxLayout();row.addWidget(self.stash_query,1);row.addWidget(self.stash_scope)
        row.addWidget(button('Columns',self.show_stash_columns));row.addWidget(button('Refresh estimates',self.price_stash));layout.addLayout(row)
        tabs_row=QHBoxLayout();tabs_row.addStretch();tabs_row.addWidget(button('Tab list',self.show_stash_tabs));layout.addLayout(tabs_row)
        self.stash_icon_manager=QNetworkAccessManager(self);self.stash_icons={};self.stash_icon_pending=set();self.stash_icon_queue=[]
        self.stash_table = QTableWidget(0, 4)
        self.stash_table.setHorizontalHeaderLabels(["Item", "Owner", "Tab", "Estimate"])
        header=self.stash_table.horizontalHeader();header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive);header.setStretchLastSection(False)
        widths=self.config.get('stash_column_widths',[320,160,180,110])
        for col in range(4):self.stash_table.setColumnWidth(col,max(45,int(widths[col])) if col<len(widths) else 120)
        visible=self.config.get('stash_visible_columns',[True,True,True,True])
        for col in range(4):self.stash_table.setColumnHidden(col,col<len(visible) and not visible[col])
        header.sectionResized.connect(self.save_stash_columns)
        self.stash_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stash_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stash_table.verticalHeader().hide()
        self.stash_table.verticalHeader().setDefaultSectionSize(38);self.stash_table.setIconSize(QSize(28,28))
        self.stash_table.setAlternatingRowColors(True);self.stash_table.setShowGrid(True)
        self.stash_table.verticalScrollBar().valueChanged.connect(self.refresh_stash_visible_icons)
        self.stash_table.setStyleSheet("QTableWidget {background:#141310; alternate-background-color:#1b1915; color:#ded3bd; gridline-color:#443c30; border:1px solid #584932; selection-background-color:#413725;} QHeaderView::section {background:#262119; color:#d7c199; padding:8px; border:0; border-right:1px solid #51442f; border-bottom:1px solid #645338;}")
        layout.addWidget(self.stash_table)
        self.stash_refresh_at = 0
        return page

    def refresh_stash(self, *_):
        if not hasattr(self, "stash_table"):
            return
        enabled = any(p.id == "pricing" and p.enabled for p in self.manager.plugins)
        query=self.stash_query.text().casefold().strip()
        sources=[]
        for item in self.snapshot.stash:
            entry=dict(item);entry['owner_label']='Guild' if item.get('scope')=='guild' else 'Personal'
            entry['source_key']=('local',item.get('scope'));entry['filter_key']=('local',item.get('scope'),item.get('tab_index'),item.get('tab'))
            sources.append(entry)
        for share in getattr(getattr(self,'connections',None),'state',{}).get('shares',[]):
            if share.get('kind')!='tabs' or share.get('owner')==getattr(self.connections,'member',None):continue
            data=share.get('data',{});owner=share.get('owner_name','Player');tab=data.get('title','Tab')
            for item in data.get('items',[]):
                entry=dict(item,owner_label=owner+' · '+('Guild' if data.get('scope')=='guild' else 'Personal'),tab=tab,scope=data.get('scope','personal'),source_key=('remote',share.get('owner')),filter_key=('remote',share.get('owner'),share.get('key')))
                sources.append(entry)
        self.stash_sources=sources
        if self.stash_legacy_selected and sources:
            selected=self.stash_legacy_selected;self.stash_tracked={key[:2] for key in selected}
            self.stash_hidden_tabs.update(set(self.stash_tab_catalog())-selected)
            self.config['stash_tracked_sources']=[list(key) for key in self.stash_tracked]
            self.config['stash_hidden_tabs']=[list(key) for key in self.stash_hidden_tabs]
            self.config.pop('stash_search_filters',None);self.stash_legacy_selected=set();self.save()
        items=[item for item in sources if enabled and (self.stash_tracked is None or item['source_key'] in self.stash_tracked) and item['filter_key'] not in self.stash_hidden_tabs and
               query in ' '.join(str(item.get(k,'')) for k in ('name','base','tab','owner_label')).casefold()]
        self.stash_visible_items=items
        self.stash_table.setRowCount(len(items))
        for row, item in enumerate(items):
            price = item.get("chaos_estimate")
            values = [item.get('name',''),item.get('owner_label',''),item.get('tab',''),
                      item.get('price_label') or (format_price(price,self.currency_estimates.get('divine orb')) if isinstance(price,(int,float)) else '')]
            for column, value in enumerate(values):
                cell=QTableWidgetItem(str(value))
                if column==0:
                    art=item.get('art','');icon=self.stash_icons.get(art)
                    if icon is not None:cell.setIcon(icon)
                self.stash_table.setItem(row,column,cell)
        self.refresh_stash_visible_icons()
    def refresh_stash_visible_icons(self,*_):
        if not self.stash_table.isVisible():return
        top=self.stash_table.rowAt(0);bottom=self.stash_table.rowAt(self.stash_table.viewport().height()-1)
        top=max(0,top);bottom=min(len(getattr(self,'stash_visible_items',[]))-1,bottom if bottom>=0 else top+25)
        for row in range(top,bottom+1):
            item=self.stash_visible_items[row];icon=self.stash_icon(item.get('art',''))
            if icon and self.stash_table.item(row,0):self.stash_table.item(row,0).setIcon(icon)

    def stash_icon(self,art):
        if not re.fullmatch(r'Art/2DItems/[A-Za-z0-9_ /.-]+\.dds',str(art),re.I):return None
        if art in self.stash_icons:return self.stash_icons[art]
        if art not in self.stash_icon_pending:
            self.stash_icon_pending.add(art);self.stash_icon_queue.append(art);self.load_stash_icons()
        return None

    def load_stash_icons(self):
        if not hasattr(self,'stash_icon_active'):self.stash_icon_active=0
        while self.stash_icon_queue and self.stash_icon_active<4:
            art=self.stash_icon_queue.pop(0);url='https://web.poecdn.com/image/'+art[:-4]+'.png'
            request=QNetworkRequest(QUrl(url));request.setTransferTimeout(8000)
            reply=self.stash_icon_manager.get(request);self.stash_icon_active+=1
            reply.finished.connect(lambda r=reply,a=art:self.stash_icon_finished(r,a))

    def stash_icon_finished(self,reply,art):
        self.stash_icon_active-=1;icon=None
        if reply.error()==reply.NetworkError.NoError and reply.bytesAvailable()<=1_000_000:
            pixmap=QPixmap()
            if pixmap.loadFromData(bytes(reply.readAll())):icon=QIcon(pixmap)
        self.stash_icons[art]=icon;self.stash_icon_pending.discard(art);reply.deleteLater();self.load_stash_icons()
        if hasattr(self,'pages') and self.pages.currentWidget() is self.stash_table.window():self.refresh_stash()
        else:
            # Update the matching cells without repeatedly rebuilding the table.
            for row,item in enumerate(getattr(self,'stash_visible_items',[])):
                if item.get('art')==art and icon and self.stash_table.item(row,0):self.stash_table.item(row,0).setIcon(icon)

    def stash_tab_catalog(self):
        tabs={}
        for tab in getattr(self.snapshot,'stash_tabs',[]):
            scope=tab.get('scope')
            if scope not in ('personal','guild'):continue
            source=('local',scope);key=('local',scope,tab.get('index'),tab.get('name'))
            tabs[key]=(source,('Personal' if scope=='personal' else 'Guild'),str(tab.get('name','Tab')))
        for item in getattr(self,'stash_sources',[]):
            key=item['filter_key'];source=item['source_key']
            tabs.setdefault(key,(source,item['owner_label'],str(item.get('tab','Tab'))))
        for share in getattr(getattr(self,'connections',None),'state',{}).get('shares',[]):
            if share.get('kind')!='tabs' or share.get('owner')==getattr(self.connections,'member',None):continue
            data=share.get('data',{});source=('remote',share.get('owner'));key=('remote',share.get('owner'),share.get('key'))
            owner=share.get('owner_name','Player')+' · '+('Guild' if data.get('scope')=='guild' else 'Personal')
            tabs[key]=(source,owner,str(data.get('title','Tab')))
        return tabs

    def build_stash_filter_menu(self):
        self.stash_filter_menu.clear();catalog=self.stash_tab_catalog()
        sources={('local','personal'):'Personal',('local','guild'):'Guild'}
        for source,owner,tab in catalog.values():
            if source[0]=='remote':sources[source]=owner.split(' · ',1)[0]
        all_action=self.stash_filter_menu.addAction('All');all_action.setCheckable(True);all_action.setChecked(self.stash_tracked is None)
        all_action.triggered.connect(lambda:self.set_stash_source(None,True,sources))
        for source,title in sources.items():
            action=self.stash_filter_menu.addAction(title);action.setCheckable(True);action.setChecked(self.stash_tracked is None or source in self.stash_tracked)
            action.triggered.connect(lambda checked,key=source:self.set_stash_source(key,checked,sources))

    def set_stash_source(self,key,checked,sources):
        if key is None:self.stash_tracked=None
        else:
            if self.stash_tracked is None:self.stash_tracked=set(sources)
            if checked:self.stash_tracked.add(key)
            else:self.stash_tracked.discard(key)
        self.config['stash_tracked_sources']=None if self.stash_tracked is None else [list(key) for key in self.stash_tracked]
        self.save();self.refresh_stash()

    def show_stash_tabs(self):
        dialog=QDialog(self);dialog.setWindowTitle('Tab list');dialog.resize(440,520)
        layout=QVBoxLayout(dialog);scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();box=QVBoxLayout(page)
        catalog=self.stash_tab_catalog();shown=0;previous_owner=None
        for key,(source,owner,title) in sorted(catalog.items(),key=lambda entry:(entry[1][1].casefold(),entry[1][2].casefold())):
            if self.stash_tracked is not None and source not in self.stash_tracked:continue
            if owner!=previous_owner:
                heading=label(owner,'sectionTitle');box.addWidget(heading);previous_owner=owner
            check=QCheckBox(title);check.setChecked(key not in self.stash_hidden_tabs)
            check.toggled.connect(lambda checked,k=key:self.set_stash_tab_visible(k,checked));box.addWidget(check);shown+=1
        if not shown:box.addWidget(label('No tabs available. Open a stash tab in PoE or connect to a group.','muted',True))
        box.addStretch();scroll.setWidget(page);layout.addWidget(scroll);dialog.exec()

    def set_stash_tab_visible(self,key,checked):
        if checked:self.stash_hidden_tabs.discard(key)
        else:self.stash_hidden_tabs.add(key)
        self.config['stash_hidden_tabs']=[list(value) for value in self.stash_hidden_tabs];self.save();self.refresh_stash()

    def show_stash_columns(self):
        menu=QMenu(self)
        for col in range(self.stash_table.columnCount()):
            action=menu.addAction(self.stash_table.horizontalHeaderItem(col).text());action.setCheckable(True);action.setChecked(not self.stash_table.isColumnHidden(col))
            action.triggered.connect(lambda checked,index=col:self.set_stash_column(index,checked))
        menu.exec(self.stash_scope.mapToGlobal(self.stash_scope.rect().bottomLeft()))

    def set_stash_column(self,index,visible):
        self.stash_table.setColumnHidden(index,not visible);self.save_stash_columns()

    def save_stash_columns(self,*_):
        previous=self.config.get('stash_column_widths',[320,160,180,110])
        self.config['stash_column_widths']=[self.stash_table.columnWidth(i) if not self.stash_table.isColumnHidden(i) and self.stash_table.columnWidth(i)>0 else (previous[i] if i<len(previous) else 120) for i in range(self.stash_table.columnCount())]
        self.config['stash_visible_columns']=[not self.stash_table.isColumnHidden(i) for i in range(self.stash_table.columnCount())]
        self.save()

    def price_stash(self):
        if self.stash_pricing_pending:
            return
        if not any(p.id == 'pricing' and p.enabled for p in self.manager.plugins):
            self.note("Enable Items & stash first.")
            return
        league = self.economy_league()
        items = [dict(item) for item in self.snapshot.stash+self.snapshot.inventory+self.snapshot.ground_items]
        if not league or not items:
            return
        self.stash_pricing_pending = True
        # Coalesce changing loot without delaying a newly seen unique by a
        # minute. Economy.get still enforces provider cache TTL/backoff.
        self.stash_price_retry = time.monotonic() + 1
        self.stash_price_signature = self.item_price_signature(items,league)
        self.note("Fetching cached unique and currency estimates for the league selected in Settings…")
        self.run_worker(lambda: self.economy.stash_prices(items, league), self.show_stash_prices)

    def show_stash_prices(self, value):
        league=self.economy_league()
        if value['league']!=league:return
        same=self.prices_league==value['league']
        self.stash_estimates = value['estimates']
        retained=dict(self.unique_quotes)if same else{}
        for key in value.get('requested_keys',[]):retained.pop(key,None)
        self.unique_quotes={**retained,**value.get('quotes',{})}
        self.currency_estimates = value['currencies']
        self.prices_league=value['league']
        self.stash_price_refresh_at=time.monotonic()+900
        self.note(f"Estimates loaded for {value['league']}. Unique ranges retain variant uncertainty; currency totals use stack quantity. Copy rare items to Item workshop to rate them.")
        self.enrich_stash()
        self.refresh_stash()

    def enrich_stash(self):
        league=self.economy_league()
        current=not self.prices_league or self.prices_league==league
        signature=(id(self.snapshot.stash),id(self.snapshot.inventory),id(self.snapshot.ground_items),
                   id(self.unique_quotes),id(self.currency_estimates),current,self.snapshot.area)
        if getattr(self,'enrichment_signature',None)==signature:
            self.snapshot.divine_chaos=self.currency_estimates.get('divine orb')if current else None
            return
        self.enrichment_signature=signature
        enrich_items(self.snapshot.stash+self.snapshot.inventory+self.snapshot.ground_items,
                     self.currency_estimates if current else {},self.unique_quotes if current else {},area=self.snapshot.area)
        self.snapshot.divine_chaos=self.currency_estimates.get('divine orb')if current else None

    @staticmethod
    def item_price_signature(items,league):
        # Stack quantities don't require new network requests. Full identities
        # and metadata do, including categories absent from the earlier cache.
        return league,tuple(sorted({repr((quote_key(i),i.get('metadata','')))for i in items
            if i.get('rarity')==3 or i.get('stackable')or i.get('metadata','').startswith(
                ('Metadata/Items/Currency/','Metadata/Items/Scarabs/','Metadata/Items/DivinationCards/','Metadata/Items/MapFragments/'))}))

    def maybe_price_items(self,now=None):
        now=time.monotonic()if now is None else now
        if (self.preview or self.stash_pricing_pending or now<self.stash_price_retry or
            not any(p.enabled and p.id=='pricing'for p in self.manager.plugins)):return
        items=self.snapshot.stash+self.snapshot.inventory+self.snapshot.ground_items
        league=self.economy_league()
        signature=self.item_price_signature(items,league)
        if not league or not signature[1]:return
        if signature!=self.stash_price_signature or not self.currency_estimates or now>=self.stash_price_refresh_at:
            self.price_stash()

    def modules_page(self):
        page=QWidget();layout=QHBoxLayout(page);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
        ledger=BrassFrame();ledger.setFixedWidth(254);left=QVBoxLayout(ledger);left.setContentsMargins(10,16,10,12);left.setSpacing(7)
        left.addWidget(label('Modules','title'))
        self.search=QLineEdit();self.search.setPlaceholderText('Find a module');self.search.textChanged.connect(self.filter_cards);left.addWidget(self.search)
        scroll=QScrollArea();scroll.setWidgetResizable(True);self.card_container=QWidget();self.grid=QGridLayout(self.card_container)
        self.grid.setContentsMargins(0,4,0,0);self.grid.setSpacing(1);self.grid.setColumnStretch(0,1)
        scroll.setWidget(self.card_container);left.addWidget(scroll,1)
        left.addWidget(button('Refresh modules',self.reload_modules))
        layout.addWidget(ledger)
        self.inspector=QScrollArea();self.inspector.setWidgetResizable(True);layout.addWidget(self.inspector,1)
        self.selected_plugin_id='map_reveal';return page

    def refresh_cards(self):
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.cards={}
        order={name:i for i,name in enumerate(('map_reveal','routes','radar','preload','pricing','workshop','hazards','uptime'))}
        self.module_rows=sorted(self.manager.plugins,key=lambda p:order.get(p.id,99))
        titles=dict(map_reveal='Map reveal',routes='Routes',radar='Monsters && objects',preload='Encounter alerts',pricing='Items && stash',workshop='Item workshop',hazards='Hazards',uptime='Buff uptime')
        for index,plugin in enumerate(self.module_rows):
            card=QFrame();card.setObjectName('moduleRow');card.setFixedHeight(48);box=QVBoxLayout(card);box.setContentsMargins(13,5,6,5);box.setSpacing(0)
            row=QHBoxLayout();check=QCheckBox();check.setChecked(plugin.enabled)
            check.toggled.connect(lambda checked,p=plugin:self.toggle(p,checked));row.addWidget(check)
            check.setAccessibleName('Enable '+plugin.name)
            select=button(titles.get(plugin.id,plugin.name.replace('&','&&')),lambda checked=False,p=plugin:self.select_module(p),'moduleSelect');select.setIcon(module_icon(plugin.id));select.setIconSize(QSize(24,24));row.addWidget(select,1)
            cog=button('',lambda checked=False,p=plugin:self.select_module(p),'cog');cog.setIcon(emblem('cog'));cog.setIconSize(QSize(16,16));cog.setFixedSize(24,24);cog.setToolTip('Settings · '+plugin.name);cog.setAccessibleName('Settings · '+plugin.name);row.addWidget(cog)
            box.addLayout(row);state=label('','badge');state.hide()
            self.grid.addWidget(card,index,0);self.cards[plugin.id]=(card,check,state)
        self.grid.setRowStretch(len(self.manager.plugins),1)
        self.filter_cards();self.update_module_states()
        selected=next((p for p in self.manager.plugins if p.id==self.selected_plugin_id),None)
        if selected:self.select_module(selected)

    def select_module(self,plugin):
        self.selected_plugin_id=plugin.id
        old=self.inspector.widget()
        if old and hasattr(old,'autosave_timer') and old.autosave_timer.isActive():
            old.autosave_timer.stop();old.accept()
        old=self.inspector.takeWidget()
        if old:old.deleteLater()
        panel=InlineSettings(plugin,self);panel.setWindowFlags(Qt.WindowType.Widget);panel.setMinimumSize(0,0)
        panel.saveRequested.connect(lambda:self.apply_module_settings(plugin,panel))
        panel.resetRequested.connect(lambda:self.select_module(plugin))
        self.inspector.setWidget(panel)
        for identity,(card,_,_)in self.cards.items():
            card.setProperty('selected',identity==plugin.id);card.style().unpolish(card);card.style().polish(card)

    def filter_cards(self):
        if not hasattr(self,'cards'):return
        query=self.search.text().casefold();visible=0
        for plugin in self.module_rows:
            card=self.cards[plugin.id][0];match=query in (plugin.name+' '+plugin.category+' '+plugin.description).casefold();card.setVisible(match)
            if match:self.grid.addWidget(card,visible,0);visible+=1

    def settings(self,plugin):self.select_module(plugin)

    def apply_module_settings(self,plugin,panel):
        self.presentation.frame=None
        self.static_frames={}
        values=panel.values()
        if plugin.id=='pricing':
            try:hotkey_parts(values['rare_hotkey'])
            except ValueError as exc:QMessageBox.warning(self,'Invalid assessment shortcut',str(exc));return
        plugin.settings.update(values)
        if plugin.id=='pricing':self.archetype.setCurrentText(plugin.settings['archetype'])
        plugin.stop();self.save();panel.reset_wealth_positions=False;self.note(plugin.name+' settings saved.')

    def toggle(self, plugin, checked):
        plugin.enabled = checked
        plugin.error = ""
        plugin.stop()
        self.update_module_states();self.save()

    def reload_modules(self):
        self.manager.saved = self.manager.serialize()
        self.manager.discover()
        self.refresh_cards()
        self.save()
        self.note("Module list refreshed." + (" Errors: " + "; ".join(self.manager.errors) if self.manager.errors else ""))

    def update_module_states(self):
        for plugin in self.manager.plugins:
            card, check, state = self.cards[plugin.id]
            missing = plugin.requires - self.snapshot.capabilities
            if plugin.error:
                state.setText("Module error")
                state.setToolTip(plugin.error)
            elif not plugin.enabled:
                state.setText("Off");state.setToolTip("")
            elif missing:
                state.setText("Needs live data" if not self.preview else "No preview data")
                state.setToolTip("Missing: " + ", ".join(sorted(missing)))
            else:
                state.setText("Preview" if self.preview and plugin.requires else "Ready")
            check.blockSignals(True)
            check.setChecked(plugin.enabled)
            check.blockSignals(False)
            card.setToolTip(plugin.name+' · '+state.text()+('\n'+state.toolTip()if state.toolTip()else ''))
        self.counter.setText(f"{sum(p.enabled for p in self.manager.plugins)} ENABLED")
        if hasattr(self,'nav')and hasattr(self,'workshop_body'):
            enabled=self.workshop_enabled()
            self.nav[1].setVisible(enabled);self.workshop_body.setEnabled(enabled)
            if not enabled and self.pages.currentIndex()==1:self.navigate(0)

    def items_page(self):
        page = QWidget();outer=QVBoxLayout(page)
        self.workshop_body=QWidget();outer.addWidget(self.workshop_body,1)
        self.workshop_body.setEnabled(self.workshop_enabled())
        layout = QVBoxLayout(self.workshop_body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Enable Items & stash, then hover a rare in PoE. Alt+F opens its breakdown (shortcut configurable in the cog). You can also assess copied items here.", "muted", True))
        row = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItems(["Automatic", *CATEGORIES])
        row.addWidget(self.category)
        layout.addLayout(row)
        self.tooltip_input = QTextEdit()
        self.tooltip_input.setPlaceholderText("Item Class: Boots\nRarity: Rare\n…")
        self.tooltip_input.setFixedHeight(115)
        self.tooltip_input.hide()
        layout.addWidget(self.tooltip_input)
        actions = QHBoxLayout()
        actions.addWidget(button("Paste & assess", self.paste_assess, "gold"))
        self.assess_button = button("Assess again", self.assess)
        actions.addWidget(self.assess_button)
        source_toggle = QCheckBox('Show copied text')
        source_toggle.toggled.connect(self.tooltip_input.setVisible)
        actions.addWidget(source_toggle)
        actions.addStretch()
        actions.addWidget(label('Build', 'muted'))
        self.archetype = QComboBox()
        pricing = next((p for p in self.manager.plugins if p.id == 'pricing'), None)
        self.archetype.addItems(pricing.fields['archetype'][2] if pricing else ['General'])
        self.archetype.setCurrentText(pricing.settings['archetype'] if pricing else 'General')
        self.archetype.currentTextChanged.connect(self.select_archetype)
        actions.addWidget(self.archetype)
        layout.addLayout(actions)
        self.result = AssessmentView()
        self.result.feedback.connect(lambda direction:self.record_assessment_feedback(direction,workshop=True))
        self.result.archetype_selected.connect(lambda value:self.choose_assessment_archetype(value,workshop=True))
        layout.addWidget(self.result, 1)
        return page

    def workshop_enabled(self):
        return any(p.id=='workshop'and p.enabled for p in self.manager.plugins)

    def choose_assessment_archetype(self,value,workshop=False):
        self.archetype.setCurrentText(value);self.select_archetype(value)
        self.hover_assessment.signature=None
        plugin=next((p for p in self.manager.plugins if p.id=='pricing'),None)
        if plugin and not workshop:self.hover_assessment.present(self.backend.window,self.snapshot,plugin)
        self.record_assessment_feedback('archetype',workshop=workshop,clicked=True)

    def paste_assess(self):
        self.tooltip_input.setPlainText(QApplication.clipboard().text())
        self.assess()

    def select_archetype(self, value):
        plugin = next((p for p in self.manager.plugins if p.id == 'pricing'), None)
        if plugin:
            plugin.settings['archetype'] = value
            self.save()
            try:
                item = parse_item(self.tooltip_input.toPlainText())
                if plugin.enabled and item.rarity == 'Rare':
                    self.result.show_rare(item, rate_rare(item, value),value)
            except ValueError:
                pass

    def run_worker(self, operation, callback):
        self.assess_button.setEnabled(False)
        future = self.pool.submit(operation)
        def complete(f):
            try: payload = (True, f.result())
            except Exception as exc: payload = (False, str(exc))
            self.signals.done.emit(callback, payload)
        future.add_done_callback(complete)

    def worker_done(self, callback, payload):
        if callback.__name__ == 'show_stash_prices':
            self.stash_pricing_pending = False
            if not payload[0]:
                self.stash_price_retry=time.monotonic()+60
                self.stash_price_signature=None
        self.assess_button.setEnabled(True)
        ok, value = payload
        if ok: callback(value)
        else:
            self.result.setPlainText("Unavailable: " + value)
            self.note(value)

    def load_leagues(self):
        def receive(leagues):
            previous=self.economy_league()
            self.league.blockSignals(True);self.league.clear()
            for league in leagues:self.league.addItem(league.get('name',league['id']),league['id'])
            index=self.league.findData(previous)
            if index<0:index=self.league.findText(previous)
            if index>=0:self.league.setCurrentIndex(index)
            elif previous:self.league.addItem(previous,previous);self.league.setCurrentIndex(self.league.count()-1)
            self.league.blockSignals(False);self.change_economy_league()
            self.note('Economy leagues refreshed.')
        self.run_worker(self.economy.leagues,receive)

    def assess(self):
        if not self.workshop_enabled():return
        plugin = next((p for p in self.manager.plugins if p.id == "pricing" and p.enabled), None)
        if not plugin:
            self.result.setPlainText("Enable Items & stash in Modules first.")
            return
        try:
            item = parse_item(self.tooltip_input.toPlainText())
            if item.rarity == "Rare":
                rating = rate_rare(item, plugin.settings["archetype"])
                self.result.show_rare(item, rating,plugin.settings['archetype'])
            elif item.rarity == "Unique":
                league = self.economy_league()
                category = self.category.currentText()
                self.result.setPlainText("Looking up matching unique variants…")
                self.run_worker(lambda: self.economy.unique(item, league, category), self.show_unique)
                self.save()
            else:
                self.result.setPlainText("This workshop currently handles uniques and identified rare equipment.")
        except Exception as exc:
            self.result.setPlainText(str(exc))

    def show_unique(self, value):
        if value.get('league')!=self.economy_league():return
        self.result.show_unique(value, self.currency_estimates.get('divine orb'))

    def preview_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.preview_check = QCheckBox("Use synthetic preview data")
        self.preview_check.toggled.connect(self.set_preview)
        layout.addWidget(self.preview_check)
        layout.addWidget(label("Switch this on, then enable individual visual modules in Modules. This is a rendering test, not in-game validation.", "muted", True))
        self.canvas = PreviewCanvas()
        layout.addWidget(self.canvas, 1)
        return page

    def set_preview(self, checked):
        for plugin in self.manager.plugins: plugin.stop()
        self.preview = checked
        self.live_reader.clear()
        self.visual_reader.clear()
        self.snapshot = Snapshot()
        self.overlay.hide()

    def settings_page(self):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,0,0,0);layout.setSpacing(12)
        economy=BrassFrame();box=QVBoxLayout(economy);box.setContentsMargins(18,16,18,18)
        box.addWidget(label('Economy','title'))
        box.addWidget(label('One league for ground, inventory, stash and unique prices.','muted',True))
        row=QHBoxLayout();row.addWidget(label('League'))
        self.league=QComboBox();self.league.setEditable(True)
        self.active_economy_league=self.config.get('league','')
        self.active_economy_league_name=self.config.get('league_name',self.active_economy_league)
        self.league.addItem(self.config.get('league_name',self.active_economy_league),self.active_economy_league)
        self.league.setPlaceholderText('Select or enter your league');row.addWidget(self.league,1)
        row.addWidget(button('Refresh leagues',self.load_leagues))
        box.addLayout(row);layout.addWidget(economy)
        self.league.activated.connect(lambda _:self.change_economy_league())
        self.league.lineEdit().editingFinished.connect(self.change_economy_league)
        game=BrassFrame();box=QVBoxLayout(game);box.setContentsMargins(18,16,18,18)
        box.addWidget(label('Path of Exile','title'))
        box.addWidget(label('Game installation','muted'))
        self.install_edit=QLineEdit(str(self.backend.install));row=QHBoxLayout();row.addWidget(self.install_edit,1)
        row.addWidget(button('Browse',self.browse_install));box.addLayout(row)
        self.install_edit.editingFinished.connect(self.recheck_install_if_changed)
        layout.addWidget(game)
        application=BrassFrame();box=QVBoxLayout(application);box.setContentsMargins(18,16,18,18)
        box.addWidget(label('Waymark','title'))
        self.remember_window=QCheckBox('Remember window size and position')
        self.remember_window.setChecked(self.config.get('remember_window',True))
        self.remember_window.toggled.connect(self.set_remember_window);box.addWidget(self.remember_window)
        box.addWidget(button('Open settings & logs',lambda:self.open_folder(self.data)))
        layout.addWidget(application);layout.addStretch();return page

    def set_remember_window(self,enabled):
        self.config['remember_window']=enabled;self.save()

    def economy_league(self):
        return self.active_economy_league

    def change_economy_league(self):
        text=self.league.currentText().strip();index=self.league.currentIndex()
        selected=self.league.currentData()if index>=0 and text==self.league.itemText(index)else text
        selected=selected or ''
        self.active_economy_league_name=text
        if selected==self.active_economy_league:
            self.save();return
        self.active_economy_league=selected
        self.stash_estimates={};self.unique_quotes={};self.currency_estimates={};self.prices_league=''
        self.stash_price_signature=None;self.stash_price_retry=0;self.stash_price_refresh_at=0
        self.enrichment_signature=None;self.enrich_stash();self.refresh_stash()
        for window in self.wealth_windows.values():window.hide()
        if self.result.kind.text().startswith('UNIQUE'):self.result.setPlainText('League changed. Assess the item again for updated prices.')
        self.save();self.note('Economy league: '+selected if selected else'Select a league in Settings to load prices.')

    def compatibility_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Exact-build matching", "cardTitle"))
        layout.addWidget(label("Memory features require a validated adapter for your executable. A repository's update date alone cannot verify compatibility.", "muted", True))
        self.compatibility_text = QTextEdit()
        self.compatibility_text.setReadOnly(True)
        layout.addWidget(self.compatibility_text, 1)
        row = QHBoxLayout()
        row.addWidget(button("Open module folder", lambda: self.open_folder(self.root / "plugins")))
        row.addWidget(button("Open profiles", lambda: self.open_folder(self.root / "profiles")))
        row.addWidget(button("Open settings & logs", lambda: self.open_folder(self.data)))
        layout.addLayout(row)
        self.fill_compatibility()
        return page

    def fill_compatibility(self):
        info = self.backend.info
        self.compatibility_text.setPlainText(
            f"INSTALLATION\n{self.backend.install}\nFound: {info['exists']}\nSteam build: {info['steam_build']}\nSHA-256: {info['sha256'] or 'unavailable'}\n\n"
            f"MEMORY INTEGRATION\n{self.backend.status}\nValidated adapter: {'Yes' if self.backend.adapter else 'No'}\n\n"
            "REFERENCE\nhttps://github.com/exApiTools/ExileApi-Compiled\n"
            "Offset-library commit: 55b23698ddfa23ed537d56a002fb3f399951a427\nUpdated: 2026-08-20\n\n"
            "AVAILABLE WITHOUT MEMORY\nItem-text parsing and rare equipment ratings.\nUnique estimates and league discovery require internet access.\n\n"
            "INDEPENDENT READER\nCurrent profile enables only its declared, checked capabilities.\n"
            "The application is read-only. Native offsets are kept in profile JSON.\n"
            "Terrain, local player vitals, buff records and entity lists were read in a hideout.\n"
            "Combat, projection and area/process transitions still need in-game checks.\n"
            "Current-generation preloads, loaded stash items were read live.\n"
            "Stash coverage depends on decoded items and currently loaded tabs.\n"
            "Personal/guild stash coverage depends on decoded tabs. No account-wide scan is claimed.\n\n"
            "MODULES\n" + ("\n".join(self.manager.errors) or "No module loading errors.")
        )

    def browse_install(self):
        path = QFileDialog.getExistingDirectory(self, "Path of Exile installation", str(self.backend.install))
        if path:
            self.install_edit.setText(path)
            self.recheck()

    def recheck_install_if_changed(self):
        if self.install_edit.text().strip()!=str(self.backend.install):self.recheck()

    def recheck(self):
        enabled={p.id:p.enabled for p in self.manager.plugins}
        self.panic()
        for plugin in self.manager.plugins:plugin.enabled=enabled[plugin.id]
        self.update_module_states()
        try:
            self.backend = Backend(self.root / "profiles", Path(self.install_edit.text()))
            self.save()
            self.fill_compatibility()
            self.note("Installation and memory profiles rechecked.")
        except Exception as exc:
            self.note("Recheck failed: " + str(exc))

    def open_folder(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def note(self, text):
        self.notice.setText(text)
        logging.info(text)

    def native_mask(self, snapshot):
        return self.map_overlap.get(snapshot)

    def panic(self):
        for plugin in self.manager.plugins:
            plugin.enabled = False
            plugin.stop()
        self.overlay.hide()
        self.route_legend.hide()
        for panel in self.floating_panels.values():panel.hide()
        for window in self.wealth_windows.values():window.hide()
        self.hover_assessment.clear()
        self.configure_rare_hotkey()
        self.configure_feedback_hotkeys()
        self.map_overlap.stop()
        self.update_module_states()
        self.note("All modules stopped.")

    def save_route_legend(self,x,y):
        plugin=next((p for p in self.manager.plugins if p.id=='routes'),None)
        if plugin:
            plugin.settings['legend_position']=[x,y]
            plugin.settings['legend_anchor']='Custom position'
            self.save()

    def save_wealth_position(self,scope,x,y):
        plugin=next((p for p in self.manager.plugins if p.id=='pricing'),None)
        if plugin:
            positions=dict(plugin.settings.get('summary_positions',{}))
            positions[scope]=[x,y];plugin.settings['summary_positions']=positions
            self.save()

    def save_wealth_size(self,scope,width,height):
        plugin=next((p for p in self.manager.plugins if p.id=='pricing'),None)
        if plugin:
            sizes=dict(plugin.settings.get('summary_sizes',{}));sizes[scope]=[width,height]
            plugin.settings['summary_sizes']=sizes;self.save()

    def exclude_buff(self,name):
        plugin=next((p for p in self.manager.plugins if p.id=='uptime'),None)
        if plugin:
            names=[n for n in plugin.settings.get('exclusions','').splitlines()if n.strip()]
            if name not in names:names.append(name)
            plugin.settings['exclusions']='\n'.join(names);self.save()
            if self.selected_plugin_id=='uptime':self.select_module(plugin)

    def save_overlay_setting(self,identity,key,value):
        plugin=next((p for p in self.manager.plugins if p.id==identity),None)
        if plugin:
            plugin.settings[key]=value;self.save()

    def save_assessment_size(self,mode,width,height):
        plugin=next((p for p in self.manager.plugins if p.id=='pricing'),None)
        if plugin:
            sizes=dict(plugin.settings.get('assessment_sizes',{}));sizes[mode]=[width,height]
            self.save_overlay_setting('pricing','assessment_sizes',sizes)

    def configure_rare_hotkey(self):
        plugin=next((p for p in self.manager.plugins if p.id=='pricing'),None)
        active=bool(plugin and plugin.enabled and plugin.settings.get('rare_enabled',True)and not self.preview and self.backend.window.foreground)
        text=plugin.settings.get('rare_hotkey','Alt+F')if plugin else'Alt+F'
        signature=(active,text)
        if signature==self.rare_hotkey_signature:return
        self.rare_hotkey_signature=signature
        if os.name!='nt':return
        import ctypes
        if self.rare_hotkey_registered:ctypes.windll.user32.UnregisterHotKey(int(self.winId()),3)
        self.rare_hotkey_registered=False
        if active:
            try:flags,key=hotkey_parts(text)
            except ValueError as exc:self.note(str(exc));return
            self.rare_hotkey_registered=bool(ctypes.windll.user32.RegisterHotKey(int(self.winId()),3,flags,key))
            if not self.rare_hotkey_registered:self.note(text+' is in use. Choose another assessment shortcut in the pricing cog.')

    def expand_hovered_item(self,retries=12,position=None,started=None):
        from PySide6.QtGui import QCursor
        if position is None:position=QCursor.pos()
        if started is None:
            started=time.monotonic();logging.info('ALTF_DIAG hotkey received')
        if (QCursor.pos()-position).manhattanLength()>8:return
        plugin=next((p for p in self.manager.plugins if p.id=='pricing'),None)
        s=self.snapshot
        if (not plugin or not plugin.enabled or not plugin.settings.get('rare_enabled',True)or self.preview or
            not self.backend.window.foreground or s.source!='live'or not s.fresh()or not s.in_game or s.loading):return
        data=self.connections.hover_tracker.current(position,time.monotonic(),s)
        if not data:
            data=s.hovered_item
            if data and data.get('hover_captured_at',s.captured_at)<started:data=None
        if data and data.get('assessment_supported')is False:
            self.note('Rare assessment supports equipment only.');return
        if data:
            self.hover_assessment.expand(dict(data,_area=(s.area_id,getattr(s,'instance_key',None))),plugin.settings)
            self.hover_assessment.present(self.backend.window,s,plugin)
            from exile.hover_assessment import assess_data
            item,rating=assess_data(data,plugin.settings['archetype'])
            self.tooltip_input.setPlainText(item_text(item))
            from dataclasses import asdict
            from exile.sharing import clean_item
            self.latest_shared_item=dict(name=item.name,league=self.economy_league(),item=clean_item(asdict(item)),text=item_text(item))
            if self.workshop_enabled():self.result.show_rare(item,rating,plugin.settings['archetype'])
        elif retries:QTimer.singleShot(60,lambda:self.expand_hovered_item(retries-1,position,started))
        else:
            logging.info('ALTF_DIAG no tooltip after retry snapshot_age_ms=%.0f',1000*(time.monotonic()-s.captured_at));self.note('Hover an identified rare item in PoE to open its assessment.')

    def active_feedback_context(self):
        plugin=next((p for p in self.manager.plugins if p.id=='pricing'),None)
        if not plugin or not plugin.enabled or self.preview or not plugin.settings.get('rare_feedback',True):return None
        if (self.hover_assessment.isVisible()and self.hover_assessment.feedback_context and
            self.snapshot.source=='live'and self.snapshot.fresh()and self.snapshot.in_game and not self.snapshot.loading and
            window_is_foreground(self.backend.window.hwnd)):
            return self.hover_assessment.feedback_context
        focus=QApplication.focusWidget()
        if (self.isActiveWindow()and self.pages.currentIndex()==1 and self.result.feedback_context and
            not isinstance(focus,(QLineEdit,QTextEdit,QComboBox,QSpinBox))):
            return self.result.feedback_context
        return None

    def configure_feedback_hotkeys(self):
        # Feedback is exclusively clickable; never intercept game arrow keys.
        if self.feedback_hotkeys and os.name=='nt':
            import ctypes
            for identity in self.feedback_hotkeys:ctypes.windll.user32.UnregisterHotKey(int(self.winId()),identity)
        self.feedback_hotkeys.clear()

    def record_assessment_feedback(self,direction,workshop=False,clicked=False):
        if workshop:
            plugin=next((p for p in self.manager.plugins if p.id=='pricing'and p.enabled),None)
            context=self.result.feedback_context if plugin and self.pages.currentIndex()==1 and self.workshop_enabled()else None
        elif clicked:
            plugin=next((p for p in self.manager.plugins if p.id=='pricing'and p.enabled),None)
            context=self.hover_assessment.feedback_context if plugin and self.hover_assessment.isVisible()and self.snapshot.fresh()and self.snapshot.in_game and not self.snapshot.loading else None
        else:context=self.active_feedback_context()
        if context is None:return False
        league=self.economy_league()
        try:entry=self.feedback_history.record(context,direction,league,self.snapshot.area)
        except (OSError,ValueError)as exc:
            self.note('Could not save assessment feedback: '+str(exc));return False
        self.feedback_view.refresh(entry['id'])
        message='Saved: '+FEEDBACK_LABELS[direction]
        if self.hover_assessment.isVisible()and not workshop:self.hover_assessment.feedback_saved(message)
        self.note(message+' · Assessment history has the copyable example.')
        return True

    def nativeEvent(self, event_type, message):
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == 1:
                self.panic()
                return True, 0
            if msg.message == 0x0312 and msg.wParam == 3:
                self.expand_hovered_item()
                return True,0
        return super().nativeEvent(event_type, message)

    def tick(self):
        tick_started=time.perf_counter()
        interval_ms=(tick_started-getattr(self,'last_tick_started',tick_started))*1000
        self.last_tick_started=tick_started
        self.configure_rare_hotkey()
        pricing_settings=next((p.settings for p in self.manager.plugins if p.id=='pricing'),{})
        self.backend.item_assessment_archetype=pricing_settings.get('archetype','General')
        self.backend.inventory_assessment_enabled=bool(pricing_settings.get('inventory_rare_ratings',True) and any(p.id=='pricing' and p.enabled for p in self.manager.plugins))
        self.backend.item_link_enabled=bool(not self.preview and self.connections.client and self.connections.linked_share.isChecked())
        self.backend.item_prices_enabled=not self.preview and (any(p.id=='pricing'and p.enabled for p in self.manager.plugins) or self.backend.item_link_enabled)
        self.snapshot = preview_snapshot() if self.preview else self.live_reader.poll(self.backend)
        self.snapshot = copy(self.snapshot)
        radar = next((p for p in self.manager.plugins if p.id == 'radar'), None)
        routes = next((p for p in self.manager.plugins if p.id == 'routes'), None)
        map_plugin = next((p for p in self.manager.plugins if p.id == 'map_reveal'), None)
        need_health=bool(radar and radar.enabled and radar.settings.get('health_bars'))
        need_routes=bool(routes and routes.enabled)
        need_map=bool((map_plugin and map_plugin.enabled)or(radar and radar.enabled and
                      (radar.settings.get('monsters')or radar.settings.get('objects'))))
        self.snapshot.entities = self.visual_reader.poll(self.backend,self.snapshot,
            bool(not self.preview and (need_health or need_routes or need_map) and self.backend.window.foreground),
            camera_only=not need_health)
        self.snapshot.camera=self.visual_reader.camera(self.snapshot)
        if self.snapshot.camera and self.snapshot.camera.get('player_world') is not None:
            self.snapshot.player_world=self.snapshot.camera['player_world']
        self.snapshot.map_transform,self.snapshot.map_captured_at=self.visual_reader.map_pose(self.snapshot)
        self.snapshot.map_transform = self.map_motion.sample(self.snapshot)
        self.entity_motion.health_delay = radar.settings.get('health_smoothing',8)/1000 if radar else .008
        self.snapshot.entities = self.entity_motion.sample(self.snapshot)
        map_plugin = next((p for p in self.manager.plugins if p.id == 'map_reveal'), None)
        self.map_overlap.configure(self.backend.window, self.snapshot,
            bool(not self.preview and map_plugin and map_plugin.enabled and map_plugin.settings.get('hide_native')),
            map_plugin.settings.get('native_margin', 6) if map_plugin else 6)
        self.enrich_stash()
        self.maybe_price_items()
        if self.pages.currentIndex()==3 and time.monotonic() - self.stash_refresh_at > 1:
            self.refresh_stash()
            self.stash_refresh_at = time.monotonic()
        s = self.snapshot
        marks = []
        if not hasattr(self,'static_frames'):self.static_frames={}
        frame_key=(self.backend.window.pid,getattr(s,'visual_context',{}).get('key'))
        for plugin in self.manager.plugins:
            if not plugin.enabled or not plugin.requires <= s.capabilities:
                continue
            if plugin.requires and (not (s.fresh()or s.visual_fresh()) or not s.in_game or s.loading):
                continue
            try:
                plugin_started=time.perf_counter()
                if not s.fresh()and s.visual_fresh()and plugin.id in ('pricing','preload','uptime'):
                    previous=self.static_frames.get(plugin.id)
                    if previous and previous[0]==frame_key and time.monotonic()-previous[1]<=.6:marks.extend(previous[2])
                    continue
                generated=plugin.tick(s,self);marks.extend(generated)
                if plugin.id in ('pricing','preload','uptime'):self.static_frames[plugin.id]=(frame_key,s.captured_at,generated)
                cost=(time.perf_counter()-plugin_started)*1000
                if cost>20 and time.monotonic()-getattr(plugin,'cost_log_at',0)>10:
                    plugin.cost_log_at=time.monotonic();logging.info('Slow overlay module: %s %.1f ms',plugin.id,cost)
            except Exception as exc:
                plugin.error = str(exc)
                plugin.enabled = False
                logging.exception("Module failed: %s", plugin.id)
        if self.preview:self.canvas.marks=marks;self.canvas.update()
        else:
            key=(self.backend.window.pid,self.backend.window.hwnd,id(self.backend.adapter),tuple((p.id,p.enabled)for p in self.manager.plugins))
            marks=self.presentation.resolve(s,marks,key,self.backend.window.foreground)
        pricing=next((p for p in self.manager.plugins if p.id=='pricing'),None)
        if self.preview:self.hover_assessment.clear()
        elif not((s.source=='disconnected'and self.presentation.frame or not s.fresh()and s.visual_fresh())and self.hover_assessment.isVisible()):
            self.hover_assessment.present(self.backend.window,s,pricing)
        self.configure_feedback_hotkeys()
        if self.preview:
            self.overlay.hide()
            self.route_legend.hide()
            for panel in self.floating_panels.values():panel.hide()
            for window in self.wealth_windows.values():window.hide()
        else:
            legend=next((m for m in marks if m.kind=='route_legend'),None)
            wealth=next((m for m in marks if m.kind=='wealth_panel'),None)
            present=set();default_y=wealth.y if wealth else 0
            if wealth:
                for section in wealth.payload['sections']:
                    scope=section['scope'];present.add(scope)
                    self.wealth_windows[scope].present_summary(self.backend.window,section,wealth.payload['settings'],default_y)
                    default_y+=self.wealth_windows[scope].height()+8
            for scope,window in self.wealth_windows.items():
                if scope not in present:window.hide()
            was_visible=self.overlay.isVisible()
            for identity,panel in self.floating_panels.items():
                mark=next((m for m in marks if m.kind==('preload_panel'if identity=='preload'else'uptime_panel')),None)
                if mark and identity=='uptime':mark.payload['uptime']=True
                panel.present(self.backend.window,mark)
            self.overlay.present(self.backend.window,[m for m in marks if m.kind not in ('route_legend','wealth_panel','preload_panel','uptime_panel')])
            self.route_legend.present(self.backend.window,legend)
            if not was_visible and self.overlay.isVisible() and self.route_legend.isVisible():
                self.route_legend.raise_()
            if not was_visible:
                for window in self.wealth_windows.values():
                    if window.isVisible():window.raise_()
        radar = next((p for p in self.manager.plugins if p.id == 'radar'), None)
        elapsed_ms=(time.perf_counter()-tick_started)*1000
        samples=getattr(self,'tick_samples',[]);samples.append(elapsed_ms);self.tick_samples=samples[-1200:]
        intervals=getattr(self,'tick_intervals',[]);intervals.append(interval_ms);self.tick_intervals=intervals[-1200:]
        if time.monotonic()-getattr(self,'timing_log_at',0)>10:
            self.timing_log_at=time.monotonic()
            ordered=sorted(self.tick_samples)
            logging.info('Overlay timing: tick p50=%.1f p95=%.1f max=%.1f ms; snapshot age=%.1f ms; entities=%d',
                ordered[len(ordered)//2],ordered[min(len(ordered)-1,int(len(ordered)*.95))],max(ordered),
                (time.monotonic()-s.captured_at)*1000,len(s.entities))
            self.tick_samples=[]
            intervals=sorted(self.tick_intervals)
            logging.info('Overlay scheduling: p50=%.1f p95=%.1f max=%.1f ms',intervals[len(intervals)//2],intervals[int((len(intervals)-1)*.95)],max(intervals));self.tick_intervals=[]
        rates=[int(p.settings.get('refresh_rate','120 fps').split()[0]) for p in (radar,routes,map_plugin) if p and p.enabled]
        self.visual_reader.interval=1/max(rates) if rates else 1/120
        interval = max(7, round(1000/max(rates))) if rates and (self.preview or self.backend.window.foreground) else 16
        if self.timer.interval() != interval:
            self.timer.setInterval(interval)
        status = "Synthetic preview · input disabled" if self.preview else self.backend.status
        if map_plugin and map_plugin.enabled and self.map_overlap.error:
            status += ' · Native map overlap detection unavailable'
        if not self.preview and s.source == "live" and s.in_game:
            status += f" · Life {s.life:,.0f} · Mana {s.mana:,.0f}/{getattr(s, 'total_mana', s.max_mana):,.0f}"
        self.status_label.setText(status)
        if time.monotonic()-getattr(self,'module_ui_at',0)>.25:
            self.module_ui_at=time.monotonic();self.update_module_states()

    def save(self):
        self.config.update({"plugins": self.manager.serialize(), "installation": str(self.backend.install),
                            "league": self.economy_league(),"league_name":self.active_economy_league_name})
        if self.config.get('remember_window',True):
            rect=self.normalGeometry()if self.isMaximized()else self.geometry()
            self.config['window_geometry']=[rect.x(),rect.y(),rect.width(),rect.height()]
        write_json(self.config_path, self.config)

    def closeEvent(self, event):
        panel=self.inspector.widget() if hasattr(self,'inspector') else None
        if panel and hasattr(panel,'autosave_timer') and panel.autosave_timer.isActive():
            panel.autosave_timer.stop();panel.accept()
        self.timer.stop()
        self.connections.shutdown()
        self.live_reader.close()
        self.visual_reader.close()
        enabled={p.id:p.enabled for p in self.manager.plugins}
        self.panic()
        for plugin in self.manager.plugins:plugin.enabled=enabled[plugin.id]
        self.save()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.overlay.close()
        self.route_legend.close()
        for panel in self.floating_panels.values():panel.close()
        for window in self.wealth_windows.values():window.close()
        self.hover_assessment.close()
        if self.hotkey_registered:
            import ctypes
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), 1)
        event.accept()


def main():
    logging.basicConfig(filename=data_root() / "obsidian.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if "--check-package" in sys.argv:
        destination = Path(sys.argv[sys.argv.index("--check-package") + 1])
        manager = PluginManager(resource_root() / "plugins")
        manager.discover()
        class NoInput:
            def key(self, key):
                raise AssertionError("Synthetic data attempted gameplay input")
            def note(self, text):
                pass
        checks = {}
        for plugin in manager.plugins:
            try:
                sample = preview_snapshot()
                if plugin.requires <= sample.capabilities:
                    checks[plugin.id] = {"marks": len(plugin.tick(sample, NoInput())), "default_off": not plugin.enabled}
                else:
                    checks[plugin.id] = {"default_off": not plugin.enabled, "live_only": True}
            except Exception as exc:
                manager.errors.append(f"{plugin.id}: {exc}")
        for plugin in manager.plugins:plugin.stop()
        icon_count=0
        if any(plugin.id=='radar'for plugin in manager.plugins):
            from exile.map_icons import catalog,original_image
            icon_count=len(catalog())
            missing=[key for key in catalog()if original_image(key).isNull()]
            if not icon_count or missing:manager.errors.append('Bundled map icons missing or unreadable: '+repr(missing))
        from exile.theme import skin_image
        skin_assets=['panel.png','texture.png','check-on.png','check-off.png','arrow-down.png','arrow-up.png']
        skin_assets += [f'{kind}-{state}.png'for kind in ('button','row','field','tab')for state in ('normal','active','pressed')]
        skin_assets += [f'icon-{name}.png'for name in ('modules','workshop','history','search','map','routes','radar','alerts','stash','hazards','hourglass','cog')]
        missing_skin=[name for name in skin_assets if skin_image(name).isNull()]
        if missing_skin:manager.errors.append('Bundled UI artwork missing or unreadable: '+repr(missing_skin))
        write_json(destination, {"plugins": checks, "icons":icon_count,"skin_assets":len(skin_assets),"errors": manager.errors})
        sys.exit(1 if manager.errors else 0)
    app = QApplication(sys.argv)
    app.setApplicationName("Waymark")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    if '--internet-host'in sys.argv:
        QTimer.singleShot(0,lambda:(window.navigate(6),window.connections.host_internet()))
    if "--screenshot" in sys.argv:
        index = sys.argv.index("--screenshot")
        destination = sys.argv[index + 1]
        QTimer.singleShot(2000, lambda: (window.grab().save(destination), window.close()))
    sys.exit(app.exec())
