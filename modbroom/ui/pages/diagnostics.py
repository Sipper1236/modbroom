"""Duplicates, conflicts, broken files, script risks, game rules, crash logs."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QTabWidget, QVBoxLayout, QHBoxLayout, QWidget, QTableWidget,
                               QTableWidgetItem, QHeaderView, QPushButton, QLabel, QMessageBox)
from . import Page


def _name(p):
    return (p or '').replace('\\', '/').rsplit('/', 1)[-1]


class _Table(QTableWidget):
    def __init__(self, headers):
        super().__init__(0, len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(headers)):
            self.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)

    def fill(self, rows):
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                self.setItem(r, c, QTableWidgetItem(str(cell)))


class DiagnosticsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.header('Diagnostics', 'Everything ModBroom thinks is wrong, grouped by cause. Nothing is changed until you act.')
        self.tabs = QTabWidget()
        self.layout_.addWidget(self.tabs, 1)

        self.dupes = _Table(['Duplicate files (keep one)', ''])
        self.dupes.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tabs.addTab(self._wrap(self.dupes, 'Quarantine selected duplicate copies', self._quar_dupes), 'Duplicates')

        self.conflicts = _Table(['Resource', 'Winner (loads last)', 'Loses to it'])
        self.tabs.addTab(self._wrap(self.conflicts, None, None), 'Conflicts')

        self.broken = _Table(['File', 'Problem'])
        self.tabs.addTab(self._wrap(self.broken, 'Quarantine selected broken files', self._quar_broken, paths_col=0), 'Broken')

        self.scripts = _Table(['File', 'Level', 'Why'])
        self.tabs.addTab(self._wrap(self.scripts, 'Quarantine selected scripts', self._quar_scripts, paths_col=0), 'Script risks')

        self.rules = _Table(['Rule', 'File', 'What to do'])
        self.tabs.addTab(self._wrap(self.rules, None, None), 'Game rules')

        crash = QWidget()
        cl = QVBoxLayout(crash)
        self.crash_summary = QLabel('No crash logs analysed yet.')
        self.crash_summary.setObjectName('muted')
        self.crash_summary.setWordWrap(True)
        cl.addWidget(self.crash_summary)
        self.suspects = _Table(['Suspect', 'Score', 'Why'])
        cl.addWidget(self.suspects, 1)
        self.tabs.addTab(crash, 'Crash logs')

    def _wrap(self, table, button_label, handler, paths_col=None):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(table, 1)
        if button_label:
            row = QHBoxLayout()
            btn = QPushButton(button_label)
            btn.setObjectName('danger')
            btn.clicked.connect(handler)
            row.addWidget(btn)
            row.addStretch(1)
            lay.addLayout(row)
        return w

    def _selected_paths(self, table, col):
        out, seen = [], set()
        for idx in table.selectionModel().selectedRows():
            item = table.item(idx.row(), col)
            if not item:
                continue
            p = item.data(Qt.UserRole) or item.text()
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def _quar_dupes(self):
        paths = []
        for idx in self.dupes.selectionModel().selectedRows():
            p = self.dupes.item(idx.row(), 0).data(Qt.UserRole)
            if p:
                paths.append(p)
        self._quarantine(paths)

    def _quar_broken(self):
        self._quarantine(self._selected_paths(self.broken, 0))

    def _quar_scripts(self):
        self._quarantine(self._selected_paths(self.scripts, 0))

    def _quarantine(self, paths):
        if not paths:
            QMessageBox.information(self, 'Nothing selected', 'Select the rows to quarantine first.')
            return
        if QMessageBox.question(self, 'Quarantine',
                                'Move %d file(s) out of Mods? They can be restored from the Tools page.' % len(paths)) != QMessageBox.Yes:
            return
        from .. import store
        store.quarantine_files(self.state, paths, 'diagnostics')
        self.window.refresh_all()
        self.window.statusBar().showMessage('Quarantined %d file(s)' % len(paths), 5000)

    def refresh(self):
        f = self.state.get('last_findings') or {}
        if not f:
            for t in (self.dupes, self.conflicts, self.broken, self.scripts, self.rules):
                t.setRowCount(0)
            self.crash_summary.setText('No scan yet — run one from the sidebar.')
            self.suspects.setRowCount(0)
            return

        dup_rows = []
        for d in f.get('duplicates', []):
            keeper = d['files'][0]
            for extra in d['files'][1:]:
                dup_rows.append((extra, 'same content as %s' % _name(keeper)))
        self.dupes.setRowCount(len(dup_rows))
        for i, (path, why) in enumerate(dup_rows):
            item = QTableWidgetItem(_name(path))
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.dupes.setItem(i, 0, item)
            self.dupes.setItem(i, 1, QTableWidgetItem(why))
        self.dupes.setToolTip('Select the copies you want gone; ModBroom keeps the first in the list.')

        rows = []
        for c in f.get('conflicts', []):
            winner = _name(c.get('winner') or (c.get('load_order') or [c['files'][-1]])[-1])
            losers = ', '.join(_name(p) for p in c.get('losers', [])) or '—'
            rows.append((c['tgi'], winner + '   (of ' + str(len(c['files'])) + ')', losers))
        self.conflicts.fill(rows)
        nl = len(f.get('not_loaded') or [])
        if f.get('resource_cfg'):
            self.conflicts.setToolTip('Load order from Resource.cfg: %s. %d package(s) match no PackedFile pattern and are never loaded.' % (f['resource_cfg'], nl))
        elif nl:
            self.conflicts.setToolTip('No Resource.cfg found — default order used. %d package(s) match no pattern.' % nl)

        rows = []
        for i in f.get('integrity', []):
            rows.append((i['file'], i.get('error', '')))
        for i in f.get('parse_errors', []):
            rows.append((i['file'], i.get('error', '')))
        self.broken.fill(rows)
        for i, (path, _) in enumerate(rows):
            self.broken.item(i, 0).setData(Qt.UserRole, path)

        rows = []
        for i in f.get('script_risks', []):
            rows.append((i['file'], i.get('level', ''), i.get('msg', '')))
        self.scripts.fill(rows)
        for i, (path, _lvl, _msg) in enumerate(rows):
            self.scripts.item(i, 0).setData(Qt.UserRole, path)

        gr = self.state.get('last_game_rules') or []
        self.rules.fill([(g.get('rule', ''), g.get('file', ''), g.get('detail', '')) for g in gr])

        crash = self.state.get('last_crashlogs') or {}
        logs = crash.get('logs') or []
        suspects = crash.get('suspects') or []
        if not logs:
            self.crash_summary.setText('No crash logs found in the configured logs folder. That is good news.')
        else:
            self.crash_summary.setText('Read %d crash log(s) from your Sims 4 folder. Suspects ranked by how often they appear in the crash context.' % len(logs))
        srows = []
        for s in suspects[:20]:
            if isinstance(s, dict):
                srows.append((s.get('file') or s.get('name') or '?', s.get('score', ''), s.get('reason') or s.get('why') or ''))
            else:
                srows.append((str(s), '', ''))
        self.suspects.fill(srows)
