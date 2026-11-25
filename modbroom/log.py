"""Central logging setup for ModBroom.

The log file is always written at DEBUG level and rotates, so it is safe to
leave on. The console stays quiet unless --verbose / MODBROOM_DEBUG=1 is set.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_NAME = 'modbroom'
ENV_LOG_FILE = 'MODBROOM_LOG_FILE'
ENV_DEBUG = 'MODBROOM_DEBUG'
DEFAULT_LOG = Path('.modbroom') / 'modbroom.log'
MAX_BYTES = 2 * 1024 * 1024
BACKUPS = 3
FILE_FORMAT = '%(asctime)s %(levelname)-7s %(name)s: %(message)s'
CONSOLE_FORMAT = '%(levelname)s %(name)s: %(message)s'

_configured = False


def log_path():
    """Where the rotating log lives (override with MODBROOM_LOG_FILE)."""
    custom = os.environ.get(ENV_LOG_FILE)
    if custom:
        return Path(custom).expanduser()
    return Path.home() / DEFAULT_LOG


def get_logger(name=None):
    """A child of the ModBroom logger, e.g. get_logger('dbpf')."""
    if not name:
        return logging.getLogger(LOG_NAME)
    return logging.getLogger('%s.%s' % (LOG_NAME, name))


def setup(verbose=None, log_file=None, force=False):
    """Configure logging once. Safe to call repeatedly.

    verbose=None follows the MODBROOM_DEBUG environment variable.
    """
    global _configured
    logger = get_logger()
    if _configured and not force:
        if verbose:
            logger.setLevel(logging.DEBUG)
            for handler in logger.handlers:
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
                    handler.setLevel(logging.DEBUG)
        return logger

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    path = Path(log_file or os.environ.get(ENV_LOG_FILE) or log_path()).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(str(path), maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(FILE_FORMAT))
        logger.addHandler(fh)
    except OSError:
        # A read-only home must never stop the app from starting.
        pass

    debug = verbose if verbose is not None else os.environ.get(ENV_DEBUG, '').lower() in ('1', 'true', 'yes')
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if debug else logging.WARNING)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    logger.addHandler(console)
    _configured = True
    logger.debug('logging initialised — file=%s file_level=DEBUG console_level=%s',
                 path, 'DEBUG' if debug else 'WARNING')
    return logger


def reset():
    """Drop all handlers (used by tests and by callers reconfiguring logging)."""
    global _configured
    logger = get_logger()
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    _configured = False
