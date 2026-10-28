"""OO-LD Converter Package.

This package provides utilities for converting between CSV datasets
and Object-Oriented Linked Data (OO-LD) JSON Schemas.
"""

from .oold_converter import (
    ConversionError,
    csv_to_json_schema,
    json_schema_to_csv,
    process_path,
)

__all__ = [
    "ConversionError",
    "csv_to_json_schema",
    "json_schema_to_csv",
    "process_path",
]
