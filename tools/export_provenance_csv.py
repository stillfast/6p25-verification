#!/usr/bin/env python
"""Export the PK and UUID of every process node of a verification project to CSV.

The workflow keeps its results in JSON files, but a JSON file does not tell you *which*
AiiDA node produced a number.  This tool writes that mapping, so that any result can be
traced back with ``verdi process show <pk>`` / ``verdi process report <pk>`` — including
the convergence scan and the production submission, which live in different AiiDA groups.

One row per process node, with the full ancestry:

    part           convergence | submit
    set            the AiiDA set name (e.g. ``ai6p25v-6p25-verification-PBE-v1``)
    group          the group the EOS workchain belongs to
    ecutwfc/dual   for ``convergence`` rows, parsed from the group label; empty for ``submit``
    system         the structure key of the EOS workchain (e.g. ``O2U-XO2``)
    level          ``eos`` | ``sub_workchain`` | ``pw_base`` | ``pw_calculation``
                           (the ACWF EOS workchain calls a relax sub-workchain, which calls
                            a PwBaseWorkChain, which calls the ``pw.x`` calculation)
    label          the process class label
    pk, uuid       the node identity
    state          process state (``finished``, ``waiting``, ``killed``, …)
    exit_status    exit status of finished processes
    ctime, mtime   creation / last-modification time
    remote_workdir for calculations, if it is still recorded
    pseudos        for calculations, the pseudopotential file names that were used
    kpoints        for calculations, the k-point mesh

Usage
-----

    python tools/export_provenance_csv.py                      # all configured pseudos
    python tools/export_provenance_csv.py --pseudos 6p25
    python tools/export_provenance_csv.py --parts convergence
    python tools/export_provenance_csv.py --output-dir /tmp

Output: ``<output-dir>/provenance-<part>.csv`` plus a combined
``provenance-all.csv``; the default output directory is ``4-analyze/outputs``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import util  # noqa: E402

FIELDS = ['part', 'set', 'group', 'ecutwfc', 'dual', 'system', 'level', 'label',
          'pk', 'uuid', 'parent_pk', 'state', 'exit_status', 'ctime', 'mtime',
          'remote_workdir', 'pseudos', 'kpoints']


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=sorted(config.PSEUDOS),
                        choices=sorted(config.PSEUDOS))
    parser.add_argument('--parts', nargs='+', default=['convergence', 'submit'],
                        choices=['convergence', 'submit'])
    parser.add_argument('--output-dir', type=Path, default=config.OUTPUTS_DIR)
    parser.add_argument('--include-killed', action='store_true', default=True,
                        help='Include workchains that were killed or failed (default: yes, '
                             'their PKs are part of the provenance of a scan).')
    parser.add_argument('--only-ok', action='store_true',
                        help='Keep only processes that finished with exit status 0.')
    return parser.parse_args()


def calculation_details(node) -> tuple:
    """``(remote_workdir, pseudos, kpoints)`` of a CalcJob node, best effort."""
    remote = node.base.attributes.get('remote_workdir', '')
    pseudos, kpoints = '', ''
    try:
        pseudos = ','.join(sorted(t.node.filename for t in node.base.links.get_incoming().all()
                                  if t.link_label.startswith('pseudos')))
    except Exception:  # noqa: BLE001
        pass
    try:
        kpoints = 'x'.join(str(value) for value in node.inputs.kpoints.get_kpoints_mesh()[0])
    except Exception:  # noqa: BLE001
        pass
    return remote, pseudos, kpoints


def rows_for_eos(node, part: str, set_name: str, group_label: str, ecutwfc='', dual=''):
    """One row per process node of an EOS workchain, walking the whole call tree.

    The ACWF EOS workchain nests several workchains before a ``pw.x`` calculation appears
    (``EquationOfStateWorkChain`` -> ``QuantumEspressoCommonRelaxWorkChain`` ->
    ``PwRelaxWorkChain`` -> ``PwBaseWorkChain`` -> ``PwCalculation``), so the walk is
    recursive instead of assuming a fixed depth: ``level`` reports the depth
    (``eos``, ``work_chain_L1`` … , ``calculation_L4``) and ``label`` names the class.
    ``parent_pk`` makes the tree reconstructible from the CSV alone.
    """
    from aiida.common.links import LinkType

    system = node.base.extras.get('configuration', node.base.extras.get('element', ''))
    common = {'part': part, 'set': set_name, 'group': group_label,
              'ecutwfc': ecutwfc, 'dual': dual, 'system': system}
    rows = []

    def emit(process, level: str, parent_pk):
        entry = dict(common, level=level, label=process.process_label,
                     pk=process.pk, uuid=str(process.uuid), parent_pk=parent_pk,
                     state=process.process_state.value if process.process_state else '',
                     exit_status='' if process.exit_status is None else process.exit_status,
                     ctime=process.ctime.isoformat(timespec='seconds'),
                     mtime=process.mtime.isoformat(timespec='seconds'),
                     remote_workdir='', pseudos='', kpoints='')
        if process.process_type and 'calculations:quantum' in process.process_type:
            entry['remote_workdir'], entry['pseudos'], entry['kpoints'] = calculation_details(process)
        rows.append(entry)

    def walk(process, depth: int, parent_pk):
        for outgoing in process.base.links.get_outgoing(link_type=LinkType.CALL_WORK).all():
            child = outgoing.node
            emit(child, f'work_chain_L{depth + 1}', process.pk)
            walk(child, depth + 1, child.pk)
        for outgoing in process.base.links.get_outgoing(link_type=LinkType.CALL_CALC).all():
            child = outgoing.node
            emit(child, f'calculation_L{depth + 1}', process.pk)

    emit(node, 'eos', '')
    walk(node, 0, node.pk)
    return rows


def collect(pseudo_key: str, parts) -> list:
    from aiida import orm

    set_name = util.set_name(pseudo_key)
    rows = []

    if 'convergence' in parts:
        groups = sorted(
            (g.label for g in orm.Group.collection.all()
             if g.label.startswith(f'acwf-verification/{set_name}/convergence/')),
        )
        for label in groups:
            parsed = util.parse_convergence_group_label(label)
            if parsed is None:
                continue
            ecutwfc, dual = parsed
            for node in orm.load_group(label).nodes:
                if node.process_type != 'aiida.workflows:common_workflows.eos':
                    continue
                rows.extend(rows_for_eos(node, 'convergence', set_name, label,
                                         ecutwfc=f'{ecutwfc:g}', dual=f'{dual:g}'))

    if 'submit' in parts:
        label = util.workflows_group_label(set_name)
        try:
            group = orm.load_group(label)
        except Exception:  # noqa: BLE001
            group = None
        if group is not None:
            for node in group.nodes:
                if node.process_type != 'aiida.workflows:common_workflows.eos':
                    continue
                rows.extend(rows_for_eos(node, 'submit', set_name, label))
    return rows


def main() -> int:
    args = parse_args()
    util.load_profile()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    everything = []
    for pseudo_key in args.pseudos:
        rows = collect(pseudo_key, args.parts)
        if args.only_ok:
            ok = {(row['pk']) for row in rows if row['level'] == 'eos' and row['state'] == 'finished'
                  and row['exit_status'] == 0}
            # keep the whole tree of the workchains that finished ok
            keep_systems = {(row['part'], row['group'], row['system']) for row in rows
                            if row['level'] == 'eos' and row['pk'] in ok}
            rows = [row for row in rows
                    if (row['part'], row['group'], row['system']) in keep_systems]
        everything.extend(rows)
        print(f'  {pseudo_key}: {len(rows)} node(s) '
              f'({sum(1 for r in rows if r["level"] == "eos")} EOS workchain(s))')

    for part in ('convergence', 'submit'):
        subset = [row for row in everything if row['part'] == part]
        if not subset:
            continue
        path = args.output_dir / f'provenance-{part}.csv'
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(subset)
        print(f'  wrote {path} ({len(subset)} rows)')

    path = args.output_dir / 'provenance-all.csv'
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(everything)
    print(f'  wrote {path} ({len(everything)} rows)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
