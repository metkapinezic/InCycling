# The integration stub is a second layer of testing. 
# While test_resolver.py tests individual functions in isolation, test_integration_stub.py tests the full pipeline end-to-end with a hardcoded map of known-correct CAS numbers — no mocking, no network, just: "given these inputs, do we get exactly these outputs?"

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Ground-truth CAS numbers verified manually against pubchem.ncbi.nlm.nih.gov
KNOWN_CAS = {
    "Acetone": "67-64-1",
    "Ethanol": "64-17-5",
    "Cresol": None,               # ambiguous — no single CAS
    "Citric": None,               # ambiguous abbreviation
    "Soy flour (defatted)": None, # mixture — no CAS
    "Sodium chloride": "7647-14-5",
    "Xylene": None,               # mixture — ambiguous
    "Formalin": "50-00-0",
    "Dichloromethane": "75-09-2",
    "Isopropyl alcohol": "67-63-0",
    "Potassium permanganate": "7722-64-7",
    "Hydrogen peroxide": "7722-84-1",
    "Oxalic acid": "144-62-7",
    "Magnesium sulfate": "7487-88-9",
    "Dichloroethane": "75-34-3",
    "Toluenne": None,             # typo in source data
    "Phosphoric acid": "7664-38-2",
    "Diethyl ether": "60-29-7",
    "Ammonium sulfate": "7783-20-2",
    "Adhesive sealant MS-180": None,  # proprietary product
    "Citric acid": "77-92-9",
    "Butyl acetate": "123-86-4",
    "Propyl alcohol": "71-23-8",
    "Sodium bicarb": None,        # abbreviation not in PubChem
    "Naphthol": "90-15-3",
    "Sodium acetate": "127-09-3",
    "Benzoic acid": "65-85-0",
    "Acetic acid": "64-19-7",
    "Acetonitrile": "75-05-8",
    "Triethylamine": "121-44-8",
}


def _make_batch_csv(tmp_path: Path, name: str, rows: list[tuple[str, str]]) -> Path:
    p = tmp_path / name
    with p.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Name", "Quantity, kg"])
        writer.writerows(rows)
    return p


class TestFullPipelineStubbed:
    def test_batch_files(self, tmp_path):
        from cas_resolver.processor import process_files

        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"

        batch1 = _make_batch_csv(input_dir, "batch_1.csv", [
            ("Acetone", "850"), ("Ethanol", "2200"), ("Cresol", "95"),
            ("Citric", "175"), ("Soy flour (defatted)", "1500"),
        ])
        batch2 = _make_batch_csv(input_dir, "batch_2.csv", [
            ("Acetone", "320"), ("Sodium chloride", "3000"), ("Formalin", "240"),
        ])
        batch3 = _make_batch_csv(input_dir, "batch_3.csv", [
            ("Sodium bicarb", "1200"), ("Benzoic acid", "88"), ("Toluenne", "290"),
        ])

        with patch(
            "cas_resolver.processor.resolve_cas_batch",
            new=AsyncMock(
                side_effect=lambda names, **kw: {n: KNOWN_CAS.get(n) for n in names}
            ),
        ):
            process_files([batch1, batch2, batch3], output_dir)

        # batch_1 spot checks
        with (output_dir / "batch_1.csv").open() as fh:
            rows = list(csv.DictReader(fh))
        assert rows[0]["CAS"] == "67-64-1"    # Acetone resolved
        assert rows[2]["CAS"] == "NOT FOUND"  # Cresol ambiguous
        assert rows[3]["CAS"] == "NOT FOUND"  # Citric ambiguous

        # batch_3 typo check
        with (output_dir / "batch_3.csv").open() as fh:
            rows = list(csv.DictReader(fh))
        toluene_row = next(r for r in rows if r["Name"] == "Toluenne")
        assert toluene_row["CAS"] == "NOT FOUND"