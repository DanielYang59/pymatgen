"""This module defines standard transformations which transforms a structure into
another structure. Standard transformations operate in a structure-wide manner,
rather than site-specific manner.
All transformations should inherit the AbstractTransformation ABC.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

import numpy as np

from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.analysis.elasticity.strain import Deformation
from pymatgen.analysis.ewald import EwaldMinimizer, EwaldSummation
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.core import Composition, get_el_sp
from pymatgen.core.operations import SymmOp
from pymatgen.core.structure import Lattice, Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.symmetry.structure import SymmetrizedStructure
from pymatgen.transformations.site_transformations import PartialRemoveSitesTransformation
from pymatgen.transformations.transformation_abc import AbstractTransformation

if TYPE_CHECKING:
    from numpy.random import Generator
    from typing_extensions import Any, Self

    from pymatgen.core.sites import PeriodicSite
    from pymatgen.util.typing import SpeciesLike


class RotationTransformation(AbstractTransformation):
    """The RotationTransformation applies a rotation to a structure."""

    def __init__(self, axis, angle, angle_in_radians=False):
        """
        Args:
            axis (3x1 array): Axis of rotation, e.g. [1, 0, 0]
            angle (float): Angle to rotate
            angle_in_radians (bool): Set to True if angle is supplied in radians.
                Else degrees are assumed.
        """
        self.axis = axis
        self.angle = angle
        self.angle_in_radians = angle_in_radians
        self._symmop = SymmOp.from_axis_angle_and_translation(self.axis, self.angle, self.angle_in_radians)

    def apply_transformation(self, structure):
        """Apply the transformation.

        Args:
            structure (Structure): Input Structure

        Returns:
            Rotated Structure.
        """
        struct = structure.copy()
        struct.apply_operation(self._symmop)
        return struct

    def __repr__(self):
        return (
            f"Rotation Transformation about axis {self.axis} with angle = "
            f"{self.angle:.4f} {'radians' if self.angle_in_radians else 'degrees'}"
        )

    @property
    def inverse(self):
        """Inverse Transformation."""
        return RotationTransformation(self.axis, -self.angle, self.angle_in_radians)


class OxidationStateDecorationTransformation(AbstractTransformation):
    """This transformation decorates a structure with oxidation states."""

    def __init__(self, oxidation_states):
        """
        Args:
            oxidation_states (dict): Oxidation states supplied as a dict,
            e.g. {"Li":1, "O":-2}.
        """
        self.oxidation_states = oxidation_states

    def apply_transformation(self, structure):
        """Apply the transformation.

        Args:
            structure (Structure): Input Structure

        Returns:
            Oxidation state decorated Structure.
        """
        struct = structure.copy()
        struct.add_oxidation_state_by_element(self.oxidation_states)
        return struct


class AutoOxiStateDecorationTransformation(AbstractTransformation):
    """This transformation automatically decorates a structure with oxidation
    states using a bond valence approach.
    """

    def __init__(
        self,
        symm_tol=0.1,
        max_radius=4,
        max_permutations=100000,
        distance_scale_factor=1.015,
        zeros_on_fail=False,
    ):
        """
        Args:
            symm_tol (float): Symmetry tolerance used to determine which sites are
                symmetrically equivalent. Set to 0 to turn off symmetry.
            max_radius (float): Maximum radius in Angstrom used to find nearest
                neighbors.
            max_permutations (int): Maximum number of permutations of oxidation
                states to test.
            distance_scale_factor (float): A scale factor to be applied. This is
                useful for scaling distances, esp in the case of
                calculation-relaxed structures, which may tend to under (GGA) or
                over bind (LDA). The default of 1.015 works for GGA. For
                experimental structure, set this to 1.
            zeros_on_fail (bool): If True and the BVAnalyzer fails to come up
                with a guess for the oxidation states, we will set the all the
                oxidation states to zero.
        """
        self.symm_tol = symm_tol
        self.max_radius = max_radius
        self.max_permutations = max_permutations
        self.distance_scale_factor = distance_scale_factor
        self.analyzer = BVAnalyzer(symm_tol, max_radius, max_permutations, distance_scale_factor)
        self.zeros_on_fail = zeros_on_fail

    def apply_transformation(self, structure):
        """Apply the transformation.

        Args:
            structure (Structure): Input Structure

        Returns:
            Oxidation state decorated Structure.
        """
        try:
            return self.analyzer.get_oxi_state_decorated_structure(structure)
        except ValueError as er:
            if self.zeros_on_fail:
                struct_ = structure.copy()
                struct_.add_oxidation_state_by_site([0] * len(struct_))
                return struct_
            raise ValueError(f"BVAnalyzer failed with error: {er}")


class OxidationStateRemovalTransformation(AbstractTransformation):
    """This transformation removes oxidation states from a structure."""

    def __init__(self):
        """No arg needed."""

    def apply_transformation(self, structure):
        """Apply the transformation.

        Args:
            structure (Structure): Input Structure

        Returns:
            Non-oxidation state decorated Structure.
        """
        return structure.copy().remove_oxidation_states()


class SupercellTransformation(AbstractTransformation):
    """The SupercellTransformation replicates a unit cell to a supercell."""

    def __init__(self, scaling_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1))):
        """
        Args:
            scaling_matrix: A matrix of transforming the lattice vectors.
                Defaults to the identity matrix. Has to be all integers. e.g.
                [[2,1,0],[0,3,0],[0,0,1]] generates a new structure with
                lattice vectors a" = 2a + b, b" = 3b, c" = c where a, b, and c
                are the lattice vectors of the original structure.
        """
        self.scaling_matrix = scaling_matrix

    @classmethod
    def from_scaling_factors(cls, scale_a: float = 1, scale_b: float = 1, scale_c: float = 1) -> Self:
        """Convenience method to get a SupercellTransformation from a simple
        series of three numbers for scaling each lattice vector. Equivalent to
        calling the normal with [[scale_a, 0, 0], [0, scale_b, 0],
        [0, 0, scale_c]].

        Args:
            scale_a: Scaling factor for lattice direction a. Defaults to 1.
            scale_b: Scaling factor for lattice direction b. Defaults to 1.
            scale_c: Scaling factor for lattice direction c. Defaults to 1.

        Returns:
            SupercellTransformation.
        """
        return cls([[scale_a, 0, 0], [0, scale_b, 0], [0, 0, scale_c]])

    @classmethod
    def from_boundary_distance(
        cls,
        structure: Structure,
        min_boundary_dist: float = 6,
        allow_rotation: bool = False,
        max_atoms: float = -1,
    ) -> Self:
        """Get a SupercellTransformation according to the desired minimum distance between periodic
        boundaries of the resulting supercell.

        Args:
            structure (Structure): Input structure.
            min_boundary_dist (float): Desired minimum distance between all periodic boundaries. Defaults to 6.
            allow_rotation (bool): Whether allowing lattice angles to change. Only useful when
                at least two of the three lattice vectors are required to expand. Defaults to False.
                If True, a SupercellTransformation satisfying min_boundary_dist but with smaller
                number of atoms than the SupercellTransformation with unchanged lattice angles
                can possibly be found. If such a SupercellTransformation cannot be found easily,
                the SupercellTransformation with unchanged lattice angles will be returned.
            max_atoms (int): Maximum number of atoms allowed in the supercell. Defaults to -1 for infinity.

        Returns:
            SupercellTransformation.
        """
        min_expand = np.int8(min_boundary_dist / np.array([structure.lattice.d_hkl(plane) for plane in np.eye(3)]))
        max_atoms = max_atoms if max_atoms > 0 else float("inf")

        # Try to find a scaling_matrix satisfying the required boundary distance with smaller cell.
        if allow_rotation and sum(min_expand != 0) > 1:
            min1, min2, min3 = map(int, min_expand)  # type: ignore[call-overload]
            scaling_matrix = [
                [min1 or 1, 1 if min1 and min2 else 0, 1 if min1 and min3 else 0],
                [-1 if min2 and min1 else 0, min2 or 1, 1 if min2 and min3 else 0],
                [-1 if min3 and min1 else 0, -1 if min3 and min2 else 0, min3 or 1],
            ]
            struct_scaled = structure.make_supercell(scaling_matrix, in_place=False)
            min_expand_scaled = np.int8(
                min_boundary_dist / np.array([struct_scaled.lattice.d_hkl(plane) for plane in np.eye(3)])
            )
            if sum(min_expand_scaled != 0) == 0 and len(struct_scaled) <= max_atoms:
                return cls(scaling_matrix)

        scaling_matrix = np.eye(3) + np.diag(min_expand)  # type: ignore[assignment]
        struct_scaled = structure.make_supercell(scaling_matrix, in_place=False)
        if len(struct_scaled) <= max_atoms:
            return cls(scaling_matrix)

        msg = f"{max_atoms=} exceeded while trying to solve for supercell. You can try lowering {min_boundary_dist=}"
        if not allow_rotation:
            msg += " or set allow_rotation=True"
        raise RuntimeError(msg)

    def apply_transformation(self, structure):
        """Apply the transformation.

        Args:
            structure (Structure): Input Structure

        Returns:
            Supercell Structure.
        """
        return structure * self.scaling_matrix

    def __repr__(self):
        return f"Supercell Transformation with scaling matrix {self.scaling_matrix}"

    @property
    def inverse(self):
        """Raises: NotImplementedError."""
        raise NotImplementedError


class SubstitutionTransformation(AbstractTransformation):
    """This transformation substitutes species for one another."""

    def __init__(
        self,
        species_map: (
            dict[SpeciesLike, SpeciesLike | dict[SpeciesLike, float]] | list[tuple[SpeciesLike, SpeciesLike]]
        ),
    ) -> None:
        """
        Args:
            species_map: A dict or list of tuples containing the species mapping in
                string-string pairs. e.g. {"Li": "Na"} or [("Fe2+","Mn2+")].
                Multiple substitutions can be done. Overloaded to accept
                sp_and_occu dictionary E.g. {"Si: {"Ge":0.75, "C":0.25}},
                which substitutes a single species with multiple species to
                generate a disordered structure.
        """
        self.species_map = species_map
        self._species_map = dict(species_map)
        for key, val in self._species_map.items():
            if isinstance(val, tuple | list):
                self._species_map[key] = dict(val)  # type: ignore[assignment]

    def apply_transformation(self, structure: Structure) -> Structure:
        """Apply the transformation.

        Args:
            structure (Structure): Input Structure

        Returns:
            Substituted Structure.
        """
        species_map = {}
        for k, v in self._species_map.items():
            value = {get_el_sp(x): y for x, y in v.items()} if isinstance(v, dict) else get_el_sp(v)
            species_map[get_el_sp(k)] = value
        struct = structure.copy()
        struct.replace_species(species_map)  # type: ignore[arg-type]
        return struct

    def __repr__(self):
        return "Substitution Transformation :" + ", ".join([f"{k}->{v}" for k, v in self._species_map.items()])

    @property
    def inverse(self):
        """Inverse Transformation."""
        inverse_map = {v: k for k, v in self._species_map.items()}
        return SubstitutionTransformation(inverse_map)


class RemoveSpeciesTransformation(AbstractTransformation):
    """Remove all occurrences of some species from a structure."""

    def __init__(self, species_to_remove):
        """
        Args:
            species_to_remove: List of species to remove. e.g. ["Li", "Mn"].
        """
        self.species_to_remove = species_to_remove

    def apply_transformation(self, structure):
        """Apply the transformation.

        Args:
            structure (Structure): Input Structure

        Returns:
            Structure with species removed.
        """
        struct = structure.copy()
        for sp in self.species_to_remove:
            struct.remove_species([get_el_sp(sp)])
        return struct

    def __repr__(self):
        return "Remove Species Transformation :" + ", ".join(self.species_to_remove)


class PartialRemoveSpecieTransformation(AbstractTransformation):
    """Remove fraction of specie from a structure.

    Requires an oxidation state decorated structure for Ewald sum to be
    computed.

    Given that the solution to selecting the right removals is NP-hard, there
    are several algorithms provided with varying degrees of accuracy and speed.
    Please see
    pymatgen.transformations.site_transformations.PartialRemoveSitesTransformation.
    """

    ALGO_FAST = 0
    ALGO_COMPLETE = 1
    ALGO_BEST_FIRST = 2
    ALGO_ENUMERATE = 3

    def __init__(self, specie_to_remove, fraction_to_remove, algo=ALGO_FAST):
        """
        Args:
            specie_to_remove: Species to remove. Must have oxidation state e.g.
                "Li+"
            fraction_to_remove: Fraction of specie to remove. e.g. 0.5
            algo: This parameter allows you to choose the algorithm to perform
                ordering. Use one of PartialRemoveSpecieTransformation.ALGO_*
                variables to set the algo.
        """
        self.specie_to_remove = specie_to_remove
        self.fraction_to_remove = fraction_to_remove
        self.algo = algo

    def apply_transformation(self, structure: Structure, return_ranked_list: bool | int = False):
        """Apply the transformation.

        Args:
            structure: input structure
            return_ranked_list (bool | int, optional): If return_ranked_list is int, that number of structures

                is returned. If False, only the single lowest energy structure is returned. Defaults to False.

        Returns:
            Depending on returned_ranked list, either a transformed structure
            or a list of dictionaries, where each dictionary is of the form
            {"structure" = .... , "other_arguments"}
            the key "transformation" is reserved for the transformation that
            was actually applied to the structure.
            This transformation is parsed by the alchemy classes for generating
            a more specific transformation history. Any other information will
            be stored in the transformation_parameters dictionary in the
            transmuted structure class.
        """
        sp = get_el_sp(self.specie_to_remove)
        specie_indices = [i for i in range(len(structure)) if structure[i].species == Composition({sp: 1})]
        trans = PartialRemoveSitesTransformation([specie_indices], [self.fraction_to_remove], algo=self.algo)
        return trans.apply_transformation(structure, return_ranked_list)

    @property
    def is_one_to_many(self) -> bool:
        """Transform one structure to many."""
        return True

    def __repr__(self):
        species = self.specie_to_remove
        fraction_to_remove = self.fraction_to_remove
        algo = self.algo
        return f"PartialRemoveSpecieTransformation({species=}, {fraction_to_remove=}, {algo=})"


class OrderDisorderedStructureTransformation(AbstractTransformation):
    """Order a disordered structure. The disordered structure must be oxidation
    state decorated for Ewald sum to be computed. No attempt is made to perform
    symmetry determination to reduce the number of combinations.

    Hence, attempting to order a large number of disordered sites can be extremely
    expensive. The time scales approximately with the
    number of possible combinations. The algorithm can currently compute
    approximately 5,000,000 permutations per minute.

    Also, simple rounding of the occupancies are performed, with no attempt
    made to achieve a target composition. This is usually not a problem for
    most ordering problems, but there can be times where rounding errors may
    result in structures that do not have the desired composition.
    This second step will be implemented in the next iteration of the code.

    If multiple fractions for a single species are found for different sites,
    these will be treated separately if the difference is above a threshold
    tolerance. currently this is .1

    For example, if a fraction of .25 Li is on sites 0, 1, 2, 3 and .5 on sites
    4, 5, 6, 7 then 1 site from [0, 1, 2, 3] will be filled and 2 sites from [4, 5, 6, 7]
    will be filled, even though a lower energy combination might be found by
    putting all lithium in sites [4, 5, 6, 7].

    USE WITH CARE.
    """

    ALGO_FAST = 0
    ALGO_COMPLETE = 1
    ALGO_BEST_FIRST = 2
    ALGO_RANDOM = -1

    def __init__(
        self,
        algo: int = ALGO_FAST,
        symmetrized_structures: bool = False,
        no_oxi_states: bool = False,
        occ_tol: float = 0.25,
        symprec: float | None = None,
        angle_tolerance: float | None = None,
    ):
        """
        Args:
            algo (int): Algorithm to use.
            symmetrized_structures (bool): Whether the input structures are
                instances of SymmetrizedStructure, and that their symmetry
                should be used for the grouping of sites.
            no_oxi_states (bool): Whether to remove oxidation states prior to
                ordering.
            occ_tol (float): Occupancy tolerance. If the total occupancy of a group is within this value
                of an integer, it will be rounded to that integer otherwise raise a ValueError.
                Defaults to 0.25.
            symprec : float or None (default)
                If a float, and symmetrized_structures is True, the linear tolerance
                used to symmetrize structures with SpacegroupAnalyzer.
            angle_tolerance : float or None (default)
                If a float, and symmetrized_structures is True, the angle tolerance
                used to symmetrize structures with SpacegroupAnalyzer.
        """
        self.algo = algo
        self._all_structures: list = []
        self.no_oxi_states = no_oxi_states
        self.symmetrized_structures = symmetrized_structures
        self.symprec = symprec
        self.angle_tolerance = angle_tolerance
        self.occ_tol = occ_tol

    def apply_transformation(
        self, structure: Structure | SymmetrizedStructure, return_ranked_list: bool | int = False
    ) -> Structure | list[Structure] | list[dict[str, Any]]:
        """For this transformation, the apply_transformation method will return
        only the ordered structure with the lowest Ewald energy, to be
        consistent with the method signature of the other transformations.
        However, all structures are stored in the all_structures attribute in
        the transformation object for easy access.

        Args:
            structure: Oxidation state decorated disordered structure to order
            return_ranked_list (bool | int, optional): If return_ranked_list is int, that number of structures
                is returned. If False, only the single lowest energy structure is returned. Defaults to False.

        Returns:
            Depending on returned_ranked list, either a transformed structure
            or a list of dictionaries, where each dictionary is of the form
            {"structure" = .... , "other_arguments"}
            the key "transformation" is reserved for the transformation that
            was actually applied to the structure.
            This transformation is parsed by the alchemy classes for generating
            a more specific transformation history. Any other information will
            be stored in the transformation_parameters dictionary in the
            transmuted structure class.
        """
        try:
            n_to_return = int(return_ranked_list)
        except ValueError:
            n_to_return = 1

        n_to_return = max(1, n_to_return)

        if self.no_oxi_states:
            structure = Structure.from_sites(structure)
            for idx, site in enumerate(structure):
                structure[idx] = {f"{k.symbol}0+": v for k, v in site.species.items()}  # type: ignore[assignment]

        if self.symmetrized_structures and not isinstance(structure, SymmetrizedStructure):
            structure = SpacegroupAnalyzer(
                structure, **{k: getattr(self, k) for k in ("symprec", "angle_tolerance") if getattr(self, k, None)}
            ).get_symmetrized_structure()

        equivalent_sites: list[list[int]] = []
        exemplars: list[PeriodicSite] = []
        # generate list of equivalent sites to order
        # equivalency is determined by sp_and_occu and symmetry
        # if symmetrized structure is true
        for idx, site in enumerate(structure):
            if site.is_ordered:
                continue
            for j, ex in enumerate(exemplars):
                sp = ex.species
                if not site.species.almost_equals(sp):
                    continue
                if self.symmetrized_structures:
                    sym_equiv = structure.find_equivalent_sites(ex)  # type:ignore[attr-defined]
                    sym_test = site in sym_equiv
                else:
                    sym_test = True
                if sym_test:
                    equivalent_sites[j].append(idx)
                    break
            else:
                equivalent_sites.append([idx])
                exemplars.append(site)

        # generate the list of manipulations and input structure
        struct = Structure.from_sites(structure)

        # We will first create an initial ordered structure by filling all sites
        # with the species that has the highest oxidation state (initial_sp)
        # replacing all other species on a given site.
        # then, we process a list of manipulations to get the final structure.
        # The manipulations are of the format:
        # [oxi_ratio, 1, [0,1,2,3], Li+]
        # which means -- Place 1 Li+ in any of these 4 sites
        # the oxi_ratio is the ratio of the oxidation state of the species to
        # the initial species. This is used to determine the energy of the
        # manipulation in the EwaldMinimizer, but is not used in the purely random
        # algorithm.
        manipulations = []
        for group in equivalent_sites:
            total_occupancy = dict(
                sum((structure[idx].species for idx in group), Composition()).items()  # type: ignore[attr-defined]
            )
            # round total occupancy to possible values
            for key, val in total_occupancy.items():
                if abs(val - round(val)) > self.occ_tol:
                    raise ValueError("Occupancy fractions not consistent with size of unit cell")
                total_occupancy[key] = round(val)
            # start with an ordered structure
            initial_sp = max(total_occupancy, key=lambda x: abs(x.oxi_state))  # type:ignore[arg-type]
            for idx in group:
                struct[idx] = initial_sp
            # determine the manipulations
            for key, val in total_occupancy.items():
                if key == initial_sp:
                    continue
                oxi_ratio = key.oxi_state / initial_sp.oxi_state if initial_sp.oxi_state else 0  # type:ignore[operator]
                manipulation = [oxi_ratio, val, list(group), key]
                manipulations.append(manipulation)
            # determine the number of empty sites
            empty = len(group) - sum(total_occupancy.values())
            if empty > 0.5:
                manipulations.append([0, empty, list(group), None])

        if self.algo == self.ALGO_RANDOM:
            rand_structures = get_randomly_manipulated_structures(
                struct=struct, manipulations=manipulations, n_return=n_to_return
            )
            if return_ranked_list:
                return [
                    {"energy": 0.0, "energy_above_minimum": 0.0, "structure": s} for s in rand_structures[:n_to_return]
                ]
            return rand_structures[0]

        matrix = EwaldSummation(struct).total_energy_matrix
        ewald_m = EwaldMinimizer(matrix, manipulations, n_to_return, self.algo)

        self._all_structures = []

        lowest_energy = ewald_m.output_lists[0][0]
        n_atoms = sum(structure.composition.values())

        for output in ewald_m.output_lists:
            struct_copy = struct.copy()
            # do deletions afterwards because they screw up the indices of the
            # structure
            del_indices = []
            for manipulation in output[1]:
                if manipulation[1] is None:
                    del_indices.append(manipulation[0])
                else:
                    struct_copy[manipulation[0]] = manipulation[1]  # type:ignore[index, assignment]
            struct_copy.remove_sites(del_indices)  # type:ignore[arg-type]

            if self.no_oxi_states:
                struct_copy.remove_oxidation_states()

            self._all_structures.append(
                {
                    "energy": output[0],
                    "energy_above_minimum": (output[0] - lowest_energy) / n_atoms,
                    "structure": struct_copy.get_sorted_structure(),
                }
            )

        if return_ranked_list:
            return self._all_structures[:n_to_return]  # type: ignore[return-value]
        return self._all_structures[0]["structure"]

    def __repr__(self):
        return "Order disordered structure transformation"

    @property
    def is_one_to_many(self) -> bool:
        """Transform one structure to many."""
        return True

    @property
    def lowest_energy_structure(self):
        """Lowest energy structure found."""
        return self._all_structures[0]["structure"]


class PrimitiveCellTransformation(AbstractTransformation):
    """This class finds the primitive cell of the input structure.
    It returns a structure that is not necessarily orthogonalized
    Author: Will Richards.
    """

    def __init__(self, tolerance=0.5):
        """
        Args:
            tolerance (float): Tolerance for each coordinate of a particular
                site. For example, [0.5, 0, 0.5] in Cartesian coordinates will be
                considered to be on the same coordinates as [0, 0, 0] for a
                tolerance of 0.5. Defaults to 0.5.
        """
        self.tolerance = tolerance

    def apply_transformation(self, structure):
        """Get most primitive cell for structure.

        Args:
            structure: A structure

        Returns:
            The most primitive structure found. The returned structure is
            guaranteed to have len(new structure) <= len(structure).
        """
        return structure.get_primitive_structure(tolerance=self.tolerance)

    def __repr__(self):
        return "Primitive cell transformation"


class ConventionalCellTransformation(AbstractTransformation):
    """This class finds the conventional cell of the input structure."""

    def __init__(self, symprec: float = 0.01, angle_tolerance=5, international_monoclinic=True):
        """
        Args:
            symprec (float): tolerance as in SpacegroupAnalyzer
            angle_tolerance (float): angle tolerance as in SpacegroupAnalyzer
            international_monoclinic (bool): whether to use beta (True) or alpha (False)
        as the non-right-angle in the unit cell.
        """
        self.symprec = symprec
        self.angle_tolerance = angle_tolerance
        self.international_monoclinic = international_monoclinic

    def apply_transformation(self, structure):
        """Get most primitive cell for structure.

        Args:
            structure: A structure

        Returns:
            The same structure in a conventional standard setting
        """
        sga = SpacegroupAnalyzer(structure, symprec=self.symprec, angle_tolerance=self.angle_tolerance)
        return sga.get_conventional_standard_structure(international_monoclinic=self.international_monoclinic)

    def __repr__(self):
        return "Conventional cell transformation"


class PerturbStructureTransformation(AbstractTransformation):
    """This transformation perturbs a structure by a specified distance in random
    directions. Used for breaking symmetries.
    """

    def __init__(
        self,
        distance: float = 0.01,
        min_distance: float | None = None,
    ):
        """
        Args:
            distance: Distance of perturbation in angstroms. All sites
                will be perturbed by exactly that distance in a random
                direction.
            min_distance: Minimum distance for the perturbation range. Defaults to None, which means all
            perturbations are the same magnitude.
        """
        self.distance = distance
        self.min_distance = min_distance

    def apply_transformation(self, structure: Structure) -> Structure:
        """Apply the transformation.

        Args:
            structure: Input Structure

        Returns:
            Structure with sites perturbed.
        """
        struct = structure.copy()
        struct.perturb(self.distance, min_distance=self.min_distance)
        return struct

    def __repr__(self):
        return f"PerturbStructureTransformation : Min_distance = {self.min_distance}"


class DeformStructureTransformation(AbstractTransformation):
    """This transformation deforms a structure by a deformation gradient matrix."""

    def __init__(self, deformation=((1, 0, 0), (0, 1, 0), (0, 0, 1))):
        """
        Args:
            deformation (array): deformation gradient for the transformation.
        """
        self._deform = Deformation(deformation)
        self.deformation = self._deform.tolist()

    def apply_transformation(self, structure):
        """Apply the transformation.

        Args:
            structure (Structure): Input Structure

        Returns:
            Deformed Structure.
        """
        return self._deform.apply_to_structure(structure)

    def __repr__(self):
        return f"DeformStructureTransformation : Deformation = {self.deformation}"

    @property
    def inverse(self):
        """Inverse Transformation."""
        return DeformStructureTransformation(self._deform.inv)


class DiscretizeOccupanciesTransformation(AbstractTransformation):
    """Discretize the site occupancies in a disordered structure; useful for
    grouping similar structures or as a pre-processing step for order-disorder
    transformations.
    """

    def __init__(self, max_denominator=5, tol: float | None = None, fix_denominator=False):
        """
        Args:
            max_denominator:
                An integer maximum denominator for discretization. A higher
                denominator allows for finer resolution in the site occupancies.
            tol:
                A float that sets the maximum difference between the original and
                discretized occupancies before throwing an error. If None, it is
                set to 1 / (4 * max_denominator).
            fix_denominator(bool):
                If True, will enforce a common denominator for all species.
                This prevents a mix of denominators (for example, 1/3, 1/4)
                that might require large cell sizes to perform an enumeration.
                'tol' needs to be > 1.0 in some cases.
        """
        self.max_denominator = max_denominator
        self.tol = tol if tol is not None else 1 / (4 * max_denominator)
        self.fix_denominator = fix_denominator

    def apply_transformation(self, structure) -> Structure:
        """Discretize the site occupancies in the structure.

        Args:
            structure: disordered Structure to discretize occupancies

        Returns:
            Structure: new disordered Structure instance with occupancies discretized
        """
        if structure.is_ordered:
            return structure

        species = [dict(sp) for sp in structure.species_and_occu]

        for sp in species:
            for k in sp:
                old_occ = sp[k]
                new_occ = float(Fraction(old_occ).limit_denominator(self.max_denominator))
                if self.fix_denominator:
                    new_occ = np.around(old_occ * self.max_denominator) / self.max_denominator
                if round(abs(old_occ - new_occ), 6) > self.tol:
                    raise RuntimeError("Cannot discretize structure within tolerance!")
                sp[k] = new_occ

        return Structure(structure.lattice, species, structure.frac_coords)

    def __repr__(self):
        return "DiscretizeOccupanciesTransformation"


class ChargedCellTransformation(AbstractTransformation):
    """The ChargedCellTransformation applies a charge to a structure (or defect
    object).
    """

    def __init__(self, charge=0):
        """
        Args:
            charge: A integer charge to apply to the structure.
                Defaults to zero. Has to be a single integer. e.g. 2.
        """
        self.charge = charge

    def apply_transformation(self, structure):
        """Apply the transformation.

        Args:
            structure (Structure): Input Structure

        Returns:
            Charged Structure.
        """
        struct = structure.copy()
        struct.set_charge(self.charge)
        return struct

    def __repr__(self):
        return f"Structure with charge {self.charge}"

    @property
    def inverse(self):
        """Raises: NotImplementedError."""
        raise NotImplementedError


class ScaleToRelaxedTransformation(AbstractTransformation):
    """Takes the unrelaxed and relaxed structure and applies its site and volume
    relaxation to a structurally similar structures (e.g. bulk: NaCl and PbTe
    (rock-salt), slab: Sc(10-10) and Mg(10-10) (hcp), GB: Mo(001) sigma 5 GB,
    Fe(001) sigma 5). Useful for finding an initial guess of a set of similar
    structures closer to its most relaxed state.
    """

    def __init__(self, unrelaxed_structure, relaxed_structure, species_map=None):
        """
        Args:
            unrelaxed_structure (Structure): Initial, unrelaxed structure
            relaxed_structure (Structure): Relaxed structure
            species_map (dict): A dict or list of tuples containing the species mapping in
                string-string pairs. The first species corresponds to the relaxed
                structure while the second corresponds to the species in the
                structure to be scaled. e.g. {"Li":"Na"} or [("Fe2+","Mn2+")].
                Multiple substitutions can be done. Overloaded to accept
                sp_and_occu dictionary E.g. {"Si: {"Ge":0.75, "C":0.25}},
                which substitutes a single species with multiple species to
                generate a disordered structure.
        """
        # Get the ratio matrix for lattice relaxation which can be
        # applied to any similar structure to simulate volumetric relaxation
        relax_params = list(relaxed_structure.lattice.abc)
        relax_params.extend(relaxed_structure.lattice.angles)
        unrelax_params = list(unrelaxed_structure.lattice.abc)
        unrelax_params.extend(unrelaxed_structure.lattice.angles)

        self.params_percent_change = [relax_params[idx] / unrelax_params[idx] for idx in range(len(relax_params))]

        self.unrelaxed_structure = unrelaxed_structure
        self.relaxed_structure = relaxed_structure
        self.species_map = species_map

    def apply_transformation(self, structure):
        """Get a copy of structure with lattice parameters
        and sites scaled to the same degree as the relaxed_structure.

        Args:
            structure (Structure): A structurally similar structure in
                regards to crystal and site positions.
        """
        if self.species_map is None:
            match = StructureMatcher()
            s_map = match.get_best_electronegativity_anonymous_mapping(self.unrelaxed_structure, structure)
        else:
            s_map = self.species_map

        params = list(structure.lattice.abc)
        params.extend(structure.lattice.angles)
        new_lattice = Lattice.from_parameters(
            *(param * self.params_percent_change[idx] for idx, param in enumerate(params))
        )
        species, frac_coords = [], []
        for site in self.relaxed_structure:
            species.append(s_map[site.specie])
            frac_coords.append(site.frac_coords)

        return Structure(new_lattice, species, frac_coords)

    def __repr__(self):
        return "ScaleToRelaxedTransformation"


def _sample_random_manipulation(manipulation, rng, manipulated) -> list[tuple[int, SpeciesLike]]:
    """Sample a single random manipulation.

    Each manipulation is given in the form of a tuple
    `(oxi_ratio, nsites, indices, sp)` where:
    Which means choose nsites from the list of indices and replace them
    With the species `sp`.
    """
    _, nsites, indices, sp = manipulation
    maniped_indices = [i for i, _ in manipulated]
    allowed_sites = [i for i in indices if i not in maniped_indices]
    if len(allowed_sites) < nsites:
        raise RuntimeError(
            "No valid manipulations possible. "
            f" You have already applied a manipulation to each site in this group {indices}"
        )
    sampled_sites = rng.choice(allowed_sites, nsites, replace=False).tolist()
    sampled_sites.sort()
    return [(i, sp) for i in sampled_sites]


def _get_manipulation(manipulations: list, rng: Generator, max_attempts, seen: set[tuple]) -> tuple:
    """Apply each manipulation."""
    for _ in range(max_attempts):
        manipulated: list[tuple] = []
        for manip_ in manipulations:
            new_manips = _sample_random_manipulation(manip_, rng, manipulated)
            manipulated += new_manips
        tm_ = tuple(manipulated)
        if tm_ not in seen:
            return tm_
    raise RuntimeError(
        "Could not apply manipulations to structure"
        "this is likely because you have already applied all the possible manipulations"
    )


def _apply_manip(struct, manipulations) -> Structure:
    """Apply manipulations to a structure."""
    struct_copy = struct.copy()
    rm_indices = []
    for manip in manipulations:
        idx, sp = manip
        if sp is None:
            rm_indices.append(idx)
        else:
            struct_copy.replace(idx, sp)
    struct_copy.remove_sites(rm_indices)
    return struct_copy


def get_randomly_manipulated_structures(
    struct: Structure, manipulations: list, seed=None, n_return: int = 1
) -> list[Structure]:
    """Get a structure with random manipulations applied.

    Args:
        struct: Input structure
        manipulations: List of manipulations to apply
        seed: Seed for random number generator
        n_return: Number of structures to return

    Returns:
        List of structures with manipulations applied.
    """
    rng = np.random.default_rng(seed)
    seen: set[tuple] = set()
    sampled_manips = []

    for _ in range(n_return):
        manip_ = _get_manipulation(manipulations, rng, 1000, seen)
        seen.add(manip_)
        sampled_manips.append(manip_)

    return [_apply_manip(struct, manip) for manip in sampled_manips]
