"""Execute and roll back an approved content-addressed plan."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .planner import atomic_json, canonical_hash, sha256_file, validate_unique_paths


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_document(path: Path, *, max_bytes: int = 5_000_000) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ValueError("Evidence document exceeds the size bound")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Evidence document must be an object")
    return payload


def _contained(root: Path, value: Any) -> Path:
    text = str(value or "")
    relative = PurePosixPath(text)
    if not text or relative.is_absolute() or ".." in relative.parts or "\\" in text or ":" in text:
        raise ValueError("Evidence contains an unsafe relative path")
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Evidence path escaped the workspace")
    return path



def guard_evidence_path(workspace: Path, document: dict[str, Any], evidence_path: Path | None) -> None:
    """Evidence must never overwrite or obstruct any source/destination path."""
    if evidence_path is None:
        return
    workspace = workspace.resolve()
    evidence = evidence_path.resolve()
    for item in document.get("items", []):
        if not isinstance(item, dict):
            raise ValueError("Invalid relocation item")
        for key in ("source", "destination"):
            protected = _contained(workspace, item.get(key))
            aliases = evidence == protected or evidence.is_relative_to(protected) or protected.is_relative_to(evidence)
            if evidence.exists() and protected.exists():
                aliases = aliases or os.path.samefile(evidence, protected)
            if aliases:
                raise ValueError("Evidence output overlaps a relocation source or destination")


def _verified_transfer(source: Path, destination: Path, expected_hash: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".relocate", dir=destination.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary, follow_symlinks=False)
        if sha256_file(temporary) != expected_hash:
            raise IOError("Copied bytes failed SHA-256 verification")
        os.replace(temporary, destination)
        try:
            source.unlink()
        except Exception:
            if destination.exists() and sha256_file(destination) == expected_hash:
                destination.unlink()
            raise
    finally:
        if temporary.exists():
            temporary.unlink()


def _seal_and_persist(
    payload: dict[str, Any],
    hash_field: str,
    evidence_path: Path | None,
) -> None:
    payload[hash_field] = canonical_hash(payload, hash_field)
    if evidence_path is not None:
        atomic_json(evidence_path, payload)


def execute_plan(
    workspace: Path,
    plan: dict[str, Any],
    approved_hash: str,
    journal_path: Path | None = None,
    *,
    replace_journal: bool = False,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    journal_path = journal_path.resolve() if journal_path is not None else None
    if journal_path is not None and journal_path.exists() and not replace_journal:
        raise FileExistsError("Execution journal exists; explicit replacement approval is required")
    if plan.get("version") != 1 or not isinstance(plan.get("items"), list):
        raise ValueError("Invalid relocation plan")
    actual_hash = canonical_hash(plan, "plan_sha256")
    if plan.get("plan_sha256") != actual_hash or approved_hash != actual_hash:
        raise PermissionError("Plan hash was not explicitly approved or no longer matches")
    if plan.get("item_count") != len(plan["items"]):
        raise ValueError("Plan item count does not match")

    validate_unique_paths(workspace, plan["items"])
    guard_evidence_path(workspace, plan, journal_path)
    prepared: list[tuple[dict[str, Any], Path, Path]] = []
    for item in plan["items"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid plan item")
        source = _contained(workspace, item.get("source"))
        destination = _contained(workspace, item.get("destination"))
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(f"Source is unavailable or not a regular file: {item.get('source')}")
        if destination.exists():
            raise FileExistsError(f"Destination already exists: {item.get('destination')}")
        if source.stat().st_size != item.get("bytes") or sha256_file(source) != item.get("sha256"):
            raise RuntimeError(f"Source changed after planning: {item.get('source')}")
        prepared.append((item, source, destination))

    journal: dict[str, Any] = {
        "version": 1,
        "plan_sha256": actual_hash,
        "started_at": _now(),
        "status": "running",
        "items": [{**item, "status": "pending"} for item, _, _ in prepared],
    }
    _seal_and_persist(journal, "journal_sha256", journal_path)
    try:
        for index, (item, source, destination) in enumerate(prepared):
            journal["items"][index]["status"] = "moving"
            _seal_and_persist(journal, "journal_sha256", journal_path)
            _verified_transfer(source, destination, str(item["sha256"]))
            journal["items"][index]["status"] = "moved"
            _seal_and_persist(journal, "journal_sha256", journal_path)
        journal["status"] = "complete"
    except Exception as exc:
        journal["status"] = "failed"
        journal["error_type"] = type(exc).__name__
        raise
    finally:
        journal["finished_at"] = _now()
        _seal_and_persist(journal, "journal_sha256", journal_path)
    return journal


def rollback(
    workspace: Path,
    journal: dict[str, Any],
    approved_hash: str,
    output_path: Path | None = None,
    *,
    replace_output: bool = False,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    output_path = output_path.resolve() if output_path is not None else None
    if output_path is not None and output_path.exists() and not replace_output:
        raise FileExistsError("Rollback journal exists; explicit replacement approval is required")
    if journal.get("version") != 1 or not isinstance(journal.get("items"), list):
        raise ValueError("Invalid execution journal")
    actual_hash = canonical_hash(journal, "journal_sha256")
    if journal.get("journal_sha256") != actual_hash or approved_hash != actual_hash:
        raise PermissionError("Journal hash was not explicitly approved or no longer matches")
    validate_unique_paths(workspace, journal["items"])
    guard_evidence_path(workspace, journal, output_path)
    prepared: list[tuple[dict[str, Any], Path, Path]] = []
    for item in reversed(journal["items"]):
        status = item.get("status")
        if status == "pending":
            continue
        if status not in {"moving", "moved"}:
            raise ValueError(f"Unknown execution item status: {status!r}")
        original = _contained(workspace, item.get("source"))
        moved = _contained(workspace, item.get("destination"))
        original_matches = (
            original.is_file()
            and not original.is_symlink()
            and sha256_file(original) == item.get("sha256")
        )
        moved_matches = (
            moved.is_file()
            and not moved.is_symlink()
            and sha256_file(moved) == item.get("sha256")
        )
        if status == "moving" and original_matches and not moved.exists():
            continue
        if original.exists():
            raise FileExistsError(f"Original path is occupied or ambiguous: {item.get('source')}")
        if not moved_matches:
            raise RuntimeError(f"Moved file is missing or changed: {item.get('destination')}")
        prepared.append((item, moved, original))
    rollback_journal: dict[str, Any] = {
        "version": 1,
        "source_journal_sha256": actual_hash,
        "started_at": _now(),
        "status": "running",
        "items": [{**item, "status": "pending"} for item, _, _ in prepared],
    }
    _seal_and_persist(rollback_journal, "rollback_sha256", output_path)
    try:
        for index, (item, moved, original) in enumerate(prepared):
            rollback_journal["items"][index]["status"] = "restoring"
            _seal_and_persist(rollback_journal, "rollback_sha256", output_path)
            _verified_transfer(moved, original, str(item["sha256"]))
            rollback_journal["items"][index]["status"] = "restored"
            _seal_and_persist(rollback_journal, "rollback_sha256", output_path)
        rollback_journal["status"] = "complete"
    except Exception as exc:
        rollback_journal["status"] = "failed"
        rollback_journal["error_type"] = type(exc).__name__
        raise
    finally:
        rollback_journal["finished_at"] = _now()
        _seal_and_persist(rollback_journal, "rollback_sha256", output_path)
    return rollback_journal


def write_evidence(path: Path, payload: dict[str, Any], *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError("Evidence output exists; use force only after reviewing the target path")
    atomic_json(path, payload)
