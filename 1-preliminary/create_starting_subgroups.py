#!/usr/bin/env python
"""Populate the ACWF structure sub-groups of this project.

The published *uranium-verification-PBE-v1* structures are already imported into
AiiDA (see :data:`config.SOURCE_STRUCTURES_GROUP`).  This script copies them into
the per-pseudopotential sub-group that the submission controller reads::

    acwf-verification/u14ve-sr-verification-PBE-v1/structures/quantum_espresso
    acwf-verification/u14ve-fr-verification-PBE-v1/structures/quantum_espresso
    acwf-verification/u14ve-fr-soc-verification-PBE-v1/structures/quantum_espresso   (optional)

These are the *same* StructureData nodes (no duplication, no re-import), so the
structures stay identical across the two pseudopotentials — a prerequisite for a
meaningful comparison.

Usage
-----

    python 1-preliminary/create_starting_subgroups.py [--configurations X/BCC XO2 ...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import util  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--configurations',
        nargs='+',
        default=list(getattr(config, 'VERIFICATION_CONFIGURATIONS', config.ALL_CONFIGURATIONS)),
        help=(
            'Subset of configurations to put in the group '
            f"(default: this project verifies "
            f"{list(getattr(config, 'VERIFICATION_CONFIGURATIONS', config.ALL_CONFIGURATIONS))}; "
            f"all ten available are {list(config.ALL_CONFIGURATIONS)})."
        ),
    )
    parser.add_argument(
        '--no-soc',
        action='store_true',
        help='Do not create the spin-orbit structure group of the fully relativistic pseudo.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    util.load_profile()

    from aiida import orm

    available = util.source_structures()
    print(f"Source group '{config.SOURCE_STRUCTURES_GROUP}': {len(available)} structure(s)")

    selected = util.filter_structures(available, args.configurations)
    if not selected:
        print('ERROR: no structure selected.', file=sys.stderr)
        return 1

    print(f"Selected {len(selected)} structure(s):")
    for node in selected:
        print(f"  {util.structure_key(node):<14} pk={node.pk:<7} natoms={len(node.sites):<3} "
              f"kinds={node.get_kind_names()}")

    labels = [(key, spin_orbit) for key in config.PSEUDOS
              for spin_orbit in ((False, True) if (config.PSEUDOS[key]['rel'] == 'full' and not args.no_soc)
                                 else (False,))]
    print()
    for key, spin_orbit in labels:
        name = util.set_name(key, spin_orbit=spin_orbit)
        label = util.structures_group_label(name)
        group, created = orm.Group.collection.get_or_create(label=label)
        group.add_nodes(selected)
        print(f"  {'created' if created else 'updated'} {label}: {len(group.nodes)} node(s)")

    print()
    print('Next step:  python 1-preliminary/verify_setup.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
