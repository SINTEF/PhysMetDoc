"""Extract prefixes from centrally maintained CSV files:

  - organisations.csv
  - people.csv
  - projects.csv

The extracted prefixes can be saved as a JSON-LD context.
"""

import argparse
import csv
import json
import warnings
from pathlib import Path
from typing import Optional

thisdir = Path(__file__).resolve().parent
default_files = [
    # "equipments.csv",  # no dedicated prefix for each equipment
    "organisations.csv",
    "people.csv",
    "projects.csv",
]


class PrefixMismatchError(ValueError):
    """Same prefix is used for two different namespaces."""


def parse(filename: Path, **spec) -> dict:
    """Parse a CSV file and return a dict with extracted prefixes.

    Args:
        filename: File to parse.
        spec: Keyword arguments to csv.reader() for specifying how `filename`
            is formatted.

    Returns:
        Dict with all prefixes extracted from `filename`.

    """
    prefixes: dict = {}
    conf = spec if spec else {}
    with open(filename, newline="", encoding="utf8") as csvfile:
        reader = csv.reader(csvfile, **conf)
        header = next(reader)
        if not "prefix" in header and not "namespace" in header:
            warnings.warn(
                f"{filename}: Missing 'prefix' or 'namespace' in header"
            )
            return {}
        iprefix = header.index("prefix")
        ins = header.index("namespace")
        for row in reader:
            prefix = row[iprefix]
            ns = row[ins]
            if prefix and ns:
                if prefix in prefixes and ns != prefixes[prefix]:
                    raise PrefixMismatchError(
                        f"duplicate definitions of prefix: {prefix}\n"
                        f"  - {prefixes[prefix]}\n"
                        f"  - {ns}"
                    )
                prefixes[prefix] = ns

    return prefixes


def write_jsonld(output: Optional[Path], prefixes: dict) -> None:
    """Write JSON-LD context.

    Args:
        output: File to write to. If None, write to stdout.
        prefixes: Dict mapping prefixes to corresponding namespaces.
    """
    context = {"@context": prefixes}
    jsonld = json.dumps(context, indent=2, sort_keys=False) + "\n"
    if output:
        with open(output, "wt", encoding="utf8") as f:
            f.write(jsonld)
    else:
        print(jsonld)


def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract prefixes from CSV files defining shared resources."
        )
    )
    parser.add_argument(
        "paths",
        metavar="PATH",
        default=["."],
        nargs="*",
        help=(
            "Directories or CSV files to parse. "
            "If no argument is given, it defaults to the current directory. "
            "If a directory is given, the following files within the "
            "directory are parsed (if they exists): "
            "organisations.csv, people.csv, projects.csv"
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="OUTPUT",
        type=Path,
        help="JSON-LD file to write. The default is to write to stdout.",
    )
    args = parser.parse_args()

    prefixes = {}

    for path in args.paths:
        abspath = Path(path).resolve()
        if abspath.is_dir():
            for filename in default_files:
                prefixes.update(parse(abspath / filename))
        else:
            prefixes.update(parse(abspath))

    write_jsonld(args.output, prefixes)


if __name__ == "__main__":
    main()
