"""Overview: health at a glance."""
import time
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QScrollArea, QWidget, QTableWidget,
                               QTableWidgetItem, QHeaderView)
from . import Page
from .. import theme
from ..widgets import StatCard, EmptyState


def _name(path):
    return (path or '').replace('\\', '/').rsplit('/', 1)[-1]


class DashboardPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.header('Dashboard', 'What ModBroom found the last time it looked at your Mods folder.')

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.body = QWidget()
        self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(0, 0, 0, 0)
        self.body_l.setSpacing(14)
        self.scroll.setWidget(self.body)
        self.layout_.addWidget(self.scroll)

        self.empty = EmptyState(
            'No scan yet',
            'Point ModBroom at your Mods folder (Settings), then hit “Scan now”. '
            'No Sims 4 handy? Load the demo library in Settings to see everything working.')
        self.layout_.addWidget(self.empty)

        self.cards_row = QHBoxLayout()
        self.cards_row.setSpacing(10)
        self.cards = {}
        for key, label in [('files', 'Files scanned'), ('duplicates', 'Duplicates'),
                           ('conflicts', 'Conflicts'), ('broken', 'Broken'),
                           ('risks', 'Risky scripts')]:
            c = StatCard(label)
            self.cards[key] = c
            self.cards_row.addWidget(c)
        self.body_l.addLayout(self.cards_row)

        self.health = QLabel('')
        self.health.setWordWrap(True)
        self.health.setObjectName('healthBanner')
        self.body_l.addWidget(self.health)

        self.summary = QLabel('')
        self.summary.setObjectName('muted')
        self.summary.setWordWrap(True)
        self.body_l.addWidget(self.summary)

        self.issues_title = QLabel('Needs attention')
        self.issues_title.setObjectName('h2')
        self.body_l.addWidget(self.issues_title)

        self.issues = QTableWidget(0, 3)
        self.issues.setHorizontalHeaderLabels(['What', 'File', 'Detail'])
        self.issues.verticalHeader().setVisible(False)
        self.issues.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.issues.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.issues.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.issues.setEditTriggers(QTableWidget.NoEditTriggers)
        self.issues.setSelectionBehavior(QTableWidget.SelectRows)
        self.issues.setAlternatingRowColors(True)
        self.issues.setMinimumHeight(140)
        self.body_l.addWidget(self.issues, 0)

        row = QHBoxLayout()
        self.fix_btn = QPushButton('Review in Diagnostics')
        self.fix_btn.setObjectName('primary')
        self.fix_btn.clicked.connect(lambda: self.window.goto(2))
        self.backup_btn = QPushButton('Back up Mods folder')
        self.backup_btn.setObjectName('ghost')
        self.backup_btn.clicked.connect(self._backup)
        row.addWidget(self.fix_btn)
        row.addWidget(self.backup_btn)
        row.addStretch(1)
        self.body_l.addLayout(row)
        self.body_l.addStretch(0)

    def _backup(self):
        from .. import store
        mods = self.state['settings'].get('mods_path')
        if not mods:
            return
        dest = store.create_backup(self.state, mods, 'manual')
        self.window.statusBar().showMessage('Backup written to %s' % dest, 8000)

    def refresh(self):
        findings = self.state.get('last_findings')
        scan = self.state.get('last_scan')
        has = bool(findings and scan)
        self.empty.setVisible(not has)
        self.scroll.setVisible(has)
        if not has:
            return

        stats = findings.get('stats', {})
        self.cards['files'].set_value(stats.get('total_files', 0))
        dup = stats.get('duplicates', 0) + stats.get('resource_dupes', 0)
        self.cards['duplicates'].set_value(dup, theme.WARN if dup else None)
        self.cards['conflicts'].set_value(stats.get('conflicts', 0),
                                          theme.WARN if stats.get('conflicts') else None)
        self.cards['broken'].set_value(stats.get('integrity', 0),
                                       theme.BAD if stats.get('integrity') else None)
        self.cards['risks'].set_value(stats.get('high_risks', 0),
                                      theme.BAD if stats.get('high_risks') else None)

        high = stats.get('high_risks', 0) + stats.get('integrity', 0)
        warn = stats.get('conflicts', 0) + dup
        if high:
            self.health.setText('⚠  %d serious problem(s) — something here is likely crashing or being ignored.' % high)
            self.health.setStyleSheet('QLabel#healthBanner { color: #ffd7d3; background: #3a1f1d; border: 1px solid %s; border-radius: 8px; padding: 10px 12px; font-size: 14px; font-weight: 600; }' % theme.BAD)
        elif warn:
            self.health.setText('◐  Mostly healthy — %d thing(s) worth a look.' % warn)
            self.health.setStyleSheet('QLabel#healthBanner { color: #ffe9b3; background: #33290f; border: 1px solid %s; border-radius: 8px; padding: 10px 12px; font-size: 14px; font-weight: 600; }' % theme.WARN)
        else:
            self.health.setText('✓  Clean. Nothing flagged.')
            self.health.setStyleSheet('QLabel#healthBanner { color: #c8f7dd; background: #14301f; border: 1px solid %s; border-radius: 8px; padding: 10px 12px; font-size: 14px; font-weight: 600; }' % theme.GOOD)

        scanned = time.strftime('%H:%M:%S', time.localtime(scan.get('scanned_at', time.time())))
        gb = (scan.get('total_bytes') or 0) / (1024 ** 3)
        usage = self.state.get('last_usage') or {}
        parts = ['Scanned %s · %d files · %.2f GB · %d resources' % (
            scanned, len(scan.get('files', [])), gb, stats.get('total_resources', 0))]
        if usage:
            parts.append('%d referenced in saves/tray · %d not referenced (heuristic)' % (
                len(usage.get('used', [])), len(usage.get('unused', []))))
        gr = self.state.get('last_game_rules') or []
        if gr:
            parts.append('%d game-rules note(s)' % len(gr))
        self.summary.setText('  ·  '.join(parts))

        rows = []
        for item in findings.get('integrity', []):
            rows.append(('Broken package', _name(item['file']), item.get('error', '')))
        for item in findings.get('parse_errors', []):
            rows.append(('Unreadable', _name(item['file']), item.get('error', '')))
        for item in findings.get('script_risks', []):
            if item.get('level') == 'high':
                rows.append(('Risky script', _name(item['file']), item.get('msg', '')))
        for item in findings.get('duplicates', [])[:20]:
            for extra in item['files'][1:]:
                rows.append(('Duplicate', _name(extra), 'identical to ' + _name(item['files'][0])))
        for item in findings.get('conflicts', [])[:20]:
            rows.append(('Override conflict', _name(item['files'][0]),
                         'shares a resource with %s' % ', '.join(_name(f) for f in item['files'][1:3])))
        for item in gr:
            if item.get('level') in ('high', 'medium'):
                rows.append(('Game rule', _name(item['file']), item.get('detail', '')))

        self.issues.setRowCount(len(rows))
        for i, (a, b, c) in enumerate(rows):
            self.issues.setItem(i, 0, QTableWidgetItem(a))
            self.issues.setItem(i, 1, QTableWidgetItem(b))
            self.issues.setItem(i, 2, QTableWidgetItem(c))
        self.issues_title.setText('Needs attention (%d)' % len(rows) if rows else 'Needs attention')
        # size the table to its rows so a short list does not leave a huge void
        row_h = self.issues.rowHeight(0) if self.issues.rowCount() else 28
        want = self.issues.horizontalHeader().height() + 2 + row_h * self.issues.rowCount() + 6
        self.issues.setMaximumHeight(max(min(want, 520), 120))
