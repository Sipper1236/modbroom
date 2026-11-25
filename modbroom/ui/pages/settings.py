"""Settings: folders, options, and the self-updater."""
import os
import threading

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFormLayout, QLineEdit, QPushButton, QCheckBox, QHBoxLayout,
                               QVBoxLayout, QLabel, QFileDialog, QMessageBox, QFrame,
                               QProgressBar, QTextEdit)

from . import Page
from ... import store


class _UpdateWorker(QThread):
    """Runs the network check off the UI thread."""
    done = Signal(object, str)   # release-or-None, message
    failed = Signal(str)
    progressed = Signal(int, int)

    def __init__(self, current_version, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self):
        from ... import updater
        try:
            rel, msg = updater.check_for_update(self.current_version)
            self.done.emit(rel, msg)
        except Exception as exc:          # noqa: BLE001 - surfaced in the UI
            self.failed.emit(str(exc))


class _DownloadWorker(QThread):
    progressed = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        from ... import updater
        try:
            path = updater.download_asset(
                self.url, progress=lambda done, total: self.progressed.emit(done, total))
            self.done.emit(str(path))
        except Exception as exc:          # noqa: BLE001
            self.failed.emit(str(exc))


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

        self.layout_.addWidget(self._update_card())
        self.layout_.addWidget(self._log_card())

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

    # ------------------------------------------------------------ logging
    def _log_card(self):
        from ... import log
        frame = QFrame()
        frame.setObjectName('card')
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        title = QLabel('Verbose log')
        title.setObjectName('h2')
        lay.addWidget(title)
        path = log.log_path()
        note = QLabel(
            'ModBroom writes a detailed DEBUG log to:\n%s\n'
            'It rotates at 2 MB and keeps three older copies. Nothing is sent anywhere.'
            % path)
        note.setObjectName('muted')
        note.setWordWrap(True)
        lay.addWidget(note)

        row = QHBoxLayout()
        open_log = QPushButton('Open log file')
        open_log.setObjectName('ghost')
        open_log.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        open_folder = QPushButton('Open logs folder')
        open_folder.setObjectName('ghost')
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))))
        row.addWidget(open_log)
        row.addWidget(open_folder)
        row.addStretch(1)
        lay.addLayout(row)
        return frame

    # ------------------------------------------------------------ updater
    def _update_card(self):
        from ... import __version__
        frame = QFrame()
        frame.setObjectName('card')
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        title = QLabel('Updates')
        title.setObjectName('h2')
        lay.addWidget(title)

        from ... import updater
        self.upd_version = QLabel('Installed version: %s' % __version__)
        self.upd_version.setObjectName('muted')
        lay.addWidget(self.upd_version)

        self.upd_status = QLabel(
            'ModBroom can check GitHub for a newer release and install it for you. '
            'It only ever contacts github.com, and nothing is installed without your say-so.')
        self.upd_status.setObjectName('muted')
        self.upd_status.setWordWrap(True)
        lay.addWidget(self.upd_status)

        self.upd_notes = QTextEdit()
        self.upd_notes.setReadOnly(True)
        self.upd_notes.setMaximumHeight(120)
        self.upd_notes.setVisible(False)
        lay.addWidget(self.upd_notes)

        self.upd_bar = QProgressBar()
        self.upd_bar.setVisible(False)
        lay.addWidget(self.upd_bar)

        btns = QHBoxLayout()
        self.upd_check = QPushButton('Check for updates')
        self.upd_check.setObjectName('primary')
        self.upd_check.clicked.connect(self._check_update)
        self.upd_install = QPushButton('Download and install')
        self.upd_install.setObjectName('ghost')
        self.upd_install.setEnabled(False)
        self.upd_install.clicked.connect(self._install_update)
        btns.addWidget(self.upd_check)
        btns.addWidget(self.upd_install)
        btns.addStretch(1)
        lay.addLayout(btns)

        self._upd_release = None
        self._upd_worker = None
        self._dl_worker = None
        self._dl_path = None
        return frame

    def _check_update(self):
        from ... import __version__
        self.upd_check.setEnabled(False)
        self.upd_status.setText('Checking GitHub for a newer release…')
        self._upd_worker = _UpdateWorker(__version__, self)
        self._upd_worker.done.connect(self._on_check_done)
        self._upd_worker.failed.connect(self._on_check_failed)
        self._upd_worker.start()

    def _on_check_done(self, release, message):
        self.upd_check.setEnabled(True)
        self.upd_status.setText(message)
        if not release:
            self.upd_install.setEnabled(False)
            self.upd_notes.setVisible(False)
            return
        self._upd_release = release
        notes = release.get('notes') or ''
        if notes:
            self.upd_notes.setPlainText(notes[:4000])
            self.upd_notes.setVisible(True)

        from ... import updater
        asset = updater.platform_asset_name()
        if asset not in release.get('assets', {}):
            self.upd_status.setText(
                '%s is available, but there is no build for this platform in the release. '
                'Open the releases page to download it manually.' % release['version'])
            self.upd_install.setEnabled(False)
            self.window.statusBar().showMessage('Update available (manual download)', 8000)
            return

        exe = updater.current_executable()
        if exe is None:
            self.upd_status.setText(
                '%s is available. You are running from source, so ModBroom cannot replace '
                'itself — use pip/git to update, or download the release build.' % release['version'])
            self.upd_install.setEnabled(False)
            return

        self.upd_install.setEnabled(True)
        self.window.statusBar().showMessage('Update %s available' % release['version'], 8000)

    def _on_check_failed(self, message):
        self.upd_check.setEnabled(True)
        self.upd_status.setText('Update check failed: %s' % message)
        self.window.statusBar().showMessage('Update check failed', 8000)

    def _install_update(self):
        from ... import updater
        if not self._upd_release:
            return
        url = self._upd_release['assets'].get(updater.platform_asset_name())
        if not url:
            return
        if QMessageBox.question(
                self, 'Install update',
                'Download ModBroom %s and replace the running copy?\n\n'
                'A backup of the current executable is kept until the next launch.'
                % self._upd_release['version']) != QMessageBox.Yes:
            return
        self.upd_install.setEnabled(False)
        self.upd_check.setEnabled(False)
        self.upd_bar.setVisible(True)
        self.upd_bar.setRange(0, 0)
        self.upd_status.setText('Downloading %s…' % self._upd_release['version'])
        self._dl_worker = _DownloadWorker(url, self)
        self._dl_worker.progressed.connect(self._on_download_progress)
        self._dl_worker.done.connect(self._on_download_done)
        self._dl_worker.failed.connect(self._on_download_failed)
        self._dl_worker.start()

    def _on_download_progress(self, done, total):
        if total:
            self.upd_bar.setRange(0, total)
            self.upd_bar.setValue(done)
        else:
            self.upd_bar.setRange(0, 0)

    def _on_download_done(self, path):
        from ... import updater
        self._dl_path = path
        self.upd_bar.setVisible(False)
        self.upd_status.setText('Downloaded. Installing…')
        try:
            message = updater.install_update(path)
        except Exception as exc:          # noqa: BLE001
            self.upd_install.setEnabled(True)
            self.upd_check.setEnabled(True)
            self.upd_status.setText('Install failed: %s' % exc)
            return
        self.upd_install.setEnabled(False)
        self.upd_status.setText(message)
        self.window.statusBar().showMessage('Update installed — restart ModBroom', 12000)
        QMessageBox.information(self, 'Update installed',
                                '%s\n\nRestart ModBroom to use the new version.' % message)

    def _on_download_failed(self, message):
        self.upd_bar.setVisible(False)
        self.upd_install.setEnabled(True)
        self.upd_check.setEnabled(True)
        self.upd_status.setText('Download failed: %s' % message)

    # ------------------------------------------------------------ folders
    def _browse(self, edit):
        start = edit.text().strip() or os.path.expanduser('~')
        folder = QFileDialog.getExistingDirectory(self, 'Choose folder', start)
        if folder:
            edit.setText(folder)

    def _save(self):
        s = self.state.get('settings', {})
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
