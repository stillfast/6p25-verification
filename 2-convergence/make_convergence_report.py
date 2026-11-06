#!/usr/bin/env python
"""Write the cutoff-convergence scan of a project as a markdown report.

The scan itself lives in AiiDA (one EOS workchain per cutoff point and diagnostic system);
`select_cutoffs.py` turns it into `cutoffs.json`.  This script turns the *same* data into a
readable markdown document, so that the numbers can be checked, quoted and archived without
re-running anything — and so that every number in it can be traced back to the AiiDA nodes
that produced it (the report carries the PK and UUID of each scan point).

Two files are written.

``convergence-report.md`` — short form: one table per diagnostic system (metal first, then the
oxide) with six columns, ``ecutwfc``, ``ecutrho``, ``ν``, ``Δν``, ``ε``, ``Δε``.  Every ``Δ``
is that row's value minus the previous (lower-cutoff) row, i.e. how much one more step of
basis moved the result; the lowest cutoff has no ``Δ``, and the reference row has distance 0
by construction.

``convergence-report-full.md`` — long form, for checking the short one:

1. the identity of the scanned pseudopotential and the conditions of the scan;
2. one row per tested cutoff: ν and ε of each diagnostic system against the reference, the
   verdict of both criteria, and the PK/UUID of the EOS workchain behind the row;
3. the distance between *neighbouring* cutoffs (the reference-free version of ``Δ``);
4. a reference-sensitivity table: which cutoff the scan recommends for *every* possible
   choice of reference point (this is what tells you whether the reference is high enough);
5. whether the standard ``pw.x`` SCFs behind the rows reached ``convergence_achieved``, and
   the quality of each Birch-Murnaghan fit (a broken fit makes ν and ε meaningless);
6. optionally the full pairwise distance matrix between the tested cutoffs;
7. notes on the two traps of this measurement (the numerical floor of ε, and the fact that
   the distances are not necessarily monotonic in the cutoff).

Usage
-----

    python 2-convergence/make_convergence_report.py
    python 2-convergence/make_convergence_report.py --reference-ecut 250
    python 2-convergence/make_convergence_report.py --tolerance-epsilon 0.02 --matrix
    python 2-convergence/make_convergence_report.py --output /tmp/scan.md

Defaults: reference = the largest tested cutoff, ν tolerance 0.2 % (the SSSP control-protocol
value), ε tolerance 0.01, output ``2-convergence/convergence-report.md`` (and the long form
``2-convergence/convergence-report-full.md``).
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import eosdata  # noqa: E402
from common import standard as std  # noqa: E402
from common import util  # noqa: E402

DEFAULT_NU_TOLERANCE = std.CUTOFF_CONVERGENCE_NU_TOLERANCE      # 0.2 %
DEFAULT_EPSILON_TOLERANCE = 0.01


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=sorted(config.PSEUDOS),
                        choices=sorted(config.PSEUDOS))
    parser.add_argument('--reference-ecut', type=float, default=None,
                        help='Reference cutoff of the main table (default: the largest tested).')
    parser.add_argument('--criterion', default='both', choices=('both', 'nu', 'epsilon'),
                        help='Which criterion the report states and judges (default: both). '
                             'Use `epsilon` for the stricter ε-only screening.')
    parser.add_argument('--tolerance-nu', type=float, default=DEFAULT_NU_TOLERANCE,
                        help=f'ν tolerance in percent (default {DEFAULT_NU_TOLERANCE}).')
    parser.add_argument('--tolerance-epsilon', type=float, default=DEFAULT_EPSILON_TOLERANCE,
                        help=f'ε tolerance (default {DEFAULT_EPSILON_TOLERANCE}).')
    parser.add_argument('--systems', nargs='+', default=None,
                        help='Restrict the table to these structures (default: all scanned).')
    parser.add_argument('--max-misfit-mev', type=float, default=0.3,
                        help='Flag a BM fit whose RMS misfit exceeds this many meV per atom '
                             '(default 0.3). A converged fit of this project sits at ~0.005, the '
                             'broken low-cutoff fits at 1-3 meV/atom.')
    parser.add_argument('--b1-range', nargs=2, type=float, default=(2.5, 8.0),
                        help='Plausible range of the Birch-Murnaghan B1 (default 2.5 8.0); a fit '
                             'outside it is flagged even if its residual looks small.')
    parser.add_argument('--no-deltas', action='store_true',
                        help='Drop the Δ columns of the short report (they are the only place '
                             'Δ appears; the long report always prints raw values).')
    parser.add_argument('--full-systems', nargs='+', default=None,
                        help='Diagnostic systems of the long-form report, when it must cover more '
                             'structures than the short form (default: the same as --systems, '
                             'i.e. everything the scan holds).')
    parser.add_argument('--matrix', action='store_true',
                        help='Also print the pairwise distance matrix between all tested cutoffs.')
    parser.add_argument('--full-output', type=Path, default=None,
                        help='Where to write the long-form report with all diagnostics '
                             '(default: the --output path with a -full suffix).')
    parser.add_argument('--output', type=Path,
                        default=PROJECT_ROOT / '2-convergence' / 'convergence-report.md')
    return parser.parse_args()


def collect(pseudo_key: str) -> Dict[Tuple[float, float], Dict[str, Dict[str, Any]]]:
    """``{(ecutwfc, dual): {structure: {'fit', 'pk', 'uuid', 'exit_status'}}}``.

    One entry per structure and cutoff point.  When a group holds several EOS workchains for
    the same structure (re-runs, or the extra systems of an interrupted submission that were
    killed), the newest *successfully finished* one wins; a group whose only node is
    unfinished yields no entry, and the caller reports that as a gap.
    """
    from aiida import orm

    name = util.set_name(pseudo_key)
    points: Dict[Tuple[float, float], Dict[str, Dict[str, Any]]] = {}
    groups = [group for group in orm.QueryBuilder().append(
        orm.Group, filters={'label': {'like': f'acwf-verification/{name}/convergence/%'}}
    ).all(flat=True)]
    for group in sorted(groups, key=lambda item: item.label):
        parsed = util.parse_convergence_group_label(group.label)
        if parsed is None:
            continue
        entries: Dict[str, Dict[str, Any]] = {}
        for node in sorted(group.nodes, key=lambda item: item.pk):
            if node.process_type != 'aiida.workflows:common_workflows.eos' or not node.is_finished_ok:
                continue
            payload = eosdata.eos_payload(node)
            if not payload['BM_fit_data']:
                continue
            try:
                system = util.structure_key(node.inputs.structure)
            except Exception:  # noqa: BLE001
                system = node.base.extras.get('configuration', str(node.pk))
            entries[system] = {'fit': payload['BM_fit_data'], 'pk': node.pk,
                               'uuid': str(node.uuid), 'node': node,
                               'natoms': payload.get('num_atoms_in_sim_cell'),
                               'npoints': len(payload.get('eos_data') or [])}
        if entries:
            points[parsed] = entries
    return points


def fit_quality(points, systems, cuts, args) -> list:
    """Report the quality of every BM fit the table above is built from.

    Every distance in this report is computed from *fitted* EOS curves, not from the raw
    energies.  When the plane-wave basis is too small the seven energies are not smooth enough
    for a three-parameter fit, and the fit then produces an unphysical B1 (negative, or far from
    ~4) with a residual orders of magnitude larger than at a converged cutoff — the fit, and
    therefore every ν and ε computed from it, is then meaningless even though all SCFs
    converged.  This table makes that visible instead of leaving it to be discovered from a
    non-monotonic distance.
    """
    low, high = args.b1_range
    lines = ['', '### Fit quality per cutoff (read this before trusting a metric)', '',
             'ν and ε are computed from *fitted* Birch-Murnaghan curves, so a fit that does not '
             'describe its seven points makes both metrics meaningless — even when every SCF '
             'converged. Two independent symptoms are shown below: the fitted B1 (the expected '
             'value for these systems is ≈4; a negative one is unphysical) and the RMS misfit of '
             'the fit expressed per atom, which is the number that matters for a per-atom metric.', '',
             '| ecutwfc | system | B1 | BM residual [eV²] | RMS misfit [meV/atom] | flag |',
             '|---|---|---|---|---|---|']
    for point in cuts:
        for system in systems:
            entry = points[point].get(system)
            if not entry:
                continue
            fit = entry['fit']
            b1 = fit.get('bulk_deriv')
            residual = fit.get('residuals')
            natoms = entry.get('natoms') or 1
            npoints = entry.get('npoints') or 7
            misfit = (residual / npoints) ** 0.5 / natoms * 1000.0 if residual is not None else None
            flags = []
            if b1 is None or not (low <= b1 <= high):
                flags.append('B1 unphysical')
            if misfit is None or misfit > args.max_misfit_mev:
                flags.append('misfit large')
            lines.append(f'| {point[0]:g} | {system} | {b1:.3f} | {residual:.2e} | '
                         f'{misfit:.3f} | '
                         f'{"**" + "; ".join(flags) + "**" if flags else "ok"} |')
    lines.append('')
    if any('**' in line for line in lines):
        lines.append("Flagged rows mean: do **not** quote that point's ν/ε as a converged-basis "
                     "statement. This is what a non-monotonic distance in the table above looks "
                     "like from the inside — the metric is fine, the fit underneath it is not.")
    return lines


def scf_check(points, systems, cuts) -> list:
    """Per cutoff: did the ``pw.x`` SCFs themselves converge?

    This is a *different* question from the cutoff convergence of the table above, and the
    report must answer it explicitly because the word "converged" is otherwise easy to
    misread.  The number comes from the plugin's parsed ``convergence_info.scf_conv`` of each
    calculation (``convergence_achieved`` plus the final ``scf_error`` against that
    calculation's own ``conv_thr``), and only the project's own SCFs count (``disk_io=nowf``;
    the cached ``base_init_relax`` SCFs belong to a different, discarded input).
    """
    from aiida.common.links import LinkType

    lines = ['', '### Did the SCFs converge? (a different question)', '',
             'The verdicts above concern the **plane-wave cutoff**: whether the EOS still moves '
             'when more plane waves are added. They say nothing about the self-consistent field, '
             'which is a separate check (`conv_thr`, here `natoms × 1e-10 Ry`). For the same '
             'calculations:', '',
             '| ecutwfc | standard `pw.x` SCFs | all reached `convergence_achieved` | '
             'worst `scf_error / conv_thr` | SCF steps |', '|---|---|---|---|---|']

    def pw_calcs(eos):
        stack, found = [eos], []
        while stack:
            current = stack.pop()
            for link in current.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
                stack.append(link.node)
            for link in current.base.links.get_outgoing(link_type=LinkType.CALL_CALC).all():
                calc = link.node
                if calc.process_type != 'aiida.calculations:quantumespresso.pw':
                    continue
                if not getattr(calc, 'is_finished_ok', False):
                    continue
                try:
                    if calc.inputs.parameters.get_dict()['CONTROL'].get('disk_io') != 'nowf':
                        continue
                except Exception:  # noqa: BLE001
                    continue
                found.append(calc)
        return found

    for point in cuts:
        calcs = []
        for system in systems:
            entry = points[point].get(system)
            if entry and entry.get('node') is not None:
                calcs.extend(pw_calcs(entry['node']))
        if not calcs:
            lines.append(f'| {point[0]:g} | 0 | — | — | — |')
            continue
        ratios, achieved, steps = [], True, []
        for calc in calcs:
            info = calc.outputs.output_parameters.get_dict().get('convergence_info', {})
            scf = info.get('scf_conv', {})
            threshold = calc.inputs.parameters.get_dict()['ELECTRONS']['conv_thr']
            achieved &= bool(scf.get('convergence_achieved'))
            ratios.append((scf.get('scf_error') or 0.0) / threshold)
            steps.append(scf.get('n_scf_steps') or 0)
        lines.append(f'| {point[0]:g} | {len(calcs)} | {achieved} | {max(ratios):.3f} | '
                     f'{min(steps)}–{max(steps)} |')
    lines += ['', 'A ratio below 1 means the final `estimated scf accuracy` was inside that '
              "calculation's own `conv_thr`. **Every SCF in every row above converged**, "
              'including the cutoffs whose *cutoff* verdict is "not converged".', '']
    return lines


def distance(metric: str, fit_a, fit_b) -> float:
    return (eosdata.epsilon_between_fits(fit_a, fit_b) if metric == 'epsilon'
            else eosdata.nu_between_fits(fit_a, fit_b))


def verdict(value: float, tolerance: float) -> str:
    """Verdict of a *cutoff-convergence* criterion (never an SCF statement)."""
    return 'cutoff-converged' if value <= tolerance else 'cutoff NOT converged'


def ordered_systems(systems) -> list:
    """Diagnostic systems in reading order: the metal first, then the oxide."""
    def rank(name):
        upper = name.upper()
        return (0 if 'FCC' in upper else 1 if 'BCC' in upper else 2 if 'SC' in upper else 3,
                name)
    return sorted(systems, key=rank)


def reference_point(points, requested):
    """The reference point: the requested ecutwfc if given, else the largest tested."""
    if requested is None:
        return max(points, key=lambda item: (item[0], item[1]))
    candidates = [point for point in points if abs(point[0] - requested) < 1e-6]
    if not candidates:
        raise SystemExit(f'no scan point at ecutwfc={requested:g} Ry; tested: '
                         f'{sorted({point[0] for point in points})}')
    return max(candidates, key=lambda item: item[1])


def concise_for(pseudo_key: str, points, args) -> str:
    """The short form: one table per diagnostic system, two numbers per metric.

    Columns are ``ν``, ``Δν``, ``ε``, ``Δε``; every ``Δ`` is that row's value minus the value
    of the previous (lower-cutoff) row, so it answers "how much did one more step of basis
    move the result?".  The lowest cutoff has no ``Δ``, and the reference row has distance 0
    by construction.
    """
    spec = config.PSEUDOS[pseudo_key]
    reference = reference_point(points, args.reference_ecut)
    systems = ordered_systems(
        args.systems or set().union(*(set(entry) for entry in points.values())))
    cuts = sorted(points)

    lines = [f'## {spec["description"]}', '']
    if args.criterion == 'epsilon':
        stated = f'criterion ε ≤ {args.tolerance_epsilon:g}'
    elif args.criterion == 'nu':
        stated = f'criterion ν ≤ {args.tolerance_nu:g} %'
    else:
        stated = f'criteria ν ≤ {args.tolerance_nu:g} % and ε ≤ {args.tolerance_epsilon:g}'
    lines.append(f'Scan of `{util.set_name(pseudo_key)}` over '
                 f'{", ".join(f"{point[0]:g}/{point[1]:g}" for point in cuts)} Ry '
                 f'(ecutwfc/dual); every row is compared with the reference point '
                 f'**{reference[0]:g} Ry**; {stated}. '
                 f'ν in %, ε dimensionless. '
                 f'Δ = this row minus the previous (lower-cutoff) row.')
    lines.append('')

    for system in systems:
        has = [point for point in cuts if system in points.get(point, {})]
        if not has:
            lines += [f'### {system}', '', 'No finished EOS for this system.', '']
            continue
        weights = ['ecutwfc', 'ecutrho', f'ν({system})']
        if not args.no_deltas:
            weights.append(f'Δν({system})')
        weights.append(f'ε({system})')
        if not args.no_deltas:
            weights.append(f'Δε({system})')
        lines.append(f'### {system}')
        lines.append('')
        lines.append('| ' + ' | '.join(weights) + ' |')
        lines.append('|' + '---|' * len(weights))
        previous = None
        for point in cuts:
            if system not in points.get(point, {}):
                continue
            fit = points[point][system]['fit']
            if system in points.get(reference, {}):
                nu = distance('nu', fit, points[reference][system]['fit'])
                eps = distance('epsilon', fit, points[reference][system]['fit'])
            else:
                nu = eps = None
            row = [f'{point[0]:g}', f'{point[0] * point[1]:g}']
            row.append('—' if nu is None else f'{nu:.4f}')
            if not args.no_deltas:
                row.append('—' if nu is None or previous is None else f'{nu - previous[0]:+.4f}')
            row.append('—' if eps is None else f'{eps:.5f}')
            if not args.no_deltas:
                row.append('—' if eps is None or previous is None else f'{eps - previous[1]:+.5f}')
            lines.append('| ' + ' | '.join(row) + ' |')
            if nu is not None and eps is not None:
                previous = (nu, eps)
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def report_for(pseudo_key: str, points, args) -> str:
    spec = config.PSEUDOS[pseudo_key]
    reference = reference_point(points, args.reference_ecut)
    systems = ordered_systems(
        args.systems or set().union(*(set(entry) for entry in points.values())))
    cuts = sorted(points)

    lines = [f'## {spec["description"]}', '',
             '| | |', '|---|---|',
             f'| AiiDA set | `{util.set_name(pseudo_key)}` |',
             f'| convergence groups | `acwf-verification/{util.set_name(pseudo_key)}/convergence/...` |',
             f'| tested cutoffs (ecutwfc, dual) | '
             f'{", ".join(f"{point[0]:g}/{point[1]:g}" for point in cuts)} |',
             f'| reference point | **{reference[0]:g} Ry** (dual {reference[1]:g}, '
             f'ecutrho {reference[0] * reference[1]:g} Ry) |',
             f'| diagnostic systems | {", ".join(systems)} |',
             f'| criteria | ν ≤ {args.tolerance_nu:g} % (SSSP control protocol) · '
             f'ε ≤ {args.tolerance_epsilon:g} |',
             f'| criterion judged below | '
             f'{args.criterion if args.criterion != "both" else "nu and epsilon"} |', '']

    # ---- main table ---------------------------------------------------------------
    header = ['ecutwfc', 'ecutrho']
    for system in systems:
        header += [f'ν({system}) [%]', f'ε({system})']
    if args.criterion in ('both', 'nu'):
        header.append('ν verdict (cutoff)')
    if args.criterion in ('both', 'epsilon'):
        header.append('ε verdict (cutoff)')
    header.append('EOS workchain PK / UUID')
    lines.append('| ' + ' | '.join(header) + ' |')
    lines.append('|' + '---|' * len(header))

    per_cut: Dict[float, Dict[str, Any]] = {}
    for point in cuts:
        entry = points[point]
        cells = [f'{point[0]:g}', f'{point[0] * point[1]:g}']
        nu_values, eps_values = {}, {}
        ident = []
        for system in systems:
            if system not in entry:
                cells += ['—', '—']
                ident.append(f'{system}: (no finished EOS)')
                continue
            fit = entry[system]['fit']
            nu_values[system] = distance('nu', fit, points[reference][system]['fit']) \
                if system in points[reference] else None
            eps_values[system] = distance('epsilon', fit, points[reference][system]['fit']) \
                if system in points[reference] else None
            cells.append('—' if nu_values[system] is None else f'{nu_values[system]:.4f}')
            cells.append('—' if eps_values[system] is None else f'{eps_values[system]:.5f}')
            ident.append(f'{system}:{entry[system]["pk"]}')
        nu_max = max((value for value in nu_values.values() if value is not None), default=None)
        eps_max = max((value for value in eps_values.values() if value is not None), default=None)
        if args.criterion in ('both', 'nu'):
            cells.append('—' if nu_max is None else verdict(nu_max, args.tolerance_nu))
        if args.criterion in ('both', 'epsilon'):
            cells.append('—' if eps_max is None else verdict(eps_max, args.tolerance_epsilon))
        cells.append(' · '.join(ident))
        lines.append('| ' + ' | '.join(cells) + ' |')
        per_cut[point] = {'nu_max': nu_max, 'eps_max': eps_max, 'systems': dict(entry),
                          'nu': dict(nu_values), 'eps': dict(eps_values)}



    # ---- SCF check (about conv_thr, not about the cutoff) --------------------------
    lines += scf_check(points, systems, cuts)

    # ---- fit quality ----------------------------------------------------------------
    lines += fit_quality(points, systems, cuts, args)

    # ---- recommendation -----------------------------------------------------------
    lines += ['', '### Recommendation', '']
    below = [point for point in cuts if point < reference]
    converged = {}
    for metric, tolerance, key in (('nu', args.tolerance_nu, 'nu_max'),
                                   ('epsilon', args.tolerance_epsilon, 'eps_max')):
        ok = [point for point in below
              if per_cut[point][key] is not None and per_cut[point][key] <= tolerance]
        converged[metric] = min(ok, key=lambda point: point[0]) if ok else None
    for metric, tolerance in (('nu', args.tolerance_nu), ('epsilon', args.tolerance_epsilon)):
        best = converged[metric]
        unit = ' %' if metric == 'nu' else ''
        if best is None:
            lines.append(f'* **{metric} <= {tolerance:g}{unit}: no tested cutoff is converged** '
                         f'against the {reference[0]:g} Ry reference — extend the scan range.')
        else:
            value = per_cut[best]['nu_max' if metric == 'nu' else 'eps_max']
            margin = tolerance / value if value else float('inf')
            lines.append(f'* **{metric} <= {tolerance:g}{unit}: {best[0]:g} Ry** '
                         f'(worst system {value:.5g}{unit}, margin {margin:.1f}x).')
    if converged['nu'] is not None and converged['epsilon'] is not None \
            and converged['nu'][0] != converged['epsilon'][0]:
        lines.append('')
        lines.append(f'> The two criteria disagree ({converged["nu"][0]:g} Ry vs '
                     f'{converged["epsilon"][0]:g} Ry). ε is the stricter, noise-sensitive one: '
                     'see the notes below, and prefer the larger cutoff if the difference '
                     'matters for the production runs.')

    # how much the *top* of the scan still moves: the honest "is this saturated?" number
    if len(cuts) >= 2:
        top, below_top = cuts[-1], cuts[-2]
        moves = []
        for system in systems:
            left = per_cut[top].get('nu', {}).get(system)
            right = per_cut[below_top].get('nu', {}).get(system)
            left_e = per_cut[top].get('eps', {}).get(system)
            right_e = per_cut[below_top].get('eps', {}).get(system)
            if None in (left, right, left_e, right_e):
                continue
            moves.append(f'{system}: |Δν| = {abs(left - right):.4f} %, '
                         f'|Δε| = {abs(left_e - right_e):.5f}')
        if moves:
            lines += ['', f'**Residual movement at the top of the scan** '
                          f'({below_top[0]:g} → {top[0]:g} Ry): ' + ' · '.join(moves) +
                      '. This is the part of the scan that the reference cannot see; if it is '
                      'not comfortably below the tolerances, the reference is too low.']

    # ---- distance between *neighbouring* cutoffs (no reference involved) ------------
    if len(cuts) >= 2:
        lines += ['', '### Distance between neighbouring cutoffs (reference-free)', '',
                  'The `Δ` above is a difference of two distances to the same reference. This '
                  'table is the purer quantity: the EOS fitted at one cutoff compared directly '
                  'with the EOS fitted at the next one. If a step is well below the tolerance, '
                  'adding that much basis changed nothing observable.', '']
        pair_header = ['step [Ry]']
        for system in systems:
            pair_header += [f'ν({system}) [%]', f'ε({system})']
        pair_header += ['worst ν', 'worst ε']
        lines.append('| ' + ' | '.join(pair_header) + ' |')
        lines.append('|' + '---|' * len(pair_header))
        for lower, upper in zip(cuts, cuts[1:]):
            cells = [f'{lower[0]:g} → {upper[0]:g}']
            pair_nu, pair_eps = [], []
            for system in systems:
                if system not in points.get(lower, {}) or system not in points.get(upper, {}):
                    cells += ['—', '—']
                    continue
                fit_l = points[lower][system]['fit']
                fit_u = points[upper][system]['fit']
                nu = distance('nu', fit_l, fit_u)
                eps = distance('epsilon', fit_l, fit_u)
                pair_nu.append(nu)
                pair_eps.append(eps)
                cells += [f'{nu:.4f}', f'{eps:.5f}']
            cells += [f'{max(pair_nu):.4f}' if pair_nu else '—',
                      f'{max(pair_eps):.5f}' if pair_eps else '—']
            lines.append('| ' + ' | '.join(cells) + ' |')
        lines.append('')
        lines.append('Read together with the `Δ` columns: a small `Δ` on a row whose '
                     'neighbouring-step distance is also small means the scan has genuinely '
                     'saturated there; a small `Δ` with a large neighbouring-step distance '
                     'means the two errors happen to cancel and nothing is settled yet.')

    # ---- reference sensitivity ----------------------------------------------------
    lines += ['', '### Sensitivity to the choice of the reference point', '',
              'The scan can only recommend a cutoff for a reference *above* it, so this table '
              'shows what every possible reference would give. A reference that is too low '
              'either yields no converged point or a misleadingly low one.', '',
              f'| reference [Ry] | smallest converged: ν ≤ {args.tolerance_nu:g} % | '
              f'smallest converged: ε ≤ {args.tolerance_epsilon:g} |', '|---|---|---|']
    for ref in cuts:
        row_nu = row_eps = '—'
        for cut in cuts:
            if cut >= ref:
                continue
            entry, ref_entry = points[cut], points[ref]
            shared = [system for system in systems if system in entry and system in ref_entry]
            if not shared:
                continue
            nu = max(distance('nu', entry[system]['fit'], ref_entry[system]['fit'])
                     for system in shared)
            eps = max(distance('epsilon', entry[system]['fit'], ref_entry[system]['fit'])
                      for system in shared)
            if nu <= args.tolerance_nu and row_nu == '—':
                row_nu = f'{cut[0]:g} Ry'
            if eps <= args.tolerance_epsilon and row_eps == '—':
                row_eps = f'{cut[0]:g} Ry'
        lines.append(f'| {ref[0]:g} | {row_nu} | {row_eps} |')

    # ---- optional pairwise matrix -------------------------------------------------
    if args.matrix:
        lines += ['', '### Pairwise distances between the tested cutoffs', '',
                  'Maximum over the diagnostic systems of ν [%] / ε. The matrix is symmetric '
                  'only up to the numerical noise of ε (the official implementation integrates '
                  'in a direction-dependent way), so mirrored cells can differ in the 5th '
                  'decimal.', '',
                  '| pair | ' + ' | '.join(f'{point[0]:g}' for point in cuts) + ' |',
                  '|---|' + '---|' * len(cuts)]
        for left in cuts:
            cells = []
            for right in cuts:
                if left == right:
                    cells.append('—')
                    continue
                entry, other = points[left], points[right]
                shared = [system for system in systems if system in entry and system in other]
                if not shared:
                    cells.append('—')
                    continue
                nu = max(distance('nu', entry[system]['fit'], other[system]['fit'])
                         for system in shared)
                eps = max(distance('epsilon', entry[system]['fit'], other[system]['fit'])
                          for system in shared)
                cells.append(f'{nu:.4f} / {eps:.5f}')
            lines.append(f'| {left[0]:g} | ' + ' | '.join(cells) + ' |')

    # ---- monotonicity check --------------------------------------------------------
    suspicious = []
    for metric, key in (('ν', 'nu_max'), ('ε', 'eps_max')):
        previous = None
        for cut in cuts:
            value = per_cut[cut][key]
            if value is None:
                continue
            if previous is not None and value > previous[1] * 1.2 and previous[1] > 0:
                suspicious.append(f'{metric}({cut[0]:g} Ry) = {value:.5g} > '
                                  f'{previous[1]:.5g} at {previous[0]:g} Ry')
            previous = (cut[0], value)
    if suspicious:
        lines += ['', '### Non-monotonic distances (treat with care)', '',
                  'A distance that grows when the cutoff grows means the measurement is '
                  'dominated by fit noise rather than by a systematic cutoff error — check the '
                  'fit-quality table above for the point in question:', '']
        lines += [f'* {item}' for item in suspicious]

    # ---- notes ---------------------------------------------------------------------
    lines += ['', '### Notes on this measurement', '',
              '* **ε has a numerical floor.** The official implementation returns ≈5×10⁻⁴ for two '
              '*identical* EOS fits (it prints `eps2 = negative due to numerical error probably` '
              'while doing so), so the reference row shows ~5×10⁻⁴ rather than 0. Values within a '
              'few times that floor are at the resolution limit of the metric.',
              '* **ε is much stricter than ν.** A perturbation test gives ε ≈ 0.01 for an '
              'equilibrium-volume error of only ~0.015 %, while ν ≤ '
              f'{args.tolerance_nu:g} % allows roughly 0.2 % — about an order of magnitude looser '
              'on V₀.',
              '* **The reference must be far enough above the recommended cutoff.** With a '
              'reference that is only marginally converged the distances saturate at the '
              "reference's own residual, and the recommendation drifts upwards; the sensitivity "
              'table above shows how much.',
              '* **"cutoff NOT converged" is not a failed calculation.** It means the EOS at that '
              'cutoff still differs from the reference EOS by more than the tolerance, i.e. the '
              'plane-wave basis is not complete enough yet — the SCF itself converged (see the SCF '
              'table above). The opposite confusion is also possible: an SCF that hits its iteration '
              'limit (`electron_maxstep`) is reported by the audit (`4-analyze/audit_standard.py`) '
              'and by the exit status, not by this table.',
              '* Every row can be traced to its AiiDA nodes with `verdi process show <PK>`; the '
              'same PKs appear in `4-analyze/outputs/provenance-convergence.csv`.', '']

    lines += ['', '### Reproduction', '', '```bash',
              f'python 2-convergence/run_cutoff_convergence.py --pseudos {pseudo_key} \\',
              f'       --cutoffs {" ".join(f"{point[0]:g}" for point in cuts)} '
              f'--configurations '
              f'{" ".join(system.split("-", 1)[1] if "-" in system else system for system in systems)}'
              f' --run --max-memory-gb 100',
              f'python 2-convergence/select_cutoffs.py --pseudos {pseudo_key}',
              f'python 2-convergence/make_convergence_report.py --pseudos {pseudo_key}'
              + (f' --reference-ecut {reference[0]:g}' if args.reference_ecut else ''),
              '```', '']
    return '\n'.join(lines)


def main() -> int:
    args = parse_args()
    if args.full_output is None:
        args.full_output = args.output.with_name(
            args.output.stem + '-full' + args.output.suffix)
    util.load_profile()

    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    head = f'# Cutoff convergence report — {config.PROJECT_ROOT.name}'
    provenance = (f'Generated {stamp} by `2-convergence/make_convergence_report.py` from the EOS '
                  f'workchains in AiiDA (no calculation was run for this report).')
    concise = [head, '', provenance, '']
    full = [head, '',
            f'Generated {stamp} by `2-convergence/make_convergence_report.py` from the EOS '
            f'workchains in AiiDA (no calculation was run for this report). Full diagnostics: '
            f'the tables below are the long form of `{args.output.name}`.', '']

    for pseudo_key in args.pseudos:
        points = collect(pseudo_key)
        if not points:
            missing = [f'## {pseudo_key}', '',
                       'No finished convergence EOS found for this pseudopotential — run '
                       '`2-convergence/run_cutoff_convergence.py` first.', '']
            concise += missing
            full += missing
            print(f'  {pseudo_key}: no finished convergence EOS found')
            continue
        concise.append(concise_for(pseudo_key, points, args))
        full_args = args
        if args.full_systems:
            full_args = argparse.Namespace(**vars(args))
            full_args.systems = list(args.full_systems)
        full.append(report_for(pseudo_key, points, full_args))
        cuts = sorted(points)
        print(f'  {pseudo_key}: {len(cuts)} cutoff point(s) '
              f'({", ".join(f"{point[0]:g}" for point in cuts)} Ry), '
              f'{len(next(iter(points.values())))} diagnostic system(s)')

    for path, document in ((args.output, concise), (args.full_output, full)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(document).rstrip() + '\n')
        print(f'Written: {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
