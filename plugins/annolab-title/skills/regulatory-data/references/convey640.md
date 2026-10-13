# Convey640

Oklahoma regulatory data (OCC completions, orders, dockets, production, transfers) behind a simple REST API. Used here for wells, completion reports, and spacing/pooling orders.

## Key

- Get one at https://app.convey640.com/sandbox.php. It looks like `<user_id>::<token>` (two colons).
- The script reads it from `CONVEY640_API_KEY`:

  ```bash
  export CONVEY640_API_KEY="<user_id>::<token>"
  ```

- If the variable is unset the script exits with an explanation and does nothing. Never hardcode, print, echo or log the key, and never ask the user to paste it into chat; have them export it in their shell.

## API

- Base: `https://convey640.tech/api`. Header: `X-API-Key: <key>`.
- `GET /tables` lists tables; `GET /<table>/columns` lists a table's columns.
- `GET /<table>?col=value&...` filters by exact match; `|` separates multiple values (`str=16-11N-12W|17-11N-12W`).
- Paging: `page` (1-based), `per_page` (max 100). Response: `{ page, pages, per_page, total, remaining, records }`. `remaining` is the account's remaining monthly record quota.
- Limit: 60 requests/minute; over it returns 429. The script sleeps 1 s between requests and backs off on 429. Document downloads additionally spend a monthly document credit each (see **Document endpoint**).
- `completions` **must** be queried by `str`; other filters alone are rejected.

### Section string (`str`)

`S-TTD-RRD`, uppercase, no leading zeros: `16-11N-12W`. The orders tables also have `gis_str` (`16-T11N-R12W`) but `str` is the one to filter on.

## Tables used

| Table | Filter | Used for |
|---|---|---|
| `completions` | `str` | wells (one per `api_index`) and completion records |
| `occ_orders` | `str` | spacing and pooling orders (`relief` contains `SPACING` or `POOLING`) |
| `occ_data` | `str`, `docket_code=ORDER` | the published document link, joined to orders by `_id` (reference only) |
| `occ_orders/document` | `id=<_id>` | the order PDF itself (spends a document credit) |

### Quirks

- `completions` keys are mixed-case (`Well_Name`, `api_index`, `last_report_date`). Orders keys are lowercase with `_date` for the order date.
- Sentinels for "no value": `""`, `1900-01-01`, `1901-01-01 00:00:00`. The script turns all of these into `null`.
- `api_index` is county code + well sequence (`01520640`); the full Oklahoma API is `35-<county3>-<seq5>` → `35-015-20640`.
- Quarter calls are split across `Qtr1`..`Qtr4` **largest first**: `Qtr1` is the biggest subdivision and the enumeration walks inward. For the written call "C SE/4 SW/4", `Qtr1` = `SW4`, `Qtr2` = `SE4`, `Qtr3` = `C`. AnnoLab's `quarterCall` is the written, smallest-first form, so the script joins `Qtr4 Qtr3 Qtr2 Qtr1` (empties dropped). `C`-prefixed calls mean "center of" (`CNW4`). Getting this order wrong puts wells in the wrong quarter, so do not join `Qtr1..Qtr4` forward.
- `Footage_NS` / `NS` and `Footage_EW` / `EW` are the distances from the section lines (`990 S`, `1650 W`). Kept in `properties`, not used for the point yet.
- `occ_orders.relief` is pipe-joined (`HORIZONTAL|SPACING`). `occ_data.order_no` can be comma-joined (`128207,128971`) when one document covers several orders.
- `occ_data` has far more rows than orders (affidavits, exhibits, notices); only `docket_code=ORDER` rows are order documents. An `occ_data` ORDER row has the **same `_id`** as its `occ_orders` row, which is how the script joins them. `occ_data.pdf` is the link as the OCC published it (`imaging.occ.ok.gov/AP/Orders/….pdf` for older orders, `public.occ.ok.gov/WebLink/DocView.aspx?id=…` viewer pages for newer ones); many do not resolve, so the script keeps it only as `provider_link` for a human and never downloads from it.
- Every row carries `_id` (`727201` for older scans, `ecf_17835473` for OCC e-filed documents). It is the key for the document endpoint below.

## Document endpoint

`GET https://convey640.tech/api/<table>/document?id=<_id>` with the same `X-API-Key` header returns the original PDF (`application/pdf`). Tables: `occ_orders`, `occ_data`, `occ_applic`, `well_records` (id = the row's `_id`) and `conveyances` (id = `doc_number`; Oklahoma and Canadian counties only). The script uses `occ_orders/document` with the order row's `_id`.

Errors are JSON with a matching status:

| Status | Body | Meaning / script behaviour |
|---|---|---|
| 404 | `{"error":"Document not found"}`, `"Document archive not found"`, `"PDF not found in archive"` | The provider has no PDF for that id (common for pre-e-filing orders). Recorded in `summary.document_failures`; the record is still written without a document. |
| 403 | `{"error":"download_pdf_count_exceeded","message":"You have exceeded your remaining monthly document credits."}` | The monthly document allowance is used up. The script stops downloading for the rest of the run and warns. |
| 429 / 5xx | | Retried with backoff like other requests. |

**Each successful download spends one credit of a monthly document allowance (500 at the time of writing), separate from the record quota.** Failed requests do not. Treat the credits as the user's money:

- The script downloads at most `--max-documents` new PDFs per run (default 25) and reuses any `--out/documents/order-<order_no>-<_id>.pdf` already on disk without a request, so re-running never re-spends credits.
- `--no-documents` makes no document requests at all; `summary.documents.with_document_id` then tells you how many credits a full download would take, so the user can approve the spend first.
- Spent credits are not reported by the API; keep a rough running count across the month from `summary.documents.downloaded`.

With `orders` in `--datasets` and downloads enabled, each downloaded order gets a `document` on its item (`file`, `endpoint`, `document_id`, `bytes`, `sha256`).

## Field mapping

### Wells (`completions` → `SaveWell`)

| Target | Source |
|---|---|
| `apiNumber` | `35-` + `api_index[0:3]` + `-` + `api_index[3:]` |
| `wellName`, `wellNumber`, `operator` | `Well_Name`, `Well_Number`, `Operator_Name` |
| `wellStatus` | default: `Well_Status` in {`PA`, `PLUGGED`, `P&A`, `ABANDONED`} → `inactive`; else `last_report_date` within 12 months → `active`; else `unknown` (user confirms) |
| `spudDate`, `completionDate` | `Spud`, `Well_Completion` (sentinels → null) |
| `location.section/township/range` | `Sec2`, `Twp`, `Rng`; `state` = `OK` |
| `location.quarterCall` | `Qtr4 Qtr3 Qtr2 Qtr1` joined (reverse of the enumeration, so the call reads smallest-first), empties dropped |
| `properties.status_code` / `status_reason` | `Well_Status` and the rule applied |
| `properties.last_report_date`, `first_prod_date` | `last_report_date`, `First_Prod` |
| `properties.footage_ns` / `footage_ew` | `Footage_NS NS`, `Footage_EW EW` |
| `properties.county`, `formation`, `well_type`, `str` | `county_str`, `Formation_Name`, `well_type_index`, `str` |

### Completion records (`completions` → custom record, category `completions`)

Flattened subset: identity (`api_number`, `well_name`, `well_number`, `operator`), status (`well_status`, `well_type`), location (`str`, `quarter_call`), dates (`spud_date`, `completion_date`, `first_prod_date`, `test_date`, `last_report_date`), geology (`formation`, `total_depth`), initial potential (`oil_bbl_per_day`, `gas_mcf_per_day`, `water_bbl_per_day`), cumulative (`cum_oil_bbl` ← `sum_total_oil`, `cum_gas_mcf` ← `sum_total_gas`, `months_produced` ← `months_prod`). Numeric strings become numbers; sentinels become `null`.

### Orders (`occ_orders` → custom record, category `regulatory`)

| Target | Source |
|---|---|
| `documentClassification` | `Pooling Order` if `POOLING` in relief, else `Spacing Order` |
| `order_no`, `case_no`, `applicant`, `county`, `str` | same-named columns |
| `order_date` | `_date` |
| `relief` | `relief` split on `\|` |
| `relief_type`, `legal`, `document_title` | same-named, empty → null |
| `document_id` | `_id` — the key for `occ_orders/document` |
| `provider_link` | `occ_data.pdf` of the ORDER row with the same `_id`; reference only, may not resolve |
| `document` (item, not a field) | the downloaded PDF, see **Document endpoint** |

## Deliberately not pulled yet

- `well_records` (1002A / 1003 scans; `well_records/document?id=<_id>`), `occ_applic/document`, `occ_data/document` for non-order filings, and `conveyances/document?id=<doc_number>` — the endpoints exist; only order documents are pulled today, and each would spend document credits.
- `production` monthly history, `transfers`, `section_intersections`, `permits`, `occ_applic` / `occ_court_dockets`.
- Orders whose relief is only location exception, increased density, or multiunit/horizontal. They are visible in the provider but outside the spacing/pooling scope of this skill.
