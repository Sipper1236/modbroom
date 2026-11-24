"""Quarantine, backups, export, single-file check, crash logs."""
import os
import subprocess
import sys
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
                               QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
                               QTextEdit, QLineEdit)

from . import Page
from ... import store, dbpf, scanner
from .library import fmt_size


def _reveal(path):
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    try:
        if sys.platform.startswith('win'):
            os.startfile(folder)  # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])
    except Exception:
        pass


class ToolsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.header('Tools', 'Quarantine, backups, export, crash logs — the safety net.')

        self.tabs = QTabWidget()
        self.layout_.addWidget(self.tabs, 1)

        # ---------- quarantine ----------
        qtab = QWidget(); ql = QVBoxLayout(qtab); ql.setContentsMargins(0, 10, 0, 0)
        qintro = QLabel('Files ModBroom has moved out of your Mods folder. Restoring puts them back exactly where they came from.')
        qintro.setWordWrap(True)
        ql.addWidget(qintro)
        self.quar = QTableWidget(0, 4)
        self.quar.setHorizontalHeaderLabels(['File', 'Reason', 'When', 'Size'])
        self.quar.verticalHeader().setVisible(False)
        self.quar.setSelectionBehavior(QTableWidget.SelectRows)
        self.quar.setSelectionMode(QTableWidget.ExtendedSelection)
        self.quar.setEditTriggers(QTableWidget.NoEditTriggers)
        self.quar.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            self.quar.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        ql.addWidget(self.quar, 1)
        qrow = QHBoxLayout()
        restore = QPushButton('Restore selected')
        restore.setObjectName('primary')
        restore.clicked.connect(self._restore)
        delete = QPushButton('Delete permanently')
        delete.setObjectName('danger')
        delete.clicked.connect(self._delete)
        openfolder = QPushButton('Open quarantine folder')
        openfolder.setObjectName('ghost')
        openfolder.clicked.connect(lambda: _reveal(str(store.QUAR_DIR)))
        qrow.addWidget(restore); qrow.addWidget(delete); qrow.addWidget(openfolder); qrow.addStretch(1)
        ql.addLayout(qrow)
        self.tabs.addTab(qtab, 'Quarantine')

        # ---------- backups ----------
        btab = QWidget(); bl = QVBoxLayout(btab); bl.setContentsMargins(0, 10, 0, 0)
        bintro = QLabel('Zips of your Mods folder. ModBroom makes one automatically before any 50/50 bisect.')
        bintro.setWordWrap(True)
        bl.addWidget(bintro)
        self.backups = QTableWidget(0, 3)
        self.backups.setHorizontalHeaderLabels(['Backup', 'Size', 'Created'])
        self.backups.verticalHeader().setVisible(False)
        self.backups.setEditTriggers(QTableWidget.NoEditTriggers)
        self.backups.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2):
            self.backups.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        bl.addWidget(self.backups, 1)
        brow = QHBoxLayout()
        mk = QPushButton('Back up now')
        mk.setObjectName('primary')
        mk.clicked.connect(self._make_backup)
        openb = QPushButton('Open backups folder')
        openb.setObjectName('ghost')
        openb.clicked.connect(lambda: _reveal(str(store.BACKUP_DIR)))
        brow.addWidget(mk); brow.addWidget(openb); brow.addStretch(1)
        bl.addLayout(brow)
        self.tabs.addTab(btab, 'Backups')

        # ---------- export ----------
        etab = QWidget(); el = QVBoxLayout(etab); el.setContentsMargins(0, 10, 0, 0)
        el.addWidget(QLabel('Export a manifest of everything scanned — useful for Reddit, Discord, or your own records.'))
        erow = QHBoxLayout()
        manifest = QPushButton('Export JSON manifest')
        manifest.setObjectName('primary')
        manifest.clicked.connect(lambda: self._export('json'))
        csv_btn = QPushButton('Export CSV')
        csv_btn.setObjectName('ghost')
        csv_btn.clicked.connect(lambda: self._export('csv'))
        html_btn = QPushButton('Export HTML report')
        html_btn.setObjectName('ghost')
        html_btn.setToolTip('A single self-contained page you can attach to a forum post or share for help')
        html_btn.clicked.connect(lambda: self._export('html'))
        erow.addWidget(manifest); erow.addWidget(csv_btn); erow.addWidget(html_btn); erow.addStretch(1)
        el.addLayout(erow)
        el.addStretch(1)
        self.tabs.addTab(etab, 'Export')

        # ---------- single file check ----------
        ctab = QWidget(); cl = QVBoxLayout(ctab); cl.setContentsMargins(0, 10, 0, 0)
        cl.addWidget(QLabel('Check one file without touching anything.'))
        crow = QHBoxLayout()
        self.check_path = QLineEdit()
        self.check_path.setPlaceholderText('Path to a .package or .ts4script')
        browse = QPushButton('Browse…')
        browse.clicked.connect(self._browse_check)
        run = QPushButton('Check')
        run.setObjectName('primary')
        run.clicked.connect(self._run_check)
        crow.addWidget(self.check_path, 1); crow.addWidget(browse); crow.addWidget(run)
        cl.addLayout(crow)
        self.check_out = QTextEdit()
        self.check_out.setReadOnly(True)
        cl.addWidget(self.check_out, 1)
        self.tabs.addTab(ctab, 'Check a file')

    # ---------------- quarantine ----------------
    def refresh(self):
        items = list(self.state.get('quarantine', []))
        self.quar.setRowCount(len(items))
        for i, it in enumerate(items):
            self.quar.setItem(i, 0, QTableWidgetItem(it.get('name', '?')))
            self.quar.setItem(i, 1, QTableWidgetItem(it.get('reason', '')))
            ts = it.get('time')
            self.quar.setItem(i, 2, QTableWidgetItem(datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M') if ts else ''))
            self.quar.setItem(i, 3, QTableWidgetItem(fmt_size(it.get('size', 0))))
            self.quar.item(i, 0).setData(Qt.UserRole, it.get('id'))
        for i, it in enumerate(items):
            self.quar.item(i, 0).setToolTip(it.get('original', ''))

        backups = store.list_backups()
        self.backups.setRowCount(len(backups))
        for i, b in enumerate(backups):
            self.backups.setItem(i, 0, QTableWidgetItem(b['name']))
            self.backups.setItem(i, 1, QTableWidgetItem(fmt_size(b['size'])))
            self.backups.setItem(i, 2, QTableWidgetItem(datetime.fromtimestamp(b['mtime']).strftime('%Y-%m-%d %H:%M')))

    def _selected_ids(self):
        ids = []
        for idx in self.quar.selectionModel().selectedRows():
            item = self.quar.item(idx.row(), 0)
            if item:
                ids.append(item.data(Qt.UserRole))
        return ids

    def _restore(self):
        ids = self._selected_ids()
        if not ids:
            return
        store.restore_quarantine(self.state, ids)
        self.window.refresh_all()
        self.window.statusBar().showMessage('Restored %d file(s)' % len(ids), 5000)

    def _delete(self):
        ids = self._selected_ids()
        if not ids:
            return
        if QMessageBox.question(self, 'Delete permanently',
                                'Permanently delete %d quarantined file(s)? This cannot be undone.' % len(ids)) != QMessageBox.Yes:
            return
        store.delete_quarantine(self.state, ids)
        self.window.refresh_all()

    def _make_backup(self):
        mods = self.state['settings'].get('mods_path')
        if not mods:
            QMessageBox.warning(self, 'No Mods folder', 'Set your Mods folder in Settings first.')
            return
        dest = store.create_backup(self.state, mods, 'manual')
        self.window.statusBar().showMessage('Backup written: %s' % dest, 8000)
        self.refresh()

    def _export(self, kind):
        scan = self.state.get('last_scan')
        findings = self.state.get('last_findings')
        if not scan:
            QMessageBox.information(self, 'Nothing to export', 'Run a scan first.')
            return
        names = {'json': ('modbroom-manifest.json', 'JSON (*.json)'),
                 'csv': ('modbroom-manifest.csv', 'CSV (*.csv)'),
                 'html': ('modbroom-report.html', 'HTML (*.html)')}
        default_name, filt = names.get(kind, names['json'])
        path, _ = QFileDialog.getSaveFileName(self, 'Export', default_name, filt)
        if not path:
            return
        if kind == 'json':
            store.export_manifest(scan, findings or {}, path)
        elif kind == 'csv':
            store.export_csv(scan, path)
        else:
            store.export_html(scan, findings or {}, path)
        self.window.statusBar().showMessage('Exported to %s' % path, 8000)

    def _browse_check(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Pick a file', '', 'Sims 4 files (*.package *.ts4script);;All files (*)')
        if path:
            self.check_path.setText(path)
            self._run_check()

    def _run_check(self):
        path = self.check_path.text().strip()
        if not path or not os.path.isfile(path):
            self.check_out.setPlainText('File not found.')
            return
        ext = os.path.splitext(path)[1].lower()
        lines = [path, 'Size: %s' % fmt_size(os.path.getsize(path)), '']
        if ext == '.package':
            try:
                reader = dbpf.PackageReader(path)
                lines.append('DBPF readable: yes — %d resources' % len(reader.entries))
                errs = reader.integrity_errors()
                lines.append('Integrity: ' + ('OK' if not errs else '; '.join(errs)))
            except Exception as exc:
                lines.append('DBPF readable: NO — %s' % exc)
        elif ext == '.ts4script':
            findings = scanner.scan_script_zip(path)
            if findings:
                for f in findings:
                    lines.append('[%s] %s' % (f.get('level', '?'), f.get('msg', '')))
            else:
                lines.append('No risky patterns found.')
        else:
            lines.append('Not a .package or .ts4script — nothing to check.')
        self.check_out.setPlainText('\n'.join(lines))
