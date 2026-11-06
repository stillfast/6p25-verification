#!/usr/bin/env python
"""Plot the E(V) curves of the cutoff-convergence runs, all pseudopotentials together.

This is the diagnostic view used to judge a candidate pseudopotential **before** the
production EOS is run: for one system it shows the seven EOS points of every
pseudopotential at the same cutoff, referenced to the energy at the middle volume (the
all-electron equilibrium volume), so that all curves pass through zero there and can be
compared directly, together with the all-electron Birch-Murnaghan curve.

A healthy pseudopotential gives a smooth parabola whose minimum sits near the reference
volume and whose shape does not change when the cutoff is increased. A defective one
gives a monotonic curve, a minimum outside the scanned window, or an energy that moves by
hundreds of meV from one volume to the next.

Usage
-----

    python 4-analyze/plot_convergence_curves.py                      # X/BCC and XO2 at 200 Ry
    python 4-analyze/plot_convergence_curves.py --cutoff 100 --ascii
    python 4-analyze/plot_convergence_curves.py --systems X/BCC
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import util  # noqa: E402
from common.quantities_for_comparison import birch_murnaghan  # noqa: E402

COLORS = {'nc6': '#1f77b4', 'opium': '#1f77b4', 'v13': '#1f77b4', 'sr': '#1f77b4', 'nc': '#d62728',
          'fr': '#2ca02c', 'reference': '#555555'}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=list(config.PSEUDOS), choices=sorted(config.PSEUDOS))
    parser.add_argument('--systems', nargs='+',
                        default=list(getattr(config, 'VERIFICATION_CONFIGURATIONS', ['X/BCC', 'XO2'])))
    parser.add_argument('--cutoff', type=float, default=200.0)
    parser.add_argument('--output', type=Path, default=config.OUTPUTS_DIR / 'plots-convergence')
    parser.add_argument('--ascii', action='store_true', help='Also print the curves as a text table.')
    return parser.parse_args()


def atoms_in_cell(pseudo_key: str, configuration: str):
    """Number of atoms of the structure used by the convergence scan."""
    from aiida import orm

    try:
        group = orm.load_group(util.convergence_structures_group_label(util.set_name(pseudo_key)))
    except Exception:  # noqa: BLE001
        return None
    for node in group.nodes:
        if node.base.extras.get('configuration') == configuration:
            return len(node.sites)
    return None


def eos_points(pseudo_key: str, configuration: str, cutoff: float):
    """Return ``[(cell volume, total energy in Ry)]`` of the convergence run."""
    from aiida import orm
    from aiida.common import LinkType
    from aiida.orm import CalcJobNode

    name = util.set_name(pseudo_key)
    tag = f'ecut-{cutoff:g}-dual-4'
    for (group,) in orm.QueryBuilder().append(
        orm.Group, filters={'label': {'like': f'%{name}/convergence/%'}}
    ).iterall():
        if group.label.rsplit('/', 1)[-1] != tag:
            continue
        for eos in group.nodes:
            if eos.inputs.structure.base.extras.get('configuration') != configuration:
                continue
            points = []
            for t in eos.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
                for inner in t.node.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
                    for base in inner.node.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
                        for cc in base.node.base.links.get_outgoing(link_type=LinkType.CALL_CALC).all():
                            c = cc.node
                            if not isinstance(c, CalcJobNode) or not c.is_finished_ok:
                                continue
                            if c.inputs.parameters.get_dict()['SYSTEM']['ecutwfc'] != cutoff:
                                continue
                            # the plugin-default `init_relax` SCF of the same workchain runs at
                            # ecutwfc = 100 Ry too: keep only the calculations that use the
                            # pseudopotential under test
                            pseudo_files = {t2.node.filename for t2 in c.base.links.get_incoming().all()
                                            if t2.link_label.startswith('pseudos')}
                            if Path(config.PSEUDOS[pseudo_key]['upf']).name not in pseudo_files:
                                continue
                            try:
                                energy = c.outputs.output_parameters.get_dict()['energy']
                            except Exception:  # noqa: BLE001
                                continue
                            points.append((c.inputs.structure.get_cell_volume(), energy))
            if points:
                return sorted(points)
    return []


def reference_fit(configuration: str):
    """``(BM fit, atoms in cell)`` of the all-electron average, or ``(None, None)``."""
    key = f'U-{configuration}'
    for filename in config.REFERENCE_FILES.values():
        path = config.REFERENCE_DATA_DIR / filename
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        fit = payload.get('BM_fit_data', {}).get(key)
        if fit:
            return fit, payload.get('num_atoms_in_sim_cell', {}).get(key)
    return None, None


def ascii_table(configuration, curves, natoms):
    """Text rendering: ΔE per atom relative to the energy at the middle volume."""
    volumes = [v / natoms for v, _ in curves[0][1]]
    middle = len(volumes) // 2
    out = [f'  {configuration} — V per atom [Å³]: ' + ' '.join(f'{v:8.3f}' for v in volumes),
           f'  {"":<6}' + ' ' * 20 + 'ΔE per atom relative to the middle volume [meV]']
    for key, points in curves:
        anchor = [e for _, e in points][middle]
        values = [(e - anchor) * 1000 / natoms for _, e in points]
        out.append(f'  {config.PSEUDOS[key]["tag"]:<6}' + ' ' * 20 + ' '.join(f'{v:8.2f}' for v in values))
    return '\n'.join(out)


def main() -> int:
    args = parse_args()
    util.load_profile()

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    args.output.mkdir(parents=True, exist_ok=True)
    written = []

    for configuration in args.systems:
        curves = []
        for pseudo_key in args.pseudos:
            points = eos_points(pseudo_key, configuration, args.cutoff)
            if points:
                curves.append((pseudo_key, points))
        if not curves:
            print(f'  {configuration}: no EOS points at {args.cutoff:g} Ry')
            continue

        natoms = atoms_in_cell(curves[0][0], configuration) or 1
        volumes = np.array([v / natoms for v, _ in curves[0][1]])
        middle = len(volumes) // 2

        fig, ax = plt.subplots(figsize=(7.4, 5.0))
        for pseudo_key, points in curves:
            v = np.array([value / natoms for value, _ in points])
            e = np.array([value / natoms for _, value in points])
            ax.plot(v, (e - e[middle]) * 1000.0, 'o-', color=COLORS.get(pseudo_key), lw=1.6, ms=5,
                    label=config.PSEUDOS[pseudo_key]['upf'])

        fit, ref_natoms = reference_fit(configuration)
        if fit:
            v0 = fit['min_volume'] / ref_natoms
            grid = np.linspace(volumes.min(), volumes.max(), 200)
            curve = birch_murnaghan(grid, 0.0, v0, fit['bulk_modulus_ev_ang3'], fit['bulk_deriv'])
            anchor = np.interp(volumes[middle], grid, curve)
            ax.plot(grid, (curve - anchor) * 1000.0, ':', color=COLORS['reference'], lw=1.8,
                    label='all-electron average (ACWF)')
            ax.axvline(v0, color=COLORS['reference'], lw=0.8, alpha=0.35)

        ax.axhline(0.0, color='black', lw=0.6, alpha=0.4)
        ax.set_xlabel('volume per atom  [Å³]')
        ax.set_ylabel('E − E(middle volume)   [meV per atom]')
        ax.set_title(f'{configuration} — convergence runs, ecutwfc = {args.cutoff:g} Ry, '
                     f'{natoms} atoms')
        ax.legend(fontsize=8)
        ax.grid(alpha=0.25)
        fig.tight_layout()
        path = args.output / f'EOS-{configuration.replace("/", "_")}-{args.cutoff:g}Ry.png'
        fig.savefig(path, dpi=150)
        plt.close(fig)
        written.append(path)
        print(f'  wrote {path}')

        if args.ascii:
            print(ascii_table(configuration, curves, natoms))
            print()

    print(f'{len(written)} plot(s) in {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
