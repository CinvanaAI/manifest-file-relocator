# Security

- All manifest and evidence paths are relative POSIX paths contained under one explicit workspace root.
- Symlinks are never planned or executed.
- Planning is read-only and records source size and SHA-256.
- Execution requires the exact reviewed plan hash and revalidates every source and destination before moving anything.
- The execution journal is created before the first move and atomically updated around every transfer. An interrupted `moving` item is rolled back only when exactly one verified copy exists.
- Destination overwrite is never permitted.
- Each transfer copies to a destination-local temporary file, verifies SHA-256, atomically publishes it, and only then removes the source.
- Rollback requires a reviewed execution-journal hash and refuses changed destinations or occupied original paths.
- Evidence files are no-overwrite by default.

This does not replace backups. Review plans carefully, especially recursive globs, and test on disposable data before using it on irreplaceable files.
