"""Compact, clickable feedback shared by workshop and pinned assessments."""
from PySide6.QtWidgets import QHBoxLayout,QPushButton,QMenu
from PySide6.QtCore import Qt
from exile.rare_scoring import PROFILES

def controls(layout,feedback,archetype):
    row=QHBoxLayout();row.setSpacing(4);buttons=[]
    for direction,title in [('higher','Higher'),('lower','Lower'),('correct','Good')]:
        button=QPushButton(title);button.setToolTip('This item should score '+title.lower()if direction!='correct'else'This rating looks right')
        button.clicked.connect(lambda checked=False,direction=direction:feedback.emit(direction))
        row.addWidget(button);buttons.append(button)
    build=QPushButton('Build…');menu=QMenu(build)
    menu.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    menu.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
    for name in ['General']+[n for n in PROFILES if n!='Balanced']:
        action=menu.addAction(name);action.triggered.connect(lambda checked=False,name=name:archetype.emit(name))
    build.setMenu(menu);row.addWidget(build);row.addStretch();layout.addLayout(row)
    return buttons,build
