"""Utility functions for assisting with CP2K IO."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import numpy as np
from monty.io import zopen

if TYPE_CHECKING:
    from pymatgen.core import Molecule, Structure


def postprocessor(data: str) -> str | float | bool | None:
    """
    Helper function to post process the results of the pattern matching functions in Cp2kOutput
    and turn them to Python types.

    Args:
        data (str): The data to be post processed.

    Raises:
        ValueError: If the data cannot be parsed.

    Returns:
        str | float | bool | None: The post processed data.
    """
    data = data.strip().replace(" ", "_")  # remove leading/trailing whitespace, replace spaces with _

    if data.lower() in {"false", "no", "f"}:
        return False
    if data.lower() == "none":
        return None
    if data.lower() in {"true", "yes", "t"}:
        return True
    if re.match(r"^-?\d+$", data):
        try:
            return int(data)
        except ValueError as exc:
            raise ValueError(f"Error parsing {data!r} as int in CP2K file.") from exc
    if re.match(r"^[+\-]?(?=.)(?:0|[1-9]\d*)?(?:\.\d*)?(?:\d[eE][+\-]?\d+)?$", data):
        try:
            return float(data)
        except ValueError as exc:
            raise ValueError(f"Error parsing {data!r} as float in CP2K file.") from exc
    if re.match(r"\*+", data):
        return np.nan
    return data


def preprocessor(data: str, dir: str = ".") -> str:  # noqa: A002
    """
    CP2K contains internal preprocessor flags that are evaluated before execution. This helper
    function recognizes those preprocessor flags and replaces them with an equivalent CP2K input
    (this way everything is contained neatly in the CP2K input structure, even if the user preferred
    to use the flags.

    CP2K preprocessor flags (with arguments) are:

        @INCLUDE FILENAME: Insert the contents of FILENAME into the file at
            this location.
        @SET VAR VALUE: set a variable, VAR, to have the value, VALUE.
        $VAR or ${VAR}: replace these with the value of the variable, as set
            by the @SET flag.
        @IF/@ELIF: Not implemented yet.

    Args:
        data (str): CP2K input to preprocess
        dir (str, optional): Path for include files. Default is '.' (current directory).

    Returns:
        Preprocessed string
    """
    includes = re.findall(r"(@include.+)", data, re.IGNORECASE)
    for incl in includes:
        inc = incl.split()
        if len(inc) != 2:  # @include filename
            raise ValueError(f"length of inc should be 2, got {len(inc)}")
        inc = inc[1].strip("'")
        inc = inc.strip('"')
        with zopen(os.path.join(dir, inc), mode="rt", encoding="utf-8") as file:
            data = re.sub(rf"{incl}", file.read(), data)
    variable_sets = re.findall(r"(@SET.+)", data, re.IGNORECASE)
    for match in variable_sets:
        v = match.split()
        if len(v) != 3:  # @SET VAR value
            raise ValueError(f"length of v should be 3, got {len(v)}")
        var, value = v[1:]
        data = re.sub(rf"{match}", "", data)
        data = re.sub(rf"\${{?{var}}}?", value, data)

    c1 = re.findall(r"@IF", data, re.IGNORECASE)
    c2 = re.findall(r"@ELIF", data, re.IGNORECASE)
    if len(c1) > 0 or len(c2) > 0:
        raise NotImplementedError("This CP2K input processor does not currently support conditional blocks.")
    return data


def chunk(string: str):
    """Chunk the string from a CP2K basis or potential file."""
    lines = iter(line for line in (line.strip() for line in string.split("\n")) if line and not line.startswith("#"))
    chunks: list = []
    for line in lines:
        if line.split()[0].isalpha():
            chunks.append([])
        chunks[-1].append(line)
    return ["\n".join(c) for c in chunks]


def natural_keys(text: str):
    """
    Sort text by numbers coming after an underscore with natural number
    convention,
    Ex: [file_1, file_12, file_2] becomes [file_1, file_2, file_12].
    """

    def atoi(t):
        return int(t) if t.isdigit() else t

    return [atoi(c) for c in re.split(r"_(\d+)", text)]


def get_unique_site_indices(struct: Structure | Molecule):
    """Get unique site indices for a structure according to site properties. Whatever site-property
    has the most unique values is used for indexing.

    For example, if you have magnetic CoO with half Co atoms having a positive moment, and the
    other half having a negative moment. Then this function will create a dict of sites for
    Co_1, Co_2, O. This function also deals with "Species" properties like oxi_state and spin by
    pushing them to site properties.

    This creates unique sites, based on site properties, but does not have anything to do with
    turning those site properties into CP2K input parameters. This will only be done for properties
    which can be turned into CP2K input parameters, which are stored in parsable_site_properties.
    """
    spins = []
    oxi_states = []
    parsable_site_properties = {
        "magmom",
        "oxi_state",
        "spin",
        "u_minus_j",
        "basis",
        "potential",
        "ghost",
        "aux_basis",
    }

    for site in struct:
        for sp in site.species:
            oxi_states.append(getattr(sp, "oxi_state", 0))
            spins.append(getattr(sp, "_properties", {}).get("spin", 0))

    struct.add_site_property("oxi_state", oxi_states)
    struct.add_site_property("spin", spins)
    struct.remove_oxidation_states()
    items = [
        (
            site.species_string,
            *[struct.site_properties[k][idx] for k in struct.site_properties if k.lower() in parsable_site_properties],
        )
        for idx, site in enumerate(struct)
    ]
    unique_items = list(set(items))
    _sites: dict[tuple, list] = {u: [] for u in unique_items}
    for i, itm in enumerate(items):
        _sites[itm].append(i)
    sites = {}
    nums = dict.fromkeys(struct.symbol_set, 1)
    for site, val in _sites.items():
        sites[f"{site[0]}_{nums[site[0]]}"] = val
        nums[site[0]] += 1

    return sites


def get_truncated_coulomb_cutoff(inp_struct: Structure):
    """Get the truncated Coulomb cutoff for a given structure."""
    m = inp_struct.lattice.matrix
    m = (abs(m) > 1e-5) * m
    a, b, c = m[0], m[1], m[2]
    x = abs(np.dot(a, np.cross(b, c)) / np.linalg.norm(np.cross(b, c)))
    y = abs(np.dot(b, np.cross(a, c)) / np.linalg.norm(np.cross(a, c)))
    z = abs(np.dot(c, np.cross(a, b)) / np.linalg.norm(np.cross(a, b)))
    return np.floor(100 * min([x, y, z]) / 2) / 100
