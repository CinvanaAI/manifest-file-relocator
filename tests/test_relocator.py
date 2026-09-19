import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from manifest_file_relocator import (
    build_plan,
    execute_plan,
    rollback,
    sha256_file,
    write_evidence,
)
from manifest_file_relocator import executor


class RelocatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "inbox").mkdir()
        (self.root / "inbox" / "alpha.txt").write_text("alpha", encoding="utf-8")
        (self.root / "inbox" / "beta.txt").write_text("beta", encoding="utf-8")
        self.manifest = self.root / "manifest.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_manifest(self, operations: list[dict]) -> None:
        self.manifest.write_text(json.dumps({"version": 1, "operations": operations}), encoding="utf-8")

    def basic_plan(self) -> dict:
        self.write_manifest([{"id": "texts", "from": "inbox", "to": "accepted", "glob": "*.txt"}])
        return build_plan(self.root, self.manifest)

    def test_plan_is_content_addressed_and_non_mutating(self) -> None:
        plan = self.basic_plan()
        self.assertEqual(plan["item_count"], 2)
        self.assertEqual(len(plan["plan_sha256"]), 64)
        self.assertTrue((self.root / "inbox" / "alpha.txt").exists())
        self.assertFalse((self.root / "accepted").exists())

    def test_file_selector_moves_one_direct_child(self) -> None:
        self.write_manifest([{"id": "one", "from": "inbox", "to": "accepted", "file": "alpha.txt"}])
        plan = build_plan(self.root, self.manifest)
        self.assertEqual([item["source"] for item in plan["items"]], ["inbox/alpha.txt"])

    def test_path_traversal_and_unsupported_kinds_fail(self) -> None:
        for operation in (
            {"id": "bad", "from": "../outside", "to": "accepted", "glob": "*.txt"},
            {"id": "bad", "from": "inbox", "to": "accepted", "kind": "documents"},
        ):
            self.write_manifest([operation])
            with self.assertRaises(ValueError):
                build_plan(self.root, self.manifest)

    def test_empty_and_duplicate_plans_fail(self) -> None:
        self.write_manifest([{"id": "none", "from": "inbox", "to": "accepted", "glob": "*.png"}])
        with self.assertRaises(ValueError):
            build_plan(self.root, self.manifest)
        self.write_manifest(
            [
                {"id": "a", "from": "inbox", "to": "accepted", "glob": "*.txt"},
                {"id": "b", "from": "inbox", "to": "other", "file": "alpha.txt"},
            ]
        )
        with self.assertRaises(ValueError):
            build_plan(self.root, self.manifest)

    def test_execute_requires_exact_approved_hash(self) -> None:
        plan = self.basic_plan()
        with self.assertRaises(PermissionError):
            execute_plan(self.root, plan, "0" * 64)

    def test_changed_source_fails_before_any_move(self) -> None:
        plan = self.basic_plan()
        (self.root / "inbox" / "alpha.txt").write_text("changed", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            execute_plan(self.root, plan, plan["plan_sha256"])
        self.assertTrue((self.root / "inbox" / "beta.txt").exists())
        self.assertFalse((self.root / "accepted").exists())

    def test_existing_destination_fails_before_any_move(self) -> None:
        plan = self.basic_plan()
        (self.root / "accepted").mkdir()
        (self.root / "accepted" / "alpha.txt").write_text("occupied", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            execute_plan(self.root, plan, plan["plan_sha256"])
        self.assertTrue((self.root / "inbox" / "beta.txt").exists())

    def test_execute_verifies_and_moves_every_file(self) -> None:
        plan = self.basic_plan()
        journal = execute_plan(self.root, plan, plan["plan_sha256"])
        self.assertEqual(journal["status"], "complete")
        self.assertEqual(len(journal["items"]), 2)
        self.assertFalse((self.root / "inbox" / "alpha.txt").exists())
        self.assertEqual(sha256_file(self.root / "accepted" / "alpha.txt"), plan["items"][0]["sha256"])

    def test_failed_partial_execution_persists_recoverable_journal(self) -> None:
        plan = self.basic_plan()
        journal_path = self.root / "failed-journal.json"
        verified_transfer = executor._verified_transfer

        def fail_second(source: Path, destination: Path, expected_hash: str) -> None:
            if source.name == "beta.txt":
                raise OSError("synthetic transfer failure")
            verified_transfer(source, destination, expected_hash)

        with patch("manifest_file_relocator.executor._verified_transfer", side_effect=fail_second):
            with self.assertRaises(OSError):
                execute_plan(
                    self.root,
                    plan,
                    plan["plan_sha256"],
                    journal_path=journal_path,
                )

        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(journal["status"], "failed")
        self.assertEqual([item["status"] for item in journal["items"]], ["moved", "moving"])
        result = rollback(self.root, journal, journal["journal_sha256"])
        self.assertEqual(result["status"], "complete")
        self.assertTrue((self.root / "inbox" / "alpha.txt").exists())
        self.assertTrue((self.root / "inbox" / "beta.txt").exists())

    def test_rollback_requires_hash_and_restores_bytes(self) -> None:
        plan = self.basic_plan()
        journal = execute_plan(self.root, plan, plan["plan_sha256"])
        with self.assertRaises(PermissionError):
            rollback(self.root, journal, "0" * 64)
        result = rollback(self.root, journal, journal["journal_sha256"])
        self.assertEqual(result["status"], "complete")
        self.assertTrue((self.root / "inbox" / "alpha.txt").exists())
        self.assertFalse((self.root / "accepted" / "alpha.txt").exists())

    def test_rollback_refuses_changed_destination(self) -> None:
        plan = self.basic_plan()
        journal = execute_plan(self.root, plan, plan["plan_sha256"])
        (self.root / "accepted" / "alpha.txt").write_text("changed", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            rollback(self.root, journal, journal["journal_sha256"])

    def test_evidence_output_is_no_overwrite_by_default(self) -> None:
        output = self.root / "plan.json"
        write_evidence(output, {"ok": True})
        with self.assertRaises(FileExistsError):
            write_evidence(output, {"ok": False})
        self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["ok"])


if __name__ == "__main__":
    unittest.main()
