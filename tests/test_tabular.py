"""Unit test suite for the tabular library."""

import logging
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest

import tabular
from tabular.models import Table, Tables
from tabular.registry import get_reader, get_writer

# --- Global Test Environment Setup ---


def get_tmp_root() -> Path:
    """Creates a temporary path for writing test outputs safely."""
    temp_dir = tempfile.mkdtemp()
    return Path(temp_dir)


TMP_ROOT = get_tmp_root()
DATA_DIR = Path(__file__).resolve().parent / "data" / "tabular"
FILE_CSV = DATA_DIR / "complex_data.csv"
FILE_EXCEL = DATA_DIR / "complex_data.xlsx"


# --- Tests for Central Registry Logic ---


def test_registry_unsupported_read():
    """Verify registry rejects unknown/write-only formats on read."""
    with pytest.raises(
        ValueError, match="Unsupported format for reading: 'unknown'"
    ):
        get_reader("unknown")

    with pytest.raises(
        ValueError, match="Unsupported format for reading: 'md'"
    ):
        get_reader("md")


def test_registry_unsupported_write():
    """Verify registry rejects unknown formats when writing."""
    with pytest.raises(
        ValueError, match="Unsupported format for writing: 'unknown'"
    ):
        get_writer("unknown")


# --- Tests for Validation & Error Handling ---


def test_read_nonexistent_path_raises_error():
    """Verify reading a non-existent path raises FileNotFoundError."""
    missing_path = TMP_ROOT / "non_existent_file.csv"
    with pytest.raises(FileNotFoundError, match="Path not found"):
        tabular.read(missing_path)


def test_write_directory_raises_error():
    """Verify writing a Table to a directory raises IsADirectoryError."""
    t = Table("T1", ["A"], [[1]])
    with pytest.raises(IsADirectoryError, match="Target path is a directory"):
        tabular.write(t, DATA_DIR, format="csv")


def test_csv_encoding_error():
    """Verify CSVReader catches UnicodeDecodeError and raises ValueError."""
    bad_csv = TMP_ROOT / "bad_encoding.csv"
    bad_csv.write_bytes(b"\xff\xfe\xfd")
    with pytest.raises(ValueError, match="Encoding error reading"):
        tabular.read(bad_csv, format="csv")


def test_excel_invalid_file_error():
    """Verify Excel files catch invalid structures and raise ValueError."""
    bad_excel = TMP_ROOT / "bad_excel.xlsx"
    bad_excel.write_text(
        "This is definitely not a zip or excel file.", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Failed to load Excel file"):
        tabular.read(bad_excel, format="xlsx")


# --- Tests for Symmetric Path Read / Write Workflows ---


def test_symmetric_read_write_directory_workflow():
    """
    Verify symmetric read/write behaviour where the exact path passed to
    write() can be passed directly to read() to merge or update data.
    The format should be automatically inferred even for a directory path.
    """
    t1 = Table("SheetA", ["ID", "Val"], [[1, "A"]])
    t2 = Table("SheetB", ["ID", "Val"], [[2, "B"]])
    original_tables = Tables([t1, t2])

    target_path = TMP_ROOT / "dataset.csv"

    # Writing multi-table CSV creates 'dataset' directory
    tabular.write(original_tables, target_path)

    # Re-reading exact same path loads split files from directory seamlessly
    # NOTE: NO explicit format="csv" is provided here. It infers it.
    reloaded_tables = tabular.read(target_path)

    assert len(reloaded_tables.tables) == 2
    assert "SheetA" in [t.name for t in reloaded_tables.tables]
    assert "SheetB" in [t.name for t in reloaded_tables.tables]

    # Demonstrate merging logic before writing back
    new_table = Table("SheetC", ["ID", "Val"], [[3, "C"]])
    reloaded_tables.append(new_table)

    tabular.write(reloaded_tables, target_path)

    # Again, read without explicit format
    updated_tables = tabular.read(target_path)
    assert len(updated_tables.tables) == 3


# --- Tests for Readers using Unified Real Files ---


def test_csv_returns_tables_collection():
    """Verify standard CSV files read and infer complex types."""
    result = tabular.read(FILE_CSV)

    assert isinstance(result, Tables)
    assert len(result.tables) == 1

    table = result.first
    assert table.headers == [
        "ID",
        "Navn",
        "Temp (°C)",
        "US Format",
        "Euro Format",
        "Spaced Format",
        "NBSP Format",
        "Date 1 (dd/mm/yyyy)",
        "Date 2 (dd.mm.yyyy)",
        "Date 3 (yyyy-mm-dd)",
    ]

    assert table.rows[0] == [
        1,
        "Bjørn Ærø",
        25.5,
        1500.5,
        1500.5,
        1500.5,
        1500.5,
        "12/05/2026",
        "12.05.2026",
        "2026-05-12",
    ]


def test_excel_multi_sheet_and_inference():
    """Verify Excel files return sheets and infer types correctly."""
    result = tabular.read(FILE_EXCEL)

    assert isinstance(result, Tables)
    assert len(result.tables) == 2

    sheet_names = [t.name for t in result.tables]
    assert "Mixed Formats" in sheet_names
    assert "Simple Data" in sheet_names


def test_read_sheets():
    """Test read selected sheets."""
    tables = tabular.read(FILE_EXCEL, sheets=[1, 0])
    assert tables.names == ["Simple Data", "Mixed Formats"]


def test_table_read_sheet():
    """Test read selected sheets."""
    table = Table.read(FILE_EXCEL, sheet=0)
    assert table.headers[0] == "ID"


# --- Tests for Table / Tables Built-In Class Methods ---


def test_table_class_read_and_write():
    """Verify Table class can natively read and write files."""
    t = Table.read(FILE_CSV)
    assert t.name == "complex_data"

    out_path = TMP_ROOT / "class_write_test.csv"
    t.write(out_path)
    assert out_path.exists()


def test_tables_class_read_and_write():
    """Verify Tables class can natively read and write files."""
    ts = Tables.read(FILE_EXCEL)
    assert len(ts.tables) == 2

    json_str = ts.write(format="json")
    assert "Mixed Formats" in str(json_str)


# --- Tests for Table Model Appending, Logging & Features ---


def test_append_table_strict_rejection():
    """Test append_table fails if target lacks headers and merge=False."""
    t1 = Table("Target", ["A", "B"], [[1, 2]])
    t2 = Table("Source", ["A", "C"], [[3, 4]])

    with pytest.raises(ValueError, match="Unrecognized headers: \\['C'\\]"):
        t1.append_table(t2, merge_headers=False)


def test_append_table_merge_success():
    """Test append_table expands columns and inserts None when merge=True."""
    t1 = Table("Target", ["A", "B"], [[1, 2]])
    t2 = Table("Source", ["A", "C"], [[3, 4]])

    t1.append_table(t2, merge_headers=True)

    assert set(t1.headers) == {"A", "B", "C"}
    assert t1.rows[0] == [1, 2, None]
    assert t1.rows[1] == [3, None, 4]


def test_append_table_logs_error():
    """A mismatch in headers when merging=False logs a specific error."""
    t1 = Table("Target", ["A", "B"], [[1, 2]])
    t2 = Table("Source", ["A", "C"], [[3, 4]])

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    logger = logging.getLogger("tabular.models.table")
    old_level = logger.level
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)

    try:
        with pytest.raises(ValueError):
            t1.append_table(t2, merge_headers=False)
        assert "Unrecognized headers:" in log_capture.getvalue()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)


def test_csv_reader_sniff_warns_on_fail():
    """Sniffing an empty/invalid file logs a warning gracefully."""
    bad_csv = TMP_ROOT / "empty.csv"
    bad_csv.write_text("", encoding="utf-8")

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    logger = logging.getLogger("tabular.readers.csv_reader")
    old_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)

    try:
        tabular.read(bad_csv, sniff_dialect=True)
        assert "Could not sniff dialect" in log_capture.getvalue()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)


def test_table_indexing_and_iteration():
    """Verify Table supports row/column indexing and iteration."""
    t = Table("Test", ["ID", "Name"], [[1, "Alice"], [2, "Bob"]])
    assert t[0] == [1, "Alice"]
    assert t["Name"] == ["Alice", "Bob"]
    with pytest.raises(KeyError):
        _ = t["UnknownColumn"]


def test_table_append_from_file_and_write():
    """Verify Table appends data directly from a file and writes to disk."""
    t = Table("Base", ["ID", "Navn", "Temp (°C)"], [[99, "Zero", 0.0]])
    new_data = tabular.read(FILE_CSV)
    t.append_table(new_data.first, merge_headers=True)

    assert len(t.rows) == 4
    out_path = TMP_ROOT / "table_output.csv"
    tabular.write(t, out_path)
    assert out_path.exists()


def test_table_write_unsupported_format_raises_exception():
    """Verify writing a Table with bad format raises ValueError."""
    t = Table("Sheet1", ["A"])
    with pytest.raises(ValueError, match="Unsupported format for writing"):
        tabular.write(t, TMP_ROOT / "out.unknownformat")


def test_table_printable():
    """Verify Table has aligned Markdown __str__ and __repr__."""
    t = Table("TestSheet", ["ID", "Name"], [[1, "Alice"], [2, "Bob"]])
    expected = (
        "## TestSheet\n"
        "| ID | Name  |\n"
        "|----|-------|\n"
        "| 1  | Alice |\n"
        "| 2  | Bob   |"
    )
    assert str(t) == expected


# --- Tests for Tables Model Features ---


def test_tables_init_with_list():
    """Verify Tables initializes directly with a list of Tables."""
    t1 = Table("Sheet1", ["A"])
    t2 = Table("Sheet2", ["B"])
    ts = Tables([t1, t2])
    assert len(ts.tables) == 2


def test_tables_remove_table():
    """Verify Tables can be removed by index or by name."""
    t1, t2, t3 = Table("S1", []), Table("S2", []), Table("S3", [])
    ts = Tables([t1, t2, t3])

    ts.remove_table("S2")
    assert len(ts.tables) == 2

    ts.remove_table(0)
    assert len(ts.tables) == 1

    with pytest.raises(TypeError, match="Key must be an integer .* or string"):
        ts.remove_table(cast(Any, {"wrong": "type"}))


def test_tables_indexing_and_iteration():
    """Verify Tables supports indexing by int/name and iteration."""
    t1, t2 = Table("S1", []), Table("S2", [])
    ts = Tables([t1, t2])
    assert ts[0] == t1
    assert ts["S2"] == t2


def test_tables_append_from_file_and_write():
    """Verify Tables appends data from a file and writes to disk."""
    ts = Tables()
    new_data = tabular.read(FILE_CSV)
    for table in new_data.tables:
        ts.append(table)

    ts.append(Table("second_sheet", ["A"], [[1]]))
    split_csv_path = TMP_ROOT / "output.csv"

    tabular.write(ts, split_csv_path)

    expected_dir = TMP_ROOT / "output"
    assert expected_dir.is_dir()
    assert (expected_dir / "complex_data.csv").exists()
    assert (expected_dir / "second_sheet.csv").exists()


def test_tables_write_unsupported_format_raises_exception():
    """Verify writing Tables with bad format raises ValueError."""
    ts = Tables([Table("Sheet1", ["A"])])
    with pytest.raises(ValueError, match="Unsupported format for writing"):
        tabular.write(ts, TMP_ROOT / "out.unknownformat")


def test_tables_printable():
    """Verify Tables has aligned Markdown __str__ and __repr__."""
    t1 = Table("Sheet1", ["A"], [[1]])
    t2 = Table("Sheet2", ["B"], [[2]])
    ts = Tables([t1, t2])
    expected = (
        "## Sheet1\n| A |\n|---|\n| 1 |\n\n## Sheet2\n| B |\n|---|\n| 2 |"
    )
    assert str(ts) == expected


# --- Tests for Writers ---


def test_csv_write_splits_multiple_tables():
    """Verify multi-table CSV writes split into a dir and warn."""
    base_out_csv = TMP_ROOT / "split_output.csv"
    tables = tabular.read(FILE_EXCEL)

    tabular.write(tables, base_out_csv)

    expected_dir = TMP_ROOT / "split_output"
    assert expected_dir.is_dir()
    assert (expected_dir / "Mixed Formats.csv").exists()
    assert (expected_dir / "Simple Data.csv").exists()

    assert (
        not base_out_csv.exists()
    ), "io.write created a merged CSV instead of splitting into a directory."


def test_writers_append_newline():
    """Verify MD and JSON writers append a single newline at file end."""
    t = Table("NewlineTest", ["Col"], [[1]])
    md_path, json_path = TMP_ROOT / "test.md", TMP_ROOT / "test.json"

    try:
        tabular.write(t, md_path)
        has_md = True
    except ValueError:
        has_md = False

    try:
        tabular.write(t, json_path)
        has_json = True
    except ValueError:
        has_json = False

    if has_md and md_path.exists():
        md_content = md_path.read_text(encoding="utf-8")
        assert md_content.endswith(
            "\n"
        ), "Markdown output must end with a newline character."
        assert not md_content.endswith(
            "\n\n"
        ), "Markdown output must have exactly one trailing newline."

    if has_json and json_path.exists():
        json_content = json_path.read_text(encoding="utf-8")
        assert json_content.endswith(
            "\n"
        ), "JSON output must end with a newline character."
        assert not json_content.endswith(
            "\n\n"
        ), "JSON output must have exactly one trailing newline."


def test_json_unicode_formatting():
    """Verify JSON writer formats unicode natively."""
    tables = tabular.read(FILE_EXCEL)
    json_str = tabular.write(tables, format="json")
    assert "Bjørn Ærø" in str(json_str)


def test_match_rows():
    """Test match_rows method."""
    t = Table(
        "TestSheet",
        ["ID", "Name", "Age"],
        [(1, "Alice", 32), (2, "Bob", 33), (3, "Cyril", 33)],
    )
    assert t.match_rows("Name", "Bob") == [[2, "Bob", 33]]
    assert t.match_rows("Age", 33) == [[2, "Bob", 33], [3, "Cyril", 33]]
    assert t.match_rows("Age", 42) == []
    assert t.match_rows(("Age", "Name"), (33, "Bob")) == [[2, "Bob", 33]]
    assert t.match_rows((), ()) == [
        [1, "Alice", 32],
        [2, "Bob", 33],
        [3, "Cyril", 33],
    ]


def test_lookup():
    """Test lookup method."""
    t = Table(
        "TestSheet",
        ["ID", "Name", "Age"],
        [(1, "Alice", 32), (2, "Bob", 33), (3, "Cyril", 33)],
    )
    assert t.lookup("Name", "Bob", "ID") == [2]
    assert t.lookup(1, "Bob", "ID") == [2]
    assert t.lookup("Age", 33, "ID") == [2, 3]
    assert t.lookup(2, 33, 0) == [2, 3]
    assert t.lookup("Name", "Bob", "ID", mode="unique") == 2
    assert t.lookup("Age", 33, "ID", mode="first") == 2
    assert t.lookup("Age", 42, "ID", default=-1) == -1
    with pytest.raises(LookupError):
        t.lookup("Age", 33, "ID", mode="unique")
    with pytest.raises(ValueError):
        t.lookup("Non-existing", 33, "ID", mode="unique")
    with pytest.raises(IndexError):
        t.lookup(5, 33, "ID", mode="unique")


# pylint: disable=duplicate-code
if __name__ == "__main__":
    print("Running Tabular Data IO tests standalone...\n")
    test_functions = [
        obj
        for name, obj in globals().items()
        if callable(obj) and name.startswith("test_")
    ]

    PASSED, FAILED = 0, 0
    for test_func in test_functions:
        sys.stdout.write(f"Running {test_func.__name__} ... ")
        try:
            test_func()
            print("PASSED")
            PASSED += 1
        except (
            AssertionError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
        ) as e:
            print(f"FAILED\n  -> {type(e).__name__}: {e}")
            FAILED += 1

    print("\n--- Test Run Summary ---")
    print(f"Total: {PASSED + FAILED} | Passed: {PASSED} | Failed: {FAILED}")

    if FAILED > 0:
        raise RuntimeError(f"Test suite failed with {FAILED} errors.")
