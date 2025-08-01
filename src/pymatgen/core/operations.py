"""This module provides classes that operate on points or vectors in 3D space."""

from __future__ import annotations

import copy
import math
import re
import string
import warnings
from typing import TYPE_CHECKING, Literal, cast

import numpy as np
from monty.json import MSONable

from pymatgen.electronic_structure.core import Magmom
from pymatgen.util.due import Doi, due
from pymatgen.util.string import transformation_to_string

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from numpy.typing import ArrayLike, NDArray
    from typing_extensions import Self

__author__ = "Shyue Ping Ong, Shyam Dwaraknath, Matthew Horton"


class SymmOp(MSONable):
    """A symmetry operation in Cartesian space. Consists of a rotation plus a
    translation. Implementation is as an affine transformation matrix of rank 4
    for efficiency. Read: https://wikipedia.org/wiki/Affine_transformation.

    Attributes:
        affine_matrix (NDArray): A 4x4 array representing the symmetry operation.
    """

    def __init__(
        self,
        affine_transformation_matrix: ArrayLike,
        tol: float = 0.01,
    ) -> None:
        """Initialize the SymmOp from a 4x4 affine transformation matrix.
        In general, this constructor should not be used unless you are
        transferring rotations. Use the static constructors instead to
        generate a SymmOp from proper rotations and translation.

        Args:
            affine_transformation_matrix (4x4 array): Representing an
                affine transformation.
            tol (float): Tolerance for determining if matrices are equal. Defaults to 0.01.

        Raises:
            ValueError: if matrix is not 4x4.
        """
        affine_transformation_matrix = np.asarray(affine_transformation_matrix)
        shape = affine_transformation_matrix.shape
        if shape != (4, 4):
            raise ValueError(f"Affine Matrix must be a 4x4 numpy array, got {shape=}")
        self.affine_matrix = affine_transformation_matrix
        self.tol = tol

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return np.allclose(self.affine_matrix, other.affine_matrix, atol=self.tol)

    def __hash__(self) -> int:
        return 7

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.affine_matrix=})"

    def __str__(self) -> str:
        return "\n".join(
            [
                "Rot:",
                str(self.affine_matrix[:3][:, :3]),
                "tau",
                str(self.affine_matrix[:3][:, 3]),
            ]
        )

    def __mul__(self, other) -> Self:
        """Get a new SymmOp which is equivalent to apply the "other" SymmOp
        followed by this one.
        """
        return type(self)(np.dot(self.affine_matrix, other.affine_matrix))

    @classmethod
    def from_rotation_and_translation(
        cls,
        rotation_matrix: ArrayLike = ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        translation_vec: ArrayLike = (0, 0, 0),
        tol: float = 0.1,
    ) -> Self:
        """Create a symmetry operation from a rotation matrix and a translation
        vector.

        Args:
            rotation_matrix (3x3 array): Rotation matrix.
            translation_vec (3x1 array): Translation vector.
            tol (float): Tolerance to determine if rotation matrix is valid.

        Returns:
            SymmOp object
        """
        rotation_matrix = np.asarray(rotation_matrix)
        translation_vec = np.asarray(translation_vec)
        if rotation_matrix.shape != (3, 3):
            raise ValueError("Rotation Matrix must be a 3x3 numpy array.")
        if translation_vec.shape != (3,):
            raise ValueError("Translation vector must be a rank 1 numpy array with 3 elements.")

        affine_matrix = np.eye(4)
        affine_matrix[:3][:, :3] = rotation_matrix
        affine_matrix[:3][:, 3] = translation_vec
        return cls(affine_matrix, tol)

    def operate(self, point: ArrayLike) -> NDArray[np.float64]:
        """Apply the operation on a point.

        Args:
            point: Cartesian coordinate.

        Returns:
            Coordinates of point after operation.
        """
        affine_point = np.asarray([*point, 1])
        return np.dot(self.affine_matrix, affine_point)[:3]

    def operate_multi(self, points: ArrayLike) -> NDArray[np.float64]:
        """Apply the operation on a list of points.

        Args:
            points: List of Cartesian coordinates

        Returns:
            Numpy array of coordinates after operation
        """
        points = np.asarray(points)
        affine_points = np.concatenate([points, np.ones((*points.shape[:-1], 1))], axis=-1)
        return np.inner(affine_points, self.affine_matrix)[..., :-1]

    def apply_rotation_only(self, vector: NDArray) -> NDArray:
        """Vectors should only be operated by the rotation matrix and not the
        translation vector.

        Args:
            vector (3x1 array): A vector.
        """
        return np.dot(self.rotation_matrix, vector)

    def transform_tensor(self, tensor: NDArray) -> NDArray:
        """Apply rotation portion to a tensor. Note that tensor has to be in
        full form, not the Voigt form.

        Args:
            tensor (numpy array): A rank n tensor

        Returns:
            Transformed tensor.
        """
        dim = tensor.shape
        rank = len(dim)
        if any(val != 3 for val in dim):
            raise ValueError("Some dimension in tensor is not 3.")

        # Build einstein sum string
        lc = string.ascii_lowercase
        indices = lc[:rank], lc[rank : 2 * rank]
        einsum_string = ",".join(a + i for a, i in zip(*indices, strict=True))
        einsum_string += f",{indices[::-1][0]}->{indices[::-1][1]}"
        einsum_args = [self.rotation_matrix] * rank + [tensor]

        return np.einsum(einsum_string, *einsum_args)

    def are_symmetrically_related(
        self,
        point_a: NDArray[np.float64],
        point_b: NDArray[np.float64],
        tol: float = 0.001,
    ) -> bool:
        """Check if two points are symmetrically related.

        Args:
            point_a (3x1 array): First point.
            point_b (3x1 array): Second point.
            tol (float): Absolute tolerance for checking distance. Defaults to 0.001.

        Returns:
            bool: True if self.operate(point_a) == point_b or vice versa.
        """
        return any(np.allclose(self.operate(p1), p2, atol=tol) for p1, p2 in [(point_a, point_b), (point_b, point_a)])

    def are_symmetrically_related_vectors(
        self,
        from_a: NDArray[np.float64],
        to_a: NDArray[np.float64],
        r_a: NDArray[np.float64],
        from_b: NDArray[np.float64],
        to_b: NDArray[np.float64],
        r_b: NDArray[np.float64],
        tol: float = 0.001,
    ) -> tuple[bool, bool]:
        """Check if two vectors, or rather two vectors that connect two points
        each are symmetrically related. r_a and r_b give the change of unit
        cells. Two vectors are also considered symmetrically equivalent if starting
        and end point are exchanged.

        Args:
            from_a (3x1 array): Starting point of the first vector.
            to_a (3x1 array): Ending point of the first vector.
            from_b (3x1 array): Starting point of the second vector.
            to_b (3x1 array): Ending point of the second vector.
            r_a (3x1 array): Change of unit cell of the first vector.
            r_b (3x1 array): Change of unit cell of the second vector.
            tol (float): Absolute tolerance for checking distance.

        Returns:
            tuple[bool, bool]: First bool indicates if the vectors are related,
                the second if the vectors are related but the starting and end point
                are exchanged.
        """
        from_c = self.operate(from_a)
        to_c = self.operate(to_a)

        vec = np.array([from_c, to_c])
        floored = np.floor(vec)
        is_too_close = np.abs(vec - floored) > 1 - tol
        floored[is_too_close] += 1

        r_c = self.apply_rotation_only(r_a) - floored[0] + floored[1]
        from_c %= 1
        to_c %= 1

        if np.allclose(from_b, from_c, atol=tol) and np.allclose(to_b, to_c) and np.allclose(r_b, r_c, atol=tol):
            return True, False
        if np.allclose(to_b, from_c, atol=tol) and np.allclose(from_b, to_c) and np.allclose(r_b, -r_c, atol=tol):
            return True, True
        return False, False

    @property
    def rotation_matrix(self) -> NDArray:
        """A 3x3 numpy.array representing the rotation matrix."""
        return self.affine_matrix[:3][:, :3]

    @property
    def translation_vector(self) -> NDArray:
        """A rank 1 numpy.array of dim 3 representing the translation vector."""
        return self.affine_matrix[:3][:, 3]

    @property
    def inverse(self) -> Self:
        """Inverse of transformation."""
        new_instance = copy.deepcopy(self)
        new_instance.affine_matrix = np.linalg.inv(self.affine_matrix)
        return new_instance

    @staticmethod
    def from_axis_angle_and_translation(
        axis: NDArray,
        angle: float,
        angle_in_radians: bool = False,
        translation_vec: Sequence[float] | NDArray = (0, 0, 0),
    ) -> SymmOp:
        """Generate a SymmOp for a rotation about a given axis plus translation.

        Args:
            axis: The axis of rotation in Cartesian space. For example,
                [1, 0, 0]indicates rotation about x-axis.
            angle (float): Angle of rotation.
            angle_in_radians (bool): Set to True if angles are given in
                radians. Or else, units of degrees are assumed.
            translation_vec: A translation vector. Defaults to zero.

        Returns:
            SymmOp for a rotation about given axis and translation.
        """
        if isinstance(axis, tuple | list):
            axis = np.array(axis)

        vec = np.asarray(translation_vec)

        ang = angle if angle_in_radians else angle * np.pi / 180
        cos_a = math.cos(ang)
        sin_a = math.sin(ang)
        unit_vec: NDArray = axis / np.linalg.norm(axis)  # type:ignore[call-overload]
        rot_mat = np.zeros((3, 3))
        rot_mat[0, 0] = cos_a + unit_vec[0] ** 2 * (1 - cos_a)
        rot_mat[0, 1] = unit_vec[0] * unit_vec[1] * (1 - cos_a) - unit_vec[2] * sin_a
        rot_mat[0, 2] = unit_vec[0] * unit_vec[2] * (1 - cos_a) + unit_vec[1] * sin_a
        rot_mat[1, 0] = unit_vec[0] * unit_vec[1] * (1 - cos_a) + unit_vec[2] * sin_a
        rot_mat[1, 1] = cos_a + unit_vec[1] ** 2 * (1 - cos_a)
        rot_mat[1, 2] = unit_vec[1] * unit_vec[2] * (1 - cos_a) - unit_vec[0] * sin_a
        rot_mat[2, 0] = unit_vec[0] * unit_vec[2] * (1 - cos_a) - unit_vec[1] * sin_a
        rot_mat[2, 1] = unit_vec[1] * unit_vec[2] * (1 - cos_a) + unit_vec[0] * sin_a
        rot_mat[2, 2] = cos_a + unit_vec[2] ** 2 * (1 - cos_a)

        return SymmOp.from_rotation_and_translation(rot_mat, vec)

    @staticmethod
    def from_origin_axis_angle(
        origin: Sequence[float] | NDArray,
        axis: Sequence[float] | NDArray,
        angle: float,
        angle_in_radians: bool = False,
    ) -> SymmOp:
        """Generate a SymmOp for a rotation about a given axis through an
        origin.

        Args:
            origin (3x1 array): The origin which the axis passes through.
            axis (3x1 array): The axis of rotation in Cartesian space. For
                example, [1, 0, 0]indicates rotation about x-axis.
            angle (float): Angle of rotation.
            angle_in_radians (bool): Set to True if angles are given in
                radians. Or else, units of degrees are assumed.

        Returns:
            SymmOp.
        """
        theta: float = angle if angle_in_radians else angle * np.pi / 180
        a: float
        b: float
        c: float
        ax_u: float
        ax_v: float
        ax_w: float
        a, b, c = origin
        ax_u, ax_v, ax_w = axis
        # Set some intermediate values.
        u2, v2, w2 = ax_u * ax_u, ax_v * ax_v, ax_w * ax_w
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        l2 = u2 + v2 + w2
        lsqrt = math.sqrt(l2)

        # Build the matrix entries element by element.
        m11 = (u2 + (v2 + w2) * cos_t) / l2
        m12 = (ax_u * ax_v * (1 - cos_t) - ax_w * lsqrt * sin_t) / l2
        m13 = (ax_u * ax_w * (1 - cos_t) + ax_v * lsqrt * sin_t) / l2
        m14 = (
            a * (v2 + w2)
            - ax_u * (b * ax_v + c * ax_w)
            + (ax_u * (b * ax_v + c * ax_w) - a * (v2 + w2)) * cos_t
            + (b * ax_w - c * ax_v) * lsqrt * sin_t
        ) / l2

        m21 = (ax_u * ax_v * (1 - cos_t) + ax_w * lsqrt * sin_t) / l2
        m22 = (v2 + (u2 + w2) * cos_t) / l2
        m23 = (ax_v * ax_w * (1 - cos_t) - ax_u * lsqrt * sin_t) / l2
        m24 = (
            b * (u2 + w2)
            - ax_v * (a * ax_u + c * ax_w)
            + (ax_v * (a * ax_u + c * ax_w) - b * (u2 + w2)) * cos_t
            + (c * ax_u - a * ax_w) * lsqrt * sin_t
        ) / l2

        m31 = (ax_u * ax_w * (1 - cos_t) - ax_v * lsqrt * sin_t) / l2
        m32 = (ax_v * ax_w * (1 - cos_t) + ax_u * lsqrt * sin_t) / l2
        m33 = (w2 + (u2 + v2) * cos_t) / l2
        m34 = (
            c * (u2 + v2)
            - ax_w * (a * ax_u + b * ax_v)
            + (ax_w * (a * ax_u + b * ax_v) - c * (u2 + v2)) * cos_t
            + (a * ax_v - b * ax_u) * lsqrt * sin_t
        ) / l2

        return SymmOp(
            np.array(
                [
                    [m11, m12, m13, m14],
                    [m21, m22, m23, m24],
                    [m31, m32, m33, m34],
                    [0, 0, 0, 1],
                ]
            )
        )

    @staticmethod
    def reflection(normal: ArrayLike, origin: ArrayLike = (0, 0, 0)) -> SymmOp:
        """Get reflection symmetry operation.

        Args:
            normal (3x1 array): Vector of the normal to the plane of
                reflection.
            origin (3x1 array): A point in which the mirror plane passes
                through.

        Returns:
            SymmOp for the reflection about the plane
        """
        # Normalize the normal vector first.
        u: float
        v: float
        w: float
        u, v, w = np.array(normal, dtype=float) / np.linalg.norm(normal)

        translation = np.eye(4)
        translation[:3, 3] = -np.asarray(origin)

        xx = 1 - 2 * u**2
        yy = 1 - 2 * v**2
        zz = 1 - 2 * w**2
        xy = -2 * u * v
        xz = -2 * u * w
        yz = -2 * v * w
        mirror_mat = np.array([[xx, xy, xz, 0], [xy, yy, yz, 0], [xz, yz, zz, 0], [0, 0, 0, 1]])

        if np.linalg.norm(origin) > 1e-6:
            mirror_mat = np.dot(np.linalg.inv(translation), np.dot(mirror_mat, translation))
        return SymmOp(mirror_mat)

    @staticmethod
    def inversion(origin: ArrayLike = (0, 0, 0)) -> SymmOp:
        """Inversion symmetry operation about axis.

        Args:
            origin (3x1 array): Origin of the inversion operation. Defaults
                to [0, 0, 0].

        Returns:
            SymmOp representing an inversion operation about the origin.
        """
        mat = -np.eye(4)
        mat[3, 3] = 1
        mat[:3, 3] = 2 * np.asarray(origin)
        return SymmOp(mat)

    @staticmethod
    def rotoreflection(axis: Sequence[float], angle: float, origin: Sequence[float] = (0, 0, 0)) -> SymmOp:
        """Get a roto-reflection symmetry operation.

        Args:
            axis (3x1 array): Axis of rotation / mirror normal
            angle (float): Angle in degrees
            origin (3x1 array): Point left invariant by roto-reflection.
                Defaults to (0, 0, 0).

        Returns:
            Roto-reflection operation
        """
        rot = SymmOp.from_origin_axis_angle(origin, axis, angle)
        refl = SymmOp.reflection(axis, origin)
        matrix = np.dot(rot.affine_matrix, refl.affine_matrix)
        return SymmOp(matrix)

    def as_dict(self) -> dict[str, Any]:
        """MSONable dict."""
        return {
            "@module": type(self).__module__,
            "@class": type(self).__name__,
            "matrix": self.affine_matrix.tolist(),
            "tolerance": self.tol,
        }

    def as_xyz_str(self) -> str:
        """Get a string of the form 'x, y, z', '-x, -y, z', '-y+1/2, x+1/2, z+1/2', etc.
        Only works for integer rotation matrices.
        """
        # Check for invalid rotation matrix
        if not np.allclose(self.rotation_matrix, np.round(self.rotation_matrix)):
            warnings.warn("Rotation matrix should be integer", stacklevel=2)

        return transformation_to_string(
            self.rotation_matrix,
            translation_vec=self.translation_vector,
            delim=", ",
        )

    @classmethod
    def from_xyz_str(cls, xyz_str: str) -> Self:
        """
        Args:
            xyz_str (str): "x, y, z", "-x, -y, z", "-2y+1/2, 3x+1/2, z-y+1/2", etc.

        Returns:
            SymmOp
        """
        rot_matrix: NDArray = np.zeros((3, 3))
        trans: NDArray = np.zeros(3)
        tokens: list[str] = xyz_str.strip().replace(" ", "").lower().split(",")
        re_rot = re.compile(r"([+-]?)([\d\.]*)/?([\d\.]*)([x-z])")
        re_trans = re.compile(r"([+-]?)([\d\.]+)/?([\d\.]*)(?![x-z])")

        for idx, tok in enumerate(tokens):
            # Build the rotation matrix
            for match in re_rot.finditer(tok):
                factor = -1.0 if match[1] == "-" else 1.0
                if match[2] != "":
                    factor *= float(match[2]) / float(match[3]) if match[3] != "" else float(match[2])
                j = ord(match[4]) - 120
                rot_matrix[idx, j] = factor

            # Build the translation vector
            for match in re_trans.finditer(tok):
                factor = -1 if match[1] == "-" else 1
                num = float(match[2]) / float(match[3]) if match[3] != "" else float(match[2])
                trans[idx] = num * factor

        return cls.from_rotation_and_translation(rot_matrix, trans)

    @classmethod
    def from_dict(cls, dct: dict) -> Self:
        """
        Args:
            dct: dict.

        Returns:
            SymmOp from dict representation.
        """
        return cls(dct["matrix"], dct["tolerance"])


class MagSymmOp(SymmOp):
    """Thin wrapper around SymmOp to extend it to support magnetic symmetry by including a time
    reversal operator. Magnetic symmetry is similar to conventional crystal symmetry, except
    symmetry is reduced by the addition of a time reversal operator which acts on an atom's magnetic
    moment.
    """

    def __init__(
        self,
        affine_transformation_matrix: ArrayLike,
        time_reversal: Literal[-1, 1],
        tol: float = 0.01,
    ) -> None:
        """Initialize the MagSymmOp from a 4x4 affine transformation matrix and time reversal
        operator. In general, this constructor should not be used unless you are transferring
        rotations. Use the static constructors instead to generate a SymmOp from proper rotations
        and translation.

        Args:
            affine_transformation_matrix (4x4 array): Representing an
                affine transformation.
            time_reversal (int): 1 or -1
            tol (float): Tolerance for determining if matrices are equal.
        """
        super().__init__(affine_transformation_matrix, tol=tol)
        if time_reversal not in {-1, 1}:
            raise RuntimeError(f"Invalid {time_reversal=}, must be 1 or -1")

        self.time_reversal = time_reversal

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return np.allclose(self.affine_matrix, other.affine_matrix, atol=self.tol) and (
            self.time_reversal == other.time_reversal
        )

    def __str__(self) -> str:
        return self.as_xyzt_str()

    def __repr__(self) -> str:
        return "\n".join(
            [
                "Rot:",
                str(self.affine_matrix[:3][:, :3]),
                "tau",
                str(self.affine_matrix[:3][:, 3]),
                "Time reversal:",
                str(self.time_reversal),
            ]
        )

    def __hash__(self) -> int:
        """Useful for obtaining a set of unique MagSymmOps."""
        hashable_value = (*tuple(self.affine_matrix.flatten()), self.time_reversal)
        return hash(hashable_value)

    @due.dcite(
        Doi("10.1051/epjconf/20122200010"),
        description="Symmetry and magnetic structures",
    )
    def operate_magmom(self, magmom: Magmom) -> Magmom:
        """Apply time reversal operator on the magnetic moment. Note that
        magnetic moments transform as axial vectors, not polar vectors.

        See 'Symmetry and magnetic structures', Rodríguez-Carvajal and
        Bourée for a good discussion. DOI: 10.1051/epjconf/20122200010

        Args:
            magmom: Magnetic moment as electronic_structure.core.Magmom
            class or as list or np array-like

        Returns:
            Magnetic moment after operator applied as Magmom class
        """
        # Type casting to handle lists as input
        magmom = Magmom(magmom)

        transformed_moment = (
            self.apply_rotation_only(magmom.global_moment) * np.linalg.det(self.rotation_matrix) * self.time_reversal
        )

        # Retain input spin axis if different from default
        return Magmom.from_global_moment_and_saxis(transformed_moment, magmom.saxis)

    @classmethod
    def from_symmop(cls, symmop: SymmOp, time_reversal: Literal[-1, 1]) -> Self:
        """Initialize a MagSymmOp from a SymmOp and time reversal operator.

        Args:
            symmop (SymmOp): SymmOp
            time_reversal (int): Time reversal operator, +1 or -1.

        Returns:
            MagSymmOp object
        """
        return cls(symmop.affine_matrix, time_reversal, symmop.tol)

    @staticmethod
    def from_rotation_and_translation_and_time_reversal(
        rotation_matrix: ArrayLike = ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        translation_vec: ArrayLike = (0, 0, 0),
        time_reversal: Literal[-1, 1] = 1,
        tol: float = 0.1,
    ) -> MagSymmOp:
        """Create a symmetry operation from a rotation matrix, translation
        vector and time reversal operator.

        Args:
            rotation_matrix (3x3 array): Rotation matrix.
            translation_vec (3x1 array): Translation vector.
            time_reversal (int): Time reversal operator, +1 or -1.
            tol (float): Tolerance to determine if rotation matrix is valid.

        Returns:
            MagSymmOp object
        """
        symm_op = SymmOp.from_rotation_and_translation(
            rotation_matrix=rotation_matrix, translation_vec=translation_vec, tol=tol
        )
        return MagSymmOp.from_symmop(symm_op, time_reversal)

    @classmethod
    def from_xyzt_str(cls, xyzt_str: str) -> Self:
        """
        Args:
            xyzt_str (str): of the form 'x, y, z, +1', '-x, -y, z, -1',
                '-2y+1/2, 3x+1/2, z-y+1/2, +1', etc.

        Returns:
            MagSymmOp object
        """
        symm_op = SymmOp.from_xyz_str(xyzt_str.rsplit(",", 1)[0])
        try:
            time_reversal = int(xyzt_str.rsplit(",", 1)[1])
        except Exception:
            raise RuntimeError("Time reversal operator could not be parsed.")

        if time_reversal in {-1, 1}:
            return cls.from_symmop(symm_op, cast("Literal[-1, 1]", time_reversal))

        raise RuntimeError("Time reversal should be -1 or 1.")

    def as_xyzt_str(self) -> str:
        """Get a string of the form 'x, y, z, +1', '-x, -y, z, -1',
        '-y+1/2, x+1/2, z+1/2, +1', etc. Only works for integer rotation matrices.
        """
        xyzt_string = super().as_xyz_str()
        return f"{xyzt_string}, {self.time_reversal:+}"

    def as_dict(self) -> dict[str, Any]:
        """MSONable dict."""
        return {
            "@module": type(self).__module__,
            "@class": type(self).__name__,
            "matrix": self.affine_matrix.tolist(),
            "tolerance": self.tol,
            "time_reversal": self.time_reversal,
        }

    @classmethod
    def from_dict(cls, dct: dict) -> Self:
        """
        Args:
            dct: dict.

        Returns:
            MagneticSymmOp from dict representation.
        """
        return cls(dct["matrix"], tol=dct["tolerance"], time_reversal=dct["time_reversal"])
