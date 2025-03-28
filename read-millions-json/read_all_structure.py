from __future__ import annotations

import gzip
import json
import os

from pymatgen.core import Structure


def load_structure_from_gzipped_json(filepath):
    with gzip.open(filepath, "rt", encoding="utf-8") as f:
        struct_dict = json.load(f)
        return Structure.from_dict(struct_dict)


def load_all_structures(directory):
    structures = []
    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".json.gz"):
            filepath = os.path.join(directory, filename)
            try:
                structure = load_structure_from_gzipped_json(filepath)
                structures.append(structure)
                print(f"Loaded: {filename}")
            except Exception as e:
                print(f"Failed to load {filename}: {e}")
    return structures


if __name__ == "__main__":
    INPUT_DIR = "dummy_structures"  # Change if needed
    structures = load_all_structures(INPUT_DIR)
    print(f"\nTotal structures loaded: {len(structures)}")
