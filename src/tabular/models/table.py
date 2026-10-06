"""Table model representing a single 2D dataset."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    Sequence,
    Union,
)

PathType = Union[str, Path]
IndexType = Union[int, str]


logger = logging.getLogger(__name__)


class NODEFAULT:
    """Sentinel value indicating that no default has been provided."""


class Table:
    """
    Represents a single two-dimensional dataset.

    A Table consists of an optional name, a list of string headers representing
    the columns, and a list of rows containing the actual data. It provides
    utilities for row-level manipulation and Markdown formatting.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        headers: Optional[List[str]] = None,
        rows: Optional[List[List[Any]]] = None,
    ):
        """
        Initializes a new Table.

        Args:
            name (str, optional): The name of the table (e.g., sheet name).
                Defaults to None.
            headers (List[str], optional): A list of string headers.
                Defaults to an empty list.
            rows (List[List[Any]], optional): A list of rows, where each row is
                a list of values. Defaults to an empty list.
        """
        self.name = name
        self.headers = headers if headers is not None else []
        self.rows: List[List[Any]] = []
        if rows:
            self.append_rows(rows)

    # --- Dunder Methods ---

    def __str__(self) -> str:
        """
        Returns an aligned Markdown string representation of the Table.

        Returns:
            str: The formatted Markdown table data.
        """
        if not self.headers:
            return f"Empty Table: {self.name}"

        str_headers = [str(h) for h in self.headers]
        str_rows = [
            [str(c) if c is not None else "" for c in row] for row in self.rows
        ]

        widths = [len(h) for h in str_headers]
        for row in str_rows:
            for i, cell in enumerate(row):
                if i < len(widths) and len(cell) > widths[i]:
                    widths[i] = len(cell)

        def fmt_row(row_data: List[str]) -> str:
            return (
                "| "
                + " | ".join(
                    c.ljust(widths[i]) for i, c in enumerate(row_data)
                )
                + " |"
            )

        lines = []
        if self.name:
            lines.append(f"## {self.name}")

        lines.append(fmt_row(str_headers))
        lines.append("|" + "|".join("-" * (w + 2) for w in widths) + "|")

        for r in str_rows:
            lines.append(fmt_row(r))

        return "\n".join(lines)

    def __repr__(self) -> str:
        """
        Returns a detailed string representation of the Table for debugging.

        Returns:
            str: Unambiguous representation detailing name, columns, and rows.
        """
        name_repr = f"'{self.name}'" if self.name else "None"
        return (
            f"<Table(name={name_repr}, "
            f"columns={len(self.headers)}, rows={len(self.rows)})>"
        )

    def __getitem__(self, key: IndexType) -> List[Any]:
        """
        Allows indexing into the table to get a row or a column.

        Args:
            key (IndexType): An integer to get a row by index, or a string to
                get a column by header name.

        Returns:
            List[Any]: The requested row or column.

        Raises:
            KeyError: If a string key is not found in the headers.
            IndexError: If an integer key is out of bounds for the rows.
            TypeError: If the key is neither an int nor a str.
        """
        if isinstance(key, int):
            return self.rows[key]
        if isinstance(key, str):
            if key not in self.headers:
                raise KeyError(f"Column '{key}' not found in headers.")
            idx = self.headers.index(key)
            return [row[idx] for row in self.rows]
        raise TypeError(
            "Key must be an integer (row index) or string (column name)."
        )

    def __iter__(self) -> Iterator[List[Any]]:
        """
        Allows iterating over the rows of the table.

        Returns:
            Iterator[List[Any]]: An iterator yielding each row sequentially.
        """
        return iter(self.rows)

    # --- Class Methods ---

    @classmethod
    def read(
        cls,
        path: PathType,
        format: Optional[str] = None,
        sheet: IndexType = 0,
        **kwargs: Any,
    ) -> Table:
        """
        Reads a file or directory directly into a Table instance.

        If `format` is not provided, it is inferred from the path's extension,
        regardless of whether the path points to a file or a directory.

        Args:
            path (PathType): Path to the file or directory.
            format (Optional[str], optional): Format override.
            sheet (IndexType): Sheet name or number to read.
            **kwargs: Extra parameters passed to the reader.

        Returns:
            Table: The parsed single table.

        Raises:
            ValueError: If the target file contains multiple tables.
        """
        # pylint: disable=import-outside-toplevel
        from tabular.io import read

        sheets = None if sheet is None else [sheet]
        tables = read(path, format=format, sheets=sheets, **kwargs)
        tables_list = getattr(tables, "tables", None)
        if tables_list is not None and len(tables_list) > 1:
            raise ValueError(
                "Expected a single table but found multiple. "
                "Use Tables.read() instead."
            )
        return getattr(tables, "first")

    # --- Instance Methods ---

    def write(
        self,
        path: Optional[PathType] = None,
        format: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        Writes this Table directly to a file or returns a string.

        Args:
            path (Optional[PathType], optional): Destination path.
            format (Optional[str], optional): Format override.
            **kwargs: Extra parameters passed to the writer.

        Returns:
            Optional[str]: Serialized string if path is None, else None.
        """
        # pylint: disable=import-outside-toplevel
        from tabular.io import write

        return write(self, path=path, format=format, **kwargs)

    def append_row(self, row: List[Any]) -> None:
        """
        Appends a single row to the table sequentially.

        Args:
            row (List[Any]): The data row to append.

        Raises:
            ValueError: If the length of the row does not match headers.
        """
        if len(row) != len(self.headers):
            msg = (
                f"Row length ({len(row)}) != "
                f"header length ({len(self.headers)})."
            )
            logger.error("%s", msg)
            raise ValueError(msg)
        self.rows.append(list(row))

    def append_rows(self, rows: List[List[Any]]) -> None:
        """
        Appends multiple rows to the table sequentially.

        Args:
            rows (List[List[Any]]): A list of data rows to append.

        Raises:
            ValueError: If any row length does not match the header length.
        """
        for row in rows:
            self.append_row(row)

    def append_table(self, other: Table, merge_headers: bool = False) -> None:
        """
        Appends data from another Table object into this Table.

        Args:
            other (Table): The source Table to append data from.
            merge_headers (bool, optional):
                If True, dynamically adds new columns to this table if they
                exist in `other`, filling existing rows with None.
                If False, strictly requires `other`'s headers to be identical.

        Raises:
            ValueError: If merge_headers is False and `other` contains columns
                        not present in this table.
        """
        new_headers = [h for h in other.headers if h not in self.headers]

        if new_headers:
            if not merge_headers:
                msg = (
                    f"Failed to append '{other.name}' to '{self.name}'. "
                    f"Unrecognized headers: {new_headers}. "
                    "Set merge_headers=True to allow."
                )
                logger.error("%s", msg)
                raise ValueError(msg)

            logger.info(
                "Expanding table '%s' schema with headers: %s",
                self.name,
                new_headers,
            )
            self.headers.extend(new_headers)
            for row in self.rows:
                row.extend([None] * len(new_headers))

        for other_row in other.rows:
            row_dict = dict(zip(other.headers, other_row))
            mapped_row = [row_dict.get(h, None) for h in self.headers]
            self.rows.append(mapped_row)

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """
        Converts table into a list of dicts mapping headers to values.

        Returns:
            List[Dict[str, Any]]: A list where each dict represents one row.
        """
        return [dict(zip(self.headers, row)) for row in self.rows]

    def match_rows(
        self,
        columns: Union[IndexType, Sequence[IndexType]],
        values: Union[Any, Sequence[Any]],
    ) -> list:
        """
        Matches rows whose values in the specified columns equals `values`.

        Args:
            columns (Union[IndexType, Sequence[IndexType]]): One or more
                columns to match against. May be specified by number or name.
            values (Union[Any, Sequence[Any]]): Corresponding values to look
                for. Must have the same length as `columns`.

        Returns:
            list: List of matching rows.

        Raises:
            ValueError: If an invalid column name is specified.
            IndexError: If a colum index is out of range.
        """
        if isinstance(columns, (str, int)):
            columns, values = [columns], [values]
        rows = self.rows
        for col, value in zip(columns, values):
            i = self.headers.index(col) if isinstance(col, str) else col
            rows = [row for row in rows if row[i] == value]
        return rows

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def lookup(
        self,
        columns: Union[IndexType, Sequence[IndexType]],
        values: Union[Any, Sequence[Any]],
        outcol: IndexType,
        mode: Literal["unique", "all", "first"] = "all",
        default: Any = NODEFAULT,
    ) -> Any:
        """
        Looks up occurences of `value` in `columns` and return the
        corresponding value(s) in `outcol`.

        If no rows match the criteria, returns `default`.

        Args:
            columns (Union[IndexType, Sequence[IndexType]]): One or more
                columns to match for. May be specified by number or name.
            values (Union[Any, Sequence[Any]]): Corresponding values to look
                for.  Must have the same length as `columns`.
            outcol (IndexType): Column to return the corresponding value form.
            mode (str): If `mode` is:
                - "unique": Return unique lookup value. Raises LookupError if
                      there is not exact one matching row.
                - "all": Returns a list with all matching values.
                      May be an empty list.
                - "first": Returns the falue of the first matching row.
                      Raises LookupError if there are no matching rows.
            default (Any): Default value to return if no rows matches.

        Returns:
            Any: The value(s) in `outcol` based on the specified `mode`.

        Raises:
            ValueError: If an invalid column name or mode is specified.
            IndexError: If a colum index is out of range.
            LookupError: If there are too many or few matching rows (depending
                on `mode`).
        """
        rows = self.match_rows(columns, values)
        if not rows and default is not NODEFAULT:
            return default

        i = self.headers.index(outcol) if isinstance(outcol, str) else outcol
        if mode == "unique":
            if len(rows) != 1:
                raise LookupError(
                    f"expected only one matching row, got {len(rows)} for "
                    f"{columns=} and {values=}"
                )
            return rows[0][i]
        if mode == "all":
            return [row[i] for row in rows]
        if mode == "first":
            if not rows:
                raise LookupError("no matching rows")
            return rows[0][i]
        raise ValueError(
            f'`mode` must be "unique", "all" or "first", got: "{mode}'
        )
