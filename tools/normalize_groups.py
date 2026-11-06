#!/usr/bin/env python
"""Keep exactly one successful EOS workchain per system in every AiiDA group.

Re-submitting a batch can leave several workchains for the same
``(element, configuration)`` in a group, and failed or killed attempts stay there
as well.  The analysis reads the group, so the group must be normalised first:
this tool removes every EOS node that did not finish successfully, and then keeps
only the most recent successful one per system.

Removed nodes stay in the AiiDA database — only their group membership changes.

Usage
-----

    python tools/normalize_groups.py --dry-run
    python tools/normalize_groups.py

    # the cutoff-convergence groups of the same set (see --convergence below)
    python tools/normalize_groups.py --convergence --dry-run
    python tools/normalize_groups.py --convergence
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import util  # noqa: E402

EOS_PROCESS_TYPE = 'aiida.workflows:common_workflows.eos'


def configured_sets(args) -> list:
    """``[(label, set name)]`` to normalise.

    Built from ``config.PSEUDOS`` so that a project with a different (or single) candidate
    works unchanged; the u14ve project used to hardcode its own key list here, which broke
    the sibling project. ``--set-tag`` selects one tagged variant set per pseudopotential
    (the same convention as the launcher).
    """
    if args.set_names:
        return [(name, name) for name in args.set_names]
    names = []
    for key in sorted(config.PSEUDOS):
        suffix = f'{args.set_tag}-verification-PBE-v1' if args.set_tag else None
        names.append((f'{key}-{args.set_tag}' if args.set_tag else key,
                      util.set_name(key, suffix=suffix)))
        if not args.set_tag and config.PSEUDOS[key]['rel'] == 'full':
            names.append((f'{key}-soc', util.set_name(key, spin_orbit=True)))
    return names


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--set-tag', default=None,
                        help='Normalise this tagged variant set (e.g. `ecut200` for the set '
                             '`<prefix>-<key>-ecut200-verification-PBE-v1`) instead of the '
                             'production sets.')
    parser.add_argument('--set-names', nargs='+', default=None,
                        help='Explicit set names to normalise, overriding everything else.')
    parser.add_argument('--convergence', action='store_true',
                        help='Normalise the cutoff-convergence groups '
                             '(`.../convergence/<plugin>/ecut-*-dual-*`) instead of the '
                             'production workflows group. A killed EOS node keeps its group '
                             'membership, and the scan controller counts group membership '
                             'rather than process state — so such a node silently blocks its '
                             'cutoff point and structure from ever being submitted again. This '
                             'mode drops the membership of every node that is not the newest '
                             'successful one per system, which is what the controller needs.')
    parser.add_argument('--failed-only', action='store_true',
                        help='Remove only terminally failed EOS nodes and keep every other node, '
                             'including workchains that are still running. Use this in the middle '
                             'of a campaign: the default mode would also drop running nodes.')
    return parser.parse_args()


def convergence_groups(name: str) -> list:
    """Every convergence cutoff group of a set, ordered by cutoff."""
    from aiida import orm

    prefix = util.convergence_group_label(name, 0, 0).rsplit('/', 1)[0] + '/'
    groups = [group for group in orm.QueryBuilder().append(orm.Group).all(flat=True)
              if group.label.startswith(prefix)]
    return sorted(groups, key=lambda group: util.parse_convergence_group_label(group.label) or (0, 0))


def normalize_group(group, name: str, args, show_always: bool = False) -> tuple:
    """Drop the group membership of every EOS node that must not be counted."""
    eos_nodes = [n for n in group.nodes if n.process_type == EOS_PROCESS_TYPE]
    label = group.label.split('/', 1)[-1] if show_always else name

    if args.failed_only:
        removed = 0
        for node in eos_nodes:
            if node.is_finished and not node.is_finished_ok:
                print(f'   - remove pk={node.pk} {node.base.extras.get("system", "?")} '
                      f'state={node.process_state} exit={node.exit_status}')
                if not args.dry_run:
                    group.remove_nodes([node])
                removed += 1
        print(f'{label}: {len(eos_nodes)} EOS node(s) -> removed {removed} failed')
        return len(eos_nodes), removed

    by_system = defaultdict(list)
    for node in eos_nodes:
        try:
            by_system[util.structure_key(node.inputs.structure)].append(node)
        except Exception:  # noqa: BLE001
            continue

    keep, drop = [], []
    for system, nodes in by_system.items():
        successful = [n for n in nodes if n.is_finished_ok]
        if successful:
            successful.sort(key=lambda n: n.pk)
            keep.append(successful[-1])
            drop.extend(n for n in nodes if n is not successful[-1])
        else:
            drop.extend(nodes)

    print(f'{label}: {len(eos_nodes)} EOS node(s) over {len(by_system)} system(s) '
          f'-> keep {len(keep)}, remove {len(drop)}')
    for node in sorted(drop, key=lambda n: n.pk):
        try:
            key = util.structure_key(node.inputs.structure)
        except Exception:  # noqa: BLE001
            key = '?'
        print(f'   - remove pk={node.pk} {key} state={node.process_state.value} '
              f'exit={node.exit_status}')
    if drop and not args.dry_run:
        group.remove_nodes(drop)
    return len(eos_nodes), len(drop)


def main() -> int:
    args = parse_args()
    util.load_profile()

    for _label, set_name in configured_sets(args):
        name = set_name
        if args.convergence:
            groups = convergence_groups(name)
            if not groups:
                print(f'{name}: no convergence group found — skipped')
                continue
            total = removed = 0
            for group in groups:
                count, gone = normalize_group(group, name, args, show_always=True)
                total += count
                removed += gone
            print(f'{name}: {len(groups)} convergence group(s), {total} EOS node(s) '
                  f'-> dropped membership of {removed}')
            continue

        try:
            group = __import__('aiida').orm.load_group(util.workflows_group_label(name))
        except Exception:  # noqa: BLE001
            print(f'{name}: group not found — skipped')
            continue
        normalize_group(group, name, args)

    if args.dry_run:
        print('\nDRY RUN: nothing changed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
