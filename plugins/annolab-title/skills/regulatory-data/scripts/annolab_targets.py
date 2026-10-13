"""Target shapes and shared helpers for regulatory-data provider scripts.

Every provider script emits the structures defined here so the MCP push step is identical
regardless of provider. See ../references/annolab-targets.md for the documented shapes.

Standard library only.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

ACTIVE = "active"
INACTIVE = "inactive"
UNKNOWN = "unknown"

CLASSIFICATION_COMPLETION = "Completion Report"
CLASSIFICATION_SPACING = "Spacing Order"
CLASSIFICATION_POOLING = "Pooling Order"

CATEGORY_COMPLETIONS = "completions"
CATEGORY_REGULATORY = "regulatory"

# Values providers use to mean "no value".
DATE_SENTINELS = {"", "1900-01-01", "1901-01-01", "1900-01-01 00:00:00", "1901-01-01 00:00:00", "0000-00-00"}

# Status codes that mean the well is no longer capable of producing.
PLUGGED_STATUS_CODES = {"PA", "P&A", "PLUGGED", "PLUGGED AND ABANDONED", "ABANDONED", "ABD", "P A"}


@dataclass
class WellLocation:
    section: str
    township: str
    range: str
    quarterCall: str | None
    state: str


@dataclass
class SaveWell:
    """One item for `save_abstract_wells`."""

    apiNumber: str | None
    wellName: str | None
    wellNumber: str | None
    operator: str | None
    wellStatus: str
    spudDate: str | None
    completionDate: str | None
    location: WellLocation
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecordDocument:
    """A PDF downloaded for a record, to be attached with begin/complete_custom_record_upload.

    `file` is relative to the `--out` directory. `endpoint` and `document_id` identify the
    provider document endpoint the file came from (e.g. `occ_orders/document`, id `ecf_17835473`).
    """

    file: str
    endpoint: str
    document_id: str
    bytes: int
    sha256: str


@dataclass
class CustomRecord:
    """One item for `save_abstract_custom_records`.

    `document` is not part of the MCP payload: when present, the push step uploads the file with
    `begin_custom_record_upload` → PUT → `complete_custom_record_upload` (which creates the record)
    instead of `save_abstract_custom_records`.
    """

    category: str
    documentClassification: str
    fields: dict[str, Any] = field(default_factory=dict)
    document: RecordDocument | None = None


@dataclass
class Summary:
    provider: str
    strs: list[str]
    datasets: list[str]
    counts: dict[str, int] = field(default_factory=dict)
    wells_by_status: dict[str, int] = field(default_factory=dict)
    # YYYY-MM (or "none") -> wells, for proposing activity decisions in bulk.
    wells_by_last_report_month: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    unknown_activity_wells: list[dict[str, Any]] = field(default_factory=list)
    wells_without_quarter_call: list[str] = field(default_factory=list)
    orders_by_classification: dict[str, int] = field(default_factory=dict)
    # Order documents: how many were downloaded, how many orders have none, and why downloads failed.
    documents: dict[str, int] = field(default_factory=dict)
    document_failures: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    quota_remaining: int | None = None
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------------------------
# Cleaning helpers


def clean_text(value: Any) -> str | None:
    """Strips whitespace and turns empty strings into None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_date(value: Any) -> str | None:
    """Returns YYYY-MM-DD or None. Handles sentinel dates and datetime strings."""
    text = clean_text(value)
    if text is None or text in DATE_SENTINELS:
        return None
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    year, month, day = match.groups()
    if year in {"1900", "1901", "0000"} and month == "01" and day == "01":
        return None
    return f"{year}-{month}-{day}"


def clean_number(value: Any) -> int | float | None:
    """Parses numeric strings (with commas) into numbers; anything else becomes None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = clean_text(value)
    if text is None:
        return None
    text = text.replace(",", "")
    try:
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        return None


def normalize_api_number(digits: str | None, state_code: str = "35") -> str | None:
    """Builds a dashed 10-digit API number (SS-CCC-NNNNN) from the provider's digits.

    Accepts an 8-digit county+sequence index (Convey640 `api_index`), a 10-digit API, or a
    12/14-digit API with sidetrack/event suffixes (truncated to the well).
    """
    if not digits:
        return None
    only = re.sub(r"\D", "", str(digits))
    if len(only) == 8:
        only = f"{state_code}{only}"
    if len(only) > 10:
        only = only[:10]
    if len(only) != 10:
        return None
    return f"{only[0:2]}-{only[2:5]}-{only[5:10]}"


def normalize_str(value: str) -> str:
    """Normalizes a section-township-range string to `16-11N-12W`."""
    text = re.sub(r"\s+", "", value.upper())
    match = re.fullmatch(r"0*(\d+)-?T?0*(\d+)([NS])-?R?0*(\d+)([EW])", text)
    if not match:
        raise ValueError(f'"{value}" is not a section-township-range like 16-11N-12W')
    sec, twn, twn_dir, rng, rng_dir = match.groups()
    return f"{sec}-{twn}{twn_dir}-{rng}{rng_dir}"


def split_str(value: str) -> tuple[str, str, str]:
    sec, twn, rng = normalize_str(value).split("-")
    return sec, twn, rng


def join_quarter_calls(parts_smallest_first: Iterable[Any]) -> str | None:
    """Joins quarter-call parts, given smallest first, into the written form ("C SE4 SW4").

    The AnnoLab `quarterCall` convention is the way a call is written: smallest first, so
    "C SE4 SW4" is the center of the SE/4 of the SW/4. Callers must order the parts that way
    before calling; see `join_quarter_calls_largest_first` for providers that enumerate the
    other way round. Empties are dropped.
    """
    tokens = [clean_text(part) for part in parts_smallest_first]
    tokens = [token.upper() for token in tokens if token]
    return " ".join(tokens) if tokens else None


def join_quarter_calls_largest_first(parts_largest_first: Iterable[Any]) -> str | None:
    """Joins parts enumerated largest first (Convey640 `Qtr1`..`Qtr4`) into the written form.

    Convey640 numbers calls from the largest subdivision down: for "C SE4 SW4", Qtr1 = SW4,
    Qtr2 = SE4, Qtr3 = C. The written call is therefore the enumeration reversed.
    """
    return join_quarter_calls(reversed(list(parts_largest_first)))


# ----------------------------------------------------------------------------------------------
# Activity rule (owned by SKILL.md; implemented once here)


ACTIVE_WITHIN_MONTHS = 12


def derive_well_status(
    status_code: str | None,
    last_report_date: str | None,
    today: date | None = None,
) -> tuple[str, str]:
    """Returns (default wellStatus, reason) per the skill's activity rule.

    Plugged/abandoned -> inactive; production reported within the last 12 months -> active;
    otherwise unknown. The user confirms these defaults (see leasehold-analysis).
    """
    code = (status_code or "").strip().upper()
    if code in PLUGGED_STATUS_CODES or "PLUG" in code or "ABANDON" in code:
        return INACTIVE, f"status code {code or '(none)'} indicates plugged/abandoned"
    if last_report_date:
        reported = _parse_date(last_report_date)
        today = today or date.today()
        if reported and reported >= _months_before(today, ACTIVE_WITHIN_MONTHS):
            return ACTIVE, f"production reported {last_report_date}, within the last {ACTIVE_WITHIN_MONTHS} months"
        return UNKNOWN, f"last production report {last_report_date} is older than {ACTIVE_WITHIN_MONTHS} months"
    return UNKNOWN, f"status code {code or '(none)'} and no production report date"


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _months_before(anchor: date, months: int) -> date:
    month_index = anchor.year * 12 + (anchor.month - 1) - months
    year, month = divmod(month_index, 12)
    return date(year, month + 1, min(anchor.day, 28))


def last_report_month(last_report_date: str | None) -> str:
    """YYYY-MM bucket for grouping wells in the summary; 'none' when no report."""
    reported = _parse_date(last_report_date) if last_report_date else None
    return reported.strftime("%Y-%m") if reported else "none"


def classify_order(relief: Iterable[str]) -> str | None:
    """Maps an order's relief list to a classification, or None if out of scope."""
    upper = {item.strip().upper() for item in relief if item and item.strip()}
    if any("POOL" in item for item in upper):
        return CLASSIFICATION_POOLING
    if any("SPACING" in item for item in upper):
        return CLASSIFICATION_SPACING
    return None


# ----------------------------------------------------------------------------------------------
# Output


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=_to_jsonable)
        handle.write("\n")


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_outputs(
    out_dir: Path,
    wells: list[SaveWell] | None,
    completions: list[CustomRecord] | None,
    orders: list[CustomRecord] | None,
    summary: Summary,
) -> None:
    """Writes the four target files. Datasets passed as None are not written."""
    if wells is not None:
        write_json(out_dir / "wells.json", {"abstractId": None, "wells": [asdict(well) for well in wells]})
    if completions is not None:
        write_json(out_dir / "completions.json", {"abstractId": None, "items": [asdict(item) for item in completions]})
    if orders is not None:
        write_json(out_dir / "orders.json", {"abstractId": None, "items": [asdict(item) for item in orders]})
    write_json(out_dir / "summary.json", asdict(summary))
