# Manifest File Relocator

Preview, execute and undo an organized file move while checking that the reviewed files have not changed.

## Try it

Python 3.11+. Run from this checkout:

```sh
python -m pip install -e .
python -m examples.offline_demo
```

**Input:** Two disposable files and a manifest describing their new relative destinations.

**Result:** The real planner, executor and rollback restore the original bytes. The demo never touches your existing files.

See [the captured example](examples/RESULT.md) for the observed output and reproduction command.

## How it works

The plan binds source content hashes to contained destinations. Execution checks every source and destination before moving; a journal records observed progress for rollback.

Source: [manifest_file_relocator/planner.py](manifest_file_relocator/planner.py), [manifest_file_relocator/executor.py](manifest_file_relocator/executor.py), [examples/offline_demo.py](examples/offline_demo.py).

## Use it for your work

Use `manifest-file-relocator plan WORKSPACE MANIFEST --output plan.json`, review it, then use the CLIâ€™s exact `--approve-sha256` flow. Keep the plan and execution journal until rollback is no longer needed.

[Complete CLI rehearsal and recovery guide](docs/OPERATING.md) | [Origin and continuation](ORIGIN.md)

## Scope

Hashes bind bytes, not trusted authorship. Filesystem concurrency and crashes can still require inspection. Rollback refuses changed destination bytes or occupied original paths.

Owned code is available under the [MIT license](LICENSE.md).
