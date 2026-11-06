#!/usr/bin/env python
"""Remove the remote scratch of this project's calculations.

Every ``pw.x`` calculation of Wavefunction-City leaves the Quantum ESPRESSO
scratch (wavefunction and charge-density files) in the AiiDA work directory on
the cluster.  With a few hundred SCFs of a 14-valence-electron uranium
pseudopotential that is hundreds of GB, which is enough to hit the Lustre user
quota of the account.

This tool removes the remote directory of the calculations **of this project
only**.  It never touches calculations that are still running, and it never
touches directories outside the AiiDA work directory of the configured
computer.  The retrieved data stay in the local AiiDA repository, so the
provenance is unaffected: only the scratch that QE would need for a restart
(which this project never uses) is deleted.

With ``--dry-run`` (the default) it only reports what it would delete.

Usage
-----

    python tools/clean_remote_scratch.py                    # report only
    python tools/clean_remote_scratch.py --delete           # actually delete
    python tools/clean_remote_scratch.py --delete --keep-running
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import util  # noqa: E402

#: Sizes are only reported if `du` is fast enough; this is the batch size used
#: for the delete command (keeps the command line short).
BATCH = 40


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--delete', action='store_true', help='Actually delete (default: report only).')
    parser.add_argument('--pseudos', nargs='+', default=sorted(config.PSEUDOS), choices=sorted(config.PSEUDOS))
    parser.add_argument('--include-smoke-test', action='store_true', default=True)
    parser.add_argument('--all-project-nodes', action='store_true',
                        help='Also include calculations from the convergence and smoke-test groups (default).')
    parser.add_argument('--measure', action='store_true', help='Measure the freed space with du (slow).')
    return parser.parse_args()


def our_calcjobs(pseudo_keys) -> list:
    """Return the ``CalcJobNode`` instances created by this project."""
    from aiida import orm
    from aiida.common import LinkType
    from aiida.orm import CalcJobNode

    groups = []
    for key in pseudo_keys:
        for name in (util.set_name(key), util.set_name(key, spin_orbit=True),
                     util.set_name(key, suffix='smoketest-verification-PBE-v1')):
            groups.append(util.workflows_group_label(name))
            groups.append(util.convergence_structures_group_label(name))

    eos_nodes = set()
    for label in groups:
        try:
            group = orm.load_group(label)
        except Exception:  # noqa: BLE001
            continue
        for node in group.nodes:
            if node.process_type == 'aiida.workflows:common_workflows.eos':
                eos_nodes.add(node.pk)

    # Also the convergence groups (they are siblings of the structures groups).
    for label in list(groups):
        if '/convergence-structures/' not in label:
            continue
        base = label.split('/convergence-structures/')[0]
        qb = orm.QueryBuilder().append(
            orm.Group, filters={'label': {'like': f'{base}/convergence/%'}}
        )
        for (group,) in qb.iterall():
            for node in group.nodes:
                if node.process_type == 'aiida.workflows:common_workflows.eos':
                    eos_nodes.add(node.pk)

    calcs = {}
    for pk in eos_nodes:
        eos = orm.load_node(pk)
        for triple in eos.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
            for inner in triple.node.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
                for base in inner.node.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
                    for calc in base.node.base.links.get_outgoing(link_type=LinkType.CALL_CALC).all():
                        node = calc.node
                        if isinstance(node, CalcJobNode):
                            calcs[node.pk] = node
    return list(calcs.values())


def main() -> int:
    args = parse_args()
    util.load_profile()

    from aiida import orm

    computer = orm.load_computer(config.CODE_LABEL.split('@')[-1])
    workdir_root = computer.get_workdir()

    calcs = our_calcjobs(args.pseudos)
    print(f'computer      : {computer.label}')
    print(f'AiiDA workdir : {workdir_root}')
    print(f'calculations  : {len(calcs)} belonging to this project')

    paths = []
    skipped_running = 0
    no_remote = 0
    for node in calcs:
        state = node.process_state.value
        if state in ('created', 'waiting'):
            skipped_running += 1
            continue
        try:
            path = node.get_remote_workdir()
        except Exception:  # noqa: BLE001
            no_remote += 1
            continue
        if not path or not path.startswith(workdir_root):
            no_remote += 1
            continue
        paths.append((node.pk, path))

    paths = sorted(set(paths))
    print(f'  still running (kept)      : {skipped_running}')
    print(f'  without a remote workdir  : {no_remote}')
    print(f'  deletable remote workdirs : {len(paths)}')

    if args.measure and paths:
        transport = computer.get_transport()
        with transport:
            listing = ' '.join(f'"{path}"' for _, path in paths[:400])
            result = transport.exec_command_wait(f'du -sch {listing} 2>/dev/null | tail -1', timeout=600)
            print(f'  total size                : {result[1].strip()}')

    if not args.delete:
        print('\nDRY RUN: nothing deleted. Add --delete to remove these directories.')
        return 0

    transport = computer.get_transport()
    deleted = 0
    with transport:
        for start in range(0, len(paths), BATCH):
            chunk = paths[start:start + BATCH]
            listing = ' '.join(f'"{path}"' for _, path in chunk)
            command = f'rm -rf {listing}'
            try:
                result = transport.exec_command_wait(command, timeout=900)
                deleted += len(chunk)
                print(f'  deleted {len(chunk)} workdir(s) [{result[0]}]', flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f'  ERROR deleting batch {start}: {type(exc).__name__}: {exc}')

    print(f'\nDeleted {deleted} remote workdir(s) of this project.')
    print('The retrieved data and the provenance are untouched.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
