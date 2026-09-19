"""Plan, execute, and roll back manifest-driven file relocations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .executor import guard_evidence_path, execute_plan, load_document, rollback, write_evidence
from .planner import build_plan


def _preflight_output(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError("Evidence output exists; refusing state change without --force")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run-first, content-addressed file relocation.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("workspace", type=Path)
    plan_parser.add_argument("manifest", type=Path)
    plan_parser.add_argument("--output", type=Path, required=True)
    plan_parser.add_argument("--force", action="store_true")

    execute_parser = subparsers.add_parser("execute")
    execute_parser.add_argument("workspace", type=Path)
    execute_parser.add_argument("plan", type=Path)
    execute_parser.add_argument("--approve-sha256", required=True)
    execute_parser.add_argument("--journal", type=Path, required=True)
    execute_parser.add_argument("--force", action="store_true")

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("workspace", type=Path)
    rollback_parser.add_argument("journal", type=Path)
    rollback_parser.add_argument("--approve-sha256", required=True)
    rollback_parser.add_argument("--output", type=Path, required=True)
    rollback_parser.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.command == "plan":
        _preflight_output(args.output, args.force)
        result = build_plan(args.workspace, args.manifest)
        if args.output.resolve() == args.manifest.resolve():
            raise ValueError("Plan output must not replace its source manifest")
        guard_evidence_path(args.workspace, result, args.output)
        write_evidence(args.output, result, force=args.force)
    elif args.command == "execute":
        _preflight_output(args.journal, args.force)
        result = execute_plan(
            args.workspace,
            load_document(args.plan),
            args.approve_sha256,
            journal_path=args.journal,
            replace_journal=args.force,
        )
    else:
        _preflight_output(args.output, args.force)
        result = rollback(
            args.workspace,
            load_document(args.journal),
            args.approve_sha256,
            output_path=args.output,
            replace_output=args.force,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
