"""An updated treeweaver implementation."""

# pylint: disable=too-few-public-methods

import argparse
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import parse
import yaml

import tabular.io
from tabular import Table, Tables

__version__ = "2.0"

PathType = Union[Path, str]
ValueType = Union[str, list, dict, bool, int, float, None]  # template values


# Parse formatters
def underscored(string: str):
    """Parse formatter that converts blanks to underscore."""
    return string.replace(" ", "_")


def escaped(string: str):
    """Parse formatter that converts blanks to %-encoded."""
    # Alternatively we could use urllib.parse.quote()
    return string.replace(" ", "%20")


def xstrip(string: str):
    """Strip file extension and replace blanks with underscore."""
    return re.sub(r"\.\w+$", "", string).replace(" ", "_")


underscored.pattern = "[^/]+"  # type: ignore[attr-defined]
escaped.pattern = "[^/]+"  # type: ignore[attr-defined]
parse_formatters = {
    "underscored": underscored,
    "escaped": escaped,
    "xstrip": xstrip,
}


class Template:
    """Represents a template for a JSON-LD representation of a resource.

    Arguments:
        name: Name of the template (ex "dataset").
        stencils: Dict mapping variable names to stencil strings (using the
            Python Format Specification Mini-Language).

    """

    def __init__(self, name: str, stencils: dict[str, str]) -> None:
        self.name = name
        self.stencils = stencils

    def substitute(self, env: dict) -> dict:
        """Return a JSON-LD dict documenting a resource by
        substituting variables given in `env`.

        Arguments:
            env: Dict mapping variable names to values.

        Returns:
            Dict representing a JSON-LD documentation of a resource.

        """
        doc = {}
        for keyword, stencil in self.stencils.items():
            if stencil:
                try:
                    if s := substitute(stencil, env):
                        doc[keyword] = s
                except KeyError as exc:
                    raise KeyError(  # pylint: disable=raise-missing-from
                        f"Variable '{exc}' in stencil substitution for "
                        f"'{keyword}' is not assigned in pattern for "
                        f"template: '{self.name}'"
                    )
        return doc


class Pattern:
    """Represents a pattern with additional metadata.

    Arguments:
        pattern: Wildcard pattern a directory or file path.
        templates: Dict mapping template names to Template instances that this
            pattern applies to.
        vars: Dict defining variable definitions for updating the
            environment.

    """

    def __init__(self, pattern: str, vars: dict, templates: dict) -> None:
        self.pattern = parse.compile(pattern, extra_types=parse_formatters)
        self.vars = vars
        self.templates = templates

    def document(self, path: PathType, env: dict) -> dict:
        """Document a directory or file path.

        Arguments:
            path: Directory or file path to document.
            env: Base environment for substitutions.

        Returns:
            A dict mapping template names to JSON-LD documents.
            If `path` doesn't matche the pattern an empty dict is returned.
        """
        docs = {}
        if r := self.pattern.parse(str(path)):
            e = env.copy()
            e.update(r.named)
            p = Path(e.get("rootdir", ".")) / path
            if p.exists():
                ctime = datetime.fromtimestamp(p.stat().st_ctime).isoformat()
                mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
            else:
                ctime = mtime = ""
            e.setdefault("fullpath", str(p))
            e.setdefault("escapedpath", str(p).replace(" ", "%20"))
            e.setdefault("filename", p.name)
            e.setdefault("dirname", str(p.parent))
            e.setdefault("ctime", ctime)
            e.setdefault("mtime", mtime)
            e.setdefault("pattern", self.pattern.format)
            e.update({k: substitute(v, e) for k, v in self.vars.items() if v})
            for name, template in self.templates.items():
                docs[name] = template.substitute(e)
        return docs


class Treeweaver:
    """Class for documenting a directory structure."""

    def __init__(
        self,
        configfile: PathType,
        rootdir: Optional[PathType] = None,
    ) -> None:
        self.env: dict = {}
        self.templates: dict = {}
        self.patterns: list = []
        self.exclude: list = []
        newroot = Path(rootdir) if rootdir else Path(configfile).parent
        self.env["rootdir"] = str(newroot)
        self.parse_conf(configfile)

    def parse_conf(self, yamlfile: PathType) -> None:
        """Parses a treeweaver YAML configuration and updating the
        environment and templates, while replacing the patterns."""
        with open(yamlfile, "r", encoding="utf-8") as f:
            d = yaml.safe_load(f)
            self.env.update(d.get("environment", {}))
            templates = d.get("templates", {})
            self.templates.update(
                {name: Template(name, v) for name, v in templates.items()}
            )
            self.exclude.extend(d.get("exclude", ()))
            self.patterns = []
            for p in d.get("patterns", ()):
                # pylint: disable=invalid-name
                pattern, updates = next(iter(p.items()))
                vars = updates.get("vars", {})
                appliesTo = updates.get("appliesTo", self.templates.keys())
                templates = {name: self.templates[name] for name in appliesTo}
                self.patterns.append(Pattern(pattern, vars, templates))

    def document_path(self, path: PathType) -> dict:
        """Document a directory or file path.

        Arguments:
            path: Directory or file path to document.

        Returns:
            A dict mapping template names to JSON-LD documents.
        """
        docs = defaultdict(list)
        for pattern in self.patterns:
            for k, v in pattern.document(path, self.env).items():
                docs[k].append(v)
        return dict(docs)

    def document(self, rootdir: PathType) -> dict:
        """Document a directory tree.

        Arguments:
            rootdir: Root directory of directory tree to document.

        Returns:
            A dict mapping template names to JSON-LD documents.
        """
        root = Path(rootdir).resolve()
        docs = defaultdict(list)
        self.env["rootdir"] = root
        for path in root.rglob("*"):
            skip = False
            for exclude_pattern in self.exclude:
                if path.match(exclude_pattern):
                    skip = True
            if not skip:
                relpath = path.relative_to(root)
                for k, v in self.document_path(relpath).items():
                    docs[k].extend(v)
        return dict(docs)

    def totables(
        self, rootdir: PathType, oldtables: Optional[Tables] = None
    ) -> Tables:
        """Create table documentation of directory tree.

        Processes all templates from the documented directory tree and
        converts them into a Tables collection for export or further
        processing.

        Arguments:
            rootdir: Root directory of the directory tree to document.
            oldtables: Old versions of the generated tables. If given,
                columns in `oldtables` that doesn't exists in the generated
                tables will be included in the generated tables.

        Returns:
            A Tables object containing one table per template type.
        """
        tables = Tables()
        for name, docs in self.document(rootdir).items():
            if oldtables is None:
                oldtable = None
            elif len(oldtables) == 1:
                oldtable = oldtables[0]
            elif name in oldtables:
                oldtable = oldtables[name]
            else:
                oldtable = None
            table = totable(docs, name=name, oldtable=oldtable)
            tables.append(table)
        return tables

    def savedoc(
        self,
        rootdir: PathType,
        path: PathType,
        format: Optional[str] = None,  # pylint: disable=redefined-builtin
        mode: str = "update",
        **kwargs,
    ) -> None:
        """Document a directory tree and save created tables to file.

        Documents a directory tree and writes the results to a file
        in the specified format (or inferred from the file extension).

        Arguments:
            rootdir: Root directory of the directory tree to document.
            path: Output path. Format is inferred from the file extension
                unless explicitly provided via `format`.
            format: Output format. Any format supported by tabular.
                Single-file formats: xlsx, json
                Multi-file formats: csv
                If not provided, format is inferred from `path` file extension.
            mode: Either "overwrite" or "update". If "overwrite", the
                destination is overwritten. If "update", columns in the
                destination that doesn't exists in the generated table
                will be included in the generated table.
            **kwargs: Additional keyword arguments passed to the Tables.write()
                method.
        """
        singlefile_formats = set(["csv"])
        p: Path = Path(path)
        if format is None:
            if p.is_dir():
                raise ValueError(
                    "`format` is required when `path` is a directory"
                )
            format = p.suffix.lstrip(".")
        if mode == "update" and p.exists():
            if p.is_dir() and format.lower() in singlefile_formats:
                oldtables = Tables()
                for filename in p.glob(f"*.{format}"):
                    oldtables.append(Tables.read(filename))
            else:
                oldtables = tabular.io.read(p, format=format, **kwargs)
            tables = self.totables(rootdir, oldtables=oldtables)
        else:
            tables = self.totables(rootdir)
        tables.write(p, format=format, **kwargs)


def totable(
    dicts: list,
    name: Optional[str] = None,
    indexcolumn: Optional[str] = "@id",
    oldtable: Optional[Table] = None,
) -> Table:
    """Convert a list of dictionaries to a Table.

    Transforms a flat list of dictionaries into a Table object with
    consistent column ordering. Missing values in dictionaries are
    represented as None in their corresponding cells.

    Arguments:
        dicts: List of dictionaries to convert. All values should be
            JSON-compatible (str, int, float, bool, None, list, dict).
        name: Optional name for the resulting table. Defaults to None.
        indexcolumn: Name of index column. All values in the index column
            must be unique. If more than one row has the index column value,
            only the last of these rows will be included in the table.
        oldtable: Old version of the generated table. If given,
            columns in `oldtable` that doesn't exists in the generated
            table will be included in the generated table.
            Requires that `indexcolumn` is given.

    Returns:
        A Table object with headers from all unique keys across the input
        dictionaries, and rows in the order of the input list.
    """
    # headers: dict = {}  # use dict instead of set to keep ordering
    dicts = list(dicts)  # in case dicts is a iterator
    headers = {}
    for d in dicts:
        headers.update({k: True for k in d.keys()})

    if indexcolumn:
        if oldtable:
            heads = {h: False for h in oldtable.headers}
            heads.update(headers)
            headers = heads
            dl = oldtable.to_dict_list()
            oldcols = {
                d[indexcolumn]: {h: d.get(h) for h in heads if h} for d in dl
            }
            columns: dict[str, dict] = {}
            for d in dicts:
                k = d[indexcolumn]
                columns[k] = {
                    h: d.get(h) if v else oldcols.get(k, {}).get(h)
                    for h, v in headers.items()
                }
        else:
            columns: dict[str, dict] = {  # type: ignore[no-redef]
                d[indexcolumn]: {h: d.get(h) for h in headers} for d in dicts
            }
        dicts = list(columns.values())
    elif oldtable:
        raise ValueError("The `oldtable` argument requires `indexcolumn`.")

    rows = [[d.get(h) for h in headers] for d in dicts]
    return Table(name=name, headers=list(headers.keys()), rows=rows)


def substitute(stencil: ValueType, env: dict) -> ValueType:
    """Return stencil with substitutions applied from `env`."""
    if isinstance(stencil, (bool, int, float, None.__class__)):
        return stencil
    if isinstance(stencil, list):
        return [substitute(element, env) for element in stencil if element]
    if isinstance(stencil, dict):
        return {k: substitute(v, env) for k, v in stencil.items()}
    if isinstance(stencil, str):
        return stencil.format(**env) if stencil else None
    raise TypeError("Unsupported stencil type:", type(stencil))


def main():
    """Main function for the command-line interface."""
    parser = argparse.ArgumentParser(
        description="Discover datadoc entries from a structured directory."
    )
    parser.add_argument(
        "rootdir",
        help="Root directory of the file structure to be documented.",
    )
    parser.add_argument(
        "--configfile",
        "-c",
        help=(
            "Configuration YAML file. Default is `treeweaver2.yaml` in "
            "`rootdir`."
        ),
    )
    parser.add_argument(
        "--format",
        "-f",
        help=(
            "Output format. Any format supported by tabular.\n"
            "Single-file formats: xlsx, json\n"
            "Multi-file formats: csv"
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        help=(
            "Output. Should be a file path for single-file formats and "
            "a directory for multi-file formats."
        ),
    )
    args = parser.parse_args()

    tw = Treeweaver(args.configfile)
    tw.savedoc(rootdir=args.rootdir, path=args.output, format=args.format)


if __name__ == "__main__":
    main()
