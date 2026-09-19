# Recorded first use

This output was produced by the included example with network connections disabled. Synthetic provider or worker replies are identified by the example; no real model quality or billing is implied.

From the installed checkout:

```sh
python -m examples.offline_demo
```

[Complete recorded output](result.json)

```text
{
  "plan": {
    "version": 1,
    "workspace_name": "workspace",
    "manifest_sha256": "ec078cda00f917153cc2d96d743e48c75a50a1faa18084f2b8918bf421cb7afc",
    "item_count": 2,
    "items": [
      {
        "operation_id": "accept-text",
        "source": "inbox/alpha.txt",
        "destination": "accepted/alpha.txt",
        "bytes": 15,
        "sha256": "71f49e4f25b46d85934e84dc2cd7263fc3e886196e66fb4dae5da8d290c29e1c"
      },
      {
        "operation_id": "accept-text",
        "source": "inbox/beta.txt",
        "destination": "accepted/beta.txt",
        "bytes": 14,
        "sha256": "895530c53db52ae4d83617feecea2e53e76b819051f9e3c677c887c76b001504"
      }
    ],
    "plan_sha256": "af7f1eb12d01bae9c36188c9788a71b8228fa27751fb6c2f9ed61d3984438af6"
  },
  "execution": {
    "version": 1,
    "plan_sha256": "af7f1eb12d01bae9c36188c9788a71b8228fa27751fb6c2f9ed61d3984438af6",
    "started_at": "2026-09-19T14:14:23Z",
    "status": "complete",
    "items": [
      {
        "operation_id": "accept-text",
        "source": "inbox/alpha.txt",
        "destination": "accepted/alpha.txt",
        "bytes": 15,
        "sha256": "71f49e4f25b46d85934e84dc2cd7263fc3e886196e66fb4dae5da8d290c29e1c",
        "status": "moved"
      },
      {
        "operation_id": "accept-text",
        "source": "inbox/beta.txt",
        "destination": "accepted/beta.txt",
        "bytes": 14,
        "sha256": "895530c53db52ae4d83617feecea2e53e76b819051f9e3c677c887c76b001504",
        "status": "moved"
      }
    ],
    "journal_sha256": "efc93a628cd1f7f5ed20a98d8c2947afd4efd262affaacc6109f2df871301c8a",
    "finished_at": "2026-09-19T14:14:23Z"
  },
  "rollback": {
    "version": 1,
    "source_journal_sha256": "efc93a628cd1f7f5ed20a98d8c2947afd4efd262affaacc6109f2df871301c8a",
    "started_at": "2026-09-19T14:14:23Z",
    "status": "complete",
    "items": [
      {
        "operation_id": "accept-text",
        "source": "inbox/beta.txt",
        "destination": "accepted/beta.txt",
        "bytes": 14,
        "sha256": "895530c53db52ae4d83617feecea2e53e76b819051f9e3c677c887c76b001504",
        "status": "restored"
      },
      {
```

The preview is shortened; the linked artifact contains the entire recorded output.

Generated timestamps and synthetic identifiers can change between runs. The demonstrated behavior and input fixture remain inspectable in the adjacent example files.
