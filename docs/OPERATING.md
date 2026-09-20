# A reviewed relocation, from plan to undo

The original classification script selected files by name, glob or image type.
This continuation separates selection from permission to move the selected bytes.
Run `python -m examples.cli_walkthrough` for the complete disposable rehearsal.
Its [captured result](../examples/cli-result.json) includes a refused stale plan,
the successful move, persisted journals and byte-identical restoration.

## Prepare and review

Use one workspace containing both source and destination directories. The
[example manifest](../examples/manifest.json) selects `inbox/*.txt` into `accepted`.
Each operation needs a unique ID, `from`, `to`, and exactly one of `file`, `glob`
or `kind: image`. Paths are relative to the workspace and use forward slashes.
`recursive: true` allows nested selection; relative subfolders are preserved.
A selector matching nothing is an error, not a successful empty move.

```sh
manifest-file-relocator plan WORKSPACE MANIFEST.json --output plan.json
```

Inspect every `source`, `destination`, byte count and SHA-256 in `plan.json`.
Then copy its `plan_sha256` into the execution command:

```sh
manifest-file-relocator execute WORKSPACE plan.json --approve-sha256 PLAN_HASH --journal execution.json
```

The approval hash is the canonical document digest, not the hash of the
pretty-printed JSON file. Editing the plan invalidates it. Execution checks all
sources and destinations before moving the first file. It copies, verifies the
copy's hash, then removes the source; this is a filesystem mutation. Stop other
writers during the operation. Keep evidence outside the paths being moved.

## Inspect and undo

The execution journal records `pending`, `moving` and `moved` per file, then an
operation status. Read that journal even when the command fails. To undo a
successful execution, review its `journal_sha256`, then run:

```sh
manifest-file-relocator rollback WORKSPACE execution.json --approve-sha256 JOURNAL_HASH --output rollback.json
```

Rollback checks the entire restoration set first. It refuses occupied original
paths and missing or changed destination bytes. `moving` can mean interruption;
the code distinguishes an unchanged source with no destination from a completed
transfer. Ambiguous states require inspection. A failed rollback is not an
automatic resumable transaction: preserve both journals and inspect actual files
before any further action. Empty destination directories can remain after undo.

Existing evidence files are refused by default. `--force` permits replacing the
chosen evidence document; retain the old one before considering that option.
The tool does not lock the filesystem, preserve a crash-proof transaction across
every copy/delete boundary, or decide whether the manifest is a good organization.
