#!/usr/bin/env python3
"""Pull wells, completions and spacing/pooling orders from Convey640 for one or more sections.

Usage:
    export CONVEY640_API_KEY="<user_id>::<token>"      # from https://app.convey640.com/sandbox.php
    python3 convey640_pull.py --str 16-11N-12W [--str 17-11N-12W ...] \
        [--datasets wells,completions,orders] --out /tmp/regdata/my-abstract

Writes wells.json, completions.json, orders.json and summary.json into --out, in the shapes
described in ../references/annolab-targets.md, ready for save_abstract_wells and
save_abstract_custom_records. When orders are pulled, their PDFs are fetched from the provider's
document endpoint into --out/documents/ so each order record can be pushed with its document
attached. Each new download spends one credit of a small monthly document allowance, so downloads
are capped per run (--max-documents, default 25; --no-documents for none) and files already on
disk are reused. Read-only against the provider. Standard library only.

The API key is read from the environment and never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from annolab_targets import (  # noqa: E402
    CATEGORY_COMPLETIONS,
    CATEGORY_REGULATORY,
    CLASSIFICATION_COMPLETION,
    UNKNOWN,
    CustomRecord,
    RecordDocument,
    SaveWell,
    Summary,
    WellLocation,
    classify_order,
    clean_date,
    clean_number,
    clean_text,
    derive_well_status,
    join_quarter_calls_largest_first,
    last_report_month,
    normalize_api_number,
    normalize_str,
    split_str,
    write_outputs,
)

PROVIDER = "convey640"
BASE_URL = "https://convey640.tech/api"
KEY_ENV = "CONVEY640_API_KEY"
KEY_URL = "https://app.convey640.com/sandbox.php"
PER_PAGE = 100
PACE_SECONDS = 1.0
MAX_RETRIES = 5
ALL_DATASETS = ("wells", "completions", "orders")
STATE = "OK"
API_STATE_CODE = "35"

# Order PDFs come from the provider's document endpoint, keyed by the order row's `_id`. Each
# successful download spends one credit of a small monthly document allowance (500 at the time of
# writing), so downloads are capped per run and never repeated for a file already on disk.
DOCUMENT_ENDPOINT = "occ_orders/document"
DOCUMENTS_DIR = "documents"
DOCUMENT_TIMEOUT = 180
DEFAULT_MAX_DOCUMENTS = 25
CREDITS_EXCEEDED_CODE = "download_pdf_count_exceeded"


class Convey640Error(Exception):
    pass


class DocumentUnavailable(Exception):
    """The provider has no PDF for this id (JSON 404). Not retried, spends no credit."""


class DocumentCreditsExceeded(Exception):
    """The monthly document allowance is used up (JSON 403). Stop downloading for this run."""


class Convey640Client:
    """Minimal paged client with pacing and 429 backoff."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self.requests = 0
        self.quota_remaining: int | None = None
        self._last_request_at = 0.0

    def fetch_all(self, table: str, **filters: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page = 1
        while True:
            body = self._get(table, page=page, per_page=PER_PAGE, **filters)
            records.extend(body.get("records") or [])
            self.quota_remaining = body.get("remaining", self.quota_remaining)
            pages = int(body.get("pages") or 1)
            if page >= pages:
                return records
            page += 1

    def _get(self, table: str, **params: Any) -> dict[str, Any]:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        url = f"{BASE_URL}/{table}?{query}"
        backoff = 2.0
        for attempt in range(1, MAX_RETRIES + 1):
            self._pace()
            request = urllib.request.Request(url, headers={"X-API-Key": self._api_key, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    self.requests += 1
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                self.requests += 1
                detail = _read_error_body(error)
                if error.code == 429 and attempt < MAX_RETRIES:
                    retry_after = error.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                    time.sleep(wait)
                    backoff = min(backoff * 2, 60.0)
                    continue
                if error.code in (401, 403):
                    raise Convey640Error(
                        f"Convey640 rejected the API key ({error.code}). Check {KEY_ENV}; keys look like "
                        f"<user_id>::<token> and come from {KEY_URL}."
                    ) from None
                if error.code == 429:
                    raise Convey640Error("Convey640 rate limit (60 requests/minute) still exceeded after retries; wait a minute and re-run.") from None
                raise Convey640Error(f"Convey640 {table} request failed with HTTP {error.code}: {detail}") from None
            except urllib.error.URLError as error:
                if attempt < MAX_RETRIES:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                    continue
                raise Convey640Error(f"Could not reach Convey640: {error.reason}") from None
        raise Convey640Error(f"Convey640 {table} request failed after {MAX_RETRIES} attempts.")

    def fetch_document(self, endpoint: str, document_id: str) -> bytes:
        """GET /<table>/document?id=... Returns the PDF bytes. Raises DocumentUnavailable (404),
        DocumentCreditsExceeded (403 with the credits error code) or Convey640Error."""
        url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode({'id': document_id})}"
        backoff = 2.0
        for attempt in range(1, MAX_RETRIES + 1):
            self._pace()
            request = urllib.request.Request(url, headers={"X-API-Key": self._api_key, "Accept": "application/pdf, application/json"})
            try:
                with urllib.request.urlopen(request, timeout=DOCUMENT_TIMEOUT) as response:
                    self.requests += 1
                    data = response.read()
                    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            except urllib.error.HTTPError as error:
                self.requests += 1
                detail = _read_error_body(error)
                if error.code == 404:
                    raise DocumentUnavailable(detail or "Document not found") from None
                if error.code == 403 and CREDITS_EXCEEDED_CODE in detail:
                    raise DocumentCreditsExceeded(detail) from None
                if error.code in (401, 403):
                    raise Convey640Error(f"Convey640 rejected the API key for document downloads ({error.code}): {detail}") from None
                if error.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                    retry_after = error.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                    time.sleep(wait)
                    backoff = min(backoff * 2, 60.0)
                    continue
                raise Convey640Error(f"Convey640 document request failed with HTTP {error.code}: {detail}") from None
            except urllib.error.URLError as error:
                if attempt < MAX_RETRIES:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                    continue
                raise Convey640Error(f"Could not reach Convey640: {error.reason}") from None

            if data.startswith(b"%PDF"):
                return data
            # Some errors may arrive as 200 + JSON; treat them as unavailable rather than saving junk.
            raise DocumentUnavailable(f"response is not a PDF ({content_type or 'unknown content type'}, {len(data)} bytes)")
        raise Convey640Error(f"Convey640 document request failed after {MAX_RETRIES} attempts.")

    def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < PACE_SECONDS:
            time.sleep(PACE_SECONDS - elapsed)
        self._last_request_at = time.monotonic()


def _read_error_body(error: urllib.error.HTTPError) -> str:
    try:
        text = error.read().decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001
        return ""
    try:
        parsed = json.loads(text)
        return str(parsed.get("error") or parsed.get("message") or text)[:300]
    except ValueError:
        return text[:300]


# ----------------------------------------------------------------------------------------------
# Mapping


def quarter_call_from_row(row: dict[str, Any]) -> str | None:
    """Convey640 enumerates Qtr1 as the largest call ("C SE4 SW4" -> Qtr1 SW4, Qtr2 SE4, Qtr3 C),
    so the written, smallest-first call is Qtr4 Qtr3 Qtr2 Qtr1."""
    return join_quarter_calls_largest_first([row.get("Qtr1"), row.get("Qtr2"), row.get("Qtr3"), row.get("Qtr4")])


def build_well(row: dict[str, Any], str_value: str) -> SaveWell:
    api_number = normalize_api_number(row.get("api_index"), API_STATE_CODE)
    status_code = clean_text(row.get("Well_Status"))
    last_report = clean_date(row.get("last_report_date"))
    well_status, reason = derive_well_status(status_code, last_report)
    quarter_call = quarter_call_from_row(row)

    sec = clean_text(row.get("Sec2"))
    twp = clean_text(row.get("Twp"))
    rng = clean_text(row.get("Rng"))
    if not (sec and twp and rng):
        sec, twp, rng = split_str(str_value)

    footage_ns = _footage(row.get("Footage_NS"), row.get("NS"))
    footage_ew = _footage(row.get("Footage_EW"), row.get("EW"))

    return SaveWell(
        apiNumber=api_number,
        wellName=clean_text(row.get("Well_Name")),
        wellNumber=clean_text(row.get("Well_Number")),
        operator=clean_text(row.get("Operator_Name")),
        wellStatus=well_status,
        spudDate=clean_date(row.get("Spud")),
        completionDate=clean_date(row.get("Well_Completion")),
        location=WellLocation(section=sec, township=twp.upper(), range=rng.upper(), quarterCall=quarter_call, state=STATE),
        properties={
            "source": PROVIDER,
            "source_key": source_key("completions", row.get("api_index")),
            "status_code": status_code,
            "status_reason": reason,
            "last_report_date": last_report,
            "first_prod_date": clean_date(row.get("First_Prod")),
            "footage_ns": footage_ns,
            "footage_ew": footage_ew,
            "county": clean_text(row.get("county_str")),
            "formation": clean_text(row.get("Formation_Name")),
            "well_type": clean_text(row.get("well_type_index")),
            "operator_number": clean_text(row.get("Operator")),
            "str": str_value,
        },
    )


def build_completion_record(row: dict[str, Any], str_value: str) -> CustomRecord:
    return CustomRecord(
        category=CATEGORY_COMPLETIONS,
        documentClassification=CLASSIFICATION_COMPLETION,
        fields={
            "source": PROVIDER,
            "source_key": source_key("completions", row.get("api_index")),
            "api_number": normalize_api_number(row.get("api_index"), API_STATE_CODE),
            "well_name": clean_text(row.get("Well_Name")),
            "well_number": clean_text(row.get("Well_Number")),
            "operator": clean_text(row.get("Operator_Name")),
            "well_status": clean_text(row.get("Well_Status")),
            "well_type": clean_text(row.get("well_type_index")),
            "str": str_value,
            "quarter_call": quarter_call_from_row(row),
            "spud_date": clean_date(row.get("Spud")),
            "completion_date": clean_date(row.get("Well_Completion")),
            "first_prod_date": clean_date(row.get("First_Prod")),
            "test_date": clean_date(row.get("Test_Date")),
            "last_report_date": clean_date(row.get("last_report_date")),
            "formation": clean_text(row.get("Formation_Name")),
            "total_depth": clean_number(row.get("Total_Depth")),
            "oil_bbl_per_day": clean_number(row.get("OilBBL_PerDay")),
            "gas_mcf_per_day": clean_number(row.get("GasMCF_PerDay")),
            "water_bbl_per_day": clean_number(row.get("WaterBBL_PerDay")),
            "cum_oil_bbl": clean_number(row.get("sum_total_oil")),
            "cum_gas_mcf": clean_number(row.get("sum_total_gas")),
            "months_produced": clean_number(row.get("months_prod")),
        },
    )


def build_order_record(
    row: dict[str, Any],
    provider_links: dict[str, str],
    document: RecordDocument | None,
) -> CustomRecord | None:
    """One record per order row. Returns None for orders outside spacing/pooling."""
    relief = [part for part in (clean_text(row.get("relief")) or "").split("|") if part]
    classification = classify_order(relief)
    if classification is None:
        return None
    order_no = clean_text(row.get("order_no"))
    document_id = clean_text(row.get("_id"))
    return CustomRecord(
        category=CATEGORY_REGULATORY,
        documentClassification=classification,
        fields={
            "source": PROVIDER,
            "source_key": source_key("occ_orders", order_no),
            "order_no": order_no,
            "case_no": clean_text(row.get("case_no")),
            "order_date": clean_date(row.get("_date")),
            "applicant": clean_text(row.get("applicant")),
            "relief": relief,
            "relief_type": clean_text(row.get("relief_type")),
            "county": clean_text(row.get("county")),
            "str": clean_text(row.get("str")),
            "legal": clean_text(row.get("legal")),
            "document_title": clean_text(row.get("document_title")),
            "document_id": document_id,
            "provider_link": provider_links.get(document_id or ""),
        },
        document=document,
    )


def index_provider_links(rows: list[dict[str, Any]]) -> dict[str, str]:
    """occ_data ORDER rows share `_id` with their occ_orders row; keep the published link
    (OCC imaging or WebLink viewer page) as a human-facing reference only."""
    links: dict[str, str] = {}
    for row in rows:
        if (clean_text(row.get("docket_code")) or "").upper() != "ORDER":
            continue
        document_id = clean_text(row.get("_id"))
        link = clean_text(row.get("pdf"))
        if document_id and link and document_id not in links:
            links[document_id] = link
    return links


# ----------------------------------------------------------------------------------------------
# Documents


class DocumentDownloader:
    """Downloads order PDFs through the provider's document endpoint into <out>/documents.

    Budget rules: at most `max_documents` new downloads per run; a file already on disk is reused
    without a request; the first credits-exceeded response stops all further downloads; an
    unavailable document is recorded and never retried. Failures never abort the pull.
    """

    def __init__(self, client: Convey640Client, out_dir: Path, max_documents: int) -> None:
        self.client = client
        self.out_dir = out_dir
        self.documents_dir = out_dir / DOCUMENTS_DIR
        self.max_documents = max_documents
        self.downloaded = 0
        self.reused = 0
        self.skipped_over_cap = 0
        self.credits_exceeded: str | None = None
        self.failures: list[dict[str, Any]] = []
        self._by_id: dict[str, RecordDocument | None] = {}

    def fetch(self, document_id: str, order_no: str | None) -> RecordDocument | None:
        if document_id in self._by_id:
            return self._by_id[document_id]
        document = self._fetch(document_id, order_no)
        self._by_id[document_id] = document
        return document

    def _fetch(self, document_id: str, order_no: str | None) -> RecordDocument | None:
        path = self.documents_dir / _document_file_name(document_id, order_no)
        existing = _load_existing(path)
        if existing is not None:
            self.reused += 1
            return self._record(path, existing, document_id)

        if self.credits_exceeded is not None:
            self.skipped_over_cap += 1
            return None
        if self.downloaded >= self.max_documents:
            self.skipped_over_cap += 1
            return None

        try:
            data = self.client.fetch_document(DOCUMENT_ENDPOINT, document_id)
        except DocumentUnavailable as error:
            self.failures.append({"order_no": order_no, "document_id": document_id, "reason": str(error)})
            return None
        except DocumentCreditsExceeded as error:
            self.credits_exceeded = str(error)
            self.skipped_over_cap += 1
            return None
        except Convey640Error as error:
            self.failures.append({"order_no": order_no, "document_id": document_id, "reason": str(error)})
            return None

        self.documents_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.downloaded += 1
        return self._record(path, data, document_id)

    def _record(self, path: Path, data: bytes, document_id: str) -> RecordDocument:
        return RecordDocument(
            file=str(path.relative_to(self.out_dir)),
            endpoint=DOCUMENT_ENDPOINT,
            document_id=document_id,
            bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )


def _load_existing(path: Path) -> bytes | None:
    """A PDF already downloaded by an earlier run; anything else on disk is ignored."""
    if not path.is_file():
        return None
    data = path.read_bytes()
    return data if data.startswith(b"%PDF") else None


def _document_file_name(document_id: str, order_no: str | None) -> str:
    """`order-<order_no>-<_id>.pdf`, safe for the filesystem and readable in AnnoLab."""
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", document_id) or "document"
    safe_order = re.sub(r"[^0-9A-Za-z]", "", order_no or "") or "unknown"
    return f"order-{safe_order}-{safe_id}.pdf"


def source_key(table: str, identifier: Any) -> str:
    return f"{PROVIDER}:{table}:{clean_text(identifier) or 'unknown'}"


def _footage(distance: Any, direction: Any) -> str | None:
    dist = clean_text(distance)
    direction_text = clean_text(direction)
    if not dist:
        return None
    return f"{dist} {direction_text}".strip() if direction_text else dist


# ----------------------------------------------------------------------------------------------
# Main


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--str", dest="strs", action="append", required=True, metavar="S-TTD-RRD", help="Section-township-range, e.g. 16-11N-12W. Repeatable.")
    parser.add_argument("--datasets", default=",".join(ALL_DATASETS), help=f"Comma-separated subset of {','.join(ALL_DATASETS)}. Default: all.")
    parser.add_argument("--out", required=True, type=Path, help="Directory to write wells.json, completions.json, orders.json, summary.json (and documents/).")
    parser.add_argument("--no-documents", action="store_true", help="Do not download order PDFs (no document credits spent). orders.json still carries document_id so a later run can fetch them.")
    parser.add_argument("--max-documents", type=int, default=DEFAULT_MAX_DOCUMENTS, metavar="N", help=f"Cap on NEW PDF downloads this run (each spends one monthly document credit). Default {DEFAULT_MAX_DOCUMENTS}. Files already in --out/documents are reused for free.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    datasets = [part.strip().lower() for part in args.datasets.split(",") if part.strip()]
    bad = [part for part in datasets if part not in ALL_DATASETS]
    if bad or not datasets:
        print(f"--datasets must be a comma-separated subset of {', '.join(ALL_DATASETS)}; got {args.datasets!r}", file=sys.stderr)
        return 2

    try:
        strs = sorted({normalize_str(value) for value in args.strs})
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    api_key = os.environ.get(KEY_ENV, "").strip()
    if not api_key:
        print(
            f"{KEY_ENV} is not set.\n"
            f"Get a key at {KEY_URL} (it looks like <user_id>::<token>), then run:\n"
            f'  export {KEY_ENV}="<user_id>::<token>"\n'
            "and re-run this command. Nothing was fetched.",
            file=sys.stderr,
        )
        return 3
    if "::" not in api_key:
        print(f"{KEY_ENV} does not look like a Convey640 key (expected <user_id>::<token>). Nothing was fetched.", file=sys.stderr)
        return 3

    client = Convey640Client(api_key)
    summary = Summary(provider=PROVIDER, strs=strs, datasets=datasets)

    wells: list[SaveWell] | None = [] if "wells" in datasets else None
    completions: list[CustomRecord] | None = [] if "completions" in datasets else None
    orders: list[CustomRecord] | None = [] if "orders" in datasets else None

    try:
        if wells is not None or completions is not None:
            seen_wells: set[str] = set()
            for str_value in strs:
                rows = client.fetch_all("completions", str=str_value)
                if not rows:
                    summary.warnings.append(f"No completions found for {str_value}.")
                for row in rows:
                    if completions is not None:
                        completions.append(build_completion_record(row, str_value))
                    if wells is not None:
                        well = build_well(row, str_value)
                        dedupe_key = well.apiNumber or well.properties["source_key"]
                        if dedupe_key in seen_wells:
                            continue
                        seen_wells.add(dedupe_key)
                        wells.append(well)

        if orders is not None:
            if args.max_documents < 0:
                print("--max-documents must be 0 or more.", file=sys.stderr)
                return 2
            downloader = None if args.no_documents else DocumentDownloader(client, args.out, args.max_documents)
            seen_orders: set[str] = set()
            document_ids: set[str] = set()
            for str_value in strs:
                order_rows = client.fetch_all("occ_orders", str=str_value)
                in_scope = [row for row in order_rows if classify_order((clean_text(row.get("relief")) or "").split("|")) is not None]
                if not in_scope:
                    summary.warnings.append(f"No spacing or pooling orders found for {str_value} ({len(order_rows)} orders of other kinds).")
                    continue
                link_rows = client.fetch_all("occ_data", str=str_value, docket_code="ORDER")
                provider_links = index_provider_links(link_rows)

                for row in in_scope:
                    order_no = clean_text(row.get("order_no")) or ""
                    document_id = clean_text(row.get("_id"))
                    dedupe_key = order_no or document_id or ""
                    if dedupe_key in seen_orders:
                        continue  # the same order covering several of the requested sections
                    seen_orders.add(dedupe_key)
                    if document_id:
                        document_ids.add(document_id)
                    document = downloader.fetch(document_id, order_no) if downloader is not None and document_id else None
                    record = build_order_record(row, provider_links, document)
                    if record is not None:
                        orders.append(record)

            with_document = sum(1 for record in orders if record.document)
            summary.documents = {
                "with_document_id": len(document_ids),
                "attached": with_document,
                "downloaded": downloader.downloaded if downloader else 0,
                "reused": downloader.reused if downloader else 0,
                "not_downloaded": len(document_ids) - with_document,
                "unavailable": len(downloader.failures) if downloader else 0,
                "max_documents": None if downloader is None else args.max_documents,
                "credits_exceeded": bool(downloader and downloader.credits_exceeded),
            }
            if downloader is None:
                if document_ids:
                    summary.warnings.append(
                        f"{len(document_ids)} order document(s) are available but were not downloaded (--no-documents). "
                        f"Re-run without --no-documents to fetch them; each spends one monthly document credit."
                    )
            else:
                summary.document_failures = downloader.failures
                if downloader.credits_exceeded:
                    summary.warnings.append(
                        f"Convey640 monthly document credits are exhausted ({downloader.credits_exceeded}). "
                        f"{downloader.skipped_over_cap} document(s) were not downloaded; their records are still written."
                    )
                elif downloader.skipped_over_cap:
                    summary.warnings.append(
                        f"{downloader.skipped_over_cap} order document(s) were not downloaded because --max-documents {args.max_documents} was reached. "
                        "Re-run with a higher cap to fetch the rest (files already downloaded are reused, not re-charged)."
                    )
                if downloader.failures:
                    summary.warnings.append(
                        f"{len(downloader.failures)} order document(s) are not available from the provider; see document_failures. "
                        "Their records are still written (without a document) so they can be saved."
                    )
    except Convey640Error as error:
        print(str(error), file=sys.stderr)
        return 1

    if wells is not None:
        summary.counts["wells"] = len(wells)
        for well in wells:
            summary.wells_by_status[well.wellStatus] = summary.wells_by_status.get(well.wellStatus, 0) + 1
            month = last_report_month(well.properties.get("last_report_date"))
            summary.wells_by_last_report_month.setdefault(month, []).append({
                "apiNumber": well.apiNumber,
                "wellName": well.wellName,
                "wellNumber": well.wellNumber,
                "defaultStatus": well.wellStatus,
                "statusCode": well.properties.get("status_code"),
            })
            if well.wellStatus == UNKNOWN:
                summary.unknown_activity_wells.append({
                    "apiNumber": well.apiNumber,
                    "wellName": well.wellName,
                    "wellNumber": well.wellNumber,
                    "reason": well.properties.get("status_reason"),
                })
            if not well.location.quarterCall:
                summary.wells_without_quarter_call.append(well.apiNumber or well.properties["source_key"])
            if not well.apiNumber:
                summary.warnings.append(f"Well {well.wellName!r} has no usable API number; it will not dedupe on re-run.")
    if completions is not None:
        summary.counts["completions"] = len(completions)
    if orders is not None:
        summary.counts["orders"] = len(orders)
        for record in orders:
            summary.orders_by_classification[record.documentClassification] = summary.orders_by_classification.get(record.documentClassification, 0) + 1

    summary.requests = client.requests
    summary.quota_remaining = client.quota_remaining
    if isinstance(client.quota_remaining, int) and client.quota_remaining < 1000:
        summary.warnings.append(f"Convey640 quota is low: {client.quota_remaining} records remaining.")

    write_outputs(args.out, wells, completions, orders, summary)

    print(f"Wrote {args.out}/summary.json")
    for name, count in summary.counts.items():
        print(f"  {name}: {count}")
    if summary.documents:
        docs = summary.documents
        print(
            f"  order documents: {docs["with_document_id"]} with a document id, {docs['attached']} attached "
            f"({docs['downloaded']} downloaded now, {docs['reused']} reused from {args.out / DOCUMENTS_DIR}), "
            f"{docs['unavailable']} unavailable"
        )
    if summary.unknown_activity_wells:
        print(f"  wells with unknown activity: {len(summary.unknown_activity_wells)}")
    for warning in summary.warnings:
        print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
