"""OO-LD Converter module for translating between CSV and JSON Schema."""

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

# Configure package-level logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("oold.converter")

# Global schemas and contexts
CONTEXT_URL = (
    "https://raw.githubusercontent.com/SINTEF/"
    "physmet-data-documentation-templates/refs/heads/main/context/context.json"
)
META_SCHEMA = "https://oo-ld.org/latest/meta/oold-meta-schema.json"

# Strict regex for a valid JSON number (RFC 8259)
# Excludes NaN, Inf, -Inf, etc.
JSON_NUMBER_PATTERN = re.compile(
    r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$"
)


IRI_PATTERN = r"^([A-Za-z][A-Za-z0-9\-_]*:)?[A-Za-z0-9][A-Za-z0-9\-_]*$"
HARDCODED_PROPERTIES = ("@id", "@type")


def _iri_property(description: str) -> dict[str, Any]:
    """Builds the shared JSON Schema shape used for the @id and @type
    properties."""
    return {
        "anyOf": [
            {"type": "string", "format": "uri"},
            {"type": "string", "pattern": IRI_PATTERN},
        ],
        "description": description,
    }


class ConversionError(Exception):
    """Error raised when conversion between formats fails."""


def infer_type(values: list[str | None]) -> str:
    """
    Infers the JSON schema data type based on a list of string values.
    Strictly validates numbers against JSON specifications, rejecting NaN/Inf.
    Always returns a bare string type (e.g., "number", "string", "boolean").

    Args:
        values (List[Optional[str]]): The column values extracted from the CSV.

    Returns:
        str: The inferred type as a plain string.
    """
    non_nulls = [
        v.strip() for v in values if v is not None and v.strip() != ""
    ]

    if not non_nulls:
        return "string"
    if all(v.lower() in ("true", "false") for v in non_nulls):
        return "boolean"
    if all(JSON_NUMBER_PATTERN.match(v) for v in non_nulls):
        return "number"

    return "string"


def _build_base_schema(file_stem: str, base_url: str | None) -> dict[str, Any]:
    """Constructs the baseline JSON Schema dictionary structure."""
    schema_filename = f"{file_stem}.schema.json"
    schema_id = (
        f"{base_url.rstrip('/')}/{schema_filename}"
        if base_url
        else schema_filename
    )

    return {
        "$schema": META_SCHEMA,
        "$id": schema_id,
        "@context": CONTEXT_URL,
        "title": file_stem,
        "type": "object",
        "properties": {
            "@id": _iri_property(
                "Unique IRI identifying the documented resource."
            ),
            "@type": _iri_property(
                "IRI of the class the resource belongs to."
            ),
        },
        "required": ["@id", "@type"],
    }


def _process_csv_headers(
    headers: list[str],
    rows: list[dict[str, Any]],
    properties_mapping: dict[str, Any] | None,
    schema: dict[str, Any],
) -> None:
    """Processes CSV headers to define JSON Schema properties and fields."""
    for header in headers:
        if header in HARDCODED_PROPERTIES:
            schema["properties"][header]["examples"] = []
            continue

        column_values = [row.get(header) for row in rows]
        inferred_type = infer_type(column_values)

        prop_def: dict[str, Any] = {
            "type": inferred_type,
            "description": "",
            "examples": [],
        }

        mapping = (
            properties_mapping.get(header) if properties_mapping else None
        )
        if isinstance(mapping, dict):
            if "description" in mapping:
                prop_def["description"] = mapping["description"]
            if mapping.get("conformance") == "mandatory":
                schema["required"].append(header)

        schema["properties"][header] = prop_def


def _add_examples_from_first_row(
    schema: dict[str, Any], headers: list[str], first_row: dict[str, Any]
) -> None:
    """Extracts the first row of data to serve as JSON Schema examples."""
    if first_row:
        for header in headers:
            val = first_row.get(header)
            stripped = val.strip() if val is not None else None
            schema["properties"][header]["examples"].append(stripped or None)
    else:
        for header in headers:
            if "examples" in schema["properties"][header]:
                del schema["properties"][header]["examples"]


def csv_to_json_schema(
    input_file: Path,
    output_folder: Path,
    base_url: str | None = None,
    properties_mapping: dict[str, Any] | None = None,
) -> None:
    """Reads a CSV file and generates an OO-LD JSON Schema.

    Infers the type dynamically from the column data. Extract only
    `description` and `conformance` from the properties mapping. `@id`
    and `@type` are unconditionally hardcoded as mandatory
    fields. Extracts only the first row of examples from the CSV.  The
    resulting schema's title, filename, and `$id` fields are
    capitalized.

    Args:
        input_file (Path): Path to the input CSV file.
        output_folder (Path): Directory where the JSON schema will be saved.
        base_url (Optional[str]): A URL to prepend to the `$id` to create a
            valid IRI.
        properties_mapping (Optional[Dict[str, Any]]): Dictionary mapping
            column headers to their OO-LD metadata definitions.

    Raises:
        FileNotFoundError: If the input CSV file does not exist.
        ConversionError: If parsing the CSV or writing the JSON file fails.

    """
    if not input_file.exists() or not input_file.is_file():
        logger.error("Input file not found: %s", input_file)
        raise FileNotFoundError(
            f"The specified input CSV file does not exist: {input_file}"
        )

    file_stem = input_file.stem[0].upper() + input_file.stem[1:]
    schema = _build_base_schema(file_stem, base_url)

    logger.info("Reading CSV file: %s", input_file)

    try:
        with open(input_file, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            headers = list(reader.fieldnames) if reader.fieldnames else []
            rows = list(reader)

            if not headers:
                logger.warning(
                    "The CSV file '%s' is empty or missing headers.",
                    input_file,
                )

            _process_csv_headers(headers, rows, properties_mapping, schema)
            _add_examples_from_first_row(
                schema, headers, rows[0] if rows else {}
            )

    except csv.Error as e:
        logger.error("Error parsing the CSV file %s: %s", input_file, e)
        raise ConversionError(f"Failed to parse CSV: {e}") from e
    except OSError as e:
        logger.error("OS Error while reading %s: %s", input_file, e)
        raise ConversionError(f"Failed to read CSV: {e}") from e

    output_path = output_folder / f"{file_stem}.schema.json"

    try:
        output_folder.mkdir(parents=True, exist_ok=True)
        with open(output_path, mode="w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")
        logger.info("Successfully created JSON Schema at: %s", output_path)
    except OSError as e:
        logger.error(
            "Filesystem error while writing to %s: %s", output_folder, e
        )
        raise ConversionError(f"Failed to write JSON: {e}") from e


def _write_csv_reconstruction(
    output_path: Path, headers: list[str], properties: dict[str, Any]
) -> None:
    """Calculates max examples rows and outputs the reconstructed CSV."""
    max_rows = 0
    for prop in properties.values():
        examples = prop.get("examples")
        if isinstance(examples, list):
            max_rows = max(max_rows, len(examples))

    with open(output_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for i in range(max_rows):
            row = {}
            for header in headers:
                examples = properties[header].get("examples")
                if isinstance(examples, list) and i < len(examples):
                    val = examples[i]
                    row[header] = val if val is not None else ""
                else:
                    row[header] = ""
            writer.writerow(row)


def json_schema_to_csv(input_file: Path, output_folder: Path) -> None:
    """Reads an OO-LD JSON Schema and rebuilds a CSV file using its aligned
    array examples.


    Restores the original lines by reading the examples arrays index
    by index.  Null values or missing array indices are converted back
    to empty string cells. The resulting CSV file name will always be
    entirely lowercase.

    Args:
        input_file (Path): Path to the input JSON schema file.
        output_folder (Path): Directory where the CSV will be saved.

    Raises:
        FileNotFoundError: If the input JSON file does not exist.
        ValueError: If the JSON document lacks a 'properties' key.
        ConversionError: If parsing the JSON or writing the CSV file fails.

    """
    if not input_file.exists() or not input_file.is_file():
        logger.error("Input file not found: %s", input_file)
        raise FileNotFoundError(
            f"The specified input JSON file does not exist: {input_file}"
        )

    filename_str = input_file.name
    if filename_str.endswith(".schema.json"):
        file_stem = filename_str.replace(".schema.json", "")
    else:
        file_stem = input_file.stem

    file_stem = file_stem[0].lower() + file_stem[1:]

    logger.info("Reading JSON Schema file: %s", input_file)

    try:
        with open(input_file, encoding="utf-8") as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        logger.error("Failed to decode JSON from %s: %s", input_file, e)
        raise ConversionError(f"Failed to decode JSON: {e}") from e
    except OSError as e:
        logger.error("OS error reading JSON file %s: %s", input_file, e)
        raise ConversionError(f"Failed to read JSON: {e}") from e

    if "properties" not in schema:
        error_msg = (
            f"Invalid OO-LD Schema: '{input_file}' is missing the "
            "'properties' key."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    properties = schema["properties"]
    output_path = output_folder / f"{file_stem}.csv"

    try:
        output_folder.mkdir(parents=True, exist_ok=True)
        _write_csv_reconstruction(
            output_path, list(properties.keys()), properties
        )
        logger.info("Successfully created CSV at: %s", output_path)
    except OSError as e:
        logger.error(
            "Filesystem error while writing to %s: %s", output_folder, e
        )
        raise ConversionError(f"Failed to write CSV: {e}") from e
    except csv.Error as e:
        logger.error("Error writing to the CSV file %s: %s", output_path, e)
        raise ConversionError(f"Failed to write CSV fields: {e}") from e


def process_path(
    input_path: str | Path,
    output_folder: str | Path,
    mode: str,
    **kwargs: Any,
) -> None:
    """Processes a single file or a directory of files based on the specified
    mode.

    The function validates the input path and gathers all applicable
    files for conversion.  It iterates through the target files,
    bypassing any filenames explicitly provided in the exclusion
    list. Depending on the selected mode, it routes valid `.csv` files
    to the JSON Schema generator, or `.json` files to the CSV
    builder. Unsupported file formats are safely ignored (logging a
    warning if a single unsupported file was targeted directly), and a
    final summary log details the total number of successfully
    processed files.

    Args:
        input_path (Union[str, Path]): The path to the input file or directory.
        output_folder (Union[str, Path]): The directory where the output files
            should be saved.
        mode (str): The conversion mode ('csv2json' or 'json2csv').
        base_url (Optional[str]): A base URL for valid IRI generation (csv2json
            only).
        properties_mapping (Optional[Dict[str, Any]]): Dictionary mapping for
            OO-LD properties injection (csv2json only).
        exclude_files (Optional[List[str]]): A list of specific filenames to
            skip during processing.

    Raises:
        FileNotFoundError: If the specified input path does not exist.

    """
    path = Path(input_path)
    out_folder = Path(output_folder)

    base_url = kwargs.get("base_url")
    properties_mapping = kwargs.get("properties_mapping")
    exclude_files = kwargs.get("exclude_files")

    if not path.exists():
        logger.error("Input path not found: %s", input_path)
        raise FileNotFoundError(
            f"The specified input path does not exist: {input_path}"
        )

    files_to_process = (
        [path]
        if path.is_file()
        else [p for p in path.iterdir() if p.is_file()]
    )
    processed_count = 0

    for current_path in files_to_process:
        ext = current_path.suffix.lower()

        if exclude_files and current_path.name in exclude_files:
            logger.info("Skipping excluded file: %s", current_path.name)
            continue

        if mode == "csv2json" and ext == ".csv":
            csv_to_json_schema(
                current_path, out_folder, base_url, properties_mapping
            )
            processed_count += 1
        elif mode == "json2csv" and ext == ".json":
            json_schema_to_csv(current_path, out_folder)
            processed_count += 1
        else:
            if current_path.is_file():
                logger.warning(
                    "File '%s' unsupported for mode '%s'. Skipped.",
                    current_path.name,
                    mode,
                )

    if processed_count == 0:
        logger.warning(
            "No files were processed. Ensure the input contains files "
            "matching mode '%s'.",
            mode,
        )
    else:
        logger.info("Finished processing %d file(s).", processed_count)


def main() -> None:
    """
    Main CLI entry point for the OOLD converter.

    Parses arguments from the command line and executes the conversion process.
    """
    parser = argparse.ArgumentParser(
        description="Convert between CSV data and OO-LD JSON Schemas."
    )
    parser.add_argument(
        "input_path",
        help=(
            "The path to the input file (CSV/JSON) or directory containing "
            "them."
        ),
    )
    parser.add_argument(
        "output_folder",
        help="The directory where the output files should be saved.",
    )
    parser.add_argument(
        "--mode",
        choices=["json2csv", "csv2json"],
        default="json2csv",
        help="Direction of the conversion. Defaults to 'json2csv'.",
    )
    parser.add_argument(
        "--base-url",
        help="Base URL to prepend to the $id field to create a valid IRI.",
    )
    parser.add_argument(
        "--mappings",
        help=(
            "Path to a JSON file containing property mappings (e.g., "
            "description, range, conformance)."
        ),
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help=(
            "Specific filenames to exclude from processing (e.g. --exclude "
            "'skip.csv' 'ignore.json')."
        ),
    )

    args = parser.parse_args()

    properties_mapping = None
    if args.mappings:
        try:
            with open(args.mappings, encoding="utf-8") as f:
                properties_mapping = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(
                "Failed to load properties mapping from %s: %s",
                args.mappings,
                e,
            )
            sys.exit(1)

    try:
        process_path(
            args.input_path,
            args.output_folder,
            args.mode,
            base_url=args.base_url,
            properties_mapping=properties_mapping,
            exclude_files=args.exclude,
        )
    except (FileNotFoundError, ValueError, ConversionError) as e:
        logger.critical("Process failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
