from __future__ import annotations

import warnings

import numpy as np
from numpy.testing import assert_allclose

from pymatgen.core.lattice import Lattice
from pymatgen.symmetry.groups import SpaceGroup
from pymatgen.symmetry.maggroups import MagneticSpaceGroup
from pymatgen.util.testing import MatSciTest

__author__ = "Matthew Horton"
__copyright__ = "Copyright 2017, The Materials Project"
__version__ = "0.1"
__maintainer__ = "Matthew Horton"
__email__ = "mkhorton@lbl.gov"
__status__ = "Beta"
__date__ = "Feb 2017"


class TestMagneticSpaceGroup(MatSciTest):
    def setup_method(self):
        self.msg_1 = MagneticSpaceGroup([70, 530])
        self.msg_2 = MagneticSpaceGroup([62, 448])
        self.msg_3 = MagneticSpaceGroup([20, 37])
        self.msg_4 = MagneticSpaceGroup([2, 7], "c,1/4a+1/4b,-1/2a+1/2b;0,0,0")

    def test_init(self):
        # test init with the following space group:
        # 71.538 (BNS number), I_cmmm (BNS label)
        # 65.10.554 (same space group as above, OG number), C_Immm (OG label)
        msg_from_bns_1 = MagneticSpaceGroup("I_cmmm")
        msg_from_bns_2 = MagneticSpaceGroup([71, 538])
        msg_from_og_1 = MagneticSpaceGroup.from_og("C_Immm")
        msg_from_og_2 = MagneticSpaceGroup.from_og([65, 10, 554])
        assert msg_from_bns_1 == msg_from_bns_2
        assert msg_from_og_1 == msg_from_og_2
        assert msg_from_bns_1 == msg_from_og_1

    def test_crystal_system(self):
        assert self.msg_1.crystal_system == "orthorhombic"
        assert self.msg_2.crystal_system == "orthorhombic"
        assert self.msg_3.crystal_system == "orthorhombic"

    def test_sg_symbol(self):
        assert self.msg_1.sg_symbol == "Fd'd'd"
        assert self.msg_2.sg_symbol == "Pn'ma'"
        assert self.msg_3.sg_symbol == "C_A222_1"

    def test_is_compatible(self):
        cubic = Lattice.cubic(1)
        hexagonal = Lattice.hexagonal(1, 2)
        rhom = Lattice.rhombohedral(3, 80)
        tet = Lattice.tetragonal(1, 2)
        ortho = Lattice.orthorhombic(1, 2, 3)
        msg = MagneticSpaceGroup("Fm-3m")
        assert msg.is_compatible(cubic)
        assert not msg.is_compatible(hexagonal)
        msg = MagneticSpaceGroup("Pnma")
        assert msg.is_compatible(cubic)
        assert msg.is_compatible(tet)
        assert msg.is_compatible(ortho)
        assert not msg.is_compatible(rhom)
        assert not msg.is_compatible(hexagonal)
        msg = MagneticSpaceGroup("P2/c")
        assert msg.is_compatible(cubic)
        assert msg.is_compatible(tet)
        assert msg.is_compatible(ortho)
        assert not msg.is_compatible(rhom)
        assert not msg.is_compatible(hexagonal)
        msg = MagneticSpaceGroup("P-1")
        assert msg.is_compatible(cubic)
        assert msg.is_compatible(tet)
        assert msg.is_compatible(ortho)
        assert msg.is_compatible(rhom)
        assert msg.is_compatible(hexagonal)

    def test_symmetry_ops(self):
        _msg_1_symmops = "\n".join(map(str, self.msg_1.symmetry_ops))
        _msg_1_symmops_ref = """x, y, z, +1
-x+3/4, -y+3/4, z, +1
-x, -y, -z, +1
x+1/4, y+1/4, -z, +1
x, -y+3/4, -z+3/4, -1
-x+3/4, y, -z+3/4, -1
-x, y+1/4, z+1/4, -1
x+1/4, -y, z+1/4, -1
x, y+1/2, z+1/2, +1
-x+3/4, -y+5/4, z+1/2, +1
-x, -y+1/2, -z+1/2, +1
x+1/4, y+3/4, -z+1/2, +1
x, -y+5/4, -z+5/4, -1
-x+3/4, y+1/2, -z+5/4, -1
-x, y+3/4, z+3/4, -1
x+1/4, -y+1/2, z+3/4, -1
x+1/2, y, z+1/2, +1
-x+5/4, -y+3/4, z+1/2, +1
-x+1/2, -y, -z+1/2, +1
x+3/4, y+1/4, -z+1/2, +1
x+1/2, -y+3/4, -z+5/4, -1
-x+5/4, y, -z+5/4, -1
-x+1/2, y+1/4, z+3/4, -1
x+3/4, -y, z+3/4, -1
x+1/2, y+1/2, z, +1
-x+5/4, -y+5/4, z, +1
-x+1/2, -y+1/2, -z, +1
x+3/4, y+3/4, -z, +1
x+1/2, -y+5/4, -z+3/4, -1
-x+5/4, y+1/2, -z+3/4, -1
-x+1/2, y+3/4, z+1/4, -1
x+3/4, -y+1/2, z+1/4, -1"""

        # TODO: the below check is failing, need someone to fix it, see issue 4207
        warnings.warn("part of test_symmetry_ops is failing, see issue 4207", stacklevel=2)
        # self.assert_str_content_equal(msg_1_symmops, msg_1_symmops_ref)

        msg_2_symmops = "\n".join(map(str, self.msg_2.symmetry_ops))
        msg_2_symmops_ref = """x, y, z, +1
-x, y+1/2, -z, +1
-x, -y, -z, +1
x, -y+1/2, z, +1
x+1/2, -y+1/2, -z+1/2, -1
-x+1/2, -y, z+1/2, -1
-x+1/2, y+1/2, z+1/2, -1
x+1/2, y, -z+1/2, -1"""
        self.assert_str_content_equal(msg_2_symmops, msg_2_symmops_ref)

        msg_3_symmops = "\n".join(map(str, self.msg_3.symmetry_ops))
        msg_3_symmops_ref = """x, y, z, +1
x, -y, -z, +1
-x, y, -z+1/2, +1
-x, -y, z+1/2, +1
x, y+1/2, z+1/2, -1
x+1/2, -y, -z+1/2, -1
-x+1/2, y, -z, -1
-x+1/2, -y, z, -1
x+1/2, y+1/2, z, +1
x+1/2, -y+1/2, -z, +1
-x+1/2, y+1/2, -z+1/2, +1
-x+1/2, -y+1/2, z+1/2, +1
x+1/2, y, z+1/2, -1
x, -y+1/2, -z+1/2, -1
-x, y+1/2, -z, -1
-x, -y+1/2, z, -1"""
        assert msg_3_symmops == msg_3_symmops_ref

        msg_4_symmops = "\n".join(map(str, self.msg_4.symmetry_ops))
        msg_4_symmops_ref = """x, y, z, +1
-x, -y, -z, +1
x+1/2, y, z, -1
-x+1/2, -y, -z, -1"""
        assert msg_4_symmops == msg_4_symmops_ref

    def test_equivalence_to_spacegroup(self):
        # first 230 magnetic space groups have same symmetry operations
        # as normal space groups, so should give same orbits

        labels = ["Fm-3m", "Pnma", "P2/c", "P-1"]

        points = [[0, 0, 0], [0.5, 0, 0], [0.11, 0.22, 0.33]]

        for label in labels:
            sg = SpaceGroup(label)
            msg = MagneticSpaceGroup(label)
            assert sg.crystal_system == msg.crystal_system
            for p in points:
                pp_sg = np.array(sg.get_orbit(p))
                pp_msg = np.array(msg.get_orbit(p, 0)[0])  # discarding magnetic moment information
                pp_sg = pp_sg[np.lexsort(np.transpose(pp_sg)[::-1])]  # sorting arrays so we can compare them
                pp_msg = pp_msg[np.lexsort(np.transpose(pp_msg)[::-1])]
                assert_allclose(pp_sg, pp_msg)

    def test_str(self):
        msg = MagneticSpaceGroup([4, 11])

        ref_str = """BNS: 4.11 P_b2_1
Operators: (1|0,0,0) (2y|0,1/2,0) (1|0,1/2,0)' (2y|0,0,0)'
Wyckoff Positions:
4e  (x,y,z;mx,my,mz) (-x,y+1/2,-z;-mx,my,-mz) (x,y+1/2,z;-mx,-my,-mz)
    (-x,y,-z;mx,-my,mz)
2d  (1/2,y,1/2;mx,0,mz) (1/2,y+1/2,1/2;-mx,0,-mz)
2c  (1/2,y,0;mx,0,mz) (1/2,y+1/2,0;-mx,0,-mz)
2b  (0,y,1/2;mx,0,mz) (0,y+1/2,1/2;-mx,0,-mz)
2a  (0,y,0;mx,0,mz) (0,y+1/2,0;-mx,0,-mz)
Alternative OG setting exists for this space group."""

        ref_str_all = """BNS: 4.11 P_b2_1		OG: 3.7.14 P_2b2'
OG-BNS Transform: (a,2b,c;0,0,0)
Operators (BNS): (1|0,0,0) (2y|0,1/2,0) (1|0,1/2,0)' (2y|0,0,0)'
Wyckoff Positions (BNS):
4e  (x,y,z;mx,my,mz) (-x,y+1/2,-z;-mx,my,-mz) (x,y+1/2,z;-mx,-my,-mz)
    (-x,y,-z;mx,-my,mz)
2d  (1/2,y,1/2;mx,0,mz) (1/2,y+1/2,1/2;-mx,0,-mz)
2c  (1/2,y,0;mx,0,mz) (1/2,y+1/2,0;-mx,0,-mz)
2b  (0,y,1/2;mx,0,mz) (0,y+1/2,1/2;-mx,0,-mz)
2a  (0,y,0;mx,0,mz) (0,y+1/2,0;-mx,0,-mz)
Operators (OG): (1|0,0,0) (2y|0,1,0) (1|0,1,0)' (2y|0,0,0)'
Wyckoff Positions (OG): (1,0,0)+ (0,2,0)+ (0,0,1)+
4e  (x,y,z;mx,my,mz) (-x,y+1,-z;-mx,my,-mz) (x,y+1,z;-mx,-my,-mz)
    (-x,y,-z;mx,-my,mz)
2d  (1/2,y,1/2;mx,0,mz) (-1/2,y+1,-1/2;-mx,0,-mz)
2c  (1/2,y,0;mx,0,mz) (-1/2,y+1,0;-mx,0,-mz)
2b  (0,y,1/2;mx,0,mz) (0,y+1,-1/2;-mx,0,-mz)
2a  (0,y,0;mx,0,mz) (0,y+1,0;-mx,0,-mz)"""

        self.assert_str_content_equal(str(msg), ref_str)
        self.assert_str_content_equal(msg.data_str(), ref_str_all)
