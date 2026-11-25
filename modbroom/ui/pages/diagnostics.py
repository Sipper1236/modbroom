"""Duplicates, conflicts, broken files, script risks, game rules, crash logs."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QTabWidget, QVBoxLayout, QHBoxLayout, QWidget, QTableWidget,
                               QTableWidgetItem, QHeaderView, QPushButton, QLabel, QMessageBox)
from . import Page
from ..widgets import tone_item
from .. import theme


def _qcolor(c):
    return QColor(c)


def _name(p):
    return (p or '').replace('\\', '/').rsplit('/', 1)[-1]


RULE_LABELS = {
    'onedrive_documents': 'OneDrive Documents',
    'path_too_long': 'Path too long',
    'dotfile': 'Hidden dotfile',
    'trailing_dot_space': 'Trailing dot or space',
    'empty_file': 'Empty file',
    'script_too_deep': 'Script too deep',
    'loose_python': 'Loose .py file',
    'ignored_files': 'Ignored file type',
}


def _rule_label(rule):
    """Turn an internal rule id into something a player can act on."""
    if not rule:
        return 'Rule'
    return RULE_LABELS.get(rule, rule.replace('_', ' ').capitalize())


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

    def fill(self, rows, tones=None):
        """rows: list of tuples. tones: optional dict {(row, col): (color, bold)}."""
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                item = QTableWidgetItem(str(cell))
                tone = (tones or {}).get((r, c))
                if tone:
                    color, bold = tone
                    if color:
                        item.setForeground(_qcolor(color))
                    if bold:
                        f = item.font(); f.setBold(True); item.setFont(f)
                self.setItem(r, c, item)
        note = getattr(self, 'empty_note', None)
        if note is not None:
            note.setVisible(self.rowCount() == 0)
        self.autosize()

    def autosize(self):
        """Size the table to its content so a 2-row table is not a huge empty box."""
        row_h = self.rowHeight(0) if self.rowCount() else 28
        head_h = self.horizontalHeader().height() + 2
        want = head_h + row_h * self.rowCount() + 6
        self.setMinimumHeight(min(want, 150))
        self.setMaximumHeight(max(min(want, 560), 120))


class DiagnosticsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.header('Diagnostics', 'Everything ModBroom thinks is wrong, grouped by cause. Nothing is changed until you act.')
        self.tabs = QTabWidget()
        self.layout_.addWidget(self.tabs, 1)

        self.dupes = _Table(['Duplicate files (keep one)', ''])
        self.dupes.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tabs.addTab(self._wrap(self.dupes, 'Quarantine selected duplicate copies', self._quar_dupes,
                                    empty_text='No byte-identical or same-resource duplicates found.'), 'Duplicates')

        self.conflicts = _Table(['Resource', 'Winner (loads last)', 'Loses to it'])
        self.tabs.addTab(self._wrap(self.conflicts, None, None,
                                    empty_text='No two packages claim the same resource.'), 'Conflicts')

        self.broken = _Table(['File', 'Problem'])
        self.tabs.addTab(self._wrap(self.broken, 'Quarantine selected broken files', self._quar_broken, paths_col=0,
                                    empty_text='Every package parsed cleanly.'), 'Broken')

        self.scripts = _Table(['File', 'Level', 'Why'])
        self.tabs.addTab(self._wrap(self.scripts, 'Quarantine selected scripts', self._quar_scripts, paths_col=0,
                                    empty_text='No risky patterns found in any .ts4script.'), 'Script risks')

        self.rules = _Table(['Rule', 'File', 'What to do'])
        self.tabs.addTab(self._wrap(self.rules, None, None,
                                    empty_text='No loading-rule problems detected.'), 'Game rules')

        crash = QWidget()
        cl = QVBoxLayout(crash)
        self.crash_summary = QLabel('No crash logs analysed yet.')
        self.crash_summary.setObjectName('muted')
        self.crash_summary.setWordWrap(True)
        cl.addWidget(self.crash_summary)
        self.suspects = _Table(['Suspect', 'Score', 'Why'])
        cl.addWidget(self.suspects, 1)
        self.tabs.addTab(crash, 'Crash logs')

    def _wrap(self, table, button_label, handler, paths_col=None, empty_text=None):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        # keep the table at the top; leftover space falls below it instead of
        # stretching a two-row table across the whole page
        lay.addWidget(table, 0, Qt.AlignTop)
        if empty_text:
            note = QLabel(empty_text)
            note.setObjectName('muted')
            note.setWordWrap(True)
            note.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            note.setContentsMargins(2, 8, 2, 0)
            note.setVisible(table.rowCount() == 0)
            table.empty_note = note
            lay.addWidget(note)
        lay.addStretch(1)
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
        tones = {}
        for idx, c in enumerate(f.get('conflicts', [])):
            winner = _name(c.get('winner') or (c.get('load_order') or [c['files'][-1]])[-1])
            losers = ', '.join(_name(p) for p in c.get('losers', [])) or '—'
            rows.append((c['tgi'], winner + '   (of ' + str(len(c['files'])) + ')', losers))
            tones[(idx, 1)] = (theme.GOOD, True)
            tones[(idx, 2)] = (theme.MUTED, False)
        self.conflicts.fill(rows, tones)
        nl = len(f.get('not_loaded') or [])
        if f.get('resource_cfg'):
            self.conflicts.setToolTip('Load order from Resource.cfg: %s. %d package(s) match no PackedFile pattern and are never loaded.' % (f['resource_cfg'], nl))
        elif nl:
            self.conflicts.setToolTip('No Resource.cfg found — default order used. %d package(s) match no pattern.' % nl)

        rows = []
        for i in f.get('integrity', []):
            rows.append((_name(i['file']), i.get('error', '')))
        for i in f.get('parse_errors', []):
            rows.append((_name(i['file']), i.get('error', '')))
        tones = {(i, 0): (theme.BAD, True) for i in range(len(rows))}
        self.broken.fill(rows, tones)
        for i, (path, _) in enumerate(rows):
            self.broken.item(i, 0).setData(Qt.UserRole, path)

        rows = []
        tones = {}
        for idx, i in enumerate(f.get('script_risks', [])):
            rows.append((_name(i['file']), i.get('level', ''), i.get('msg', '')))
            color = theme.SEVERITY_COLORS.get(i.get('level'), theme.MUTED)
            tones[(idx, 1)] = (color, True)
        self.scripts.fill(rows, tones)
        for i, (path, _lvl, _msg) in enumerate(rows):
            self.scripts.item(i, 0).setData(Qt.UserRole, path)

        gr = self.state.get('last_game_rules') or []
        gtones = {}
        for idx, g in enumerate(gr):
            gtones[(idx, 0)] = (theme.SEVERITY_COLORS.get(g.get('level'), theme.MUTED), True)
        self.rules.fill([(_rule_label(g.get('rule')), _name(g.get('file', '')), g.get('detail', '')) for g in gr], gtones)

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
