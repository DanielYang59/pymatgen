from __future__ import annotations

import gzip
import json
import os
import random

from tqdm import tqdm

from pymatgen.core import Lattice, Structure

# Global config
N_STRUCTURES = 10_000_000  # Number of structures to generate
OUTPUT_DIR = "dummy_structures"  # Output directory
NUM_ATOMS_PER_STRUCTURE = (10, 100)  # Min and max atoms per structure (inclusive)


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


def save_structure_to_gzipped_json(structure, filepath):
    with gzip.open(filepath, "wt", encoding="utf-8") as f:
        json.dump(structure.as_dict(), f, indent=2)


def generate_and_save_structures(n, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for i in tqdm(range(1, n + 1), desc="Generating structures", unit="struct"):
        structure = generate_dummy_structure()
        filename = f"structure_{i:04d}.json.gz"
        filepath = os.path.join(output_dir, filename)
        save_structure_to_gzipped_json(structure, filepath)


if __name__ == "__main__":
    generate_and_save_structures(N_STRUCTURES, OUTPUT_DIR)
