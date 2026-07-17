"""JSON and JSONL sources. Agents emit JSON; andon verifies it against the
data it came from — so JSON has to be a first-class source, not a conversion
step the user does first."""

import json
from pathlib import Path

import pytest

from andon.errors import SourceError
from andon.sources import SourceStore


def test_reads_json_array(tmp_path: Path) -> None:
    p = tmp_path / "orders.json"
    p.write_text(
        json.dumps(
            [
                {"id": 1, "region": "EU", "revenue": 120.0},
                {"id": 2, "region": "US", "revenue": 80.0},
            ]
        ),
        encoding="utf-8",
    )
    store = SourceStore(tmp_path, {"o": "orders.json"})
    df = store.frame("o")
    assert list(df.columns) == ["id", "region", "revenue"]
    assert df["revenue"].sum() == 200.0
    assert store.infos()[0].kind == "json"


def test_reads_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text('{"id": 1, "kind": "a"}\n{"id": 2, "kind": "b"}\n', encoding="utf-8")
    store = SourceStore(tmp_path, {"e": "events.jsonl"})
    df = store.frame("e")
    assert len(df) == 2
    assert list(df.columns) == ["id", "kind"]
    assert store.infos()[0].kind == "jsonl"


def test_reads_ndjson(tmp_path: Path) -> None:
    p = tmp_path / "events.ndjson"
    p.write_text('{"id": 1}\n{"id": 2}\n{"id": 3}\n', encoding="utf-8")
    store = SourceStore(tmp_path, {"e": "events.ndjson"})
    assert len(store.frame("e")) == 3


def test_bad_json_is_a_clear_error(tmp_path: Path) -> None:
    p = tmp_path / "broken.json"
    p.write_text("{not valid json", encoding="utf-8")
    store = SourceStore(tmp_path, {"b": "broken.json"})
    with pytest.raises(SourceError, match="as JSON"):
        store.frame("b")


def test_json_headers_are_stripped(tmp_path: Path) -> None:
    p = tmp_path / "ws.json"
    p.write_text(json.dumps([{" id ": 1, "name ": "a"}]), encoding="utf-8")
    store = SourceStore(tmp_path, {"w": "ws.json"})
    assert list(store.frame("w").columns) == ["id", "name"]


def test_json_runs_end_to_end(tmp_path: Path, run_spec) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "orders.json"
    p.write_text(
        json.dumps(
            [
                {"id": 1, "status": "shipped"},
                {"id": 2, "status": "shipped"},
                {"id": 3, "status": "cancelled"},
            ]
        ),
        encoding="utf-8",
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"o": "orders.json"},
            "checks": [
                {
                    "reconcile.row_count": {
                        "left": {"source": "o", "where": "status == 'shipped'"},
                        "right": {"value": 2},
                    }
                }
            ],
        }
    )
    assert report.verdict == "PASS"
