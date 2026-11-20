import tempfile
import unittest
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from songs_api import create_app


def song(song_id, title, danceability, tempo):
    return {
        "id": song_id,
        "title": title,
        "danceability": danceability,
        "energy": 0.6,
        "mood": 1,
        "acousticness": 0.2,
        "tempo": tempo,
        "duration_ms": 200000,
        "num_sections": 8,
        "num_segments": 500,
        "valence": 0.4,
    }


class SongsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        csv_path = Path(self.temp_directory.name) / "songs.csv"
        pd.DataFrame(
            [
                song("id-d", "Delta", 0.4, 110),
                song("id-b", "Bravo", 0.2, 120),
                song("id-c", "Charlie", 0.3, None),
                song("id-a", "Alpha", 0.1, 130),
                song("id-p1", "Perfect", 0.5, 100),
                song("id-p2", "PERFECT   ", 0.6, 90),
            ]
        ).to_csv(csv_path, index=False)
        self.client = TestClient(create_app(csv_path))

    def test_pagination_and_default_sorting(self):
        response = self.client.get("/songs", params={"page": 1, "size": 2})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["page"], body["size"], body["total"]), (1, 2, 6))
        self.assertEqual([song["title"] for song in body["items"]], ["Alpha", "Bravo"])
        self.assertIsInstance(body["items"][0]["duration_ms"], int)

    def test_sorting_is_applied_to_full_dataset_before_pagination(self):
        response = self.client.get(
            "/songs",
            params={"page": 2, "size": 2, "sort_by": "title", "order": "asc"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [song["title"] for song in response.json()["items"]],
            ["Charlie", "Delta"],
        )

    def test_sorting_by_any_attribute_supports_descending_order(self):
        response = self.client.get(
            "/songs",
            params={"page": 1, "size": 1, "sort_by": "danceability", "order": "desc"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], "id-p2")

    def test_null_values_sort_last_in_descending_order(self):
        response = self.client.get(
            "/songs",
            params={"sort_by": "tempo", "order": "desc", "size": 6},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][-1]["id"], "id-c")
        self.assertIsNone(response.json()["items"][-1]["tempo"])

    def test_lookup_normalizes_case_and_whitespace_and_returns_all_matches(self):
        response = self.client.get(
            "/songs/lookup", params={"title": "  pErFeCt   "}
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(
            {song["id"] for song in body["matches"]}, {"id-p1", "id-p2"}
        )

    def test_lookup_returns_empty_matches_when_title_is_not_found(self):
        response = self.client.get("/songs/lookup", params={"title": "Not a song"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(response.json()["matches"], [])

    def test_unknown_sort_column_is_rejected(self):
        response = self.client.get("/songs", params={"sort_by": "unknown"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported sort_by", response.json()["detail"])

    def test_invalid_pagination_parameters_are_rejected(self):
        response = self.client.get("/songs", params={"page": 0, "size": 101})

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
