---
name: abstract-status
description: "Check whether an AnnoLab abstract has finished ingesting and is ready for title work, using the annolab MCP get_abstract_upload_status tool. Use when asking if an abstract is done, what's still processing, what failed, or whether a job can start."
---

# Abstract status

Answer "is this abstract ready?" with the `get_abstract_upload_status` tool from the `annolab` MCP server. Resolve the abstract with `list_projects` → `find_abstracts` first.

**Read-only and idempotent.** Never creates, uploads, or modifies anything; safe from any session, including an orchestrator between steps. If the abstract does not exist, say so and stop — creating it is the **abstract-intake** skill.

The tool's description defines readiness (four criteria, all from one call) and returns `isReady` alongside the criteria. Report each criterion, not just the verdict. Use `detail: "full"` only when a person needs per-source rows.

## Waiting

Return immediately unless the caller asked to wait. When waiting, re-call the tool no more than every 15 seconds; `READY` and `ERRORED` are terminal, and terminal does not mean succeeded. For long waits in an unattended run, return the current status and schedule a later check rather than holding a session open.

## Reporting

```
Sec 15-21N-16W — RUNNING
  12 sources: 10 ready, 1 running, 1 failed

  Blockers (1):
  · warranty_deeds_1978.pdf — OCR failed, page 14 has no extractable
    text layer. Re-upload at higher DPI.
```

Counts and blockers, ranked by how much work they gate; never the full source list or raw tool output. A clean result is one line.
