"""Exercise actual CLI approval, stale-plan refusal, durable journals and rollback."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def invoke(*args, succeeds=True):
    result = subprocess.run([sys.executable, "-m", "manifest_file_relocator.cli", *map(str, args)], capture_output=True, text=True)
    if succeeds:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0
    return result


with tempfile.TemporaryDirectory(prefix="relocation-cli-") as temporary:
    root = Path(temporary)
    workspace = root / "workspace"
    examples = Path(__file__).parent
    shutil.copytree(examples / "workspace", workspace)
    def snapshot():
        return {p.relative_to(workspace).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in workspace.rglob("*") if p.is_file()}
    before = snapshot()
    plan_path, journal_path, rollback_path = [root / name for name in ("plan.json", "execution.json", "rollback.json")]
    plan = invoke("plan", workspace, examples / "manifest.json", "--output", plan_path)
    edited = workspace / "inbox/alpha.txt"
    original = edited.read_bytes()
    edited.write_bytes(b"synthetic change after planning")
    refused = invoke("execute", workspace, plan_path, "--approve-sha256", plan["plan_sha256"], "--journal", journal_path, succeeds=False)
    assert "Source changed after planning" in refused.stderr
    assert not journal_path.exists() and not (workspace / "accepted").exists()
    edited.write_bytes(original)
    execution = invoke("execute", workspace, plan_path, "--approve-sha256", plan["plan_sha256"], "--journal", journal_path)
    assert execution == json.loads(journal_path.read_text())
    restored = invoke("rollback", workspace, journal_path, "--approve-sha256", execution["journal_sha256"], "--output", rollback_path)
    assert restored == json.loads(rollback_path.read_text())
    assert snapshot() == before
    print(json.dumps({"synthetic": True, "planned_files": plan["item_count"], "stale_plan_refused_before_move": True, "execution_status": execution["status"], "rollback_status": restored["status"], "original_bytes_restored": True, "durable_documents": ["plan.json", "execution.json", "rollback.json"]}, indent=2))
