# AnnoLab targets for regulatory data

Every provider script in this skill writes the same four files into `--out`. The item shapes are exactly what the `annolab` MCP tools accept, so the push step is a pass-through. Adding a provider means a new reference plus a new script that emits these shapes; nothing downstream changes.

## `wells.json` → `save_abstract_wells`

```json
{
  "abstractId": null,
  "wells": [
    {
      "apiNumber": "35-015-20640",
      "wellName": "J H PROPPS",
      "wellNumber": "1",
      "operator": "OTC / OCC NOT ASSIGNED",
      "wellStatus": "inactive",
      "spudDate": null,
      "completionDate": "1977-03-11",
      "location": {
        "section": "16",
        "township": "11N",
        "range": "12W",
        "quarterCall": "CNW4 SE4 NW4",
        "state": "OK"
      },
      "properties": {
        "source": "convey640",
        "source_key": "convey640:completions:01520640",
        "status_code": "PA",
        "status_reason": "Well_Status PA (plugged and abandoned)",
        "last_report_date": null,
        "footage_ns": "990 S",
        "footage_ew": "1650 W",
        "county": "CADDO",
        "formation": null,
        "well_type": "OTHER",
        "str": "16-11N-12W"
      }
    }
  ]
}
```

Rules:

- `apiNumber` is the full 10-digit API with dashes (`SS-CCC-NNNNN`). The server matches existing wells on digits only, so this is the idempotency key. Supply it whenever the provider has it.
- `wellStatus` is `active` | `inactive` | `unknown`, a default derived per the rule in `SKILL.md` that the user confirms. `properties.status_code` keeps the provider's raw code and `properties.status_reason` says how the rule applied.
- `location` is used instead of `geometry`. `quarterCall` is the call as written, smallest-first (`C SE4 SW4` = center of the SE/4 of the SW/4; `CNW4 SE4 NW4` = center of the NW/4 of the SE/4 of the NW/4). Providers that enumerate calls largest-first (Convey640 `Qtr1..Qtr4`) must be reversed before emitting. `C` alone means the section center; empty or missing means the section center too. Always include `state`.
- Dates are `YYYY-MM-DD` or `null`. Provider sentinel dates (`1900-01-01`, `1901-01-01 00:00:00`, `""`) must be cleaned to `null` before emitting.
- `properties` may hold anything else useful; keep keys snake_case and values JSON-native. Always include `source` and `source_key`.
- `abstractId` is left `null` in the file; fill it in when calling the tool.

## `completions.json` → `save_abstract_custom_records` (category `completions`)

One record per completion row, linked to the well by API number.

```json
{
  "abstractId": null,
  "items": [
    {
      "category": "completions",
      "documentClassification": "Completion Report",
      "fields": {
        "source": "convey640",
        "source_key": "convey640:completions:01520640",
        "api_number": "35-015-20640",
        "well_name": "J H PROPPS",
        "well_number": "1",
        "operator": "OTC / OCC NOT ASSIGNED",
        "well_status": "PA",
        "well_type": "OTHER",
        "str": "16-11N-12W",
        "quarter_call": "CNW4 SE4 NW4",
        "spud_date": null,
        "completion_date": "1977-03-11",
        "first_prod_date": null,
        "test_date": null,
        "last_report_date": null,
        "formation": null,
        "total_depth": null,
        "oil_bbl_per_day": null,
        "gas_mcf_per_day": null,
        "water_bbl_per_day": null,
        "cum_oil_bbl": null,
        "cum_gas_mcf": null,
        "months_produced": null
      }
    }
  ]
}
```

## `orders.json` → custom records (category `regulatory`), with their PDFs

Spacing and pooling orders only. Items with a `document` are pushed with `begin_custom_record_upload` → PUT → `complete_custom_record_upload` (which creates the record and attaches the PDF); items without one go through `save_abstract_custom_records`. `document` is the script's addition for the push step and is not sent to either tool.

```json
{
  "abstractId": null,
  "items": [
    {
      "category": "regulatory",
      "documentClassification": "Spacing Order",
      "fields": {
        "source": "convey640",
        "source_key": "convey640:occ_orders:128207",
        "order_no": "128207",
        "case_no": "47552",
        "order_date": "1977-02-17",
        "applicant": "SUN OIL CO DELAWARE",
        "relief": ["SPACING"],
        "relief_type": null,
        "county": "CADDO",
        "str": "16-11N-12W",
        "legal": null,
        "document_title": null,
        "document_id": "ecf_17835473",
        "provider_link": "https://public.occ.ok.gov/WebLink/DocView.aspx?id=17835473"
      },
      "document": {
        "file": "documents/order-749515-ecf_17835473.pdf",
        "endpoint": "occ_orders/document",
        "document_id": "ecf_17835473",
        "bytes": 183422,
        "sha256": "…"
      }
    }
  ]
}
```

- `document.file` is relative to `--out`. `document` is `null` when the PDF was not downloaded: the provider has none for that id (`summary.document_failures`), the run's `--max-documents` cap or the monthly credit allowance was hit, or `--no-documents` was given. `document_id` is always present so a later run can fetch it; `provider_link` is a reference for a human and may not resolve.
- One item per order. The same order appearing in several requested sections is emitted once.

Classification conventions (exact strings, so records group by classification across providers):

| Record | `documentClassification` | `category` |
|---|---|---|
| Completion / 1002A data | `Completion Report` | `completions` |
| Order whose relief includes pooling | `Pooling Order` | `regulatory` |
| Order whose relief includes spacing (and not pooling) | `Spacing Order` | `regulatory` |

## `source_key`

`<provider>:<table>:<id>` — e.g. `convey640:completions:01520640`, `convey640:occ_orders:128207`. It lives in `fields.source_key` on records and `properties.source_key` on wells. Before saving records, call `list_abstract_custom_records`, build `{source_key → record}`, and set `recordId` on matching items so a re-run updates rather than duplicates. (`fields` is replaced wholesale on update, which is what you want here.) For items with a `document`: if the matching record already has a `sourceReferenceId`, update its fields only; if it has none, upload and `complete_custom_record_upload` with that `recordId`. Wells do not need this step; the server dedupes them on `apiNumber`.

## `summary.json`

Written by every script for the review step. Shape:

```json
{
  "provider": "convey640",
  "strs": ["16-11N-12W"],
  "datasets": ["wells", "completions", "orders"],
  "counts": { "wells": 3, "completions": 3, "orders": 9 },
  "wells_by_status": { "active": 0, "inactive": 3, "unknown": 0 },
  "wells_by_last_report_month": { "2026-07": [ { "apiNumber": "...", "wellName": "...", "wellNumber": "...", "defaultStatus": "active", "statusCode": "AC" } ], "none": [] },
  "unknown_activity_wells": [ { "apiNumber": "...", "wellName": "...", "reason": "..." } ],
  "wells_without_quarter_call": [ "35-015-21260" ],
  "orders_by_classification": { "Spacing Order": 5, "Pooling Order": 4 },
  "documents": { "with_document_id": 9, "attached": 3, "downloaded": 1, "reused": 2, "not_downloaded": 6, "unavailable": 6, "max_documents": 25, "credits_exceeded": false },
  "document_failures": [ { "order_no": "128207", "document_id": "727201", "reason": "PDF not found in archive" } ],
  "requests": 4,
  "quota_remaining": 49800,
  "warnings": []
}
```

`documents`: `with_document_id` orders have a provider document id; `attached` have a PDF on disk (`downloaded` this run — each one spent a document credit — plus `reused` from an earlier run); `unavailable` is the provider's 404s; `not_downloaded` is everything else (cap, exhausted credits, or `--no-documents`). `credits_exceeded` is true when the provider refused further downloads this run.
