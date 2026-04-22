## the CLI entry point for the cas_resolver package ##

from __future__ import annotations

import argparse #  the standard library for building CLIs. It automatically generates a --help message, validates types, and handles missing arguments. You never parse sys.argv manually.
import logging
import sys
from pathlib import Path

from cas_resolver.processor import process_files


def _configure_logging(verbose: bool) -> None: # sets up the logging system for the whole program. Without this, all those logger.info(...) calls in your other files would silently do nothing. verbose mode switches from INFO to DEBUG, which shows the raw HTTP connection details — useful when something is broken.
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich chemical batch CSV files with CAS Registry Numbers via PubChem."
    )
    # 2 ways to specify imput: --input-dir and file 
    parser.add_argument(
        "--input-dir", # processes a whole folder
        type=Path, # tells argparse to automatically convert the string the user types into a Path object. So by the time it reaches your code, you already have a proper Path, not a raw string.
        metavar="DIR",
        help="Directory containing input CSV files (all *.csv files will be processed).",
    )
    parser.add_argument(
        "files", # lets you name specific files.
        nargs="*", # means "zero or more". Combined with our manual validation, this lets us give a helpful error message if neither input method is provided.
        type=Path,
        metavar="FILE",
        help="One or more specific CSV files to process.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        metavar="DIR",
        help="Directory for output files (default: ./output).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()
    if not args.input_dir and not args.files:
        parser.error("Provide either --input-dir or one or more FILE arguments.")
    return args


def main() -> None:
    args = _parse_args()
    _configure_logging(args.verbose)
    logger = logging.getLogger(__name__)

    if args.input_dir:
        input_paths = sorted(args.input_dir.glob("*.csv"))
        if not input_paths:
            logger.error("No CSV files found in %s", args.input_dir)
            sys.exit(1) # exit with a non-zero code signals failure to whatever called this program (a shell script, a CI pipeline, etc). sys.exit(0) or just finishing normally signals success. This is a Unix convention every production tool follows.
    else:
        input_paths = args.files
        missing = [p for p in input_paths if not p.exists()]
        if missing:
            logger.error("File(s) not found: %s", ", ".join(str(p) for p in missing))
            sys.exit(1)

    logger.info("Processing %d file(s) → output dir: %s", len(input_paths), args.output_dir)

    try:
        written = process_files(input_paths, args.output_dir)
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        sys.exit(1)

    logger.info("Done. %d file(s) written.", len(written))


if __name__ == "__main__": # this means "only run main() if this file is executed directly". It prevents main() from running if someone imports this file. Though with python -m cas_resolver this block is actually what gets triggered — Python sets __name__ to "__main__" when running a module with -m.
    main()
