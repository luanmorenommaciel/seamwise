"""Operating-system differences, kept in one place.

Everything Seamwise needs that behaves differently on Windows, Linux, and macOS
lives here: the workspace lock primitive, link detection, private-permission
checks, and default per-user state locations. The rest of the code base stays
platform-neutral and imports from this module.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import IO, Any

SUPPORTED_PLATFORM_PREFIXES = ("linux", "darwin", "win32")

# Reparse tags that redirect a path elsewhere on Windows. Other reparse points
# (cloud-sync placeholders, deduplicated files) are ordinary files to Seamwise.
_IO_REPARSE_TAG_SYMLINK = 0xA000000C
_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # directory junctions and volume mounts
_LOCK_RETRY_SECONDS = 0.05


def supported_platform() -> bool:
    """Return whether this host is a platform Seamwise is tested on."""

    return sys.platform.startswith(SUPPORTED_PLATFORM_PREFIXES)


def is_link(path: Path) -> bool:
    """Return whether the path itself redirects elsewhere.

    Covers POSIX and Windows symlinks, plus Windows directory junctions, which
    need no privilege to create and are invisible to ``Path.is_symlink``.
    """

    if path.is_symlink():
        return True
    if sys.platform == "win32":
        try:
            metadata = os.lstat(path)
        except OSError:
            return False
        if metadata.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return metadata.st_reparse_tag in (
                _IO_REPARSE_TAG_SYMLINK,
                _IO_REPARSE_TAG_MOUNT_POINT,
            )
    return False


def group_or_other_can_access(metadata: os.stat_result) -> bool:
    """Return whether POSIX permission bits expose the object beyond its owner.

    Windows does not model group and other bits: privacy there comes from the
    access-control list inherited from the per-user profile directory, so this
    check does not apply and reports no exposure.
    """

    if sys.platform == "win32":
        return False
    return bool(stat.S_IMODE(metadata.st_mode) & 0o077)


def owned_by_another_user(metadata: os.stat_result) -> bool:
    """Return whether a POSIX object belongs to a different user."""

    if sys.platform == "win32":
        return False
    return metadata.st_uid != os.getuid()


def _windows_local_app_data() -> Path:
    configured = os.environ.get("LOCALAPPDATA")
    if configured:
        return Path(configured)
    return Path.home() / "AppData" / "Local"


def default_state_home() -> Path:
    """Return the per-user state directory used outside a Git worktree."""

    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home).expanduser().resolve() / "seamwise"
    if sys.platform == "win32":
        return _windows_local_app_data() / "seamwise" / "state"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "seamwise"
    return Path.home() / ".local" / "state" / "seamwise"


def default_lock_home() -> Path:
    """Return the per-user directory that holds advisory workspace locks."""

    if sys.platform == "win32":
        # The profile directory is private to the user by default, unlike a
        # temporary directory that a service account may share.
        return _windows_local_app_data() / "seamwise" / "locks"
    return Path(tempfile.gettempdir()).resolve() / f"seamwise-locks-{os.getuid()}"


def lock_exclusive(handle: IO[Any]) -> None:
    """Block until this handle holds the exclusive advisory lock."""

    if sys.platform == "win32":
        import msvcrt

        descriptor = handle.fileno()
        while True:
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EDEADLK):
                    raise
                time.sleep(_LOCK_RETRY_SECONDS)
            else:
                return
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def unlock(handle: IO[Any]) -> None:
    """Release the advisory lock held by this handle."""

    if sys.platform == "win32":
        import msvcrt

        descriptor = handle.fileno()
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def use_utf8_streams() -> None:
    """Emit UTF-8 on stdout and stderr whatever the host locale is.

    The machine contract is JSON read by agents and other programs. A Windows
    pipe otherwise uses the legacy code page and fails on any character outside
    it, and a POSIX ``C`` locale fails on any non-ASCII character.
    """

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")
