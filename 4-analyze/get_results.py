#!/usr/bin/env python
"""Collect the EOS results of one (or all) sets into official-format JSON files.

The output layout is the one of
``acwf-verification-scripts/3-analyze/get_results.py``::

    outputs/results-<set>-<plugin>.json
    outputs/warnings-<set>-<plugin>.txt

so the files can also be fed to the official plotting/analysis scripts.

Usage
-----

    python 4-analyze/get_results.py                     # all sets that exist
    python 4-analyze/get_results.py --pseudos sr
    python 4-analyze/get_results.py --sets u14ve-fr-soc-verification-PBE-v1
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import eosdata  # noqa: E402
from common import util  # noqa: E402

#: Bumped whenever this script or the fit changes; the official consumers use it
#: to detect stale JSON files.
SCRIPT_VERSION = '0.0.4'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=None, choices=sorted(config.PSEUDOS))
    parser.add_argument('--sets', nargs='+', default=None,
                        help='Explicit set names (overrides --pseudos).')
    parser.add_argument('--include-spin-orbit', action='store_true',
                        help='Also process the spin-orbit sets of the fully relativistic pseudo.')
    parser.add_argument('--fill-from', default=None,
                        help='Fallback set name: systems without a successful EOS in the primary set '
                             'are taken from this set. Used for the fully relativistic '
                             'pseudopotential, whose unary EOS needs a wider volume window while its '
                             'oxides are fine in the standard window.')
    return parser.parse_args()


def wanted_sets(args) -> list:
    if args.sets:
        return list(args.sets)
    keys = args.pseudos or sorted(config.PSEUDOS)
    names = []
    for key in keys:
        names.append(util.set_name(key))
        if args.include_spin_orbit and config.PSEUDOS[key]['rel'] == 'full':
            names.append(util.set_name(key, spin_orbit=True))
    return names


def _successful_eos(group_label: str) -> dict:
    """Return ``{system key: EOS workchain}`` of the successful runs of a group."""
    from aiida import orm

    try:
        group = orm.load_group(group_label)
    except Exception:  # noqa: BLE001
        return {}

    result = {}
    for node in group.nodes:
        if node.process_type != 'aiida.workflows:common_workflows.eos' or not node.is_finished_ok:
            continue
        try:
            result[util.structure_key(node.inputs.structure)] = node
        except Exception:  # noqa: BLE001
            continue
    return result


def process_set(name: str, fill_from: Optional[str] = None) -> dict:
    from aiida import orm

    label = util.workflows_group_label(name)
    try:
        group = orm.load_group(label)
    except Exception:  # noqa: BLE001
        return {'error': f"group '{label}' does not exist"}

    wf_nodes = [node for node in group.nodes
                if node.process_type == 'aiida.workflows:common_workflows.eos']

    if fill_from:
        primary = _successful_eos(label)
        fallback = _successful_eos(util.workflows_group_label(fill_from))
        for system, node in fallback.items():
            if system not in primary:
                wf_nodes.append(node)
                print(f"  {system}: taken from the fallback set '{fill_from}'")

    states = []
    uuid_mapping = {}
    all_missing_outputs = {}
    completely_off = []
    failed_wfs = []
    all_eos_data = {}
    all_stress_data = {}
    all_bm_fit_data = {}
    num_atoms_in_sim_cell = {}
    warning_lines = []

    for node in sorted(wf_nodes, key=lambda item: item.pk):
        structure = node.inputs.structure
        element = structure.base.extras.get('element')
        configuration = structure.base.extras.get('configuration')
        key = f'{element}-{configuration}'
        uuid_mapping[key] = {'structure': structure.uuid, 'eos_workflow': node.uuid}

        state = node.process_state.value
        if state == 'finished':
            state = f'{state}.{node.exit_status}'
        states.append(state)

        payload = eosdata.eos_payload(node)

        if not payload['eos_data']:
            if payload['state'] in ('excepted',) or (payload['state'] == 'finished' and payload['exit_status']):
                failed_wfs.append({
                    'element': element,
                    'configuration': configuration,
                    'process_state': payload['state'],
                    'exit_status': payload['exit_status'],
                    'pk': node.pk,
                })
            all_eos_data[key] = None
            all_stress_data[key] = None
            all_bm_fit_data[key] = None
            num_atoms_in_sim_cell[key] = payload['num_atoms_in_sim_cell']
            continue

        if payload['missing_outputs']:
            all_missing_outputs[key] = payload['missing_outputs']
            warning_lines.append(
                f"WARNING! MISSING OUTPUTS: {payload['missing_outputs']} for {key}"
            )
        if payload['completely_off']:
            completely_off.append({'element': element, 'configuration': configuration,
                                   'side': payload['completely_off']})
        fit = payload['BM_fit_data']
        if fit is None:
            warning_lines.append(f"WARNING! Unable to fit {key}")
        elif fit['residuals'] > 1.0e-3:
            warning_lines.append(f"WARNING! High fit residuals: {fit['residuals']} for {key}")

        all_eos_data[key] = payload['eos_data']
        all_stress_data[key] = None
        all_bm_fit_data[key] = fit
        num_atoms_in_sim_cell[key] = payload['num_atoms_in_sim_cell']

    good = len([value for value in all_eos_data.values() if value is not None])
    warning_lines.append('')
    warning_lines.append('Counter of states: ' + str(Counter(states)))
    warning_lines.append('')
    warning_lines.append(f'Minimum completely off for {len(completely_off)}/{good}')
    for entry in completely_off:
        warning_lines.append(
            f"- {entry['element']} {entry['configuration']} "
            f"({'<' if entry['side'] == 'left' else '>'})"
        )

    data = {
        'script_version': SCRIPT_VERSION,
        'set_name': name,
        'uuid_mapping': uuid_mapping,
        'failed_wfs': failed_wfs,
        'missing_outputs': all_missing_outputs,
        'completely_off': completely_off,
        'eos_data': all_eos_data,
        'stress_data': all_stress_data,
        'BM_fit_data': all_bm_fit_data,
        'num_atoms_in_sim_cell': num_atoms_in_sim_cell,
    }

    outputs = config.OUTPUTS_DIR
    outputs.mkdir(parents=True, exist_ok=True)
    results_path = outputs / f'results-{name}-{util.PLUGIN_NAME}.json'
    warnings_path = outputs / f'warnings-{name}-{util.PLUGIN_NAME}.txt'

    results_path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    warnings_path.write_text('\n'.join(warning_lines) + '\n')

    print(f"  set '{name}': {len(wf_nodes)} EOS workchain(s), {good} fitted")
    for line in warning_lines:
        print(f"    {line}")
    print(f"    -> {results_path}")
    print(f"    -> {warnings_path}")
    return data


def main() -> int:
    args = parse_args()
    util.load_profile()

    print('=' * 78)
    print('Collecting EOS results')
    print('=' * 78)

    exit_code = 0
    for name in wanted_sets(args):
        result = process_set(name, fill_from=args.fill_from)
        if 'error' in result:
            print(f"  set '{name}': {result['error']}")
            exit_code = 1
        elif 'empty' in result:
            print(f"  set '{name}': {result['empty']} — nothing written")

    print()
    print('Next step:  python 4-analyze/compute_sssp_metrics.py')
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
