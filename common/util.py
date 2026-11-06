"""Shared AiiDA helpers for the U-14ve pseudopotential verification workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

# Make ``import config`` / ``import common.*`` work no matter where the script is
# started from (``python 3-submit/launch_calculations_qe.py``, ``verdi run``, ...).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402

SET_SUFFIX = 'verification-PBE-v1'
PLUGIN_NAME = (PROJECT_ROOT / 'plugin_name.txt').read_text().strip()


# ---------------------------------------------------------------------------
# Profile and naming
# ---------------------------------------------------------------------------


def load_profile():
    """Load the AiiDA profile in which everything is run."""
    from aiida import load_profile as _load_profile

    return _load_profile(config.AIIDA_PROFILE)


def set_name(pseudo_key: str, spin_orbit: bool = False, suffix: Optional[str] = None) -> str:
    """Return the ACWF 'set name' of a run.

    Each pseudopotential gets its own set, which mirrors the ACWF convention of
    one AiiDA group per verification set and keeps the EOS workchains, the
    results JSON and the plots of the two pseudopotentials fully separated.
    ``suffix`` is only used by the ``--smoke-test`` mode of the launcher, which
    must not mix with the production sets.
    """
    key = pseudo_key.lower()
    if key not in config.PSEUDOS:
        raise ValueError(f"Unknown pseudo key {pseudo_key!r}. Known: {sorted(config.PSEUDOS)}")
    tag = f'{key}-soc' if spin_orbit else key
    return f'{getattr(config, "SET_PREFIX", "u14ve")}-{tag}-{suffix or SET_SUFFIX}'


def structures_group_label(name: str) -> str:
    return f'acwf-verification/{name}/structures/{PLUGIN_NAME}'


def workflows_group_label(name: str) -> str:
    return f'acwf-verification/{name}/workflows/{PLUGIN_NAME}'


def pseudo_group_label(name: str) -> str:
    return f'acwf-verification/{name}/pseudo/{PLUGIN_NAME}'


def _number_tag(value: float) -> str:
    return f'{value:g}'.replace('.', 'p')


def convergence_group_label(name: str, ecutwfc: float, dual: float) -> str:
    """Group label of one convergence point, e.g. ``.../ecut-100-dual-4``."""
    return (
        f'acwf-verification/{name}/convergence/{PLUGIN_NAME}/'
        f'ecut-{_number_tag(ecutwfc)}-dual-{_number_tag(dual)}'
    )


def parse_convergence_group_label(label: str) -> Optional[tuple]:
    """Inverse of :func:`convergence_group_label`; returns ``(sort_key, ecut, dual)``."""
    tail = label.rsplit('/', 1)[-1]
    if not tail.startswith('ecut-') or '-dual-' not in tail:
        return None
    ecut_part, dual_part = tail[len('ecut-'):].split('-dual-', 1)
    try:
        ecut = float(ecut_part.replace('p', '.'))
        dual = float(dual_part.replace('p', '.'))
    except ValueError:
        return None
    return ecut, dual


def convergence_structures_group_label(name: str) -> str:
    return f'acwf-verification/{name}/convergence-structures/{PLUGIN_NAME}'



# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------


def element_of_kind(kind_name: str) -> str:
    """Strip the trailing index that AiiDA appends to duplicated kinds."""
    stripped = kind_name.rstrip('0123456789')
    return stripped or kind_name


def source_structures() -> List[Any]:
    """Return the ten uranium verification structures from the source group."""
    from aiida import orm

    try:
        group = orm.load_group(config.SOURCE_STRUCTURES_GROUP)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"ERROR: cannot load the source structures group "
            f"'{config.SOURCE_STRUCTURES_GROUP}': {exc}\n"
            f"Set U14VE_SOURCE_STRUCTURES_GROUP to the right label."
        ) from exc

    nodes = list(group.nodes)
    if not nodes:
        raise SystemExit(f"ERROR: group '{config.SOURCE_STRUCTURES_GROUP}' is empty.")
    return nodes


def filter_structures(nodes: Iterable[Any], configurations: Optional[Sequence[str]] = None) -> List[Any]:
    """Keep the structures whose ``configuration`` extra is in ``configurations``."""
    if configurations is None:
        return sorted(nodes, key=lambda node: config.ALL_CONFIGURATIONS.index(node.base.extras.get('configuration'))
                      if node.base.extras.get('configuration') in config.ALL_CONFIGURATIONS else 999)

    wanted = list(configurations)
    unknown = [c for c in wanted if c not in config.ALL_CONFIGURATIONS]
    if unknown:
        raise SystemExit(
            f"ERROR: unknown configuration(s) {unknown}. Known: {list(config.ALL_CONFIGURATIONS)}"
        )

    selected = [node for node in nodes if node.base.extras.get('configuration') in wanted]
    selected.sort(key=lambda node: wanted.index(node.base.extras.get('configuration')))
    return selected


def structure_key(node: Any) -> str:
    """Return the ACWF ``element-configuration`` key of a structure."""
    return f"{node.base.extras.get('element')}-{node.base.extras.get('configuration')}"


# ---------------------------------------------------------------------------
# Pseudopotentials
# ---------------------------------------------------------------------------


def load_pseudo_nodes(pseudo_key: str) -> Dict[str, Any]:
    """Return ``{element: UpfData}`` of the family belonging to ``pseudo_key``."""
    from aiida_pseudo.groups.family import CutoffsPseudoPotentialFamily

    label = config.PSEUDOS[pseudo_key]['family']
    try:
        family = CutoffsPseudoPotentialFamily.collection.get(label=label)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"ERROR: pseudo family '{label}' is not installed. "
            f"Run 1-preliminary/install_pseudos.py first."
        ) from exc

    nodes: Dict[str, Any] = {}
    for node in family.nodes:
        element = getattr(node, 'element', None) or node.base.attributes.get('element', '').strip()
        nodes[element] = node
    return nodes


def pseudos_for_structure(pseudo_nodes: Mapping[str, Any], structure: Any) -> Dict[str, Any]:
    """Map every kind name of ``structure`` onto its ``UpfData`` node."""
    mapping: Dict[str, Any] = {}
    missing = []
    for kind in structure.get_kind_names():
        element = element_of_kind(kind)
        if element not in pseudo_nodes:
            missing.append(element)
        else:
            mapping[kind] = pseudo_nodes[element]
    if missing:
        raise SystemExit(
            f"ERROR: no pseudopotential for element(s) {sorted(set(missing))} in the family. "
            f"Available: {sorted(pseudo_nodes)}"
        )
    return mapping


# ---------------------------------------------------------------------------
# Cutoffs
# ---------------------------------------------------------------------------


def cutoffs_file() -> Path:
    return config.OUTPUTS_DIR.parent.parent / '2-convergence' / 'cutoffs.json'


def cutoff_scan_status(pseudo_key: str):
    """``(converged, tested_points)`` of the cutoff scan of a pseudopotential.

    ``converged`` is ``None`` when the scan has never been run for this key, ``False``
    when ``select_cutoffs.py`` recorded that no scan point met the criterion -- in that
    case the cutoffs in ``cutoffs.json`` are a fallback (the project default) and every
    quantity computed with them carries an unknown cutoff error. Readers are warned
    rather than stopped, because a scan that does not converge is itself a result.
    """
    path = cutoffs_file()
    if not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None, None
    meta = payload.get(pseudo_key, {}).get('_meta', {})
    entry = payload.get(pseudo_key, {}).get('U', {})
    if not entry:
        return None, None
    return entry.get('converged'), meta.get('tested_points')


def load_cutoffs(pseudo_key: str, explicit: Optional[Mapping[str, Sequence[float]]] = None) -> Dict[str, tuple]:
    """Return ``{element: (ecutwfc, ecutrho)}`` for the given pseudopotential.

    Priority: explicit argument > ``2-convergence/cutoffs.json`` > the
    ``default_cutoffs`` of :data:`config.PSEUDOS`.  Oxygen always uses
    :data:`config.O_CUTOFFS`.
    """
    result: Dict[str, tuple] = {'O': tuple(float(v) for v in config.O_CUTOFFS)}

    if explicit is not None:
        for element, pair in explicit.items():
            result[element] = (float(pair[0]), float(pair[1]))
        return result

    path = cutoffs_file()
    if path.exists():
        try:
            payload = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            payload = {}
        entry = payload.get(pseudo_key, {}).get('U')
        if entry:
            result['U'] = (float(entry['ecutwfc']), float(entry['ecutrho']))
            return result

    for element, pair in config.PSEUDOS[pseudo_key].get('default_cutoffs', {}).items():
        result[element] = (float(pair[0]), float(pair[1]))
    return result


# ---------------------------------------------------------------------------
# EOS inputs
# ---------------------------------------------------------------------------


def build_sub_process(
    structure: Any,
    pseudos: Mapping[str, Any],
    cutoffs: Mapping[str, Sequence[float]],
    standard: Mapping[str, Any],
    spin_orbit: bool = False,
    kpoints_distance: Optional[float] = None,
) -> Dict[str, Any]:
    """Return the ``sub_process`` overrides that pin the whole standard.

    The ACWF input generator is code-agnostic and is still asked to build the
    sub-process; these overrides then replace what it produced with the exact
    pseudopotentials, cutoffs and convergence thresholds of the standard.  Doing
    it here (instead of relying on the ``verification-PBE-v1`` YAML section)
    makes the run independent of the plugin protocol defaults *and* keeps the
    standard visible in the provenance of every calculation.

    .. note::
        Only ``base_relax`` is overridden.  ``base_init_relax`` is a
        Quantum ESPRESSO >= 5.0 pre-relaxation SCF that is useless for
        ``relax_type = NONE``; overriding it would re-introduce the namespace
        for runs where the optional generator patch removes it.
    """
    from aiida import orm

    from common.standard import build_pw_parameters, effective_cutoffs

    natoms = len(structure.sites)
    ecutwfc, ecutrho = effective_cutoffs(cutoffs, config.O_CUTOFFS)
    parameters = build_pw_parameters(natoms, (ecutwfc, ecutrho), standard, spin_orbit=spin_orbit)

    # NOTE: `meta_parameters` (the per-atom convergence thresholds of the ACWF
    # protocol) is deliberately *not* injected here.  In aiida-quantumespresso
    # 5.x it is not an input port of `PwBaseWorkChain`: it is consumed by
    # `get_builder_from_protocol`, which turns it into `CONTROL.etot_conv_thr`
    # and `ELECTRONS.conv_thr`.  Setting it on the builder adds a stray dynamic
    # input whose float values make the input validation of the sub-process fail
    # at submission time.  The thresholds are recorded where they matter, in
    # `parameters` below.
    overrides: Dict[str, Any] = {
        'base_relax': {
            'kpoints_distance': float(
                standard['kpoints_distance'] if kpoints_distance is None else kpoints_distance
            ),
            'pw': {
                'pseudos': dict(pseudos),
                'parameters': orm.Dict(dict=parameters),
            },
        }
    }

    # Delete the remote scratch of each calculation after it has been retrieved.
    if config.CLEAN_REMOTE_SCRATCH:
        overrides['clean_workdir'] = True

    return overrides


def build_generator_inputs(standard: Mapping[str, Any], code_label: Optional[str] = None,
                           options: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return the code-agnostic ``generator_inputs`` of the EOS workchain."""
    from aiida_common_workflows.common import ElectronicType, RelaxType, SpinType

    return {
        'engines': {
            'relax': {
                'code': code_label or config.CODE_LABEL,
                'options': dict(options if options is not None else config.COMPUTER_OPTIONS),
            }
        },
        # The ACWF protocol name is kept for provenance/consistency; the actual
        # standard is enforced through the `sub_process` overrides, see
        # `build_sub_process`.  `spin_type` stays NONE even for the spin-orbit
        # mode because the generator only supports NONE/COLLINEAR and the
        # noncolinear flags are set directly in the pw parameters.
        'protocol': 'verification-PBE-v1',
        'relax_type': RelaxType.NONE,
        'electronic_type': ElectronicType.METAL,
        'spin_type': SpinType.NONE,
    }


def build_eos_inputs(
    structure: Any,
    pseudo_key: str,
    standard: Mapping[str, Any],
    cutoffs: Optional[Mapping[str, Sequence[float]]] = None,
    spin_orbit: bool = False,
    code_label: Optional[str] = None,
    options: Optional[Mapping[str, Any]] = None,
    kpoints_distance: Optional[float] = None,
) -> Dict[str, Any]:
    """Return the complete input dictionary of an ``EquationOfStateWorkChain``."""
    from aiida_common_workflows.plugins import (
        get_entry_point_name_from_class,
        load_workflow_entry_point,
    )

    if cutoffs is None:
        cutoffs = load_cutoffs(pseudo_key)

    pseudo_nodes = load_pseudo_nodes(pseudo_key)
    pseudos = pseudos_for_structure(pseudo_nodes, structure)

    sub_process_cls = load_workflow_entry_point('relax', 'quantum_espresso')
    sub_process_cls_name = get_entry_point_name_from_class(sub_process_cls).name

    return {
        'structure': structure,
        'generator_inputs': build_generator_inputs(standard, code_label=code_label, options=options),
        'sub_process_class': sub_process_cls_name,
        'sub_process': build_sub_process(
            structure, pseudos, cutoffs, standard,
            spin_orbit=spin_orbit, kpoints_distance=kpoints_distance,
        ),
        'scale_count': int(standard['scale_count']),
        'scale_increment': float(standard['scale_increment']),
    }
