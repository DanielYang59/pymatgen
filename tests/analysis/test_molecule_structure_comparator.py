from __future__ import annotations

import pytest

from pymatgen.analysis.molecule_structure_comparator import MoleculeStructureComparator
from pymatgen.core.structure import Molecule
from pymatgen.io.qchem.outputs import QCOutput
from pymatgen.util.testing import TEST_FILES_DIR

__author__ = "xiaohuiqu"


TEST_DIR = f"{TEST_FILES_DIR}/analysis/structural_change"


class TestMoleculeStructureComparator:
    def test_are_equal(self):
        msc1 = MoleculeStructureComparator()
        mol1 = Molecule.from_file(f"{TEST_DIR}/t1.xyz")
        mol2 = Molecule.from_file(f"{TEST_DIR}/t2.xyz")
        mol3 = Molecule.from_file(f"{TEST_DIR}/t3.xyz")
        assert not msc1.are_equal(mol1, mol2)
        assert msc1.are_equal(mol2, mol3)
        thio1 = Molecule.from_file(f"{TEST_DIR}/thiophene1.xyz")
        thio2 = Molecule.from_file(f"{TEST_DIR}/thiophene2.xyz")
        # noinspection PyProtectedMember
        msc2 = MoleculeStructureComparator(priority_bonds=msc1._get_bonds(thio1))
        assert msc2.are_equal(thio1, thio2)
        hal1 = Molecule.from_file(f"{TEST_DIR}/molecule_with_halogen_bonds_1.xyz")
        hal2 = Molecule.from_file(f"{TEST_DIR}/molecule_with_halogen_bonds_2.xyz")
        msc3 = MoleculeStructureComparator(priority_bonds=msc1._get_bonds(hal1))
        assert msc3.are_equal(hal1, hal2)

    def test_get_bonds(self):
        mol1 = Molecule.from_file(f"{TEST_DIR}/t1.xyz")
        msc = MoleculeStructureComparator()
        # noinspection PyProtectedMember
        bonds = msc._get_bonds(mol1)
        bonds_ref = [
            (0, 1),
            (0, 2),
            (0, 3),
            (0, 23),
            (3, 4),
            (3, 5),
            (5, 6),
            (5, 7),
            (7, 8),
            (7, 9),
            (7, 21),
            (9, 10),
            (9, 11),
            (9, 12),
            (12, 13),
            (12, 14),
            (12, 15),
            (15, 16),
            (15, 17),
            (15, 18),
            (18, 19),
            (18, 20),
            (18, 21),
            (21, 22),
            (21, 23),
            (23, 24),
            (23, 25),
        ]
        assert bonds == bonds_ref
        mol2 = Molecule.from_file(f"{TEST_DIR}/MgBH42.xyz")
        bonds = msc._get_bonds(mol2)
        assert bonds == [
            (1, 3),
            (2, 3),
            (3, 4),
            (3, 5),
            (6, 8),
            (7, 8),
            (8, 9),
            (8, 10),
        ]
        msc = MoleculeStructureComparator(ignore_ionic_bond=False)
        bonds = msc._get_bonds(mol2)
        assert bonds == [
            (0, 1),
            (0, 2),
            (0, 3),
            (0, 5),
            (0, 6),
            (0, 7),
            (0, 8),
            (0, 9),
            (1, 3),
            (2, 3),
            (3, 4),
            (3, 5),
            (6, 8),
            (7, 8),
            (8, 9),
            (8, 10),
        ]

        mol1 = Molecule.from_file(f"{TEST_DIR}/molecule_with_halogen_bonds_1.xyz")
        msc = MoleculeStructureComparator()
        # noinspection PyProtectedMember
        bonds = msc._get_bonds(mol1)
        assert bonds == [
            (0, 12),
            (0, 13),
            (0, 14),
            (0, 15),
            (1, 12),
            (1, 16),
            (1, 17),
            (1, 18),
            (2, 4),
            (2, 11),
            (2, 19),
            (3, 5),
            (3, 10),
            (3, 20),
            (4, 6),
            (4, 10),
            (5, 11),
            (5, 12),
            (6, 7),
            (6, 8),
            (6, 9),
        ]

    def test_to_and_from_dict(self):
        msc1 = MoleculeStructureComparator()
        d1 = msc1.as_dict()
        d2 = MoleculeStructureComparator.from_dict(d1).as_dict()
        assert d1 == d2
        thio1 = Molecule.from_file(f"{TEST_DIR}/thiophene1.xyz")
        # noinspection PyProtectedMember
        msc2 = MoleculeStructureComparator(bond_length_cap=0.2, priority_bonds=msc1._get_bonds(thio1), priority_cap=0.5)
        d1 = msc2.as_dict()
        d2 = MoleculeStructureComparator.from_dict(d1).as_dict()
        assert d1 == d2

    @pytest.mark.xfail(reason="TODO: need someone to fix this")
    def test_structural_change_in_geom_opt(self):
        qcout_path = f"{TEST_DIR}/mol_1_3_bond.qcout"
        qcout = QCOutput(qcout_path)
        mol1 = qcout.data[0]["molecules"][0]
        mol2 = qcout.data[0]["molecules"][-1]
        priority_bonds = [
            [0, 1],
            [0, 2],
            [1, 3],
            [1, 4],
            [1, 7],
            [2, 5],
            [2, 6],
            [2, 8],
            [4, 6],
            [4, 10],
            [6, 9],
        ]
        msc = MoleculeStructureComparator(priority_bonds=priority_bonds)
        assert msc.are_equal(mol1, mol2)

    def test_get_13_bonds(self):
        priority_bonds = [
            [0, 1],
            [0, 2],
            [1, 3],
            [1, 4],
            [1, 7],
            [2, 5],
            [2, 6],
            [2, 8],
            [4, 6],
            [4, 10],
            [6, 9],
        ]
        bonds_13 = MoleculeStructureComparator.get_13_bonds(priority_bonds)
        assert bonds_13 == (
            (0, 3),
            (0, 4),
            (0, 5),
            (0, 6),
            (0, 7),
            (0, 8),
            (1, 2),
            (1, 6),
            (1, 10),
            (2, 4),
            (2, 9),
            (3, 4),
            (3, 7),
            (4, 7),
            (4, 9),
            (5, 6),
            (5, 8),
            (6, 8),
            (6, 10),
        )
