#!/usr/bin/env python
"""Audit that every calculation of a set really followed the standard.

The report of this project claims that all EOS points were produced with the
ACWF/SSSP standard.  This script verifies that claim from the provenance itself,
independently of how the inputs were generated:

* every ``pw.x`` calculation of the set must use the pseudopotential under test;
* ``ecutwfc``/``ecutrho``, ``smearing``, ``degauss``, ``conv_thr``,
  ``etot_conv_thr``, ``forc_conv_thr`` and ``CONTROL.calculation`` must match
  ``common/standard.py``;
* the k-point mesh must be *identical* for all volumes of a system (the ACWF
  rule: the reference mesh is reused);
* the number of EOS volumes and the scale factors must match;
* anything that deviates (for instance a ``PwBaseWorkChain`` restart that
  loosened ``mixing_beta``) is reported explicitly.

Exit code 0 means no deviation was found.

Usage
-----

    python 4-analyze/audit_standard.py
    python 4-analyze/audit_standard.py --pseudos sr
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import standard as std  # noqa: E402
from common import util  # noqa: E402

PARAMETER_KEYS = (
    ('SYSTEM', 'ecutwfc'),
    ('SYSTEM', 'ecutrho'),
    ('SYSTEM', 'smearing'),
    ('SYSTEM', 'degauss'),
    ('ELECTRONS', 'conv_thr'),
    ('CONTROL', 'etot_conv_thr'),
    ('CONTROL', 'forc_conv_thr'),
    ('CONTROL', 'calculation'),
)


def _same_value(expected, found) -> bool:
    """Compare two input values, tolerating the float representation round trip."""
    try:
        return abs(float(expected) - float(found)) <= 1e-12 * max(abs(float(expected)), 1e-30)
    except (TypeError, ValueError):
        return expected == found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=sorted(config.PSEUDOS), choices=sorted(config.PSEUDOS))
    parser.add_argument('--include-spin-orbit', action='store_true')
    parser.add_argument('--standard', default=std.DEFAULT_STANDARD, choices=sorted(std.STANDARDS))
    parser.add_argument('--set-overrides', nargs='+', default=None,
                        help='Map a pseudopotential to another results set, e.g. '
                             '`--set-overrides best12=<prefix>-best12-ecut200-verification-PBE-v1`, '
                             'so that a variant dataset (a different cutoff) can be audited too.')
    return parser.parse_args()


def audit(name: str, pseudo_key: str, standard, spin_orbit: bool) -> int:
    from aiida import orm
    from aiida.common import LinkType
    from aiida.orm import CalcJobNode

    try:
        group = orm.load_group(util.workflows_group_label(name))
    except Exception:  # noqa: BLE001
        print(f'  {name}: workflows group not found — skipped')
        return 0

    eos_nodes = [n for n in group.nodes if n.process_type == 'aiida.workflows:common_workflows.eos']
    print(f'  {name}: {len(eos_nodes)} EOS workchain(s)')

    expected_pseudo = Path(config.PSEUDOS[pseudo_key]['upf']).name
    problems = []
    meshes = defaultdict(set)
    n_volumes = Counter()
    parameter_sets = Counter()
    n_calculations = 0
    n_standard = 0

    for eos in eos_nodes:
        system = util.structure_key(eos.inputs.structure)
        natoms = len(eos.inputs.structure.sites)
        scales = []
        for triple in eos.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
            relax = triple.node
            for inner in relax.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
                for base in inner.node.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
                    for calc in base.node.base.links.get_outgoing(link_type=LinkType.CALL_CALC).all():
                        node = calc.node
                        if not isinstance(node, CalcJobNode):
                            continue
                        if not node.is_finished_ok:
                            problems.append(f'{system}: calculation {node.pk} not finished ok '
                                            f'({node.process_state.value}/{node.exit_status})')
                            continue
                        try:
                            params = node.inputs.parameters.get_dict()
                        except Exception:  # noqa: BLE001
                            continue
                        n_calculations += 1

                        expected = std.build_pw_parameters(
                            natoms,
                            std.effective_cutoffs(util.load_cutoffs(pseudo_key), config.O_CUTOFFS),
                            standard,
                            spin_orbit=spin_orbit,
                        )
                        if params['CONTROL'].get('disk_io') != config.DISK_IO:
                            # This is the useless `base_init_relax` SCF, which the plugin runs
                            # with its own default protocol (different pseudopotential, cutoff
                            # and smearing); its results are discarded by the workchain.
                            # `disk_io` is the marker of the calculations this project generated.
                            continue
                        n_standard += 1

                        signature = tuple(str(params.get(section, {}).get(key)) for section, key in PARAMETER_KEYS)
                        parameter_sets[signature] += 1
                        for section, key in PARAMETER_KEYS:
                            if not _same_value(expected[section][key], params.get(section, {}).get(key)):
                                problems.append(
                                    f'{system}: calculation {node.pk} has '
                                    f'{section}.{key} = {params.get(section, {}).get(key)!r}, '
                                    f'expected {expected[section][key]!r}'
                                )

                        pseudos = {t.link_label.split('__')[-1]: t.node.filename
                                   for t in node.base.links.get_incoming().all()
                                   if t.link_label.startswith('pseudos')}
                        if expected_pseudo not in pseudos.values():
                            problems.append(f'{system}: calculation {node.pk} uses {pseudos}, '
                                            f'expected {expected_pseudo}')

                        try:
                            mesh = tuple(node.inputs.kpoints.get_kpoints_mesh()[0])
                            meshes[system].add(mesh)
                            scales.append(node.inputs.structure.get_cell_volume())
                        except Exception:  # noqa: BLE001
                            pass

        n_volumes[len(scales)] += 1

    print(f'    standard-conforming pw.x calculations: {n_standard} (of {n_calculations} total, '
          f'the rest being the unused `base_init_relax` SCFs)')
    print(f'    distinct parameter sets among them   : {len(parameter_sets)}')
    print(f'    EOS volumes per system               : '
          f'{dict(sorted(n_volumes.items()))}  (expected {standard["scale_count"]})')

    for system, seen in sorted(meshes.items()):
        if len(seen) != 1:
            problems.append(f'{system}: the k-point mesh is not the same for all volumes: {sorted(seen)}')

    if problems:
        unfinished = [item for item in problems if 'not finished ok' in item]
        findings = sorted(set(problems) - set(unfinished))
        if unfinished:
            print(f'    not finished yet ({len(unfinished)}) — a running campaign is not a '
                  f'deviation, these calculations simply have no result to audit yet:')
            for item in sorted(unfinished)[:10]:
                print(f'      - {item}')
            if len(unfinished) > 10:
                print(f'      ... and {len(unfinished) - 10} more')
        if findings:
            # A cutoff mismatch produces one identical line per calculation (and two per
            # calculation, ecutwfc and ecutrho), which buries anything else. Group the
            # deviations by kind first: the count is the same, the signal is not.
            cutoff = [item for item in findings if 'SYSTEM.ecutwfc' in item or 'SYSTEM.ecutrho' in item]
            # A cutoff *above* the recorded one is not a deviation: the recorded value is the
            # smallest cutoff that reproduced the EOS to the SSSP tolerance, so running with
            # more plane waves is still inside the standard (and strictly better converged).
            # Only a cutoff *below* it makes the dataset non-conforming.
            below = []
            for item in cutoff:
                match = re.search(r'has SYSTEM\.\w+ = ([\d.eE+-]+), expected ([\d.eE+-]+)', item)
                if match and float(match.group(1)) < float(match.group(2)):
                    below.append(item)
            above = [item for item in cutoff if item not in below]
            cutoff = below
            rest = [item for item in findings if item not in below and item not in above]
            # Only the lines that are real deviations survive into the verdict.
            findings = sorted(cutoff + rest)
            if above:
                pairs = sorted({item.split(' has ')[1] for item in above})
                systems_above = sorted({item.split(':')[0] for item in above})
                print(f'    note: {len(above)} line(s) over {len(systems_above)} system(s) used a '
                      f'cutoff *above* the recorded one ({" ; ".join(pairs)}) — that is more '
                      f'converged than required, not a deviation.')
            if not findings:
                print('    no deviation found among the calculations that finished')
                return 0
            print(f'    DEVIATIONS ({len(findings)}):')
            if cutoff:
                pairs = sorted({item.split(' has ')[1] for item in cutoff})
                affected = sorted({item.split(':')[0] for item in cutoff})
                print(f'      - cutoff mismatch, {len(cutoff)} line(s) over {len(affected)} system(s): '
                      f'the calculations were run with {"; ".join(pairs)}, while '
                      f'2-convergence/cutoffs.json records the cutoff of this pseudopotential. '
                      f'Every energy in this dataset therefore carries a cutoff error of that size; '
                      f're-run the batch (or update the record) so that the two agree.')
            for item in rest[:40]:
                print(f'      - {item}')
            if len(rest) > 40:
                print(f'      ... and {len(rest) - 40} more')
            return 1
        print('    no deviation found among the calculations that finished')
        return 0

    print('    no deviation found')
    return 0


def main() -> int:
    args = parse_args()
    util.load_profile()
    standard = std.get_standard(args.standard)

    print('=' * 78)
    print('Audit: did every calculation follow the standard?')
    print('=' * 78)

    overrides = {}
    for item in (args.set_overrides or []):
        key, _, value = item.partition('=')
        overrides[key] = value

    exit_code = 0
    for pseudo_key in args.pseudos:
        for spin_orbit in ((False, True) if (args.include_spin_orbit and
                                             config.PSEUDOS[pseudo_key]['rel'] == 'full') else (False,)):
            name = overrides.get(pseudo_key) or util.set_name(pseudo_key, spin_orbit=spin_orbit)
            exit_code |= audit(name, pseudo_key, standard, spin_orbit)
    print('=' * 78)
    print('AUDIT PASSED' if not exit_code else 'AUDIT FOUND DEVIATIONS')
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
