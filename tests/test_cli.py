import json
from pathlib import Path

from conftest import ORDERS_CSV
from typer.testing import CliRunner

from andon.cli import app

runner = CliRunner()


def write_spec(tmp_path: Path, body: str) -> Path:
    spec = tmp_path / "andon.yaml"
    spec.write_text(body, encoding="utf-8")
    return spec


def passing_spec(tmp_path: Path) -> Path:
    (tmp_path / "orders.csv").write_text(ORDERS_CSV, encoding="utf-8")
    return write_spec(
        tmp_path,
        "version: 1\n"
        "sources: {orders: orders.csv}\n"
        "checks:\n"
        "  - name: ids unique\n"
        "    schema.unique: {source: orders, column: order_id}\n",
    )


def failing_spec(tmp_path: Path) -> Path:
    (tmp_path / "orders.csv").write_text(ORDERS_CSV, encoding="utf-8")
    return write_spec(
        tmp_path,
        "version: 1\n"
        "sources: {orders: orders.csv}\n"
        "checks:\n"
        "  - name: impossible count\n"
        "    reconcile.row_count:\n"
        "      left: {source: orders}\n"
        "      right: {value: 999}\n",
    )


def test_run_pass_exits_zero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(passing_spec(tmp_path))])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_run_fail_exits_one_and_names_the_check(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(failing_spec(tmp_path))])
    assert result.exit_code == 1
    assert "STOP THE LINE" in result.output
    assert "impossible count" in result.output


def test_run_json_is_machine_readable(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(failing_spec(tmp_path)), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["verdict"] == "FAIL"
    assert payload["checks"][0]["evidence"]["left_count"] == 6


def test_run_writes_markdown(tmp_path: Path) -> None:
    md = tmp_path / "report.md"
    result = runner.invoke(app, ["run", str(failing_spec(tmp_path)), "--md", str(md)])
    assert result.exit_code == 1
    assert "## andon — FAIL" in md.read_text(encoding="utf-8")


def test_broken_spec_exits_four(tmp_path: Path) -> None:
    spec = write_spec(tmp_path, "version: 1\nsources: {}\nchecks:\n  - no.such_check: {}\n")
    result = runner.invoke(app, ["run", str(spec)])
    assert result.exit_code == 4


def test_init_writes_starter_and_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "andon.yaml"
    assert runner.invoke(app, ["init", str(target)]).exit_code == 0
    assert "version: 1" in target.read_text(encoding="utf-8")
    assert runner.invoke(app, ["init", str(target)]).exit_code == 4
    assert runner.invoke(app, ["init", str(target), "--force"]).exit_code == 0


def test_inspect_clean_workbook(tmp_path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    wb.active["A1"] = 1
    path = tmp_path / "clean.xlsx"
    wb.save(path)
    result = runner.invoke(app, ["inspect", str(path)])
    assert result.exit_code == 0


def test_inspect_missing_file_exits_four(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", str(tmp_path / "nope.xlsx")])
    assert result.exit_code == 4


def test_version_flag(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "andon" in result.output
