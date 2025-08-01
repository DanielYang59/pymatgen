"""This module implements classes to perform bond valence analyses."""

from __future__ import annotations

import functools
import math
import operator
import os
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np
from monty.serialization import loadfn

from pymatgen.core import Element, Species, get_el_sp
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

if TYPE_CHECKING:
    from pymatgen.core import Structure

# List of electronegative elements specified in M. O'Keefe, & N. Brese,
# JACS, 1991, 113(9), 3226-3229. doi:10.1021/ja00009a002.
ELECTRONEG = [Element(sym) for sym in "H B C Si N P As Sb O S Se Te F Cl Br I".split()]

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Read in BV parameters.
BV_PARAMS = {}
for key, val in loadfn(f"{MODULE_DIR}/bvparam_1991.yaml").items():
    BV_PARAMS[Element(key)] = val

# Read in YAML containing data-mined ICSD BV data.
all_data = loadfn(f"{MODULE_DIR}/icsd_bv.yaml")
ICSD_BV_DATA = {Species.from_str(sp): data for sp, data in all_data["bvsum"].items()}
PRIOR_PROB = {Species.from_str(sp): data for sp, data in all_data["occurrence"].items()}


def calculate_bv_sum(site, nn_list, scale_factor=1.0):
    """Calculate the BV sum of a site.

    Args:
        site (PeriodicSite): The central site to calculate the bond valence
        nn_list ([Neighbor]): A list of namedtuple Neighbors having "distance"
            and "site" attributes
        scale_factor (float): A scale factor to be applied. This is useful for
            scaling distance, esp in the case of calculation-relaxed structures
            which may tend to under (GGA) or over bind (LDA).
    """
    el1 = Element(site.specie.symbol)
    bv_sum = 0
    for nn in nn_list:
        el2 = Element(nn.specie.symbol)
        if (el1 in ELECTRONEG or el2 in ELECTRONEG) and el1 != el2:
            r1 = BV_PARAMS[el1]["r"]
            r2 = BV_PARAMS[el2]["r"]
            c1 = BV_PARAMS[el1]["c"]
            c2 = BV_PARAMS[el2]["c"]
            R = r1 + r2 - r1 * r2 * (math.sqrt(c1) - math.sqrt(c2)) ** 2 / (c1 * r1 + c2 * r2)
            vij = math.exp((R - nn.nn_distance * scale_factor) / 0.31)
            bv_sum += vij * (1 if el1.X < el2.X else -1)
    return bv_sum


def calculate_bv_sum_unordered(site, nn_list, scale_factor=1):
    """Calculate the BV sum of a site for unordered structures.

    Args:
        site (PeriodicSite): The central site to calculate the bond valence
        nn_list ([Neighbor]): A list of namedtuple Neighbors having "distance"
            and "site" attributes
        scale_factor (float): A scale factor to be applied. This is useful for
            scaling distance, esp in the case of calculation-relaxed structures
            which may tend to under (GGA) or over bind (LDA).
    """
    # If the site "site" has N partial occupations as : f_{site}_0,
    # f_{site}_1, ... f_{site}_N of elements
    # X_{site}_0, X_{site}_1, ... X_{site}_N, and each neighbors nn_i in nn
    # has N_{nn_i} partial occupations as :
    # f_{nn_i}_0, f_{nn_i}_1, ..., f_{nn_i}_{N_{nn_i}}, then the bv sum of
    # site "site" is obtained as :
    # \sum_{nn} \sum_j^N \sum_k^{N_{nn}} f_{site}_j f_{nn_i}_k vij_full
    # where vij_full is the valence bond of the fully occupied bond
    bv_sum = 0
    for specie1, occu1 in site.species.items():
        el1 = Element(specie1.symbol)
        for nn in nn_list:
            for specie2, occu2 in nn.species.items():
                el2 = Element(specie2.symbol)
                if (el1 in ELECTRONEG or el2 in ELECTRONEG) and el1 != el2:
                    r1 = BV_PARAMS[el1]["r"]
                    r2 = BV_PARAMS[el2]["r"]
                    c1 = BV_PARAMS[el1]["c"]
                    c2 = BV_PARAMS[el2]["c"]
                    R = r1 + r2 - r1 * r2 * (math.sqrt(c1) - math.sqrt(c2)) ** 2 / (c1 * r1 + c2 * r2)
                    vij = math.exp((R - nn.nn_distance * scale_factor) / 0.31)
                    bv_sum += occu1 * occu2 * vij * (1 if el1.X < el2.X else -1)
    return bv_sum


class BVAnalyzer:
    """
    This class implements a maximum a posteriori (MAP) estimation method to
    determine oxidation states in a structure. The algorithm is as follows:
    1) The bond valence sum of all symmetrically distinct sites in a structure
    is calculated using the element-based parameters in M. O'Keefe, & N. Brese,
    JACS, 1991, 113(9), 3226-3229. doi:10.1021/ja00009a002.
    2) The posterior probabilities of all oxidation states is then calculated
    using: P(oxi_state/BV) = K * P(BV/oxi_state) * P(oxi_state), where K is
    a constant factor for each element. P(BV/oxi_state) is calculated as a
    Gaussian with mean and std deviation determined from an analysis of
    the ICSD. The posterior P(oxi_state) is determined from a frequency
    analysis of the ICSD.
    3) The oxidation states are then ranked in order of decreasing probability
    and the oxidation state combination that result in a charge neutral cell
    is selected.
    """

    CHARGE_NEUTRALITY_TOLERANCE = 0.000_01

    def __init__(
        self,
        symm_tol=0.1,
        max_radius=4,
        max_permutations=100_000,
        distance_scale_factor=1.015,
        charge_neutrality_tolerance=CHARGE_NEUTRALITY_TOLERANCE,
        forbidden_species=None,
    ):
        """Initialize the BV analyzer, with useful defaults.

        Args:
            symm_tol:
                Symmetry tolerance used to determine which sites are
                symmetrically equivalent. Set to 0 to turn off symmetry.
            max_radius:
                Maximum radius in Angstrom used to find nearest neighbors.
            max_permutations:
                The maximum number of permutations of oxidation states to test.
            distance_scale_factor:
                A scale factor to be applied. This is useful for scaling
                distances, esp in the case of calculation-relaxed structures
                which may tend to under (GGA) or over bind (LDA). The default
                of 1.015 works for GGA. For experimental structure, set this to
                1.
            charge_neutrality_tolerance:
                Tolerance on the charge neutrality when unordered structures
                are at stake.
            forbidden_species:
                List of species that are forbidden (example : ["O-"] cannot be
                used) It is used when e.g. someone knows that some oxidation
                state cannot occur for some atom in a structure or list of
                structures.
        """
        self.symm_tol = symm_tol
        self.max_radius = max_radius
        self.max_permutations = max_permutations
        self.dist_scale_factor = distance_scale_factor
        self.charge_neutrality_tolerance = charge_neutrality_tolerance
        forbidden_species = [get_el_sp(sp) for sp in forbidden_species] if forbidden_species else []
        self.icsd_bv_data = (
            {get_el_sp(specie): data for specie, data in ICSD_BV_DATA.items() if specie not in forbidden_species}
            if len(forbidden_species) > 0
            else ICSD_BV_DATA
        )

    def _calc_site_probabilities(self, site, nn):
        el = site.specie.symbol
        bv_sum = calculate_bv_sum(site, nn, scale_factor=self.dist_scale_factor)
        prob = {}
        for sp, data in self.icsd_bv_data.items():
            if sp.symbol == el and sp.oxi_state != 0 and data["std"] > 0:
                u = data["mean"]
                sigma = data["std"]
                # Calculate posterior probability. Note that constant
                # factors are ignored. They have no effect on the results.
                prob[sp.oxi_state] = math.exp(-((bv_sum - u) ** 2) / 2 / (sigma**2)) / sigma * PRIOR_PROB[sp]
        # Normalize the probabilities
        try:
            prob = {k: v / sum(prob.values()) for k, v in prob.items()}
        except ZeroDivisionError:
            prob = dict.fromkeys(prob, 0)
        return prob

    def _calc_site_probabilities_unordered(self, site, nn):
        bv_sum = calculate_bv_sum_unordered(site, nn, scale_factor=self.dist_scale_factor)
        prob = {}
        for specie in site.species:
            el = specie.symbol

            prob[el] = {}
            for sp, data in self.icsd_bv_data.items():
                if sp.symbol == el and sp.oxi_state != 0 and data["std"] > 0:
                    u = data["mean"]
                    sigma = data["std"]
                    # Calculate posterior probability. Note that constant
                    # factors are ignored. They have no effect on the results.
                    prob[el][sp.oxi_state] = math.exp(-((bv_sum - u) ** 2) / 2 / (sigma**2)) / sigma * PRIOR_PROB[sp]
            # Normalize the probabilities
            try:
                prob[el] = {k: v / sum(prob[el].values()) for k, v in prob[el].items()}
            except ZeroDivisionError:
                prob[el] = dict.fromkeys(prob[el], 0)
        return prob

    def get_valences(self, structure: Structure):
        """Get a list of valences for each site in the structure.

        Args:
            structure: Structure to analyze

        Returns:
            A list of valences for each site in the structure (for an ordered structure),
            e.g. [1, 1, -2] or a list of lists with the valences for each fractional
            element of each site in the structure (for an unordered structure), e.g. [[2,
            4], [3], [-2], [-2], [-2]]

        Raises:
            A ValueError if the valences cannot be determined.
        """
        els = [Element(el.symbol) for el in structure.elements]

        if diff := set(els) - set(BV_PARAMS):
            raise ValueError(f"Structure contains elements not in set of BV parameters: {diff}")

        # Perform symmetry determination and get sites grouped by symmetry.
        if self.symm_tol:
            finder = SpacegroupAnalyzer(structure, self.symm_tol)
            symm_structure = finder.get_symmetrized_structure()
            equi_sites = symm_structure.equivalent_sites
        else:
            equi_sites = [[site] for site in structure]

        # Sort the equivalent sites by decreasing electronegativity.
        equi_sites = sorted(equi_sites, key=lambda sites: -sites[0].species.average_electroneg)

        # Get a list of valences and probabilities for each symmetrically distinct site.
        valences = []
        all_prob = []
        if structure.is_ordered:
            for sites in equi_sites:
                test_site = sites[0]
                nn = structure.get_neighbors(test_site, self.max_radius)
                prob = self._calc_site_probabilities(test_site, nn)
                all_prob.append(prob)
                val = list(prob)
                # Sort valences in order of decreasing probability.
                val = sorted(val, key=lambda v: -prob[v])
                # Retain probabilities that are at least 1/100 of highest prob.
                valences.append(list(filter(lambda v: prob[v] > 0.01 * prob[val[0]], val)))
        else:
            full_all_prob = []
            for sites in equi_sites:
                test_site = sites[0]
                nn = structure.get_neighbors(test_site, self.max_radius)
                prob = self._calc_site_probabilities_unordered(test_site, nn)
                all_prob.append(prob)
                full_all_prob.extend(prob.values())
                vals = []
                for elem, _ in get_z_ordered_elmap(test_site.species):
                    val = list(prob[elem.symbol])
                    # Sort valences in order of decreasing probability.
                    val = sorted(val, key=lambda v: -prob[elem.symbol][v])
                    # Retain probabilities that are at least 1/100 of highest prob.
                    filtered = list(
                        filter(
                            lambda v: prob[elem.symbol][v] > 1e-3 * prob[elem.symbol][val[0]],
                            val,
                        )
                    )
                    vals.append(filtered)
                valences.append(vals)

        # make variables needed for recursion
        attrib = []
        if structure.is_ordered:
            n_sites = np.array(list(map(len, equi_sites)))
            valence_min = np.array(list(map(min, valences)))
            valence_max = np.array(list(map(max, valences)))

            self._n = 0
            self._best_score = 0
            self._best_vset = None

            def evaluate_assignment(v_set):
                el_oxi = defaultdict(list)
                for idx, sites in enumerate(equi_sites):
                    el_oxi[sites[0].specie.symbol].append(v_set[idx])
                max_diff = max(max(v) - min(v) for v in el_oxi.values())
                if max_diff > 1:
                    return
                score = functools.reduce(operator.mul, [all_prob[idx][val] for idx, val in enumerate(v_set)])
                if score > self._best_score:
                    self._best_vset = v_set
                    self._best_score = score

            def _recurse(assigned=None):
                # recurses to find permutations of valences based on whether a
                # charge balanced assignment can still be found
                if self._n > self.max_permutations:
                    return
                if assigned is None:
                    assigned = []

                i = len(assigned)
                highest = valence_max.copy()
                highest[:i] = assigned
                highest *= n_sites
                highest = np.sum(highest)

                lowest = valence_min.copy()
                lowest[:i] = assigned
                lowest *= n_sites
                lowest = np.sum(lowest)

                if highest < 0 or lowest > 0:
                    self._n += 1
                    return

                if i == len(valences):
                    evaluate_assignment(assigned)
                    self._n += 1
                    return
                for v in valences[i]:
                    new_assigned = list(assigned)
                    _recurse([*new_assigned, v])
                return

        else:
            n_sites = np.array([len(sites) for sites in equi_sites])
            tmp = []
            for idx, n_site in enumerate(n_sites):
                for _ in valences[idx]:
                    tmp.append(n_site)
                    attrib.append(idx)
            new_n_sites = np.array(tmp)
            fractions = []
            elements = []
            for sites in equi_sites:
                for sp, occu in get_z_ordered_elmap(sites[0].species):
                    elements.append(sp.symbol)
                    fractions.append(occu)
            fractions = np.array(fractions, float)  # type: ignore[assignment]
            new_valences = [val for vals in valences for val in vals]
            valence_min = np.array([min(val) for val in new_valences], float)
            valence_max = np.array([max(val) for val in new_valences], float)

            self._n = 0
            self._best_score = 0
            self._best_vset = None

            def evaluate_assignment(v_set):
                el_oxi = defaultdict(list)
                jj = 0
                for sites in equi_sites:
                    for specie, _ in get_z_ordered_elmap(sites[0].species):
                        el_oxi[specie.symbol].append(v_set[jj])
                        jj += 1
                max_diff = max(max(v) - min(v) for v in el_oxi.values())
                if max_diff > 2:
                    return

                score = functools.reduce(
                    operator.mul,
                    [all_prob[attrib[iv]][elements[iv]][vv] for iv, vv in enumerate(v_set)],
                )
                if score > self._best_score:
                    self._best_vset = v_set
                    self._best_score = score

            def _recurse(assigned=None):
                # recurses to find permutations of valences based on whether a
                # charge balanced assignment can still be found
                if self._n > self.max_permutations:
                    return
                if assigned is None:
                    assigned = []

                i = len(assigned)
                highest = valence_max.copy()
                highest[:i] = assigned
                highest *= new_n_sites
                highest *= fractions
                highest = np.sum(highest)

                lowest = valence_min.copy()
                lowest[:i] = assigned
                lowest *= new_n_sites
                lowest *= fractions
                lowest = np.sum(lowest)

                if highest < -self.charge_neutrality_tolerance or lowest > self.charge_neutrality_tolerance:
                    self._n += 1
                    return

                if i == len(new_valences):
                    evaluate_assignment(assigned)
                    self._n += 1
                    return

                for v in new_valences[i]:
                    new_assigned = list(assigned)
                    _recurse([*new_assigned, v])

                return

        _recurse()

        if self._best_vset:
            if structure.is_ordered:
                assigned = {}
                for val, sites in zip(self._best_vset, equi_sites, strict=True):
                    for site in sites:
                        assigned[site] = val

                return [int(assigned[site]) for site in structure]
            assigned = {}
            new_best_vset = [[] for _ in equi_sites]
            for ival, val in enumerate(self._best_vset):
                new_best_vset[attrib[ival]].append(val)
            for val, sites in zip(new_best_vset, equi_sites, strict=True):
                for site in sites:
                    assigned[site] = val

            return [[int(frac_site) for frac_site in assigned[site]] for site in structure]
        raise ValueError("Valences cannot be assigned!")

    def get_oxi_state_decorated_structure(self, structure: Structure) -> Structure:
        """Get an oxidation state decorated structure. This currently works only
        for ordered structures only.

        Args:
            structure: Structure to analyze

        Returns:
            Structure: modified with oxidation state decorations.

        Raises:
            ValueError if the valences cannot be determined.
        """
        struct = structure.copy()
        if struct.is_ordered:
            valences = self.get_valences(struct)
            struct.add_oxidation_state_by_site(valences)
        else:
            valences = self.get_valences(struct)
            struct = add_oxidation_state_by_site_fraction(struct, valences)
        return struct


def get_z_ordered_elmap(comp):
    """
    Arbitrary ordered element map on the elements/species of a composition of a
    given site in an unordered structure. Returns a list of tuples (
    element_or_specie: occupation) in the arbitrary order.

    The arbitrary order is based on the Z of the element and the smallest
    fractional occupations first.
    Example : {"Ni3+": 0.2, "Ni4+": 0.2, "Cr3+": 0.15, "Zn2+": 0.34,
    "Cr4+": 0.11} will yield the species in the following order :
    Cr4+, Cr3+, Ni3+, Ni4+, Zn2+ ... or
    Cr4+, Cr3+, Ni4+, Ni3+, Zn2+
    """
    return sorted((elem, comp[elem]) for elem in comp)


def add_oxidation_state_by_site_fraction(structure: Structure, oxidation_states: list[list[int]]) -> Structure:
    """
    Add oxidation states to a structure by fractional site.

    Args:
        oxidation_states (list[list[int]]): List of list of oxidation states for each
            site fraction for each site.
            e.g. [[2, 4], [3], [-2], [-2], [-2]]
    """
    try:
        for idx, site in enumerate(structure):
            new_sp: dict[Species, float] = defaultdict(float)
            for j, (el, occu) in enumerate(get_z_ordered_elmap(site.species)):
                specie = Species(el.symbol, oxidation_states[idx][j])
                new_sp[specie] += occu
            structure[idx] = new_sp
        return structure
    except IndexError:
        raise ValueError("Oxidation state of all sites must be specified in the list.")
