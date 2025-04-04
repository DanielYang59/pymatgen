from __future__ import annotations

import gzip
import os
import random

import orjson
import json
from line_profiler import profile

from pymatgen.core import Lattice, Structure

N_STRUCTURES = 1_000  # Number of structures to generate
OUTPUT_DIR = "dummy_structures"  # Output directory
NUM_ATOMS_PER_STRUCTURE = (10, 100)


def generate_dummy_structure():
    # Random cubic lattice
    a = random.uniform(3.5, 6.0)
    lattice = Lattice.cubic(a)

    # Random number of atoms
    num_atoms = random.randint(*NUM_ATOMS_PER_STRUCTURE)

    # Random element(s)
    possible_elements = ["Si", "Ge", "Ga", "As", "In", "P", "Al", "N"]
    species = [random.choice(possible_elements) for _ in range(num_atoms)]
    coords = [[random.uniform(0, 1) for _ in range(3)] for _ in range(num_atoms)]

    return Structure(lattice, species, coords)


@profile
def generate_and_save_structures(n, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for i in range(n):
        structure = generate_dummy_structure()
        filename = f"structure_{i:04d}.json.gz"
        filepath = os.path.join(output_dir, filename)

        # with gzip.open(filepath, "wb") as f:
        #     dct = structure.as_dict()
        #     f.write(orjson.dumps(dct))

        with gzip.open(filepath, "wt", encoding="utf-8") as f:
            dct  = structure.as_dict()
            json.dump(dct, f)


if __name__ == "__main__":
    generate_and_save_structures(N_STRUCTURES, OUTPUT_DIR)
