from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd


REQUIRED_COLUMNS = (
    "id",
    "title",
    "danceability",
    "energy",
    "mood",
    "acousticness",
    "tempo",
    "duration_ms",
    "num_sections",
    "num_segments",
)
OPTIONAL_COLUMNS = ("valence",)
INTEGER_COLUMNS = frozenset(("mood", "duration_ms", "num_sections", "num_segments"))
RANGE_COLUMNS = frozenset(("danceability", "energy", "acousticness", "valence"))
NULL_STRINGS = frozenset(("", "n/a", "na", "null", "none", "nan"))
SOURCE_ROW_COLUMN = "_source_row_index"
SOURCE_TABLE_COLUMN = "_source_table"
METADATA_COLUMNS = frozenset((SOURCE_ROW_COLUMN, SOURCE_TABLE_COLUMN))


@dataclass(frozen=True)
class ValidationRules:
    """Business rules used to validate and normalize song attributes."""

    numeric_ranges: Mapping[str, tuple[float | None, float | None]] = field(
        default_factory=lambda: {
            "danceability": (0.0, 1.0),
            "energy": (0.0, 1.0),
            "acousticness": (0.0, 1.0),
            "valence": (0.0, 1.0),
            "tempo": (0.0, None),
        }
    )
    allowed_values: Mapping[str, frozenset[int]] = field(
        default_factory=lambda: {"mood": frozenset((0, 1))}
    )
    positive_integer_columns: frozenset[str] = frozenset(
        ("duration_ms", "num_sections", "num_segments")
    )
    suspicious_duration_ms_below: int | None = 1000
    source_priority: tuple[str, ...] = ("table1", "table2")


@dataclass
class NormalizationResult:
    normalized_songs: pd.DataFrame
    rejected_records: pd.DataFrame
    conflicts: pd.DataFrame
    validation_report: pd.DataFrame
    data_quality_report: dict[str, Any]


def standardize_column_name(name: Any) -> str:
    """Convert a column label to lowercase snake_case."""
    normalized = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip().lower())
    normalized = normalized.strip("_")
    if not normalized:
        raise ValueError(f"Column name {name!r} becomes empty after standardization")
    return normalized


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in NULL_STRINGS
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isnan(value) if isinstance(value, float) else False
    return False


def _json_safe(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _row_index_sort_key(value: Any) -> tuple[int, Any]:
    text = str(value)
    if text.isdigit():
        return (0, int(text))
    return (1, text)


def columnar_json_to_dataframe(
    payload: Mapping[str, Any], source_name: str
) -> pd.DataFrame:
    """Convert a column-oriented JSON object into a row-oriented DataFrame."""
    if not isinstance(payload, Mapping):
        raise ValueError(f"{source_name} must contain a JSON object at its root")

    columns: dict[str, Mapping[str, Any]] = {}
    for raw_name, values in payload.items():
        name = standardize_column_name(raw_name)
        if name in columns:
            raise ValueError(
                f"{source_name} has multiple columns that standardize to {name!r}"
            )
        if not isinstance(values, Mapping):
            raise ValueError(
                f"{source_name}.{raw_name} must be a mapping of row index to value"
            )
        columns[name] = values

    row_indices = set().union(*(set(values) for values in columns.values()))
    ordered_indices = sorted(row_indices, key=_row_index_sort_key)
    records = [
        {
            **{name: values.get(index, pd.NA) for name, values in columns.items()},
            SOURCE_ROW_COLUMN: str(index),
            SOURCE_TABLE_COLUMN: source_name,
        }
        for index in ordered_indices
    ]
    output_columns = [*columns, SOURCE_ROW_COLUMN, SOURCE_TABLE_COLUMN]
    return pd.DataFrame(
        {
            column: pd.Series(
                [record[column] for record in records], dtype=object
            )
            for column in output_columns
        },
        columns=output_columns,
    )


def read_columnar_json(path: Path, source_name: str) -> pd.DataFrame:
    with path.open("r", encoding="utf-8-sig") as file:
        payload = json.load(file)
    return columnar_json_to_dataframe(payload, source_name)


def _numeric_value(value: Any) -> tuple[int | float | None, str | None]:
    if isinstance(value, bool):
        return None, "boolean_is_not_numeric"
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None, "not_numeric"
    if not math.isfinite(number):
        return None, "not_finite"
    if number.is_integer():
        return int(number), None
    return number, None


def _validate_numeric(
    column: str, original: Any, rules: ValidationRules
) -> tuple[int | float | None, str | None]:
    number, error = _numeric_value(original)
    if error:
        return None, error
    if number is None:
        return None, None

    if column in rules.numeric_ranges:
        minimum, maximum = rules.numeric_ranges[column]
        if minimum is not None and number < minimum:
            return None, "out_of_range"
        if maximum is not None and number > maximum:
            return None, "out_of_range"

    if column in rules.allowed_values and number not in rules.allowed_values[column]:
        return None, "not_in_allowed_values"

    if column in INTEGER_COLUMNS and not isinstance(number, int):
        return None, "not_an_integer"

    if column == "tempo" and number <= 0:
        return None, "must_be_positive"

    if column in rules.positive_integer_columns and number <= 0:
        return None, "must_be_positive"

    return number, None


def _records_from_source(
    frame: pd.DataFrame,
    source_name: str,
    all_columns: Sequence[str],
    rules: ValidationRules,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    standardized = frame.copy()
    renamed: dict[Any, str] = {}
    for column in standardized.columns:
        if column in METADATA_COLUMNS:
            renamed[column] = column
        else:
            renamed[column] = standardize_column_name(column)
    standardized = standardized.rename(columns=renamed)
    if len(set(standardized.columns)) != len(standardized.columns):
        raise ValueError(f"{source_name} has duplicate columns after standardization")

    for column in all_columns:
        if column not in standardized:
            standardized[column] = pd.NA
    if SOURCE_ROW_COLUMN not in standardized:
        standardized[SOURCE_ROW_COLUMN] = [str(index) for index in standardized.index]
    if SOURCE_TABLE_COLUMN not in standardized:
        standardized[SOURCE_TABLE_COLUMN] = source_name

    missing_counts = {
        column: sum(_is_missing(value) for value in standardized[column].tolist())
        for column in all_columns
    }

    valid_records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for raw in standardized.to_dict(orient="records"):
        cleaned: dict[str, Any] = {}
        source_row_index = str(raw[SOURCE_ROW_COLUMN])

        for column in all_columns:
            value = raw.get(column, pd.NA)
            if _is_missing(value):
                cleaned[column] = pd.NA
            elif column == "id":
                cleaned[column] = value
            elif isinstance(value, str):
                cleaned[column] = value.strip()
            else:
                cleaned[column] = value

        row_issues: list[dict[str, Any]] = []
        for key in ("id", "title"):
            value = cleaned.get(key, pd.NA)
            invalid_reason: str | None = None
            if _is_missing(value):
                invalid_reason = "missing_required_value"
                issue_type = "missing_value"
            elif not isinstance(value, str) or not value.strip():
                invalid_reason = "required_value_must_be_non_empty_text"
                issue_type = "invalid_value"
            else:
                issue_type = ""
            if invalid_reason:
                row_issues.append(
                    {
                        "source_table": source_name,
                        "source_row_index": source_row_index,
                        "song_id": _json_safe(cleaned.get("id")),
                        "title": _json_safe(cleaned.get("title")),
                        "column": key,
                        "original_value": _json_safe(raw.get(key, pd.NA)),
                        "issue_type": issue_type,
                        "reason": invalid_reason,
                    }
                )

        if any(issue["column"] in ("id", "title") for issue in row_issues):
            rejected.append(
                {
                    "source_table": source_name,
                    "source_row_index": source_row_index,
                    "song_id": _json_safe(raw.get("id", pd.NA)),
                    "title": _json_safe(raw.get("title", pd.NA)),
                    "rejection_reason": "; ".join(
                        f"{issue['column']}: {issue['reason']}" for issue in row_issues
                    ),
                    "original_record": json.dumps(
                        _json_safe(raw), ensure_ascii=False, sort_keys=True
                    ),
                }
            )
            for issue in row_issues:
                issue["original_record"] = json.dumps(
                    _json_safe(raw), ensure_ascii=False, sort_keys=True
                )
            issues.extend(row_issues)
            continue

        for column in all_columns:
            if column in ("id", "title"):
                continue
            value = raw.get(column, pd.NA)
            cleaned_value = cleaned.get(column, pd.NA)
            if _is_missing(value):
                cleaned[column] = pd.NA
                if column in REQUIRED_COLUMNS or column in OPTIONAL_COLUMNS:
                    row_issues.append(
                        {
                            "source_table": source_name,
                            "source_row_index": source_row_index,
                            "song_id": cleaned["id"],
                            "title": cleaned["title"],
                            "column": column,
                            "original_value": _json_safe(value),
                            "issue_type": "missing_value",
                            "reason": "value_missing_or_null",
                        }
                    )
                continue

            if column in REQUIRED_COLUMNS or column in OPTIONAL_COLUMNS:
                value, error = _validate_numeric(column, cleaned_value, rules)
                if error:
                    row_issues.append(
                        {
                            "source_table": source_name,
                            "source_row_index": source_row_index,
                            "song_id": cleaned["id"],
                            "title": cleaned["title"],
                            "column": column,
                            "original_value": _json_safe(raw.get(column, pd.NA)),
                            "issue_type": "invalid_value",
                            "reason": error,
                        }
                    )
                    cleaned[column] = pd.NA
                else:
                    cleaned[column] = value

            if column == "duration_ms" and not _is_missing(cleaned[column]):
                threshold = rules.suspicious_duration_ms_below
                if threshold is not None and cleaned[column] < threshold:
                    row_issues.append(
                        {
                            "source_table": source_name,
                            "source_row_index": source_row_index,
                            "song_id": cleaned["id"],
                            "title": cleaned["title"],
                            "column": column,
                            "original_value": _json_safe(raw.get(column, pd.NA)),
                            "issue_type": "suspicious_outlier",
                            "reason": f"duration_ms_below_configured_threshold_{threshold}",
                        }
                    )

        title = cleaned["title"]
        if isinstance(title, str) and "\ufffd" in title:
            row_issues.append(
                {
                    "source_table": source_name,
                    "source_row_index": source_row_index,
                    "song_id": cleaned["id"],
                    "title": title,
                    "column": "title",
                    "original_value": title,
                    "issue_type": "text_replacement_character",
                    "reason": "title_contains_unicode_replacement_character",
                }
            )

        for issue in row_issues:
            issue["original_record"] = json.dumps(
                _json_safe(raw), ensure_ascii=False, sort_keys=True
            )
        cleaned[SOURCE_ROW_COLUMN] = source_row_index
        cleaned[SOURCE_TABLE_COLUMN] = source_name
        valid_records.append(cleaned)
        issues.extend(row_issues)

    return valid_records, rejected, issues, sum(missing_counts.values())


def _values_equal(left: Any, right: Any) -> bool:
    if _is_missing(left) or _is_missing(right):
        return _is_missing(left) and _is_missing(right)
    try:
        result = left == right
        return bool(result)
    except (TypeError, ValueError):
        return json.dumps(_json_safe(left), sort_keys=True) == json.dumps(
            _json_safe(right), sort_keys=True
        )


def _aggregate_source_rows(
    rows: list[dict[str, Any]],
    source_name: str,
    columns: Sequence[str],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """Combine duplicate IDs within a source deterministically."""
    ordered = sorted(rows, key=lambda row: _row_index_sort_key(row[SOURCE_ROW_COLUMN]))
    result: dict[str, Any] = {
        SOURCE_TABLE_COLUMN: source_name,
        SOURCE_ROW_COLUMN: [row[SOURCE_ROW_COLUMN] for row in ordered],
    }
    first = ordered[0]
    for column in columns:
        candidates = [row.get(column, pd.NA) for row in ordered]
        present = [value for value in candidates if not _is_missing(value)]
        if not present:
            result[column] = pd.NA
            continue
        chosen = present[0]
        distinct = []
        for value in present:
            if not any(_values_equal(value, existing) for existing in distinct):
                distinct.append(value)
        if len(distinct) > 1:
            issues.append(
                {
                    "source_table": source_name,
                    "source_row_index": ",".join(result[SOURCE_ROW_COLUMN]),
                    "song_id": first.get("id"),
                    "title": first.get("title"),
                    "column": column,
                    "original_value": json.dumps(
                        [_json_safe(value) for value in present], ensure_ascii=False
                    ),
                    "issue_type": "duplicate_source_conflict",
                    "reason": "multiple_valid_values_for_id_within_source; selected_first_sorted_row",
                }
            )
        result[column] = chosen
    return result


def _to_nullable_dataframe(
    rows: list[dict[str, Any]], columns: Sequence[str]
) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=columns)
    for column in INTEGER_COLUMNS:
        if column in frame:
            frame[column] = pd.array(frame[column], dtype="Int64")
    for column in RANGE_COLUMNS | {"tempo"}:
        if column in frame:
            frame[column] = pd.array(frame[column], dtype="Float64")
    return frame


def _object_dataframe(
    rows: list[dict[str, Any]], columns: Sequence[str]
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: pd.Series(
                [row.get(column, pd.NA) for row in rows], dtype=object
            )
            for column in columns
        },
        columns=columns,
    )


def normalize_tables(
    sources: Mapping[str, pd.DataFrame],
    rules: ValidationRules | None = None,
) -> NormalizationResult:
    """Clean, validate, deduplicate, and merge named source tables.

    Source names are stable identities (normally ``table1`` and ``table2``);
    their mapping insertion order does not affect the result.
    """
    rules = rules or ValidationRules()
    if len(sources) != 2:
        raise ValueError("Exactly two named source tables are required")
    if len(set(rules.source_priority)) != len(rules.source_priority):
        raise ValueError("source_priority cannot contain duplicate names")
    if set(sources) != set(rules.source_priority):
        raise ValueError(
            "source_priority must list exactly the source names present in sources"
        )

    source_order = list(rules.source_priority)
    all_columns = set(REQUIRED_COLUMNS) | set(OPTIONAL_COLUMNS)
    for frame in sources.values():
        for column in frame.columns:
            if column not in METADATA_COLUMNS:
                all_columns.add(standardize_column_name(column))
    ordered_columns = list(REQUIRED_COLUMNS) + [
        column
        for column in sorted(all_columns - set(REQUIRED_COLUMNS) - set(OPTIONAL_COLUMNS))
    ] + list(OPTIONAL_COLUMNS)

    records_by_source: dict[str, list[dict[str, Any]]] = {}
    rejected_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    source_row_counts: dict[str, int] = {}
    missing_counts = {column: 0 for column in ordered_columns}

    for source_name in source_order:
        frame = sources[source_name]
        source_row_counts[source_name] = len(frame)
        records, rejected, issues, _ = _records_from_source(
            frame, source_name, ordered_columns, rules
        )
        records_by_source[source_name] = records
        rejected_rows.extend(rejected)
        validation_rows.extend(issues)

        standardized = frame.copy()
        rename_map = {
            column: column
            if column in METADATA_COLUMNS
            else standardize_column_name(column)
            for column in standardized.columns
        }
        standardized = standardized.rename(columns=rename_map)
        for column in ordered_columns:
            if column not in standardized:
                missing_counts[column] += len(standardized)
            else:
                missing_counts[column] += sum(
                    _is_missing(value) for value in standardized[column].tolist()
                )

    groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for source_name in source_order:
        for row in records_by_source[source_name]:
            groups.setdefault(row["id"], {}).setdefault(source_name, []).append(row)

    aggregated: dict[str, dict[str, dict[str, Any]]] = {}
    for song_id, source_groups in groups.items():
        aggregated[song_id] = {}
        for source_name, rows in source_groups.items():
            aggregated[song_id][source_name] = _aggregate_source_rows(
                rows, source_name, ordered_columns, validation_rows
            )

    conflicts: list[dict[str, Any]] = []
    canonical_rows: list[dict[str, Any]] = []
    first_source, second_source = source_order

    for song_id in sorted(groups):
        source_groups = aggregated[song_id]
        selected: dict[str, Any] = {"id": song_id}
        for column in ordered_columns:
            if column == "id":
                continue
            values = {
                source: source_groups[source].get(column, pd.NA)
                for source in source_order
                if source in source_groups
            }
            valid = {source: value for source, value in values.items() if not _is_missing(value)}
            if len(valid) == 2 and not _values_equal(
                valid[first_source], valid[second_source]
            ):
                chosen_source = first_source
                selected_value = valid[chosen_source]
                conflicts.append(
                    {
                        "song_id": song_id,
                        "column": column,
                        "table1_value": _json_safe(
                            source_groups.get("table1", {}).get(column, pd.NA)
                        ),
                        "table2_value": _json_safe(
                            source_groups.get("table2", {}).get(column, pd.NA)
                        ),
                        "selected_value": _json_safe(selected_value),
                        "selected_source": chosen_source,
                        "resolution_reason": "both_valid_different_values; configured_source_priority",
                    }
                )
            elif valid:
                chosen_source = next(
                    source for source in source_order if source in valid
                )
                selected_value = valid[chosen_source]
            else:
                selected_value = pd.NA
            selected[column] = selected_value

        selected["source_tables"] = ";".join(
            source for source in source_order if source in source_groups
        )
        selected["source_row_indices"] = json.dumps(
            {
                source: source_groups[source][SOURCE_ROW_COLUMN]
                for source in source_order
                if source in source_groups
            },
            sort_keys=True,
        )
        canonical_rows.append(selected)

    canonical_columns = [
        *ordered_columns,
        "source_tables",
        "source_row_indices",
    ]
    normalized = _to_nullable_dataframe(canonical_rows, canonical_columns)

    rejected_columns = (
        "source_table",
        "source_row_index",
        "song_id",
        "title",
        "rejection_reason",
        "original_record",
    )
    conflict_columns = (
        "song_id",
        "column",
        "table1_value",
        "table2_value",
        "selected_value",
        "selected_source",
        "resolution_reason",
    )
    validation_columns = (
        "source_table",
        "source_row_index",
        "song_id",
        "title",
        "column",
        "original_value",
        "original_record",
        "issue_type",
        "reason",
    )
    rejected_frame = _object_dataframe(rejected_rows, rejected_columns)
    conflict_frame = _object_dataframe(conflicts, conflict_columns)
    validation_frame = _object_dataframe(validation_rows, validation_columns)

    invalid_counts: dict[str, int] = {}
    for issue in validation_rows:
        if issue["issue_type"] == "invalid_value":
            invalid_counts[issue["column"]] = invalid_counts.get(issue["column"], 0) + 1
    invalid_counts = {column: invalid_counts.get(column, 0) for column in ordered_columns}

    ids_by_source = {
        source: {row["id"] for row in records_by_source[source]}
        for source in source_order
    }
    overlap_ids = sorted(ids_by_source[source_order[0]] & ids_by_source[source_order[1]])
    quality_report = {
        "total_records_table1": source_row_counts["table1"],
        "total_records_table2": source_row_counts["table2"],
        "total_unique_song_ids": len(groups),
        "duplicate_records_detected": sum(
            sum(len(rows) for rows in source_groups.values()) - 1
            for source_groups in groups.values()
        ),
        "overlapping_song_ids": overlap_ids,
        "missing_values_per_column": missing_counts,
        "invalid_values_per_column": invalid_counts,
        "conflicting_attributes": len(conflicts),
        "rejected_records": len(rejected_rows),
        "successfully_normalized_records": len(normalized),
        "suspicious_outliers": int(
            sum(validation_frame["issue_type"] == "suspicious_outlier")
        )
        if not validation_frame.empty
        else 0,
    }

    return NormalizationResult(
        normalized_songs=normalized,
        rejected_records=rejected_frame,
        conflicts=conflict_frame,
        validation_report=validation_frame,
        data_quality_report=quality_report,
    )


def write_outputs(result: NormalizationResult, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    result.normalized_songs.to_csv(
        output_directory / "normalized_songs.csv", index=False, encoding="utf-8"
    )
    result.rejected_records.to_csv(
        output_directory / "rejected_records.csv", index=False, encoding="utf-8"
    )
    result.conflicts.to_csv(
        output_directory / "conflicts.csv", index=False, encoding="utf-8"
    )
    result.validation_report.to_csv(
        output_directory / "validation_report.csv", index=False, encoding="utf-8"
    )
    with (output_directory / "data_quality_report.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(result.data_quality_report, file, ensure_ascii=False, indent=2)


def _find_unique_input(root: Path, filename: str) -> Path:
    matches = [
        path
        for path in root.rglob(filename)
        if "__MACOSX" not in path.parts
        and "normalized_output" not in path.parts
    ]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one {filename!r} under {root}, found {len(matches)}"
        )
    return matches[0]


def _print_summary(result: NormalizationResult) -> None:
    report = result.data_quality_report
    print("Normalization summary")
    print(f"  Table 1 records: {report['total_records_table1']}")
    print(f"  Table 2 records: {report['total_records_table2']}")
    print(f"  Unique song IDs: {report['total_unique_song_ids']}")
    print(f"  Overlapping IDs: {', '.join(report['overlapping_song_ids']) or 'none'}")
    print(f"  Missing values by column: {report['missing_values_per_column']}")
    print(f"  Invalid values by column: {report['invalid_values_per_column']}")
    print(f"  Valid-value conflicts: {report['conflicting_attributes']}")
    print(f"  Rejected records: {report['rejected_records']}")
    print(f"  Suspicious outliers: {report['suspicious_outliers']}")
    if not result.validation_report.empty:
        noteworthy = result.validation_report[
            result.validation_report["issue_type"].isin(
                ("invalid_value", "suspicious_outlier", "text_replacement_character")
            )
        ]
        if not noteworthy.empty:
            print("  Noteworthy findings:")
            for issue in noteworthy.to_dict(orient="records"):
                print(
                    "   - "
                    f"{issue['source_table']} row {issue['source_row_index']}: "
                    f"{issue['title']!r}, {issue['column']}={issue['original_value']!r} "
                    f"({issue['issue_type']}: {issue['reason']})"
                )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize and reconcile two column-oriented music JSON exports."
    )
    parser.add_argument("--table1", type=Path, help="Path to the higher-priority JSON export")
    parser.add_argument("--table2", type=Path, help="Path to the lower-priority JSON export")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("normalized_output"),
        help="Directory for CSV and JSON outputs (default: normalized_output)",
    )
    parser.add_argument(
        "--suspicious-duration-ms-below",
        type=int,
        default=1000,
        help="Flag positive durations below this value without changing them (default: 1000)",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    try:
        table1_path = args.table1 or _find_unique_input(root, "songs_part1.json")
        table2_path = args.table2 or _find_unique_input(root, "songs_part2.json")
        sources = {
            "table1": read_columnar_json(table1_path, "table1"),
            "table2": read_columnar_json(table2_path, "table2"),
        }
        rules = ValidationRules(
            suspicious_duration_ms_below=args.suspicious_duration_ms_below
        )
        result = normalize_tables(sources, rules)
        _print_summary(result)
        write_outputs(result, args.output_dir)
        print(f"  Outputs written to: {args.output_dir.resolve()}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Normalization failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
