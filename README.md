# InCycling
Python tool that processes each file and produces a corresponding output file, with the same filename in a different directory.

## What it does
Reads CSV files in the `data_imput` folder containing chemical names, calls the PubChem public API to resolve each name to a CAS Registry Number, and writes enriched output CSVs with the same filename to `data_output`.

Created files and what each one owns:
- cas_resolver/pubchem.py -- knows how to talk to PubChem. Async HTTP, rate limiting, retries, CAS extraction from synonyms.
- cas_resolver/processor.py -- knows how to read and write CSVs and orchestrate the pipeline. Calls pubchem.py. 
- cas_resolver/__main__.py -- the front door. Parses CLI arguments, configures logging, calls processor.py. 
- tests/test_resolver.py -- verifies all the logic works without touching the network.
- tests/test_integration.py -- tests the full pipeline end-to-end with a hardcoded map of known-correct CAS numbers


Input format:
Name,"Quantity, kg"

Output format (CAS column inserted after Name):
Name,CAS,"Quantity, kg"


Chemicals that cannot be resolved get `NOT FOUND` in the CAS column.

## Setup

Requires Python 3.9+.

```bash
pip install -e ".[dev]"
```

## How to run

Process all CSV files in a directory:
```bash
python3 -m cas_resolver --input-dir data_imput/ --output-dir data_output/
```

Process specific files:
```bash
python3 -m cas_resolver data_imput/batch_1.csv data_imput/batch_2.csv --output-dir data_output/
```

Add `--verbose` for detailed logs including every HTTP request:
```bash
python3 -m cas_resolver --input-dir data_imput/ --output-dir data_output/ --verbose
```

## How to run the tests

```bash
python3 -m pytest tests/ -v
```



