"""Piezo sensitivity analysis module."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import numpy as np
from monty.dev import requires

from pymatgen.core.tensors import Tensor
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

try:
    from phonopy import Phonopy
    from phonopy.harmonic import dynmat_to_fc as dyntofc
except ImportError:
    Phonopy = dyntofc = None


if TYPE_CHECKING:
    from pymatgen.core import Structure

__author__ = "Handong Ling"
__copyright__ = "Copyright 2019, The Materials Project"
__version__ = "1.0"
__maintainer__ = "Handong Ling"
__email__ = "hling@lbl.gov"
__status__ = "Development"
__date__ = "Feb, 2019"


class BornEffectiveCharge:
    """This class describes the Nx3x3 born effective charge tensor."""

    def __init__(self, structure: Structure, bec, pointops, tol: float = 1e-3):
        """
        Create an BornEffectiveChargeTensor object defined by a
        structure, point operations of the structure's atomic sites.
        Note that the constructor uses __new__ rather than __init__
        according to the standard method of subclassing numpy ndarrays.

        Args:
            input_matrix (Nx3x3 array-like): the Nx3x3 array-like
                representing the born effective charge tensor
        """
        self.structure = structure
        self.bec = bec
        self.pointops = pointops
        self.BEC_operations = None
        if np.sum(self.bec) >= tol:
            warnings.warn("Input born effective charge tensor does not satisfy charge neutrality", stacklevel=2)

    def get_BEC_operations(self, eigtol=1e-5, opstol=1e-3):
        """Get the symmetry operations which maps the tensors
        belonging to equivalent sites onto each other in the form
        [site index 1, site index 2, [Symmops mapping from site
        index 1 to site index 2]].

        Args:
            eigtol (float): tolerance for determining if two sites are
            related by symmetry
            opstol (float): tolerance for determining if a symmetry
            operation relates two sites

        Returns:
            list of symmetry operations mapping equivalent sites and
            the indexes of those sites.
        """
        bec = self.bec
        struct = self.structure
        ops = SpacegroupAnalyzer(struct).get_symmetry_operations(cartesian=True)
        uniq_point_ops = list(ops)

        for ops in self.pointops:
            for op in ops:
                if op not in uniq_point_ops:
                    uniq_point_ops.append(op)

        passed = []
        relations = []
        for site, val in enumerate(bec):
            unique = 1
            eig1, _vecs1 = np.linalg.eig(val)
            index = np.argsort(eig1)
            new_eig = np.real([eig1[index[0]], eig1[index[1]], eig1[index[2]]])
            for index, p in enumerate(passed):
                if np.allclose(new_eig, p[1], atol=eigtol):
                    relations.append([site, index])
                    unique = 0
                    passed.append([site, p[0], new_eig])
                    break
            if unique == 1:
                relations.append([site, site])
                passed.append([site, new_eig])
        BEC_operations = []
        for atom, r in enumerate(relations):
            BEC_operations.append(r)
            BEC_operations[atom].append([])

            for op in uniq_point_ops:
                new = op.transform_tensor(self.bec[r[1]])

                # Check the matrix it references
                if np.allclose(new, self.bec[r[0]], atol=opstol):
                    BEC_operations[atom][2].append(op)

        self.BEC_operations = BEC_operations
        return BEC_operations

    def get_rand_BEC(self, max_charge=1):
        """Generate a random born effective charge tensor which obeys a structure's
        symmetry and the acoustic sum rule.

        Args:
            max_charge (float): maximum born effective charge value

        Returns:
            np.array Born effective charge tensor
        """
        n_atoms = len(self.structure)
        BEC = np.zeros((n_atoms, 3, 3))
        for atom, ops in enumerate(self.BEC_operations):
            if ops[0] == ops[1]:
                temp_tensor = Tensor(np.random.default_rng().random((3, 3)) - 0.5)
                temp_tensor = sum(temp_tensor.transform(symm_op) for symm_op in self.pointops[atom]) / len(
                    self.pointops[atom]
                )
                BEC[atom] = temp_tensor
            else:
                temp_fcm = np.zeros([3, 3])
                for op in ops[2]:
                    temp_fcm += op.transform_tensor(BEC[self.BEC_operations[atom][1]])
                BEC[ops[0]] = temp_fcm
                if len(ops[2]) != 0:
                    BEC[ops[0]] /= len(ops[2])

        # Enforce Acoustic Sum
        disp_charge = np.einsum("ijk->jk", BEC) / n_atoms
        add = np.zeros([n_atoms, 3, 3])

        for atom, ops in enumerate(self.BEC_operations):
            if ops[0] == ops[1]:
                temp_tensor = Tensor(disp_charge)
                temp_tensor = sum(temp_tensor.transform(symm_op) for symm_op in self.pointops[atom]) / len(
                    self.pointops[atom]
                )
                add[ops[0]] = temp_tensor
            else:
                temp_tensor = np.zeros([3, 3])
                for op in ops[2]:
                    temp_tensor += op.transform_tensor(add[self.BEC_operations[atom][1]])

                add[ops[0]] = temp_tensor

                if len(ops) != 0:
                    add[ops[0]] /= len(ops[2])

        BEC -= add

        return BEC * max_charge


class InternalStrainTensor:
    """
    This class describes the Nx3x3x3 internal tensor defined by a
    structure, point operations of the structure's atomic sites.
    """

    def __init__(self, structure: Structure, ist, pointops, tol: float = 1e-3):
        """
        Create an InternalStrainTensor object.

        Args:
            input_matrix (Nx3x3x3 array-like): the Nx3x3x3 array-like
                representing the internal strain tensor
        """
        self.structure = structure
        self.ist = ist
        self.pointops = pointops
        self.IST_operations: list[list[list]] = []

        obj = self.ist
        if not np.allclose(obj, np.transpose(obj, (0, 1, 3, 2)), atol=tol, rtol=0):
            warnings.warn("Input internal strain tensor does not satisfy standard symmetries", stacklevel=2)

    def get_IST_operations(self, opstol=1e-3) -> list[list[list]]:
        """Get the symmetry operations which maps the tensors
        belonging to equivalent sites onto each other in the form
        [site index 1, site index 2, [SymmOps mapping from site
        index 1 to site index 2]].

        Args:
            opstol (float): tolerance for determining if a symmetry
            operation relates two sites

        Returns:
            list[list[list]]: symmetry operations mapping equivalent sites and the indexes of those sites.
        """
        struct = self.structure
        ops = SpacegroupAnalyzer(struct).get_symmetry_operations(cartesian=True)
        uniq_point_ops = list(ops)

        for ops in self.pointops:
            for op in ops:
                if op not in uniq_point_ops:
                    uniq_point_ops.append(op)

        IST_operations: list[list[list]] = []
        for atom_idx in range(len(self.ist)):
            IST_operations.append([])
            for j in range(atom_idx):
                for op in uniq_point_ops:
                    new = op.transform_tensor(self.ist[j])

                    # Check the matrix it references
                    if np.allclose(new, self.ist[atom_idx], atol=opstol):
                        IST_operations[atom_idx].append([j, op])

        self.IST_operations = IST_operations
        return IST_operations

    def get_rand_IST(self, max_force=1):
        """Generate a random internal strain tensor which obeys a structure's
        symmetry and the acoustic sum rule.

        Args:
            max_force (float): maximum born effective charge value

        Returns:
            InternalStrainTensor
        """
        n_atoms = len(self.structure)
        IST = np.zeros((n_atoms, 3, 3, 3))
        for atom, ops in enumerate(self.IST_operations):
            temp_tensor = np.zeros([3, 3, 3])
            for op in ops:
                temp_tensor += op[1].transform_tensor(IST[op[0]])

            if len(ops) == 0:
                temp_tensor = Tensor(np.random.default_rng().random((3, 3, 3)) - 0.5)
                for dim in range(3):
                    temp_tensor[dim] = (temp_tensor[dim] + temp_tensor[dim].T) / 2
                temp_tensor = sum(temp_tensor.transform(symm_op) for symm_op in self.pointops[atom]) / len(
                    self.pointops[atom]
                )
            IST[atom] = temp_tensor
            if len(ops) != 0:
                IST[atom] /= len(ops)

        return IST * max_force


class ForceConstantMatrix:
    """
    This class describes the NxNx3x3 force constant matrix defined by a
    structure, point operations of the structure's atomic sites, and the
    shared symmetry operations between pairs of atomic sites.
    """

    def __init__(self, structure: Structure, fcm, pointops, sharedops, tol: float = 1e-3):
        """
        Create an ForceConstantMatrix object.

        Args:
            input_matrix (NxNx3x3 array-like): the NxNx3x3 array-like
                representing the force constant matrix
        """
        self.structure = structure
        self.fcm = fcm
        self.pointops = pointops
        self.sharedops = sharedops
        self.FCM_operations = None

    def get_FCM_operations(self, eigtol=1e-5, opstol=1e-5):
        """Get the symmetry operations which maps the tensors
        belonging to equivalent sites onto each other in the form
        [site index 1a, site index 1b, site index 2a, site index 2b,
        [Symmops mapping from site index 1a, 1b to site index 2a, 2b]].

        Args:
            eigtol (float): tolerance for determining if two sites are
            related by symmetry
            opstol (float): tolerance for determining if a symmetry
            operation relates two sites

        Returns:
            list of symmetry operations mapping equivalent sites and
            the indexes of those sites.
        """
        struct = self.structure
        ops = SpacegroupAnalyzer(struct).get_symmetry_operations(cartesian=True)
        uniq_point_ops = list(ops)

        for ops in self.pointops:
            for op in ops:
                if op not in uniq_point_ops:
                    uniq_point_ops.append(op)

        passed = []
        relations = []
        for atom1 in range(len(self.fcm)):
            for atom2 in range(atom1, len(self.fcm)):
                unique = 1
                eig1, _vecs1 = np.linalg.eig(self.fcm[atom1][atom2])
                index = np.argsort(eig1)
                new_eig = np.real([eig1[index[0]], eig1[index[1]], eig1[index[2]]])

                for p in passed:
                    if np.allclose(new_eig, p[2], atol=eigtol):
                        relations.append([atom1, atom2, p[0], p[1]])
                        unique = 0
                        break
                if unique == 1:
                    relations.append([atom1, atom2, atom2, atom1])
                    passed.append([atom1, atom2, np.real(new_eig)])
        FCM_operations = []
        for entry, r in enumerate(relations):
            FCM_operations.append(r)
            FCM_operations[entry].append([])

            good = 0
            for op in uniq_point_ops:
                new = op.transform_tensor(self.fcm[r[2]][r[3]])

                if np.allclose(new, self.fcm[r[0]][r[1]], atol=opstol):
                    FCM_operations[entry][4].append(op)
                    good = 1
            if r[0] == r[3] and r[1] == r[2]:
                good = 1
            if r[0] == r[2] and r[1] == r[3]:
                good = 1
            if good == 0:
                FCM_operations[entry] = [r[0], r[1], r[3], r[2]]
                FCM_operations[entry].append([])
                for op in uniq_point_ops:
                    new = op.transform_tensor(self.fcm[r[2]][r[3]])
                    if np.allclose(
                        new.T,
                        self.fcm[r[0]][r[1]],
                        atol=opstol,
                    ):
                        FCM_operations[entry][4].append(op)

        self.FCM_operations = FCM_operations
        return FCM_operations

    def get_unstable_FCM(self, max_force=1):
        """Generate an unsymmetrized force constant matrix.

        Args:
            max_charge (float): maximum born effective charge value

        Returns:
            numpy array representing the force constant matrix
        """
        struct = self.structure
        operations = self.FCM_operations
        # set max force in reciprocal space
        n_sites = len(struct)
        D = (1 / max_force) * 2 * (np.ones([n_sites * 3, n_sites * 3]))
        for op in operations:
            same = transpose = 0
            if op[0] == op[1] and op[0] == op[2] and op[0] == op[3]:
                same = 1
            if op[0] == op[3] and op[1] == op[2]:
                transpose = 1
            if transpose == 0 and same == 0:
                D[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] = np.zeros([3, 3])
                D[3 * op[1] : 3 * op[1] + 3, 3 * op[0] : 3 * op[0] + 3] = np.zeros([3, 3])

                for symop in op[4]:
                    temp_fcm = D[3 * op[2] : 3 * op[2] + 3, 3 * op[3] : 3 * op[3] + 3]
                    temp_fcm = symop.transform_tensor(temp_fcm)
                    D[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] += temp_fcm

                if len(op[4]) != 0:
                    D[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] /= len(op[4])

                D[3 * op[1] : 3 * op[1] + 3, 3 * op[0] : 3 * op[0] + 3] = D[
                    3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3
                ].T
                continue

            temp_tensor = Tensor(np.random.default_rng().random((3, 3)) - 0.5) * max_force

            temp_tensor_sum = sum(temp_tensor.transform(symm_op) for symm_op in self.sharedops[op[0]][op[1]])
            temp_tensor_sum /= len(self.sharedops[op[0]][op[1]])
            if op[0] != op[1]:
                for pair in range(len(op[4])):
                    temp_tensor2 = temp_tensor_sum.T
                    temp_tensor2 = op[4][pair].transform_tensor(temp_tensor2)
                    temp_tensor_sum = (temp_tensor_sum + temp_tensor2) / 2

            else:
                temp_tensor_sum = (temp_tensor_sum + temp_tensor_sum.T) / 2

            D[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] = temp_tensor_sum
            D[3 * op[1] : 3 * op[1] + 3, 3 * op[0] : 3 * op[0] + 3] = temp_tensor_sum.T

        return D

    def get_symmetrized_FCM(self, unsymmetrized_fcm, max_force=1):
        """Generate a symmetrized force constant matrix from an unsymmetrized matrix.

        Args:
            unsymmetrized_fcm (numpy array): unsymmetrized force constant matrix
            max_charge (float): maximum born effective charge value

        Returns:
            3Nx3N numpy array representing the force constant matrix
        """
        operations = self.FCM_operations
        for op in operations:
            same = transpose = 0
            if op[0] == op[1] and op[0] == operations[2] and op[0] == op[3]:
                same = 1
            if op[0] == op[3] and op[1] == op[2]:
                transpose = 1
            if transpose == 0 and same == 0:
                unsymmetrized_fcm[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] = np.zeros([3, 3])

                for symop in op[4]:
                    temp_fcm = unsymmetrized_fcm[3 * op[2] : 3 * op[2] + 3, 3 * op[3] : 3 * op[3] + 3]
                    temp_fcm = symop.transform_tensor(temp_fcm)

                    unsymmetrized_fcm[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] += temp_fcm

                if len(op[4]) != 0:
                    unsymmetrized_fcm[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] /= len(op[4])
                unsymmetrized_fcm[3 * op[1] : 3 * op[1] + 3, 3 * op[0] : 3 * op[0] + 3] = unsymmetrized_fcm[
                    3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3
                ].T
                continue

            temp_tensor = Tensor(unsymmetrized_fcm[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3])
            temp_tensor_sum = sum(temp_tensor.transform(symm_op) for symm_op in self.sharedops[op[0]][op[1]])
            if len(self.sharedops[op[0]][op[1]]) != 0:
                temp_tensor_sum /= len(self.sharedops[op[0]][op[1]])

            # Apply the proper transformation if there is an equivalent already
            if op[0] != op[1]:
                for pair in range(len(op[4])):
                    temp_tensor2 = temp_tensor_sum.T
                    temp_tensor2 = op[4][pair].transform_tensor(temp_tensor2)
                    temp_tensor_sum = (temp_tensor_sum + temp_tensor2) / 2

            else:
                temp_tensor_sum = (temp_tensor_sum + temp_tensor_sum.T) / 2

            unsymmetrized_fcm[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] = temp_tensor_sum
            unsymmetrized_fcm[3 * op[1] : 3 * op[1] + 3, 3 * op[0] : 3 * op[0] + 3] = temp_tensor_sum.T

        return unsymmetrized_fcm

    def get_stable_FCM(self, fcm, fcmasum=10):
        """Generate a symmetrized force constant matrix that obeys the objects symmetry
        constraints, has no unstable modes and also obeys the acoustic sum rule through an
        iterative procedure.

        Args:
            fcm (numpy array): unsymmetrized force constant matrix
            fcmasum (int): number of iterations to attempt to obey the acoustic sum
                rule

        Returns:
            3Nx3N numpy array representing the force constant matrix
        """
        check = count = 0
        while check == 0:
            # if re-symmetrizing brings back unstable modes 20 times, the method breaks
            if count > 20:
                check = 1
                break

            eigs, vecs = np.linalg.eig(fcm)

            max_eig = np.max(-1 * eigs)
            eig_sort = np.argsort(np.abs(eigs))
            rng = np.random.default_rng()
            for idx in range(3, len(eigs)):
                if eigs[eig_sort[idx]] > 1e-6:
                    eigs[eig_sort[idx]] = -1 * max_eig * rng.random()
            diag = np.real(np.eye(len(fcm)) * eigs)

            fcm = np.real(np.matmul(np.matmul(vecs, diag), vecs.T))
            fcm = self.get_symmetrized_FCM(fcm)
            fcm = self.get_asum_FCM(fcm)
            eigs, vecs = np.linalg.eig(fcm)
            unstable_modes = 0
            eig_sort = np.argsort(np.abs(eigs))
            for idx in range(3, len(eigs)):
                if eigs[eig_sort[idx]] > 1e-6:
                    unstable_modes = 1
            if unstable_modes == 1:
                count += 1
                continue
            check = 1

        return fcm

    # acoustic sum

    def get_asum_FCM(self, fcm: np.ndarray, numiter: int = 15):
        """Generate a symmetrized force constant matrix that obeys the objects symmetry
        constraints and obeys the acoustic sum rule through an iterative procedure.

        Args:
            fcm (numpy array): 3Nx3N unsymmetrized force constant matrix
            numiter (int): number of iterations to attempt to obey the acoustic sum
                rule

        Returns:
            numpy array representing the force constant matrix
        """
        # set max force in reciprocal space
        operations = self.FCM_operations
        if operations is None:
            raise RuntimeError("No symmetry operations found. Run get_FCM_operations first.")

        n_sites = len(self.structure)

        D = np.ones([n_sites * 3, n_sites * 3])
        for _ in range(numiter):
            X = np.real(fcm)

            # symmetry operations
            pastrow = 0
            total = np.zeros([3, 3])
            for col in range(n_sites):
                total += X[:3, col * 3 : col * 3 + 3]

            total /= n_sites
            for op in operations:
                same = transpose = 0
                if op[0] == op[1] and op[0] == op[2] and op[0] == op[3]:
                    same = 1
                if op[0] == op[3] and op[1] == op[2]:
                    transpose = 1
                if transpose == 0 and same == 0:
                    D[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] = np.zeros([3, 3])

                    for symop in op[4]:
                        tempfcm = D[3 * op[2] : 3 * op[2] + 3, 3 * op[3] : 3 * op[3] + 3]
                        tempfcm = symop.transform_tensor(tempfcm)

                        D[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] += tempfcm

                    if len(op[4]) != 0:
                        D[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] /= len(op[4])
                    D[3 * op[1] : 3 * op[1] + 3, 3 * op[0] : 3 * op[0] + 3] = D[
                        3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3
                    ].T
                    continue
                # Get the difference in the sum up to this point
                curr_row = op[0]
                if curr_row != pastrow:
                    total = np.zeros([3, 3])
                    for col in range(n_sites):
                        total += X[curr_row * 3 : curr_row * 3 + 3, col * 3 : col * 3 + 3]
                    for col in range(curr_row):
                        total -= D[curr_row * 3 : curr_row * 3 + 3, col * 3 : col * 3 + 3]
                    total /= n_sites - curr_row
                pastrow = curr_row

                # Apply the point symmetry operations of the site
                temp_tensor = Tensor(total)
                temp_tensor_sum = sum(temp_tensor.transform(symm_op) for symm_op in self.sharedops[op[0]][op[1]])

                if len(self.sharedops[op[0]][op[1]]) != 0:
                    temp_tensor_sum /= len(self.sharedops[op[0]][op[1]])

                # Apply the proper transformation if there is an equivalent already
                if op[0] != op[1]:
                    for pair in range(len(op[4])):
                        temp_tensor2 = temp_tensor_sum.T
                        temp_tensor2 = op[4][pair].transform_tensor(temp_tensor2)
                        temp_tensor_sum = (temp_tensor_sum + temp_tensor2) / 2

                else:
                    temp_tensor_sum = (temp_tensor_sum + temp_tensor_sum.T) / 2

                D[3 * op[0] : 3 * op[0] + 3, 3 * op[1] : 3 * op[1] + 3] = temp_tensor_sum
                D[3 * op[1] : 3 * op[1] + 3, 3 * op[0] : 3 * op[0] + 3] = temp_tensor_sum.T
            fcm -= D

        return fcm

    @requires(Phonopy, "phonopy not installed!")
    def get_rand_FCM(self, asum=15, force=10):
        """Generate a symmetrized force constant matrix from an unsymmetrized matrix
        that has no unstable modes and also obeys the acoustic sum rule through an
        iterative procedure.

        Args:
            force (float): maximum force constant
            asum (int): number of iterations to attempt to obey the acoustic sum
                rule

        Returns:
            NxNx3x3 np.array representing the force constant matrix
        """
        from pymatgen.io.phonopy import get_phonopy_structure

        n_sites = len(self.structure)
        structure = get_phonopy_structure(self.structure)
        pn_struct = Phonopy(structure, np.eye(3), np.eye(3))

        dyn = self.get_unstable_FCM(force)
        dyn = self.get_stable_FCM(dyn)

        dyn = np.reshape(dyn, (n_sites, 3, n_sites, 3)).swapaxes(1, 2)

        dyn_mass = np.zeros([len(self.structure), len(self.structure), 3, 3])
        masses = [self.structure[idx].specie.atomic_mass for idx in range(n_sites)]

        dyn_mass = np.zeros([n_sites, n_sites, 3, 3])
        for m in range(n_sites):
            for n in range(n_sites):
                dyn_mass[m][n] = dyn[m][n] * np.sqrt(masses[m]) * np.sqrt(masses[n])

        supercell = pn_struct.supercell
        primitive = pn_struct.primitive

        converter = dyntofc.DynmatToForceConstants(primitive, supercell)

        dyn = np.reshape(np.swapaxes(dyn_mass, 1, 2), (n_sites * 3, n_sites * 3))

        converter.dynamical_matrices = [dyn]

        converter.run()
        return converter.force_constants


def get_piezo(BEC, IST, FCM, rcond=0.0001):
    """
    Generate a random piezoelectric tensor based on a structure and corresponding
    symmetry.

    Args:
        BEC (numpy array): Nx3x3 array representing the born effective charge tensor
        IST (numpy array): Nx3x3x3 array representing the internal strain tensor
        FCM (numpy array): NxNx3x3 array representing the born effective charge tensor
        rcondy (float): condition for excluding eigenvalues in the pseudoinverse

    Returns:
        3x3x3 calculated Piezo tensor
    """
    n_sites = len(BEC)
    temp_fcm = np.reshape(np.swapaxes(FCM, 1, 2), (n_sites * 3, n_sites * 3))

    eigs, _vecs = np.linalg.eig(temp_fcm)
    K = np.linalg.pinv(
        -temp_fcm,
        rcond=np.abs(eigs[np.argsort(np.abs(eigs))[2]]) / np.abs(eigs[np.argsort(np.abs(eigs))[-1]]) + rcond,
    )

    K = np.reshape(K, (n_sites, 3, n_sites, 3)).swapaxes(1, 2)
    return np.einsum("ikl,ijlm,jmno->kno", BEC, K, IST) * 16.0216559424  # codespell:ignore kno


@requires(Phonopy, "phonopy not installed!")
def rand_piezo(struct, pointops, sharedops, BEC, IST, FCM, anumiter=10):
    """
    Generate a random piezoelectric tensor based on a structure and corresponding
    symmetry.

    Args:
        struct (pymatgen structure): structure whose symmetry operations the piezo tensor must obey
        pointops: list of point operations obeyed by a single atomic site
        sharedops: list of point operations shared by a pair of atomic sites
        BEC (numpy array): Nx3x3 array representing the born effective charge tensor
        IST (numpy array): Nx3x3x3 array representing the internal strain tensor
        FCM (numpy array): NxNx3x3 array representing the born effective charge tensor
        anumiter (int): number of iterations for acoustic sum rule convergence

    Returns:
        list in the form of [Nx3x3 random born effective charge tenosr,
        Nx3x3x3 random internal strain tensor, NxNx3x3 random force constant matrix, 3x3x3 piezo tensor]
    """
    bec = BornEffectiveCharge(struct, BEC, pointops)
    bec.get_BEC_operations()
    rand_BEC = bec.get_rand_BEC()

    ist = InternalStrainTensor(struct, IST, pointops)
    ist.get_IST_operations()
    rand_IST = ist.get_rand_IST()

    fcm = ForceConstantMatrix(struct, FCM, pointops, sharedops)
    fcm.get_FCM_operations()
    rand_FCM = fcm.get_rand_FCM()

    P = get_piezo(rand_BEC, rand_IST, rand_FCM) * 16.0216559424 / struct.volume

    return (rand_BEC, rand_IST, rand_FCM, P)
