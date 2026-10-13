---
name: abstract-intake
description: "Set up a new AnnoLab land abstract and ingest its documents — confirm scope, ask whether each file is one instrument or several, create the abstract with the annolab MCP tools, upload with the SDK. Use when starting a new title job, opening an abstract, or adding documents to an existing one."
---

# Abstract intake

The one interactive, state-creating step in the title pipeline. Requires the **annolab** MCP server (tools and the `abstract_intake` prompt) and the **annolab** skill for the SDK upload call. Use the **legal-descriptions** skill to parse the written description into AOIs.

## Run the server's workflow

Fetch and follow the `abstract_intake` prompt from the `annolab` MCP server. It owns the procedure: resolve the project, find before create, confirm scope in plain terms, ask single-vs-multi per file, present one proposal, `create_abstract`, upload, hand off. The tool descriptions carry the rest.

Two things are asked of the operator and nothing else: the **scope** (AOI) and, per file, **single instrument or several**. OCR is always on and the workflow is always `land_title`.

## What lives on the client

The server cannot see the operator's files or disk, so these are the skill's responsibility.

**Uploads** go through the SDK (see the **annolab** skill):

```python
abstract = lab.find_project(project_name).find_abstract(abstract_name)  # names as returned by the tools
result = abstract.upload_file(file=doc.filename, ocr=True, workflow="land_title")
```

**The intake record** captures intent alongside the ids the platform assigned. Write it to `intake/<abstract-name>.json` before the first upload and save it after each one, so a crash leaves a record of exactly what landed.

```
IntakeRecord {
  project:        str,
  abstract_name:  str,          # as returned by create_abstract / find_abstracts
  abstract_id:    int | None,
  aoi:            [AOI],
  documents: [{
    filename:     str,
    kind:         SINGLE_INSTRUMENT | MULTI_INSTRUMENT,
    source_id:    int | None,   # result.pending_source_id
    execution_id: int | None,   # result.execution_id
  }],
}
```

**Idempotency.** Before uploading a file, skip it if the record already has a `source_id` for it or `get_abstract_upload_status` (detail `full`) already lists a source of that name. If the record exists but the abstract does not, the previous run failed before creation; resume from `create_abstract`.

## Unattended runs

Proceed only when the caller supplied a `kind` for every document (an orchestrator passing a decided manifest is fine). Otherwise write the record with those documents unanswered, create nothing, and report what needs a decision. Never default `kind`.

## Reporting

Abstract name, scope in plain terms, files uploaded, files skipped as already present, and where the record was written. Do not print the record. Intake ends when uploads are accepted; readiness is the **abstract-status** skill.
