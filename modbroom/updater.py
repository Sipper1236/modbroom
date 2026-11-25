"""Self-updater.

Checks the project's GitHub releases for a newer version, downloads the matching
build and replaces the running executable.

Design constraints:
- stdlib only (no requests) so the frozen exe stays self-contained.
- On Windows a running .exe cannot be overwritten or deleted, so the current
  binary is renamed to *.old.exe, the new one is moved into place, and the old
  one is deleted on the next launch.
- When running from source (not frozen) there is no binary to replace, so the
  caller is told to open the releases page instead.
- Nothing happens without the user confirming: the updater only *downloads and
  stages* until it is told to install.
"""
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__

REPO = 'Sipper1236/modbroom'
API_LATEST = 'https://api.github.com/repos/%s/releases/latest' % REPO
RELEASES_PAGE = 'https://github.com/%s/releases' % REPO
UA = 'ModBroom/%s (self-updater)' % __version__
TIMEOUT = 20


class UpdateError(Exception):
    pass


def _parse_version(text):
    """'v1.2.3' -> (1, 2, 3). Junk -> (0,)."""
    raw = (text or '').strip().lstrip('vV')
    parts = []
    for chunk in raw.split('.'):
        num = ''
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        if not num:
            break
        parts.append(int(num))
    return tuple(parts) if parts else (0,)


def is_newer(candidate, current=__version__):
    """True when candidate version is strictly newer than current."""
    c, cur = _parse_version(candidate), _parse_version(current)
    # pad so 1.2 == 1.2.0
    length = max(len(c), len(cur))
    c += (0,) * (length - len(c))
    cur += (0,) * (length - len(cur))
    return c > cur


def _get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise UpdateError('GitHub returned HTTP %s' % exc.code)
    except urllib.error.URLError as exc:
        raise UpdateError('No network connection (%s)' % exc.reason)
    except (ValueError, OSError) as exc:
        raise UpdateError('Could not read the release info (%s)' % exc)


def platform_asset_name():
    """Name of the release asset for the current platform."""
    if sys.platform.startswith('win'):
        return 'ModBroom.exe'
    if sys.platform == 'darwin':
        return 'ModBroom'
    return 'ModBroom'


def current_executable():
    """Path of the running binary, or None when running from source."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve()
    return None


def fetch_latest_release():
    """Returns {'version', 'tag', 'url', 'notes', 'assets': {name: url}}."""
    data = _get_json(API_LATEST)
    tag = data.get('tag_name') or ''
    assets = {}
    for a in data.get('assets') or []:
        name = a.get('name')
        if name:
            assets[name] = a.get('browser_download_url')
    return {
        'version': tag.lstrip('vV'),
        'tag': tag,
        'url': data.get('html_url') or RELEASES_PAGE,
        'notes': (data.get('body') or '').strip(),
        'assets': assets,
        'published_at': data.get('published_at'),
    }


def check_for_update(current=__version__):
    """Check the release feed. Returns (release_or_None, message).

    The message is human-readable and safe to show in the UI.
    """
    rel = fetch_latest_release()
    if not rel['version']:
        return None, 'No release information found.'
    if is_newer(rel['version'], current):
        return rel, 'Version %s is available (you have %s).' % (rel['version'], current)
    return None, 'You are up to date (%s).' % current


def download_asset(url, dest_dir=None, progress=None):
    """Download a release asset to dest_dir. Returns the local path."""
    dest_dir = Path(dest_dir or tempfile.gettempdir())
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = url.rsplit('/', 1)[-1] or 'ModBroom.download'
    target = dest_dir / name
    tmp = target.with_suffix(target.suffix + '.part')
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get('Content-Length') or 0)
            done = 0
            with open(tmp, 'wb') as fh:
                while True:
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except urllib.error.URLError as exc:
        raise UpdateError('Download failed (%s)' % exc.reason)
    except OSError as exc:
        raise UpdateError('Could not write the download (%s)' % exc)
    tmp.replace(target)
    return target


def install_update(new_binary):
    """Replace the running executable with new_binary.

    Returns a short description of what happened. On Windows the old binary is
    renamed (allowed while running) and cleaned up on the next launch.
    """
    new_binary = Path(new_binary)
    exe = current_executable()
    if exe is None:
        raise UpdateError('Cannot replace the binary while running from source.')
    if not new_binary.exists():
        raise UpdateError('Downloaded file is missing.')

    if sys.platform.startswith('win'):
        old = exe.with_name(exe.name + '.old')
        try:
            if old.exists():
                old.unlink()
        except OSError:
            pass
        try:
            os.replace(str(exe), str(old))
        except OSError as exc:
            raise UpdateError('Could not set the old version aside (%s)' % exc)
        try:
            shutil.copy2(str(new_binary), str(exe))
        except OSError as exc:
            # put the old one back so the user is not left without an app
            try:
                os.replace(str(old), str(exe))
            except OSError:
                pass
            raise UpdateError('Could not install the new version (%s)' % exc)
        # the old copy is removed the next time the app starts
        _schedule_cleanup(old)
        return 'Installed %s. Restart ModBroom to finish.' % exe.name

    try:
        shutil.copy2(str(new_binary), str(exe))
    except OSError as exc:
        raise UpdateError('Could not install the new version (%s)' % exc)
    return 'Installed %s. Restart ModBroom to use the new version.' % exe.name


def app_dir():
    """Where ModBroom keeps its own state (same place as the rest of the app)."""
    return Path(os.path.expanduser('~')) / '.modbroom'


def _schedule_cleanup(old_path):
    """Ask the app to delete the leftover .old.exe the next time it starts."""
    marker = app_dir() / 'cleanup.txt'
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(old_path), encoding='utf-8')
    except OSError:
        pass


def run_pending_cleanup():
    """Delete a leftover *.old.exe from a previous update. Safe to call always."""
    marker = app_dir() / 'cleanup.txt'
    if not marker.is_file():
        return
    try:
        old = marker.read_text(encoding='utf-8').strip()
        marker.unlink()
        p = Path(old)
        if p.is_file():
            p.unlink()
    except OSError:
        pass
