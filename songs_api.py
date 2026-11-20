from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from fastapi import FastAPI, HTTPException, Query


SONG_COLUMNS = (
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
    "valence",
)
MAX_PAGE_SIZE = 100
CSV_DTYPES = {
    "id": "string",
    "danceability": "Float64",
    "energy": "Float64",
    "mood": "Int64",
    "acousticness": "Float64",
    "tempo": "Float64",
    "duration_ms": "Int64",
    "num_sections": "Int64",
    "num_segments": "Int64",
    "valence": "Float64",
}


def _normalized_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized.strip()).casefold()


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _song_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {column: _json_value(row[column]) for column in SONG_COLUMNS}


def create_app(csv_path: str | Path | None = None) -> FastAPI:
    """Create the API, optionally pointing it at a specific normalized CSV."""
    data_path = Path(
        csv_path
        or os.environ.get(
            "SONGS_CSV_PATH",
            Path(__file__).resolve().parent
            / "normalized_output"
            / "normalized_songs.csv",
        )
    )
    dataset: pd.DataFrame | None = None

    def get_dataset() -> pd.DataFrame:
        nonlocal dataset
        if dataset is None:
            try:
                loaded = pd.read_csv(data_path, dtype=CSV_DTYPES)
            except OSError as error:
                raise RuntimeError(
                    f"Could not read normalized songs CSV at {data_path}: {error}"
                ) from error

            missing_columns = sorted(set(SONG_COLUMNS) - set(loaded.columns))
            if missing_columns:
                raise RuntimeError(
                    f"Normalized songs CSV is missing columns: {', '.join(missing_columns)}"
                )
            loaded = loaded.loc[:, SONG_COLUMNS].copy()
            loaded["title"] = loaded["title"].astype("string")
            if loaded["id"].isna().any() or loaded["title"].isna().any():
                raise RuntimeError("Normalized songs CSV contains a missing ID or title")
            if loaded["id"].duplicated().any():
                raise RuntimeError("Normalized songs CSV contains duplicate IDs")
            dataset = loaded
        return dataset

    app = FastAPI(title="Songs API", version="1.0.0")

    @app.get("/songs")
    def list_songs(
        page: int = Query(default=1, ge=1),
        size: int = Query(default=10, ge=1, le=MAX_PAGE_SIZE),
        sort_by: str = Query(default="title"),
        order: str = Query(default="asc", pattern="^(asc|desc)$"),
    ) -> dict[str, Any]:
        songs = get_dataset()
        if sort_by not in SONG_COLUMNS:
            allowed = ", ".join(SONG_COLUMNS)
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported sort_by {sort_by!r}. Choose from: {allowed}",
            )

        sorted_songs = songs.sort_values(
            by=sort_by,
            ascending=order == "asc",
            na_position="last",
            kind="mergesort",
        )
        start = (page - 1) * size
        items = [
            _song_record(row)
            for row in sorted_songs.iloc[start : start + size].to_dict(
                orient="records"
            )
        ]
        return {"page": page, "size": size, "total": len(songs), "items": items}

    @app.get("/songs/lookup")
    def lookup_song(
        title: str = Query(..., min_length=1),
    ) -> dict[str, Any]:
        query = _normalized_title(title)
        if not query:
            raise HTTPException(status_code=422, detail="title must not be blank")

        songs = get_dataset()
        normalized_titles = songs["title"].map(_normalized_title)
        matches = songs.loc[normalized_titles == query]
        records = [_song_record(row) for row in matches.to_dict(orient="records")]
        return {"query": title, "count": len(records), "matches": records}

    return app


app = create_app()
