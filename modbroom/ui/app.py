"""ModBroom window: sidebar + stacked pages."""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                               QListWidget, QListWidgetItem, QStackedWidget, QLabel, QPushButton,
                               QFrame, QStatusBar, QMessageBox)

from .. import core, store
from . import theme
from .pages import dashboard, library, diagnostics, fifty, tools, settings, companion

ASSETS = Path(__file__).resolve().parent.parent / 'assets'


def app_icon():
    icon = QIcon()
    svg = ASSETS / 'broom.svg'
    if svg.exists():
        renderer = QSvgRenderer(str(svg))
        for size in (16, 32, 48, 64, 128, 256):
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            renderer.render(p)
            p.end()
            icon.addPixmap(pm)
    return icon


class Bridge(QObject):
    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)


PAGES = [
    ('⌂  Dashboard', 'Overview and health', dashboard.DashboardPage),
    ('☰  Library', 'Every file found', library.LibraryPage),
    ('⚠  Diagnostics', 'Duplicates, conflicts, broken files', diagnostics.DiagnosticsPage),
    ('½  50/50 Test', 'Binary-search the broken mod', fifty.FiftyPage),
    ('🛠  Tools', 'Quarantine, backups, export, crash logs', tools.ToolsPage),
    ('✦  Companion', 'In-game mod + link status', companion.CompanionPage),
    ('⌘  Settings', 'Folders and options', settings.SettingsPage),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('ModBroom')
        self.setWindowIcon(app_icon())
        self.resize(1220, 800)
        self.setMinimumSize(1024, 640)

        theme.apply(QApplication.instance())
        self.state = store.load_state()
        self.bridge = Bridge()
        self.bridge.progress.connect(self._on_progress)
        self.bridge.done.connect(self._on_scan_done)
        self.bridge.failed.connect(self._on_scan_failed)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- sidebar ----------
        side = QFrame()
        side.setObjectName('sidebar')
        side.setFixedWidth(212)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(2)

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(34, 34))
        brand.addWidget(logo)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        b1 = QLabel('ModBroom')
        b1.setStyleSheet('font-size: 17px; font-weight: 700;')
        b2 = QLabel('Sims 4 mod doctor')
        b2.setObjectName('muted')
        b2.setStyleSheet('font-size: 10px;')
        bt.addWidget(b1); bt.addWidget(b2)
        brand.addLayout(bt)
        brand.addStretch(1)
        sl.addLayout(brand)
        sl.addSpacing(14)

        self.nav = QListWidget()
        self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setFocusPolicy(Qt.NoFocus)
        for name, _hint, _cls in PAGES:
            item = QListWidgetItem(name)
            item.setSizeHint(item.sizeHint().__class__(item.sizeHint().width(), 40))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._switch)
        sl.addWidget(self.nav, 1)

        self.scan_btn = QPushButton('Scan now')
        self.scan_btn.setObjectName('primary')
        self.scan_btn.setFixedHeight(38)
        self.scan_btn.clicked.connect(self.start_scan)
        sl.addWidget(self.scan_btn)
        self.side_status = QLabel('Idle')
        self.side_status.setObjectName('muted')
        self.side_status.setWordWrap(True)
        sl.addWidget(self.side_status)
        root.addWidget(side)

        # ---------- pages ----------
        self.stack = QStackedWidget()
        self.pages = []
        for name, hint, cls in PAGES:
            page = cls(self)
            self.pages.append(page)
            self.stack.addWidget(page)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage('Ready')
        self.nav.setCurrentRow(0)
        self.refresh_all()

    # ------------------------------------------------- scan plumbing
    def start_scan(self):
        if not self.state['settings'].get('mods_path'):
            QMessageBox.information(self, 'Pick a folder',
                                    'Choose your Sims 4 Mods folder in Settings first.')
            self.nav.setCurrentRow(len(PAGES) - 1)
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText('Scanning…')
        self.side_status.setText('Scanning…')
        self.statusBar().showMessage('Scanning ' + self.state['settings']['mods_path'])
        core.run_scan(self.state,
                      on_progress=lambda d, t, cur: self.bridge.progress.emit(d, t, cur),
                      on_done=lambda st: self.bridge.done.emit(st),
                      on_error=lambda e: self.bridge.failed.emit(str(e)))

    def _on_progress(self, done, total, current):
        self.side_status.setText('Scanning %d/%d\n%s' % (done, total, current[-46:]))

    def _on_scan_done(self, state):
        self.state = state
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText('Scan now')
        self.side_status.setText('Scan complete')
        self.statusBar().showMessage('Scan complete', 5000)
        self.refresh_all()

    def _on_scan_failed(self, message):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText('Scan now')
        self.side_status.setText('Scan failed')
        QMessageBox.critical(self, 'Scan failed', str(message))

    def _switch(self, row):
        self.stack.setCurrentIndex(row)
        page = self.pages[row]
        if hasattr(page, 'on_show'):
            page.on_show()

    def refresh_all(self):
        for page in self.pages:
            if hasattr(page, 'refresh'):
                try:
                    page.refresh()
                except Exception as exc:
                    print('refresh error in %s: %s' % (type(page).__name__, exc))

    def goto(self, index):
        self.nav.setCurrentRow(index)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('ModBroom')
    app.setOrganizationName('ModBroom')
    app.setWindowIcon(app_icon())
    theme.apply(app)
    win = MainWindow()
    win.show()
    return app.exec()
