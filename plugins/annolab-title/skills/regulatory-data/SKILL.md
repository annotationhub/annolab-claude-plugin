---
name: regulatory-data
description: "Bring wells, completion reports and spacing/pooling orders into an AnnoLab abstract, from an external regulatory data provider (currently Convey640) or from the user's own well lists and order documents, using the annolab MCP tools. Use when asked to add wells, completions, production status, spacing or pooling orders to an abstract, or to bring in OCC / regulatory data for a section."
---

# Regulatory data

Brings a section's regulatory record into an AnnoLab abstract: the wells drilled on it (with location and whether they are still active), their completion reports, and the spacing and pooling orders that govern it. Providers are pluggable: each has a reference and a pull script that emit the same target shapes, and the MCP push is identical regardless of where the data came from.

| Provider | Reference | Script | Covers |
|---|---|---|---|
| Convey640 (Oklahoma) | `references/convey640.md` | `scripts/convey640_pull.py` | wells, completions, OCC spacing & pooling orders |

The target shapes every script emits are in `references/annolab-targets.md`. Read that and the provider reference before running anything.

Ask the user where the data should come from before assuming a provider: a provider pull (below), their own files (see **Data the user already has**), or both.

## Procedure (provider pull)

1. **Resolve the abstract.** `list_projects` → `find_abstracts`. Record `abstractId`. Never create an abstract here; that is the **abstract-intake** skill.
2. **Build the section list.** One `S-TTD-RRD` string per section, uppercase, no leading zeros (`16-11N-12W`). Take it from the abstract's legal description (the intake record `intake/<abstract-name>.json` if it exists, or the description the user gives, parsed with the **legal-descriptions** skill). If you do not have it, ask for it in plain terms: "Which section, township and range?"
3. **Ensure the provider key.** Check the environment variable named in the provider reference. If it is unset, tell the user where to get a key (the reference has the URL and format) and how to export it, then stop until they have. Never ask the user to paste the key into chat, and never print, echo or log it.
4. **Run the pull script with `--no-documents` first**, into a scratch directory: `python3 scripts/convey640_pull.py --str 16-11N-12W --out /tmp/regdata/<abstract> --no-documents`. It writes `wells.json`, `completions.json`, `orders.json` and `summary.json` and makes no document requests. If it exits non-zero, relay its message; the common causes are a missing key, a bad section string, and the provider's rate limit.
5. **Review `summary.json` with the user** before spending anything: counts per dataset, the wells whose activity is `unknown`, any wells with no quarter call, the provider's remaining record quota, and `documents.with_document_id` — the number of order PDFs on offer. **Every order PDF downloaded spends one credit of a small monthly document allowance (500 at the time of writing, shared across all of the user's pulls).** Tell the user that number and ask whether to fetch the PDFs, all or a cap. Do not page the raw JSON into the conversation.
6. **Fetch the documents the user approved.** Re-run the same command without `--no-documents` and with `--max-documents <approved count>` (default 25). Already-downloaded files in `--out/documents/` are reused without a request, so repeating the run never double-spends; `summary.documents` shows `downloaded` (credits spent this run), `reused`, `unavailable` (the provider has no PDF for that order — common for older orders — listed in `document_failures`) and whether `credits_exceeded` stopped the run. If credits ran out, say so and carry on with the records; the user can top up and re-run later.
7. **Dedupe, then push.**
   - Wells: `save_abstract_wells` with the `wells.json` items as-is. The server matches on API number, so re-running converges rather than duplicating.
   - Records: `list_abstract_custom_records` for the abstract once and index existing records by `fields.source_key`.
     - Items **without** a `document` (all completions; orders whose PDF was unavailable or not fetched): set `recordId` where the `source_key` already exists, then `save_abstract_custom_records` in batches of up to 100.
     - Items **with** a `document` (orders): for each, `begin_custom_record_upload` (`fileName` = the file's base name) → `PUT` the file at `--out/<document.file>` to the returned URL (use the `exampleCurl`) → `complete_custom_record_upload` with the item's `category`, `documentClassification` and `fields` (pass `recordId` instead if the `source_key` already exists, which attaches the PDF to that record). This stores the PDF with no OCR or extraction. If an existing record already has a `sourceReferenceId`, skip the upload and just update its fields via `save_abstract_custom_records`.
8. **Report.** Counts created/updated per dataset; document credits spent this run and how many orders now have their PDF attached; the orders whose PDF the provider does not have (order numbers, with `provider_link` so the user can try the OCC site by hand) and any left unfetched by the cap; every well with `wellStatus: "unknown"` (name, API number, why); every well the server returned with `locationStatus: "unmappable"` (it is drawn at the section center with a question mark until someone fixes the location); and the abstract link from the tool result.

## Data the user already has

No provider is required. The target shapes in `references/annolab-targets.md` are the contract, whatever the source.

- **Well lists** (spreadsheet, CSV, a prior report): map the columns into `SaveWell` items — API number, name/number, operator, dates, status code and last production date for the activity rule, and either `location` (section/township/range + quarter call as written) or `geometry` if coordinates are given. Set `properties.source` to describe the origin and `properties.source_key` to something stable from the file (e.g. `<file>:<api>`). Review the mapping with the user on a few rows, then push with `save_abstract_wells`.
- **Order and completion PDFs** (OCC imaging downloads, scans): attach each to a custom record with `begin_custom_record_upload` → PUT the file → `complete_custom_record_upload` (category `regulatory` or `completions`, classification per the conventions in the targets reference, the key facts in `fields`). This stores the document without running extraction. If the user wants the document read and extracted instead, upload it through **abstract-intake**.
- **Documents from a URL** (OCC order links, or a `provider_link` for an order the provider could not supply): have the user download them locally, then handle as PDFs above.

## Well activity

Providers do not say whether a well is producing today, so the script derives `wellStatus` and the skill owns the rule:

| Evidence | Default `wellStatus` |
|---|---|
| Status code says plugged / abandoned (Convey640 `Well_Status` `PA`, `PLUGGED`, etc.) | `inactive` |
| Not plugged and production reported within the last 12 months | `active` |
| Not plugged and last production report older than 12 months, or none | `unknown` |

These are defaults the user confirms, not conclusions. `summary.json` groups wells by last-report month (`wells_by_last_report_month`) so you can propose decisions in bulk — "6 wells last reported production in July 2026, mark all active?" — rather than well by well; the **leasehold-analysis** skill owns that conversation. Apply the user's answers with `save_abstract_wells`. The raw status code and dates are kept in `properties` so the call can be revisited.

## Well location

Scripts emit `location: { section, township, range, quarterCall }`, never coordinates, because regulatory data carries quarter calls rather than lat/long. `quarterCall` is always the call as written, smallest-first (`C SE4 SW4` = center of the SE/4 of the SW/4); when a provider enumerates calls from the largest inward, the script reverses them (see the provider reference). `save_abstract_wells` resolves the call to a point from PLSS section geometry and reports `locationStatus`:

- `quarter_call` — resolved; the well sits at the center of its smallest call.
- `unmappable` — the call could not be read; the well sits at the section center and `locationNote` says why. Report these.

If the user has surveyed coordinates for a well, pass `geometry` instead of `location` for that well. Never send both.

## Idempotency and safety

- Wells converge on API number. Records converge on `fields.source_key` (`<provider>:<table>:<id>`), which is why step 6 lists before saving.
- `save_*` only; never call `remove_abstract_wells` or `remove_abstract_custom_records` from this skill. Removing is the user's explicit decision.
- The scripts are read-only against the provider and write only inside `--out` (including `documents/`).
- Document uploads converge too: an order whose `source_key` already has a record with a document is not uploaded again.
- Quota: the provider reference states the limits. The script paces itself and backs off on 429; if `summary.json` shows a low `remaining` count, say so.
- Document credits are the scarce resource. Never download order PDFs without the user's go-ahead on the count (steps 4–6), never raise `--max-documents` beyond what they approved, and prefer re-using an existing `--out` directory over a fresh one so files on disk are reused.

## Not yet covered

Completion report PDFs (1002A/1003 scans), applications and conveyance documents are not downloaded yet, though the provider has endpoints for them; only order documents are, and each costs a document credit. Footages are stored in well `properties` but not used to refine the point.
