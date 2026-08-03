"""Deterministic serialization, hashes, and atomic workspace writes."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


class UnsafeWriteTargetError(OSError):
    """A managed file output is occupied by a non-regular filesystem object."""


class StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: StrictSafeLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def strict_yaml_load(text: str) -> Any:
    return yaml.load(text, Loader=StrictSafeLoader)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_object(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def load_yaml(path: Path) -> Any:
    return strict_yaml_load(path.read_text(encoding="utf-8"))


def dump_yaml(value: Any) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=100)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"missing YAML frontmatter: {path}")
    try:
        raw, body = text[4:].split("\n---\n", 1)
    except ValueError as error:
        raise ValueError(f"unterminated YAML frontmatter: {path}") from error
    value = strict_yaml_load(raw)
    if not isinstance(value, dict):
        raise ValueError(f"frontmatter must be a mapping: {path}")
    return value, body


def dump_frontmatter(value: dict[str, Any], body: str) -> str:
    return f"---\n{dump_yaml(value)}---\n{body.lstrip()}"


class Writer:
    """Write atomically, or record intended paths in dry-run mode."""

    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.touched: list[Path] = []

    def text(self, path: Path, content: str, *, mode: int | None = None) -> None:
        self.touched.append(path)
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if mode is not None:
                temp_path.chmod(mode)
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def bytes(self, path: Path, content: bytes, *, mode: int | None = None) -> None:
        self.touched.append(path)
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if mode is not None:
                temp_path.chmod(mode)
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def json(self, path: Path, value: Any) -> None:
        self.text(path, dump_json(value))

    def yaml(self, path: Path, value: Any) -> None:
        self.text(path, dump_yaml(value))

    def jsonl(self, path: Path, records: list[dict[str, Any]]) -> None:
        content = "".join(canonical_json(record) + "\n" for record in records)
        self.text(path, content)


class TransactionWriter:
    """Stage a set of writes and roll the whole set back if commit fails."""

    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.touched: list[Path] = []
        self._writes: dict[Path, tuple[str | bytes, int | None]] = {}

    def text(self, path: Path, content: str, *, mode: int | None = None) -> None:
        if path not in self._writes:
            self.touched.append(path)
        self._writes[path] = (content, mode)

    def bytes(self, path: Path, content: bytes, *, mode: int | None = None) -> None:
        if path not in self._writes:
            self.touched.append(path)
        self._writes[path] = (content, mode)

    def json(self, path: Path, value: Any) -> None:
        self.text(path, dump_json(value))

    def yaml(self, path: Path, value: Any) -> None:
        self.text(path, dump_yaml(value))

    def jsonl(self, path: Path, records: list[dict[str, Any]]) -> None:
        self.text(path, "".join(canonical_json(record) + "\n" for record in records))

    def commit(self) -> None:
        for path in self._writes:
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise UnsafeWriteTargetError(
                    f"Refusing to replace non-regular managed file target: {path}"
                )
        if self.dry_run:
            return
        staged: dict[Path, Path] = {}
        replaced: list[tuple[Path, Path | None]] = []
        try:
            for path, (content, mode) in self._writes.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
                temp_path = Path(temp_name)
                if isinstance(content, bytes):
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(content)
                        handle.flush()
                        os.fsync(handle.fileno())
                else:
                    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                        handle.write(content)
                        handle.flush()
                        os.fsync(handle.fileno())
                if mode is not None:
                    temp_path.chmod(mode)
                staged[path] = temp_path
            for path, temp_path in staged.items():
                backup: Path | None = None
                if path.is_symlink() or (path.exists() and not path.is_file()):
                    raise UnsafeWriteTargetError(
                        f"Managed file target changed to a non-regular object: {path}"
                    )
                if path.exists():
                    backup = path.parent / f".{path.name}.seamwise-backup-{os.getpid()}"
                    if backup.exists():
                        raise FileExistsError(f"transaction backup exists: {backup}")
                    os.replace(path, backup)
                replaced.append((path, backup))
                os.replace(temp_path, path)
        except Exception:
            for path, backup in reversed(replaced):
                if path.exists():
                    path.unlink()
                if backup is not None and backup.exists():
                    os.replace(backup, path)
            raise
        else:
            for _, backup in replaced:
                if backup is not None:
                    with contextlib.suppress(OSError):
                        backup.unlink()
        finally:
            for temp_path in staged.values():
                if temp_path.exists():
                    temp_path.unlink()


def private_state_path(root: Path, *parts: str) -> Path:
    """Resolve local runtime state outside the consumer worktree."""

    resolved_root = root.resolve()
    try:
        output = subprocess.run(
            ["git", "rev-parse", "--git-path", "seamwise"],
            cwd=resolved_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        base = Path(output)
        if not base.is_absolute():
            base = resolved_root / base
        digest = hashlib.sha256(str(resolved_root).encode("utf-8")).hexdigest()[:20]
        base = base.resolve() / "workspaces" / digest
    except (FileNotFoundError, subprocess.CalledProcessError):
        digest = hashlib.sha256(str(resolved_root).encode("utf-8")).hexdigest()[:20]
        configured = os.environ.get("SEAMWISE_STATE_HOME")
        if configured:
            state_home = Path(configured).expanduser().resolve()
        elif os.environ.get("XDG_STATE_HOME"):
            state_home = Path(os.environ["XDG_STATE_HOME"]).expanduser().resolve() / "seamwise"
        elif sys.platform == "darwin":
            state_home = Path.home() / "Library" / "Application Support" / "seamwise"
        else:
            state_home = Path.home() / ".local" / "state" / "seamwise"
        base = state_home / "workspaces" / digest
    return base.joinpath(*parts)


def workspace_lock_path(root: Path) -> Path:
    """Resolve the non-authoritative lock outside sandbox-protected Git metadata."""

    resolved_root = root.resolve()
    digest = hashlib.sha256(str(resolved_root).encode("utf-8")).hexdigest()[:20]
    configured = os.environ.get("SEAMWISE_LOCK_HOME")
    if configured:
        lock_home = Path(os.path.abspath(os.path.expanduser(configured)))
    else:
        user_id = str(os.getuid()) if hasattr(os, "getuid") else "user"
        lock_home = Path(tempfile.gettempdir()).resolve() / f"seamwise-locks-{user_id}"
    return lock_home / digest / "workspace.lock"


def _ensure_private_lock_directory(path: Path) -> None:
    """Create and verify a user-private directory without accepting a symlink leaf."""

    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise UnsafeWriteTargetError(f"Unsafe workspace lock directory: {path}")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise UnsafeWriteTargetError(f"Unsafe workspace lock directory: {path}")
    metadata = path.stat()
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise UnsafeWriteTargetError(f"Workspace lock directory is not user-owned: {path}")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise UnsafeWriteTargetError(f"Workspace lock directory is not private: {path}")


@contextlib.contextmanager
def workspace_lock(root: Path, *, dry_run: bool = False) -> Iterator[None]:
    """Serialize mutations with an advisory lock on supported POSIX hosts."""

    if dry_run:
        yield
        return
    import fcntl

    lock_path = workspace_lock_path(root)
    lock_home = lock_path.parents[1]
    _ensure_private_lock_directory(lock_home)
    _ensure_private_lock_directory(lock_path.parent)
    if lock_path.is_symlink() or (lock_path.exists() and not lock_path.is_file()):
        raise UnsafeWriteTargetError(f"Unsafe workspace lock file: {lock_path}")
    flags = os.O_CREAT | os.O_RDWR | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise UnsafeWriteTargetError(
            f"Unable to open workspace lock safely: {lock_path}"
        ) from error
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        os.close(descriptor)
        raise UnsafeWriteTargetError(f"Unsafe workspace lock file: {lock_path}")
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
