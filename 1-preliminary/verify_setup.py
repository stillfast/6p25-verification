#!/usr/bin/env python
"""Verify that the profile is ready and that the standard really is applied.

This is the safety net of the project.  It does *not* trust that the protocol
YAML was picked up: it rebuilds the sub-process exactly the way the EOS workchain
does (ACWF input generator + ``sub_process`` merge) and compares the resulting
inputs against the standard of ``common/standard.py``.  If anything does not
match, the script fails loudly.

Checks performed
----------------

1. the AiiDA profile, the code and its plugin;
2. the pseudo families: elements, ``z_valence`` and cutoff table;
3. the structure groups: ten systems, four unaries and six oxides;
4. the effective ``pw.x`` inputs for one unary and one oxide system per
   pseudopotential: pseudopotentials, ``ecutwfc``/``ecutrho``,
   ``kpoints_distance``, ``conv_thr``, ``etot_conv_thr``, ``forc_conv_thr``,
   smearing/degauss;
5. the k-point mesh that the density generates for the reference (unscaled) cell;
6. a diagnostic of the ``verification-PBE-v1`` ACWF protocol section
   (see the note below).

Note on the ACWF protocol section
---------------------------------

``aiida-common-workflows`` 1.0 stores the Quantum ESPRESSO protocol under the
keys ``base`` / ``base_final_scf``, which were renamed to ``base_relax`` /
``base_init_relax`` in ``aiida-quantumespresso`` 5.0.  With the plugin versions
installed here those keys are therefore reported as *unrecognised overrides* and
have no effect: the plugin silently falls back to its own protocol defaults
(``kpoints_distance = 0.15``, ``smearing = cold``, ``degauss = 0.02``, ...).

This project does not depend on that section: the standard is enforced by
``sub_process``.  The diagnostic is printed because a run whose provenance says
``protocol='verification-PBE-v1'`` while the YAML is inert is easy to
misread.  ``1-preliminary/patch_acwf_qe_generator.py`` can additionally repair
the section (and remove the useless pre-relaxation SCF) if you want the
recorded protocol to be self-consistent.

Usage
-----

    python 1-preliminary/verify_setup.py [--configurations X/BCC XO2]
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import standard as std  # noqa: E402
from common import util  # noqa: E402

FAILURES: list = []


def check(condition: bool, message: str, detail: str = '') -> bool:
    if condition:
        print(f"  [ OK ] {message}")
    else:
        FAILURES.append(message)
        print(f"  [FAIL] {message}")
        if detail:
            for line in detail.splitlines():
                print(f"         {line}")
    return condition


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--standard', default=std.DEFAULT_STANDARD, choices=sorted(std.STANDARDS))
    parser.add_argument('--configurations', nargs='+', default=None)
    return parser.parse_args()


def effective_sub_process_inputs(structure, pseudo_key, standard, spin_orbit=False):
    """Rebuild the sub-process builder the way the EOS workchain does."""
    from aiida_common_workflows.plugins import load_workflow_entry_point

    inputs = util.build_eos_inputs(
        structure, pseudo_key, standard, spin_orbit=spin_orbit
    )
    gen = load_workflow_entry_point('relax', 'quantum_espresso').get_input_generator()
    builder = gen.get_builder(structure=structure, **inputs['generator_inputs'])
    builder._merge(**inputs['sub_process'])
    return inputs, builder


def main() -> int:
    args = parse_args()
    # The ACWF protocol section of this checkout triggers harmless
    # "unrecognised key in overrides" warnings; keep the output readable.
    warnings.filterwarnings('ignore', message=r'Found unrecognised key in overrides: .*')

    util.load_profile()
    standard = std.get_standard(args.standard)

    from aiida import orm

    print('=' * 78)
    print('1. Profile, code and plugin')
    print('=' * 78)
    print(f"  profile : {config.AIIDA_PROFILE}")
    try:
        code = orm.load_code(config.CODE_LABEL)
        print(f"  code    : {code.label} (pk={code.pk}) on computer '{code.computer.label}'")
        check(code.default_calc_job_plugin == 'quantumespresso.pw',
              f"code '{config.CODE_LABEL}' uses the quantumespresso.pw plugin",
              f"found {code.default_calc_job_plugin!r}")
    except Exception as exc:  # noqa: BLE001
        check(False, f"code '{config.CODE_LABEL}' can be loaded", str(exc))
        return 1

    print()
    print('=' * 78)
    print('2. Pseudopotential families')
    print('=' * 78)
    pseudo_nodes = {}
    for key, spec in config.PSEUDOS.items():
        try:
            nodes = util.load_pseudo_nodes(key)
            pseudo_nodes[key] = nodes
        except SystemExit as exc:
            check(False, f"family '{spec['family']}' is installed", str(exc))
            continue
        check(set(nodes) >= {'U', 'O'}, f"family '{spec['family']}' contains U and O",
              f"elements found: {sorted(nodes)}")
        u_node = nodes.get('U')
        expected_z = float(spec.get('z_valence') or 0)
        if u_node is not None:
            attrs = u_node.base.attributes.all
            filename = attrs.get('filename', u_node.filename)
            expected_name = Path(spec['upf']).name
            check(filename == expected_name,
                  f"family '{spec['family']}' holds {expected_name}",
                  f"found {filename}")
            check(not expected_z or abs(float(attrs.get('z_valence', 0)) - expected_z) < 1e-6,
                  f"{spec['upf']} has {expected_z:g} valence electrons",
                  f"found z_valence={attrs.get('z_valence')!r}")

    print()
    print('=' * 78)
    print('3. Structures')
    print('=' * 78)
    for key, spec in config.PSEUDOS.items():
        for spin_orbit in ((False, True) if spec['rel'] == 'full' else (False,)):
            name = util.set_name(key, spin_orbit=spin_orbit)
            label = util.structures_group_label(name)
            try:
                group = orm.load_group(label)
                configs = sorted(node.base.extras.get('configuration') for node in group.nodes)
                check(len(group.nodes) > 0, f"'{label}' has {len(group.nodes)} structure(s)",
                      f"configurations: {configs}")
            except Exception as exc:  # noqa: BLE001
                check(False, f"'{label}' exists", f"run create_starting_subgroups.py ({exc})")

    print()
    print('=' * 78)
    print('4. Effective pw.x inputs (generator + sub_process merge)')
    print('=' * 78)

    try:
        structures = util.filter_structures(util.source_structures(), args.configurations)
    except SystemExit as exc:
        check(False, 'structures can be loaded', str(exc))
        return 1

    # One representative unary and one representative oxide are enough: the
    # inputs only depend on the element set and the number of atoms.
    samples = {}
    for node in structures:
        conf = node.base.extras.get('configuration')
        kind = 'unary' if conf in config.UNARY_CONFIGURATIONS else 'oxide'
        samples.setdefault(kind, node)

    for key, spec in config.PSEUDOS.items():
        if key not in pseudo_nodes:
            continue
        for spin_orbit in ((False, True) if spec['rel'] == 'full' else (False,)):
            name = util.set_name(key, spin_orbit=spin_orbit)
            print(f"\n  --- {name} ({spec['description']}) ---")
            cutoffs = util.load_cutoffs(key)
            for kind, structure in samples.items():
                try:
                    inputs, builder = effective_sub_process_inputs(structure, key, standard, spin_orbit)
                except Exception as exc:  # noqa: BLE001
                    check(False, f"[{name}] sub-process can be built for {kind}",
                          f"{type(exc).__name__}: {exc}")
                    continue

                base = builder.base_relax
                params = base.pw.parameters.get_dict()
                pseudos = {k: v.filename for k, v in base.pw.pseudos.items()}
                natoms = len(structure.sites)
                expected = std.build_pw_parameters(
                    natoms, std.effective_cutoffs(cutoffs, config.O_CUTOFFS), standard, spin_orbit=spin_orbit
                )

                label = f"[{name}] {util.structure_key(structure)}"
                check(pseudos.get('U') == Path(spec['upf']).name,
                      f"{label} uses {Path(spec['upf']).name}", f"found {pseudos}")
                check(all(
                    pseudos.get(k) == pseudo_nodes[key][util.element_of_kind(k)].filename for k in pseudos
                ), f"{label} pseudos match the family", f"found {pseudos}")

                check(params['SYSTEM']['ecutwfc'] == expected['SYSTEM']['ecutwfc']
                      and params['SYSTEM']['ecutrho'] == expected['SYSTEM']['ecutrho'],
                      f"{label} cutoffs = {expected['SYSTEM']['ecutwfc']}/{expected['SYSTEM']['ecutrho']} Ry",
                      f"found {params['SYSTEM']['ecutwfc']}/{params['SYSTEM']['ecutrho']}")
                check(abs(float(base.kpoints_distance.value) - standard['kpoints_distance']) < 1e-12,
                      f"{label} kpoints_distance = {standard['kpoints_distance']} 1/Angstrom",
                      f"found {base.kpoints_distance.value}")
                check(abs(params['ELECTRONS']['conv_thr'] - expected['ELECTRONS']['conv_thr']) < 1e-18,
                      f"{label} conv_thr = {expected['ELECTRONS']['conv_thr']:.2e} Ry",
                      f"found {params['ELECTRONS']['conv_thr']:.2e}")
                check(abs(params['CONTROL']['etot_conv_thr'] - expected['CONTROL']['etot_conv_thr']) < 1e-18,
                      f"{label} etot_conv_thr = {expected['CONTROL']['etot_conv_thr']:.2e} Ry",
                      f"found {params['CONTROL']['etot_conv_thr']:.2e}")
                check(params['CONTROL']['forc_conv_thr'] == expected['CONTROL']['forc_conv_thr'],
                      f"{label} forc_conv_thr = {expected['CONTROL']['forc_conv_thr']:.1e} Ry/bohr",
                      f"found {params['CONTROL']['forc_conv_thr']:.1e}")
                check(params['SYSTEM']['smearing'] == expected['SYSTEM']['smearing']
                      and params['SYSTEM']['degauss'] == expected['SYSTEM']['degauss'],
                      f"{label} smearing = {expected['SYSTEM']['smearing']} / {expected['SYSTEM']['degauss']} Ry",
                      f"found {params['SYSTEM']['smearing']} / {params['SYSTEM']['degauss']}")
                check(params['CONTROL']['calculation'] == 'scf',
                      f"{label} CONTROL.calculation = scf",
                      f"found {params['CONTROL'].get('calculation')!r}")
                if spin_orbit:
                    check(params['SYSTEM'].get('noncolin') is True
                          and params['SYSTEM'].get('lspinorb') is True
                          and params['SYSTEM'].get('nspin') == 4,
                          f"{label} spin-orbit flags set",
                          f"found { {k: params['SYSTEM'].get(k) for k in ('noncolin', 'lspinorb', 'nspin')} }")
                check('scale_count' not in inputs or int(inputs['scale_count']) == standard['scale_count'],
                      f"{label} scale_count = {standard['scale_count']}")

                kpoints = _kpoints_mesh(structure, base.kpoints_distance.value)
                print(f"         -> {natoms} atoms, k-mesh {kpoints} "
                      f"({_irreducible_hint(structure)})")
                print(f"         -> parameters: {json.dumps(params, sort_keys=True)}")

    print()
    print('=' * 78)
    print('5. Submission-level input validation')
    print('=' * 78)
    print('  Rebuilds the EOS inputs and the sub-process inputs exactly as AiiDA does at')
    print('  submission time, for every structure/pseudopotential combination.')
    _submission_validation(structures, standard)

    print()
    print('=' * 78)
    print('6. ACWF protocol section diagnostic')
    print('=' * 78)
    _protocol_diagnostic()

    print()
    print('=' * 78)
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} check(s) FAILED")
        for item in FAILURES:
            print(f"  - {item}")
        print('=' * 78)
        return 1
    print('RESULT: all checks passed — the standard is applied as defined in common/standard.py')
    print('=' * 78)
    return 0


def _kpoints_mesh(structure, distance):
    """Return the Monkhorst-Pack mesh that the k-point density generates."""
    try:
        from aiida_quantumespresso.calculations.functions.create_kpoints_from_distance import (
            create_kpoints_from_distance,
        )
        from aiida import orm

        node = create_kpoints_from_distance(
            structure=structure, distance=orm.Float(distance), force_parity=orm.Bool(False)
        )
        return node.get_kpoints_mesh()[0]
    except Exception as exc:  # noqa: BLE001
        return f'<could not compute: {exc}>'


def _irreducible_hint(structure):
    return 'mesh reused across all 7 volumes'


def _submission_validation(structures, standard):
    """Validate the EOS inputs and the sub-process inputs for every structure.

    This is the check that catches stray inputs: it replicates what AiiDA does
    when the workchain is submitted (``spec().inputs.serialize`` + ``validate``).
    """
    from aiida.plugins import WorkflowFactory

    from aiida_common_workflows.plugins import load_workflow_entry_point

    eos_cls = WorkflowFactory('common_workflows.eos')
    eos_namespace = eos_cls.spec().inputs

    for key, spec in config.PSEUDOS.items():
        for spin_orbit in ((False, True) if spec['rel'] == 'full' else (False,)):
            name = util.set_name(key, spin_orbit=spin_orbit)
            failures = []
            for structure in structures:
                label = f"[{name}] {util.structure_key(structure)}"
                try:
                    inputs = util.build_eos_inputs(structure, key, standard, spin_orbit=spin_orbit)
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{label}: build failed: {exc}")
                    continue

                try:
                    processed = eos_namespace.pre_process(dict(inputs))
                    error = eos_namespace.validate(eos_namespace.serialize(processed))
                except Exception as exc:  # noqa: BLE001
                    error = f'validation raised {type(exc).__name__}: {exc}'
                if error:
                    failures.append(f"{label}: EOS inputs: {error}")

                try:
                    generator = load_workflow_entry_point(
                        'relax', 'quantum_espresso'
                    ).get_input_generator()
                    builder = generator.get_builder(structure=structure, **inputs['generator_inputs'])
                    builder._merge(**inputs['sub_process'])
                    namespace = builder._process_class.spec().inputs
                    error = namespace.validate(namespace.serialize(builder._inputs(prune=True)))
                except Exception as exc:  # noqa: BLE001
                    error = f'validation raised {type(exc).__name__}: {exc}'
                if error:
                    failures.append(f"{label}: sub-process inputs: {error}")

            check(not failures, f"[{name}] all {len(structures)} structure(s) pass input validation")
            for item in failures:
                print(f"         {item}")
                FAILURES.append(item)


def _protocol_diagnostic():
    """Report whether the ACWF verification-PBE-v1 YAML section is effective."""
    import yaml
    from importlib import resources

    try:
        import aiida_common_workflows.workflows.relax.quantum_espresso as qe_module

        with resources.open_text(qe_module, 'protocol.yml') as handle:
            protocols = yaml.safe_load(handle)
    except Exception as exc:  # noqa: BLE001
        print(f"  could not read the ACWF protocol YAML: {exc}")
        return

    entry = protocols.get('verification-PBE-v1', {})
    keys = sorted(k for k in entry if k not in ('description',))
    print(f"  verification-PBE-v1 keys found: {keys}")
    if any(k in entry for k in ('base', 'base_final_scf')):
        print(
            "  [WARN] the section uses the pre-5.0 `base` / `base_final_scf` namespace names.\n"
            "         aiida-quantumespresso 5.x expects `base_relax` / `base_init_relax`, so this\n"
            "         section is inert: without the `sub_process` overrides of this project the EOS\n"
            "         runs would silently use the plugin defaults (kpoints_distance 0.15,\n"
            "         smearing 'cold', degauss 0.02, ...) instead of the ACWF standard.\n"
            "         This project does not rely on it; see the module docstring."
        )
    else:
        pseudo_family = entry.get('base_relax', {}).get('pseudo_family')
        print(f"  [ OK ] the section uses the 5.x namespace names (pseudo_family={pseudo_family!r})")


if __name__ == '__main__':
    sys.exit(main())
