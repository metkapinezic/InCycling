## CSV reading/writing logic ##
# Its only job is: read a CSV, call the API, write the enriched CSV.#

from __future__ import annotations

import asyncio
import csv
import logging
from pathlib import Path
from typing import Optional

from cas_resolver.pubchem import resolve_cas_batch

logger = logging.getLogger(__name__)

NAME_COLUMN = "Name"
CAS_COLUMN = "CAS"
NOT_FOUND_SENTINEL = "NOT FOUND"


# helper function to read a CSV and return a list of names#

def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    """Return (fieldnames, rows) from a CSV file."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh) # why csv.DictReader and not just csv.reader? because we want to access columns by name, not by index. csv.reader gives you rows as plain lists — ["Acetone", "850"]. You'd have to remember that index 0 is the name and index 1 is the quantity. csv.DictReader gives you rows as dictionaries — {"Name": "Acetone", "Quantity, kg": "850"}. This is more readable and robust to changes in column order.
        if reader.fieldnames is None:
            raise ValueError(f"Empty or header-less CSV: {path}")
        if NAME_COLUMN not in reader.fieldnames:
            raise ValueError(
                f"Expected a '{NAME_COLUMN}' column in {path.name}, " # Why validate the Name column exists? Fail fast with a clear message rather than crash later with a confusing KeyError. This is a principle called defensive programming — check your assumptions at the boundary where data enters your system.
                f"found: {list(reader.fieldnames)}"
            )
        return list(reader.fieldnames), list(reader)
    
# column builder #
# This takes ["Name", "Quantity, kg"] and returns ["Name", "CAS", "Quantity, kg"]. We insert CAS right after Name so the output is readable — the identifier sits next to the name it belongs to.

def _build_output_fieldnames(input_fieldnames: list[str]) -> list[str]:
    """Insert CAS column right after Name."""
    idx = input_fieldnames.index(NAME_COLUMN)
    return (
        input_fieldnames[: idx + 1]
        + [CAS_COLUMN]
        + input_fieldnames[idx + 1 :]
    )

# writing function #

def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict],
    cas_map: dict[str, Optional[str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True) # If the output directory doesn't exist yet, this creates it automatically. exist_ok=True means it won't crash if it already exists. Without this, writing to output/batch_1.csv would fail if output/ doesn't exist yet.
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            name = row[NAME_COLUMN]
            cas = cas_map.get(name)
            writer.writerow(
                {**row, CAS_COLUMN: cas if cas is not None else NOT_FOUND_SENTINEL} # This is dictionary unpacking. **row spreads all existing key-value pairs into a new dict, then we add the CAS key on top. It's a clean one-liner way to create a new dict that's a copy of row with one extra field added.
            )

# functions that tie everything together #

def process_file(input_path: Path, output_dir: Path) -> Path:
    """
    Process a single CSV file: resolve CAS numbers and write enriched output.
    """
    logger.info("Processing %s", input_path.name)

    fieldnames, rows = _read_csv(input_path)
    names = [row[NAME_COLUMN] for row in rows]
    unique_names = list(dict.fromkeys(names))   # deduplicate, preserve order but only on a file level - we don't want to waste API calls on duplicate names within the same file. We use dict.fromkeys() because it's a neat Python trick to deduplicate while preserving order. 
                                                # The deduplication never sees across file boundaries because each process_file call creates its own fresh names list and its own fresh cas_map. They have no shared memory.
    logger.info("  Resolving %d unique chemical name(s) via PubChem...", len(unique_names))
    cas_map = asyncio.run(resolve_cas_batch(unique_names)) # resolve_cas_batch is an async function. But process_file is a normal synchronous function. asyncio.run() is the bridge — it starts an event loop, runs the async function to completion, and returns the result back to synchronous code.

    resolved = sum(1 for v in cas_map.values() if v is not None)
    logger.info("  Resolved %d / %d names", resolved, len(unique_names))
    for name, cas in cas_map.items():
        if cas is None:
            logger.warning("  Could not resolve CAS for: %r", name)

    output_fieldnames = _build_output_fieldnames(fieldnames)
    output_path = output_dir / input_path.name
    _write_csv(output_path, output_fieldnames, rows, cas_map)

    logger.info("  Written → %s", output_path)
    return output_path


def process_files(input_paths: list[Path], output_dir: Path) -> list[Path]:
    """Process multiple CSV files sequentially."""
    return [process_file(p, output_dir) for p in input_paths]

# sequential processing is simpler and more robust for a small number of files. 
# on scale, you'd want to process files in parallel too, but that adds complexity around managing multiple event loops and ensuring we don't exceed API rate limits across all concurrent tasks. For 3 files, sequential is just fine.