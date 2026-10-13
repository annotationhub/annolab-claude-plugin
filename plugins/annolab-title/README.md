# AnnoLab Title

Land and mineral title production with AnnoLab. The plugin connects the `annolab` MCP server and ships six thin skills that route work to it, keeping the Python SDK only for document uploads.

## What's inside

| Piece | Does |
|---|---|
| **`.mcp.json`** | Connects the `annolab` MCP server at `https://api.annolab.ai/mcp`, authenticated with `ANNOLAB_API_KEY` |
| **annolab** skill | The routing rule (MCP tools for everything, SDK for uploads), setup, and the SDK upload recipe; routes document review to the `prompt_documents` MCP tool (server-side vision model over instruments or page ranges, 50 pages per call) |
| **abstract-intake** skill | Runs the server's `abstract_intake` prompt; owns the client-side parts — SDK uploads, the intake record, idempotency, unattended behaviour |
| **abstract-status** skill | Read-only readiness via `get_abstract_upload_status`, with the reporting format |
| **legal-descriptions** skill | Parses and normalizes OK PLSS and TX block/survey/abstract descriptions; flags patterns for examiner review; hands AOIs to `create_abstract` |
| **regulatory-data** skill | Pulls wells, completion reports and spacing/pooling orders for an abstract's sections from an external provider (Convey640 today) with a bundled script that also downloads the order PDFs, then loads them through `save_abstract_wells`, `save_abstract_custom_records` and the custom-record upload tools (orders land with their PDF attached); owns the well-activity rule and the quarter-call location convention |
| **leasehold-analysis** skill | Offers the user the inputs for a leasehold analysis — leasing instruments via the county records search (user selects in AnnoLab or here), wells and OK spacing/pooling via `regulatory-data` — and runs the grouped active/inactive well decision with the user |

## Where the instructions live

The MCP server is the source of truth for how to use AnnoLab. It delivers, at connect time and per tool:

- **Server instructions** (`initialize`) — the object model, the MCP-vs-SDK split, find-before-create, confirm-scope-first, the readiness predicate, reporting rules.
- **Tool descriptions** — parameters, preconditions and next steps for `list_projects`, `find_abstracts`, `create_abstract`, `get_abstract_upload_status`, `search_county_records`, `get_county_records_search`, `add_county_records_to_abstract`, `get_add_records_status`.
- **Prompts** — `abstract_intake` and `build_abstract_from_county_records`, the two multi-step workflows.

Skills only carry what the server cannot: the SDK upload call (the server never sees the operator's files), the on-disk intake record, domain knowledge about legal descriptions, and calls to third-party data providers the server has no credentials for. When behaviour needs to change, change it in the server (`web-server/src/mcp`) first; a skill edit is only needed if the client-side part changes.

## Setup

```bash
export ANNOLAB_API_KEY="..."
pip install 'annolab>=0.7.2'
```

The same key authenticates both the MCP server (`Authorization: Api-Key …`, sent by `.mcp.json`) and the SDK (`AnnoLab()` reads `ANNOLAB_API_KEY`). The key needs `read:all` for the read tools and `write:all` for `create_abstract`, `add_county_records_to_abstract` and uploads.

For a staging or self-hosted server, override the URL in the user's own `.mcp.json` and pass `api_url=` to `AnnoLab()`.

## Design notes

**Intake asks two questions.** Scope, and single- vs multi-instrument per file. OCR is always on and the workflow is always `land_title`.

**Intake does no document analysis.** AnnoLab classifies, extracts and interprets after upload.

**The intake record captures intent.** `intake/<abstract-name>.json` records the scope, the per-file decision, and the ids the platform assigned. That is what makes a retry idempotent.

**Readiness is a predicate, not a judgment.** Four criteria from one `get_abstract_upload_status` call: `READY`, zero failed, zero running, no blockers. The tool also returns `isReady`.

**Intake and status are separate skills on purpose.** Intake is a consequential burst; status is read-only and checked repeatedly, possibly by a different person in a session with no memory of intake.

**Flag, don't adjudicate.** Legal questions are escalated as structured exceptions, never concluded.

**External data is provider-pluggable.** `regulatory-data` fixes the target shapes (`references/annolab-targets.md`) and the activity rule; each provider is a reference plus a script that emits those shapes. The provider key stays in the operator's environment and is never seen by the server or the conversation. When a provider partnership lands, the pull moves into the server as an MCP tool and the skill shrinks to the trigger and the review step.

## Unattended behavior

`abstract-intake` proceeds unattended only when the caller supplied a kind for every document. Otherwise it writes the record with those documents unanswered, creates nothing, and reports what needs a decision. `add_county_records_to_abstract` asks the user to confirm the final selection through MCP elicitation; a client that cannot answer elicitations cannot add records unattended.

`abstract-status` is safe unattended in all cases.

`regulatory-data` requires the provider key in the environment and pauses for a review of `summary.json` before pushing; it only calls `save_*` tools, never `remove_*`.

## Where this goes next

Roughly in dependency order:

- **instrument-construction** — interpreting a deed or lease into typed conveyances
- **interest-math** — exact-rational net mineral acre computation and the invariant suite
- **curative** — the exception taxonomy and requirement drafting
- **title-report** — the orchestrator that owns process, validity tiers, termination, and escalation

New capabilities should land as MCP tools first; a skill earns its place only with a distinct trigger condition and client-side work the server cannot do.

## Versions

- **0.6.1** — `regulatory-data` fetches order PDFs through Convey640's new `/<table>/document?id=<_id>` endpoint instead of guessing links; downloads are capped per run (`--max-documents`), reused from disk, and gated on the user approving the credit spend because the monthly document allowance is small
- **0.6.0** — `regulatory-data` downloads spacing/pooling order PDFs and pushes each order as a custom record with the PDF attached
- **0.5.1** — routes document review to the new `prompt_documents` MCP tool (prompt against instruments or page ranges without pulling the document into the agent's context)
- **0.5.0** — adds `leasehold-analysis`; well activity defaults to active only when production was reported in the last 12 months, confirmed by the user in bulk
- **0.4.0** — adds `regulatory-data`: Convey640 pull script for wells, completions and spacing/pooling orders, loaded through `save_abstract_wells` (with quarter-call locations) and `save_abstract_custom_records`
- **0.3.0** — connects the `annolab` MCP server; skills rewritten to route to its tools and prompts, SDK retained for uploads only; `get_abstract_upload_status` replaces SDK status checks; minimum SDK 0.7.2
- **0.2.2** — removes pre-upload document classification; AnnoLab classifies, extracts and interprets after upload
- **0.2.1** — drops expected instrument counts from intake and readiness; instrument counts are the platform's determination
- **0.2.0** — adds `abstract-intake` and `abstract-status`; SDK skill updated to 0.7.1
- **0.1.0** — `annolab` and `legal-descriptions`, built against SDK 0.6.0
