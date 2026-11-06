#!/usr/bin/env python
"""SSSP-style plane-wave cutoff convergence scan.

The two candidate pseudopotentials carry no recommended cutoff in their UPF
header ("Suggested minimum cutoff for wavefunctions: 0. Ry"), so the cutoff has
to be determined before the verification runs — this is exactly what the SSSP
protocol does.

The scan follows the SSSP control protocol
(``aiida-sssp-workflow``, ``protocol/control.yml`` and ``control_U.yml``):

* scan ``ecutwfc`` at a **fixed dual** (``ecutrho = dual * ecutwfc``); the scan
  starts at 50 Ry because of the uranium ``f`` channel;
* optionally scan the dual at the largest wavefunction cutoff (the SSSP
  ``nc_dual_scan``); the ACWF protocol default for norm-conserving pseudos is
  dual = 4.

For every cutoff a 7-point EOS is computed for a small, representative subset of
structures (by default the BCC unary and the dioxide).  ``select_cutoffs.py``
then picks the smallest cutoff whose EOS fit is within the SSSP tolerance of the
fit obtained at the reference (largest) cutoff.

Usage
-----

    # dry run of the default scan
    python 2-convergence/run_cutoff_convergence.py --pseudos sr

    # submit it
    python 2-convergence/run_cutoff_convergence.py --pseudos sr --run

    # both pseudos with the denser SSSP "standard" scan
    python 2-convergence/run_cutoff_convergence.py --pseudos sr fr --scan standard --run

    # additionally scan the dual at the largest wavefunction cutoff
    python 2-convergence/run_cutoff_convergence.py --pseudos sr --duals 3 4 6 8 --run

    # follow up
    python 2-convergence/select_cutoffs.py --pseudos sr fr
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

warnings.filterwarnings('ignore', message=r'Found unrecognised key in overrides: .*')

#: ``ecutwfc`` scans (Ry) of the SSSP control protocol.
SCANS = {
    'test': [60, 100, 200],
    'quick': [50, 60, 75, 100, 150, 200],
    'standard': [50, 55, 60, 65, 70, 75, 80, 90, 100, 120, 150, 200],
}

#: Default dual for norm-conserving pseudopotentials in the ACWF protocol.
DEFAULT_DUAL = 4.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--run', action='store_true', help='Actually submit. Default is a dry run.')
    parser.add_argument('--pseudos', nargs='+', default=sorted(config.PSEUDOS), choices=sorted(config.PSEUDOS))
    parser.add_argument('--scan', default='quick', choices=sorted(SCANS),
                        help=f"Cutoff scan preset (default: quick). Available: {sorted(SCANS)}")
    parser.add_argument('--cutoffs', nargs='+', type=float, default=None,
                        help='Explicit list of ecutwfc values (Ry); overrides --scan.')
    parser.add_argument('--dual', type=float, default=DEFAULT_DUAL,
                        help=f"ecutrho / ecutwfc ratio (default: {DEFAULT_DUAL}).")
    parser.add_argument('--duals', nargs='+', type=float, default=None,
                        help='Additional duals to scan at the largest wavefunction cutoff '
                             '(the SSSP nc_dual_scan).')
    parser.add_argument('--configurations', nargs='+',
                        default=list(getattr(config, 'VERIFICATION_CONFIGURATIONS', ['X/BCC', 'XO2'])),
                        help='Structures used for the scan (default: the configurations this '
                             'project verifies).')
    parser.add_argument('--standard', default=std.DEFAULT_STANDARD, choices=sorted(std.STANDARDS))
    parser.add_argument('--max-concurrent', type=int, default=config.MAX_CONCURRENT)
    parser.add_argument('--max-memory-gb', type=float, default=None,
                        help='Request this much memory per node (GB) for every calculation of the '
                             'scan, i.e. `#SBATCH --mem=`. The partition default (872 MB per core, '
                             'so ~49 GB for 56 cores) is not enough for the largest cells at the '
                             'highest cutoffs of the scan.')
    return parser.parse_args()


def make_controller_class():
    from aiida import orm
    from aiida.plugins import WorkflowFactory
    from aiida_submission_controller import FromGroupSubmissionController

    class ConvergenceSubmissionController(FromGroupSubmissionController):
        """Submit the EOS workchains of one convergence point."""

        def __init__(self, code_label, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._code = orm.load_code(code_label)
            self._process_class = WorkflowFactory('common_workflows.eos')

        def set_point(self, pseudo_key, standard, cutoffs, options=None):
            self._pseudo_key = pseudo_key
            self._standard = standard
            self._cutoffs = cutoffs
            self._options = options

        def get_extra_unique_keys(self):
            return ['element', 'configuration']

        def get_inputs_and_processclass_from_extras(self, extras_values):
            structure = self.get_parent_node_from_extras(extras_values)
            inputs = util.build_eos_inputs(
                structure,
                self._pseudo_key,
                self._standard,
                cutoffs=self._cutoffs,
                spin_orbit=False,
                options=self._options,
            )
            return inputs, self._process_class

    return ConvergenceSubmissionController


def scan_points(args) -> list:
    """Return the ``(ecutwfc, ecutrho, dual)`` points of the scan."""
    ecuts = args.cutoffs if args.cutoffs else SCANS[args.scan]
    points = [(float(ecut), float(ecut) * args.dual, float(args.dual)) for ecut in ecuts]
    if args.duals:
        reference_ecut = max(ecuts)
        for dual in args.duals:
            point = (float(reference_ecut), float(reference_ecut) * float(dual), float(dual))
            if point not in points:
                points.append(point)
    points.sort(key=lambda item: (item[0], item[2]))
    return points


def main() -> int:
    args = parse_args()
    util.load_profile()

    from aiida import orm

    standard = std.get_standard(args.standard)

    available = util.source_structures()
    subset = util.filter_structures(available, args.configurations)
    if not subset:
        print('ERROR: no structure selected for the scan.', file=sys.stderr)
        return 1

    points = scan_points(args)

    print('=' * 78)
    print('Cutoff convergence scan (SSSP control protocol)')
    print('=' * 78)
    print(f"  profile        : {config.AIIDA_PROFILE}")
    print(f"  code           : {config.CODE_LABEL}")
    print(f"  standard       : {standard['name']} (k-points and thresholds unchanged)")
    print(f"  structures     : {[util.structure_key(node) for node in subset]}")
    print(f"  scan points    : {[(e, r, d) for e, r, d in points]}")
    print(f"  dry run        : {not args.run}")
    print()

    controller_class = make_controller_class()
    exit_code = 0

    for pseudo_key in args.pseudos:
        spec = config.PSEUDOS[pseudo_key]
        name = util.set_name(pseudo_key)

        # When only a subset of the structures is requested, use a *dedicated* parent group
        # for it: the controller iterates over the parent group, so re-using the shared
        # convergence-structures group would silently submit every structure ever added to it
        # (that is how a two-system scan once launched ten systems per cutoff).
        if args.configurations:
            tag = 'selected-' + '-'.join(configuration.replace('/', '_')
                                         for configuration in args.configurations)
            structures_label = f'{util.convergence_structures_group_label(name)}/{tag}'
        else:
            structures_label = util.convergence_structures_group_label(name)
        group, _ = orm.Group.collection.get_or_create(label=structures_label)
        group.add_nodes(subset)
        print('-' * 78)
        print(f"{spec['description']}  (set '{name}')")
        print(f"  scan structures group: {structures_label} ({len(group.nodes)} node(s))")
        print('-' * 78)

        for ecutwfc, ecutrho, dual in points:
            cutoffs = {'U': (ecutwfc, ecutrho), 'O': config.O_CUTOFFS}
            group_label = util.convergence_group_label(name, ecutwfc, dual)
            controller = controller_class(
                code_label=config.CODE_LABEL,
                parent_group_label=structures_label,
                group_label=group_label,
                max_concurrent=args.max_concurrent,
            )
            options = dict(config.COMPUTER_OPTIONS)
            if args.max_memory_gb is not None:
                options['max_memory_kb'] = int(args.max_memory_gb * 1024 * 1024)
            controller.set_point(pseudo_key, standard, cutoffs, options=options)

            print(f"  ecutwfc={ecutwfc:>6g} Ry  ecutrho={ecutrho:>7g} Ry (dual {dual:g})")
            print(f"    group        : {group_label}")
            print(f"    already run  : {controller.num_already_run}   "
                  f"active: {controller.num_active_slots}   to run: {controller.num_to_run}")

            run_processes = controller.submit_new_batch(dry_run=not args.run)
            for extras, process in run_processes.items():
                # `extras` is the tuple of unique extra values, e.g. ('U', 'X/BCC');
                # never run dict() on it.
                extras_str = tuple(extras) if isinstance(extras, (tuple, list)) else extras
                if process is None:
                    print(f"      {extras_str} --> to be run")
                else:
                    print(f"      {extras_str} --> pk = {process.pk}")
            if not run_processes:
                print('      nothing to do')

    print()
    if not args.run:
        print('This was a DRY RUN. Add --run to actually submit the workchains.')
    else:
        print('Submitted. Once the EOS workchains are finished run:')
    print('  python 2-convergence/select_cutoffs.py --pseudos ' + ' '.join(args.pseudos))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
