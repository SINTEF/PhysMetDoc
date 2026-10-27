"""Unit tests for the OO-LD converter module."""

import csv
import json
import logging
import tempfile
from io import StringIO
from pathlib import Path
from typing import List, Optional

import jsonschema
import pytest
import requests
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from oold_converter import (
    CONTEXT_URL,
    META_SCHEMA,
    ConversionError,
    csv_to_json_schema,
    infer_type,
    json_schema_to_csv,
    process_path,
)

# --- Global Test Environment Setup ---

DATA_DIR = Path(__file__).parent / "data" / "oold_converter"

# Create a root temporary directory for the session
# pylint: disable=consider-using-with
_SESSION_TMP_DIR = tempfile.TemporaryDirectory()
TMP_ROOT = Path(_SESSION_TMP_DIR.name)

# Cache the registry so we only download it once using a mutable list wrapper
_REGISTRY_CACHE: list = []


def get_schema_registry():
    """
    Creates a referencing Registry that explicitly allows fetching remote
    schemas.

    Safely prevents the jsonschema DeprecationWarning about auto-fetching URLs.
    """
    if _REGISTRY_CACHE:
        return _REGISTRY_CACHE[0]

    def retrieve_schema(uri):
        response = requests.get(uri, timeout=10)
        response.raise_for_status()
        return Resource.from_contents(response.json())

    try:
        oold_meta = retrieve_schema(META_SCHEMA)
        registry = Registry(retrieve=retrieve_schema).with_resource(
            META_SCHEMA, oold_meta
        )
        _REGISTRY_CACHE.append(registry)
        return registry
    except requests.exceptions.RequestException as e:
        logger = logging.getLogger("oold.converter")
        logger.warning("Could not reach the OO-LD meta-schema: %s", e)
        return None


def get_test_tmp_path(test_name: str) -> Path:
    """Creates an isolated temporary directory for a specific test."""
    p = TMP_ROOT / test_name
    p.mkdir(exist_ok=True)
    return p


# --- Tests for type inference ---


def test_infer_type():
    """Type inference always returns a bare string type without 'null'."""
    cases = [
        ([], "string"),
        ([None, "", "  "], "string"),
        (["true", "False", None], "boolean"),
        (["1", "2", "true"], "string"),
        (["1", None, "2.5", "-3.1e2"], "number"),
        (["NaN", "Infinity", "-Infinity"], "string"),
    ]
    for raw_values, expected in cases:
        # Re-cast to bypass Pylance's invariance rule for test cases
        values: List[Optional[str]] = list(raw_values)
        assert infer_type(values) == expected


def test_infer_type_blank_entries_dont_affect_type():
    """A blank/empty entry among otherwise-consistent booleans or numbers
    should not affect type inference."""
    cases = [
        (["true", "", "false"], "boolean"),
        (["1", "", "2.5"], "number"),
    ]
    for raw_values, expected in cases:
        values: List[Optional[str]] = list(raw_values)
        assert infer_type(values) == expected


# --- Tests for CSV to JSON Schema ---


def test_csv_to_json_schema_content():
    """Tests if the CSV parsing extracts only the first row for examples and
    hardcodes @id and @type."""
    tmp_path = get_test_tmp_path("csv_to_json_schema_content")
    input_csv = DATA_DIR / "test_input.csv"

    csv_to_json_schema(input_csv, tmp_path)

    output_file = tmp_path / "Test_input.schema.json"
    assert output_file.exists(), "The JSON schema was not created."

    with open(output_file, "r", encoding="utf-8") as f:
        schema = json.load(f)

    assert schema["$id"] == "Test_input.schema.json"
    assert schema["title"] == "Test_input"

    assert "@id" in schema["properties"]
    assert "@type" in schema["properties"]
    assert "@id" in schema["required"]
    assert "@type" in schema["required"]

    assert len(schema["properties"]["@type"]["anyOf"]) == 2

    # Asserting plain string types
    assert schema["properties"]["title"]["type"] == "string"
    assert schema["properties"]["title"]["examples"] == ["Sample 1"]
    assert schema["properties"]["@id"]["examples"] == ["id:1"]
    assert "examples" not in schema["properties"]["@type"]


def test_csv_to_json_schema_type_inference():
    """Tests if type inference dynamically resolves numbers, booleans, and
    strings."""
    tmp_path = get_test_tmp_path("csv_to_json_schema_type_inference")
    input_csv = tmp_path / "inference_test.csv"
    input_csv.write_text(
        "id,count,is_active,name\n1,42,true,Alice\n2,13,false,Bob",
        encoding="utf-8",
    )

    csv_to_json_schema(input_csv, tmp_path)

    with open(
        tmp_path / "Inference_test.schema.json", "r", encoding="utf-8"
    ) as f:
        schema = json.load(f)

    properties = schema["properties"]
    assert properties["id"]["type"] == "number"
    assert properties["count"]["type"] == "number"
    assert properties["is_active"]["type"] == "boolean"
    assert properties["name"]["type"] == "string"


def test_csv_to_json_schema_strict_number_inference():
    """Tests if type inference strictly rejects NaN and Inf, falling back to
    string."""
    tmp_path = get_test_tmp_path("csv_to_json_schema_strict_number_inference")
    input_csv = tmp_path / "strict_numbers.csv"
    input_csv.write_text(
        "valid_int,valid_float,valid_exp,invalid_nan,invalid_inf\n"
        "42,-3.14,1.2e-5,NaN,inf\n"
        "0,0.0,-2E10,nan,-Infinity",
        encoding="utf-8",
    )

    csv_to_json_schema(input_csv, tmp_path)

    with open(
        tmp_path / "Strict_numbers.schema.json", "r", encoding="utf-8"
    ) as f:
        schema = json.load(f)

    properties = schema["properties"]
    assert properties["valid_int"]["type"] == "number"
    assert properties["invalid_nan"]["type"] == "string"
    assert properties["invalid_inf"]["type"] == "string"


def test_csv_to_json_schema_no_rows_omits_examples():
    """A CSV with headers but no data rows should produce properties with no
    'examples' key at all."""
    tmp_path = get_test_tmp_path("csv_to_json_schema_no_rows")
    input_csv = tmp_path / "headers_only.csv"
    input_csv.write_text("title,description\n", encoding="utf-8")

    csv_to_json_schema(input_csv, tmp_path)

    with open(
        tmp_path / "Headers_only.schema.json", "r", encoding="utf-8"
    ) as f:
        schema = json.load(f)

    for prop in schema["properties"].values():
        assert "examples" not in prop


def test_csv_to_json_schema_base_url():
    """Tests if providing a base URL correctly formats the $id as an IRI."""
    tmp_path = get_test_tmp_path("csv_to_json_schema_base_url")
    input_csv = DATA_DIR / "test_input.csv"
    base_url = "https://raw.githubusercontent.com/schemas"

    csv_to_json_schema(input_csv, tmp_path, base_url=base_url)

    output_file = tmp_path / "Test_input.schema.json"
    with open(output_file, "r", encoding="utf-8") as f:
        schema = json.load(f)

    assert schema["$id"] == f"{base_url}/Test_input.schema.json"


def test_csv_to_json_schema_properties_mapping():
    """Tests if mapping ONLY extracts description/conformance and safely
    ignores other properties."""
    tmp_path = get_test_tmp_path("csv_to_json_schema_properties_mapping")
    input_csv = DATA_DIR / "test_input.csv"

    mapping = {
        "title": {
            "iri": "dcterms:title",
            "range": "rdfs:Literal",
            "conformance": "mandatory",
            "datatype": "rdf:langString",
            "usageNote": "A name given to the resource.",
            "description": "My Custom Title Description",
        }
    }

    csv_to_json_schema(input_csv, tmp_path, properties_mapping=mapping)

    output_file = tmp_path / "Test_input.schema.json"
    with open(output_file, "r", encoding="utf-8") as f:
        schema = json.load(f)

    properties = schema["properties"]

    # Conformance was 'mandatory', so it should be required, but type stays
    # purely "string"
    assert "title" in schema["required"]
    assert properties["title"]["type"] == "string"
    assert properties["title"]["description"] == "My Custom Title Description"

    # Verify ignored properties
    assert "iri" not in properties["title"]


def test_csv_to_json_schema_oold_compliance():
    """Strictly validates the generated JSON against the official OO-LD
    meta-schema."""
    registry = get_schema_registry()
    if registry is None:
        # Skip gracefully if running without internet access
        return

    tmp_path = get_test_tmp_path("csv_to_json_schema_oold_compliance")
    input_csv = DATA_DIR / "test_input.csv"
    csv_to_json_schema(input_csv, tmp_path)

    output_file = tmp_path / "Test_input.schema.json"
    with open(output_file, "r", encoding="utf-8") as f:
        generated_schema = json.load(f)

    try:
        oold_meta_schema = registry.resolver().lookup(META_SCHEMA).contents
        jsonschema.validate(
            instance=generated_schema,
            schema=oold_meta_schema,
            registry=registry,
        )
    except ValidationError as e:
        raise AssertionError(
            f"Schema failed OO-LD validation: {e.message}"
        ) from e


def test_csv_to_json_file_not_found():
    """Tests error handling for missing CSV files."""
    tmp_path = get_test_tmp_path("csv_to_json_file_not_found")
    missing_file = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        csv_to_json_schema(missing_file, tmp_path)


# --- Tests for JSON Schema to CSV ---


def test_json_schema_to_csv_content():
    """Tests if the schema correctly unpacks array examples into CSV rows
    (expecting 1 row)."""
    tmp_path = get_test_tmp_path("json_schema_to_csv_content")
    input_json = tmp_path / "Test_input.schema.json"

    # Creating mock schema with pure string types
    mock_schema = {
        "$schema": META_SCHEMA,
        "$id": "Test_input.schema.json",
        "@context": CONTEXT_URL,
        "title": "Test_input",
        "type": "object",
        "properties": {
            "@id": {"anyOf": [], "description": "", "examples": ["id:1"]},
            "@type": {"anyOf": [], "description": "", "examples": ["type:1"]},
            "title": {
                "type": "string",
                "description": "",
                "examples": ["Sample 1"],
            },
        },
    }
    with open(input_json, "w", encoding="utf-8") as f:
        json.dump(mock_schema, f)

    json_schema_to_csv(input_json, tmp_path)
    output_file = tmp_path / "test_input.csv"
    assert output_file.exists(), "The CSV file was not created."

    with open(output_file, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    assert len(reader) == 1
    assert reader[0]["title"] == "Sample 1"
    assert reader[0]["@id"] == "id:1"


def test_json_schema_to_csv_invalid_schema():
    """Tests error handling when the JSON file lacks a 'properties' key."""
    tmp_path = get_test_tmp_path("json_schema_to_csv_invalid_schema")
    input_json = DATA_DIR / "invalid_schema.json"

    with pytest.raises(ValueError, match="missing the 'properties' key"):
        json_schema_to_csv(input_json, tmp_path)


# --- Tests for Directory Path Processing ---


def test_process_path_directory():
    """Tests if process_path correctly processes a folder based on mode."""
    tmp_path = get_test_tmp_path("process_path_directory")
    process_path(DATA_DIR, tmp_path, "csv2json")

    expected_output = tmp_path / "Test_input.schema.json"
    assert (
        expected_output.exists()
    ), "The directory processor failed to generate the schema."


def test_process_path_directory_skips_mismatched_files():
    """Files in a directory that don't match the requested mode are silently
    skipped."""
    tmp_path = get_test_tmp_path("process_path_directory_skips")
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "notes.txt").write_text("not convertible", encoding="utf-8")

    # Manually capture logs without relying on pytest caplog fixture
    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    log = logging.getLogger("oold.converter")
    log.addHandler(handler)

    try:
        process_path(input_dir, tmp_path / "out", "csv2json")
        assert "No files were processed" in log_capture.getvalue()
    finally:
        log.removeHandler(handler)


def test_process_path_single_unsupported_file_warns():
    """A single file explicitly passed in that doesn't match the mode logs a
    specific warning."""
    tmp_path = get_test_tmp_path("process_path_single_unsupported")
    bad_file = tmp_path / "notes.txt"
    bad_file.write_text("not convertible", encoding="utf-8")

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    log = logging.getLogger("oold.converter")
    log.addHandler(handler)

    try:
        process_path(bad_file, tmp_path / "out", "csv2json")
        assert "unsupported for mode" in log_capture.getvalue()
    finally:
        log.removeHandler(handler)


def test_process_path_missing_input():
    """Tests error handling for a completely missing input path."""
    tmp_path = get_test_tmp_path("process_path_missing_input")
    missing = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError):
        process_path(missing, tmp_path / "out", "csv2json")


def test_process_path_exclude_files():
    """Tests if process_path correctly skips multiple files specified by the
    exclude_files parameter."""
    tmp_path = get_test_tmp_path("process_path_exclude_files")

    # Create input and output directories
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # Create valid CSV files
    file1 = input_dir / "keep_me.csv"
    file2 = input_dir / "skip_me.csv"
    file3 = input_dir / "also_skip.csv"
    file1.write_text("col1\nval1", encoding="utf-8")
    file2.write_text("col1\nval1", encoding="utf-8")
    file3.write_text("col1\nval1", encoding="utf-8")

    # Process the directory but exclude skip_me.csv and also_skip.csv
    process_path(
        input_dir,
        out_dir,
        "csv2json",
        exclude_files=["skip_me.csv", "also_skip.csv"],
    )

    # Check that keep_me.csv was processed
    assert (
        out_dir / "Keep_me.schema.json"
    ).exists(), "The non-excluded file was not processed."

    # Check that the other two were skipped
    assert not (
        out_dir / "Skip_me.schema.json"
    ).exists(), "An excluded file was incorrectly processed."
    assert not (
        out_dir / "Also_skip.schema.json"
    ).exists(), "An excluded file was incorrectly processed."


def test_conversion_error_wraps_original_exception():
    """ConversionError should preserve the underlying exception for callers
    using the __cause__ attribute."""
    original = ValueError("boom")

    try:
        try:
            raise original
        except ValueError as e:
            raise ConversionError("wrapped failure") from e
    except ConversionError as e:
        assert str(e) == "wrapped failure"
        assert e.__cause__ is original
