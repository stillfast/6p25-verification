#!/usr/bin/env python
"""Plot the energy-volume curves of both pseudopotentials against the reference.

For every verification system one PNG is produced that shows

* the computed EOS points and their Birch-Murnaghan fit for each candidate
  pseudopotential,
* the all-electron reference EOS of the ACWF paper (dotted),
* optionally, with ``--reference-codes``, the published ACWF runs of other codes
  (VASP, CASTEP, ...) as points + fit, and
* the equilibrium volume, bulk modulus and ``delta`` of each curve.

Both the energy and the volume are divided by the **number of atoms of the
simulation cell** (so ``X/FCC`` with four atoms is divided by four, ``XO2`` with
twelve atoms by twelve, ...), which makes the curves of different systems
directly comparable, and matches the per-atom definition of the ``delta`` metric.

Energies are additionally **shifted to the equilibrium energy of each curve**
(``E - E0``) and expressed in meV, so that curves obtained with different
pseudopotentials — whose total-energy zeros differ by hundreds of Ry — can be
overlaid and compared directly.

Usage
-----

    python 4-analyze/plot_ev_curves.py
    python 4-analyze/plot_ev_curves.py --pseudos sr --configurations X/BCC XO2
    python 4-analyze/plot_ev_curves.py --include-spin-orbit

    # one pseudopotential against the published plane-wave codes
    python 4-analyze/plot_ev_curves.py --pseudos v13 --reference-codes vasp castep \
        --output 4-analyze/outputs/plots-v13-refs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import eosdata  # noqa: E402
from common import util  # noqa: E402
from common.quantities_for_comparison import birch_murnaghan  # noqa: E402

COLORS = {
    # candidate pseudopotentials of this project (one color per key, so that the
    # data points and the fitted line of a curve never end up in two colors)
    'nc6': '#1f77b4',
    '6p25': '#1f77b4',
    'opium': '#1f77b4',
    'v13': '#1f77b4',
    'best': '#e377c2',
    'nc': '#bcbd22',
    'sr': '#1f77b4',
    'fr': '#d62728',
    'rc1': '#2ca02c',
    'rc2': '#9467bd',
    # reference curves
    'reference': '#555555',
    'qe-sssp': '#ff7f0e',
    'vasp': '#17becf',
    'fleur': '#7f7f7f',
    'wien2k': '#393b79',
    'castep': '#8c564b',
}

#: Fallback for a key that has no entry in :data:`COLORS` (a new pseudopotential in
#: ``config.PSEUDOS``): a single fixed color, so the curve stays one color, plus a
#: printed warning that the palette needs an entry.
FALLBACK_COLOR = '#000000'


def color_for(key: str, warned: set) -> str:
    if key in COLORS:
        return COLORS[key]
    if key not in warned:
        warned.add(key)
        print(f"  WARNING: no color defined for '{key}' — using {FALLBACK_COLOR}. "
              f"Add it to COLORS in this script.")
    return FALLBACK_COLOR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=list(config.PSEUDOS), choices=sorted(config.PSEUDOS))
    parser.add_argument('--configurations', nargs='+', default=None)
    parser.add_argument('--output', type=Path, default=config.OUTPUTS_DIR / 'plots')
    parser.add_argument('--include-spin-orbit', action='store_true')
    parser.add_argument('--reference-codes', nargs='+', default=None,
                        choices=sorted(config.REFERENCE_CODES),
                        help='Also draw the published ACWF runs of these codes '
                             f'({", ".join(sorted(config.REFERENCE_CODES))}) as points + BM fit. '
                             'Their Delta is measured against the same all-electron average as ours.')
    parser.add_argument('--no-ae-average', action='store_true',
                        help='Do not draw the all-electron average (only useful together with '
                             '--reference-codes).')
    parser.add_argument('--window', type=float, default=0.03,
                        help='Margin added around the computed volume range on the x axis '
                             '(default 0.03 = 3 %%).')
    parser.add_argument('--ascii', action='store_true',
                        help='Also print each curve as a text table — the plotted curves, '
                             'readable without an image viewer.')
    return parser.parse_args()


def pseudo_label(key: str, spin_orbit: bool = False) -> str:
    """``U.pbe-n-nc.UPF [V13]`` — file name plus tag of a candidate pseudopotential.

    The bare file name is not enough: four candidates are all called
    ``U.pbe-n-nc.UPF`` (and two of them even live in a folder called ``rc_best``), and
    their full paths are too long for a legend.  This is the same label as the one used
    by ``4-analyze/make_comparison_report.py``.
    """
    spec = config.PSEUDOS[key]
    tag = spec.get('tag') or ('SR' if spec['rel'] == 'scalar' else 'FR')
    if spin_orbit:
        tag += '+SOC'
    return f"{Path(spec['upf']).name} [{tag}]"


def load_results(name: str):
    path = config.OUTPUTS_DIR / f'results-{name}-{util.PLUGIN_NAME}.json'
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_references():
    """Return ``{canonical system key: (BM fit, atoms in the simulation cell)}``."""
    references = {}
    for filename in config.REFERENCE_FILES.values():
        path = config.REFERENCE_DATA_DIR / filename
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        for key, fit in payload.get('BM_fit_data', {}).items():
            if fit is None:
                continue
            references[key] = (fit, payload.get('num_atoms_in_sim_cell', {}).get(key))
    return references


def ascii_block(system_key, rows, volumes, reference):
    """The same seven-point curves as the PNG, as text (see `common.eosdata`)."""
    return eosdata.eos_ascii_block(system_key, rows, volumes, reference)


def load_reference_codes(code_keys):
    """Return ``{code key: (label, {canonical system key: entry})}`` for the requested codes.

    ``entry`` is ``{'fit': BM fit, 'natoms': atoms in the simulation cell, 'volumes':
    [...], 'energies': [...]}``, so a published code can be drawn exactly like one of
    our candidates.  The unaries and oxides files are merged under the canonical
    ``U-<configuration>`` keys used by :func:`load_references`.
    """
    codes = {}
    for key in code_keys or []:
        spec = config.REFERENCE_CODES[key]
        entries = {}
        for kind in ('unaries', 'oxides'):
            path = config.ACWF_REFERENCE_OUTPUTS_DIR / spec['filename'].format(kind=kind)
            if not path.exists():
                print(f"  WARNING: reference code '{key}': {path} not found — skipped.")
                entries = {}
                break
            payload = json.loads(path.read_text())
            eos_data = payload.get('eos_data', {})
            fits = payload.get('BM_fit_data', {})
            natoms = payload.get('num_atoms_in_sim_cell', {})
            for system_key, points in eos_data.items():
                if not points or fits.get(system_key) is None or not natoms.get(system_key):
                    continue
                entries[system_key] = {
                    'fit': fits[system_key],
                    'natoms': natoms[system_key],
                    'volumes': [point[0] for point in points],
                    'energies': [point[1] for point in points],
                }
        if entries:
            codes[key] = (spec['label'], entries)
    return codes


def delta_mev_per_atom(fit, natoms, reference_fit, reference_natoms):
    """``delta`` of one curve against the all-electron average, in meV per atom.

    Both fits are converted to volumes per **atom** before the call, and the metric is
    then already per atom: the per-formula-unit divisor is 1.  (Passing the number of
    atoms of the formula unit as well would divide a second time and understate every
    ``delta`` — the values printed here are the ones of ``metrics-*.md``.)
    """
    return eosdata.delta_per_atom(
        fit['min_volume'] / natoms, fit['bulk_modulus_ev_ang3'], fit['bulk_deriv'],
        reference_fit['min_volume'] / reference_natoms,
        reference_fit['bulk_modulus_ev_ang3'], reference_fit['bulk_deriv'],
        1,
    )


def main() -> int:
    args = parse_args()
    util.load_profile()

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    args.output.mkdir(parents=True, exist_ok=True)
    references = load_references() if not args.no_ae_average else {}
    reference_codes = load_reference_codes(args.reference_codes)
    warned_colors = set()

    sets = []
    for key in args.pseudos:
        sets.append((key, False))
        if args.include_spin_orbit and config.PSEUDOS[key]['rel'] == 'full':
            sets.append((key, True))

    data = {}
    for key, spin_orbit in sets:
        results = load_results(util.set_name(key, spin_orbit=spin_orbit))
        if results is None:
            print(f"  {util.set_name(key, spin_orbit=spin_orbit)}: no results file — skipped")
            continue
        data[(key, spin_orbit)] = results

    if not data:
        print('Nothing to plot. Run 4-analyze/get_results.py first.')
        return 1

    # One PNG per system holds the curves of every requested pseudo, so plotting a
    # subset silently replaces a richer PNG with a poorer one. Say so out loud.
    omitted = []
    for key in config.PSEUDOS:
        if key in args.pseudos:
            continue
        for spin_orbit in (False, True):
            if spin_orbit and config.PSEUDOS[key]['rel'] != 'full':
                continue
            name = util.set_name(key, spin_orbit=spin_orbit)
            if (config.OUTPUTS_DIR / f'results-{name}-quantum_espresso.json').exists():
                omitted.append(name)
    if omitted:
        if sorted(args.output.glob('EOS-*.png')):
            print('  note: these existing result sets are NOT in the plots below, so their PNGs will be '
                  'replaced by versions without them: ' + ', '.join(omitted))
        else:
            print('  note: these result sets exist but are NOT in the plots below: ' + ', '.join(omitted))

    systems = sorted(
        {system_key for results in data.values() for system_key in results.get('eos_data', {})},
        key=lambda key: (key.split('-', 1)[1] not in config.UNARY_CONFIGURATIONS, key),
    )
    if args.configurations:
        systems = [key for key in systems if key.split('-', 1)[1] in args.configurations]

    written = []
    for system_key in systems:
        configuration = system_key.split('-', 1)[1]
        canonical = f'U-{configuration}'

        reference = references.get(canonical)
        if reference is not None and not reference[1]:
            reference = None

        # Volume range covered by the computed EOS points (per atom).
        v_lo, v_hi = None, None
        for results in data.values():
            payload = results.get('eos_data', {}).get(system_key)
            natoms = results.get('num_atoms_in_sim_cell', {}).get(system_key)
            if not payload or not natoms:
                continue
            volumes = np.array(payload)[:, 0] / natoms
            v_lo = volumes.min() if v_lo is None else min(v_lo, volumes.min())
            v_hi = volumes.max() if v_hi is None else max(v_hi, volumes.max())

        if v_lo is None:
            continue
        # The published runs of the other codes explore the same ±6 % window, but their
        # structures differ in the last digits (up to 0.7 % for U-X/SC); widen the axis
        # by their points too, so that no curve that is drawn gets clipped at the edge.
        for _, code_systems in reference_codes.values():
            entry = code_systems.get(canonical)
            if entry is None:
                continue
            code_volumes = np.asarray(entry['volumes'], dtype=float) / entry['natoms']
            v_lo, v_hi = min(v_lo, code_volumes.min()), max(v_hi, code_volumes.max())

        margin = args.window * (v_hi - v_lo)
        x_lo, x_hi = v_lo - margin, v_hi + margin

        # More curves (and their two-line labels) need a wider canvas than two.
        wide = len(data) + len(reference_codes) >= 3
        fig, ax = plt.subplots(figsize=(9.2, 5.4) if wide else (7.2, 5.0))

        ascii_rows = []
        ascii_volumes = None
        plotted_y = []       # every drawn curve, to reserve space for the legend

        for (key, spin_orbit), results in sorted(data.items()):
            payload = results.get('eos_data', {}).get(system_key)
            fit = results.get('BM_fit_data', {}).get(system_key)
            natoms = results.get('num_atoms_in_sim_cell', {}).get(system_key)
            if not payload or not natoms:
                continue
            # A curve whose minimum sits outside the ±6 % window has no Birch-Murnaghan fit.
            # Draw it anyway: that shape *is* the finding, and dropping the row would hide the
            # very case the figure is needed for. Anchor it at its own lowest computed energy.
            no_fit = fit is None
            if no_fit:
                lowest = min(energy for _, energy in payload)
                fit = {'E0': lowest, 'min_volume': float('nan'),
                       'bulk_modulus_ev_ang3': float('nan'), 'bulk_deriv': float('nan')}

            arrays = np.array(payload)
            volumes = arrays[:, 0] / natoms            # per atom
            energies = arrays[:, 1] / natoms           # per atom
            e0 = fit['E0'] / natoms                    # equilibrium energy of this curve
            v0 = fit['min_volume'] / natoms            # equilibrium volume per atom

            color = color_for(key, warned_colors)
            style = '--' if spin_orbit else '-'
            label = pseudo_label(key, spin_orbit)
            if no_fit:
                label += '\n   NO minimum inside the ±6 % window'
            else:
                label += (f'\n   V₀ = {v0:.3f} Å³/atom,  '
                          f'B₀ = {fit["bulk_modulus_ev_ang3"] * 160.21766208:.0f} GPa')
            if reference is not None and not no_fit:
                delta = delta_mev_per_atom(fit, natoms, reference[0], reference[1])
                label += f',  Δ = {delta:.2f} meV/atom'

            # data points and fit, both shifted to the equilibrium energy of the curve
            ax.plot(volumes, (energies - e0) * 1000.0, 'o', color=color, ms=5)
            plotted_y.append((energies - e0) * 1000.0)
            if not no_fit:
                v_grid = np.linspace(volumes.min(), volumes.max(), 200)
                values = birch_murnaghan(v_grid, 0.0, v0, fit['bulk_modulus_ev_ang3'],
                                         fit['bulk_deriv']) * 1000.0
                ax.plot(v_grid, values, style, color=color, lw=1.8, label=label)
                plotted_y.append(values)
            else:
                ax.plot(volumes, (energies - e0) * 1000.0, style, color=color, lw=1.8, label=label)

            if ascii_volumes is None:
                ascii_volumes = volumes
            ascii_rows.append((
                config.PSEUDOS[key]['tag'] + ('/SOC' if spin_orbit else ''),
                (energies - e0) * 1000.0,
            ))

        # Published ACWF runs of other codes (VASP, CASTEP, ...): same treatment as our
        # own curves — points + Birch-Murnaghan fit, energies shifted to their own E0 —
        # so the figure answers "how do we compare with what was published" directly.
        for code_key, (code_label, code_systems) in reference_codes.items():
            entry = code_systems.get(canonical)
            if entry is None:
                continue
            code_fit = entry['fit']
            code_natoms = entry['natoms']
            code_volumes = np.asarray(entry['volumes'], dtype=float) / code_natoms
            code_energies = np.asarray(entry['energies'], dtype=float) / code_natoms
            code_e0 = code_fit['E0'] / code_natoms
            code_v0 = code_fit['min_volume'] / code_natoms

            color = color_for(code_key, warned_colors)
            label = (f'{code_label}  (published)\n'
                     f'   V₀ = {code_v0:.3f} Å³/atom,  '
                     f'B₀ = {code_fit["bulk_modulus_ev_ang3"] * 160.21766208:.0f} GPa')
            if reference is not None:
                delta = delta_mev_per_atom(code_fit, code_natoms, reference[0], reference[1])
                label += f',  Δ = {delta:.2f} meV/atom'

            ax.plot(code_volumes, (code_energies - code_e0) * 1000.0, 's', color=color, ms=4)
            v_grid = np.linspace(code_volumes.min(), code_volumes.max(), 200)
            code_values = birch_murnaghan(v_grid, 0.0, code_v0, code_fit['bulk_modulus_ev_ang3'],
                                          code_fit['bulk_deriv']) * 1000.0
            ax.plot(v_grid, code_values, '-', color=color, lw=1.3, alpha=0.85, label=label)
            plotted_y.append((code_energies - code_e0) * 1000.0)
            plotted_y.append(code_values)
            if ascii_volumes is None:
                ascii_volumes = code_volumes
                code_ascii = (code_energies - code_e0) * 1000.0
            else:
                # The text table has one shared volume grid (that of the first curve), so the
                # published curve is sampled on it like the all-electron reference below.
                code_ascii = birch_murnaghan(
                    ascii_volumes, 0.0, code_v0, code_fit['bulk_modulus_ev_ang3'],
                    code_fit['bulk_deriv']) * 1000.0
            ascii_rows.append((code_key.upper(), code_ascii))

        if reference is not None:
            fit, natoms = reference
            v0_ref = fit['min_volume'] / natoms
            v_grid = np.linspace(x_lo, x_hi, 200)
            ae_values = birch_murnaghan(
                v_grid, 0.0, v0_ref, fit['bulk_modulus_ev_ang3'], fit['bulk_deriv']) * 1000.0
            ax.plot(
                v_grid, ae_values, ':', color=COLORS['reference'], lw=1.8,
                label=f'all-electron average (ACWF)\n'
                      f'   V₀ = {v0_ref:.3f} Å³/atom,  B₀ = {fit["bulk_modulus_ev_ang3"] * 160.21766208:.0f} GPa',
            )
            plotted_y.append(ae_values)
            ax.axvline(v0_ref, color=COLORS['reference'], lw=0.8, alpha=0.35)

        ax.set_xlim(x_lo, x_hi)

        ax.axhline(0.0, color='black', lw=0.6, alpha=0.4)
        ax.set_xlabel('volume per atom  [Å³]')
        ax.set_ylabel('E − E₀(V₀)   [meV per atom]')
        ax.set_title(f'{system_key}   (7-point EOS, Birch-Murnaghan fit)')
        # Several curves each carry a two-line label, so a wide figure and a two-column
        # legend once there are three or more of them.
        curves_in_legend = len(data) + len(reference_codes) + (1 if reference is not None else 0)
        if curves_in_legend >= 4 and plotted_y:
            # Four or more two-line entries fill the top of the axes; the curve arms at the
            # left and right edges reach the top there, so reserve that band by hand
            # instead of letting the legend cover the curves.
            y_lo = min(float(np.min(values)) for values in plotted_y)
            y_hi = max(float(np.max(values)) for values in plotted_y)
            span = max(y_hi - y_lo, 1.0)
            ax.set_ylim(y_lo - 0.06 * span, y_hi + 0.42 * span)
        ax.legend(fontsize=8 if curves_in_legend <= 3 else 7,
                  loc='upper center', ncol=1 if curves_in_legend <= 3 else 2,
                  framealpha=0.88)
        ax.grid(alpha=0.25)
        fig.tight_layout()

        path = args.output / f'EOS-{system_key.replace("/", "_")}.png'
        fig.savefig(path, dpi=150)
        plt.close(fig)
        written.append(path)
        print(f'  wrote {path}')

        if args.ascii and ascii_volumes is not None:
            print(ascii_block(system_key, ascii_rows, ascii_volumes, reference))

    print(f'\n{len(written)} plot(s) written to {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
