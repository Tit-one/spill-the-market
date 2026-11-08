"""Durable atomic file commits resilient to short Windows sharing denials."""
from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import uuid4

MAX_REPLACE_SECONDS = 1.5


class AtomicWriteCancelled(InterruptedError):
    pass


class AtomicWriteError(OSError):
    """The last committed destination remains intact after an unsuccessful save."""


def _cancel(cancel_check):
    if cancel_check and cancel_check():
        raise AtomicWriteCancelled("Atomic save cancelled; the previous committed file was preserved")


def _transient_replace_error(error: OSError) -> bool:
    return (getattr(error, "winerror", None) in {5, 32, 33} or
            os.name == "nt" and isinstance(error, PermissionError))


def atomic_write(path: Path, write, *, description="file", cancel_check=None):
    """Write once to an exclusive sibling, fsync/close it, then retry only replace.

    Every writer owns a unique staging name. No destination is unlinked or
    truncated; failed attempts cannot destroy an earlier committed checkpoint.
    Sharing/access denials get at most 1.5 seconds of bounded backoff. Other
    errors fail immediately with their original cause and actionable context.
    """
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    failure = None
    try:
        _cancel(cancel_check)
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as stream:
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        deadline, delay = time.monotonic() + MAX_REPLACE_SECONDS, .025
        while True:
            _cancel(cancel_check)
            try:
                os.replace(temporary, path)
                return
            except OSError as error:
                remaining = deadline - time.monotonic()
                if not _transient_replace_error(error) or remaining <= 0:
                    raise
                _cancel(cancel_check)
                time.sleep(min(delay, remaining))
                delay = min(.25, delay * 2)
    except AtomicWriteCancelled as error:
        failure = error
        raise
    except OSError as error:
        failure = AtomicWriteError(error.errno,
            f"Cannot commit {description}; any previous committed file was preserved. "
            "Check file locks, permissions and disk space, then resume this run. "
            f"Windows error: {getattr(error, 'winerror', None)}.", str(path))
        raise failure from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup_error:
            if failure is not None:
                failure.add_note(f"This writer's staged file could not be removed: {temporary} ({cleanup_error})")
            else:
                raise AtomicWriteError(cleanup_error.errno,
                    "Atomic-save staging cleanup failed; inspect this writer's temporary file.", str(temporary)) from cleanup_error
