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
python3 -m cas_resolver --input-dir data_input/ --output-dir data_output/
```

Process specific files:
```bash
python3 -m cas_resolver data_input/batch_1.csv data_imput/batch_2.csv --output-dir data_output/
```

Add `--verbose` for detailed logs including every HTTP request:
```bash
python3 -m cas_resolver --input-dir data_input/ --output-dir data_output/ --verbose
```

## How to run the tests

```bash
python3 -m pytest tests/ -v
```

## pyproject.toml explained

`pyproject.toml` is the single configuration file for the project. It replaces the older `setup.py` and `requirements.txt` approach.

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```
Tells pip how to build the package. Required for `pip install -e .` to work.

```toml
[project]
name = "cas-resolver"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
    "httpx>=0.27",
]
```
The project identity card. `dependencies` lists what gets installed automatically when someone installs this package. `httpx` is the only runtime dependency — it's the async HTTP library used to call PubChem.

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
]
```
Dependencies only needed for development (running tests). Installed with `pip install -e ".[dev]"`. Not included when someone installs the tool just to use it.

```toml
[tool.setuptools.packages.find]
include = ["cas_resolver*"]
```
Tells setuptools to only package the `cas_resolver` folder and ignore everything else (input/output folders, tests, etc).

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```
Pytest configuration. Restricts test discovery to the `tests/` folder. `asyncio_mode = "auto"` handles async test functions automatically without extra decorators.

