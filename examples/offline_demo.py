import json
import shutil
import tempfile
from pathlib import Path

from manifest_file_relocator import build_plan, execute_plan, rollback


example_root = Path(__file__).parent
with tempfile.TemporaryDirectory() as temporary:
    workspace = Path(temporary) / "workspace"
    shutil.copytree(example_root / "workspace", workspace)
    plan = build_plan(workspace, example_root / "manifest.json")
    journal = execute_plan(workspace, plan, plan["plan_sha256"])
    rollback_journal = rollback(workspace, journal, journal["journal_sha256"])
    print(json.dumps({"plan": plan, "execution": journal, "rollback": rollback_journal}, indent=2))
