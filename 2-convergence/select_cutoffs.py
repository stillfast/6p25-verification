#!/usr/bin/env python
"""Turn the cutoff scan into recommended cutoffs (``cutoffs.json``).

For every convergence point of ``run_cutoff_convergence.py`` the EOS of each scan
structure is fitted with the same Birch-Murnaghan implementation used everywhere
else in this project.  The fit is then compared with the fit at the reference
point (the largest ``ecutwfc``, and among those the largest dual) using the SSSP
criterion for a *converged EOS*::

    nu-like distance  <=  CUTOFF_CONVERGENCE_NU_TOLERANCE   (0.2, percent)

which is the ``eos: bounds = [0.0, 0.2]`` entry of the SSSP ``criteria.yml``
(``standard`` set), evaluated with the same ``rel_errors_vec_length`` definition
(weights ``1/20`` on B0 and ``1/400`` on B1).

The recommended cutoff is the smallest scan point that satisfies the criterion
for **all** scan structures.

Usage
-----

    python 2-convergence/select_cutoffs.py --pseudos sr fr
    python 2-convergence/select_cutoffs.py --pseudos sr --tolerance 0.1
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=sorted(config.PSEUDOS), choices=sorted(config.PSEUDOS))
    parser.add_argument('--criterion', default='nu', choices=('nu', 'epsilon'),
                        help='Which distance between the EOS fits decides convergence: `nu` (the '
                             'SSSP control-protocol choice: weighted relative difference of V0, B0, '
                             'B1, in percent) or `epsilon` (the dimensionless area between the two '
                             'EOS curves). Both are printed for every point either way.')
    parser.add_argument('--tolerance', type=float, default=None,
                        help='Tolerance of the chosen criterion: percent for `nu` (default '
                             f'{std.CUTOFF_CONVERGENCE_NU_TOLERANCE}, the SSSP value), dimensionless for '
                             '`epsilon` (default 0.01).')
    parser.add_argument('--reference-ecut', type=float, default=None,
                        help='Use the EOS at this ecutwfc as the reference instead of the largest '
                             'tested cutoff, e.g. `--reference-ecut 200`.')
    parser.add_argument('--systems', nargs='+', default=None,
                        help='Restrict the verdict to these diagnostic structures (e.g. '
                             '`X/BCC X2O3`). By default every structure found in the '
                             'convergence groups is used, i.e. the verdict is the worst over '
                             'all of them.')
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT / '2-convergence' / 'cutoffs.json')
    return parser.parse_args()


DEFAULT_TOLERANCE = {'nu': std.CUTOFF_CONVERGENCE_NU_TOLERANCE, 'epsilon': 0.01}


def resolve_tolerance(args) -> float:
    return args.tolerance if args.tolerance is not None else DEFAULT_TOLERANCE[args.criterion]


def distance(criterion: str, fit_a, fit_b) -> float:
    """Distance between two EOS fits of the same cell, in the chosen metric."""
    if criterion == 'epsilon':
        return eosdata.epsilon_between_fits(fit_a, fit_b)
    return eosdata.nu_between_fits(fit_a, fit_b)


def collect_points(name: str):
    """Return ``{(ecutwfc, dual): {structure_key: BM fit}}`` for one set."""
    from aiida import orm

    points = {}
    for group in orm.QueryBuilder().append(
        orm.Group, filters={'label': {'like': f'acwf-verification/{name}/convergence/%'}}
    ).all(flat=True):
        parsed = util.parse_convergence_group_label(group.label)
        if parsed is None:
            continue
        ecutwfc, dual = parsed
        fits = {}
        for node in group.nodes:
            if node.process_type != 'aiida.workflows:common_workflows.eos':
                continue
            try:
                key = util.structure_key(node.inputs.structure)
            except Exception:  # noqa: BLE001
                continue
            payload = eosdata.eos_payload(node)
            if payload['BM_fit_data'] is not None:
                fits[key] = payload['BM_fit_data']
        if fits:
            points[(ecutwfc, dual)] = fits
    return points


def main() -> int:
    args = parse_args()
    util.load_profile()

    results = {}
    failures = []

    for pseudo_key in args.pseudos:
        name = util.set_name(pseudo_key)
        spec = config.PSEUDOS[pseudo_key]
        points = collect_points(name)

        print('=' * 78)
        print(f"{spec['description']}   (set '{name}')")
        print('=' * 78)

        tolerance = resolve_tolerance(args)
        if not points:
            print('  no finished convergence EOS found.')
            failures.append(pseudo_key)
            continue

        if args.reference_ecut is not None:
            candidates = [point for point in points if abs(point[0] - args.reference_ecut) < 1e-6]
            if not candidates:
                print(f'  ERROR: no scan point at ecutwfc={args.reference_ecut:g} Ry; tested: '
                      f'{sorted({point[0] for point in points})}', file=sys.stderr)
                failures.append(pseudo_key)
                continue
            reference_point = max(candidates, key=lambda item: item[1])
        else:
            reference_point = max(points, key=lambda item: (item[0], item[1]))
        reference = points[reference_point]
        structures = sorted(set().union(*(set(fits) for fits in points.values())))
        if args.systems:
            missing = [key for key in args.systems if key not in structures]
            if missing:
                print(f'  ERROR: no finished convergence EOS for {missing}; found {structures}',
                      file=sys.stderr)
                failures.append(pseudo_key)
                continue
            structures = [key for key in args.systems if key in structures]
        print(f"  reference point: ecutwfc={reference_point[0]:g} Ry, dual={reference_point[1]:g} "
              f"(ecutrho={reference_point[0] * reference_point[1]:g} Ry)")
        print(f"  structures     : {structures}")
        print()
        print(f"  criterion      : {args.criterion} <= {tolerance:g}"
              f"{' %' if args.criterion == 'nu' else ''}")
        print(f"  {'ecutwfc':>8} {'dual':>5} {'ecutrho':>8}   " +
              '  '.join(f'{key:>14}' for key in structures) +
              '   ' + '  '.join(f'{key + " (eps)":>16}' for key in structures) + '   verdict')
        print('  ' + '-' * (34 + 34 * len(structures) + 10))

        rows = {}
        for point in sorted(points):
            fits = points[point]
            values = {}
            epsilons = {}
            ok = True
            for key in structures:
                if key not in fits or key not in reference:
                    values[key] = None
                    epsilons[key] = None
                    ok = False
                    continue
                values[key] = eosdata.nu_between_fits(fits[key], reference[key])
                epsilons[key] = eosdata.epsilon_between_fits(fits[key], reference[key])
                if distance(args.criterion, fits[key], reference[key]) > tolerance:
                    ok = False
            rows[point] = {'values': values, 'epsilons': epsilons, 'converged': ok}
            cells = '  '.join(
                f"{values[key]:>14.4f}" if values[key] is not None else f"{'--':>14}" for key in structures
            )
            eps_cells = '  '.join(
                (f"{epsilons[key]:>16.5f}" if epsilons.get(key) is not None else f"{'--':>16}")
                for key in structures)
            print(f"  {point[0]:>8g} {point[1]:>5g} {point[0] * point[1]:>8g}   {cells}   "
                  f"{eps_cells}   {'converged' if ok else 'not converged'}")

        # Smallest wavefunction cutoff (at the dual of the reference) that is converged.
        wfc_candidates = sorted(
            (point for point, row in rows.items() if row['converged'] and point[1] == reference_point[1]),
            key=lambda item: item[0],
        )
        if not wfc_candidates:
            print('\n  WARNING: no scan point satisfies the criterion. Increase the scan range, '
                  'or relax --tolerance.')
            failures.append(pseudo_key)
            # Do NOT record the reference point as if it were a recommendation: it was only the
            # top of the scan, and writing it would both change the cutoffs of every later
            # submission and make the audit flag the runs that used the project default.
            fallback = config.PSEUDOS[pseudo_key].get('default_cutoffs', {}).get('U')
            if fallback is None:
                print(f'  ERROR: {pseudo_key} has no `default_cutoffs` to fall back to.',
                      file=sys.stderr)
                return 1
            chosen = (float(fallback[0]), float(fallback[1]) / float(fallback[0]))
            print(f'  The scan did NOT converge, so no cutoff is recommended. Recording the '
                  f'project default ({fallback[0]:g}/{fallback[1]:g} Ry) with '
                  f'`converged: false`, which is also what submissions will use.')
        else:
            chosen = wfc_candidates[0]

        # For the dual: smallest dual at the chosen wavefunction cutoff that is converged.
        if wfc_candidates:
            dual_candidates = sorted(
                (point for point, row in rows.items() if row['converged'] and point[0] == chosen[0]),
                key=lambda item: item[1],
            )
            if dual_candidates:
                chosen = dual_candidates[0]
            else:
                chosen = (chosen[0], max(reference_point[1], chosen[1]))

        ecutwfc, dual = chosen
        ecutrho = ecutwfc * dual
        converged = bool(rows.get(chosen, {}).get('converged', False))
        print()
        print(f"  ==> recommended: ecutwfc = {ecutwfc:g} Ry, dual = {dual:g}, "
              f"ecutrho = {ecutrho:g} Ry")
        unit = ' %' if args.criterion == 'nu' else ''
        if converged:
            print(f"      (converged: {args.criterion} <= {tolerance:g}{unit} between the plane-wave "
                  f"cutoff at {ecutwfc:g} Ry and the reference at {reference_point[0]:g} Ry)")
        else:
            print('      NOT CONVERGED — this value is a fallback, not a verified cutoff.')

        results[pseudo_key] = {
            'U': {
                'ecutwfc': ecutwfc,
                'ecutrho': ecutrho,
                'dual': dual,
                'converged': converged,
                'nu_percent': {key: (None if value is None else round(value, 5))
                               for key, value in rows.get(chosen, {}).get('values', {}).items()},
                'epsilon': {key: (None if value is None else round(value, 6))
                            for key, value in rows.get(chosen, {}).get('epsilons', {}).items()},
            },
            'O': {'ecutwfc': float(config.O_CUTOFFS[0]), 'ecutrho': float(config.O_CUTOFFS[1])},
            '_meta': {
                'reference_point': {'ecutwfc': reference_point[0], 'dual': reference_point[1]},
                'criterion': args.criterion,
                'tolerance': tolerance,
                'tolerance_percent': tolerance if args.criterion == 'nu' else None,
                'tested_points': sorted(point[0] for point in rows),
                **({} if converged else {
                    'note': 'no scan point met the criterion; the value recorded here is the '
                            'project default, NOT a converged cutoff'}),
            },
        }
        print()

    if not results:
        print('ERROR: nothing to write.', file=sys.stderr)
        return 1

    # Merge into whatever is already there instead of replacing it: the recommended cutoff of
    # a pseudopotential that was not part of this invocation must survive, otherwise a run for
    # candidate B silently drops the record of candidate A (and the audit then flags A's whole
    # dataset as having "the wrong cutoff", which is how this bug was found).
    payload = {}
    if args.output.exists():
        try:
            payload = json.loads(args.output.read_text())
        except Exception:  # noqa: BLE001
            payload = {}
    payload.pop('_metadata', None)
    payload.update(results)
    payload['_metadata'] = {
        'criterion': 'per-pseudopotential: the entry records which metric decided it '
                     '(`criterion`: nu or epsilon, with `tolerance` and `reference_point`). '
                     'The SSSP control protocol uses nu <= 0.2 %.',
        'tolerance_percent': args.tolerance,
        'note': 'O cutoffs are fixed to the recommended values of O_ONCV_PBE-1.0; the effective '
                'cutoff of a mixed U/O cell is the maximum over its elements.',
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    print(f"Written: {args.output}")
    print('The launcher (3-submit/launch_calculations_qe.py) picks these values up automatically.')

    if failures:
        print(f"\nWARNING: no converged cutoff could be determined for {failures}.")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
