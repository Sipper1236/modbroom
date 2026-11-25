"""Small shared widgets."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QLabel, QVBoxLayout, QWidget, QTableWidgetItem)
from . import theme


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()


class StatCard(QFrame):
    def __init__(self, label, value='—', tone='text'):
        super().__init__()
        self.setObjectName('card')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(2)
        self.value = QLabel(str(value))
        self.value.setObjectName('statNumber')
        self.caption = QLabel(label.upper())
        self.caption.setObjectName('statLabel')
        self.caption.setWordWrap(True)
        lay.addWidget(self.value)
        lay.addWidget(self.caption)

    def set_value(self, value, color=None):
        self.value.setText(str(value))
        accent = color or theme.TEXT
        self.value.setStyleSheet('color: %s;' % accent)
        if color:
            self.setStyleSheet(
                'QFrame#card { border: 1px solid %s; border-left: 3px solid %s; }'
                % (theme.PANEL3, color))
        else:
            self.setStyleSheet('')


class SectionHeader(QWidget):
    def __init__(self, title, subtitle=None):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(2)
        h = QLabel(title)
        h.setObjectName('h1')
        lay.addWidget(h)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName('muted')
            s.setWordWrap(True)
            lay.addWidget(s)


class EmptyState(QFrame):
    def __init__(self, title, hint):
        super().__init__()
        self.setObjectName('card')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 30, 24, 30)
        lay.setSpacing(6)
        t = QLabel(title)
        t.setObjectName('h2')
        t.setAlignment(Qt.AlignCenter)
        d = QLabel(hint)
        d.setObjectName('muted')
        d.setWordWrap(True)
        d.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(d)


def scan_in_thread(state, on_progress, on_done, on_error):
    """Run the scan inline on a worker thread (core.run_scan already threads, so we call it directly)."""
    import threading
    from .. import core

    def work():
        core.run_scan(state, on_progress=on_progress, on_done=on_done, on_error=on_error)

    threading.Thread(target=work, daemon=True).start()


def tone_item(text, color=None, bold=False, bg=None):
    """A table cell whose colour carries meaning (severity, winner, etc.)."""
    item = QTableWidgetItem(str(text))
    if color:
        item.setForeground(QColor(color))
    if bg:
        item.setBackground(QColor(bg))
    font = item.font()
    font.setBold(bold)
    item.setFont(font)
    return item
