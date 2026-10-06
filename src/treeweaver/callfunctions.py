"""Module with general call functions.

Tries to extract vendor and technique from experimental output files.
"""

# import warnings
from pathlib import Path
from typing import Any, Optional

from wcmatch import glob

from tabular import Table
from treeweaver.treeweaver2 import PathType


def get_equipment(
    path: PathType,
    env: dict,
    override: bool = False,
    maxarray: int = 3,
    equipment_table: Optional[str | Path | Table] = None,
    **kwargs,
) -> dict:
    """Extract equipment and techniqe from raw output file.

    Arguments:
        path: Path to the raw output file from the equipment.
        env: Existing environment.
        override: Only assign variables if they are not already defined in
            the environment.
        maxarray: Max length of arrays to report in tags. If zero, it is turned
            off.
        equipment_table: Table listing equipments. The columns manufacturer,
            model and serialNumber are used to identify the equipment ID.
        kwargs: Keyword arguments passed to the Table reader if
            `equipment_table` is a file path.

    Returns:
        Dict defining `equipment` and `technique`.
    """
    if not override and "equipment" in env and "technique" in env:
        return {}

    if isinstance(equipment_table, (str, Path)):
        rootdir = Path(env.get("rootdir", "."))
        equipment_table = Table.read(rootdir / equipment_table, **kwargs)

    for parser in parsers:
        if tags := parser(path, maxarray=maxarray):
            for extractor in extractors:
                try:
                    if d := extractor(tags, equipment_table):
                        return d
                except LookupError:
                    print(
                        "*** The equipment cannot be uniquely identified "
                        "in the equipment table:"
                    )
                    for k, v in tags.items():
                        print(f"  - {k}: {v}")
                    print("*** path:", path)
                    raise
    return {}


def _match(filename: PathType, patterns: str) -> bool:
    """Return wheter `path`  matches `pattern`."""
    return glob.globmatch(
        filename,
        patterns,
        flags=glob.IGNORECASE | glob.GLOBSTAR | glob.BRACE | glob.SPLIT,
    )


def _strip(s: Any) -> Any:
    """Return `s` stripped if it is a string, otherwise return it unchanged."""
    return s.strip() if isinstance(s, str) else s


# -------------------------------------------------------------------------
# Parsers


def _parse_png_tags(filename: PathType, maxarray: int = 3) -> dict:
    """Return tags from file accompanying .txt file to a .png file."""
    if not _match(filename, "**/*.png"):
        return {}

    tags = {}
    txtfile = Path(filename).with_suffix(".txt")
    if txtfile.exists():
        tags.update(_parse_txt_tags(txtfile, maxarray=maxarray))
    tags["Make"] = tags.get("$CM_FORMAT")
    tags["Model"] = tags.get("$CM_INSTRUMENT")
    return tags


def _parse_tiff_tags(filename: PathType, maxarray: int = 3) -> dict:
    """Return tags from a tiff file (or accompanying .txt file)."""
    if not _match(filename, "**/*.{tif,tiff}"):
        return {}

    tags = {}

    txtfile = Path(filename).with_suffix(".txt")
    if txtfile.exists():
        tags.update(_parse_txt_tags(txtfile, maxarray=maxarray))

    # pylint: disable=import-outside-toplevel
    from PIL import Image
    from PIL.TiffTags import TAGS

    # Known non-standard tags
    special_tags = {
        34118: _tifftag_34118,
        34959: None,
        34960: _tifftag_34960,
        34961: None,
    }
    with Image.open(filename) as img:
        for k, v in img.tag.items():
            if k in TAGS:
                if maxarray and isinstance(v, tuple) and len(v) > maxarray:
                    continue
                tags[TAGS[k]] = v
            elif k in special_tags:
                if special_tags[k]:
                    special_tags[k](v, tags)  # type: ignore[misc]
            else:
                # warnings.warn(f"Unknown tag {k} in: {filename}")
                print(f"Unknown tag {k} in: {filename}")
    return tags


def _parse_txt_tags(filename: PathType, maxarray: int = 3) -> dict:
    """Return tags from a text file."""
    # pylint: disable=unused-argument
    tags: dict = {}
    if not _match(filename, "**/*.txt"):
        return tags

    with open(filename, "rt") as f:  # pylint: disable=unspecified-encoding
        line1 = next(f).strip()
        f.seek(0)
        if line1.startswith("$") and "=" not in line1:
            for line in f:
                key, value = line.strip().split(" ", 1)
                tags.setdefault(key.strip(), value.strip())
        else:
            print(
                f"Unknown format of text file: '{filename}'. "
                f"Starts with: '{line1}'"
            )
    return tags


def _parse_dm3_tags(filename: PathType, maxarray: int = 3) -> dict:
    """Return tags from a dm3 and dm4 files."""
    # pylint: disable=unused-argument
    tags: dict = {}
    if not _match(filename, "**/*.{dm3,dm4}"):
        return tags

    # pylint: disable=import-outside-toplevel
    from dm3_lib import DM3

    dm3 = DM3(filename)
    tags.update(dm3.tags)  # Quite large. Skip it?

    # Make, Model and Mode are also available from the tags:
    #   - root.ImageList.1.ImageTags.Microscope Info.Name
    #   - root.ImageList.1.ImageTags.Microscope Info.Microscope
    #   - root.ImageList.1.ImageTags.Microscope Info.Operation Mode
    tags["Make"] = dm3.info["name_old"].decode()
    tags["Model"] = dm3.info["micro_old"].decode()
    tags["Mode"] = dm3.info["mode"].decode()
    return tags


# -------------------------------------------------------------------------
# Handle special TIFF tags


def _tifftag_34118(tifftag: Any, tags: dict) -> None:
    """Parse TIFF tag `tifftag` and update the `tags` dict."""
    for field in tifftag[0].split("\r\n"):
        if not isinstance(field, str):
            continue
        var, val = field.split("=", 1) if "=" in field else (field, True)
        tags.setdefault(_strip(var), _strip(val))


def _tifftag_34960(tifftag: Any, tags: dict) -> None:
    """Parse TIFF tag `tifftag` and update the `tags` dict."""
    # pylint: disable=unused-argument
    tags.setdefault("instrument", "SIMS")


# -------------------------------------------------------------------------
# Extractors


def _extract_equipment(tags: dict, table: Optional[Table] = None) -> dict:
    """Try to infer equipmentId from tags and equipment table."""
    if not table:
        return {}
    names = (
        ("manufacturer", "Make", "Vendor"),
        ("model", "Model", "$CM_INSTRUMENT"),
        ("serialNumber", "Serial No."),
        ("software", "Software"),
    )
    values = {}
    for colnames in names:
        for name in colnames:
            if name in tags and colnames[0] in table.headers:
                v = tags[name]
                values[colnames[0]] = v[0] if isinstance(v, tuple) else v
    if not values:
        return {}
    iri = table.lookup(
        list(values.keys()), list(values.values()), "@id", mode="unique"
    )
    return {"equipmentId": iri}


parsers = [
    _parse_png_tags,
    _parse_tiff_tags,
    _parse_dm3_tags,
]

extractors = [
    _extract_equipment,
]
