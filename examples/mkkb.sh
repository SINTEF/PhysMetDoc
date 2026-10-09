#!/bin/bash
# Script creating a example knowledge base in `examples/kb.ttl`
# documenting test data from Armel and Andreas.

#set -x
set -e

rootdir="$(git rev-parse --show-toplevel)"

tmproot="$rootdir/examples/tmp"
mkdir -p "$tmproot"
datadir="$rootdir/tests/treeweaver/data"
tmpdir="$(mktemp -d --tmpdir=$tmproot tmp.XXXXXX)"
kb="$rootdir/examples/kb.ttl"
prefixfile="$tmpdir/prefixes.json"
context="$rootdir/context/context.json"

# Create prefix file
extract-prefixes \
    -o "$prefixfile" \
    "$rootdir"/shared/{people,projects,organisations}.csv

# Extract data documentation
treeweaver2 "$datadir" -c "$datadir/Armel.yaml" -f csv -o "$tmpdir/Armel"
treeweaver2 "$datadir" -c "$datadir/Andreas.yaml" -f csv -o "$tmpdir/Andreas"

# Create empty knowledge base
rm -f "$kb"
touch "$kb"

# Populate the knowledge base
for csvdir in "$rootdir/shared" "$tmpdir/Armel" "$tmpdir/Andreas"; do
    for csvfile in "$csvdir"/*.csv; do
        if [ $(basename "$csvfile") != "prefixes.csv" ]; then
            datadoc --parse="$kb" add \
                    --context="$prefixfile" \
                    --context="$context" \
                    --dump="$kb" \
                    "$csvfile"
        fi
    done
done

# Clean up temporary files
rm -r "$tmpdir"
