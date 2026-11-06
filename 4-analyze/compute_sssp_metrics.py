#!/usr/bin/env python
"""Compute the three ACWF/SSSP comparison metrics of every system.

Metrics — all of them computed with the official implementations in
``common/quantities_for_comparison.py``:

``delta`` (meV/atom)
    RMS energy difference between the pseudopotential EOS and the all-electron
    EOS, evaluated over the +-6 % volume window around the average equilibrium
    volume.
``nu`` (%)
    Weighted relative difference of (V0, B0, B1); weights 1/20 on B0 and
    1/400 on B1.
``epsilon``
    Normalised area between the two EOS curves.

The reference is the all-electron average published with the ACWF paper
(``acwf_paper_plots/code-data/results-*-verification-PBE-v1-AE-average.json``).
In addition the two candidate pseudopotentials are always compared with each
other, and ``--compare-set`` accepts further results JSON files (for instance the
published Quantum ESPRESSO/SSSP results shipped with the ACWF paper).

Usage
-----

    python 4-analyze/compute_sssp_metrics.py
    python 4-analyze/compute_sssp_metrics.py --pseudos sr
    python 4-analyze/compute_sssp_metrics.py --include-spin-orbit
    python 4-analyze/compute_sssp_metrics.py --compare-set /path/to/results-....json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import eosdata  # noqa: E402
from common import standard as std  # noqa: E402
from common import util  # noqa: E402
from common.quantities_for_comparison import get_num_atoms_in_formula_unit  # noqa: E402

METRICS = ('delta', 'nu', 'epsilon')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=sorted(config.PSEUDOS), choices=sorted(config.PSEUDOS))
    parser.add_argument('--include-spin-orbit', action='store_true')
    parser.add_argument('--set-overrides', nargs='*', default=None,
                        help='Map a pseudopotential to another results set, e.g. '
                             '`--set-overrides fr=u14ve-fr-wide-verification-PBE-v1`.')
    parser.add_argument('--compare-set', nargs='*', default=None,
                        help='Additional results JSON files to compare against, e.g. the published '
                             'results-unaries-verification-PBE-v1-quantum_espresso-SSSP-1.3-PBE-precision.json.')
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


def reference_fits() -> Dict[str, Dict[str, Any]]:
    """Return ``{system key: {'fit', 'natoms_cell', 'source'}}`` of the AE averages."""
    reference: Dict[str, Dict[str, Any]] = {}
    for filename in config.REFERENCE_FILES.values():
        path = config.REFERENCE_DATA_DIR / filename
        if not path.exists():
            print(f"  WARNING: reference file {path} not found — skipping it.")
            continue
        payload = json.loads(path.read_text())
        for key, fit in payload.get('BM_fit_data', {}).items():
            if fit is None:
                continue
            reference[key] = {
                'fit': fit,
                'natoms_cell': payload.get('num_atoms_in_sim_cell', {}).get(key),
                'source': filename,
            }
    return reference


def canonical_key(system_key: str) -> str:
    """``O2U-XO2`` -> ``U-XO2``, the convention of the published reference data."""
    _, configuration = system_key.split('-', 1)
    return f'U-{configuration}'


def results_of_set_name(key: str) -> str:
    """Set name actually used for a pseudopotential (honouring --set-overrides)."""
    return _SET_OVERRIDES.get(key) or util.set_name(key)


_SET_OVERRIDES: Dict[str, str] = {}


def load_results(name: str) -> Optional[Dict[str, Any]]:
    path = config.OUTPUTS_DIR / f'results-{name}-{util.PLUGIN_NAME}.json'
    if not path.exists():
        print(f"  WARNING: {path} not found — run 4-analyze/get_results.py first.")
        return None
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Metric evaluation
# ---------------------------------------------------------------------------


def evaluate(name: str, reference: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the three metrics of one set of results against ``reference``."""
    results = load_results(name)
    if results is None:
        return {}

    payload: Dict[str, Any] = {'set_name': name, 'systems': {}}
    for system_key, fit in sorted(results.get('BM_fit_data', {}).items()):
        if fit is None:
            continue
        natoms = results.get('num_atoms_in_sim_cell', {}).get(system_key)
        if natoms is None:
            continue

        reference_entry = reference.get(canonical_key(system_key))
        if reference_entry is None or reference_entry.get('natoms_cell') is None:
            print(f"  no reference for {system_key} — skipped")
            continue

        configuration = system_key.split('-', 1)[1]
        natoms_fu = get_num_atoms_in_formula_unit(configuration)

        reference_fit = reference_entry['fit']
        pseudo_v0 = eosdata.volume_per_formula_unit(fit, natoms, natoms_fu)
        other_v0 = eosdata.volume_per_formula_unit(reference_fit, reference_entry['natoms_cell'], natoms_fu)

        payload['systems'][system_key] = {
            'configuration': configuration,
            'class': 'unary' if configuration in config.UNARY_CONFIGURATIONS else 'oxide',
            'natoms_in_cell': natoms,
            'natoms_in_formula_unit': natoms_fu,
            'V0_pseudo': pseudo_v0,
            'V0_other': other_v0,
            'B0_pseudo': fit['bulk_modulus_ev_ang3'],
            'B0_other': reference_fit['bulk_modulus_ev_ang3'],
            'B1_pseudo': fit['bulk_deriv'],
            'B1_other': reference_fit['bulk_deriv'],
            'delta': eosdata.delta_per_atom(
                pseudo_v0, fit['bulk_modulus_ev_ang3'], fit['bulk_deriv'],
                other_v0, reference_fit['bulk_modulus_ev_ang3'], reference_fit['bulk_deriv'], natoms_fu,
            ),
            'nu': eosdata.nu_metric(
                pseudo_v0, fit['bulk_modulus_ev_ang3'], fit['bulk_deriv'],
                other_v0, reference_fit['bulk_modulus_ev_ang3'], reference_fit['bulk_deriv'],
            ),
            'epsilon': eosdata.epsilon_metric(
                pseudo_v0, fit['bulk_modulus_ev_ang3'], fit['bulk_deriv'],
                other_v0, reference_fit['bulk_modulus_ev_ang3'], reference_fit['bulk_deriv'],
            ),
        }
    return payload


def verdict(metric: str, value: float) -> str:
    criterion = std.get_criterion(metric)
    if value <= criterion['pass']:
        return 'PASS'
    if value <= criterion['good']:
        return 'acceptable'
    return 'FAIL'


def summarise(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    systems = payload.get('systems', {})
    for metric in METRICS:
        values = [entry[metric] for entry in systems.values()]
        if not values:
            continue
        summary[metric] = {
            'max': max(values),
            'mean': sum(values) / len(values),
            'worst_system': max(systems, key=lambda key: systems[key][metric]),
            # Two readings, because they answer different questions: the SSSP criteria are
            # applied to the *average* metric of a library entry, while the conservative
            # reading asks whether *every* system is inside the band. Reporting only the
            # worst case makes a candidate with excellent means look like a failure.
            'verdict': verdict(metric, max(values)),
            'verdict_mean': verdict(metric, sum(values) / len(values)),
            'passing': sum(1 for value in values if value <= std.get_criterion(metric)['pass']),
            'n_systems': len(values),
        }
        for label, configurations in (('unaries', config.UNARY_CONFIGURATIONS),
                                      ('oxides', config.OXIDE_CONFIGURATIONS)):
            subset = [entry[metric] for entry in systems.values() if entry['configuration'] in configurations]
            if subset:
                summary[metric][label] = {'max': max(subset), 'verdict': verdict(metric, max(subset))}
    return summary


def report_to_files(name: str, label: str, payload: Dict[str, Any], summary: Dict[str, Any]) -> None:
    outputs = config.OUTPUTS_DIR
    outputs.mkdir(parents=True, exist_ok=True)
    payload = {'reference': {'label': label}, **payload}
    (outputs / f'metrics-{name}.json').write_text(
        json.dumps({'summary': summary, **payload}, indent=2, sort_keys=True) + '\n'
    )
    (outputs / f'metrics-{name}.md').write_text(markdown_report(name, label, payload, summary))


def markdown_report(name: str, label: str, payload: Dict[str, Any], summary: Dict[str, Any]) -> str:
    lines = [f'# {name}', '', f'Reference: {label}', '']
    lines.append('| system | class | V0 [A^3/f.u.] | B0 [eV/A^3] | B1 | delta [meV/atom] | nu [%] | epsilon |')
    lines.append('|---|---|---|---|---|---|---|---|')
    for key, entry in sorted(payload.get('systems', {}).items()):
        lines.append(
            f"| {key} | {entry['class']} | {entry['V0_pseudo']:.3f} | {entry['B0_pseudo']:.4f} | "
            f"{entry['B1_pseudo']:.2f} | {entry['delta']:.3f} | {entry['nu']:.3f} | {entry['epsilon']:.4f} |"
        )
    lines.append('')
    lines.append('| metric | max | mean | worst system | unaries (max) | oxides (max) | '
                 'verdict (worst) | verdict (mean) | systems within pass |')
    lines.append('|---|---|---|---|---|---|---|---|---|')
    for metric in METRICS:
        values = summary.get(metric)
        if not values:
            continue
        unit = std.get_criterion(metric)['unit']
        lines.append(
            f"| {metric}{' [' + unit + ']' if unit else ''} | {values['max']:.4f} | {values['mean']:.4f} | "
            f"{values['worst_system']} | {values.get('unaries', {}).get('max', float('nan')):.4f} | "
            f"{values.get('oxides', {}).get('max', float('nan')):.4f} | {values['verdict']} | "
            f"{values.get('verdict_mean', values['verdict'])} | "
            f"{values.get('passing', '?')}/{values.get('n_systems', '?')} |"
        )
    lines.append('')
    lines.append('Criteria (configurable in `common/standard.py`): ' + '; '.join(
        f"{metric} <= {std.get_criterion(metric)['pass']} {std.get_criterion(metric)['unit']} = pass, "
        f"<= {std.get_criterion(metric)['good']} {std.get_criterion(metric)['unit']} = acceptable"
        for metric in METRICS
    ))
    return '\n'.join(lines) + '\n'


def print_payload(payload: Dict[str, Any], summary: Dict[str, Any]) -> None:
    for system_key, entry in sorted(payload.get('systems', {}).items()):
        print(f"  {system_key:<14} V0={entry['V0_pseudo']:>8.3f} A^3/f.u.  "
              f"B0={entry['B0_pseudo'] * 160.21766208:>7.1f} GPa  B1={entry['B1_pseudo']:>5.2f}  "
              f"d={entry['delta']:>7.3f} meV/atom  nu={entry['nu']:>6.3f} %  eps={entry['epsilon']:>6.4f}")
    print()
    for metric in METRICS:
        values = summary.get(metric)
        if not values:
            continue
        criterion = std.get_criterion(metric)
        print(f"  max  {metric:<8} = {values['max']:.4f} {criterion['unit']:<9} ({values['worst_system']})"
              f"  ->  {values['verdict']}   [pass <= {criterion['pass']}, "
              f"acceptable <= {criterion['good']}]")
        print(f"  mean {metric:<8} = {values['mean']:.4f} {criterion['unit']:<9}"
              f"  ->  {values.get('verdict_mean', values['verdict'])}"
              f"   ({values.get('passing', '?')}/{values.get('n_systems', '?')} systems within pass)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    util.load_profile()

    print('=' * 78)
    print('ACWF / SSSP metrics')
    print('=' * 78)

    reference = reference_fits()
    print(f"  {len(reference)} all-electron reference systems loaded from {config.REFERENCE_DATA_DIR}")
    print()

    overrides = {}
    for item in (args.set_overrides or []):
        key, _, value = item.partition('=')
        overrides[key] = value
    _SET_OVERRIDES.update(overrides)

    sets = []
    for key in args.pseudos:
        sets.append((key, False))
        if args.include_spin_orbit and config.PSEUDOS[key]['rel'] == 'full':
            sets.append((key, True))

    results_of_set = {}
    for key, spin_orbit in sets:
        name = overrides.get(key) if not spin_orbit else None
        name = name or util.set_name(key, spin_orbit=spin_orbit)
        print('-' * 78)
        print(f"{config.PSEUDOS[key]['description']}{'  [spin-orbit]' if spin_orbit else ''}")
        print(f"set: {name}")
        print('-' * 78)

        if spin_orbit:
            print('  NOTE: the all-electron reference is scalar relativistic. These numbers\n'
                  '        quantify the spin-orbit effect, they are not an accuracy statement.')

        payload = evaluate(name, reference)
        if not payload.get('systems'):
            print('  no finished EOS found for this set.')
            print()
            continue

        results_of_set[key] = load_results(name)
        summary = summarise(payload)
        print_payload(payload, summary)
        report_to_files(name, 'all-electron average (ACWF paper)', payload, summary)
        print(f"  -> {config.OUTPUTS_DIR / f'metrics-{name}.json'}")
        print(f"  -> {config.OUTPUTS_DIR / f'metrics-{name}.md'}")
        print()

    # The two candidate pseudopotentials against each other.
    keys = [key for key, spin_orbit in sets if not spin_orbit]
    if len(keys) >= 2:
        first, second = keys[0], keys[1]
        reference_payload = results_of_set.get(first)
        if reference_payload is not None:
            name = f'{results_of_set_name(second)}-vs-{results_of_set_name(first)}'
            print('-' * 78)
            print(f"{config.PSEUDOS[second]['description']}  against  {config.PSEUDOS[first]['description']}")
            print('-' * 78)
            cross_reference = {
                system_key: {
                    'fit': fit,
                    'natoms_cell': reference_payload.get('num_atoms_in_sim_cell', {}).get(system_key),
                    'source': results_of_set_name(first),
                }
                for system_key, fit in reference_payload.get('BM_fit_data', {}).items()
                if fit is not None
            }
            # `evaluate` canonicalises the key of the *other* set (O2U-XO2 -> U-XO2),
            # so the cross reference must be reachable under both spellings.
            for system_key, entry in list(cross_reference.items()):
                cross_reference.setdefault(canonical_key(system_key), entry)
            payload = evaluate(results_of_set_name(second), cross_reference)
            if payload.get('systems'):
                summary = summarise(payload)
                print_payload(payload, summary)
                report_to_files(name, f'set {results_of_set_name(first)}', payload, summary)
                print(f"  -> {config.OUTPUTS_DIR / f'metrics-{name}.json'}")
            print()

    # Additional published/custom result files.
    for path_str in (args.compare_set or []):
        path = Path(path_str)
        if not path.exists():
            print(f"  WARNING: comparison file {path} not found — skipped.")
            continue
        other = json.loads(path.read_text())
        other_reference = {
            system_key: {
                'fit': fit,
                'natoms_cell': other.get('num_atoms_in_sim_cell', {}).get(system_key),
                'source': path.name,
            }
            for system_key, fit in other.get('BM_fit_data', {}).items()
            if fit is not None
        }
        for key, spin_orbit in sets:
            name = util.set_name(key, spin_orbit=spin_orbit)
            print('-' * 78)
            print(f"{name}  against  {path.name}")
            print('-' * 78)
            payload = evaluate(name, other_reference)
            if not payload.get('systems'):
                print('  nothing to compare.')
                print()
                continue
            summary = summarise(payload)
            print_payload(payload, summary)
            report_to_files(f'{name}-vs-{path.stem}', path.name, payload, summary)
            print()

    print('Next step:  python 4-analyze/plot_ev_curves.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
