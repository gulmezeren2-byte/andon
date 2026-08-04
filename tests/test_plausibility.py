from conftest import one

from andon.result import Status


def test_bounds_flags_but_never_fails(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [
                {
                    "plausibility.bounds": {
                        "source": "orders",
                        "column": "revenue",
                        "min": 0,
                        "max": 199.0,  # one order is 200.0
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.REVIEW
    assert r.evidence["above_max"] == 1
    assert report.exit_code() == 2
    assert report.exit_code(strict=True) == 1


def test_bounds_pass(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [
                {"plausibility.bounds": {"source": "orders", "column": "revenue", "min": 0}}
            ],
        }
    )
    assert one(report).status is Status.PASS


def test_new_categories_flagged(orders_csv, tmp_path, run_spec) -> None:
    (tmp_path / "new.csv").write_text("region\nEU\nLATAM\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name, "new": "new.csv"},
            "checks": [
                {
                    "plausibility.new_categories": {
                        "column": "region",
                        "left": {"source": "orders"},
                        "right": {"source": "new"},
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.REVIEW
    assert r.evidence["new_categories"] == ["LATAM"]


def test_mean_shift_flags_large_move(orders_csv, tmp_path, run_spec) -> None:
    (tmp_path / "next.csv").write_text("revenue\n5000\n5200\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name, "next": "next.csv"},
            "checks": [
                {
                    "plausibility.mean_shift": {
                        "column": "revenue",
                        "left": {"source": "orders"},
                        "right": {"source": "next"},
                        "max_sigmas": 3,
                    }
                }
            ],
        }
    )
    assert one(report).status is Status.REVIEW


# --------------------------------------------------------------------------- #
# a heuristic must never call "I could not read this" a PASS
#
# Turkish Excel writes amounts as `1.234,56` with `;` separators — the ordinary
# export in this tool's home market. Those read as text, coerce to NaN, and used to
# leave an empty series behind: zero values out of bounds, reported as PASS. A
# verification tool that prints "a PASS is arithmetic, not an opinion" under every
# report cannot be the one doing that.
# --------------------------------------------------------------------------- #
def test_bounds_does_not_pass_when_nothing_is_numeric(tmp_path, run_spec) -> None:
    (tmp_path / "tr.csv").write_text(
        "siparis;tutar\nA;1.234,56\nB;2.000,00\n", encoding="utf-8"
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"tr": {"path": "tr.csv", "delimiter": ";"}},
            # a bound nothing could satisfy: if this passes, nothing was compared
            "checks": [
                {"plausibility.bounds": {"source": "tr", "column": "tutar", "min": 999999999}}
            ],
        }
    )
    r = one(report)
    assert r.status is Status.REVIEW
    assert "nothing was compared" in r.summary
    assert r.evidence["values_checked"] == 0
    assert r.evidence["values_total"] == 2


def test_bounds_reports_the_denominator_when_only_part_is_readable(tmp_path, run_spec) -> None:
    # `n/a` is in pandas' default na_values, so it never reaches to_numeric — the old
    # coerce-delta counted it as zero skipped while silently dropping it
    (tmp_path / "half.csv").write_text("v\n10\n12\nn/a\nn/a\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"h": "half.csv"},
            "checks": [{"plausibility.bounds": {"source": "h", "column": "v", "max": 1000}}],
        }
    )
    r = one(report)
    assert r.status is Status.REVIEW  # in bounds, but only half was read
    assert (r.evidence["values_checked"], r.evidence["values_total"]) == (2, 4)
    assert r.evidence["values_skipped"] == 2
    assert "2 of 4" in r.summary


def test_mean_shift_says_when_it_averaged_only_part_of_the_column(tmp_path, run_spec) -> None:
    # a mean over the values that happened to parse is a statement about the data we
    # chose, not the data we were given
    (tmp_path / "base.csv").write_text("v\n10\n12\n", encoding="utf-8")
    (tmp_path / "new.csv").write_text("v\n10\n12\nn/a\nn/a\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"base": "base.csv", "new": "new.csv"},
            "checks": [
                {
                    "plausibility.mean_shift": {
                        "column": "v",
                        "left": {"source": "base"},
                        "right": {"source": "new"},
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.REVIEW
    assert r.evidence["candidate_values_checked"] == 2
    assert r.evidence["candidate_values_total"] == 4
    assert "2 of 4" in r.summary


def test_clean_numeric_data_still_passes_quietly(tmp_path, run_spec) -> None:
    # the fix must not turn every ordinary run into a REVIEW
    (tmp_path / "clean.csv").write_text("v\n5\n7\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"c": "clean.csv"},
            "checks": [
                {"plausibility.bounds": {"source": "c", "column": "v", "min": 0, "max": 100}}
            ],
        }
    )
    r = one(report)
    assert r.status is Status.PASS
    assert r.evidence["values_skipped"] == 0
