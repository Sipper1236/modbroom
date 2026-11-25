"""50/50 bisect: let ModBroom move the files; you just tell it how the game behaved."""
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QCheckBox, QFrame,
                               QMessageBox, QScrollArea, QAbstractItemView)

from . import Page
from .. import bisect_bridge  # thin shim so UI never imports engine directly for state mutation
from ... import log as mblog

log = mblog.get_logger('ui.bisect')


class BisectWorker(QObject):
    """Run a bisect engine call off the UI thread and report progress."""

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, fn, args, state):
        super().__init__()
        self._fn, self._args, self._state = fn, args, state

    @Slot()
    def run(self):
        try:
            result = self._fn(self._state, *self._args,
                              progress=lambda msg: self.progress.emit(msg))
            self.done.emit(result)
        except Exception as exc:
            log.exception('bisect worker failed: %s', exc)
            self.failed.emit(str(exc))


def _restore_and_forget(state, sid, progress=None):
    bisect_bridge.restore_all(state, sid, progress=progress)
    bisect_bridge.forget(state, sid)


def _finish_and_forget(state, sid, progress=None):
    bisect_bridge.finish(state, sid, progress=progress)
    bisect_bridge.forget(state, sid)


class FiftyPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.header('50/50 Test',
                    'ModBroom moves suspects out of the game, you launch Sims 4 and say whether it still breaks. '
                    'Splits are risk-balanced so each game launch eliminates as many files as possible. '
                    'Backups and file moves run in the background; everything is reversible.')

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
        self.undo_btn = QPushButton('Undo last answer')
        self.undo_btn.setObjectName('ghost')
        self.undo_btn.setToolTip('Put the files back exactly as they were before your last answer')
        self.undo_btn.clicked.connect(self._undo)
        self.abort_btn = QPushButton('Stop and put everything back')
        self.abort_btn.setObjectName('ghost')
        self.abort_btn.clicked.connect(self._abort)
        abort_row.addWidget(self.undo_btn)
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
        self.reject_btn = QPushButton('Not this one — keep searching')
        self.reject_btn.setObjectName('ghost')
        self.reject_btn.setToolTip('The problem still happens without this file: put it back and search the rest')
        self.finish_btn = QPushButton('Keep the culprit out and finish')
        self.finish_btn.setObjectName('primary')
        done_l.addWidget(self.done_title)
        done_l.addWidget(self.done_detail)
        row2 = QHBoxLayout()
        row2.addWidget(self.finish_btn)
        row2.addWidget(self.reject_btn)
        row2.addWidget(self.restore_all_btn)
        row2.addStretch(1)
        done_l.addLayout(row2)
        done_l.addStretch(1)
        self.body.addWidget(self.done_box, 1)
        self.restore_all_btn.clicked.connect(self._restore_all)
        self.reject_btn.clicked.connect(self._reject)
        self.finish_btn.clicked.connect(self._finish)

        self._session_id = None
        self._busy = False
        self._busy_label = ''
        self._thread = None
        self._worker = None

    # ------------------------------------------------ async engine calls
    def _set_busy(self, busy):
        self._busy = busy
        for btn in (self.start_btn, self.suggest_btn, self.broken_btn, self.fixed_btn,
                    self.undo_btn, self.abort_btn, self.reject_btn, self.finish_btn,
                    self.restore_all_btn):
            btn.setEnabled(not busy)

    def _run_bisect(self, fn, label, *args):
        """Run engine work in a worker thread so the UI never freezes."""
        if self._busy:
            return
        self._busy_label = label
        self._set_busy(True)
        self.banner.setText('%s — starting…' % label)
        thread = QThread(self)
        worker = BisectWorker(fn, args, self.state)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_bisect_progress)
        worker.done.connect(self._on_bisect_done)
        worker.failed.connect(self._on_bisect_failed)
        self._thread, self._worker = thread, worker
        thread.start()

    def _release_thread(self):
        thread, worker = self._thread, self._worker
        self._thread = self._worker = None
        if thread:
            thread.quit()
            thread.wait(3000)
        if worker:
            worker.deleteLater()
        if thread:
            thread.deleteLater()

    @Slot(str)
    def _on_bisect_progress(self, msg):
        self.banner.setText('%s — %s' % (self._busy_label, msg))

    @Slot(object)
    def _on_bisect_done(self, session):
        self._release_thread()
        self._set_busy(False)
        self.window.refresh_all()

    @Slot(str)
    def _on_bisect_failed(self, msg):
        self._release_thread()
        self._set_busy(False)
        QMessageBox.critical(self, '50/50 failed', msg)
        self.window.refresh_all()

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
        pool_n = max(0, len(s.get('pool', [])))
        rounds = (pool_n - 1).bit_length()   # ceil(log2(n)): tests left with ideal splits
        estimate = ('about %d more game test(s)' % rounds) if rounds else 'one final check'
        strategy = s.get('strategy')
        if step == 1 and strategy == 'risk-balanced':
            self.step_lbl.setText('Step 1 — %d suspects left, %s' % (pool_n, estimate))
            self.detail_lbl.setText(
                'The files most likely to be responsible were moved out first, with related files kept together. '
                'Launch The Sims 4 and reproduce the problem.\n'
                'Still broken → the culprit is in the enabled group. '
                'Problem gone → it is in the group currently moved out.')
        else:
            self.step_lbl.setText('Step %d — %d suspects left, %s' % (step, pool_n, estimate))
            self.detail_lbl.setText(
                'Launch The Sims 4 now and reproduce the problem. Then tell ModBroom which happened.\n'
                'Still broken → the culprit is in the group still enabled. '
                'Problem gone → it is in the group currently moved out.')
        self.undo_btn.setEnabled(bool(s.get('history')))
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
        self.reject_btn.setVisible(bool(culprit) and not s.get('candidate_confirmed'))
        if culprit:
            self.done_title.setText('Likely culprit: %s' % Path(culprit).name)
            extra = '' if s.get('candidate_confirmed') else (
                'If the problem still happens with this file out, click “Not this one — keep searching”.')
            self.done_detail.setText(
                'Path: %s\n\nIt has been moved out of your Mods folder. '
                'Everything else is back where it belongs. Delete it, update it, or report it to its author.\n\n%s'
                % (culprit, extra))
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
            'ModBroom will move some of the %d selected file(s) out of your Mods folder right now.\n\n'
            'A full backup is taken first, and every move is reversible. Continue?' % len(paths))
        if ok != QMessageBox.Yes:
            return
        self._run_bisect(bisect_bridge.start, 'Starting 50/50', paths, mods)

    def _verdict(self, result):
        self._run_bisect(bisect_bridge.verdict, 'Applying answer', self._session_id, result)

    def _undo(self):
        self._run_bisect(bisect_bridge.undo_verdict, 'Undoing last answer', self._session_id)

    def _reject(self):
        ok = QMessageBox.question(
            self, 'Keep searching',
            'Put this file back and test the remaining files without it?\n\n'
            'Use this if the problem still happens with the candidate out of the game.')
        if ok != QMessageBox.Yes:
            return
        self._run_bisect(bisect_bridge.reject_candidate, 'Continuing search', self._session_id)

    def _abort(self):
        ok = QMessageBox.question(self, 'Stop 50/50',
                                  'Move every file back where it was and discard this session?')
        if ok != QMessageBox.Yes:
            return
        self._run_bisect(bisect_bridge.restore_all, 'Restoring every file', self._session_id)

    def _restore_all(self):
        self._run_bisect(_restore_and_forget, 'Putting every file back', self._session_id)

    def _finish(self):
        self._run_bisect(_finish_and_forget, 'Finishing 50/50', self._session_id)
