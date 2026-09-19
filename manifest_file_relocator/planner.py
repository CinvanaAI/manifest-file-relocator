"""Build an immutable, content-addressed relocation plan without moving files."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


OPERATION_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(payload: dict[str, Any], excluded: str) -> str:
    body = {key: value for key, value in payload.items() if key != excluded}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _relative(value: Any, label: str) -> PurePosixPath:
    text = str(value or "")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or "\\" in text or ":" in text:
        raise ValueError(f"{label} must be a contained relative POSIX path")
    return path


def _resolve(root: Path, relative: PurePosixPath) -> Path:
    candidate = root.joinpath(*relative.parts).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Path escaped the workspace root")
    return candidate


def _manifest(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    if len(raw) > 1_000_000:
        raise ValueError("Manifest exceeds one megabyte")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Manifest must be an object")
    return payload, hashlib.sha256(raw).hexdigest()


def validate_unique_paths(workspace: Path, items: list[dict[str, Any]]) -> None:
    """Use resolved Path equality (including Windows case rules), before any writes."""
    paths: list[Path] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid relocation item")
        for key in ("source", "destination"):
            path = _resolve(workspace, _relative(item.get(key), key))
            if any(path == prior or path.is_relative_to(prior) or prior.is_relative_to(path) for prior in paths):
                raise ValueError("Plan contains duplicate, aliased, or overlapping source/destination paths")
            paths.append(path)


def build_plan(workspace: Path, manifest_path: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise NotADirectoryError(workspace)
    manifest, manifest_hash = _manifest(manifest_path)
    if manifest.get("version") != 1 or not isinstance(manifest.get("operations"), list):
        raise ValueError("Manifest version must be 1 and operations must be an array")
    if len(manifest["operations"]) > 200:
        raise ValueError("Manifest exceeds 200 operations")
    plan_items: list[dict[str, Any]] = []
    operation_ids: set[str] = set()
    source_paths: set[str] = set()
    destination_paths: set[str] = set()

    for raw in manifest["operations"]:
        if not isinstance(raw, dict):
            raise ValueError("Every operation must be an object")
        operation_id = str(raw.get("id") or "")
        if not OPERATION_ID.fullmatch(operation_id) or operation_id in operation_ids:
            raise ValueError(f"Invalid or duplicate operation id: {operation_id!r}")
        operation_ids.add(operation_id)
        source_relative = _relative(raw.get("from"), "from")
        destination_relative = _relative(raw.get("to"), "to")
        source_root = _resolve(workspace, source_relative)
        destination_root = _resolve(workspace, destination_relative)
        if not source_root.is_dir():
            raise NotADirectoryError(source_root)
        recursive = raw.get("recursive", False) is True
        selectors = [key for key in ("file", "glob", "kind") if key in raw]
        if len(selectors) != 1:
            raise ValueError(f"Operation {operation_id} needs exactly one of file, glob, or kind")
        selector = selectors[0]
        candidates: list[Path]
        if selector == "file":
            file_relative = _relative(raw["file"], "file")
            if len(file_relative.parts) != 1:
                raise ValueError("file selects one direct child name")
            candidates = [source_root / file_relative.name]
        elif selector == "kind":
            if str(raw["kind"]).casefold() != "image":
                raise ValueError("Only the built-in image kind is supported")
            iterator = source_root.rglob("*") if recursive else source_root.iterdir()
            candidates = [path for path in iterator if path.is_file() and path.suffix.casefold() in IMAGE_SUFFIXES]
        else:
            pattern = str(raw["glob"] or "")
            if not pattern or ".." in PurePosixPath(pattern).parts or "\\" in pattern or ":" in pattern:
                raise ValueError("glob must be a contained POSIX pattern")
            if not recursive and "/" in pattern:
                raise ValueError("non-recursive globs cannot contain path separators")
            candidates = list(source_root.rglob(pattern) if recursive else source_root.glob(pattern))
        candidates = sorted(path for path in candidates if path.is_file() and not path.is_symlink())
        if not candidates:
            raise ValueError(f"Operation {operation_id} matched no regular files")
        for source in candidates:
            source = source.resolve()
            if not source.is_relative_to(source_root):
                raise ValueError("Matched source escaped its declared source directory")
            suffix = source.relative_to(source_root)
            destination = (destination_root / suffix).resolve()
            if not destination.is_relative_to(destination_root):
                raise ValueError("Destination escaped its declared directory")
            source_key = source.relative_to(workspace).as_posix()
            destination_key = destination.relative_to(workspace).as_posix()
            if source_key == destination_key or source_key in source_paths or destination_key in destination_paths:
                raise ValueError("Plan contains duplicate or identical source/destination paths")
            source_paths.add(source_key)
            destination_paths.add(destination_key)
            plan_items.append(
                {
                    "operation_id": operation_id,
                    "source": source_key,
                    "destination": destination_key,
                    "bytes": source.stat().st_size,
                    "sha256": sha256_file(source),
                }
            )

    if not plan_items:
        raise ValueError("Manifest produced an empty relocation plan")

    validate_unique_paths(workspace, plan_items)

    plan: dict[str, Any] = {
        "version": 1,
        "workspace_name": workspace.name,
        "manifest_sha256": manifest_hash,
        "item_count": len(plan_items),
        "items": plan_items,
    }
    plan["plan_sha256"] = canonical_hash(plan, "plan_sha256")
    return plan
