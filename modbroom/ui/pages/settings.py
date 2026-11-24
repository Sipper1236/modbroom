"""Folders and options."""
import os

from PySide6.QtWidgets import (QFormLayout, QLineEdit, QPushButton, QCheckBox, QHBoxLayout,
                               QVBoxLayout, QLabel, QFileDialog, QMessageBox, QFrame)

from . import Page
from ... import store


class SettingsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.header('Settings', 'Point ModBroom at your Sims 4 folders. Everything stays on this machine — there is no account and no network.')

        form_frame = QFrame()
        form_frame.setObjectName('card')
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form = QFormLayout()
        form.setSpacing(10)
        self.fields = {}
        labels = [
            ('mods_path', 'Mods folder'),
            ('saves_path', 'Saves folder'),
            ('tray_path', 'Tray folder'),
            ('logs_path', 'Logs folder (crash logs)'),
            ('game_path', 'Game install folder'),
        ]
        for key, label in labels:
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText('Choose a folder…')
            browse = QPushButton('Browse…')
            browse.clicked.connect(lambda _=False, e=edit: self._browse(e))
            row.addWidget(edit, 1)
            row.addWidget(browse)
            form.addRow(label, row)
            self.fields[key] = edit
        form_layout.addLayout(form)

        self.include_saves = QCheckBox('Count saves and Tray files when scoring "unused" content (heuristic)')
        form_layout.addWidget(self.include_saves)
        self.layout_.addWidget(form_frame)

        row = QHBoxLayout()
        save = QPushButton('Save settings')
        save.setObjectName('primary')
        save.clicked.connect(self._save)
        auto = QPushButton('Auto-detect (Windows/Steam defaults)')
        auto.setObjectName('ghost')
        auto.clicked.connect(self._autodetect)
        row.addWidget(save)
        row.addWidget(auto)
        row.addStretch(1)
        self.layout_.addLayout(row)

        demo_frame = QFrame()
        demo_frame.setObjectName('card')
        dl = QVBoxLayout(demo_frame)
        dl.setContentsMargins(16, 14, 16, 14)
        t = QLabel('No Sims 4 on this machine?')
        t.setObjectName('h2')
        d = QLabel('ModBroom can load a synthetic Mods folder with a broken package, '
                   'a duplicate, a conflict, a risky script and a fake crash log — '
                   'everything in the app works against it.')
        d.setObjectName('muted')
        d.setWordWrap(True)
        dl.addWidget(t)
        dl.addWidget(d)
        demo_btn = QPushButton('Load demo library')
        demo_btn.setObjectName('ghost')
        demo_btn.clicked.connect(self._load_demo)
        dl.addWidget(demo_btn, 0)
        self.layout_.addWidget(demo_frame)
        self.layout_.addStretch(1)

    def _browse(self, edit):
        start = edit.text().strip() or os.path.expanduser('~')
        folder = QFileDialog.getExistingDirectory(self, 'Choose folder', start)
        if folder:
            edit.setText(folder)

    def _save(self):
        s = self.state['settings']
        for key, edit in self.fields.items():
            s[key] = edit.text().strip()
        s['include_saves'] = self.include_saves.isChecked()
        store.save_state(self.state)
        self.window.statusBar().showMessage('Settings saved', 4000)

    def _autodetect(self):
        det = store.autodetect_paths()
        for key, edit in self.fields.items():
            if det.get(key):
                edit.setText(det[key])
        self.window.statusBar().showMessage('Detected default locations — review and Save.', 6000)

    def _load_demo(self):
        from .. import core
        if QMessageBox.question(self, 'Load demo library',
                                'This replaces the current folder paths with a synthetic demo library in ~/.modbroom/demo. '
                                'Your real folders are not affected. Continue?') != QMessageBox.Yes:
            return
        new_state = core.demo_library()
        self.window.state.clear()
        self.window.state.update(new_state)
        self.window.refresh_all()
        self.refresh()
        self.window.statusBar().showMessage('Demo library loaded — press Scan now.', 6000)

    def refresh(self):
        s = self.state.get('settings', {})
        for key, edit in self.fields.items():
            edit.setText(s.get(key) or '')
        self.include_saves.setChecked(bool(s.get('include_saves', True)))
