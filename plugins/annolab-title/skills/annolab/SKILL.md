---
name: annolab
description: "Work with AnnoLab projects, land abstracts, documents and county records. Routes work to the annolab MCP server tools, with the annolab Python SDK used only for document uploads. Use whenever a task involves AnnoLab data, an AnnoLab API key, land abstracts, or title instruments."
---

# AnnoLab

AnnoLab is an AI-first title production platform. `Project` → `LandAbstract` → sources (documents) and instruments.

Two ways in, with a fixed split:

| Need | Use |
|---|---|
| Find projects and abstracts, create an abstract, check readiness, search or add county records | **`annolab` MCP tools** — `list_projects`, `find_abstracts`, `create_abstract`, `get_abstract_upload_status`, `search_county_records`, `get_county_records_search`, `add_county_records_to_abstract`, `get_add_records_status` |
| Add wells, map features or custom records to an abstract | **`annolab` MCP tools** — `list_abstract_wells`, `save_abstract_wells`, `list_abstract_custom_records`, `save_abstract_custom_records` |
| Review a document's contents (summarise, extract fields, compare instruments, answer a question) without reading it yourself | **`annolab` MCP tool** — `prompt_documents`: pass your prompt plus documents by `subDocumentId` (an instrument) or `sourceReferenceId` + `startPage`/`endPage`; optional `responseJsonSchema` for structured output. Server-side vision model; up to 10 documents and 50 total pages per call, so split larger reviews |
| Pull wells, completions, spacing/pooling orders from an external provider (Convey640) into an abstract | **regulatory-data** skill — provider script to JSON, then the MCP tools above |
| Gather leasing instruments, wells and regulatory data for a leasehold analysis | **leasehold-analysis** skill — county records flow + `regulatory-data`, then the well-activity decision |
| Upload a document to an abstract | **Python SDK** — `LandAbstract.upload_file` |

The MCP server carries its own instructions, tool descriptions and workflow prompts (`abstract_intake`, `build_abstract_from_county_records`). Follow them; do not re-derive the workflow here. If the `annolab` MCP server is not connected, stop and tell the user to set `ANNOLAB_API_KEY` and reload the plugin rather than reimplementing tool behaviour with the SDK.

## Setup

Both surfaces use the same API key.

```bash
export ANNOLAB_API_KEY="..."
pip install 'annolab>=0.7.2' -q   # add --break-system-packages on a system Python
```

The plugin's `.mcp.json` sends the key to `https://api.annolab.ai/mcp`. The SDK reads it from `ANNOLAB_API_KEY` (or `api_key=` / `annolab.api_key`). If no key resolves, stop and ask for one. Never hardcode, print, or echo the key.

## Uploading documents (SDK)

The MCP tools return the exact `name` of the project and abstract. Use those names to reach the `LandAbstract`, then upload:

```python
from annolab import AnnoLab

lab = AnnoLab()                                   # api_url="https://api.annolab.ai" is the default
abstract = lab.find_project(project_name).find_abstract(abstract_name)

result = abstract.upload_file(file=path, ocr=True, workflow="land_title")
result.pending_source_id   # int | None  — record this
result.execution_id        # int | None  — record this
```

- `ocr=True` and `workflow="land_title"` always. Never ask the user about either.
- Use the abstract name **returned by** `create_abstract` / `find_abstracts`; `create_abstract` may have appended a ` V<n>` suffix.
- Do not call `result.wait_until_complete()` during intake. Readiness is `get_abstract_upload_status`.
- The export is `AnnoLab` (capital L). `from annolab import Annolab` raises `ImportError`.

## Other SDK entry points

Only for work the MCP tools do not cover. Signatures for reference; full docs at https://docs.annolab.ai/.

```python
lab.create_project(name, owner_name=None, is_public=False)   # find_project first — duplicates are not recoverable
proj.create_pdf_source(file, name=None, directory=None, ocr=True, workflow=None, abstractId=None)  # -> UploadResult
proj.create_pdf_source_from_web(url, name=None, directory=None)
proj.create_text_source(name, text, directory=None)
abstract.populate_instruments(timeout=120.0).instruments       # pages the full instrument set; expensive
proj.create_annotation_layer(name, is_gold=False, description=None)
proj.create_annotations(source_name, annotations, relations=[], dedup=True)
proj.export(filepath, source_ids=None, layers=None, include_sources=False, include_text_bounds=False, timeout=3600)
```

## Working discipline

AnnoLab payloads are large. When the SDK is involved, script against it: pull, aggregate, print a summary. Never page full instrument or annotation lists into the conversation; report counts, distinct values, and the specific records the task is about. Report exact figures from the data, never estimates.
