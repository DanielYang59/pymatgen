"""Support for Abinit input variables."""

from __future__ import annotations

import collections
import collections.abc
import string
from collections.abc import Sequence

import numpy as np

_SPECIAL_DATASET_INDICES = (":", "+", "?")
_DATASET_INDICES = "".join([*string.digits, *_SPECIAL_DATASET_INDICES])
_UNITS = {
    "bohr": 1.0,
    "angstrom": 1.8897261328856432,
    "hartree": 1.0,
    "Ha": 1.0,
    "eV": 0.03674932539796232,
}


class InputVariable:
    """An Abinit input variable."""

    def __init__(self, name: str, value, units: str = "", valperline: int = 3) -> None:
        """
        Args:
            name: Name of the variable.
            value: Value of the variable.
            units: String specifying one of the units supported by Abinit. Default: atomic units.
            valperline: Number of items printed per line.
        """
        self._name = name
        self.value = value
        self._units = units

        self.valperline = valperline  # Maximum number of values per line.
        if name == "bdgw":
            self.valperline = 2

        if isinstance(self.value, Sequence) and isinstance(self.value[-1], str) and self.value[-1] in _UNITS:
            self.value = list(self.value)
            self._units = self.value.pop(-1)

    def get_value(self):
        """Return the value."""
        if self.units:
            return [*self.value, self.units]
        return self.value

    @property
    def name(self):
        """Name of the variable."""
        return self._name

    @property
    def basename(self):
        """The name trimmed of any dataset index."""
        basename = self.name
        return basename.rstrip(_DATASET_INDICES)

    @property
    def dataset(self):
        """The dataset index in string form."""
        return self.name.split(self.basename)[-1]

    @property
    def units(self):
        """The units."""
        return self._units

    def __str__(self):
        """Declaration of the variable in the input file."""
        value = self.value
        if value is None or not str(value):
            return ""

        var = self.name
        line = " " + var

        # By default, do not impose a number of decimal points
        float_decimal = 0

        # For some inputs, enforce number of decimal points...
        if any(inp in var for inp in ("xred", "xcart", "rprim", "qpt", "kpt")):
            float_decimal = 16

        # ...but not for those
        if any(inp in var for inp in ("ngkpt", "kptrlatt", "ngqpt", "ng2qpt")):
            float_decimal = 0

        if isinstance(value, np.ndarray):
            value = list(value.flatten())

        # values in lists
        if isinstance(value, list | tuple):
            # Reshape a list of lists into a single list
            if all(isinstance(v, list | tuple) for v in value):
                line += self.format_list2d(value, float_decimal)

            else:
                line += self.format_list(value, float_decimal)

        # scalar values
        else:
            line += f" {value}"

        # Add units
        if self.units:
            line += f" {self.units}"

        return line

    @staticmethod
    def format_scalar(val, float_decimal=0):
        """Format a single numerical value into a string
        with the appropriate number of decimal.
        """
        str_val = str(val)
        if str_val.lstrip("-").lstrip("+").isdigit() and float_decimal == 0:
            return str_val

        try:
            fval = float(val)
        except Exception:
            return str_val

        if fval == 0 or (1e-3 < abs(fval) < 1e4):
            form = "f"
            add_len = 5
        else:
            form = "e"
            add_len = 8

        n_dec = max(len(str(fval - int(fval))) - 2, float_decimal)
        n_dec = min(n_dec, 10)

        str_val = f"{fval:>{n_dec + add_len}.{n_dec}{form}}"

        return str_val.replace("e", "d")

    @staticmethod
    def format_list2d(values, float_decimal=0):
        """Format a list of lists."""
        flattened_list = flatten(values)

        # Determine the representation
        if all(isinstance(v, int) for v in flattened_list):
            type_all = int
        else:
            try:
                for v in flattened_list:
                    float(v)
                type_all = float
            except Exception:
                type_all = str

        # Determine the format
        width = max(len(str(s)) for s in flattened_list)
        if type_all is int:
            fmt_spec = f">{width}d"
        elif type_all is str:
            fmt_spec = f">{width}"
        else:
            # Number of decimal
            max_dec = max(len(str(f - int(f))) - 2 for f in flattened_list)
            n_dec = min(max(max_dec, float_decimal), 10)

            if all(f == 0 or (abs(f) > 1e-3 and abs(f) < 1e4) for f in flattened_list):
                fmt_spec = f">{n_dec + 5}.{n_dec}f"
            else:
                fmt_spec = f">{n_dec + 8}.{n_dec}e"

        line = "\n"
        for lst in values:
            for val in lst:
                line += f" {val:{ {fmt_spec} }}"
            line += "\n"

        return line.rstrip("\n")

    def format_list(self, values, float_decimal=0):
        """Format a list of values into a string.
        The result might be spread among several lines.
        """
        line = ""

        # Format the line declaring the value
        for i, val in enumerate(values, start=1):
            line += f" {self.format_scalar(val, float_decimal)}"
            if self.valperline is not None and i % self.valperline == 0:
                line += "\n"

        # Add a carriage return in case of several lines
        if "\n" in line.rstrip("\n"):
            line = "\n" + line

        return line.rstrip("\n")


def flatten(iterable):
    """Make an iterable flat, i.e. a 1d iterable object."""
    iterator = iter(iterable)
    array, stack = collections.deque(), collections.deque()
    while True:
        try:
            value = next(iterator)
        except StopIteration:
            if not stack:
                return tuple(array)
            iterator = stack.pop()
        else:
            if not isinstance(value, str) and isinstance(value, collections.abc.Iterable):
                stack.append(iterator)
                iterator = iter(value)
            else:
                array.append(value)
