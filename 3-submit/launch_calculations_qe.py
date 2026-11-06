#!/usr/bin/env python
"""Submit the ACWF equation-of-state workflows for the two uranium pseudopotentials.

This is the direct analogue of
``acwf-verification-scripts/2-submit/launch_calculations_qe.py``: it walks the
structures of a set and submits one ``EquationOfStateWorkChain`` per structure
through a ``FromGroupSubmissionController``, so it can be called repeatedly and
always only submits what is still missing.

What makes it different
-----------------------

* two sets are submitted (one per candidate pseudopotential), plus an optional
  spin-orbit set for the fully relativistic one;
* every code-dependent input is pinned through ``sub_process.base_relax``
  (pseudopotentials, cutoffs, k-point density, convergence thresholds, smearing),
  so the run follows the ACWF/SSSP standard no matter what the plugin protocol
  defaults are — see ``common/standard.py`` and ``common/util.py``.

Usage
-----

    # dry run (default): show what would be submitted, submit nothing
    python 3-submit/launch_calculations_qe.py

    # actually submit, for both pseudopotentials, all ten systems
    python 3-submit/launch_calculations_qe.py --run

    # the recommended loop for long submissions
    while true ; do python 3-submit/launch_calculations_qe.py --run ; sleep 60 ; done

    # only the four unaries, only the scalar-relativistic pseudo, 10 at a time
    python 3-submit/launch_calculations_qe.py --run --pseudos sr \
        --configurations X/SC X/BCC X/FCC X/Diamond --max-concurrent 10

    # optional spin-orbit runs of the fully relativistic pseudo
    python 3-submit/launch_calculations_qe.py --run --pseudos fr --spin-orbit

    # use converged cutoffs from a JSON file instead of 2-convergence/cutoffs.json
    python 3-submit/launch_calculations_qe.py --run --cutoffs my-cutoffs.json
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import standard as std  # noqa: E402
from common import util  # noqa: E402

# The ACWF `verification-PBE-v1` section of aiida-common-workflows 1.0 uses the
# pre-5.0 namespace names, which aiida-quantumespresso 5.x reports as
# "unrecognised key in overrides".  That warning is expected and harmless here:
# the standard is enforced through `sub_process`.  See 1-preliminary/verify_setup.py.
warnings.filterwarnings('ignore', message=r'Found unrecognised key in overrides: .*')


def make_controller_class():
    """Create the submission controller class (imported lazily, needs AiiDA)."""
    from aiida import orm
    from aiida.plugins import WorkflowFactory
    from aiida_submission_controller import FromGroupSubmissionController

    class EosSubmissionController(FromGroupSubmissionController):
        """A SubmissionController for submitting EOS with Quantum ESPRESSO common workflows."""

        def __init__(self, code_label, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._code = orm.load_code(code_label)
            self._process_class = WorkflowFactory('common_workflows.eos')

        def set_pseudo(self, pseudo_key, standard, cutoffs, spin_orbit, kpoints_distance=None,
                       options=None):
            """Pin the pseudopotential, cutoffs and standard used by this batch."""
            self._pseudo_key = pseudo_key
            self._standard = standard
            self._cutoffs = cutoffs
            self._spin_orbit = spin_orbit
            self._kpoints_distance = kpoints_distance
            self._options = options

        def get_extra_unique_keys(self):
            """Identify each EOS workchain by (element, configuration)."""
            return ['element', 'configuration']

        def get_inputs_and_processclass_from_extras(self, extras_values):
            structure = self.get_parent_node_from_extras(extras_values)
            inputs = util.build_eos_inputs(
                structure,
                self._pseudo_key,
                self._standard,
                cutoffs=self._cutoffs,
                spin_orbit=self._spin_orbit,
                kpoints_distance=self._kpoints_distance,
                options=self._options,
            )
            return inputs, self._process_class

    return EosSubmissionController


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--run', action='store_true', help='Actually submit. Default is a dry run.')
    parser.add_argument('--pseudos', nargs='+', default=None, choices=sorted(config.PSEUDOS),
                        help=f"Pseudopotentials to submit (default: {sorted(config.PSEUDOS)}).")
    parser.add_argument('--standard', default=std.DEFAULT_STANDARD, choices=sorted(std.STANDARDS),
                        help=f"Calculation standard (default: {std.DEFAULT_STANDARD}).")
    parser.add_argument('--configurations', nargs='+',
                        default=list(getattr(config, 'VERIFICATION_CONFIGURATIONS',
                                             config.ALL_CONFIGURATIONS)),
                        help='Subset of configurations (default: this project verifies '
                             f'{list(getattr(config, "VERIFICATION_CONFIGURATIONS", config.ALL_CONFIGURATIONS))}; '
                             f'all ten available are {list(config.ALL_CONFIGURATIONS)}).')
    parser.add_argument('--spin-orbit', action='store_true',
                        help='Also submit spin-orbit (noncolin/lspinorb) runs of the fully '
                             'relativistic pseudo. These are NOT comparable with the '
                             'scalar-relativistic all-electron references.')
    parser.add_argument('--only-spin-orbit', action='store_true',
                        help='Submit only the spin-orbit set.')
    parser.add_argument('--max-concurrent', type=int, default=config.MAX_CONCURRENT)
    parser.add_argument('--max-memory-gb', type=float, default=None,
                        help='Request this much memory per node (GB) for every calculation of the '
                             'batch, i.e. `#SBATCH --mem=`. Needed for the large cells: the partition '
                             'default is 872 MB per core, which is only ~49 GB for 56 cores and makes '
                             '8-atom cells at high cutoff die with "Out Of Memory".')
    parser.add_argument('--cutoffs', type=Path, default=None,
                        help='JSON file with converged cutoffs (default: 2-convergence/cutoffs.json).')
    parser.add_argument('--kpoints-distance', type=float, default=None,
                        help='DEV ONLY: override the k-point density of the standard. Values above '
                             '0.06 1/Angstrom make the runs much cheaper but the results are then '
                             'NOT in the ACWF/SSSP standard and must not be reported as such.')
    parser.add_argument('--dry-run-count', type=int, default=None,
                        help='Limit the number of workchains reported in a dry run.')
    parser.add_argument('--set-tag', default=None,
                        help='Extra tag inserted in the set name (e.g. `--set-tag wide` gives '
                             '`u14ve-sr-wide-verification-PBE-v1`). Use it to run a variant of the '
                             'standard without mixing it with the main set.')
    parser.add_argument('--scale-increment', type=float, default=None,
                        help='Override the EOS step of the standard. E.g. 0.035 gives 7 volumes '
                             'spanning +-10.5 %% instead of +-6 %%, which is needed for a '
                             'pseudopotential whose equilibrium volume lies outside the standard '
                             'window (the Birch-Murnaghan fit would otherwise not be bracketed).')
    parser.add_argument('--scale-count', type=int, default=None,
                        help='Override the number of EOS volumes of the standard.')
    parser.add_argument('--smoke-test', action='store_true',
                        help='Pre-flight run: one cheap EOS (X/SC, 3 volumes, coarse k-points) in '
                             'its own set, to check that the whole chain runs before starting the '
                             'production campaign. The results are NOT part of the verification.')
    return parser.parse_args()


def convergence_warning(pseudo_key: str):
    """Return a warning string if the cutoff scan did not converge for this pseudo.

    ``select_cutoffs.py`` records ``converged: false`` when no scan point satisfies the
    SSSP criterion.  Running the production EOS anyway would burn compute on an EOS that
    is not usable, so the launcher says so explicitly.
    """
    import json

    path = util.cutoffs_file()
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text()).get(pseudo_key, {}).get('U', {})
    except Exception:  # noqa: BLE001
        return None
    if entry.get('converged') is False:
        tested = (json.loads(path.read_text()).get(pseudo_key, {}).get('_meta', {})
                  .get('tested_points'))
        return (
            f"WARNING: the cutoff convergence scan did NOT converge for pseudo "
            f"'{pseudo_key}' (2-convergence/cutoffs.json: converged=false, "
            f"ecutwfc={entry.get('ecutwfc')} Ry, tested {tested} Ry). "
            f"The equations of state of this pseudopotential should be treated as unusable "
            f"until the cause is understood — see the diagnosis documents in "
            f"4-analyze/outputs/*-pseudopotential-diagnosis.md. Proceeding anyway."
        )
    return None


def resolve_cutoffs(pseudo_key: str, path: Path | None):
    if path is None:
        return util.load_cutoffs(pseudo_key)

    import json

    payload = json.loads(path.read_text())
    entry = payload.get(pseudo_key)
    if entry is None:
        raise SystemExit(f"ERROR: no entry for pseudo '{pseudo_key}' in {path}")

    cutoffs = {}
    for element, pair in entry.items():
        if element.startswith('_'):          # bookkeeping keys ('_meta', ...)
            continue
        if isinstance(pair, dict):
            cutoffs[element] = (float(pair['ecutwfc']), float(pair['ecutrho']))
        else:
            cutoffs[element] = (float(pair[0]), float(pair[1]))
    if not cutoffs:
        raise SystemExit(f"ERROR: no cutoffs for pseudo '{pseudo_key}' in {path}")
    return cutoffs


def submit_one(controller_class, pseudo_key, spin_orbit, standard, cutoffs, args, set_suffix=None):
    name = util.set_name(pseudo_key, spin_orbit=spin_orbit, suffix=set_suffix)
    structures_label = util.structures_group_label(name)
    workflows_label = util.workflows_group_label(name)

    from aiida import orm

    try:
        group = orm.load_group(structures_label)
    except Exception:  # noqa: BLE001
        if set_suffix is None:
            print(f"  ERROR: structures group '{structures_label}' does not exist. "
                  f"Run 1-preliminary/create_starting_subgroups.py first.")
            return 1
        # Smoke-test sets are created on the fly from the production structures.
        source = orm.load_group(util.structures_group_label(util.set_name(pseudo_key, spin_orbit)))
        subset = util.filter_structures(list(source.nodes), args.configurations)
        group, _ = orm.Group.collection.get_or_create(label=structures_label)
        group.add_nodes(subset)
        print(f"  created '{structures_label}' with {len(subset)} structure(s)")

    selected = util.filter_structures(list(group.nodes), args.configurations)
    if not selected:
        print(f"  no structure selected for {name}")
        return 0

    # The submission controller works from a *group*: when only a subset of the
    # configurations is requested, put that subset into its own group and use it
    # as the parent group.  The workflows group does not change, so batches with
    # different selections accumulate in the same group and the controller still
    # skips everything that has already been submitted.
    if args.configurations is not None:
        tag = '-'.join(conf.replace('/', '_') for conf in args.configurations)
        structures_label = f'{structures_label}/selected-{tag}'
        subset_group, _ = orm.Group.collection.get_or_create(label=structures_label)
        subset_group.add_nodes(selected)

    options = dict(config.COMPUTER_OPTIONS)
    if args.max_memory_gb is not None:
        options['max_memory_kb'] = int(args.max_memory_gb * 1024 * 1024)

    controller = controller_class(
        code_label=config.CODE_LABEL,
        parent_group_label=structures_label,
        group_label=workflows_label,
        max_concurrent=args.max_concurrent,
    )
    controller.set_pseudo(pseudo_key, standard, cutoffs, spin_orbit,
                          kpoints_distance=args.kpoints_distance, options=options)

    print(f"  set            : {name}")
    print(f"  structures     : {len(selected)} of {len(group.nodes)} in '{structures_label}'")
    print(f"  workflows group: {workflows_label}")
    print(f"  already run    : {controller.num_already_run}")
    print(f"  active slots   : {controller.num_active_slots}")
    print(f"  still to run   : {controller.num_to_run}")

    run_processes = controller.submit_new_batch(dry_run=not args.run)
    shown = 0
    for extras, process in run_processes.items():
        # `extras` is the tuple of unique extra values, e.g. ('U', 'X/BCC'); do not
        # run dict() on it (that would pair up the characters of the strings).
        extras_str = tuple(extras) if isinstance(extras, (tuple, list)) else extras
        if process is None:
            print(f"    {extras_str} --> to be run")
        else:
            print(f"    {extras_str} --> pk = {process.pk}")
        shown += 1
        if not args.run and args.dry_run_count and shown >= args.dry_run_count:
            print(f"    ... ({len(run_processes) - shown} more)")
            break
    print()
    return 0


def main() -> int:
    args = parse_args()
    util.load_profile()

    standard = std.get_standard(args.standard)
    if args.scale_increment is not None:
        standard = {**standard, 'scale_increment': args.scale_increment}
    if args.scale_count is not None:
        standard = {**standard, 'scale_count': args.scale_count}

    set_suffix = f'{args.set_tag}-verification-PBE-v1' if args.set_tag else None
    if args.smoke_test:
        standard = {**standard, 'kpoints_distance': 0.3,
                    'scale_count': args.scale_count or 3,
                    'scale_increment': args.scale_increment or 0.04}
        set_suffix = 'smoketest-verification-PBE-v1'
        if not args.configurations:
            args.configurations = ['X/SC']
        if args.max_concurrent == config.MAX_CONCURRENT:
            args.max_concurrent = 2

    pseudo_keys = args.pseudos or sorted(config.PSEUDOS)
    modes = []
    for key in pseudo_keys:
        if not args.only_spin_orbit:
            modes.append((key, False))
        if args.spin_orbit or args.only_spin_orbit:
            if config.PSEUDOS[key]['rel'] != 'full':
                if args.spin_orbit or args.only_spin_orbit:
                    print(f"  NOTE: skipping spin-orbit for '{key}' "
                          f"({config.PSEUDOS[key]['rel']}-relativistic pseudo).")
                continue
            modes.append((key, True))

    print('=' * 78)
    print("ACWF/SSSP verification of the U-14ve pseudopotentials")
    print('=' * 78)
    print(f"  profile   : {config.AIIDA_PROFILE}")
    print(f"  code      : {config.CODE_LABEL}")
    print(f"  standard  : {standard['name']} — {standard['description']}")
    print(f"  dry run   : {not args.run}")
    print(f"  sets      : {[util.set_name(k, s, suffix=set_suffix) for k, s in modes]}")
    print()

    controller_class = make_controller_class()

    exit_code = 0
    for pseudo_key, spin_orbit in modes:
        warning = convergence_warning(pseudo_key)
        if warning:
            print(warning)
            print()
        cutoffs = resolve_cutoffs(pseudo_key, args.cutoffs)
        spec = config.PSEUDOS[pseudo_key]
        print('-' * 78)
        print(f"{spec['description']}{'  [spin-orbit]' if spin_orbit else ''}")
        print(f"  UPF           : {spec['upf']}")
        print(f"  cutoffs (Ry)  : {cutoffs}")
        converged, tested = util.cutoff_scan_status(pseudo_key)
        if converged is False:
            print('  WARNING       : the cutoff scan did NOT converge for this pseudopotential '
                  f'(tested: {tested or "?"} Ry).')
            print('                  The values above are a fallback, so every energy in this '
                  'batch carries an unknown cutoff error.')
        print(std.describe_standard(standard, std.effective_cutoffs(cutoffs, config.O_CUTOFFS)).replace('\n', '\n  '))
        print('-' * 78)
        exit_code |= submit_one(controller_class, pseudo_key, spin_orbit, standard, cutoffs, args,
                                set_suffix=set_suffix)

    if not args.run:
        print('This was a DRY RUN. Add --run to actually submit the workchains.')
    else:
        print('Submitted. Use `verdi process list -a` and the workflows groups to follow the runs.')
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
