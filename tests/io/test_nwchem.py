from __future__ import annotations

import orjson
import pytest
from numpy.testing import assert_allclose
from pytest import approx

from pymatgen.core.structure import Molecule
from pymatgen.io.nwchem import NwInput, NwInputError, NwOutput, NwTask
from pymatgen.util.testing import TEST_FILES_DIR

TEST_DIR = f"{TEST_FILES_DIR}/io/nwchem"

coords = [
    [0.000000, 0.000000, 0.000000],
    [0.000000, 0.000000, 1.089000],
    [1.026719, 0.000000, -0.363000],
    [-0.513360, -0.889165, -0.363000],
    [-0.513360, 0.889165, -0.363000],
]
mol = Molecule(["C", "H", "H", "H", "H"], coords)


class TestNwTask:
    def setup_method(self):
        self.task = NwTask(
            0,
            1,
            basis_set={"H": "6-31g"},
            theory="dft",
            theory_directives={"xc": "b3lyp"},
        )
        self.task_cosmo = NwTask(
            0,
            1,
            basis_set={"H": "6-31g"},
            theory="dft",
            theory_directives={"xc": "b3lyp"},
            alternate_directives={"cosmo": "cosmo"},
        )
        self.task_esp = NwTask(0, 1, basis_set={"H": "6-31g"}, theory="esp")

    def test_multi_bset(self):
        t = NwTask.from_molecule(
            mol,
            theory="dft",
            basis_set={"C": "6-311++G**", "H": "6-31++G**"},
            theory_directives={"xc": "b3lyp"},
        )
        answer = """title "H4C1 dft optimize"
charge 0
basis cartesian
 C library "6-311++G**"
 H library "6-31++G**"
end
dft
 xc b3lyp
end
task dft optimize"""
        assert str(t) == answer

    def test_str(self):
        answer = """title "dft optimize"
charge 0
basis cartesian
 H library "6-31g"
end
dft
 xc b3lyp
end
task dft optimize"""
        assert str(self.task) == answer

    def test_as_from_dict(self):
        dct = self.task.as_dict()
        task = NwTask.from_dict(dct)
        assert isinstance(task, NwTask)

    def test_init(self):
        with pytest.raises(NwInputError, match="Invalid theory='bad'"):
            NwTask(0, 1, {"H": "6-31g"}, theory="bad")
        with pytest.raises(NwInputError, match="Invalid operation='bad'"):
            NwTask(0, 1, {"H": "6-31g"}, operation="bad")

    def test_dft_task(self):
        task = NwTask.dft_task(mol, charge=1, operation="energy")
        answer = """title "H4C1 dft energy"
charge 1
basis cartesian
 C library "6-31g"
 H library "6-31g"
end
dft
 mult 2
 xc b3lyp
end
task dft energy"""
        assert str(task) == answer

    def test_dft_cosmo_task(self):
        task = NwTask.dft_task(
            mol,
            charge=mol.charge,
            operation="energy",
            xc="b3lyp",
            basis_set="6-311++G**",
            alternate_directives={"cosmo": {"dielec": 78.0}},
        )
        answer = """title "H4C1 dft energy"
charge 0
basis cartesian
 C library "6-311++G**"
 H library "6-311++G**"
end
dft
 mult 1
 xc b3lyp
end
cosmo
 dielec 78.0
end
task dft energy"""
        assert str(task) == answer

    def test_esp_task(self):
        task = NwTask.esp_task(mol, charge=mol.charge, operation="", basis_set="6-311++G**")
        answer = """title "H4C1 esp "
charge 0
basis cartesian
 C library "6-311++G**"
 H library "6-311++G**"
end

task esp """
        assert str(task) == answer


class TestNwInput:
    def setup_method(self):
        tasks = [
            NwTask.dft_task(mol, operation="optimize", xc="b3lyp", basis_set="6-31++G*"),
            NwTask.dft_task(mol, operation="freq", xc="b3lyp", basis_set="6-31++G*"),
            NwTask.dft_task(mol, operation="energy", xc="b3lyp", basis_set="6-311++G**"),
            NwTask.dft_task(
                mol,
                charge=mol.charge + 1,
                operation="energy",
                xc="b3lyp",
                basis_set="6-311++G**",
            ),
            NwTask.dft_task(
                mol,
                charge=mol.charge - 1,
                operation="energy",
                xc="b3lyp",
                basis_set="6-311++G**",
            ),
        ]

        self.nwi = NwInput(
            mol,
            tasks,
            geometry_options=["units", "angstroms", "noautoz"],
            memory_options="total 1000 mb",
        )
        self.nwi_symm = NwInput(
            mol,
            tasks,
            geometry_options=["units", "angstroms", "noautoz"],
            symmetry_options=["c1"],
        )

    def test_str(self):
        answer = """memory total 1000 mb
geometry units angstroms noautoz
 C 0.0 0.0 0.0
 H 0.0 0.0 1.089
 H 1.026719 0.0 -0.363
 H -0.51336 -0.889165 -0.363
 H -0.51336 0.889165 -0.363
end

title "H4C1 dft optimize"
charge 0
basis cartesian
 C library "6-31++G*"
 H library "6-31++G*"
end
dft
 mult 1
 xc b3lyp
end
task dft optimize

title "H4C1 dft freq"
charge 0
basis cartesian
 C library "6-31++G*"
 H library "6-31++G*"
end
dft
 mult 1
 xc b3lyp
end
task dft freq

title "H4C1 dft energy"
charge 0
basis cartesian
 C library "6-311++G**"
 H library "6-311++G**"
end
dft
 mult 1
 xc b3lyp
end
task dft energy

title "H4C1 dft energy"
charge 1
basis cartesian
 C library "6-311++G**"
 H library "6-311++G**"
end
dft
 mult 2
 xc b3lyp
end
task dft energy

title "H4C1 dft energy"
charge -1
basis cartesian
 C library "6-311++G**"
 H library "6-311++G**"
end
dft
 mult 2
 xc b3lyp
end
task dft energy
"""
        assert str(self.nwi) == answer

        ans_symm = """geometry units angstroms noautoz
 symmetry c1
 C 0.0 0.0 0.0
 H 0.0 0.0 1.089
 H 1.026719 0.0 -0.363
 H -0.51336 -0.889165 -0.363
 H -0.51336 0.889165 -0.363
end

title "H4C1 dft optimize"
charge 0
basis cartesian
 C library "6-31++G*"
 H library "6-31++G*"
end
dft
 mult 1
 xc b3lyp
end
task dft optimize

title "H4C1 dft freq"
charge 0
basis cartesian
 C library "6-31++G*"
 H library "6-31++G*"
end
dft
 mult 1
 xc b3lyp
end
task dft freq

title "H4C1 dft energy"
charge 0
basis cartesian
 C library "6-311++G**"
 H library "6-311++G**"
end
dft
 mult 1
 xc b3lyp
end
task dft energy

title "H4C1 dft energy"
charge 1
basis cartesian
 C library "6-311++G**"
 H library "6-311++G**"
end
dft
 mult 2
 xc b3lyp
end
task dft energy

title "H4C1 dft energy"
charge -1
basis cartesian
 C library "6-311++G**"
 H library "6-311++G**"
end
dft
 mult 2
 xc b3lyp
end
task dft energy
"""

        assert str(self.nwi_symm) == ans_symm

    def test_as_from_dict(self):
        dct = self.nwi.as_dict()
        nwi = NwInput.from_dict(dct)
        assert isinstance(nwi, NwInput)
        # Ensure it is json-serializable.
        orjson.dumps(dct).decode()
        dct = self.nwi_symm.as_dict()
        nwi_symm = NwInput.from_dict(dct)
        assert isinstance(nwi_symm, NwInput)
        orjson.dumps(dct).decode()

    def test_from_str_and_file(self):
        nwi = NwInput.from_file(f"{TEST_DIR}/ch4.nw")
        assert nwi.tasks[0].theory == "dft"
        assert nwi.memory_options == "total 1000 mb stack 400 mb"
        assert nwi.tasks[0].basis_set["C"] == "6-31++G*"
        assert nwi.tasks[-1].basis_set["C"] == "6-311++G**"
        # Try a simplified input.
        str_inp = """start H4C1
geometry units angstroms
 C 0.0 0.0 0.0
 H 0.0 0.0 1.089
 H 1.026719 0.0 -0.363
 H -0.51336 -0.889165 -0.363
 H -0.51336 0.889165 -0.363
end

title "H4C1 dft optimize"
charge 0
basis cartesian
 H library "6-31++G*"
 C library "6-31++G*"
end
dft
 xc b3lyp
 mult 1
end
task scf optimize

title "H4C1 dft freq"
charge 0
task scf freq

title "H4C1 dft energy"
charge 0
basis cartesian
 H library "6-311++G**"
 C library "6-311++G**"
end
task dft energy

title "H4C1 dft energy"
charge 1
dft
 xc b3lyp
 mult 2
end
task dft energy

title "H4C1 dft energy"
charge -1
task dft energy
"""
        nwi = NwInput.from_str(str_inp)
        assert nwi.geometry_options == ["units", "angstroms"]
        assert nwi.tasks[0].theory == "scf"
        assert nwi.tasks[0].basis_set["C"] == "6-31++G*"
        assert nwi.tasks[-1].theory == "dft"
        assert nwi.tasks[-1].basis_set["C"] == "6-311++G**"

        str_inp_symm = str_inp.replace("geometry units angstroms", "geometry units angstroms\n symmetry c1")

        nwi_symm = NwInput.from_str(str_inp_symm)
        assert nwi_symm.geometry_options == ["units", "angstroms"]
        assert nwi_symm.symmetry_options == ["c1"]
        assert nwi_symm.tasks[0].theory == "scf"
        assert nwi_symm.tasks[0].basis_set["C"] == "6-31++G*"
        assert nwi_symm.tasks[-1].theory == "dft"
        assert nwi_symm.tasks[-1].basis_set["C"] == "6-311++G**"


class TestNwOutput:
    def test_read(self):
        nw_output = NwOutput(f"{TEST_DIR}/CH4.nwout")
        nwo_cosmo = NwOutput(f"{TEST_DIR}/N2O4.nwout")

        assert nw_output[0]["charge"] == 0
        assert nw_output[-1]["charge"] == -1
        assert len(nw_output) == 5
        assert nw_output[0]["energies"][-1] == approx(-1102.6224491715582, abs=1e-2)
        assert nw_output[2]["energies"][-1] == approx(-1102.9986291578023, abs=1e-3)
        assert nwo_cosmo[5]["energies"][0]["cosmo scf"] == approx(-11156.354030653656, abs=1e-3)
        assert nwo_cosmo[5]["energies"][0]["gas phase"] == approx(-11153.374133394364, abs=1e-3)
        assert nwo_cosmo[5]["energies"][0]["sol phase"] == approx(-11156.353632962995, abs=1e-2)
        assert nwo_cosmo[6]["energies"][0]["cosmo scf"] == approx(-11168.818934311605, abs=1e-2)
        assert nwo_cosmo[6]["energies"][0]["gas phase"] == approx(-11166.3624424611462, abs=1e-2)
        assert nwo_cosmo[6]["energies"][0]["sol phase"] == approx(-11168.818934311605, abs=1e-2)
        assert nwo_cosmo[7]["energies"][0]["cosmo scf"] == approx(-11165.227959110889, abs=1e-2)
        assert nwo_cosmo[7]["energies"][0]["gas phase"] == approx(-11165.025443612385, abs=1e-2)
        assert nwo_cosmo[7]["energies"][0]["sol phase"] == approx(-11165.227959110154, abs=1e-2)

        assert nw_output[1]["hessian"][0][0] == approx(4.60187e01)
        assert nw_output[1]["hessian"][1][2] == approx(-1.14030e-08)
        assert nw_output[1]["hessian"][2][3] == approx(2.60819e01)
        assert nw_output[1]["hessian"][6][6] == approx(1.45055e02)
        assert nw_output[1]["hessian"][11][14] == approx(1.35078e01)

        # CH4.nwout, line 722
        assert nw_output[0]["forces"][0][3] == approx(-0.001991)

        # N2O4.nwout, line 1071
        assert nwo_cosmo[0]["forces"][0][4] == approx(0.011948)

        # There should be four DFT gradients.
        assert len(nwo_cosmo[0]["forces"]) == 4

        ie = nw_output[4]["energies"][-1] - nw_output[2]["energies"][-1]
        ea = nw_output[2]["energies"][-1] - nw_output[3]["energies"][-1]
        assert ie == approx(0.7575358648355177)
        assert ea == approx(-14.997877958701338, abs=1e-3)
        assert nw_output[4]["basis_set"]["C"]["description"] == "6-311++G**"

        nw_output = NwOutput(f"{TEST_DIR}/H4C3O3_1.nwout")
        assert nw_output[-1]["has_error"]
        assert nw_output[-1]["errors"][0] == "Bad convergence"

        nw_output = NwOutput(f"{TEST_DIR}/CH3CH2O.nwout")
        assert nw_output[-1]["has_error"]
        assert nw_output[-1]["errors"][0] == "Bad convergence"

        nw_output = NwOutput(f"{TEST_DIR}/C1N1Cl1_1.nwout")
        assert nw_output[-1]["has_error"]
        assert nw_output[-1]["errors"][0] == "autoz error"

        nw_output = NwOutput(f"{TEST_DIR}/anthrachinon_wfs_16_ethyl.nwout")
        assert nw_output[-1]["has_error"]
        assert nw_output[-1]["errors"][0] == "Geometry optimization failed"
        nw_output = NwOutput(f"{TEST_DIR}/anthrachinon_wfs_15_carboxyl.nwout")
        assert nw_output[1]["frequencies"][0][0] == approx(-70.47)
        assert len(nw_output[1]["frequencies"][0][1]) == 27
        assert nw_output[1]["frequencies"][-1][0] == approx(3696.74)
        assert_allclose(nw_output[1]["frequencies"][-1][1][-1], (0.20498, -0.94542, -0.00073))
        assert nw_output[1]["normal_frequencies"][1][0] == approx(-70.72)
        assert nw_output[1]["normal_frequencies"][3][0] == approx(-61.92)
        assert_allclose(nw_output[1]["normal_frequencies"][1][1][-1], (0.00056, 0.00042, 0.06781))

    def test_parse_tddft(self):
        nw_output = NwOutput(f"{TEST_DIR}/phen_tddft.log")
        roots = nw_output.parse_tddft()
        assert len(roots["singlet"]) == 20
        assert roots["singlet"][0]["energy"] == approx(3.9291)
        assert roots["singlet"][0]["osc_strength"] == approx(0.0)
        assert roots["singlet"][1]["osc_strength"] == approx(0.00177)

    def test_get_excitation_spectrum(self):
        nw_output = NwOutput(f"{TEST_DIR}/phen_tddft.log")
        spectrum = nw_output.get_excitation_spectrum()
        assert len(spectrum.x) == 2000
        assert spectrum.x[0] == approx(1.9291)
        assert spectrum.y[0] == approx(0.0)
        assert spectrum.y[1000] == approx(0.0007423569947114812)
