from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import AsyncMock, patch #AsyncMock instead of regular Mock because resolve_cas_batch is an async function — you need an async-compatible mock.

import pytest

# testing private functions from resolver. Generally you don't test private functions directly — you test the public interface. But _extract_cas is pure logic with no dependencies, so testing it directly is clean and fast. It also means if it ever breaks, the test tells you exactly where. 

from cas_resolver.pubchem import _extract_cas, _CAS_PATTERN
from cas_resolver.processor import (  
    _build_output_fieldnames,
    _read_csv,
    _write_csv,
    NOT_FOUND_SENTINEL,
    NAME_COLUMN,
    CAS_COLUMN,
)

# CAS pattern tests #

# Each test has one job. When it fails, you know exactly what broke. One big test that checks everything tells you something broke but not what. This is a principle called "one assertion per test" — not always strictly followed but a good default.

class TestCasPattern:
    def test_valid_short(self):
        assert _CAS_PATTERN.match("67-64-1")

    def test_valid_long(self):
        assert _CAS_PATTERN.match("1336-21-6")

    def test_valid_seven_digits(self):
        assert _CAS_PATTERN.match("1234567-89-0")

    def test_invalid_no_dashes(self):
        assert not _CAS_PATTERN.match("67641")

    def test_invalid_wrong_check_digit_length(self):
        assert not _CAS_PATTERN.match("67-64-12")

    def test_invalid_letters(self):
        assert not _CAS_PATTERN.match("AB-64-1")


class TestExtractCas:
    def test_picks_first_cas_from_synonyms(self):
        synonyms = ["Acetone", "Propan-2-one", "67-64-1", "67-64-1"]
        assert _extract_cas(synonyms) == "67-64-1"

    def test_returns_none_when_no_cas(self):
        assert _extract_cas(["Acetone", "Propanone", "CHEBI:15347"]) is None

    def test_strips_whitespace(self):
        assert _extract_cas(["  67-64-1  "]) == "67-64-1"

    def test_empty_list(self):
        assert _extract_cas([]) is None


# CSV helper tests #
 # tmp_path It's a pytest built-in fixture — pytest automatically creates a temporary folder for each test and deletes it afterwards. You never have to create or clean up test files manually. Any function parameter named tmp_path gets this automatically.

def _make_csv_file(tmp_path: Path, rows: list[list[str]]) -> Path:
    p = tmp_path / "test.csv"
    with p.open("w", newline="") as fh:
        writer = csv.writer(fh)
        for row in rows:
            writer.writerow(row)
    return p


class TestReadCsv:
    def test_reads_rows_and_fieldnames(self, tmp_path):
        p = _make_csv_file(tmp_path, [["Name", "Qty"], ["Acetone", "100"]])
        fieldnames, rows = _read_csv(p)
        assert fieldnames == ["Name", "Qty"]
        assert rows[0]["Name"] == "Acetone"

    def test_raises_on_missing_name_column(self, tmp_path):
        p = _make_csv_file(tmp_path, [["Chemical", "Qty"], ["Acetone", "100"]])
        with pytest.raises(ValueError, match="'Name' column"):
            _read_csv(p)


class TestBuildOutputFieldnames:
    def test_inserts_cas_after_name(self):
        result = _build_output_fieldnames(["Name", "Qty"])
        assert result == ["Name", "CAS", "Qty"]

    def test_single_column(self):
        result = _build_output_fieldnames(["Name"])
        assert result == ["Name", "CAS"]


class TestWriteCsv:
    def test_writes_resolved_cas(self, tmp_path):
        rows = [{"Name": "Acetone", "Qty": "100"}]
        cas_map = {"Acetone": "67-64-1"}
        out = tmp_path / "out.csv"
        _write_csv(out, ["Name", "CAS", "Qty"], rows, cas_map)

        with out.open() as fh:
            reader = csv.DictReader(fh)
            result = list(reader)
        assert result[0]["CAS"] == "67-64-1"

    def test_writes_sentinel_on_missing(self, tmp_path):
        rows = [{"Name": "UnknownChem", "Qty": "10"}]
        cas_map = {"UnknownChem": None}
        out = tmp_path / "out.csv"
        _write_csv(out, ["Name", "CAS", "Qty"], rows, cas_map)

        with out.open() as fh:
            reader = csv.DictReader(fh)
            result = list(reader)
        assert result[0]["CAS"] == NOT_FOUND_SENTINEL



# integration test that mocks the whole pipeline #

class TestProcessFile:
    def test_end_to_end(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"

        csv_path = _make_csv_file(
            input_dir,
            [["Name", "Qty"], ["Acetone", "100"], ["Ethanol", "200"]],
        )

        mock_cas = {"Acetone": "67-64-1", "Ethanol": "64-17-5"}

        with patch(         # patch temporarily replaces a real function with a fake one during a test. Here we replace resolve_cas_batch — the function that calls PubChem — with AsyncMock(return_value=mock_cas). This means the test never touches the internet. It's fast, reliable, and works offline.
            "cas_resolver.processor.resolve_cas_batch",
            new=AsyncMock(return_value=mock_cas),  # AsyncMock instead of regular Mock because resolve_cas_batch is an async function — you need an async-compatible mock.
        ):
            from cas_resolver.processor import process_file
            out = process_file(csv_path, output_dir)

        assert out.exists()
        with out.open() as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        assert rows[0]["CAS"] == "67-64-1"
        assert rows[1]["CAS"] == "64-17-5"
        assert list(rows[0].keys()) == ["Name", "CAS", "Qty"]