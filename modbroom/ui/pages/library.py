"""Every file ModBroom saw, searchable and sortable."""
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
                               QHeaderView, QLabel, QMessageBox, QPushButton)
from . import Page


def fmt_size(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return ('%.0f %s' % (n, unit)) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024


class LibraryPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.header('Library', 'Everything in your Mods folder. Type to filter, click a column to sort, select rows to quarantine.')

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Filter by filename or path…')
        self.search.textChanged.connect(self._fill)
        bar.addWidget(self.search, 1)
        self.kind = QComboBox()
        self.kind.addItems(['All types', 'Packages', 'Scripts', 'Loose .py'])
        self.kind.currentIndexChanged.connect(self._fill)
        bar.addWidget(self.kind)
        self.count = QLabel('')
        self.count.setObjectName('muted')
        bar.addWidget(self.count)
        self.layout_.addLayout(bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['File', 'Type', 'Size', 'Resources', 'Status'])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.setSortingEnabled(True)
        self.layout_.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.open_btn = QPushButton('Show in folder')
        self.open_btn.clicked.connect(self._reveal)
        self.quar_btn = QPushButton('Quarantine selected')
        self.quar_btn.setObjectName('danger')
        self.quar_btn.clicked.connect(self._quarantine)
        row.addWidget(self.open_btn)
        row.addWidget(self.quar_btn)
        row.addStretch(1)
        self.layout_.addLayout(row)

        self._rows = []

    def refresh(self):
        scan = self.state.get('last_scan') or {}
        files = list(scan.get('files', []))
        findings = self.state.get('last_findings') or {}
        bad = {i['file'] for i in findings.get('integrity', [])} | {i['file'] for i in findings.get('parse_errors', [])}
        risky = {i['file'] for i in findings.get('script_risks', []) if i.get('level') == 'high'}
        dupes = set()
        for d in findings.get('duplicates', []):
            dupes.update(d['files'][1:])
        for f in files:
            if f['path'] in bad:
                f['_status'] = 'broken'
            elif f['path'] in risky:
                f['_status'] = 'risky script'
            elif f['path'] in dupes:
                f['_status'] = 'duplicate'
            else:
                f['_status'] = 'ok'
        self._rows = files
        self._fill()

    def _filtered(self):
        q = self.search.text().strip().lower()
        kind = self.kind.currentIndex()
        out = []
        for f in self._rows:
            if kind == 1 and f['kind'] != 'package':
                continue
            if kind == 2 and f['kind'] != 'script':
                continue
            if kind == 3 and f['kind'] != 'python':
                continue
            if q and q not in f['rel'].lower():
                continue
            out.append(f)
        return out

    def _fill(self):
        rows = self._filtered()
        self.count.setText('%d of %d files' % (len(rows), len(self._rows)))
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, f in enumerate(rows):
            item = QTableWidgetItem(f['rel'])
            item.setData(Qt.UserRole, f['path'])
            self.table.setItem(i, 0, item)
            self.table.setItem(i, 1, QTableWidgetItem(f['kind']))
            size_item = QTableWidgetItem()
            size_item.setData(Qt.DisplayRole, int(f['size']))
            size_item.setText(fmt_size(f['size']))
            self.table.setItem(i, 2, size_item)
            res_item = QTableWidgetItem()
            res_item.setData(Qt.DisplayRole, int(f.get('entry_count') or 0))
            res_item.setText(str(f.get('entry_count') or 0))
            self.table.setItem(i, 3, res_item)
            st = f.get('_status', 'ok')
            st_item = QTableWidgetItem(st)
            if st == 'ok':
                st_item.setForeground(Qt.green)
            elif st in ('broken', 'risky script'):
                st_item.setForeground(Qt.red)
            else:
                st_item.setForeground(Qt.yellow)
            self.table.setItem(i, 4, st_item)
        self.table.setSortingEnabled(True)

    def _selected_paths(self):
        paths, seen = [], set()
        for idx in self.table.selectionModel().selectedRows():
            item = self.table.item(idx.row(), 0)
            if item is None:
                continue
            p = item.data(Qt.UserRole)
            if p and p not in seen:
                seen.add(p)
                paths.append(p)
        return paths

    def _reveal(self):
        paths = self._selected_paths()
        if not paths:
            return
        self._reveal_path(os.path.dirname(paths[0]))

    @staticmethod
    def _reveal_path(folder):
        import sys, subprocess
        try:
            if sys.platform.startswith('win'):
                os.startfile(folder)  # noqa: S606
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', folder])
            else:
                subprocess.Popen(['xdg-open', folder])
        except Exception as exc:
            print('reveal failed:', exc)

    def _quarantine(self):
        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, 'Nothing selected', 'Select one or more files first.')
            return
        if QMessageBox.question(self, 'Quarantine',
                                'Move %d file(s) into ModBroom quarantine?\nThey leave your Mods folder; you can restore them any time.' % len(paths)) != QMessageBox.Yes:
            return
        from .. import store
        store.quarantine_files(self.state, paths, 'manual')
        self.window.refresh_all()
        self.window.statusBar().showMessage('Quarantined %d file(s)' % len(paths), 5000)
