"""Copyable local feedback history for later, deliberate model tuning."""
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import(QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPlainTextEdit,QLineEdit)

from exile.feedback import FEEDBACK_LABELS


class FeedbackView(QWidget):
    def __init__(self,history,copy_text,notify):
        super().__init__();self.history=history;self.copy_text=copy_text;self.notify=notify
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        hint=QLabel('Use the assessment buttons to give feedback or choose a build. Saved examples can be copied for review.')
        hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout();self.count=QLabel();row.addWidget(self.count,1)
        for title,action in [('Copy selected',lambda:self.copy(True)),('Copy all',lambda:self.copy(False)),('Delete selected',self.delete_selected)]:
            button=QPushButton(title);button.clicked.connect(action);row.addWidget(button)
        layout.addLayout(row)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['When','Item','Score','Fit','Your feedback'])
        self.table.setStyleSheet('QTableWidget {background:#15140f;alternate-background-color:#1b222c;color:#ddd1b7;gridline-color:#4a3d28;border:1px solid #4a3d28;} QHeaderView::section {background:#272217;color:#bbac90;padding:8px;border:0;} QTableWidget::item {padding:5px;} QTableWidget::item:selected {background:#403b2d;color:#edd8b2;}')
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().hide()
        for column in range(5):self.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.Stretch if column==1 else QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.selection_changed);layout.addWidget(self.table,1)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(155)
        self.details.setStyleSheet('QPlainTextEdit {background:#15140f;color:#ddd1b7;border:1px solid #4a3d28;padding:8px;}')
        self.details.setPlaceholderText('Select an example to review its saved modifiers and explanation.')
        layout.addWidget(self.details)
        notes=QHBoxLayout();self.note=QLineEdit();self.note.setPlaceholderText('Optional explanation for the selected example…')
        notes.addWidget(self.note,1);save=QPushButton('Save note');save.clicked.connect(self.save_note);notes.addWidget(save)
        layout.addLayout(notes);self.refresh()

    def selected_ids(self):
        return[self.table.item(index.row(),0).data(Qt.ItemDataRole.UserRole)for index in self.table.selectionModel().selectedRows()]

    def refresh(self,select_id=None):
        selected=set(self.selected_ids())if self.table.rowCount()else set()
        if select_id:selected={select_id}
        self.table.blockSignals(True);self.table.clearSelection();self.table.setRowCount(len(self.history.examples))
        for row,entry in enumerate(reversed(self.history.examples)):
            score=entry['rating'].get('score');fit=entry['rating'].get('assessment',{}).get('best_fit','Review')
            stamp=datetime.fromisoformat(entry['updated_at']).astimezone().strftime('%b %d %H:%M')
            values=(stamp,' '.join(entry['item']['name'].split())+'\n'+entry['item']['base'],
                    f'{score:g}/10'if score is not None else'Unrated',fit,FEEDBACK_LABELS[entry['feedback']])
            for col,value in enumerate(values):
                cell=QTableWidgetItem(value);cell.setData(Qt.ItemDataRole.UserRole,entry['id']);self.table.setItem(row,col,cell)
            self.table.setRowHeight(row,46)
            if entry['id']in selected:
                from PySide6.QtCore import QItemSelectionModel
                self.table.selectionModel().select(self.table.model().index(row,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        self.table.blockSignals(False)
        counts={key:sum(e['feedback']==key for e in self.history.examples)for key in FEEDBACK_LABELS}
        self.count.setText(f"{len(self.history.examples)} examples · {counts['higher']} higher · {counts['lower']} lower · {counts['correct']} look right")
        self.selection_changed()

    def selection_changed(self):
        ids=self.selected_ids()
        if len(ids)!=1:self.details.clear();self.note.clear();return
        entry=next(e for e in self.history.examples if e['id']==ids[0]);rating=entry['rating']
        lines=[entry['item']['name']+' — '+entry['item']['base'],FEEDBACK_LABELS[entry['feedback']],
               f"Saved score: {rating.get('score')} · Build preference: {entry['build_preference']} · {entry['scorer_version']}",'']
        lines+=entry['item']['mods']
        lines+=['']+[reason for reason in rating.get('reasons',[])if reason.startswith('Synergy:')]
        if rating.get('unknown'):lines+=['Needs review: '+ '; '.join(rating['unknown'])]
        self.details.setPlainText('\n'.join(lines));self.note.setText(entry.get('note',''))

    def copy(self,selected):
        ids=self.selected_ids()if selected else None
        if not self.history.examples or(selected and not ids):self.notify('Select feedback examples to copy.');return
        self.copy_text(self.history.export(ids));self.notify('Assessment feedback copied. Paste it into this chat when you want tuning reviewed.')

    def save_note(self):
        ids=self.selected_ids()
        if len(ids)!=1:self.notify('Select one feedback example to add a note.');return
        try:self.history.set_note(ids[0],self.note.text())
        except OSError as exc:self.notify('Could not save the feedback note: '+str(exc));return
        self.notify('Feedback note saved.')

    def delete_selected(self):
        ids=self.selected_ids()
        if not ids:return
        try:self.history.delete(ids)
        except OSError as exc:self.notify('Could not delete examples: '+str(exc));return
        self.refresh();self.notify('Selected examples deleted.')
