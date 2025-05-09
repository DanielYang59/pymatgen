"""
Created on Nov 10, 2012.

@author: Shyue Ping Ong
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pytest import approx

from pymatgen.core import Composition, DummySpecies, Element, Species
from pymatgen.core.composition import ChemicalPotential, CompositionError, reduce_formula
from pymatgen.util.testing import MatSciTest


class TestComposition(MatSciTest):
    def setup_method(self):
        self.comps = [
            Composition("Li3Fe2(PO4)3"),
            Composition("Li3Fe(PO4)O"),
            Composition("LiMn2O4"),
            Composition("Li4O4"),
            Composition("Li3Fe2Mo3O12"),
            Composition("Li3Fe2((PO4)3(CO3)5)2"),
            Composition("Li1.5Si0.5"),
            Composition("ZnOH"),
        ]

        self.indeterminate_comp = [
            Composition.ranked_compositions_from_indeterminate_formula("Co1", lock_if_strict=True),
            Composition.ranked_compositions_from_indeterminate_formula("Co1", lock_if_strict=False),
            Composition.ranked_compositions_from_indeterminate_formula("co2o3"),
            Composition.ranked_compositions_from_indeterminate_formula("ncalu"),
            Composition.ranked_compositions_from_indeterminate_formula("calun"),
            Composition.ranked_compositions_from_indeterminate_formula("liCoo2n (pO4)2"),
            Composition.ranked_compositions_from_indeterminate_formula("(co)2 (PO)4"),
            Composition.ranked_compositions_from_indeterminate_formula("Fee3"),
        ]

    def test_immutable(self):
        with pytest.raises(TypeError) as exc:
            self.comps[0]["Fe"] = 1

        assert "'Composition' object does not support item assignment" in str(exc.value)

        with pytest.raises(TypeError) as exc:
            del self.comps[0]["Fe"]

        assert "'Composition' object does not support item deletion" in str(exc.value)

    def test_in(self):
        # test the Composition.__contains__ magic method
        assert "Fe" in self.comps[0]
        assert "Fe" not in self.comps[2]
        assert Element("Fe") in self.comps[0]
        assert self.comps[0]["Fe"] == 2
        assert self.comps[0]["Mn"] == 0
        with pytest.raises(KeyError, match="Invalid key='Hello'"):
            self.comps[0]["Hello"]
        with pytest.raises(KeyError, match="Invalid key='Vac'"):
            self.comps[0]["Vac"]

        # Test Species in Composition
        comp = Composition({Species("Fe2+"): 2})
        assert Species("Fe2+") in comp
        assert Species("Fe3+") not in comp
        assert "Fe" in comp
        assert Element("Fe") in comp

        # Test Element in Composition with Species
        comp = Composition({Species("Fe2+"): 2})
        assert Element("Fe") in comp
        assert Element("O") not in comp
        assert "Fe" in comp
        assert "O" not in comp

        # Test str in Composition with Element
        comp = Composition({"Fe": 2})
        assert "Fe" in comp
        assert "O" not in comp
        assert Element("Fe") in comp
        assert Element("O") not in comp

        # Test int (atomic number) in Composition
        comp = Composition({Element("Fe"): 2})
        assert 26 in comp  # atomic number for Fe
        assert 8 not in comp  # atomic number for O

        # Test float in Composition
        comp = Composition({Element("Fe"): 2})
        with pytest.raises(TypeError, match="Invalid key=1.5 for Composition"):
            assert 1.5 in comp

        # Test DummySpecies in Composition
        comp = Composition({DummySpecies("X"): 2})
        assert DummySpecies("X") in comp
        assert DummySpecies("A") not in comp
        assert "X" in comp
        assert "Y" not in comp
        assert Element("Fe") not in comp
        assert Species("Fe2+") not in comp

    def test_getitem(self):
        comp = Composition({"Li+": 1, "Mn3+": 2, "O2-": 4, "Li": 1})
        assert comp["Li"] == 2
        assert comp["Li+"] == 1
        assert comp["Mn3+"] == 2
        assert comp["Mn"] == 2
        assert comp["O2-"] == 4
        assert comp["O"] == 4

    def test_hill_formula(self):
        comp = Composition("CaCO3")
        assert comp.hill_formula == "C Ca O3"
        comp = Composition("C2H5OH")
        assert comp.hill_formula == "C2 H6 O"
        # A test case with both C and H, but not one after another (mp-1228185)
        comp = Composition("Ga8 As16 H102 C32 S36 O3")
        assert comp.hill_formula == "C32 H102 As16 Ga8 O3 S36"
        # A test case with H but no C
        comp = Composition("Ga8 As16 H102 S36 O3")
        assert comp.hill_formula == "As16 Ga8 H102 O3 S36"

    def test_init(self):
        with pytest.raises(ValueError, match="Amounts in Composition cannot be negative"):
            Composition({"H": -0.1})

        assert Composition({"Fe": 4, "Li": 4, "O": 16, "P": 4}).formula == "Li4 Fe4 P4 O16"

        with pytest.raises(ValueError, match="Can't parse Element or Species from"):
            Composition({None: 4, "Li": 4, "O": 16, "P": 4})

        assert Composition({1: 2, 8: 1}).formula == "H2 O1"
        assert Composition(Na=2, O=1).formula == "Na2 O1"

        comp = Composition({"S": Composition.amount_tolerance / 2})
        assert len(comp.elements) == 0

        # test Composition from int/float raises
        for val in (1, 2.5):
            with pytest.raises(TypeError, match=f"{type(val).__name__!r} object is not iterable"):
                Composition(val)

    def test_init_mixed_valence(self):
        assert Composition({"Fe3+": 2, "Fe2+": 2, "Li": 4, "O": 16, "P": 4}).formula == "Li4 Fe4 P4 O16"
        assert Composition({"Fe3+": 2, "Fe": 2, "Li": 4, "O": 16, "P": 4}).formula == "Li4 Fe4 P4 O16"

    def test_str_and_repr(self):
        test_cases = [
            (
                {"Li+": 2, "Mn3+": 2, "O2-": 4},
                {"str": "Li+2 Mn3+2 O2-4", "repr": "Composition('Li+:2 Mn3+:2 O2-:4')"},
            ),
            ("H2O", {"str": "H2 O1", "repr": "Composition('H2 O1')"}),
            (
                {"Fe3+": 2, "O2-": 3},
                {"str": "Fe3+2 O2-3", "repr": "Composition('Fe3+:2 O2-:3')"},
            ),
            ("C6H6", {"str": "C6 H6", "repr": "Composition('C6 H6')"}),
        ]

        for comp, expected in test_cases:
            assert str(Composition(comp)) == expected["str"]
            assert repr(Composition(comp)) == expected["repr"]

    def test_average_electroneg(self):
        electro_negs = (
            2.7224999999999997,
            2.4160000000000004,
            2.5485714285714285,
            2.21,
            2.718,
            3.08,
            1.21,
            2.43,
        )
        for elem, val in zip(self.comps, electro_negs, strict=True):
            assert elem.average_electroneg == approx(val)

    def test_total_electrons(self):
        test_cases = {"C": 6, "SrTiO3": 84}
        for key, val in test_cases.items():
            comp = Composition(key)
            assert comp.total_electrons == val

    def test_formula(self):
        correct_formulas = [
            "Li3 Fe2 P3 O12",
            "Li3 Fe1 P1 O5",
            "Li1 Mn2 O4",
            "Li4 O4",
            "Li3 Fe2 Mo3 O12",
            "Li3 Fe2 P6 C10 O54",
            "Li1.5 Si0.5",
            "Zn1 H1 O1",
        ]
        all_formulas = [c.formula for c in self.comps]
        assert all_formulas == correct_formulas
        with pytest.raises(ValueError, match="co2 is an invalid formula"):
            Composition("(co2)(po4)2")

        assert Composition("K Na 2").reduced_formula == "KNa2"

        assert Composition("K3 Na 2").reduced_formula == "K3Na2"

        assert Composition("Na 3 Zr (PO 4) 3").reduced_formula == "Na3Zr(PO4)3"

        # gh-3559
        very_nested_formula = (
            "(Bi2(Mg0.667Nb1.333)O7)((Bi2(Mg0.667Nb1.333)O7)0.9(SrCO3)0.1)((Bi2(Mg0.667Nb1.333)O7)0.7(SrCO3)0.3)"
        )
        assert Composition(very_nested_formula).formula == "Sr0.4 Mg1.7342 Nb3.4658 Bi5.2 C0.4 O19.4"
        assert Composition(very_nested_formula) == Composition(
            "(Bi2(Mg0.667Nb1.333)O7)1((Bi2(Mg0.667Nb1.333)O7)0.9(SrCO3)0.1)((Bi2(Mg0.667Nb1.333)O7)0.7(SrCO3)0.3)"
        )
        assert Composition("(C)((C)0.9(B)0.1)") == Composition("C1.9 B0.1")

        assert Composition("NaN").reduced_formula == "NaN"
        with pytest.raises(
            ValueError,
            match=r"float\('NaN'\) is not a valid Composition, did you mean 'NaN'\?",
        ):
            Composition(float("NaN"))

        # test bad formulas raise ValueError
        for bad_formula in ("", " ", "  2", "4 2", "6123", "1.2", "1/2", "1.2.3"):
            with pytest.raises(ValueError, match=f"Invalid formula={bad_formula!r}"):
                Composition(bad_formula)

    def test_to_latex_html_unicode(self):
        assert self.comps[0].to_latex_string() == "Li$_{3}$Fe$_{2}$P$_{3}$O$_{12}$"
        assert self.comps[0].to_html_string() == "Li<sub>3</sub>Fe<sub>2</sub>P<sub>3</sub>O<sub>12</sub>"
        assert self.comps[0].to_unicode_string() == "Li₃Fe₂P₃O₁₂"

    def test_iupac_formula(self):
        correct_formulas = [
            "Li3 Fe2 P3 O12",
            "Li3 Fe1 P1 O5",
            "Li1 Mn2 O4",
            "Li4 O4",
            "Li3 Mo3 Fe2 O12",
            "Li3 Fe2 C10 P6 O54",
            "Li1.5 Si0.5",
            "Zn1 H1 O1",
        ]
        all_formulas = [c.iupac_formula for c in self.comps]
        assert all_formulas == correct_formulas

    def test_mixed_valence(self):
        comp = Composition({"Fe2+": 2, "Fe3+": 4, "Li+": 8})
        assert comp.reduced_formula == "Li4Fe3"
        assert comp.alphabetical_formula == "Fe6 Li8"
        assert comp.formula == "Li8 Fe6"

    def test_indeterminate_formula(self):
        correct_formulas = [
            ["Co1"],
            ["Co1", "C1 O1"],
            ["Co2 O3", "C1 O5"],
            ["N1 Ca1 Lu1", "U1 Al1 C1 N1"],
            ["N1 Ca1 Lu1", "U1 Al1 C1 N1"],
            [
                "Li1 Co1 P2 N1 O10",
                "Li1 Co1 Po8 N1 O2",
                "Li1 P2 C1 N1 O11",
                "Li1 Po8 C1 N1 O3",
            ],
            ["Co2 P4 O4", "Co2 Po4", "P4 C2 O6", "Po4 C2 O2"],
            [],
        ]
        for idx, formulas in enumerate(correct_formulas):
            assert [*map(Composition, formulas)] == self.indeterminate_comp[idx]

    def test_alphabetical_formula(self):
        correct_formulas = [
            "Fe2 Li3 O12 P3",
            "Fe1 Li3 O5 P1",
            "Li1 Mn2 O4",
            "Li4 O4",
            "Fe2 Li3 Mo3 O12",
            "C10 Fe2 Li3 O54 P6",
            "Li1.5 Si0.5",
            "H1 O1 Zn1",
        ]
        all_formulas = [c.alphabetical_formula for c in self.comps]
        assert all_formulas == correct_formulas

    def test_reduced_composition(self):
        correct_reduced_formulas = [
            "Li3Fe2(PO4)3",
            "Li3FePO5",
            "LiMn2O4",
            "Li2O2",
            "Li3Fe2(MoO4)3",
            "Li3Fe2P6(C5O27)2",
            "Li1.5Si0.5",
            "ZnHO",
        ]
        for idx, comp in enumerate(self.comps):
            assert comp.reduced_composition == Composition(correct_reduced_formulas[idx])

    def test_reduced_formula(self):
        correct_reduced_formulas = [
            "Li3Fe2(PO4)3",
            "Li3FePO5",
            "LiMn2O4",
            "Li2O2",
            "Li3Fe2(MoO4)3",
            "Li3Fe2P6(C5O27)2",
            "Li1.5Si0.5",
            "ZnHO",
        ]
        all_formulas = [c.reduced_formula for c in self.comps]
        assert all_formulas == correct_reduced_formulas

        # test IUPAC reduced formula (polyanions should still appear at the end)
        all_formulas = [c.get_reduced_formula_and_factor(iupac_ordering=True)[0] for c in self.comps]
        assert all_formulas == correct_reduced_formulas
        assert Composition("H6CN").get_integer_formula_and_factor(iupac_ordering=True)[0] == "CNH6"

        # test rounding
        comp = Composition({"Na": 2 - Composition.amount_tolerance / 2, "Cl": 2})
        assert comp.reduced_formula == "NaCl"

    def test_integer_formula(self):
        correct_reduced_formulas = [
            "Li3Fe2(PO4)3",
            "Li3FePO5",
            "LiMn2O4",
            "Li2O2",
            "Li3Fe2(MoO4)3",
            "Li3Fe2P6(C5O27)2",
            "Li3Si",
            "ZnHO",
        ]
        all_formulas = [c.get_integer_formula_and_factor()[0] for c in self.comps]
        assert all_formulas == correct_reduced_formulas
        assert Composition("Li0.5O0.25").get_integer_formula_and_factor() == (
            "Li2O",
            0.25,
        )
        assert Composition("O0.25").get_integer_formula_and_factor() == ("O2", 0.125)
        formula, factor = Composition("Li0.16666667B1.0H1.0").get_integer_formula_and_factor()
        assert formula == "Li(BH)6"
        assert factor == approx(1 / 6)

        # test IUPAC reduced formula (polyanions should still appear at the end)
        all_formulas = [c.get_integer_formula_and_factor(iupac_ordering=True)[0] for c in self.comps]
        assert all_formulas == correct_reduced_formulas
        assert Composition("H6CN0.5").get_integer_formula_and_factor(iupac_ordering=True) == ("C2NH12", 0.5)

    def test_num_atoms(self):
        correct_num_atoms = [20, 10, 7, 8, 20, 75, 2, 3]

        all_n_atoms = [c.num_atoms for c in self.comps]
        assert all_n_atoms == correct_num_atoms

    def test_weight(self):
        correct_weights = [
            417.427086,
            187.63876199999999,
            180.81469,
            91.7616,
            612.3258,
            1302.430172,
            24.454250000000002,
            82.41634,
        ]
        all_weights = [c.weight for c in self.comps]
        assert_allclose(all_weights, correct_weights, 5)

    def test_get_atomic_fraction(self):
        correct_at_frac = {"Li": 0.15, "Fe": 0.1, "P": 0.15, "O": 0.6}
        for el in ["Li", "Fe", "P", "O"]:
            assert self.comps[0].get_atomic_fraction(el) == correct_at_frac[el], "Wrong computed atomic fractions"
        assert self.comps[0].get_atomic_fraction("S") == 0, "Wrong computed atomic fractions"

    def test_anonymized_formula(self):
        expected_formulas = [
            "A2B3C3D12",
            "ABC3D5",
            "AB2C4",
            "AB",
            "A2B3C3D12",
            "A2B3C6D10E54",
            "A0.5B1.5",
            "ABC",
        ]
        for idx, comp in enumerate(self.comps):
            assert comp.anonymized_formula == expected_formulas[idx]

    def test_get_wt_fraction(self):
        correct_wt_frac = {
            "Li": 0.0498841610868,
            "Fe": 0.267567687258,
            "P": 0.222604831158,
            "O": 0.459943320496,
        }
        for el, expected in correct_wt_frac.items():
            assert self.comps[0].get_wt_fraction(el) == approx(expected), "Wrong computed weight fraction"
        assert self.comps[0].get_wt_fraction(Element("S")) == 0, "Wrong computed weight fractions"

    def test_from_dict(self):
        sym_dict = {"Fe": 6, "O": 8}
        assert Composition.from_dict(sym_dict).reduced_formula == "Fe3O4", "Creation form sym_amount dictionary failed!"
        comp = Composition({"Fe2+": 2, "Fe3+": 4, "O2-": 8})
        comp2 = Composition.from_dict(comp.as_dict())
        assert comp == comp2

    def test_from_weight_dict(self):
        weight_dict_list = [
            {"Ti": 90, "V": 6, "Al": 4},
            {"Ni": 60, "Ti": 40},
            {"H": 0.1119, "O": 0.8881},
        ]
        formula_list = ["Ti87.6 V5.5 Al6.9", "Ti44.98 Ni55.02", "H2O"]

        for weight_dict, formula in zip(weight_dict_list, formula_list, strict=True):
            c1 = Composition(formula).fractional_composition
            c2 = Composition.from_weight_dict(weight_dict).fractional_composition
            assert set(c1.elements) == set(c2.elements)
            for el in c1.elements:
                assert c1[el] == approx(c2[el], abs=1e-3)

    def test_to_from_weight_dict(self):
        for comp in self.comps:
            c2 = Composition().from_weight_dict(comp.as_weight_dict())
            comp.almost_equals(c2)

    def test_composition_from_weights(self):
        ref_comp = Composition({"Fe": 0.5, "Ni": 0.5})

        # Test basic weight-based composition
        comp = Composition.from_weights({"Fe": ref_comp.get_wt_fraction("Fe"), "Ni": ref_comp.get_wt_fraction("Ni")})
        assert comp["Fe"] == approx(ref_comp.get_atomic_fraction("Fe"))
        assert comp["Ni"] == approx(ref_comp.get_atomic_fraction("Ni"))

        # Test with another Composition instance
        comp = Composition({"Fe": ref_comp.get_wt_fraction("Fe"), "Ni": ref_comp.get_wt_fraction("Ni")})
        comp = Composition.from_weights(comp)
        assert comp["Fe"] == approx(ref_comp.get_atomic_fraction("Fe"))
        assert comp["Ni"] == approx(ref_comp.get_atomic_fraction("Ni"))

        # Test with string input
        comp = Composition.from_weights(f"Fe{ref_comp.get_wt_fraction('Fe')}Ni{ref_comp.get_wt_fraction('Ni')}")
        assert comp["Fe"] == approx(ref_comp.get_atomic_fraction("Fe"))
        assert comp["Ni"] == approx(ref_comp.get_atomic_fraction("Ni"))

        # Test with kwargs
        comp = Composition.from_weights(Fe=ref_comp.get_wt_fraction("Fe"), Ni=ref_comp.get_wt_fraction("Ni"))
        assert comp["Fe"] == approx(ref_comp.get_atomic_fraction("Fe"))
        assert comp["Ni"] == approx(ref_comp.get_atomic_fraction("Ni"))

        # Test strict mode
        with pytest.raises(ValueError, match="'Xx' is not a valid Element"):
            Composition.from_weights({"Xx": 10}, strict=True)

        # Test allow_negative
        with pytest.raises(ValueError, match="Weights in Composition cannot be negative!"):
            Composition.from_weights({"Fe": -55.845})

        # Test NaN handling
        with pytest.raises(ValueError, match=r"float\('NaN'\) is not a valid Composition"):
            Composition.from_weights(float("nan"))

    def test_as_dict(self):
        comp = Composition.from_dict({"Fe": 4, "O": 6})
        dct = comp.as_dict()
        correct_dict = {"Fe": 4.0, "O": 6.0}
        assert dct["Fe"] == correct_dict["Fe"]
        assert dct["O"] == correct_dict["O"]
        correct_dict = {"Fe": 2.0, "O": 3.0}
        dct = comp.as_reduced_dict()
        assert isinstance(dct, dict)
        assert dct["Fe"] == correct_dict["Fe"]
        assert dct["O"] == correct_dict["O"]

    def test_pickle(self):
        for comp in self.comps:
            self.serialize_with_pickle(comp)
            self.serialize_with_pickle(comp.as_data_dict())

    def test_as_data_dict(self):
        comp = Composition("Fe0.00009Ni0.99991")
        dct = comp.as_data_dict()
        assert dct["reduced_cell_composition"]["Fe"] == approx(9e-5)

    def test_add(self):
        assert (self.comps[0] + self.comps[2]).formula == "Li4 Mn2 Fe2 P3 O16", "Incorrect composition after addition!"
        assert (self.comps[3] + {"Fe": 4, "O": 4}).formula == "Li4 Fe4 O8", "Incorrect composition after addition!"

        Fe = Element("Fe")
        assert self.comps[0].__add__(Fe) == NotImplemented

    def test_sub(self):
        assert (self.comps[0] - Composition("Li2O")).formula == "Li1 Fe2 P3 O11", (
            "Incorrect composition after addition!"
        )
        assert (self.comps[0] - {"Fe": 2, "O": 3}).formula == "Li3 P3 O9"

        with pytest.raises(ValueError, match="Amounts in Composition cannot be negative"):
            _ = Composition("O") - Composition("H")

        # check that S is completely removed by subtraction
        c1 = Composition({"S": 1 + Composition.amount_tolerance / 2, "O": 1})
        c2 = Composition({"S": 1})
        assert len((c1 - c2).elements) == 1

        Fe = Element("Fe")
        assert self.comps[0].__add__(Fe) == NotImplemented

    def test_mul(self):
        assert (self.comps[0] * 4).formula == "Li12 Fe8 P12 O48"
        assert (3 * self.comps[1]).formula == "Li9 Fe3 P3 O15"

    def test_div(self):
        assert (self.comps[0] / 4).formula == "Li0.75 Fe0.5 P0.75 O3"

    def test_equals(self):
        # generate randomized compositions for robustness (tests might pass for specific elements
        # but fail for others)
        rng = np.random.default_rng()
        random_z = rng.integers(1, 92)
        fixed_el = Element.from_Z(random_z)
        other_z = rng.integers(1, 92)
        while other_z == random_z:
            other_z = rng.integers(1, 92)
        comp1 = Composition({fixed_el: 1, Element.from_Z(other_z): 0})
        other_z = rng.integers(1, 92)
        while other_z == random_z:
            other_z = rng.integers(1, 92)
        comp2 = Composition({fixed_el: 1, Element.from_Z(other_z): 0})
        assert comp1 == comp2, f"Composition equality test failed. {comp1.formula} should be equal to {comp2.formula}"
        assert hash(comp1) == hash(comp2), "Hash equality test failed!"

        c1, c2 = self.comps[:2]
        assert c1 == c1
        assert c1 != c2

    def test_hash_robustness(self):
        c1 = Composition(f"O{0.2}Fe{0.8}Na{Composition.amount_tolerance * 0.99}")
        c2 = Composition(f"O{0.2}Fe{0.8}Na{Composition.amount_tolerance * 1.01}")
        c3 = Composition(f"O{0.2}Fe{0.8 + Composition.amount_tolerance * 0.99}")

        assert c1 == c3, "__eq__ not robust"
        assert (c1 == c3) == (hash(c1) == hash(c3)), "Hash doesn't match eq when true"
        assert hash(c1) != hash(c2), "Hash equal for different chemical systems"

    def test_comparisons(self):
        c1 = Composition({"S": 1})
        c1_1 = Composition({"S": 1.00000000000001})
        c2 = Composition({"S": 2})
        c3 = Composition({"O": 1})
        c4 = Composition({"O": 1, "S": 1})
        assert not c1 > c2
        assert not c1_1 > c1
        assert not c1_1 < c1
        assert c1 > c3
        assert c3 < c1
        assert c4 > c1
        assert sorted([c1, c1_1, c2, c4, c3]) == [c3, c1, c1_1, c4, c2]

        Fe = Element("Fe")
        assert c1 != Fe, NotImplemented
        assert c1 != Fe
        with pytest.raises(
            TypeError,
            match="'<' not supported between instances of 'Composition' and 'Element'",
        ):
            _ = c1 < Fe

    def test_almost_equals(self):
        c1 = Composition({"Fe": 2.0, "O": 3.0, "Mn": 0})
        c2 = Composition({"O": 3.2, "Fe": 1.9, "Zn": 0})
        c3 = Composition({"Ag": 2.0, "O": 3.0})
        c4 = Composition({"Fe": 2.0, "O": 3.0, "Ag": 2.0})
        assert c1.almost_equals(c2, rtol=0.1)
        assert not c1.almost_equals(c2, rtol=0.01)
        assert not c1.almost_equals(c3, rtol=0.1)
        assert not c1.almost_equals(c4, rtol=0.1)

    def test_equality(self):
        assert self.comps[0] == self.comps[0]
        assert self.comps[0] != self.comps[1]
        assert self.comps[0] == self.comps[0]
        assert self.comps[0] != self.comps[1]

    def test_fractional_composition(self):
        for comp in self.comps:
            assert comp.fractional_composition.num_atoms == 1

    def test_init_numerical_tolerance(self):
        assert Composition({"B": 1, "C": -1e-12}) == Composition("B")

    def test_negative_compositions(self):
        assert Composition("Li-1(PO-1)4", allow_negative=True).formula == "Li-1 P4 O-4"
        assert Composition("Li-1(PO-1)4", allow_negative=True).reduced_formula == "Li-1(PO-1)4"
        assert Composition("Li-2Mg4", allow_negative=True).reduced_composition == Composition(
            "Li-1Mg2", allow_negative=True
        )
        assert Composition("Li-2.5Mg4", allow_negative=True).reduced_composition == Composition(
            "Li-2.5Mg4", allow_negative=True
        )

        # test math
        c1 = Composition("LiCl", allow_negative=True)
        c2 = Composition("Li")
        assert c1 - 2 * c2 == Composition({"Li": -1, "Cl": 1}, allow_negative=True)
        assert (c1 + c2).allow_negative
        assert c1 / -1 == Composition("Li-1Cl-1", allow_negative=True)

        # test num_atoms
        c1 = Composition("Mg-1Li", allow_negative=True)
        assert c1.num_atoms == 2
        assert c1.get_atomic_fraction("Mg") == approx(0.5)
        assert c1.get_atomic_fraction("Li") == approx(0.5)
        assert c1.fractional_composition == Composition("Mg-0.5Li0.5", allow_negative=True)

        # test copy
        assert c1.copy() == c1

        # test species
        c1 = Composition({"Mg": 1, "Mg2+": -1}, allow_negative=True)
        assert c1.num_atoms == 2
        assert c1.get_el_amt_dict() == {"Mg": 0}
        assert c1.average_electroneg == approx(1.31)  # correct Mg electronegativity)

    def test_special_formulas(self):
        special_formulas = {
            "LiO": "Li2O2",
            "NaO": "Na2O2",
            "KO": "K2O2",
            "HO": "H2O2",
            "CsO": "Cs2O2",
            "RbO": "Rb2O2",
            "O": "O2",
            "N": "N2",
            "F": "F2",
            "Cl": "Cl2",
            "H": "H2",
        }
        for k, v in special_formulas.items():
            assert Composition(k).reduced_formula == v

    def test_oxi_state_guesses(self):
        assert Composition("LiFeO2").oxi_state_guesses() == ({"Li": 1, "Fe": 3, "O": -2},)

        assert Composition("Fe4O5").oxi_state_guesses() == ({"Fe": 2.5, "O": -2},)

        assert Composition("V2O3").oxi_state_guesses() == ({"V": 3, "O": -2},)

        # all_oxidation_states produces *many* possible responses
        assert len(Composition("MnO").oxi_state_guesses(all_oxi_states=True)) == 4

        # can't balance b/c missing V4+
        assert Composition("VO2").oxi_state_guesses(oxi_states_override={"V": [2, 3, 5]}) == ()

        # missing V4+, but can balance due to additional sites
        assert Composition("V2O4").oxi_state_guesses(oxi_states_override={"V": [2, 3, 5]}) == ({"V": 4, "O": -2},)

        # multiple solutions - Mn/Fe = 2+/4+ or 3+/3+ or 4+/2+
        MnFeO3 = Composition("MnFeO3")
        MnFeO3_guesses = MnFeO3.oxi_state_guesses(oxi_states_override={"Mn": [2, 3, 4], "Fe": [2, 3, 4]})
        assert len(MnFeO3_guesses) == 3

        # multiple solutions prefers 3/3 over 2/4 or 4/2
        assert MnFeO3_guesses[0] == {"Mn": 3, "Fe": 3, "O": -2}

        # https://github.com/materialsproject/pymatgen/issues/3324
        # always expect 0 for oxi_state_guesses of elemental systems
        for atomic_num in np.random.default_rng().choice(range(1, 92), 10):  # try 10 random elements
            elem = Element.from_Z(atomic_num).symbol
            assert Composition(f"{elem}2").oxi_state_guesses() == ({elem: 0},)
            assert Composition(f"{elem}3").oxi_state_guesses() == ({elem: 0},)

        # target charge of 1
        assert Composition("V2O6").oxi_state_guesses(oxi_states_override={"V": [2, 3, 4, 5]}, target_charge=-2) == (
            {"V": 5, "O": -2},
        )

        expected_oxi_guesses = {"Li": 1, "Fe": 2, "P": 5, "O": -2}
        # max_sites for very large composition - should timeout if incorrect
        assert Composition("Li10000Fe10000P10000O40000").oxi_state_guesses(max_sites=7)[0] == expected_oxi_guesses

        # max_sites for very large composition - should timeout if incorrect
        assert Composition("Li10000Fe10000P10000O40000").oxi_state_guesses(max_sites=-1)[0] == expected_oxi_guesses

        # negative max_sites less than -1 - should throw error if cannot reduce
        # to under the abs(max_sites) number of sites. Will also timeout if
        # incorrect.
        assert Composition("Sb10000O10000F10000").oxi_state_guesses(max_sites=-3)[0] == {"Sb": 3, "O": -2, "F": -1}
        with pytest.raises(
            ValueError,
            match="Composition Li1 O1 F1 cannot accommodate max_sites setting",
        ):
            Composition("LiOF").oxi_state_guesses(max_sites=-2)

        with pytest.raises(ValueError, match="Composition V2 O3 cannot accommodate max_sites setting"):
            Composition("V2O3").oxi_state_guesses(max_sites=1)

    def test_oxi_state_decoration(self):
        # Basic test: Get compositions where each element is in a single charge state
        decorated = Composition("H2O").add_charges_from_oxi_state_guesses()
        assert Species("H", 1) in decorated
        assert decorated.get(Species("H", 1)) == 2

        # Test: More than one charge state per element
        decorated = Composition("Fe3O4").add_charges_from_oxi_state_guesses()
        assert decorated.get(Species("Fe", 2)) == 1
        assert decorated.get(Species("Fe", 3)) == 2
        assert decorated.get(Species("O", -2)) == 4

        # Test: No possible charge states
        #   It should return an uncharged composition
        decorated = Composition("NiAl").add_charges_from_oxi_state_guesses()
        assert decorated.get(Species("Ni", 0)) == 1
        assert decorated.get(Species("Al", 0)) == 1

    def test_metallofullerene(self):
        # Test: Parse Metallofullerene formula (e.g. Y3N@C80)
        comp1 = Composition("Y3N@C80")
        comp2 = Composition({"Y": 3, "N": 1, "C": 80})
        assert comp1 == comp2

    def test_contains_element_type(self):
        EuTiO3 = Composition("EuTiO3")
        assert EuTiO3.contains_element_type("lanthanoid") is True
        assert EuTiO3.contains_element_type("noble_gas") is False
        assert EuTiO3.contains_element_type("f-block") is True
        assert EuTiO3.contains_element_type("s-block") is False
        assert EuTiO3.contains_element_type("alkali") is False
        NaCl = Composition("NaCl")
        assert NaCl.contains_element_type("halogen") is True
        assert NaCl.contains_element_type("alkali") is True
        assert NaCl.contains_element_type("s-block") is True
        assert NaCl.contains_element_type("p-block") is True
        assert NaCl.contains_element_type("d-block") is False
        assert NaCl.contains_element_type("f-block") is False

        with pytest.raises(ValueError, match="Invalid category='invalid', pick from"):
            EuTiO3.contains_element_type("invalid")

    def test_elements(self):
        assert Composition("NaCl").elements == list(map(Element, ["Na", "Cl"]))
        assert Composition({"Na+": 1, "Cl-": 1}).elements == list(map(Species, ["Na+", "Cl-"]))

    def test_chemical_system(self):
        assert Composition({"Na": 1, "Cl": 1}).chemical_system == "Cl-Na"
        assert Composition({"Na+": 1, "Cl-": 1}).chemical_system == "Cl-Na"
        assert Composition({"Na+": 1, "Na2+": 1, "Cl-": 1}).chemical_system == "Cl-Na"

    def test_chemical_system_set(self):
        assert Composition({"Na": 1, "Cl": 1}).chemical_system_set == {"Cl", "Na"}
        assert Composition({"Na+": 1, "Cl-": 1}).chemical_system_set == {"Cl", "Na"}

    def test_is_valid(self):
        formula = "NaCl"
        comp = Composition(formula)
        assert comp.valid

        formula = "NaClX"
        comp = Composition(formula)
        assert not comp.valid

        with pytest.raises(ValueError, match="Composition is not valid, contains: Na, Cl, X0+"):
            Composition("NaClX", strict=True)

    def test_remove_charges(self):
        comp1 = Composition({"Al3+": 2.0, "O2-": 3.0})

        comp2 = Composition({"Al": 2.0, "O": 3.0})
        assert str(comp1) != str(comp2)

        comp1 = comp1.remove_charges()
        assert str(comp1) == str(comp2)

        comp1 = comp1.remove_charges()
        assert str(comp1) == str(comp2)

        comp1 = Composition({"Fe3+": 2.0, "Fe2+": 3.0, "O2-": 6.0})
        comp2 = Composition({"Fe": 5.0, "O": 6.0})
        assert str(comp1) != str(comp2)

        comp1 = comp1.remove_charges()
        assert str(comp1) == str(comp2)

    def test_replace(self):
        Fe2O3 = Composition("Fe2O3")
        Cu2O3 = Composition("Cu2O3")
        MgCuO3 = Composition("MgCuO3")
        Mg2Cu2O3 = Composition("Mg2Cu2O3")

        Cu2O3_repl = Fe2O3.replace({"Fe": "Cu"})
        assert Cu2O3_repl == Cu2O3

        # handles one-to-many substitutions
        MgCuO3_repl = Fe2O3.replace({"Fe": {"Cu": 0.5, "Mg": 0.5}})
        assert MgCuO3_repl == MgCuO3

        # handles unnormalized one-to-many substitutions
        Mg2Cu2O3_repl = Fe2O3.replace({"Fe": {"Cu": 1, "Mg": 1}})
        assert Mg2Cu2O3_repl == Mg2Cu2O3

        # leaves the composition unchanged when replacing non-existent species
        assert Fe2O3 == Fe2O3.replace({"Li": "Cu"})

        # check for complex substitutions where element is involved at
        # multiple places
        Ca2NF = Composition("Ca2NF")
        example_sub_1 = {"Ca": "Sr", "N": "O", "F": "O"}
        c_new_1 = Ca2NF.replace(example_sub_1)
        assert c_new_1 == Composition("Sr2O2")

        example_sub_2 = {"Ca": "Sr", "N": "F", "F": "Cl"}
        c_new_2 = Ca2NF.replace(example_sub_2)
        assert c_new_2 == Composition("Sr2ClF")

        example_sub_3 = {"Ca": "Sr", "N": "F", "F": "N"}
        c_new_3 = Ca2NF.replace(example_sub_3)
        assert c_new_3 == Composition("Sr2NF")

        # Check with oxidation-state decorated compositions
        Ca2NF_oxi = Ca2NF.add_charges_from_oxi_state_guesses()
        example_sub_4 = {"Ca2+": "Mg2+", "N3-": "O2-", "F-": "O2-"}
        c_new_4 = Ca2NF_oxi.replace(example_sub_4)
        assert c_new_4 == Composition("Mg2O2").add_charges_from_oxi_state_guesses()

    def test_is_charge_balanced(self):
        false_dct = dict.fromkeys("FeO FeO2 MgO Mg2O3 Mg2O4".split(), False)
        true_dct = dict.fromkeys("Fe2O3 FeO CaTiO3 SrTiO3 MgO Mg2O2".split(), True)

        for formula, expected in (false_dct | true_dct).items():
            comp = Composition(formula)
            # by default, compositions contain elements, not species and hence have no oxidation states
            assert comp.charge is None

            # convert elements to species with oxidation states
            oxi_comp = comp.add_charges_from_oxi_state_guesses()
            assert oxi_comp.charge_balanced is expected, f"Failed for {formula=}"

            if expected is True:
                assert abs(oxi_comp.charge) < Composition.charge_balanced_tolerance
            else:
                assert oxi_comp.charge is None

    def test_isotopes(self):
        composition = Composition({"D": 2, "O": 1})
        assert "Deuterium" in [elem.long_name for elem in composition.elements]

        # adding oxidation state removes Deuterium characteristic
        composition = composition.add_charges_from_oxi_state_guesses()
        assert "Deuterium" not in [elem.long_name for elem in composition.elements]

        # however the user can explicitly add an oxidation state to deuterium
        composition = Composition({"D+": 2, "O": 1})
        assert composition.elements[0].oxi_state == 1
        assert "Deuterium" in [elem.long_name for elem in composition.elements]

    def test_curly_bracket_deeply_nested_formulas(self):
        """Test parsing of bulk metallic glass formulas with complex nested brackets collected in
        Ward et al. (2018) https://doi.org/10.1016/j.actamat.2018.08.002.
        """
        for formula, expected in {
            "{[(Fe0.6Co0.4)0.75B0.2Si0.05]0.96Nb0.04}100": "Nb4 Fe43.2 Co28.8 Si4.8 B19.2",
            "{[(Fe0.6Co0.4)0.75B0.2Si0.05]0.96Nb0.04}99Cr1": "Nb3.96 Cr1 Fe42.768 Co28.512 Si4.752 B19.008",
            "{[(Fe0.6Co0.4)0.75B0.2Si0.05]0.96Nb0.04}98Cr2": "Nb3.92 Cr2 Fe42.336 Co28.224 Si4.704 B18.816",
            "{[(Fe0.6Co0.4)0.75B0.2Si0.05]0.96Nb0.04}97Cr3": "Nb3.88 Cr3 Fe41.904 Co27.936 Si4.656 B18.624",
            "{[(Fe0.6Co0.4)0.75B0.2Si0.05]0.96Nb0.04}96Cr4": "Nb3.84 Cr4 Fe41.472 Co27.648 Si4.608 B18.432",
        }.items():
            assert Composition(formula).formula == expected


def test_reduce_formula():
    assert reduce_formula({"Li": 2, "Mn": 4, "O": 8}) == ("LiMn2O4", 2)
    assert reduce_formula({"Li": 4, "O": 4}) == ("LiO", 4)
    assert reduce_formula({"Zn": 2, "O": 2, "H": 2}) == ("ZnHO", 2)


def test_composition_error():
    error = CompositionError("Composition error")
    assert isinstance(error, CompositionError)
    assert str(error) == "Composition error"


class TestChemicalPotential:
    def test_init(self):
        dct = {"Fe": 1, Element("Fe"): 1}
        with pytest.raises(ValueError, match="Duplicate potential specified"):
            ChemicalPotential(dct)
        for key in ChemicalPotential(Fe=1):
            assert isinstance(key, Element)

    def test_math(self):
        fe_pot = ChemicalPotential({"Fe": 1})
        o_pot = ChemicalPotential({"O": 2.1})
        pots = ChemicalPotential({"Fe": 1, "O": 2.1})
        pots_x2 = ChemicalPotential({"Fe": 2, "O": 4.2})
        fe_o2 = Composition("FeO2")

        # test get_energy()
        assert pots.get_energy(fe_o2) == approx(5.2)
        assert fe_pot.get_energy(fe_o2, strict=False) == approx(1)
        with pytest.raises(ValueError, match="Potentials not specified for {Element O}"):
            fe_pot.get_energy(fe_o2)

        # test multiplication
        with pytest.raises(TypeError, match="unsupported operand type"):
            _ = pots * pots
        assert pots * 2 == pots_x2
        assert 2 * pots == pots_x2

        # test division
        assert pots_x2 / 2 == pots
        assert pots.__div__(pots) == NotImplemented
        assert pots.__div__(fe_o2) == NotImplemented

        # test add/subtract
        assert pots + pots == pots_x2
        assert pots_x2 - pots == pots
        assert fe_pot + o_pot == pots
        assert fe_pot - o_pot == pots - o_pot - o_pot

    def test_square_brackets(self):
        comp = Composition("(NH4)2[FeCl5(H2O)]")
        assert str(comp) == "N2 H10 Fe1 Cl5 O1"
        # test nested brackets
        comp = Composition("[[[[Fe]]]]")
        assert str(comp) == "Fe1"
        # test nested brackets with charge
        comp = Composition("[N[Fe]2]2")
        assert str(comp) == "N2 Fe4"
