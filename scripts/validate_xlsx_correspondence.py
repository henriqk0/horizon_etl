"""
Validate that full-refresh ingested advisorship data corresponds to the correct
raw .xlsx files.

Each record can appear in multiple years' .xlsx files (e.g., same CodPT in both
2024/ and 2025/ folders with different date ranges for each academic phase).
The last-processed file (highest year folder) wins for attribute values.

Validations:
  A. All ingested records must exist in the source_file they are attributed to  ✓
  B. A record's last-known dates should match the year folder of its latest source
  C. Optionally filter by date range to check specific periods
"""
import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from datetime import datetime

import pandas as pd


def load_all_xlsx_advisorships(base_dir="data/raw/sigpesq/advisorships"):
    """Read all .xlsx files organized by year. Returns dict year -> list of records."""
    xlsx_records = {}
    for year_dir in sorted(glob.glob(f"{base_dir}/*")):
        year = int(year_dir.split("/")[-1])
        xlsx_files = glob.glob(f"{year_dir}/*.xlsx")
        if not xlsx_files:
            continue

        df = pd.read_excel(xlsx_files[0])
        df = df.fillna("")

        records = []
        for _, row in df.iterrows():
            codpt = str(row.get("CodPT", "")).strip()
            codpt_match = re.search(r"\d+", codpt)
            normalized_codpt = codpt_match.group(0) if codpt_match else ""

            records.append({
                "Id": row.get("Id"),
                "CodPT": codpt,
                "CodPT_normalized": normalized_codpt,
                "Inicio_raw": row.get("Inicio", ""),
                "Fim_raw": row.get("Fim", ""),
                "Ano": row.get("Ano"),
            })
        xlsx_records[year] = records

    return xlsx_records


def load_full_refresh_tracking(path="data/exports/advisorships_tracking.json"):
    """Load advisorship tracking records from full-refresh exports."""
    with open(path) as f:
        data = json.load(f)

    sigpesq_records = []
    for rec in data:
        if rec.get("entity_type") != "advisorship":
            continue
        created_by = rec.get("created_by", {})
        source_file = created_by.get("source_file", "")
        if "sigpesq/advisorships" not in source_file:
            continue
        sigpesq_records.append(rec)

    return sigpesq_records


def parse_tracking_record(rec):
    """Extract relevant fields from a tracking record."""
    created_by = rec.get("created_by", {})

    source_record_id = created_by.get("source_record_id", "")
    match = re.match(r"sigpesq workplan\|(.+)", source_record_id)
    tracking_codpt = match.group(1).strip() if match else ""

    # All match sources
    match_sources = set()
    for m in rec.get("matches", []):
        sf = m.get("source_file", "")
        year_match = re.search(r"advisorships/(\d{4})/", sf)
        if year_match:
            match_sources.add(int(year_match.group(1)))

    # First source year
    first_sf = created_by.get("source_file", "")
    first_year_m = re.search(r"advisorships/(\d{4})/", first_sf)
    first_source_year = int(first_year_m.group(1)) if first_year_m else None

    # Latest source year (from attributes)
    attr = rec.get("attributes", {})
    latest_source_year = None
    for field_data in attr.values():
        if isinstance(field_data, dict) and "source_file" in field_data:
            sf = field_data["source_file"]
            year_match = re.search(r"advisorships/(\d{4})/", sf)
            if year_match:
                latest_source_year = int(year_match.group(1))
            break

    # Get dates from attributes
    start_str = attr.get("start_date", {}).get("value", "")
    end_str = attr.get("end_date", {}).get("value", "")
    name = attr.get("name", {}).get("value", "")

    start_date = None
    end_date = None
    try:
        if start_str:
            start_date = datetime.fromisoformat(start_str.strip('"'))
    except (ValueError, TypeError):
        pass
    try:
        if end_str:
            end_date = datetime.fromisoformat(end_str.strip('"'))
    except (ValueError, TypeError):
        pass

    return {
        "codpt": tracking_codpt,
        "first_source_year": first_source_year,
        "latest_source_year": latest_source_year,
        "match_sources": match_sources,
        "start_date": start_date,
        "end_date": end_date,
        "name": name.strip('"') if name else "",
    }


def validate_advisorships(date_from=None, date_to=None):
    """Main validation logic."""
    xlsx_data = load_all_xlsx_advisorships()
    tracking = load_full_refresh_tracking()

    # Build lookup: normalized CodPT -> which year folders contain it
    codpt_to_years = defaultdict(set)
    for year, records in xlsx_data.items():
        for rec in records:
            ncodpt = rec["CodPT_normalized"]
            if ncodpt:
                codpt_to_years[ncodpt].add(year)

    missing_from_source = []
    date_source_mismatch = []
    ok_count = 0
    filtered_total = 0

    for trec in tracking:
        parsed = parse_tracking_record(trec)
        ncodpt = parsed["codpt"]
        start_date = parsed["start_date"]
        end_date = parsed["end_date"]

        if not ncodpt:
            continue

        # Apply date filter: keep records that START within [date_from, date_to]
        if date_from is not None:
            if start_date is None or start_date < date_from:
                continue
        if date_to is not None:
            if start_date is None or start_date > date_to:
                continue

        filtered_total += 1

        # A. Does CodPT exist in any xlsx at all?
        if ncodpt not in codpt_to_years:
            missing_from_source.append(
                f"CodPT={ncodpt} ({parsed['name']}) NOT FOUND in ANY xlsx"
            )
            continue

        present_in = sorted(codpt_to_years[ncodpt])

        # B. Is the CodPT in one of its match sources?
        all_known_sources = (parsed["match_sources"]
                            | {parsed["first_source_year"]}
                            | {parsed["latest_source_year"]})
        all_known_sources.discard(None)

        if not all_known_sources.intersection(present_in):
            missing_from_source.append(
                f"CodPT={ncodpt} ({parsed['name']}) tracked sources={sorted(all_known_sources)} "
                f"but only found in xlsx years: {present_in}"
            )
            continue

        ok_count += 1

        # C. Date-source year consistency
        latest = parsed["latest_source_year"]
        if latest and start_date and latest != start_date.year:
            if start_date.year not in present_in:
                date_source_mismatch.append(
                    f"CodPT={ncodpt} | {parsed['start_date'].strftime('%Y-%m-%d')}→"
                    f"{parsed['end_date'].strftime('%Y-%m-%d') if parsed['end_date'] else '?'} "
                    f"source={latest}/ → expected {start_date.year}/ (not in that xlsx; "
                    f"only in {present_in}) | {parsed['name']}"
                )

    xlsx_counts = {year: len(recs) for year, recs in xlsx_data.items()}

    return {
        "missing_from_source": missing_from_source,
        "date_source_mismatch": date_source_mismatch,
        "ok_count": ok_count,
        "filtered_total": filtered_total,
        "tracking_count": len(tracking),
        "xlsx_counts": xlsx_counts,
        "xlsx_total": sum(xlsx_counts.values()),
        "unique_codpts": len(codpt_to_years),
    }


def print_report(results):
    """Print a formatted report."""
    print("=" * 75)
    print("  XLSX vs Full-Refresh Correspondence Validation Report")
    print("=" * 75)

    print(f"\n  Source xlsx files by year:")
    for year in sorted(results["xlsx_counts"]):
        print(f"    {year}/: {results['xlsx_counts'][year]} records")
    print(f"  Total xlsx records:              {results['xlsx_total']}")
    print(f"  Unique workplans (CodPT):        {results['unique_codpts']}")
    print(f"  Tracking records (sigpesq):      {results['tracking_count']}")
    print(f"  After date filter:               {results['filtered_total']}")
    print(f"  ✓ OK (CodPT in source):          {results['ok_count']}")
    print(f"  ✗ Not in any xlsx:               {len(results['missing_from_source'])}")
    print(f"  ⚠ Start-year ≠ source-year:      {len(results['date_source_mismatch'])}")
    print()

    if results["missing_from_source"]:
        print("-" * 75)
        print("  ✗ RECORDS NOT FOUND IN ANY XLSX:")
        print("-" * 75)
        for issue in results["missing_from_source"]:
            print(f"  • {issue}")
        print()

    if results["date_source_mismatch"]:
        print("-" * 75)
        print("  ⚠ START-YEAR ≠ SOURCE-YEAR (not in expected year xlsx)")
        print("-" * 75)
        for issue in results["date_source_mismatch"]:
            print(f"  • {issue}")
        print()

    total_issues = len(results["missing_from_source"]) + len(results["date_source_mismatch"])
    if total_issues == 0:
        print("  ✅ All records match their expected source xlsx correctly.")
    else:
        print(f"  Found {total_issues} issue(s).")
        print("  (Mismatches can be legitimate: same CodPT may appear across multiple")
        print("   year xlsx files, each with different date ranges for different phases.)")


def main():
    parser = argparse.ArgumentParser(description="Validate xlsx vs full-refresh correspondence")
    parser.add_argument("--from", dest="date_from", help="Start date filter (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="End date filter (YYYY-MM-DD)")
    args = parser.parse_args()

    date_from = datetime.strptime(args.date_from, "%Y-%m-%d") if args.date_from else None
    date_to = datetime.strptime(args.date_to, "%Y-%m-%d") if args.date_to else None

    results = validate_advisorships(date_from, date_to)
    print_report(results)


if __name__ == "__main__":
    main()
