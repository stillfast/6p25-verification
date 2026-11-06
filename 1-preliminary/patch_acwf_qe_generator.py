#!/usr/bin/env python
"""OPTIONAL: repair the ACWF Quantum ESPRESSO protocol for aiida-quantumespresso 5.x.

This script is **not needed** by the workflow: ``3-submit/launch_calculations_qe.py``
pins every code-dependent input through ``sub_process`` and therefore follows the
ACWF/SSSP standard even with an untouched checkout.  It exists for two reasons.

1. **Provenance.** ``aiida-common-workflows`` 1.0 stores the
   ``verification-PBE-v1`` protocol under the namespace names ``base`` /
   ``base_final_scf``, which were renamed to ``base_relax`` / ``base_init_relax``
   in ``aiida-quantumespresso`` 5.0.  With 5.x installed those keys are reported
   as *unrecognised overrides* and ignored, so a run whose provenance says
   ``protocol='verification-PBE-v1'`` actually used the plugin defaults
   (``kpoints_distance = 0.15``, ``smearing = cold``, ``degauss = 0.02``, ...).
   Renaming the keys makes the recorded protocol self-consistent.

2. **Speed.** ``PwRelaxWorkChain`` of 5.x always runs ``base_init_relax`` — a
   second full SCF per EOS volume — when the namespace is present, which is
   pointless for ``relax_type = NONE``.  Removing it halves the cost of every
   EOS workchain.

Both edits are applied to files of the installed packages.  The script keeps a
``*.u14ve-backup`` copy next to each file and can restore it with ``--restore``.
Package upgrades overwrite the edits; nothing else in this project depends on
them.

Usage
-----

    python 1-preliminary/patch_acwf_qe_generator.py --check
    python 1-preliminary/patch_acwf_qe_generator.py --apply
    python 1-preliminary/patch_acwf_qe_generator.py --restore
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import util  # noqa: E402

BACKUP_SUFFIX = '.u14ve-backup'

#: The ACWF protocol section, rewritten with the 5.x namespace names and the
#: values of the ACWF/SSSP standard (see common/standard.py).
NEW_PROTOCOL_ENTRY = """\
verification-PBE-v1:
  description: Main protocol for the ACWF verification study - SSSP version
  # NOTE: `base_relax` / `base_init_relax` are the aiida-quantumespresso >= 5.0
  # namespace names; the upstream file uses the pre-5.0 `base` /
  # `base_final_scf` names, which 5.x silently ignores.
  # This section was repaired by u14ve-verification/1-preliminary/patch_acwf_qe_generator.py.
  base_relax:
    pseudo_family: &pseudo_family {pseudo_family}
    kpoints_distance: &kpoints_distance 0.06
    meta_parameters:
      conv_thr_per_atom: &conv_thr_per_atom 0.1e-9
      etot_conv_thr_per_atom: &etot_conv_thr_per_atom 0.5e-5
    pw:
      parameters:
        CONTROL:
          forc_conv_thr: 0.5e-4
        SYSTEM:
          smearing: &smearing fd
          degauss: &degauss 0.0045
  base_init_relax:
    pseudo_family: *pseudo_family
    kpoints_distance: *kpoints_distance
    meta_parameters:
      conv_thr_per_atom: *conv_thr_per_atom
      etot_conv_thr_per_atom: *etot_conv_thr_per_atom
    pw:
      parameters:
        CONTROL:
          forc_conv_thr: 0.5e-4
        SYSTEM:
          smearing: *smearing
          degauss: *degauss
"""

#: Patch of the generator: skip the useless pre-relaxation SCF for scf-only runs.
GENERATOR_ANCHOR = "        builder._process_class = self.process_class\n"
GENERATOR_PATCH = """        # PATCH (u14ve-verification): `base_init_relax` is a pre-relaxation SCF
        # that is useless for `relax_type = NONE` (EOS runs) and doubles the
        # cost of every image. Removing the namespace from the builder makes
        # `PwRelaxWorkChain.should_run_init_relax` return False.
        if relax_type is types.RelaxType.NONE:
            try:
                del builder.base_init_relax
            except (AttributeError, KeyError):
                pass

        builder._process_class = self.process_class
"""


def protocol_path() -> Path:
    import aiida_common_workflows.workflows.relax.quantum_espresso as module

    return Path(module.__file__).parent / 'protocol.yml'


def generator_path() -> Path:
    import aiida_common_workflows.workflows.relax.quantum_espresso.generator as module

    return Path(module.__file__)


def backup(path: Path) -> Path:
    target = path.with_name(path.name + BACKUP_SUFFIX)
    if not target.exists():
        shutil.copyfile(path, target)
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='Report the current state, change nothing.')
    group.add_argument('--apply', action='store_true', help='Apply the patch (idempotent).')
    group.add_argument('--restore', action='store_true', help='Restore the original files from the backups.')
    parser.add_argument('--pseudo-family',
                        default=config.PSEUDOS[sorted(config.PSEUDOS)[0]]['family'],
                        help='pseudo_family written into the protocol (default: the family of the '
                             'pseudopotential under test).')
    return parser.parse_args()


def check() -> int:
    path = protocol_path()
    text = path.read_text()
    broken = '  base:\n' in text or '\n  base:\n' in text
    print(f"  protocol.yml : {path}")
    print(f"    uses pre-5.0 namespace names `base` / `base_final_scf` : {broken}")
    print(f"    backup present                                       : {path.with_name(path.name + BACKUP_SUFFIX).exists()}")

    gen = generator_path()
    gtext = gen.read_text()
    patched = 'base_init_relax' in gtext and 'del builder.base_init_relax' in gtext
    print(f"  generator.py : {gen}")
    print(f"    pre-relaxation SCF removed for scf runs              : {patched}")
    return 0


def apply_patch(args) -> int:
    path = protocol_path()
    lines = path.read_text().splitlines(keepends=True)

    start = None
    others = []
    for index, line in enumerate(lines):
        if line.startswith('verification-PBE-v1:'):
            start = index
            continue
        if start is None and line.strip() and not line[0].isspace():
            others.append(line.strip())

    if start is None:
        print(f"  ERROR: no `verification-PBE-v1:` section in {path}", file=sys.stderr)
        return 1
    if others:
        print(f"  ERROR: {path} contains other top-level protocols ({others}); the anchors used by")
        print('         this patch would break them. Refusing to patch.')
        return 1

    backup(path)
    path.write_text(''.join(lines[:start]) + NEW_PROTOCOL_ENTRY.format(pseudo_family=args.pseudo_family))
    print(f"  patched {path}")
    print(f"    backup: {path.with_name(path.name + BACKUP_SUFFIX)}")

    gen = generator_path()
    gtext = gen.read_text()
    if 'del builder.base_init_relax' in gtext:
        print(f"  {gen} already patched")
    elif GENERATOR_ANCHOR in gtext:
        backup(gen)
        gen.write_text(gtext.replace(GENERATOR_ANCHOR, GENERATOR_PATCH, 1))
        print(f"  patched {gen}")
        print(f"    backup: {gen.with_name(gen.name + BACKUP_SUFFIX)}")
    else:
        print(f"  WARNING: anchor not found in {gen}; the pre-relaxation SCF is kept.")
        print('           The workflow is still correct (the cutoffs, k-points and thresholds are')
        print('           pinned by sub_process), it just runs one extra SCF per EOS image.')
    return 0


def restore() -> int:
    for path in (protocol_path(), generator_path()):
        target = path.with_name(path.name + BACKUP_SUFFIX)
        if target.exists():
            shutil.copyfile(target, path)
            print(f"  restored {path} from {target}")
        else:
            print(f"  no backup for {path} — nothing restored")
    return 0


def main() -> int:
    args = parse_args()
    if not args.check:
        util.load_profile()
    if args.check:
        return check()
    if args.restore:
        return restore()
    return apply_patch(args)


if __name__ == '__main__':
    sys.exit(main())
