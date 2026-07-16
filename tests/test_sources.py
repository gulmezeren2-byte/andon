from pathlib import Path

import pytest

from andon.errors import SourceError
from andon.sources import SourceStore, parse_ref

BASE = Path(".")


def test_parse_plain_csv() -> None:
    ref = parse_ref("data/orders.csv", BASE)
    assert ref.path == BASE / "data/orders.csv"
    assert ref.sheet is None and ref.cell_range is None


def test_parse_sheet_and_range() -> None:
    ref = parse_ref("out/report.xlsx#Summary!A1:D50", BASE)
    assert ref.sheet == "Summary"
    assert ref.cell_range == "A1:D50"


def test_hash_after_csv_is_part_of_the_filename() -> None:
    # '#' introduces a sheet only after an Excel path. Everywhere else it is a
    # legal filename character, so this parses as a file called
    # "orders.csv#Sheet1", not as a sheet reference on a CSV.
    ref = parse_ref("data/orders.csv#Sheet1", BASE)
    assert ref.path == BASE / "data/orders.csv#Sheet1"
    assert ref.sheet is None and ref.cell_range is None


def test_unknown_alias_lists_declared_sources(orders_csv: Path) -> None:
    store = SourceStore(orders_csv.parent, {"orders": orders_csv.name})
    with pytest.raises(SourceError, match="Declared sources: orders"):
        store.frame("oders")


def test_where_filter_error_lists_columns(orders_csv: Path) -> None:
    store = SourceStore(orders_csv.parent, {"orders": orders_csv.name})
    with pytest.raises(SourceError, match="order_id"):
        store.frame("orders", where="statuz == 'shipped'")


def test_headers_are_stripped(tmp_path: Path) -> None:
    p = tmp_path / "ws.csv"
    p.write_text("id , name \n1,a\n", encoding="utf-8")
    store = SourceStore(tmp_path, {"ws": "ws.csv"})
    assert list(store.frame("ws").columns) == ["id", "name"]


def test_excel_range_frame(workbook_factory) -> None:
    path = workbook_factory(
        "r.xlsx",
        {"S": {"B2": "region", "C2": "revenue", "B3": "EU", "C3": 10, "B4": "US", "C4": 20}},
    )
    store = SourceStore(path.parent, {"r": f"{path.name}#S!B2:C4"})
    df = store.frame("r")
    assert list(df.columns) == ["region", "revenue"]
    assert df["revenue"].sum() == 30


def test_missing_sheet_lists_sheets(workbook_factory) -> None:
    path = workbook_factory("r.xlsx", {"Summary": {"A1": 1}})
    store = SourceStore(path.parent, {"r": f"{path.name}#Nope"})
    with pytest.raises(SourceError, match="Sheets: Summary"):
        store.cell("r", "A1")


def test_uncalculated_formula_cell_refuses_to_guess(workbook_factory) -> None:
    path = workbook_factory("f.xlsx", {"S": {"A1": 5, "A2": "=A1*2"}})
    store = SourceStore(path.parent, {"f": f"{path.name}#S"})
    with pytest.raises(SourceError, match="never recalculated"):
        store.cell("f", "A2")


def test_text_in_numeric_range_is_an_error(workbook_factory) -> None:
    path = workbook_factory("t.xlsx", {"S": {"B1": 10, "B2": "oops", "B3": 30}})
    store = SourceStore(path.parent, {"t": f"{path.name}#S"})
    with pytest.raises(SourceError, match="does not coerce text"):
        store.values("t", "B1:B3")


def test_values_skips_blanks_and_reports_them(workbook_factory) -> None:
    path = workbook_factory("b.xlsx", {"S": {"B1": 10, "B3": 30}})
    store = SourceStore(path.parent, {"b": f"{path.name}#S"})
    numbers, blanks = store.values("b", "B1:B3")
    assert numbers == [10.0, 30.0]
    assert blanks == 1


def test_side_with_unknown_key_rejected(orders_csv: Path) -> None:
    store = SourceStore(orders_csv.parent, {"orders": orders_csv.name})
    with pytest.raises(SourceError, match="unknown key"):
        store.resolve_side({"source": "orders", "were": "x == 1"}, context="test")


def test_unreferenced_sheets_are_reported(workbook_factory) -> None:
    path = workbook_factory("m.xlsx", {"Used": {"A1": 1}, "Ignored": {"A1": 2}})
    store = SourceStore(path.parent, {"m": f"{path.name}#Used"})
    store.cell("m", "A1")
    assert store.unreferenced_sheets() == [f"{path.name}#Ignored"]
