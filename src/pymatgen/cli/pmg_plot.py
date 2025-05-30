#!/usr/bin/env python

"""Implementation for `pmg plot` CLI."""

from __future__ import annotations

import matplotlib.pyplot as plt

from pymatgen.analysis.diffraction.xrd import XRDCalculator
from pymatgen.core.structure import Structure
from pymatgen.electronic_structure.plotter import DosPlotter
from pymatgen.io.vasp import Chgcar, Vasprun
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.util.plotting import pretty_plot


def get_dos_plot(args) -> plt.Axes:
    """Plot DOS from vasprun.xml file.

    Args:
        args (dict): Args from argparse.
    """
    vasp_run = Vasprun(args.dos_file)
    dos = vasp_run.complete_dos

    all_dos = {}
    all_dos["Total"] = dos

    structure = vasp_run.final_structure

    if args.site:
        for idx, site in enumerate(structure):
            all_dos[f"Site {idx} {site.specie.symbol}"] = dos.get_site_dos(site)  # type:ignore[assignment]

    if args.element:
        syms = [tok.strip() for tok in args.element[0].split(",")]
        all_dos = {}
        for el, el_dos in dos.get_element_dos().items():
            if el.symbol in syms:
                all_dos[el] = el_dos  # type:ignore[assignment,index]
    if args.orbital:
        all_dos = dos.get_spd_dos()  # type:ignore[assignment]

    plotter = DosPlotter()
    plotter.add_dos_dict(all_dos)
    return plotter.get_plot()


def get_chgint_plot(args, ax: plt.Axes | None = None) -> plt.Axes:
    """Plot integrated charge from CHGCAR file.

    Args:
        args (dict): args from argparse.
        ax (plt.Axes): Matplotlib Axes object for plotting.

    Returns:
        plt.Axes: Matplotlib Axes object.
    """
    chgcar = Chgcar.from_file(args.chgcar_file)
    struct = chgcar.structure

    if args.inds:
        atom_ind = [int(i) for i in args.inds[0].split(",")]
    else:
        finder = SpacegroupAnalyzer(struct, symprec=0.1)
        sites = [sites[0] for sites in finder.get_symmetrized_structure().equivalent_sites]
        atom_ind = [struct.index(site) for site in sites]

    ax = ax or pretty_plot(12, 8)
    for idx in atom_ind:
        d = chgcar.get_integrated_diff(idx, args.radius, 30)
        ax.plot(d[:, 0], d[:, 1], label=f"Atom {idx} - {struct[idx].species_string}")
    ax.legend(loc="upper left")
    ax.set_xlabel("Radius (A)")
    ax.set_ylabel("Integrated charge (e)")
    plt.tight_layout()
    return ax


def get_xrd_plot(args) -> plt.Axes:
    """Plot XRD from structure.

    Args:
        args (dict): Args from argparse
    """
    struct = Structure.from_file(args.xrd_structure_file)
    calculator = XRDCalculator()
    return calculator.get_plot(struct)


def plot(args) -> None:
    """Master control function calling other plot functions based on args.

    Args:
        args (dict): Args from argparse.
    """
    if args.chgcar_file:
        fig: plt.Figure | plt.SubFigure | None = get_chgint_plot(args).figure
    elif args.xrd_structure_file:
        fig = get_xrd_plot(args).figure
    elif args.dos_file:
        fig = get_dos_plot(args).figure
    else:
        fig = None

    if fig is not None:
        if args.out_file:
            fig.savefig(args.out_file)
        else:
            fig.show()
