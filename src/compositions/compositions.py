"""Parse composition.csv files.

Compositions has a more complex representation in RDF and requires
special handling.

"""

import argparse
import csv
import warnings
from pathlib import Path
from typing import Optional, Sequence, Union

from tripper import Session, Triplestore
from tripper.datadoc import store

from compositions.utils import (
    EMMO,
    atomic_masses,
    atomic_names,
    get_species_iri,
)

__all__ = ("parse", "main")

TEMPLATE_URL = (
    "https://github.com/SINTEF/physmet-data-documentation-templates/"
    "blob/main/templates/compositions.csv"
)


def normalize_unit(unit: str) -> str:
    """Normalise composition unit. Raises ValueError if the unit is unknown."""
    if unit in ("wt%", "weight%", "weight-percent", "mass%"):
        return "wt%"
    if unit in ("at%", "atom%", "atom-percent"):
        return "at%"
    if unit in ("wtfrac", "wt-fraction", "weight-fraction"):
        return "wtfrac"
    if unit in ("atfrac", "at-fraction", "atom-fraction"):
        return "atfrac"
    raise ValueError(f"unknown composition unit: {unit}")


def _asfloat(
    values: Sequence[Union[str, float]], balance: float = 100
) -> list[float]:
    """Returns `v` as a list of floating point numbers."""
    ib = -1
    vsum = 0.0
    vals = []
    for i, v in enumerate(values):
        if isinstance(v, str) and v.startswith("bal"):
            ib = i
            vals.append(0.0)
        else:
            val = float(v) if v else 0.0
            vals.append(val)
            vsum += val
    if ib > -1:
        vals[ib] = balance - vsum

    # Check ranges
    for i, v in enumerate(vals):
        if v < 0 or v > balance:
            raise ValueError(f"composition {i} is out of range: {v}")
    if vsum > balance:
        raise ValueError(f"composition sum out of range: {vsum}")

    return vals


def to_wtpercent(
    values: Sequence[Union[str, float]],
    symbols: Sequence[str],
    unit: Optional[str] = None,
) -> list[float]:
    """Convert `values` from unit `unit` to 'wt%'.

    Args:
        values: List of composition values in units of `unit`.
            An element starting with "bal", will be adjusted such that the
            returned sum is 100 wt%.
        symbols: Chemical symbols corresponding to `values`.
        unit: Unit of `values`.

    Returns:
        Composition converted to wt%.

    """
    unit = normalize_unit(unit) if unit else "wt%"
    vals = _asfloat(values, balance=100 if unit.endswith("%") else 1)
    if unit == "wt%":
        return vals
    if unit == "at%":
        t = sum(v * atomic_masses[s] for v, s in zip(vals, symbols))
        return [100 * v * atomic_masses[s] / t for v, s in zip(vals, symbols)]
    if unit == "wtfrac":
        return [100 * v for v in vals]
    if unit == "atfrac":
        t = sum(v * atomic_masses[s] for v, s in zip(vals, symbols))
        return [100 * v * atomic_masses[s] / t for v, s in zip(vals, symbols)]
    raise ValueError(f"not a normalised unit: {unit}")


def from_wtpercent(
    values: Sequence[Union[str, float]],
    symbols: Sequence[str],
    unit: Optional[str] = None,
) -> list[float]:
    """Convert `values` from unit 'wt%' to `unit`.

    Args:
        values: List of composition values in units of wt%.
            An element starting with "bal", will be adjusted such that the
            returned sum is 100%.
        symbols: Chemical symbols corresponding to `values`.
        unit: Composition unit to convert `values` to.

    Returns:
        Composition in units of `unit`.

    """
    unit = normalize_unit(unit) if unit else "wt%"
    vals = _asfloat(values, balance=100)
    if unit == "wt%":
        return vals
    if unit == "at%":
        t = sum(v / atomic_masses[s] for v, s in zip(vals, symbols))
        return [100 * v / atomic_masses[s] / t for v, s in zip(vals, symbols)]
    if unit == "wtfrac":
        return [0.01 * v for v in vals]
    if unit == "atfrac":
        t = sum(v / atomic_masses[s] for v, s in zip(vals, symbols))
        return [v / atomic_masses[s] / t for v, s in zip(vals, symbols)]
    raise ValueError(f"not a normalised unit: {unit}")


def parse(filename: Path, **spec) -> list:
    """Parse a CSV file with chemical compositions.

    Args:
        filename: CSV file to parse.
        spec: Keyword arguments to csv.reader() for specifying how `filename`
            is formatted.

    Returns:
        List of compositions correctly represented according to EMMO.
    """
    # pylint: disable=too-many-locals
    conf = spec if spec else {}
    with open(filename, "rt", newline="", encoding="utf8") as csvfile:
        reader = csv.reader(csvfile, **conf)
        header = [h.strip() for h in next(reader)]

        # Array of indices for columns with chemical compositions
        icomp = [
            i for i, h in enumerate(header) if h.split("[")[0] in atomic_names
        ]

        # Chemical symbols
        symbols = [header[i].split("[", 1)[0] for i in icomp]

        # Determine unit
        unitname = None
        for i in icomp:
            h = header[i]
            if "[" in h:
                u = normalize_unit(h.split("[")[1].rstrip("]"))
            else:
                warnings.warn(f"No unit provided for '{h}', assuming wt%")
                u = normalize_unit("wt%")
            if unitname is None:
                unitname = u
            elif u != unitname:
                raise ValueError("All compositions must have the same unit")
        # quantity, unit = get_unit(unitname)
        quantity, unit = EMMO.MassFraction, EMMO.WeightPercent

        compositions = []
        for row in reader:
            d = {
                "@id": [cell for h, cell in zip(header, row) if h == "@id"][0],
                "@type": EMMO.ChemicalComposition,
                "hasSingleComponentComposition": [],
            }
            values = to_wtpercent([row[i] for i in icomp], symbols, unitname)
            for symbol, v in zip(symbols, values):
                species = get_species_iri(symbol)
                d["hasSingleComponentComposition"].append(
                    {
                        "@type": EMMO.SingleComponentComposition,
                        "hasSpeciesPart": species,
                        "hasQuantityPart": {
                            "@type": quantity,
                            "hasMeasurementUnit": unit,
                            "dataValue": v,
                        },
                    }
                )
            compositions.append(d)

    return compositions


def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Converts CSV with chemical composition to RDF.",
        epilog="The output can be specified with either the "
        "--triplestore/--config options or with the --backend/"
        "--base-iri/--database/--package options.",
    )
    parser.add_argument(
        "csvfile",
        metavar="PATH",
        help=(
            "CSV file with compositions. For an example file, see "
            f"{TEMPLATE_URL}"
        ),
    )
    parser.add_argument(
        "--config",
        "-c",
        metavar="PATH",
        type=Path,
        help="Tripper session configuration file.",
    )
    parser.add_argument(
        "--triplestore",
        "-t",
        metavar="NAME",
        help=(
            "Name of triplestore to connect to. The name should be "
            "defined in the session configuration file."
        ),
    )
    parser.add_argument(
        "--backend",
        "-b",
        default="rdflib",
        help=(
            'Triplestore backend to use. Defaults to "rdflib" - an '
            "in-memory rdflib triplestore, that can be pre-loaded with "
            "--parse."
        ),
    )
    parser.add_argument(
        "--base-iri",
        "-B",
        help="Base IRI of the triplestore.",
    )
    parser.add_argument(
        "--database",
        "-d",
        help="Name of database to connect to (for backends supporting it).",
    )
    parser.add_argument(
        "--package",
        help="Only needed when `backend` is a relative module.",
    )
    parser.add_argument(
        "--parse",
        "-p",
        metavar="LOCATION",
        help="Load triplestore from this location.",
    )
    parser.add_argument(
        "--parse-format",
        "-F",
        help="Used with `--parse`. Format to use when parsing triplestore.",
    )
    parser.add_argument(
        "--prefix",
        "-P",
        action="append",
        metavar="PREFIX=URL",
        help=(
            "Namespace prefix to bind to the triplestore. "
            "This option can be given multiple times."
        ),
    )

    args = parser.parse_args()

    if args.triplestore:
        session = Session(config=args.config)
        ts = session.get_triplestore(args.triplestore)
    else:
        ts = Triplestore(
            backend=args.backend,
            base_iri=args.base_iri,
            database=args.database,
            package=args.package,
        )

    if args.parse:
        ts.parse(args.parse, format=args.parse_format)

    if args.prefix:
        for token in args.prefix:
            prefix, ns = token.split("=", 1)
            ts.bind(prefix, ns)

    compositions = parse(args.csvfile)
    store(ts, compositions)


if __name__ == "__main__":
    main()
