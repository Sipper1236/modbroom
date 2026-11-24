"""The in-game companion mod: what it is, how to install it, and link status."""
import os
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QFrame,
                               QMessageBox, QTextEdit)

from . import Page
from ... import bridge, core


class CompanionPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.header('In-game companion',
                    'A real Sims 4 script mod that reads the scan results out loud while you play. Optional — ModBroom works fully without it.')

        card = QFrame()
        card.setObjectName('card')
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(10)

        title = QLabel('ModBroom Bridge (.ts4script)')
        title.setObjectName('h2')
        cl.addWidget(title)

        what = QLabel(
            'Installs into your Mods folder as a real script mod. Once in-game you get four cheat commands:\n\n'
            '    mb_help     — list the commands\n'
            '    mb_status   — the last ModBroom scan: files, duplicates, conflicts, broken files, risky scripts\n'
            '    mb_stats    — live count of .package/.ts4script files, and a warning if a script sits too deep for the game to load it\n'
            '    mb_find X   — locate files whose name contains X, and flag ones the game silently ignores\n\n'
            'It reads a small file ModBroom writes to ~/.modbroom/partner.json after every scan. '
            'It never writes to your saves, never touches the network, and does nothing you did not ask for.')
        what.setWordWrap(True)
        cl.addWidget(what)

        honesty = QLabel('Honest status: the companion is written against the public Sims 4 script-mod API '
                         '(sims4.commands, CheatOutput). It has been syntax-checked and packaged, but it has NOT been run inside the game '
                         'on this machine — there is no Sims 4 install here. If a command does nothing in-game, that is why.')
        honesty.setWordWrap(True)
        honesty.setStyleSheet('color: #e8b33f;')
        cl.addWidget(honesty)

        self.install_btn = QPushButton('Install into my Mods folder')
        self.install_btn.setObjectName('primary')
        self.install_btn.clicked.connect(self._install)
        self.build_btn = QPushButton('Build .ts4script only…')
        self.build_btn.setObjectName('ghost')
        self.build_btn.clicked.connect(self._build_only)
        row = QHBoxLayout()
        row.addWidget(self.install_btn)
        row.addWidget(self.build_btn)
        row.addStretch(1)
        cl.addLayout(row)
        self.layout_.addWidget(card)

        link_card = QFrame()
        link_card.setObjectName('card')
        ll = QVBoxLayout(link_card)
        ll.setContentsMargins(16, 16, 16, 16)
        ll.setSpacing(8)
        lt = QLabel('Desktop ↔ game link')
        lt.setObjectName('h2')
        ll.addWidget(lt)
        self.link_state = QLabel('')
        self.link_state.setWordWrap(True)
        ll.addWidget(self.link_state)
        self.partner_view = QTextEdit()
        self.partner_view.setReadOnly(True)
        self.partner_view.setMaximumHeight(150)
        ll.addWidget(self.partner_view)
        sync = QPushButton('Rewrite partner.json from the latest scan')
        sync.setObjectName('ghost')
        sync.clicked.connect(self._resync)
        ll.addWidget(sync, 0, Qt.AlignLeft)
        self.layout_.addWidget(link_card)

        note = QLabel('Install steps: 1) click Install, 2) start The Sims 4, 3) Game Options → Other → tick '
                      '“Enable Custom Content and Mods” and “Script Mods Allowed”, 4) fully restart the game, '
                      '5) open the cheat console (Ctrl+Shift+C) and type mb_help.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        self.layout_.addWidget(note)
        self.layout_.addStretch(1)

    def _install(self):
        mods = self.state['settings'].get('mods_path')
        try:
            built, partner, dest = bridge.install(self.state, mods)
        except Exception as exc:
            QMessageBox.critical(self, 'Install failed', str(exc))
            return
        if dest:
            QMessageBox.information(self, 'Installed',
                                    'ModBroom Bridge installed to:\n%s\n\npartner.json written to:\n%s\n\nNow restart The Sims 4 and type mb_help in the cheat console.' % (dest, partner))
        else:
            QMessageBox.information(self, 'Built, not installed',
                                    'No Mods folder is configured, so the file was built but not copied.\n\nBuilt at:\n%s\n\nSet your Mods folder in Settings and click Install again.' % built)
        self.refresh()

    def _build_only(self):
        from PySide6.QtWidgets import QFileDialog
        dest, _ = QFileDialog.getSaveFileName(self, 'Save ModBroomBridge.ts4script', 'ModBroomBridge.ts4script', 'Sims 4 script mod (*.ts4script)')
        if not dest:
            return
        try:
            src = bridge.build_ts4script()
            with open(src, 'rb') as a, open(dest, 'wb') as b:
                b.write(a.read())
        except Exception as exc:
            QMessageBox.critical(self, 'Build failed', str(exc))
            return
        self.window.statusBar().showMessage('Wrote %s' % dest, 6000)

    def _resync(self):
        if not self.state.get('last_scan'):
            QMessageBox.information(self, 'Nothing to sync', 'Run a scan first.')
            return
        partner = bridge.write_partner(self.state)
        self.refresh()
        self.window.statusBar().showMessage('Wrote %s' % partner, 6000)

    def refresh(self):
        partner = core.read_partner()
        mods = self.state['settings'].get('mods_path') or ''
        installed = bool(mods) and os.path.isfile(os.path.join(mods, bridge.NAME))
        if partner:
            age = time.time() - float(partner.get('written_at', 0))
            self.link_state.setText(
                'Status: %s · partner.json written %s ago · %s files / %s issues in last scan\n%s' % (
                    'installed in Mods folder' if installed else 'NOT installed in Mods folder',
                    _human_age(age), partner.get('files', '?'), partner.get('issues', '?'),
                    'The game can read this file.' if installed else 'Run Install to copy the .ts4script into Mods.'))
            self.partner_view.setPlainText(_format_partner(partner))
        else:
            self.link_state.setText('Status: no scan data yet. Run a scan — ModBroom will write partner.json automatically at scan time.')
            self.partner_view.setPlainText('{ }')
        self.install_btn.setText('Reinstall in Mods folder' if installed else 'Install into my Mods folder')


def _human_age(seconds):
    seconds = int(max(0, seconds))
    if seconds < 90:
        return '%ds' % seconds
    if seconds < 5400:
        return '%d min' % (seconds // 60)
    if seconds < 172800:
        return '%d h' % (seconds // 3600)
    return '%d d' % (seconds // 86400)


def _format_partner(p):
    import json
    return json.dumps(p, indent=2, sort_keys=True)
