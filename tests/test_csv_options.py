"""CSV encoding and delimiter controls.

Turkish exports out of Excel are the motivating case: they are frequently
`;`-separated and encoded cp1254, and they carry a UTF-8 BOM that poisons the
first column name unless it is stripped. These tests cover the mapping form of
a source (`{path:, encoding:, delimiter:}`), the utf-8-sig default, and the
error a wrong encoding produces.
"""

import csv
from pathlib import Path

import pytest

from andon.errors import SourceError
from andon.sources import SourceStore, parse_ref

BASE = Path(".")


# -- parse_ref, the mapping form -------------------------------------------


def test_parse_mapping_carries_csv_options() -> None:
    ref = parse_ref({"path": "data/sales.csv", "encoding": "cp1254", "delimiter": ";"}, BASE)
    assert ref.path == BASE / "data/sales.csv"
    assert ref.encoding == "cp1254"
    assert ref.delimiter == ";"


def test_plain_string_has_no_options() -> None:
    ref = parse_ref("data/sales.csv", BASE)
    assert ref.encoding is None and ref.delimiter is None


def test_mapping_needs_a_path() -> None:
    with pytest.raises(SourceError, match="needs a `path:`"):
        parse_ref({"encoding": "utf-8"}, BASE)


def test_mapping_rejects_unknown_option() -> None:
    with pytest.raises(SourceError, match="Unknown source option"):
        parse_ref({"path": "a.csv", "enkoding": "cp1254"}, BASE)


def test_delimiter_must_be_a_single_character() -> None:
    with pytest.raises(SourceError, match="single character"):
        parse_ref({"path": "a.csv", "delimiter": ";;"}, BASE)


def test_encoding_must_be_a_string() -> None:
    with pytest.raises(SourceError, match="encoding` must be a string"):
        parse_ref({"path": "a.csv", "encoding": 1254}, BASE)


def test_options_apply_only_to_csv() -> None:
    with pytest.raises(SourceError, match="only to .csv"):
        parse_ref({"path": "report.xlsx", "encoding": "cp1254"}, BASE)


# -- reading behavior -------------------------------------------------------


def test_reads_cp1254(tmp_path: Path) -> None:
    p = tmp_path / "tr.csv"
    p.write_bytes("şehir,nüfus\nİstanbul,15840900\nİzmir,4462000\n".encode("cp1254"))
    store = SourceStore(tmp_path, {"c": {"path": "tr.csv", "encoding": "cp1254"}})
    df = store.frame("c")
    assert list(df.columns) == ["şehir", "nüfus"]
    assert df["şehir"].tolist() == ["İstanbul", "İzmir"]


def test_wrong_encoding_gives_a_helpful_error(tmp_path: Path) -> None:
    # Written cp1254, read with the utf-8-sig default: the Turkish bytes are
    # invalid UTF-8, so decoding fails — and the message should say what to do.
    p = tmp_path / "tr.csv"
    p.write_bytes("şehir\nİstanbul\n".encode("cp1254"))
    store = SourceStore(tmp_path, {"c": "tr.csv"})
    with pytest.raises(SourceError, match="cp1254"):
        store.frame("c")


def test_unknown_encoding_name(tmp_path: Path) -> None:
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    store = SourceStore(tmp_path, {"c": {"path": "x.csv", "encoding": "klingon"}})
    with pytest.raises(SourceError, match="Unknown encoding"):
        store.frame("c")


def test_semicolon_delimiter_splits_columns(tmp_path: Path) -> None:
    p = tmp_path / "s.csv"
    p.write_text("sehir;nufus\nIstanbul;15840900\n", encoding="utf-8")
    store = SourceStore(tmp_path, {"c": {"path": "s.csv", "delimiter": ";"}})
    assert list(store.frame("c").columns) == ["sehir", "nufus"]


def test_without_delimiter_semicolon_file_is_one_column(tmp_path: Path) -> None:
    # The mirror of the test above: without the delimiter option, a ;-file
    # parses as a single comma-delimited column. This is why the option exists.
    p = tmp_path / "s.csv"
    p.write_text("sehir;nufus\nIstanbul;15840900\n", encoding="utf-8")
    store = SourceStore(tmp_path, {"c": "s.csv"})
    assert list(store.frame("c").columns) == ["sehir;nufus"]


def test_bom_is_stripped_by_default(tmp_path: Path) -> None:
    # utf-8-sig write emits a BOM; the utf-8-sig default read must strip it,
    # or the first column name becomes "﻿id" and every check on it fails.
    p = tmp_path / "bom.csv"
    p.write_text("id,name\n1,a\n", encoding="utf-8-sig")
    store = SourceStore(tmp_path, {"c": "bom.csv"})
    assert list(store.frame("c").columns) == ["id", "name"]


def test_options_are_noted_in_the_honesty_block(tmp_path: Path) -> None:
    p = tmp_path / "tr.csv"
    p.write_bytes("şehir,nüfus\nİstanbul,15840900\n".encode("cp1254"))
    store = SourceStore(tmp_path, {"c": {"path": "tr.csv", "encoding": "cp1254"}})
    store.frame("c")
    assert "encoding cp1254" in store.infos()[0].detail


def test_default_read_adds_no_report_noise(tmp_path: Path) -> None:
    p = tmp_path / "plain.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    store = SourceStore(tmp_path, {"c": "plain.csv"})
    store.frame("c")
    assert store.infos()[0].detail == ""


def test_mapping_runs_end_to_end(tmp_path: Path, run_spec) -> None:  # type: ignore[no-untyped-def]
    # Through the same door a user uses: a spec with a mapping source. The
    # tmp_path fixture is the same directory run_spec binds as its base_dir.
    path = tmp_path / "sales.csv"
    with path.open("w", encoding="cp1254", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["bölge", "gelir"])
        w.writerow(["Marmara", "100"])
        w.writerow(["Ege", "200"])
    report = run_spec(
        {
            "version": 1,
            "sources": {"sales": {"path": "sales.csv", "encoding": "cp1254", "delimiter": ";"}},
            "checks": [
                {"reconcile.row_count": {"left": {"source": "sales"}, "right": {"value": 2}}}
            ],
        }
    )
    assert report.verdict == "PASS"
