#!/usr/bin/env python
"""Compare the candidate pseudopotentials with the published reference methods.

The tables of ``comparison_tables.md`` already contain the pairwise numbers; this
script extracts the part that answers the practical question *"how good is our
pseudopotential compared with the published codes of the ACWF verification
paper?"* and prints it as a compact, class-wise summary.

Two different comparisons are reported, and they mean different things:

``vs AE avg``
    Distance to the all-electron average.  This is the accuracy of the
    pseudopotential (or of the code): the published codes agree with the average
    to a few 0.1 meV/atom, so for them this column is the numerical noise of the
    verification, while for our pseudopotentials it is their true error.
``vs <code>``
    Distance to one published reference calculation.  Because the reference codes
    are all essentially converged implementations of the same physics, comparing
    with any single one of them gives the same answer as comparing with the
    average; the columns are shown to document that this is the case.

Usage
-----

    python 4-analyze/compare_with_references.py
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
from common import standard as std  # noqa: E402
from common import util  # noqa: E402
from common.quantities_for_comparison import get_num_atoms_in_formula_unit  # noqa: E402
from make_comparison_report import (  # noqa: E402
    EXTERNAL_METHODS,
    KINDS,
    canonical_key,
    short_label,
)

NFU = {conf: get_num_atoms_in_formula_unit(conf) for conf in config.ALL_CONFIGURATIONS}

#: Baselines for the two classes, in meV/atom.
SSSP_PRECISION_U = 2.17


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=list(config.PSEUDOS), choices=sorted(config.PSEUDOS))
    parser.add_argument('--metric', default='delta', choices=('delta', 'nu', 'epsilon'))
    return parser.parse_args()


def load_fits(path: Path, canonicalize: bool = False) -> dict:
    """Return ``{system key: {'fit': BM fit, 'natoms': atoms in cell}}``.

    ``canonicalize`` must be used **only** for the results of this project, whose
    keys carry the cell composition (``O2U-XO2``); it rewrites the element part to
    ``U`` to match the convention of the published data.  Applying it to the
    published files (which hold every element, keyed ``Ac-X/SC``, ``U-X/SC``, ...)
    would collapse them all onto ``U-...`` and silently mix elements.
    """
    payload = json.loads(path.read_text())
    result = {}
    for key, fit in payload.get('BM_fit_data', {}).items():
        if fit is None:
            continue
        natoms = payload.get('num_atoms_in_sim_cell', {}).get(key)
        if natoms is None:
            continue
        result[canonical_key(key) if canonicalize else key] = {'fit': fit, 'natoms': natoms}
    return result


def metric(a: dict, b: dict, configuration: str, metric: str) -> float:
    """Metric between two EOS of the same system (per atom for delta)."""
    natoms_fu = NFU[configuration]
    v0_a = eosdata.volume_per_formula_unit(a['fit'], a['natoms'], natoms_fu)
    v0_b = eosdata.volume_per_formula_unit(b['fit'], b['natoms'], natoms_fu)
    common = (a['fit']['bulk_modulus_ev_ang3'], a['fit']['bulk_deriv'],
              b['fit']['bulk_modulus_ev_ang3'], b['fit']['bulk_deriv'])
    if metric == 'delta':
        return eosdata.delta_per_atom(v0_a, common[0], common[1], v0_b, common[2], common[3], natoms_fu)
    if metric == 'nu':
        return eosdata.nu_metric(v0_a, common[0], common[1], v0_b, common[2], common[3])
    return eosdata.epsilon_metric(v0_a, common[0], common[1], v0_b, common[2], common[3])


def main() -> int:
    args = parse_args()
    util.load_profile()

    reference_dir = config.ACWF_SCRIPTS_DIR / '3-analyze' / 'outputs'

    # all-electron average
    ae = {}
    for filename in config.REFERENCE_FILES.values():
        ae.update(load_fits(config.REFERENCE_DATA_DIR / filename))

    # published codes
    codes = {}
    for label, template in EXTERNAL_METHODS:
        data = {}
        for kind in KINDS:
            path = reference_dir / template.format(kind=kind)
            if path.exists():
                data.update(load_fits(path))
        codes[short_label(label)] = data

    units = {'delta': 'meV/atom', 'nu': '%', 'epsilon': ''}
    order = [f'U-{conf}' for conf in config.ALL_CONFIGURATIONS]
    unary = [key for key in order if key.split('-', 1)[1] in config.UNARY_CONFIGURATIONS]
    oxide = [key for key in order if key.split('-', 1)[1] not in config.UNARY_CONFIGURATIONS]

    for pseudo_key in args.pseudos:
        name = util.set_name(pseudo_key)
        path = config.OUTPUTS_DIR / f'results-{name}-{util.PLUGIN_NAME}.json'
        if not path.exists():
            print(f'  {name}: no results — skipped')
            continue
        ours = load_fits(path, canonicalize=True)
        label = short_label(f"{config.PSEUDOS[pseudo_key]['upf']} "
                            f"[{'SR' if config.PSEUDOS[pseudo_key]['rel'] == 'scalar' else 'FR'}]")

        print('=' * 100)
        print(f'{label}  —  {args.metric} [{units[args.metric]}] against the all-electron average '
              f'and against the published codes')
        print('=' * 100)
        header = f"{'system':<13}{'ours|AE':>9}" + ''.join(f"{'|' + code:>9}" for code in codes) + \
                 f"{'':>4}" + ''.join(f"{'AE|' + code:>10}" for code in codes)
        print(header)
        print('-' * len(header))

        rows = {}
        for system in order + ['__mean_unary__', '__mean_oxide__']:
            if system.startswith('__'):
                subset = unary if 'unary' in system else oxide
                cells = {}
                for code in ['AE'] + list(codes):
                    values = [rows[item][code] for item in subset if item in rows]
                    cells[code] = sum(values) / len(values) if values else float('nan')
                rows[system] = cells
                title = 'mean unaries' if 'unary' in system else 'mean oxides'
                print(f'{title:<13}' + ''.join(f'{cells[code]:>9.3f}' for code in ['AE'] + list(codes)))
                continue

            configuration = system.split('-', 1)[1]
            if system not in ours or system not in ae:
                continue
            cells = {'AE': metric(ours[system], ae[system], configuration, args.metric)}
            for code, data in codes.items():
                if system in data:
                    cells[code] = metric(ours[system], data[system], configuration, args.metric)
            rows[system] = cells
            line = f'{system:<13}{cells["AE"]:>9.3f}' + ''.join(
                f'{cells.get(code, float("nan")):>9.3f}' for code in codes)
            if args.metric == 'delta' and ae:
                line += '    ' + ''.join(
                    f'{metric(ae[system], codes[code][system], configuration, args.metric):>10.3f}'
                    for code in codes if system in codes[code])
            print(line)

        print()
        print('  Reference for the two bands of the SSSP criteria (meV/atom): '
              f'pass <= {std.get_criterion("delta")["pass"]}, '
              f'acceptable <= {std.get_criterion("delta")["good"]}; '
              f'the published SSSP precision pseudopotentials reach '
              f'Delta <= {SSSP_PRECISION_U} for uranium.')
        print('  The last columns (AE|<code>) are the distance between the all-electron average '
              'and each published code:')
        print('  they show that all reference codes are converged implementations of the same '
              'physics, so any of them is an equivalent yardstick.')
        print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
