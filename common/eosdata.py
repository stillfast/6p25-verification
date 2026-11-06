"""Extraction of EOS data points and Birch-Murnaghan fits from AiiDA nodes.

The logic mirrors ``acwf-verification-scripts/3-analyze/get_results.py`` so that
the JSON files produced by this project use the same format (and could be fed to
the official plotting/analysis scripts).  The fit itself is the untouched
``eosfit_31_adapted.py`` from the official repository.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from common.eosfit_31_adapted import BM, echarge
from common.quantities_for_comparison import birch_murnaghan

#: Minimum fraction of the EOS volumes that must be available to attempt a fit
#: when a workchain did not finish cleanly.
MIN_VOLUME_FRACTION = 0.8


def eos_ascii_block(system_key: str, rows, volumes, reference=None, indent: str = '  ') -> str:
    """Render the EOS curves of one system as text.

    ``rows`` is a sequence of ``(label, energies_per_atom)`` and ``volumes`` the matching
    volumes per atom; every row must already be shifted to the minimum of its own
    Birch-Murnaghan fit, exactly like the plotted curves, so the rows can be compared
    point by point. ``reference`` is an optional ``(fit, natoms_in_cell)`` tuple of the
    all-electron average, evaluated on the same volumes: that is the curve Δ integrates
    against, so having it next to ours makes the metric readable by eye.

    This exists because a PNG cannot be read from a terminal, and because a shape that is
    shifted, flat or asymmetric is the fastest way to see *why* a Δ is large.
    """
    out = [f'{indent}{system_key}   (E − E₀ of each fit, meV/atom; volumes per atom in Å³)',
           f'{indent}  ' + ' ' * 10 + ' '.join(f'{value:8.3f}' for value in volumes)]
    for label, values in rows:
        out.append(f'{indent}  {label:<9}' + ' '.join(f'{value:8.2f}' for value in values))
    if reference is not None:
        fit, natoms = reference
        if fit:
            curve = birch_murnaghan(np.asarray(volumes, dtype=float), 0.0,
                                    fit['min_volume'] / natoms, fit['bulk_modulus_ev_ang3'],
                                    fit['bulk_deriv']) * 1000.0
            out.append(f'{indent}  {"AE ref":<9}' + ' '.join(f'{value:8.2f}' for value in curve))
    return '\n'.join(out)


def _outgoing(node, **kwargs):
    """``get_outgoing`` that avoids the aiida-core 2.8 deprecation warning."""
    try:
        return node.base.links.get_outgoing(**kwargs)
    except AttributeError:
        return node.get_outgoing(**kwargs)


def _iter_called_workchains(node):
    from aiida.common import LinkType

    return _outgoing(node, link_type=LinkType.CALL_WORK).all()


def collect_eos(node) -> Dict[str, Any]:
    """Return the EOS data points of an ``EquationOfStateWorkChain`` node.

    Handles the three cases of the official script: a cleanly finished workchain,
    a failed one from which at least 80 % of the volumes were still recovered,
    and everything else (still running / too broken to be used).
    """
    from aiida.common import LinkType, NotExistentAttributeError

    result: Dict[str, Any] = {
        'volumes': [],
        'energies': [],
        'num_atoms': None,
        'num_attempt_vols': 0,
        'usable': False,
        'state': node.process_state.value,
        'exit_status': None,
    }

    if node.process_state.value == 'finished':
        result['exit_status'] = node.exit_status

    if node.process_state.value == 'finished' and node.exit_status == 0:
        outputs = _outgoing(node, link_type=LinkType.RETURN).nested()
        for index, sub_structure in sorted(outputs['structures'].items()):
            if result['num_atoms'] is None:
                result['num_atoms'] = len(sub_structure.sites)
            result['volumes'].append(sub_structure.get_cell_volume())
            result['energies'].append(outputs['total_energies'][index].value)
        result['num_attempt_vols'] = len(result['volumes'])
        result['usable'] = True
        return result

    # Failed, or still running: try to salvage the volumes that did complete.
    for triple in _iter_called_workchains(node):
        sub = triple.node
        result['num_attempt_vols'] += 1
        if not sub.is_finished_ok:
            continue
        try:
            natoms = len(sub.outputs.relaxed_structure.sites)
        except NotExistentAttributeError:
            break
        if result['num_atoms'] is None:
            result['num_atoms'] = natoms
        result['volumes'].append(sub.outputs.relaxed_structure.get_cell_volume())
        result['energies'].append(sub.outputs.total_energy.value)

    if result['num_attempt_vols'] and (
        len(result['volumes']) / float(result['num_attempt_vols']) >= MIN_VOLUME_FRACTION
    ):
        result['usable'] = True

    return result


def fit_birch_murnaghan(volumes: List[float], energies: List[float]) -> Optional[Dict[str, float]]:
    """Fit a third-order Birch-Murnaghan EOS, exactly as the official script does."""
    if len(volumes) < 3:
        return None

    order = np.argsort(volumes)
    volumes = list(np.asarray(volumes)[order])
    energies = list(np.asarray(energies)[order])

    data = (np.array([volumes, energies]).T).tolist()

    try:
        min_volume, e0, bulk_modulus_internal, bulk_deriv, residuals = BM(np.array(data))
    except (ValueError, np.linalg.LinAlgError):
        # No minimum inside the computed volume range, or a degenerate fit.
        return None

    bulk_modulus_gpa = bulk_modulus_internal * echarge * 1.0e21
    # 1 eV/Angstrom^3 = 160.21766208 GPa
    bulk_modulus_ev_ang3 = bulk_modulus_gpa / 160.21766208

    # `numpy.polyfit(..., full=True)` returns an EMPTY array as the residual sum of
    # squares whenever the polynomial fits the data exactly (a 4-point EOS fitted
    # with a cubic, i.e. every production EOS of this project, or any
    # rank-deficient fit).  The official script does `residuals[0]` and crashes in
    # that case; report 0.0 instead.
    residual_array = np.atleast_1d(np.asarray(residuals, dtype=float))
    residual_value = float(residual_array[0]) if residual_array.size else 0.0

    return {
        'min_volume': float(min_volume),
        'E0': float(e0),
        'bulk_modulus_ev_ang3': float(bulk_modulus_ev_ang3),
        'bulk_deriv': float(bulk_deriv),
        'residuals': residual_value,
    }


def eos_payload(node) -> Dict[str, Any]:
    """Return an official-format payload for a single EOS workchain."""
    collected = collect_eos(node)

    payload: Dict[str, Any] = {
        'state': collected['state'],
        'exit_status': collected['exit_status'],
        'eos_data': None,
        'BM_fit_data': None,
        'num_atoms_in_sim_cell': collected['num_atoms'],
        'missing_outputs': None,
        'completely_off': None,
    }

    if not collected['usable'] or not collected['volumes']:
        return payload

    volumes = collected['volumes']
    energies = collected['energies']

    sorted_pairs = sorted(zip(volumes, energies))
    sorted_volumes = [pair[0] for pair in sorted_pairs]
    sorted_energies = [pair[1] for pair in sorted_pairs]

    payload['eos_data'] = np.array([sorted_volumes, sorted_energies]).T.tolist()
    payload['missing_outputs'] = collected['num_attempt_vols'] - len(sorted_volumes)

    # Was the energy minimum on the very edge of the computed volume range?
    min_loc = int(np.array(sorted_energies).argmin())
    if min_loc == 0:
        payload['completely_off'] = 'left'
    elif min_loc == len(sorted_energies) - 1:
        payload['completely_off'] = 'right'

    payload['BM_fit_data'] = fit_birch_murnaghan(sorted_volumes, sorted_energies)
    return payload


def volume_per_formula_unit(bm_fit: Dict[str, float], natoms_cell: int, natoms_formula_unit: int) -> float:
    """Return V0 normalised per formula unit (the official convention)."""
    scaling = natoms_cell / float(natoms_formula_unit)
    return bm_fit['min_volume'] / scaling


def delta_per_atom(
    pseudo_v0: float,
    pseudo_b0: float,
    pseudo_b1: float,
    reference_v0: float,
    reference_b0: float,
    reference_b1: float,
    natoms_formula_unit: int,
) -> float:
    """Return the ACWF ``delta`` metric in meV/atom.

    ``quantities_for_comparison.delta`` expects volumes normalised per formula
    unit and returns an energy per formula unit; dividing by the number of atoms
    in the formula unit converts it to meV/atom.
    """
    from common.quantities_for_comparison import delta

    value = delta(
        pseudo_v0, pseudo_b0, pseudo_b1,
        reference_v0, reference_b0, reference_b1,
        1.0,
        1.0 / 20.0,
        1.0 / 400.0,
    )
    return float(value) / float(natoms_formula_unit)


def nu_metric(
    pseudo_v0: float, pseudo_b0: float, pseudo_b1: float,
    reference_v0: float, reference_b0: float, reference_b1: float,
) -> float:
    """Return the ACWF ``nu`` metric in percent."""
    from common.quantities_for_comparison import nu

    value = nu(
        pseudo_v0, pseudo_b0, pseudo_b1,
        reference_v0, reference_b0, reference_b1,
        100.0,
        1.0 / 20.0,
        1.0 / 400.0,
    )
    return float(value)


def epsilon_metric(
    pseudo_v0: float, pseudo_b0: float, pseudo_b1: float,
    reference_v0: float, reference_b0: float, reference_b1: float,
) -> float:
    """Return the ACWF ``epsilon`` metric (dimensionless)."""
    from common.quantities_for_comparison import epsilon

    value = epsilon(
        pseudo_v0, pseudo_b0, pseudo_b1,
        reference_v0, reference_b0, reference_b1,
        1.0,
        1.0 / 20.0,
        1.0 / 400.0,
    )
    return float(value)


def epsilon_between_fits(fit_a: Dict[str, float], fit_b: Dict[str, float]) -> float:
    """``epsilon`` (dimensionless) between two BM fits of the *same* system.

    The sibling of :func:`nu_between_fits`, used by the cutoff convergence scan when the
    criterion is the area between the two EOS curves rather than the distance between the
    fitted (V0, B0, B1).  Like ``nu`` it needs no per-formula-unit normalisation because
    both fits describe the same cell.
    """
    return epsilon_metric(
        fit_a['min_volume'], fit_a['bulk_modulus_ev_ang3'], fit_a['bulk_deriv'],
        fit_b['min_volume'], fit_b['bulk_modulus_ev_ang3'], fit_b['bulk_deriv'],
    )


def nu_between_fits(fit_a: Dict[str, float], fit_b: Dict[str, float]) -> float:
    """``nu`` (percent) between two BM fits of the *same* system.

    Used by the cutoff convergence scan, where both fits describe the same cell,
    so no per-formula-unit normalisation is needed.
    """
    return nu_metric(
        fit_a['min_volume'], fit_a['bulk_modulus_ev_ang3'], fit_a['bulk_deriv'],
        fit_b['min_volume'], fit_b['bulk_modulus_ev_ang3'], fit_b['bulk_deriv'],
    )
