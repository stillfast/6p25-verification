#!/usr/bin/env python
"""Upload the uranium pseudopotential under test and build its family.

What this script does
---------------------

1. Uploads ``U.UPF`` (OPIUM route, 12 valence electrons, scalar-relativistic)
   plus the norm-conserving oxygen pseudopotential used for the oxide systems.
2. Creates one ``CutoffsPseudoPotentialFamily`` per uranium pseudopotential,
   each containing ``U`` (the candidate) and ``O`` (the shared NC oxygen), with
   explicit recommended cutoffs.
3. Adds every pseudopotential to an ``acwf-verification/<set>/pseudo/...``
   documentation group, mirroring the layout of ``acwf-verification-scripts``.
4. Checks that the pseudo family used by the ACWF Quantum ESPRESSO input
   generator for its first pass exists (see the note below).

Why the oxygen pseudopotential must be norm conserving
------------------------------------------------------

Mixing a norm-conserving uranium pseudo with a PAW/ultrasoft oxygen pseudo would
make the delta/nu/epsilon comparison against the all-electron reference
meaningless, so the oxygen pseudopotential is required to be NC as well
(``O_ONCV_PBE-1.0.upf`` by default).

Note on the ACWF input generator
--------------------------------

The ACWF EOS workchain builds its sub-process with the code-agnostic input
generator, which always resolves a ``pseudo_family`` before our overrides are
merged in.  That family only has to *exist* and to contain the elements of the
structure; the actual pseudopotential used in every calculation is pinned by
``sub_process.base_relax.pw.pseudos`` (see ``common/util.py``).  This script
reports the family that the generator will resolve and, with
``--fix-generator-family``, can create it when it is missing.

Usage
-----

    conda activate aiida
    python 1-preliminary/install_pseudos.py                 # report only
    python 1-preliminary/install_pseudos.py --fix-generator-family
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
        '--fix-generator-family',
        action='store_true',
        help=(
            'Create the pseudo family that the ACWF input generator resolves by default, '
            'if it is missing. It is created from the U pseudo under test + O.'
        ),
    )
    return parser.parse_args()


def upload(path: Path):
    """Upload (or fetch) a pseudo potential file as an ``UpfData`` node."""
    from aiida.plugins import DataFactory

    UpfData = DataFactory('pseudo.upf')
    result = UpfData.get_or_create(source=str(path))
    node = result[0] if isinstance(result, tuple) else result
    if not node.is_stored:
        node.store()
    return node


def upf_header(path: Path) -> dict:
    """Read the few UPF header attributes that aiida-pseudo does not store.

    ``relativistic`` and ``pseudo_type`` are the two that matter here: they tell
    scalar- from fully-relativistic pseudopotentials and NC from PAW/USPP, which
    is exactly what the verification is about.
    """
    import re

    text = path.read_text(errors='replace')[:20000]
    info = {}
    for key in ('relativistic', 'pseudo_type', 'functional', 'z_valence'):
        match = re.search(rf'{key}\s*=\s*"([^"]*)"', text)
        if match:
            info[key] = match.group(1).strip()
    if 'is_ultrasoft' in text and re.search(r'is_ultrasoft\s*=\s*"\.?[Tt]', text):
        info['pseudo_type'] = 'US'
    if 'is_paw' in text and re.search(r'is_paw\s*=\s*"\.?[Tt]', text):
        info['pseudo_type'] = 'PAW'
    return info


def describe(node, label: str, path: Path | None = None) -> str:
    attrs = node.base.attributes.all
    element = attrs.get('element') or getattr(node, 'element', '?')
    header = upf_header(path) if path is not None and path.exists() else {}
    return (
        f"  {label:<28} pk={node.pk:<7} element={str(element).strip():<3} "
        f"z_valence={attrs.get('z_valence', '?'):<5} "
        f"relativistic={header.get('relativistic', '?'):<8} "
        f"type={header.get('pseudo_type', '?'):<5} functional={header.get('functional', '?'):<6} "
        f"file={attrs.get('filename', node.filename)}"
    )


def generator_default_family() -> str | None:
    """Read the ``pseudo_family`` that the QE plugin protocol uses by default."""
    try:
        import yaml
        import aiida_quantumespresso.workflows.protocols.pw as pw_protocols
        from importlib import resources
        with resources.open_text(pw_protocols, 'base.yaml') as handle:
            data = yaml.safe_load(handle)
        return data.get('default_inputs', {}).get('pseudo_family')
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    args = parse_args()
    util.load_profile()

    from aiida import orm
    from aiida_pseudo.groups.family import CutoffsPseudoPotentialFamily

    print('=' * 78)
    print('1. Uploading pseudopotentials')
    print('=' * 78)

    o_path = Path(config.O_PSEUDO_FILE)
    if not o_path.exists():
        print(f"ERROR: oxygen pseudopotential {o_path} not found.", file=sys.stderr)
        return 1

    o_node = upload(o_path)
    print(describe(o_node, 'O (shared, NC)', o_path))

    nodes = {}
    for key, spec in config.PSEUDOS.items():
        path = Path(spec['upf'])
        if not path.is_absolute():
            path = Path(config.PSEUDO_DIR) / spec['upf']
        if not path.exists():
            print(f"ERROR: pseudo file {path} not found.", file=sys.stderr)
            return 1
        node = upload(path)
        nodes[key] = node
        print(describe(node, f"{spec['upf']} [{key}]", path))

        z_valence = node.base.attributes.get('z_valence')
        expected_z = float(spec.get('z_valence') or 0)
        if expected_z and (z_valence is None or abs(float(z_valence) - expected_z) > 1e-6):
            print(
                f"  WARNING: expected {expected_z:g} valence electrons, found {z_valence!r}. "
                "Double-check that the right file was installed."
            )

    o_z = float(o_node.base.attributes.get('z_valence', 0) or 0)
    if abs(o_z - 6.0) > 1e-6:
        print(f"  NOTE: oxygen z_valence is {o_z} (expected 6 for O_ONCV_PBE-1.0).")

    print()
    print('=' * 78)
    print('2. Creating the cutoff pseudo families')
    print('=' * 78)

    for key, spec in config.PSEUDOS.items():
        family_label = spec['family']
        family, created = CutoffsPseudoPotentialFamily.collection.get_or_create(
            label=family_label,
            description=(
                f"U={spec['upf']} ({spec['description']}), "
                f"O={o_path.name} (NC). Created by the u14ve-verification workflow."
            ),
        )
        family.clear()
        family.add_nodes([nodes[key], o_node])

        cutoffs = {'O': {'cutoff_wfc': float(config.O_CUTOFFS[0]), 'cutoff_rho': float(config.O_CUTOFFS[1])}}
        for element, (wfc, rho) in spec['default_cutoffs'].items():
            cutoffs[element] = {'cutoff_wfc': float(wfc), 'cutoff_rho': float(rho)}

        family.set_cutoffs(cutoffs=cutoffs, stringency='normal', unit='rydberg')
        family.set_default_stringency('normal')
        print(f"  {'created' if created else 'updated'}: {family_label}")
        print(f"      elements = {family.elements}")
        print(f"      cutoffs  = {family.get_cutoffs()}")

    print()
    print('=' * 78)
    print('3. Documentation groups')
    print('=' * 78)
    for key, spec in config.PSEUDOS.items():
        for spin_orbit in (False, True):
            if spin_orbit and spec['rel'] != 'full':
                continue
            label = util.pseudo_group_label(util.set_name(key, spin_orbit=spin_orbit))
            group, _ = orm.Group.collection.get_or_create(label=label)
            group.add_nodes([nodes[key], o_node])
            print(f"  {label}: {len(group.nodes)} node(s)")

    print()
    print('=' * 78)
    print('4. Pseudo family resolved by the ACWF input generator')
    print('=' * 78)
    # The placeholder family below is built from the pseudopotential under test.  This
    # repository configures exactly one (`config.PSEUDOS` may hold more upstream).
    candidate_key = sorted(config.PSEUDOS)[0]
    candidate_cutoffs = config.PSEUDOS[candidate_key]['default_cutoffs']['U']
    default_family = generator_default_family()
    if default_family is None:
        print('  could not read the default pseudo_family from the QE plugin protocol.')
    else:
        print(f"  default pseudo_family = {default_family!r}")
        try:
            family = orm.load_group(default_family)
            elements = sorted(getattr(family, 'elements', []) or [])
            print(f"  -> exists, elements = {elements}")
            missing = {'U', 'O'} - set(elements)
            if missing:
                print(
                    f"  WARNING: it does not contain {sorted(missing)}. The ACWF generator will fail\n"
                    f"           for structures with those elements. Re-run with "
                    f"--fix-generator-family."
                )
                if args.fix_generator_family:
                    family.clear()
                    family.add_nodes([nodes[candidate_key], o_node])
                    family.set_cutoffs(
                        cutoffs={
                            'U': {'cutoff_wfc': float(candidate_cutoffs[0]),
                                  'cutoff_rho': float(candidate_cutoffs[1])},
                            'O': {'cutoff_wfc': float(config.O_CUTOFFS[0]),
                                  'cutoff_rho': float(config.O_CUTOFFS[1])},
                        },
                        stringency='normal',
                        unit='rydberg',
                    )
                    family.set_default_stringency('normal')
                    print(f"  -> fixed: {default_family} now contains {family.elements}")
        except Exception:  # noqa: BLE001
            print('  -> DOES NOT EXIST.')
            if args.fix_generator_family:
                family = CutoffsPseudoPotentialFamily(
                    label=default_family,
                    description='Placeholder family created by u14ve-verification/install_pseudos.py.',
                ).store()
                family.add_nodes([nodes[candidate_key], o_node])
                family.set_cutoffs(
                    cutoffs={
                        'U': {'cutoff_wfc': float(candidate_cutoffs[0]),
                              'cutoff_rho': float(candidate_cutoffs[1])},
                        'O': {'cutoff_wfc': float(config.O_CUTOFFS[0]),
                              'cutoff_rho': float(config.O_CUTOFFS[1])},
                    },
                    stringency='normal',
                    unit='rydberg',
                )
                family.set_default_stringency('normal')
                print(f"  -> created placeholder family {default_family!r} (elements {family.elements}).")
            else:
                print(
                    '     The ACWF input generator resolves this family before our overrides are\n'
                    '     applied, so a missing family makes every EOS workchain fail. Re-run with\n'
                    '     --fix-generator-family to create it from the U pseudo under test.'
                )

    print()
    print('Next step:  python 1-preliminary/create_starting_subgroups.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
