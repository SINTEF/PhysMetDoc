# Compositions
A simplified user-friendly table format is provided for specifying alloy compositions.
An example table may look like this:

| @id        | Fe[wt%] | Mn[wt%] | C[wt%] | B[wt%] | Si[wt%] | Al[wt%] | Ti[wt%] | Ca[wt%] |
|------------|---------|---------|--------|--------|---------|---------|---------|---------|
| avb:JM     | 57      | 13      | 24     | 6      |         |         |         |         |
| elkem:FeSi | 25.06   | 0.13    |        |        | bal     | 0.81    | 0.12    | 0.12    |

**Notes**:
* @id is (as usual) a unique id for a given composition.
* @type is implicitly assumed to be emmo:ChemicalComposition.
* The header of columns specifying chemical composition should start with a chemical symbol optionally followed by a square bracket with the unit. Default unit is "wt%".
* Supported units include:
  - weight percent: wt%, wt-percent, weight-percent, mass% (default)
  - atom percent: at%, at-percent
  - weight fraction: wtfrac, wt-fraction, weight-fraction
  - atom fraction: atfrac, at-fraction, atom-fraction
* A composition value starting with "bal" means that the value in this cell is adjusted such that the total composition is 100%.

When parsed, it will produce an RDF representation looking like the following:

![RDF representation](figs/compositions-rdf.png)


## Usage example
This example reads a composition file and serialises it in turtle.
The context file could e.g. be the one found in [context/context.json](#../context/context.json).

```python
from tripper import Triplestore
from tripper.datadoc import get_context, store
from parse_compositions import parse

# Parse compositions
compositions = parse("compositions.csv")

# Load local context
context = get_context("context/context.json")

# Save compositions to triplestore and write turtle file
ts = Triplestore(backend="rdflib")
store(ts, compositions, context=context)
ts.serialize("compositions.ttl")
```
