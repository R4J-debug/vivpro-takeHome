import json
import unittest

import pandas as pd

from normalize_songs import (
    ValidationRules,
    columnar_json_to_dataframe,
    normalize_tables,
)


def make_sources(table1_rows, table2_rows):
    return {
        "table1": pd.DataFrame(table1_rows),
        "table2": pd.DataFrame(table2_rows),
    }


def valid_song(song_id="song-1", **overrides):
    row = {
        "id": song_id,
        "title": "Example Song",
        "danceability": 0.5,
        "energy": 0.6,
        "mood": 1,
        "acousticness": 0.2,
        "tempo": 120,
        "duration_ms": 200000,
        "num_sections": 8,
        "num_segments": 500,
        "valence": 0.4,
    }
    row.update(overrides)
    return row


class NormalizeTablesTests(unittest.TestCase):
    def test_columnar_rows_align_by_index_and_keep_original_integer_type(self):
        frame = columnar_json_to_dataframe(
            {
                "song ID": {"0": "song-1", "2": "song-2"},
                "title": {"1": "Middle", "2": "Last"},
                "duration_ms": {"0": 158, "2": 200000},
            },
            "table1",
        )

        self.assertEqual(len(frame), 3)
        first = frame.loc[frame["_source_row_index"] == "0"].iloc[0]
        second = frame.loc[frame["_source_row_index"] == "1"].iloc[0]
        self.assertEqual(first["song_id"], "song-1")
        self.assertEqual(first["duration_ms"], 158)
        self.assertIsInstance(first["duration_ms"], int)
        self.assertTrue(pd.isna(first["title"]))
        self.assertTrue(pd.isna(second["song_id"]))

    def test_identical_duplicate_has_one_song_and_no_conflict(self):
        row = valid_song()
        result = normalize_tables(make_sources([row], [row]))

        self.assertEqual(len(result.normalized_songs), 1)
        self.assertTrue(result.conflicts.empty)
        self.assertEqual(result.data_quality_report["duplicate_records_detected"], 1)

    def test_conflicting_valid_value_uses_table1_and_reports_both(self):
        result = normalize_tables(
            make_sources(
                [valid_song(danceability=0.688)],
                [valid_song(danceability=0.7)],
            )
        )

        song = result.normalized_songs.iloc[0]
        conflict = result.conflicts.iloc[0]
        self.assertEqual(song["danceability"], 0.688)
        self.assertEqual(conflict["table1_value"], 0.688)
        self.assertEqual(conflict["table2_value"], 0.7)
        self.assertEqual(conflict["selected_value"], 0.688)
        self.assertEqual(conflict["selected_source"], "table1")

    def test_missing_value_uses_other_sources_valid_value(self):
        result = normalize_tables(
            make_sources(
                [valid_song(danceability=None)],
                [valid_song(danceability=0.7)],
            )
        )
        self.assertEqual(result.normalized_songs.iloc[0]["danceability"], 0.7)
        self.assertTrue(result.conflicts.empty)

    def test_invalid_danceability_is_nulled_but_record_is_retained(self):
        result = normalize_tables(
            make_sources([valid_song(danceability=1.42)], [valid_song("other")])
        )
        song = result.normalized_songs.loc[
            result.normalized_songs["id"] == "song-1"
        ].iloc[0]

        self.assertTrue(pd.isna(song["danceability"]))
        self.assertEqual(len(result.normalized_songs), 2)
        issue = result.validation_report[
            (result.validation_report["song_id"] == "song-1")
            & (result.validation_report["column"] == "danceability")
        ].iloc[0]
        self.assertEqual(issue["original_value"], 1.42)
        self.assertEqual(issue["issue_type"], "invalid_value")

    def test_negative_acousticness_is_invalid_and_preserved_in_report(self):
        result = normalize_tables(
            make_sources([valid_song(acousticness=-0.05)], [valid_song("other")])
        )
        song = result.normalized_songs.loc[
            result.normalized_songs["id"] == "song-1"
        ].iloc[0]
        self.assertTrue(pd.isna(song["acousticness"]))
        self.assertIn(
            -0.05,
            result.validation_report.loc[
                result.validation_report["column"] == "acousticness",
                "original_value",
            ].tolist(),
        )

    def test_zero_tempo_is_invalid(self):
        result = normalize_tables(
            make_sources([valid_song(tempo=0)], [valid_song("other")])
        )
        song = result.normalized_songs.loc[
            result.normalized_songs["id"] == "song-1"
        ].iloc[0]
        self.assertTrue(pd.isna(song["tempo"]))

    def test_same_title_different_ids_are_not_merged(self):
        result = normalize_tables(
            make_sources(
                [valid_song("song-1", title="Shared title")],
                [valid_song("song-2", title="Shared title")],
            )
        )
        self.assertEqual(len(result.normalized_songs), 2)

    def test_numeric_strings_are_coerced_and_na_string_is_missing(self):
        result = normalize_tables(
            make_sources(
                [
                    valid_song(
                        danceability="0.521",
                        tempo="108.73",
                        energy="N/A",
                    )
                ],
                [valid_song("other")],
            )
        )
        song = result.normalized_songs.loc[
            result.normalized_songs["id"] == "song-1"
        ].iloc[0]
        self.assertEqual(song["danceability"], 0.521)
        self.assertEqual(song["tempo"], 108.73)
        self.assertTrue(pd.isna(song["energy"]))
        energy_issue = result.validation_report[
            (result.validation_report["song_id"] == "song-1")
            & (result.validation_report["column"] == "energy")
        ].iloc[0]
        self.assertEqual(energy_issue["original_value"], "N/A")
        original_record = json.loads(energy_issue["original_record"])
        self.assertEqual(original_record["energy"], "N/A")

    def test_suspicious_duration_is_flagged_not_changed(self):
        result = normalize_tables(
            make_sources(
                [valid_song(duration_ms=158)],
                [valid_song("other")],
            )
        )
        song = result.normalized_songs.loc[
            result.normalized_songs["id"] == "song-1"
        ].iloc[0]
        issue = result.validation_report[
            (result.validation_report["song_id"] == "song-1")
            & (result.validation_report["column"] == "duration_ms")
        ].iloc[0]

        self.assertEqual(song["duration_ms"], 158)
        self.assertEqual(issue["issue_type"], "suspicious_outlier")
        self.assertEqual(issue["original_value"], 158)
        self.assertIsInstance(issue["original_value"], int)

    def test_missing_id_is_rejected(self):
        result = normalize_tables(
            make_sources(
                [valid_song(id=None)],
                [valid_song("other")],
            )
        )
        self.assertEqual(len(result.rejected_records), 1)
        self.assertNotIn(None, result.normalized_songs["id"].tolist())
        self.assertIn("id", result.rejected_records.iloc[0]["rejection_reason"])

    def test_repeated_execution_is_deterministic(self):
        sources = make_sources(
            [valid_song(danceability=0.688)],
            [valid_song(danceability=0.7), valid_song("second")],
        )
        first = normalize_tables(sources)
        second = normalize_tables(sources)

        pd.testing.assert_frame_equal(first.normalized_songs, second.normalized_songs)
        pd.testing.assert_frame_equal(first.conflicts, second.conflicts)
        self.assertEqual(first.data_quality_report, second.data_quality_report)
        self.assertEqual(first.data_quality_report["total_unique_song_ids"], 2)

    def test_source_mapping_order_does_not_change_results(self):
        table1 = pd.DataFrame([valid_song(danceability=0.688)])
        table2 = pd.DataFrame([valid_song(danceability=0.7)])
        first = normalize_tables({"table1": table1, "table2": table2})
        reversed_mapping = normalize_tables({"table2": table2, "table1": table1})

        pd.testing.assert_frame_equal(
            first.normalized_songs, reversed_mapping.normalized_songs
        )
        pd.testing.assert_frame_equal(first.conflicts, reversed_mapping.conflicts)


if __name__ == "__main__":
    unittest.main()
