"""Script that updates the PhysMet KG."""

# ruff: noqa: T201

from pathlib import Path

import keyring
import requests
from tripper import EMMO, Triplestore
from tripper.datadoc import TableDoc, get_context

from extract_prefixes import parse
from tabular import Tables
from treeweaver import Treeweaver

rootdir = Path(__file__).resolve().parent.parent
examplesdir = rootdir / "examples"
tmpdir = examplesdir / "tmp"
shared_resources = rootdir / "shared" / "shared_resources.xlsx"
ListSharePoint = tmpdir / "ListSharePoint.xlsx"
kg = rootdir.parent / "PhysMetKnowledgeGraph/" / "kg.ttl"


tmpdir.mkdir(parents=True, exist_ok=True)


# Set up your active session cookies. To find these:
#   - Open DevTools (F12) -> Application/Storage -> Cookies -> SharePoint site
#   - Store the values of FedAuth and rtFa in your keyring.
#     Use service_name="physmet-shared_resources" and `username` "FedAuth"
#     and "rtFa", respectively.
cookies = {
    "FedAuth": keyring.get_password("physmet-shared_resources", "FedAuth"),
    "rtFa": keyring.get_password("physmet-shared_resources", "rtFa"),
}

headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

shared_resources_url = (
    "https://studntnu.sharepoint.com/sites/o365_SFIPhysMet/Shared%20Documents/"
    "Reseach%20Areas,%20RA%20(Open%20channel)/"
    "RA%205%20Data,%20sharing%20and%20digital%20platforms/"
    "Datasets/shared_resources.xlsx"
)
ListSharePoint_url = (
    "https://studntnu.sharepoint.com/sites/o365_SFIPhysMet/Shared%20Documents/"
    "Reseach%20Areas,%20RA%20(Open%20channel)/"
    "RA%205%20Data,%20sharing%20and%20digital%20platforms/"
    "Tools/ListSharePoint.xlsm"
)


def get(url: str, outfile: str | Path) -> None:
    """Download file `url` from SharePoint and store it in `outfile`."""
    print("Downloading file from SharePoint...")
    response = requests.get(url, cookies=cookies, headers=headers, timeout=3)
    if response.status_code == 200:
        with open(outfile, "wb") as f:
            f.write(response.content)
    else:
        response.raise_for_status()


get(shared_resources_url, shared_resources)
get(ListSharePoint_url, ListSharePoint)


# Extract prefixes
extracted_prefixes = {}
shared_tables = Tables.read(shared_resources)
for table in shared_tables.tables:
    filepath = tmpdir / f"{table.name}.csv"
    table.write(filepath, newline="\n")
    if "prefix" in table.headers:
        extracted_prefixes.update(parse(filepath))


# Get context
context = get_context(rootdir / "context" / "context.json", default_theme=None)
context.add_prefixes(extracted_prefixes)
context.add_prefixes({"emmo": EMMO})


# Create triplestore
ts = Triplestore("rdflib")
ts.namespaces["emmo"] = EMMO


# Populate with shared resources
for table in shared_tables.tables:
    if "@id" in table.headers:
        td = TableDoc.parse_csv(tmpdir / f"{table.name}.csv", context=context)
        td.save(ts)

# Populate with documented data
sharepoint_tables = Tables.read(ListSharePoint)
for yamlfile in examplesdir.glob("*.yaml"):
    print("*** Processing yaml file:", yamlfile.name)
    output = tmpdir / f"{yamlfile.stem}.xlsx"
    tw = Treeweaver(yamlfile)
    # This would have been more efficient
    tw.savedoc(source=ListSharePoint, output=output, sheet=yamlfile.stem)
    # tw.savedoc(source=ListSharePoint, output=output)

    tables = Tables.read(output)
    for sheet in tables.names:
        td = TableDoc.parse_excel(output, sheet=sheet, context=context)
        td.save(ts)


# Save triplestore
ts.serialize(kg)
