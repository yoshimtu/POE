"""Keep Qt alive until test widgets and their worker owners are cleaned up."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import gc
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent

@pytest.fixture(scope='session',autouse=True)
def qt_session():
    app=QApplication.instance()or QApplication([])
    yield app
    app.closeAllWindows()
    # Dispose C++ widgets while their Python callbacks and QApplication still
    # exist; leaving them for interpreter shutdown can crash Qt on Windows.
    for widget in app.topLevelWidgets():widget.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()
