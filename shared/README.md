# Shared resources
Documentation of shared resources.

> [!IMPORTANT]
> Don't edit the CSV files in this folder manually!

The CSV files are generated from this [Excel spreadsheet] using the script [update_csvfiles.py].

Each row in a CSV template documents an individual, class or property that will be added to the knowledge base.

The meaning of the CSV files are as follows:
- **[accessRights.csv](accessRights.csv)**: Pre-defined levels of access rights for datasets (DCAT-AP).
- **[availability.csv](availability.csv)**: Pre-defined levels of availability (DCAT-AP).
- **[equipment.csv](equipment.csv)**: Equipment for materials processing, characterisation instruments, etc.
- **[licenses.csv](licenses.csv)**: Licenses used in SFI PhysMet.
- **[organisations.csv](organisations.csv)**: Organisations. May e.g. be referred to as the owner of a dataset.
- **[people.csv](people.csv)**: People. May be a contact point for a sample, dataset or equipment or the operator of a process.
- **[projects.csv](projects.csv)**: Projects. May e.g. be referred to as the creator of a sample or dataset.
- **[software.csv](software.csv)**: Software used for driving a process.
- **[techniques.csv](techniques.csv)**: Characterisation techniques (documented as classes)

The file [prefixes.csv](prefixes.csv) does not document a resource, but defines prefixes used for the data documentation within SFI PhysMet.


[Excel spreadsheet]: https://studntnu.sharepoint.com/sites/o365_SFIPhysMet/Shared%20Documents/Reseach%20Areas,%20RA%20(Open%20channel)/RA%205%20Data,%20sharing%20and%20digital%20platforms/Datasets/shared_resources.xlsx
[update_csvfiles.py]: update_csvfiles.py
[accessRights.csv]: accessRights.csv
[availability.csv]: availability.csv
[equipment.csv]: http://publications.europa.eu/resource/authority/planned-availability/
