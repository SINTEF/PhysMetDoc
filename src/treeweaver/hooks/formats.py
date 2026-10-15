"""Module with hooks for formats."""

from treeweaver.treeweaver2 import PathType


def canonical_extension(path: PathType, env: dict) -> dict:
    """Extract canonical file extension.

    Uses `format` in the input and returns dict with `format` set to the
    canonical file extension.
    """
    # pylint: disable=unused-argument
    translated_formats = {
        "tif": "tiff",
        "TIF": "tiff",
        "jpg": "jpeg",
        "h5": "hdf5",
    }
    format = env.get("format", "")
    return {"format": translated_formats.get(format, format)}


def media_type(path: PathType, env: dict) -> dict:
    """Extract file extension.

    Uses `format` in the input and returns dict with `mediaType` set to the
    full IANA IRI (or "", if format is unknown).
    """
    # pylint: disable=unused-argument
    media_types = {
        "png": "iana:image/png",
        "tiff": "iana:image/tiff",
        "jpeg": "iana:image/jpeg",
        "bmp": "iana:image/bmp",
        "hdf5": "iana:application/vnd.hdfgroup.hdf5",
        "dat": "iana:application/dat",
        "cbf": "iana:application/cbf",
        "docx": (
            "iana:application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        "xlsx": (
            "iana:application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        "xls": "iana:application/vnd.ms-excel",
        "xml": "iana:application/xml",
        "csv": "iana:application/csv",
        "vesta": "iana:application/x-vesta",
        "dm3": "iana:application/x-dm3",
        "dm4": "iana:application/x-dm4",
        "npy": "iana:application/x-numpy",
        "ipynb": "iana:application/x-ipynb+json",
        "txt": "iana:text/plain",
        # "fd": "iana:???",
        # "ldf": "iana:???",
        # "lsd": "iana:???",
        # "mdf": "iana:???",
        # "pal": "iana:???",
        # "Spc": "iana:???",
        # "ipr": "iana:???",
        # "osc": "iana:???",
    }
    format = env.get("format", "")
    return {"mediaType": media_types.get(format, "")}
