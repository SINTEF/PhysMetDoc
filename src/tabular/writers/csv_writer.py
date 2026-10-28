"""CSV writer implementation."""

import csv
import io
import logging
from pathlib import Path
from typing import Any

import tabular.models

from .base import BaseWriter

logger = logging.getLogger(__name__)


class CSVWriter(BaseWriter):
    """Writes tabular data to a CSV format."""

    def write(
        self,
        data: tabular.models.Table | tabular.models.Tables,
        path: Path | None = None,
        newline: str | None = "",
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> str | None:
        """
        Writes tabular data to a CSV file or string. If a multiple-table
        collection is provided, it automatically merges them prior to writing.

        Args:
            data (Union[tabular.models.Table, tabular.models.Tables]):
                The dataset to export.
            path (Optional[Path], optional): Output destination path.
                If None, returns the CSV string.
            newline (Optional[str], optional): Controls how universal newlines
                works. See docstring for open().
            encoding(Optional[str], optional): Encoding used to encode the
                output file.
            **kwargs: Standard parameters accepted by the `csv.writer`
                (e.g., delimiter).

        Returns:
            Optional[str]: The CSV string if path is None, else None.

        Raises:
            IsADirectoryError: If the path provided is a directory.
            PermissionError: If the file cannot be written to
                (e.g., open in Excel).
        """
        self._validate_write_path(path)

        if path is not None:
            self._ensure_directory(path)

        table = (
            data.merge_all()
            if (
                isinstance(data, tabular.models.Tables)
                and len(data.tables) > 1
            )
            else (
                data.first if isinstance(data, tabular.models.Tables) else data
            )
        )

        if path is None:
            # String memory writing
            with io.StringIO() as f:
                writer = csv.writer(f, **kwargs)
                writer.writerow(table.headers)
                writer.writerows(table.rows)
                return f.getvalue()
        else:
            # Physical file writing
            try:
                with open(
                    path, mode="w", newline=newline, encoding=encoding
                ) as f:
                    writer = csv.writer(f, **kwargs)
                    writer.writerow(table.headers)
                    writer.writerows(table.rows)
            except PermissionError as e:
                msg = (
                    f"Permission denied writing to '{path}'.\n"
                    "Ensure the file is not open in another program "
                    "(like Excel)."
                )
                logger.error(msg)
                raise PermissionError(msg) from e
            return None
