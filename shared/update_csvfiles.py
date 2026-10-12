"""Script for lownloading `shared resources.xlsx` from SharePoint and update
the CSV files."""

# pylint: disable=invalid-name

import sys
from pathlib import Path

import keyring
import requests

from tabular import Tables

thisdir = Path(__file__).resolve().parent
xlsxfile = thisdir / "shared_resources.xlsx"


# 1. Paste the direct download URL from SharePoint
# (Tip: In SharePoint, click the file -> Copy link, or find the 'download.aspx'
# URL)
url = (
    "https://studntnu.sharepoint.com/sites/o365_SFIPhysMet/Shared%20Documents/"
    "Reseach%20Areas,%20RA%20(Open%20channel)/"
    "RA%205%20Data,%20sharing%20and%20digital%20platforms/"
    "Datasets/shared_resources.xlsx"
)

# 2. Set up your active session cookies
# To find these:
#   Open DevTools (F12) -> Application/Storage -> Cookies -> SharePoint site
# Store them in your keyring, with `service_name="physmet-shared_resources"`
# and `username` "FedAuth" and "rtFa", respectively
FedAuth = keyring.get_password("physmet-shared_resources", "FedAuth")
rtFa = keyring.get_password("physmet-shared_resources", "rtFa")
if not FedAuth or not rtFa:
    raise PermissionError(
        "Missing 'FedAuth' and 'rtFa' users in your keyring for service "
        "'physmet-shared_resources'. Please add them."
    )
cookies = {
    "FedAuth": FedAuth,
    "rtFa": rtFa,
}

headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

# 3. Download the file into memory
print("Downloading file from SharePoint...")
response = requests.get(url, cookies=cookies, headers=headers, timeout=3)

if response.status_code == 200:
    # 4. Load directly into a Pandas DataFrame without saving to disk
    with open(xlsxfile, "wb") as f:
        f.write(response.content)
else:
    print(f"Failed to download. Status code: {response.status_code}")
    sys.exit(1)


tables = Tables.read(xlsxfile)
for table in tables.tables:
    table.write(thisdir / f"{table.name}.csv", newline="\n")
