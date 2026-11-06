#!/usr/bin/env python
"""Import the ten ACWF uranium verification structures shipped with this repo.

The archive in ``data/structures/`` is an AiiDA export of the group
``acwf-verification/uranium-verification-PBE-v1/structures/quantum_espresso``
(the four unaries and six oxides used by this project). Importing it once is
enough; the script is a no-op when the group already exists.

Usage
-----

    conda activate aiida
    python 1-preliminary/import_structures.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import util  # noqa: E402

ARCHIVE = PROJECT_ROOT / 'data' / 'structures' / 'uranium-verification-PBE-v1_structures.aiida'


def main() -> int:
    util.load_profile()

    from aiida import orm
    from aiida.common.exceptions import NotExistent

    try:
        group = orm.load_group(config.SOURCE_STRUCTURES_GROUP)
    except NotExistent:
        group = None

    if group is not None:
        print(f"group already present: {config.SOURCE_STRUCTURES_GROUP} ({len(group.nodes)} nodes)")
        return 0

    if not ARCHIVE.is_file():
        raise SystemExit(f'ERROR: missing structure archive: {ARCHIVE}')

    subprocess.run(['verdi', 'archive', 'import', str(ARCHIVE)], check=True)
    print(f"imported: {config.SOURCE_STRUCTURES_GROUP}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
