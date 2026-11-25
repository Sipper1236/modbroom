"""50/50 bisect: let ModBroom move the files; you just tell it how the game behaved."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QCheckBox, QFrame,
                               QMessageBox, QScrollArea, QAbstractItemView)

from . import Page
from .. import bisect_bridge  # thin shim so UI never imports engine directly for state mutation


class FiftyPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.header('50/50 Test',
                    'ModBroom moves half your suspect mods out of the game, you launch Sims 4 and say whether it still breaks. '
                    'Each answer halves the pile. A backup is taken first and everything is reversible.')

        self.banner = QLabel('')
        self.banner.setWordWrap(True)
        self.banner.setObjectName('muted')
        self.layout_.addWidget(self.banner)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        self.body = QVBoxLayout(container)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)
        self.scroll.setWidget(container)
        self.layout_.addWidget(self.scroll, 1)

        # --- selection view (no active session) ---
        self.select_box = QWidget()
        sel = QVBoxLayout(self.select_box)
        sel.setContentsMargins(0, 0, 0, 0)
        sel.setSpacing(8)

        row = QHBoxLayout()
        self.select_all = QCheckBox('Select all')
        self.select_all.toggled.connect(self._toggle_all)
        row.addWidget(self.select_all)
        self.suggest_btn = QPushButton('Select suspects only')
        self.suggest_btn.setObjectName('ghost')
        self.suggest_btn.setToolTip('Broken files, risky scripts, duplicates and override conflicts from the last scan')
        self.suggest_btn.clicked.connect(self._select_suspects)
        row.addWidget(self.suggest_btn)
        row.addStretch(1)
        self.count_lbl = QLabel('0 selected')
        self.count_lbl.setObjectName('muted')
        row.addWidget(self.count_lbl)
        sel.addLayout(row)

        self.files = QListWidget()
        self.files.setSelectionMode(QAbstractItemView.NoSelection)
        self.files.setAlternatingRowColors(True)
        self.files.itemChanged.connect(self._on_item_changed)
        sel.addWidget(self.files, 1)
        self.files.setStyleSheet('QListWidget { padding: 4px; }')

        start_row = QHBoxLayout()
        self.start_btn = QPushButton('Start 50/50')
        self.start_btn.setObjectName('primary')
        self.start_btn.clicked.connect(self._start)
        start_row.addWidget(self.start_btn)
        start_row.addStretch(1)
        sel.addLayout(start_row)
        self.body.addWidget(self.select_box, 1)

        # --- session view (active bisect) ---
        self.session_box = QWidget()
        ses = QVBoxLayout(self.session_box)
        ses.setContentsMargins(0, 0, 0, 0)
        ses.setSpacing(10)
        self.step_lbl = QLabel('')
        self.step_lbl.setObjectName('h2')
        self.step_lbl.setWordWrap(True)
        ses.addWidget(self.step_lbl)
        self.detail_lbl = QLabel('')
        self.detail_lbl.setObjectName('muted')
        self.detail_lbl.setWordWrap(True)
        ses.addWidget(self.detail_lbl)
        self.enabled_list = QListWidget()
        self.disabled_list = QListWidget()
        cols = QHBoxLayout()
        for title, widget in (('Enabled right now (half)', self.enabled_list),
                              ('Moved out (other half)', self.disabled_list)):
            col = QVBoxLayout()
            lbl = QLabel(title)
            lbl.setObjectName('muted')
            col.addWidget(lbl)
            col.addWidget(widget, 1)
            cols.addLayout(col)
        ses.addLayout(cols, 1)
        verdict_row = QHBoxLayout()
        self.broken_btn = QPushButton('Still broken')
        self.broken_btn.setObjectName('danger')
        self.fixed_btn = QPushButton("It's fixed / problem gone")
        self.fixed_btn.setObjectName('primary')
        self.broken_btn.clicked.connect(lambda: self._verdict('broken'))
        self.fixed_btn.clicked.connect(lambda: self._verdict('fixed'))
        verdict_row.addWidget(self.broken_btn)
        verdict_row.addWidget(self.fixed_btn)
        verdict_row.addStretch(1)
        ses.addLayout(verdict_row)
        abort_row = QHBoxLayout()
        self.abort_btn = QPushButton('Stop and put everything back')
        self.abort_btn.setObjectName('ghost')
        self.abort_btn.clicked.connect(self._abort)
        abort_row.addWidget(self.abort_btn)
        abort_row.addStretch(1)
        ses.addLayout(abort_row)
        self.body.addWidget(self.session_box, 1)

        self.done_box = QWidget()
        done_l = QVBoxLayout(self.done_box)
        done_l.setContentsMargins(0, 0, 0, 0)
        done_l.setSpacing(8)
        self.done_title = QLabel('')
        self.done_title.setObjectName('h2')
        self.done_title.setWordWrap(True)
        self.done_detail = QLabel('')
        self.done_detail.setObjectName('muted')
        self.done_detail.setWordWrap(True)
        self.restore_all_btn = QPushButton('Put every file back')
        self.restore_all_btn.setObjectName('ghost')
        self.finish_btn = QPushButton('Keep the culprit out and finish')
        self.finish_btn.setObjectName('primary')
        done_l.addWidget(self.done_title)
        done_l.addWidget(self.done_detail)
        row2 = QHBoxLayout()
        row2.addWidget(self.finish_btn)
        row2.addWidget(self.restore_all_btn)
        row2.addStretch(1)
        done_l.addLayout(row2)
        done_l.addStretch(1)
        self.body.addWidget(self.done_box, 1)
        self.restore_all_btn.clicked.connect(self._restore_all)
        self.finish_btn.clicked.connect(self._finish)

        self._session_id = None

    # ------------------------------------------------ helpers
    def _suspect_paths(self):
        f = self.state.get('last_findings') or {}
        out = []
        def add(p):
            if p and p not in out:
                out.append(p)
        for i in f.get('integrity', []):
            add(i.get('file'))
        for i in f.get('parse_errors', []):
            add(i.get('file'))
        for i in f.get('script_risks', []):
            if i.get('level') in ('high', 'medium'):
                add(i.get('file'))
        for d in f.get('duplicates', []):
            for p in d.get('files', [])[1:]:
                add(p)
        for c in f.get('conflicts', []):
            for p in c.get('files', []):
                add(p)
        return out

    def _toggle_all(self, on):
        self.files.blockSignals(True)
        for i in range(self.files.count()):
            self.files.item(i).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.files.blockSignals(False)
        self._update_count()

    def _on_item_changed(self, item):
        self._update_count()

    def _select_suspects(self):
        suspects = set(self._suspect_paths())
        self.files.blockSignals(True)
        for i in range(self.files.count()):
            item = self.files.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in suspects else Qt.Unchecked)
        self.files.blockSignals(False)
        self._update_count()

    def _update_count(self):
        n = sum(1 for i in range(self.files.count()) if self.files.item(i).checkState() == Qt.Checked)
        self.count_lbl.setText('%d selected' % n)

    def _checked_paths(self):
        return [self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())
                if self.files.item(i).checkState() == Qt.Checked]

    def refresh(self):
        active = bisect_bridge.active_sessions(self.state)
        if active:
            self._show_session(active[-1])
            return
        done = [s for s in bisect_bridge.all_sessions(self.state) if s.get('status') == 'done']
        if done:
            self._show_done(done[-1])
            return
        self._show_selection()

    def _show_selection(self):
        self.select_box.show()
        self.session_box.hide()
        self.done_box.hide()
        self.select_all.setChecked(False)
        scan = self.state.get('last_scan') or {}
        files = scan.get('files', [])
        self.files.clear()
        suspects = set(self._suspect_paths())
        for f in files:
            f['_suspect'] = f['path'] in suspects
        for f in sorted(files, key=lambda x: (not x['_suspect'], x['rel'].lower())):
            label = f['rel']
            if f['_suspect']:
                label = '⚠  ' + label
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, f['path'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.files.addItem(item)
        self._select_suspects()
        mods = self.state['settings'].get('mods_path') or '(not set)'
        self.banner.setText('Mods folder: %s — a full backup is taken before anything is moved.' % mods)

    def _show_session(self, s):
        self._session_id = s['id']
        self.select_box.hide()
        self.done_box.hide()
        self.session_box.show()
        step = len(s.get('history', [])) + 1
        self.step_lbl.setText('Step %d — half the suspects are out of the game' % step)
        self.detail_lbl.setText(
            'Launch The Sims 4 now and reproduce the problem. Then tell ModBroom which happened.\n'
            'Still broken → the culprit is in the half still enabled. '
            'Problem gone → it is in the half currently moved out.')
        self.enabled_list.clear()
        for rel in s.get('enabled', []):
            self.enabled_list.addItem(rel)
        self.disabled_list.clear()
        for rel in s.get('disabled', []):
            self.disabled_list.addItem(rel)
        self.banner.setText('Backup taken before the first move: %s' % (s.get('backup') or 'n/a'))

    def _show_done(self, s):
        self._session_id = s['id']
        self.select_box.hide()
        self.session_box.hide()
        self.done_box.show()
        culprit = s.get('culprit')
        if culprit:
            self.done_title.setText('Found it: %s' % Path(culprit).name)
            self.done_detail.setText(
                'Path: %s\n\nIt has been moved out of your Mods folder. '
                'Everything else is back where it belongs. Delete it, update it, or report it to its author.' % culprit)
        else:
            self.done_title.setText('No single culprit')
            self.done_detail.setText('The bisect ended without isolating one file. Restore everything and try a wider net.')
        self.banner.setText('Session finished. Backup: %s' % (s.get('backup') or 'n/a'))

    # ------------------------------------------------ actions
    def _start(self):
        paths = self._checked_paths()
        if len(paths) < 2:
            QMessageBox.information(self, 'Pick at least two', 'Select two or more files to bisect.')
            return
        mods = self.state['settings'].get('mods_path')
        if not mods:
            QMessageBox.warning(self, 'No Mods folder', 'Set your Mods folder in Settings first.')
            return
        ok = QMessageBox.question(
            self, 'Start 50/50',
            'ModBroom will move %d file(s) out of your Mods folder right now.\n\n'
            'A full backup is taken first, and every move is reversible. Continue?' % (len(paths) // 2))
        if ok != QMessageBox.Yes:
            return
        try:
            bisect_bridge.start(self.state, paths, mods)
        except Exception as exc:
            QMessageBox.critical(self, 'Could not start', str(exc))
            return
        self.window.refresh_all()

    def _verdict(self, result):
        try:
            bisect_bridge.verdict(self.state, self._session_id, result)
        except Exception as exc:
            QMessageBox.critical(self, '50/50 failed', str(exc))
            return
        self.window.refresh_all()

    def _abort(self):
        ok = QMessageBox.question(self, 'Stop 50/50',
                                  'Move every file back where it was and discard this session?')
        if ok != QMessageBox.Yes:
            return
        bisect_bridge.restore_all(self.state, self._session_id)
        self.window.refresh_all()

    def _restore_all(self):
        bisect_bridge.restore_all(self.state, self._session_id)
        bisect_bridge.forget(self.state, self._session_id)
        self.window.refresh_all()

    def _finish(self):
        bisect_bridge.finish(self.state, self._session_id)
        bisect_bridge.forget(self.state, self._session_id)
        self.window.refresh_all()
