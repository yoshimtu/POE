"""Structured item assessment view shared by rare and unique results."""
from datetime import datetime

from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QProgressBar,QPushButton)

from exile.prices import format_price


def text(value, name='muted'):
    label = QLabel(value)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


class AssessmentView(QWidget):
    feedback=Signal(str)
    archetype_selected=Signal(str)
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        summary = QFrame()
        summary.setObjectName('card')
        row = QHBoxLayout(summary)
        row.setContentsMargins(20, 18, 20, 18)
        title = QVBoxLayout()
        self.kind = text('ITEM ASSESSMENT', 'eyebrow')
        self.name = text('Know what you found', 'cardTitle')
        self.base = text('Paste a copied item to see its strengths and trade references.')
        title.addWidget(self.kind)
        title.addWidget(self.name)
        title.addWidget(self.base)
        row.addLayout(title, 1)
        self.score = text('—', 'title')
        self.score.setMinimumWidth(125)
        self.score.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.score)
        layout.addWidget(summary)
        self.message = text('Enable Items & stash, then paste an item.')
        layout.addWidget(self.message)
        self.synergy = text('', 'badge')
        layout.addWidget(self.synergy)
        self.table = QTableWidget(0, 4)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setWordWrap(True)
        self.table.setStyleSheet('QTableWidget {background:#15140f; gridline-color:#4a3d28; border:1px solid #4a3d28; border-radius:0px;} QHeaderView::section {background:#272217; color:#bbac90; padding:9px; border:0;} QTableWidget::item {padding:7px;} QProgressBar {background:#272e39; border:0; border-radius:0px; text-align:center; color:#d5dddf; font-size:10px;} QProgressBar::chunk {background:#596e62; border-radius:0px;}')
        layout.addWidget(self.table, 1)
        self.footnote = text('Ratings describe modifier strength and synergy. Market estimates are not guaranteed sale prices.')
        self.footnote.setStyleSheet('color:#727e91; font-size:11px;')
        layout.addWidget(self.footnote)
        self.feedback_context=None;self.feedback_buttons=[]
        from exile.assessment_controls import controls
        self.feedback_buttons,self.build_button=controls(layout,self.feedback,self.archetype_selected)
        for button in self.feedback_buttons+[self.build_button]:button.setEnabled(False)

    def clear_feedback(self):
        self.feedback_context=None
        for button in self.feedback_buttons+[self.build_button]:button.setEnabled(False)

    def columns(self, names, first_stretch=True):
        self.table.clearContents()
        self.table.setColumnCount(len(names))
        self.table.setHorizontalHeaderLabels(names)
        header = self.table.horizontalHeader()
        for i in range(len(names)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if i == 0 or not first_stretch else QHeaderView.ResizeMode.ResizeToContents)

    def cell(self, row, column, value, color=None):
        item = QTableWidgetItem(str(value))
        item.setToolTip(str(value))
        if color:
            item.setForeground(QColor(color))
        self.table.setItem(row, column, item)

    def setPlainText(self, message):
        self.clear_feedback()
        self.kind.setText('ITEM ASSESSMENT')
        self.name.setText('Ready when you are')
        self.base.setText('Copy an item from PoE with Ctrl+C.')
        self.score.setText('—')
        self.message.setText(message)
        self.synergy.clear()
        self.table.setRowCount(0)

    def show_rare(self, item, rating,preference=None):
        assessment=rating.get('assessment',{})
        if preference is None:preference=assessment.get('best_fit','General')if assessment.get('selection')=='Selected'else'General'
        self.feedback_context=dict(item=item,rating=rating,preference=preference,source='workshop')
        for button in self.feedback_buttons+[self.build_button]:button.setEnabled(True)
        self.kind.setText('RARE  /  MODIFIER ASSESSMENT')
        self.name.setText(item.name)
        self.base.setText(f'{item.base}  ·  {item.item_class}')
        score = rating.get('score')
        self.score.setText(f'{score:g}<span style="font-size:14px;color:#8c96a8"> / 10</span>' if score is not None else 'Unrated')
        rows = list(rating.get('evaluated', []))
        if not rows:
            rows = [dict(mod=mod, category='Needs review', strength=None, tier=None, impact='Not scored') for mod in rating.get('unknown', [])]
        count = sum(row['strength'] is not None for row in rows)
        affix=rating.get('affix_score')
        affix_note=f' · Affixes {affix:g}/10'if affix is not None and affix!=score else''
        self.message.setText(f'{count}/{len(rows)} explicit modifiers evaluated  ·  {rating["confidence"]} confidence{affix_note}  ·  Affix quality heuristic, not a price')
        synergies = [reason.removeprefix('Synergy: ') for reason in rating.get('reasons', []) if reason.startswith('Synergy: ')]
        synergies+=rating.get('link_notes',[])
        synergies += [reason for reason in rating.get('reasons',[])if reason.startswith('Crafting:')]
        assessment=rating.get('assessment',{})
        if assessment:synergies.insert(0,('Best fit: 'if assessment['selection']=='Automatic'else'Selected profile: ')+assessment['best_fit'])
        self.synergy.setText('  +  '.join(synergies))
        self.columns(['Modifier', 'Role', 'Reference strength', 'Score effect'])
        self.table.setRowCount(len(rows) + len(item.special_mods))
        for index, row in enumerate(rows):
            self.cell(index, 0, row['mod'])
            tier = f" · T{row['tier']}" if row.get('tier') else ''
            self.cell(index, 1, row['category'] + tier)
            strength = row['strength']
            if strength is None:
                self.cell(index, 2, 'Not evaluated', '#d4ad73')
            else:
                meter = QProgressBar()
                meter.setRange(0, 100)
                meter.setValue(round(strength * 100))
                meter.setFormat('%v%')
                meter.setMaximumHeight(20)
                meter.setToolTip('Share of a reference roll; not a percentile or market value.')
                self.table.setCellWidget(index, 2, meter)
            self.cell(index, 3, row['impact'], '#9fc1aa' if strength is not None else '#d4ad73')
        for index, special in enumerate(item.special_mods, len(rows)):
            self.cell(index, 0, special['mod'])
            self.cell(index, 1, special['source'])
            self.cell(index, 2, 'Build/content dependent', '#a5b5cf')
            self.cell(index, 3, 'Context only')
        self.table.resizeRowsToContents()
        self.footnote.setText('Tier labels come from advanced copied text. Reference bars use approximate modifier-specific rolls. Context and unrecognized modifiers add no points; they can still affect value.')

    def show_unique(self, result, divine_chaos=None):
        self.clear_feedback()
        self.kind.setText('UNIQUE  /  MARKET REFERENCES')
        candidates = result['candidates']
        self.name.setText(candidates[0].get('name', 'Unique item') if candidates else 'No matching market data')
        stamp = datetime.fromtimestamp(result['fetched']).astimezone().strftime('%H:%M %Z')
        self.base.setText(f"{result['league']}  ·  Updated {stamp}  ·  poe.ninja")
        self.score.setText(f'{len(candidates)}<span style="font-size:12px;color:#8c96a8"> variants</span>')
        self.message.setText(result['message'])
        self.synergy.clear()
        self.columns(['Variant / base', 'Estimate', 'Links / corruption', 'Observations'])
        self.table.setRowCount(len(candidates))
        for index, row in enumerate(candidates):
            ratio = row['chaosValue'] / row['divineValue'] if row.get('divineValue', 0) > 0 else divine_chaos
            self.cell(index, 0, row.get('variant') or row.get('baseType') or 'Base variant')
            self.cell(index, 1, format_price(row.get('chaosValue'), ratio), '#e5c589')
            self.cell(index, 2, f"{row.get('links', 0)}L · {'Corrupted' if row.get('corrupted') else 'Uncorrupted'}")
            self.cell(index, 3, row.get('listingCount', row.get('count', 'Unknown')))
        self.table.resizeRowsToContents()
        self.footnote.setText('Compare rolls, links and corruption before pricing. Reference-only variants are identified above and may differ from your item.')
