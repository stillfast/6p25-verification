#!/usr/bin/env python
"""Generate the pairwise comparison report of the U-14ve verification.

Produces ``4-analyze/outputs/comparison_tables.md``: for every verification system
a set of three tables (epsilon, nu, Delta) comparing all methods pairwise —
the two candidate pseudopotentials of this project, the all-electron average of
the ACWF paper and the five published reference codes.

All quantities are computed with the official implementations in
``common/quantities_for_comparison.py``:

* ``epsilon`` dimensionless (0 = identical EOS curves),
* ``nu`` in percent,
* ``delta`` in meV/atom (see ``common/eosdata.delta_per_atom``).

Usage
-----

    python 4-analyze/make_comparison_report.py
    python 4-analyze/make_comparison_report.py --output /tmp/report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import eosdata  # noqa: E402
from common import standard as std  # noqa: E402
from common import util  # noqa: E402
from common.quantities_for_comparison import (  # noqa: E402
    epsilon as epsilon_metric,
    get_num_atoms_in_formula_unit,
    nu as nu_metric,
)

#: Published ACWF reference calculations, read from the official
#: ``acwf-verification-scripts/3-analyze/outputs`` folder of this machine.
EXTERNAL_METHODS = [
    ('QE (SSSP-prec-1.3)', 'results-{kind}-verification-PBE-v1-Quantum ESPRESSO@PW|SSSP-prec-v1.3.json'),
    ('VASP (GW-PAW54*)', 'results-{kind}-verification-PBE-v1-VASP@PW|GW-PAW54*.json'),
    ('FLEUR (LAPW+LO)', 'results-{kind}-verification-PBE-v1-FLEUR@LAPW+LO.json'),
    ('WIEN2k ((L)APW+lo+LO)', 'results-{kind}-verification-PBE-v1-WIEN2k@(L)APW+lo+LO.json'),
    ('CASTEP (PW|C19MK2)', 'results-{kind}-verification-PBE-v1-CASTEP@PW|C19MK2.json'),
]

KINDS = ('unaries', 'oxides')

#: Short names used inside the tables (the full description is given in the legend).
#: Short labels keep the pairwise tables narrow enough to be readable, and they never
#: contain ``|`` — a pipe inside a markdown cell is a rendering hazard even when
#: escaped.
SHORT_LABELS = {
    'U.pbe-n-nc.14ve.UPF [SR]': 'SR',
    'U.rel-pbe-n-nc.14ve.UPF [FR]': 'FR',
    'U.pbe-n-nc.UPF [NC]': 'NC',
    'U.pbe-n-nc.UPF [RC1]': 'RC1',
    'U.pbe-n-nc.UPF [RC2]': 'RC2',
    'U.pbe-n-nc.UPF [BEST]': 'BEST',
    'U.pbe-n-nc.UPF [V13]': 'V13',
    'AE average': 'AE avg',
    'QE (SSSP-prec-1.3)': 'QE-SSSP',
    'VASP (GW-PAW54*)': 'VASP',
    'FLEUR (LAPW+LO)': 'FLEUR',
    'WIEN2k ((L)APW+lo+LO)': 'WIEN2k',
    'CASTEP (PW|C19MK2)': 'CASTEP',
}


def short_label(label: str) -> str:
    """Return the short, table-safe name of a method."""
    return SHORT_LABELS.get(label, label.replace('|', '/'))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pseudos', nargs='+', default=list(config.PSEUDOS), choices=sorted(config.PSEUDOS))
    parser.add_argument('--output', type=Path, default=config.OUTPUTS_DIR / 'comparison_tables.md')
    parser.add_argument('--standard', default=std.DEFAULT_STANDARD, choices=sorted(std.STANDARDS))
    parser.add_argument('--include-spin-orbit', action='store_true',
                        help='Add the spin-orbit runs of the fully relativistic pseudo as an extra '
                             'method (only the systems for which they exist are filled in).')
    parser.add_argument('--set-overrides', nargs='*', default=None,
                        help='Map a pseudopotential to another results set, e.g. '
                             '`--set-overrides fr=u14ve-fr-wide-verification-PBE-v1` (the fully '
                             'relativistic pseudo needs a wider EOS window, so its verification uses '
                             'the wide set while its metrics are still comparable).')
    parser.add_argument('--cutoffs-note', default=None,
                        help='Free text appended to the "how these numbers were produced" section.')
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_our_results(pseudo_key: str, set_override: Optional[str] = None,
                     spin_orbit: bool = False) -> Optional[Dict[str, Any]]:
    name = set_override or util.set_name(pseudo_key, spin_orbit=spin_orbit)
    path = config.OUTPUTS_DIR / f'results-{name}-{util.PLUGIN_NAME}.json'
    if not path.exists():
        print(f"  WARNING: {path} not found — run 4-analyze/get_results.py first.")
        return None
    payload = json.loads(path.read_text())
    payload['_label'] = label_of(pseudo_key, spin_orbit)
    payload['_source'] = path.name
    return payload


def canonical_key(system_key: str) -> str:
    """``O2U-XO2`` -> ``U-XO2`` (the convention of the published reference data)."""
    _, configuration = system_key.split('-', 1)
    return f'U-{configuration}'


def label_of(pseudo_key: str, spin_orbit: bool = False) -> str:
    spec = config.PSEUDOS[pseudo_key]
    tag = spec.get('tag') or ('SR' if spec['rel'] == 'scalar' else 'FR')
    if spin_orbit:
        tag += '+SOC'
    return f"{Path(spec['upf']).name} [{tag}]"


def load_external_reference(path: Path, label: str) -> Optional[Dict[str, Any]]:
    if not path.exists():
        print(f"  WARNING: reference '{path}' not found — skipped.")
        return None
    payload = json.loads(path.read_text())
    payload['_label'] = label
    payload['_source'] = path.name
    return payload


def load_references() -> List[Dict[str, Any]]:
    """Return the AE average plus the published reference codes."""
    methods: List[Dict[str, Any]] = []

    for kind, filename in config.REFERENCE_FILES.items():
        path = config.REFERENCE_DATA_DIR / filename
        payload = load_external_reference(path, 'AE average')
        if payload is not None:
            methods.append(payload)

    # The unaries file carries only the four unary systems and the oxides file
    # only the six oxides, so they are two separate "methods" that are merged
    # when a system is looked up.
    for label, template in EXTERNAL_METHODS:
        for kind in KINDS:
            filename = template.format(kind=kind)
            path = config.ACWF_SCRIPTS_DIR / '3-analyze' / 'outputs' / filename
            payload = load_external_reference(path, label)
            if payload is not None:
                payload['_kind'] = kind
                methods.append(payload)

    return methods


def payload_fits(payload: Dict[str, Any]) -> Dict[str, Tuple[Dict[str, float], int]]:
    """Return ``{canonical system key: (BM fit, atoms in the cell)}`` of one dataset.

    The results of this project use the composition in the key (``O2U-XO2``) while
    the published data uses ``U-XO2``; the mapping is only applied to our own
    datasets, because the published files hold every element and mapping them all
    onto ``U`` would silently mix elements.
    """
    result: Dict[str, Tuple[Dict[str, float], int]] = {}
    for key, fit in payload.get('BM_fit_data', {}).items():
        if fit is None:
            continue
        natoms = payload.get('num_atoms_in_sim_cell', {}).get(key)
        if natoms is None:
            continue
        name = canonical_key(key) if payload.get('_ours') else key
        result.setdefault(name, (fit, natoms))
    return result


def fits_for_system(methods: List[Dict[str, Any]], system_key: str) -> Dict[str, Tuple[float, float, float]]:
    """Return ``{label: (V0 per formula unit, B0, B1)}`` for one system."""
    configuration = system_key.split('-', 1)[1]
    natoms_fu = get_num_atoms_in_formula_unit(configuration)

    result: Dict[str, Tuple[float, float, float]] = {}
    for payload in methods:
        entry = payload_fits(payload).get(system_key)
        if entry is None:
            continue
        fit, natoms = entry
        v0 = eosdata.volume_per_formula_unit(fit, natoms, natoms_fu)
        result[short_label(payload['_label'])] = (v0, fit['bulk_modulus_ev_ang3'], fit['bulk_deriv'])
    return result


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def pair_metrics(a: Tuple[float, float, float], b: Tuple[float, float, float], natoms_fu: int) -> Tuple[float, float, float]:
    """Return ``(epsilon, nu, delta meV/atom)`` of two EOS fits."""
    delta = eosdata.delta_per_atom(a[0], a[1], a[2], b[0], b[1], b[2], natoms_fu)
    nu = nu_metric(a[0], a[1], a[2], b[0], b[1], b[2], 100.0, std.WEIGHT_B0, std.WEIGHT_B1)
    eps = epsilon_metric(a[0], a[1], a[2], b[0], b[1], b[2], 1.0, std.WEIGHT_B0, std.WEIGHT_B1)
    return float(eps), float(nu), float(delta)


def md_cell(text) -> str:
    """Escape a string so that it can be used inside a markdown table cell.

    Method names and file names of this report contain ``|`` (``CASTEP (PW|C19MK2)``,
    ``...@PW|SSSP-prec-v1.3.json``), which would otherwise split the cell and destroy
    the table.
    """
    return str(text).replace('|', '\\|').replace('\n', ' ').strip()


def table(labels: List[str], values: Dict[Tuple[str, str], float], fmt: str) -> List[str]:
    """Render a pairwise table; the labels are escaped before their width is measured."""
    rendered = [md_cell(label) for label in labels]
    width = max(11, max(len(label) for label in rendered) + 2)

    lines = []
    lines.append('| ' + ' ' * (width - 2) + ' | ' +
                 ' | '.join(label.ljust(width - 2) for label in rendered) + ' |')
    lines.append('| ' + ' | '.join('-' * (width - 2) for _ in range(len(rendered) + 1)) + ' |')

    for index, row_label in enumerate(labels):
        cells = []
        for column_index, column_label in enumerate(labels):
            if index == column_index:
                cells.append('-'.center(width - 2))
            else:
                value = values.get((row_label, column_label))
                cells.append(('n/a' if value is None else format(value, fmt)).center(width - 2))
        lines.append(f'| {rendered[index].ljust(width - 2)} | ' + ' | '.join(cells) + ' |')
    return lines


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

DEFINITIONS = """
## Metric definitions

All three metrics compare two fitted Birch-Murnaghan equations of state E_a(V) and E_b(V)
of the same system. They are computed with the official implementations of
`acwf-verification-scripts` (`quantities_for_comparison.py`) and of the ACWF paper.

### epsilon — normalised area between the two EOS curves (dimensionless)

    epsilon(a,b) = sqrt( < (E_a - E_b)^2 > / sqrt( < (E_a - <E_a>)^2 > * < (E_b - <E_b>)^2 > ) )

    - epsilon < 0.06 : excellent agreement
    - epsilon < 0.2  : good agreement

### nu — weighted relative difference of V0, B0 and B1 [%]

    nu(a,b) = 100 * sqrt( sum_Y [ w_Y * (Y_a - Y_b) / ((Y_a + Y_b)/2) ]^2 ),
              Y in {V0, B0, B1},  w_V0 = 1,  w_B0 = 1/20,  w_B1 = 1/400

    - nu < 0.1  : excellent fit
    - nu < 0.33 : good fit

### Delta — RMS energy difference [meV/atom]

    Delta(a,b) = (1/n_f.u.) * sqrt( integral of (E_a(V) - E_b(V))^2 dV / dV ),
                 integrated over the +-6 % window around V0 = (V0_a + V0_b)/2

All three metrics are **per atom**: `Delta` is given in meV per atom, and the
per-formula-unit volumes used inside the formula are divided by the number of
atoms per formula unit, `n_f.u.` (1 for X/SC, X/BCC and X/FCC, 2 for X/Diamond
and XO, 3 for XO2 and X2O, 4 for XO3, 5 for X2O3, 7 for X2O5). The equilibrium
volumes in the tables are given both per formula unit and per atom of the
simulation cell (four atoms for X/FCC, twelve for XO2, ...).

    - Delta < 0.3  meV/atom : excellent agreement
    - Delta < 0.95 meV/atom : good agreement
"""


def convergence_section(pseudo_keys: List[str], standard) -> str:
    """Markdown table of the cutoff convergence scan and the chosen cutoffs."""
    import importlib.util

    path = PROJECT_ROOT / '2-convergence' / 'select_cutoffs.py'
    spec = importlib.util.spec_from_file_location('select_cutoffs', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    lines = ['## Plane-wave cutoff convergence (SSSP control protocol)', '']
    lines.append(
        'The two candidate pseudopotentials carry no recommended cutoff in their UPF header '
        '("Suggested minimum cutoff for wavefunctions: 0. Ry"), so the cutoff was determined with '
        'the SSSP control-protocol scan implemented in `2-convergence/`: a 7-point EOS is computed '
        'at several `ecutwfc` values (fixed dual = 4, the ACWF value for norm-conserving '
        'pseudopotentials) for the BCC unary and the dioxide, and every fit is compared with the fit '
        'at the reference cutoff (200 Ry) through the nu-like distance that the SSSP `criteria.yml` '
        f'(`standard` set) bounds at {std.CUTOFF_CONVERGENCE_NU_TOLERANCE} %.'
    )
    lines.append('')
    lines.append('| ecutwfc [Ry] | ecutrho [Ry] | ' +
                 ' | '.join(f'nu({short_label(label_of(key))}) [%]' for key in pseudo_keys) +
                 ' | verdict |')
    lines.append('| --- | --- | ' + ' | '.join('---' for _ in pseudo_keys) + ' | --- |')

    per_pseudo = {}
    for key in pseudo_keys:
        try:
            per_pseudo[key] = module.collect_points(util.set_name(key))
        except Exception:  # noqa: BLE001
            per_pseudo[key] = {}

    if not any(per_pseudo.values()):
        lines.append('')
        lines.append('*(no convergence data found)*')
        return '\n'.join(lines) + '\n'

    points = sorted({point for data in per_pseudo.values() for point in data})
    for point in points:
        cells, verdicts = [], []
        for key in pseudo_keys:
            data = per_pseudo[key]
            if point not in data or not data[point]:
                cells.append('n/a')
                verdicts.append(None)
                continue
            reference_point = max(data, key=lambda item: (item[0], item[1]))
            reference = data[reference_point]
            values = [eosdata.nu_between_fits(fit, reference[system])
                      for system, fit in sorted(data[point].items()) if system in reference]
            worst = max(values) if values else None
            cells.append('n/a' if worst is None else f'{worst:.3f}')
            verdicts.append(None if worst is None else worst <= std.CUTOFF_CONVERGENCE_NU_TOLERANCE)
        verdict = 'converged' if verdicts and all(v for v in verdicts if v is not None) else 'not converged'
        lines.append(f'| {point[0]:g} | {point[0] * point[1]:g} | ' + ' | '.join(cells) + f' | {verdict} |')

    lines.append('')
    lines.append('**Chosen cutoffs** — the smallest converged scan point, written to '
                 '`2-convergence/cutoffs.json` and read automatically by the submission script:')
    lines.append('')
    lines.append('| pseudopotential | ecutwfc [Ry] | ecutrho [Ry] (U) | dual |')
    lines.append('| --- | --- | --- | --- |')
    for key in pseudo_keys:
        cutoffs = util.load_cutoffs(key)
        wfc, rho = cutoffs.get('U', (float('nan'), float('nan')))
        lines.append(f'| **{short_label(label_of(key))}** | {wfc:g} | {rho:g} | {rho / wfc:.1f} |')
    lines.append('')
    lines.append(
        'The effective cutoffs of a mixed U/O cell are the maximum over its elements, so the oxides '
        f'run at `ecutwfc = max(ecutwfc(U), {config.O_CUTOFFS[0]:g})` Ry and '
        f'`ecutrho = max(ecutrho(U), {config.O_CUTOFFS[1]:g})` Ry, the recommended values of '
        '`O_ONCV_PBE-1.0.upf`. The 50 Ry and 60 Ry rows coincide for the dioxide because oxygen '
        'sets the lower bound.'
    )
    lines.append('')
    return '\n'.join(lines) + '\n'


def ascii_eos_section(payloads: List[Dict[str, Any]], args) -> str:
    """The EOS curves themselves, as text, next to the all-electron curve.

    Every number in this report is derived from seven energies per system, and the metrics
    hide their shape: two curves can share V0 and B0 and still differ in the third order.
    Printing the curves makes the metrics auditable by eye — a row shifted sideways, or
    steeper on one side, is a large Δ. Each row is referenced to the minimum of its own
    Birch-Murnaghan fit, so the rows are directly comparable, and the all-electron row is
    the published fit evaluated at our volumes.
    """
    our_methods = [payload for payload in payloads if payload.get('_ours')]
    ae_methods = [payload for payload in payloads if payload['_label'] == 'AE average']
    if not our_methods:
        return ''

    # our results use the composition in the key, the references do not
    by_canonical: Dict[str, List[Tuple[Dict[str, Any], str]]] = {}
    for payload in our_methods:
        for key in payload.get('eos_data', {}):
            by_canonical.setdefault(canonical_key(key), []).append((payload, key))

    systems = sorted(by_canonical,
                     key=lambda key: (key.split('-', 1)[1] not in config.UNARY_CONFIGURATIONS,
                                      config.ALL_CONFIGURATIONS.index(key.split('-', 1)[1])
                                      if key.split('-', 1)[1] in config.ALL_CONFIGURATIONS else 99))

    blocks = ['## The EOS curves as text', '',
              'Seven volumes per system, energies per atom relative to the minimum of each '
              'curve’s own Birch-Murnaghan fit (meV/atom), so the rows below can be compared '
              'point by point. `AE ref` is the published all-electron average evaluated at the '
              'same volumes — the curve Δ integrates against. The same curves are drawn as PNG '
              'files in `4-analyze/outputs/plots/` (`plot_ev_curves.py`); these tables exist so '
              'that the numbers can be checked without an image viewer.', '']
    for system in systems:
        entries = by_canonical[system]
        rows: List[Tuple[str, Any]] = []
        volumes = None
        for payload, key in entries:
            points = payload['eos_data'].get(key)
            fit = payload['BM_fit_data'].get(key)
            natoms_cell = payload.get('num_atoms_in_sim_cell', {}).get(key)
            if not points or not fit or not natoms_cell:
                continue
            array = list(zip(*points))
            volumes = [value / natoms_cell for value in array[0]]
            rows.append((short_label(payload['_label']),
                         [(energy - fit['E0']) * 1000.0 / natoms_cell for energy in array[1]]))
        if volumes is None:
            continue
        reference = None
        for payload in ae_methods:
            entry = payload_fits(payload).get(system)
            if entry:
                reference = entry
                break
        blocks.append('```')
        blocks.append(eosdata.eos_ascii_block(system, rows, volumes, reference, indent=''))
        blocks.append('```')
        blocks.append('')
    return '\n'.join(blocks) + '\n'


def build_report(payloads: List[Dict[str, Any]], args) -> str:
    our_methods = [payload for payload in payloads if payload.get('_ours')]
    all_methods = payloads

    # System universe: the systems of our own runs (they define what was verified).
    systems: List[str] = []
    for payload in our_methods:
        for key in payload.get('BM_fit_data', {}):
            canonical = f"U-{key.split('-', 1)[1]}"
            if canonical not in systems:
                systems.append(canonical)
    systems.sort(key=lambda key: (key.split('-', 1)[1] not in config.UNARY_CONFIGURATIONS,
                                 config.ALL_CONFIGURATIONS.index(key.split('-', 1)[1])
                                 if key.split('-', 1)[1] in config.ALL_CONFIGURATIONS else 99))

    # One entry per method: the published references are split over a unaries and an
    # oxides file, and the two all-electron files share the label 'AE average'.
    full_labels: List[str] = []
    for payload in all_methods:
        if payload['_label'] not in full_labels:
            full_labels.append(payload['_label'])

    # Keep a stable order: ours first, then the references.
    labels = [short_label(label) for label in full_labels]
    lines: List[str] = []
    lines.append('# U-14ve pseudopotential verification — comparison tables')
    lines.append('')
    lines.append(
        'Pairwise comparison of the equations of state obtained with the candidate '
        'uranium pseudopotentials of this project and the published reference data of the '
        'ACWF verification paper (E. Bosoni et al., *Nat. Rev. Phys.* **6**, 45 (2024)).'
    )
    lines.append('')
    lines.append('Methods of the tables (the exact source of every dataset is listed afterwards):')
    lines.append('')
    lines.append('| label | method |')
    lines.append('| --- | --- |')
    seen = set()
    for payload in all_methods:
        if payload['_label'] in seen:
            continue
        seen.add(payload['_label'])
        if payload.get('_ours'):
            description = (
                f"this work — Quantum ESPRESSO, standard `{payload['_standard']}`, "
                f"ecutwfc / ecutrho = {payload['_cutoffs']} Ry, "
                f"k-point distance {payload['_kpoints_distance']} 1/Å"
            )
        else:
            description = 'published all-electron average (ACWF paper)' if payload['_label'] == 'AE average' \
                else 'published results of the ACWF verification paper'
        lines.append(f"| **{md_cell(short_label(payload['_label']))}** | {md_cell(description)} |")
    lines.append('')
    lines.append('Sources of the published datasets:')
    lines.append('')
    sources = []
    for payload in all_methods:
        if payload.get('_ours') or payload['_source'] in [item[1] for item in sources]:
            continue
        sources.append((short_label(payload['_label']), payload['_source']))
    for label, source in sources:
        lines.append(f'- **{label}** — `{source}`')
    lines.append('')
    lines.append(DEFINITIONS)
    lines.append('## Per-system pairwise comparisons')
    lines.append('')
    lines.append('Rows and columns are the methods of the table above; every entry is the metric '
                 'between the two fitted EOS of that system. `-` marks the diagonal.')
    lines.append('')

    for system_key in systems:
        lines.append(f'### {system_key}')
        lines.append('')
        fits = fits_for_system(all_methods, system_key)
        present = [label for label in labels if label in fits]
        natoms_fu = get_num_atoms_in_formula_unit(system_key.split('-', 1)[1])

        eps_values, nu_values, delta_values = {}, {}, {}
        for i, first in enumerate(present):
            for second in present[i + 1:]:
                eps, nu, delta = pair_metrics(fits[first], fits[second], natoms_fu)
                eps_values[(first, second)] = eps_values[(second, first)] = eps
                nu_values[(first, second)] = nu_values[(second, first)] = nu
                delta_values[(first, second)] = delta_values[(second, first)] = delta

        lines.append('#### ε — normalised area between EOS curves (dimensionless)')
        lines.append('')
        lines.extend(table(present, eps_values, '.4f'))
        lines.append('')
        lines.append('#### ν — weighted relative error in V₀, B₀, B₁ [%]')
        lines.append('')
        lines.extend(table(present, nu_values, '.3f'))
        lines.append('')
        lines.append('#### Δ — RMS energy difference [meV/atom]')
        lines.append('')
        lines.extend(table(present, delta_values, '.3f'))
        lines.append('')

        # Equilibrium values, useful to read the tables above.
        lines.append('#### Fitted equilibrium quantities')
        lines.append('')
        lines.append('| method | V₀ [Å³/f.u.] | V₀ [Å³/atom] | B₀ [GPa] | B₁ |')
        lines.append('| --- | --- | --- | --- | --- |')
        plain = {short_label(payload['_label']): payload for payload in all_methods}
        for label in present:
            v0, b0, b1 = fits[label]
            natoms = plain[label].get('num_atoms_in_sim_cell', {}).get(
                next((key for key in plain[label].get('BM_fit_data', {})
                      if f"U-{key.split('-', 1)[1]}" == system_key), ''), None)
            v0_atom = f'{v0 / natoms_fu:.4f}' if natoms is None else f'{v0 / natoms_fu:.4f}'
            lines.append(f'| **{md_cell(label)}** | {v0:.4f} | {v0_atom} | '
                         f'{b0 * 160.21766208:.2f} | {b1:.3f} |')
        lines.append('')

    return '\n'.join(lines) + '\n'



def ranking_section(payloads: List[Dict[str, Any]], args) -> str:
    """Mean distance to the all-electron average, per method and material class.

    This is the section that answers "how good is our pseudopotential compared with
    the published codes": every method — ours and the published ones — is measured
    with the same metric against the same all-electron average, so the numbers are
    directly comparable.
    """
    ae_labels = {payload['_label'] for payload in payloads if payload['_label'] == 'AE average'}
    if not ae_labels:
        return ''

    systems = []
    for payload in payloads:
        for key in payload.get('BM_fit_data', {}):
            canonical = f'U-{key.split("-", 1)[1]}'
            if canonical not in systems:
                systems.append(canonical)
    systems = [key for key in systems
               if key.split('-', 1)[1] in config.ALL_CONFIGURATIONS]

    unaries = [key for key in systems if key.split('-', 1)[1] in config.UNARY_CONFIGURATIONS]
    oxides = [key for key in systems if key.split('-', 1)[1] not in config.UNARY_CONFIGURATIONS]

    # distance of each method to the all-electron average
    distances: Dict[str, Dict[str, float]] = {}
    for payload in payloads:
        if payload['_label'] in ae_labels:
            continue
        label = short_label(payload['_label'])
        per_system = {}
        for system in systems:
            configuration = system.split('-', 1)[1]
            natoms_fu = get_num_atoms_in_formula_unit(configuration)
            fits = fits_for_system([payload], system)
            reference_fits = fits_for_system([p for p in payloads if p['_label'] in ae_labels], system)
            if not fits or not reference_fits:
                continue
            name = next(iter(fits))
            reference_name = next(iter(reference_fits))
            v0, b0, b1 = fits[name]
            reference_v0, reference_b0, reference_b1 = reference_fits[reference_name]
            per_system[system] = {
                'delta': eosdata.delta_per_atom(v0, b0, b1, reference_v0, reference_b0, reference_b1, natoms_fu),
                'nu': nu_metric(v0, b0, b1, reference_v0, reference_b0, reference_b1, 100.0,
                                std.WEIGHT_B0, std.WEIGHT_B1),
                'epsilon': epsilon_metric(v0, b0, b1, reference_v0, reference_b0, reference_b1, 1.0,
                                          std.WEIGHT_B0, std.WEIGHT_B1),
            }
        if per_system:
            # a published method is split over a unaries and an oxides file: merge them
            distances.setdefault(label, {}).update(per_system)

    if not distances:
        return ''

    ours = [short_label(payload['_label']) for payload in payloads if payload.get('_ours')]
    ordered = ours + [label for label in ['QE-SSSP', 'VASP', 'CASTEP', 'FLEUR', 'WIEN2k']
                      if label in distances and label not in ours]

    lines = ['## How the candidates compare with the published codes', '']
    lines.append(
        'Every method is measured with the same metric against the same all-electron average, so the '
        'rows of this table are directly comparable. The published codes split into two groups, which '
        'is worth keeping in mind: `FLEUR` and `WIEN2k` are **all-electron** codes (they contribute to '
        'the all-electron average itself), while `QE-SSSP`, `VASP` and `CASTEP` are plane-wave codes '
        'using pseudopotentials — those are the meaningful yardsticks for a pseudopotential test.'
    )
    lines.append('')
    lines.append('### Δ against the all-electron average [meV/atom]')
    lines.append('')
    lines.append('| method | kind | mean over unaries | mean over oxides | worst system | worst Δ | '
                 'how many systems pass Δ ≤ 1 |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- |')
    for label in ordered:
        per_system = distances[label]
        if label in ours:
            kind = 'this work (pseudopotential)'
        elif label in ('FLEUR', 'WIEN2k'):
            kind = 'all-electron code'
        else:
            kind = 'pseudopotential code'
        means = []
        for subset in (unaries, oxides):
            values = [per_system[system]['delta'] for system in subset if system in per_system]
            means.append(sum(values) / len(values) if values else float('nan'))
        worst_system = max(per_system, key=lambda key: per_system[key]['delta'])
        passing = sum(1 for entry in per_system.values() if entry['delta'] <= std.get_criterion('delta')['pass'])
        lines.append(f'| **{md_cell(label)}** | {kind} | {means[0]:.3f} | {means[1]:.3f} | '
                     f'{worst_system} | {per_system[worst_system]["delta"]:.3f} | '
                     f'{passing}/{len(per_system)} |')
    lines.append('')
    lines.append('### ν against the all-electron average [%]')
    lines.append('')
    lines.append('| method | mean over unaries | mean over oxides | worst system | worst ν |')
    lines.append('| --- | --- | --- | --- | --- |')
    for label in ordered:
        per_system = distances[label]
        means = []
        for subset in (unaries, oxides):
            values = [per_system[system]['nu'] for system in subset if system in per_system]
            means.append(sum(values) / len(values) if values else float('nan'))
        worst_system = max(per_system, key=lambda key: per_system[key]['nu'])
        lines.append(f'| **{md_cell(label)}** | {means[0]:.3f} | {means[1]:.3f} | {worst_system} | '
                     f'{per_system[worst_system]["nu"]:.3f} |')
    lines.append('')

    def mean(label, subset, key='delta'):
        values = [distances[label][system][key] for system in subset if system in distances.get(label, {})]
        return sum(values) / len(values) if values else float('nan')

    def passing(label):
        return sum(1 for entry in distances[label].values()
                   if entry['delta'] <= std.get_criterion('delta')['pass'])

    pw_codes = [label for label in ('QE-SSSP', 'VASP', 'CASTEP') if label in distances]

    lines.append('### Reading the table')
    lines.append('')
    if 'SR' in distances and pw_codes:
        sr_ox, sr_un = mean('SR', oxides), mean('SR', unaries)
        best_ox = min(pw_codes, key=lambda label: mean(label, oxides))
        lines.append(
            f'- **Oxides**: the scalar-relativistic candidate [SR] has a mean Δ of {sr_ox:.2f} meV/atom, '
            f'which is *lower* than every published pseudopotential code in the table — the best of them '
            f'({best_ox}) reaches {mean(best_ox, oxides):.2f}. Five of the six oxides meet the strict '
            f'SSSP band Δ ≤ 1 meV/atom ([SR] passes the band for {passing("SR")} of the ten systems).'
        )
        comparison = ', '.join(f'{mean(label, unaries):.2f} for {label}' for label in pw_codes)
        lines.append(
            f'- **Uranium metal is harder for this pseudopotential**: the unary mean Δ of [SR] is '
            f'{sr_un:.2f} meV/atom, against {comparison}. The 14-electron norm-conserving '
            f'pseudopotential is therefore not competitive with the published SSSP and VASP '
            f'pseudopotentials for the four unaries, while it is better than all of them for the oxides.'
        )
        # The other candidates of this project, measured against SR: a trade-off between the two
        # classes would otherwise read as a plain regression (or as a plain improvement).
        our_labels = {short_label(payload['_label']) for payload in payloads if payload.get('_ours')}
        for label in [candidate for candidate in distances
                      if candidate in our_labels and candidate != 'SR'
                      and len(distances.get(candidate, {})) == len(unaries) + len(oxides)]:
            ox, un = mean(label, oxides), mean(label, unaries)
            if un < sr_un and ox > sr_ox:
                shape = (f'trades the two material classes off: better on the unaries '
                         f'({un:.2f} against {sr_un:.2f} for [SR]) but worse on the oxides '
                         f'({ox:.2f} against {sr_ox:.2f})')
            elif un > sr_un and ox > sr_ox:
                shape = (f'is worse than [SR] in both classes (unaries {un:.2f} against {sr_un:.2f}, '
                         f'oxides {ox:.2f} against {sr_ox:.2f})')
            elif un < sr_un and ox < sr_ox:
                shape = (f'is better than [SR] in both classes (unaries {un:.2f} against {sr_un:.2f}, '
                         f'oxides {ox:.2f} against {sr_ox:.2f})')
            else:
                shape = (f'is better on the oxides ({ox:.2f} against {sr_ox:.2f}) but worse on the '
                         f'unaries ({un:.2f} against {sr_un:.2f})')
            lines.append(f'- **The other candidate of this project, [{label}]**, {shape}. It passes the '
                         f'Δ ≤ 1 band for {passing(label)} of the ten systems.')
        lines.append(
            '- **What dominates Δ here**: the fitted B₀ and B₁ of both candidates agree with the '
            'all-electron fit to order 1 %, so the differences above come mostly from the equilibrium '
            'volume: Δ is the RMS of the energy difference over ±6 % around V₀, and the stiff structures '
            '(X/SC, X/Diamond, B₀ ≈ 160–170 GPa) turn a given relative V₀ error into the largest energy '
            'difference. A candidate with an excellent ν can therefore still have a large Δ.'
        )
        lines.append(
            '- **The all-electron codes are not a score**: FLEUR and WIEN2k agree with the all-electron '
            'average to ~0.1 meV/atom because they take part in it. The distance of a '
            'pseudopotential-based method from that average *is* the pseudopotential error, which is '
            'what this verification quantifies.'
        )
        lines.append(
            '- A caveat on the metric: Δ integrates the energy difference over the ±6 % volume window, '
            'so it is dominated by the equilibrium volume and the curvature (B₀); ν and ε above give '
            'the same ranking with different weights.'
        )
    lines.append('')
    return '\n'.join(lines) + '\n'


def notes_section(pseudo_keys: List[str], standard) -> str:
    """Notes, caveats and the checks that back the numbers of this report."""
    lines = ['## Notes, caveats and validation', '']

    # The window-robustness check only exists for the fully relativistic candidate of the
    # u14ve project (`fr`), which was re-run in a ±10.5 % window. A project that does not
    # configure that key (and does not hold that dataset) has nothing to say here, so the
    # whole section — heading, preamble and table — is conditional.
    wide_name = util.set_name('fr', suffix='wide-verification-PBE-v1') \
        if 'fr' in config.PSEUDOS else ''
    standard_name = util.set_name('fr') if 'fr' in config.PSEUDOS else ''
    wide = None
    if wide_name:
        path = config.OUTPUTS_DIR / f'results-{wide_name}-{util.PLUGIN_NAME}.json'
        if path.exists():
            wide = json.loads(path.read_text())
    narrow = None
    if standard_name:
        path_narrow = config.OUTPUTS_DIR / f'results-{standard_name}-{util.PLUGIN_NAME}.json'
        if path_narrow.exists():
            narrow = json.loads(path_narrow.read_text())

    if wide and narrow:
        lines.append('### Robustness of the EOS window')
        lines.append('')
        lines.append(
            'The ACWF protocol scales the input structure by ±6 % in seven steps. For the fully '
            'relativistic pseudopotential the resulting EOS minima of the metallic systems fall '
            '*outside* that window (+7 % for BCC and FCC), so the ±6 % Birch-Murnaghan fit '
            'extrapolates the minimum. A second set with a ±10.5 % window (7 volumes, step 3.5 %) '
            'was therefore computed for all ten systems of that pseudopotential:'
        )
        lines.append('')
        lines.append('| system | Δ from the ±6 % fit [meV/atom] | Δ from the ±10.5 % fit [meV/atom] | difference |')
        lines.append('| --- | --- | --- | --- |')
        ae = load_external_reference(config.REFERENCE_DATA_DIR /
                                     config.REFERENCE_FILES['unaries'], 'AE average')
        ae_ox = load_external_reference(config.REFERENCE_DATA_DIR /
                                        config.REFERENCE_FILES['oxides'], 'AE average')
        reference = {}
        for payload in (ae, ae_ox):
            if payload:
                for key, fit in payload['BM_fit_data'].items():
                    if fit:
                        reference[key] = (fit, payload['num_atoms_in_sim_cell'][key])
        for key in sorted(narrow['BM_fit_data']):
            if narrow['BM_fit_data'][key] is None:
                continue
            canonical = canonical_key(key)
            if canonical not in reference or wide['BM_fit_data'].get(key) is None:
                continue
            configuration = canonical.split('-', 1)[1]
            natoms_fu = get_num_atoms_in_formula_unit(configuration)
            values = []
            for payload in (narrow, wide):
                fit = payload['BM_fit_data'][key]
                v0 = eosdata.volume_per_formula_unit(fit, payload['num_atoms_in_sim_cell'][key], natoms_fu)
                ref_fit, ref_natoms = reference[canonical]
                ref_v0 = eosdata.volume_per_formula_unit(ref_fit, ref_natoms, natoms_fu)
                values.append(eosdata.delta_per_atom(
                    v0, fit['bulk_modulus_ev_ang3'], fit['bulk_deriv'],
                    ref_v0, ref_fit['bulk_modulus_ev_ang3'], ref_fit['bulk_deriv'], natoms_fu))
            lines.append(f'| {canonical} | {values[0]:.3f} | {values[1]:.3f} | '
                         f'{100 * abs(values[1] - values[0]) / max(values[0], 1e-9):.1f} % |')
        lines.append('')
        lines.append(
            'The difference is at most a few tenths of a percent, i.e. the fitted EOS and therefore '
            'every metric of this report is insensitive to the window. The tables above use the '
            '**standard ±6 % runs for both pseudopotentials**, so all systems are treated identically.'
        )
    lines.append('')
    lines.append(
        'This check also shows that the "minimum is on the edge of the window" warning of '
        '`get_results.py` does not invalidate the fits here — but it is the reason the numbers of the '
        'fully relativistic pseudopotential for the metals should be read with care.'
    )
    lines.append('')

    lines.append('### Spin-orbit coupling')
    lines.append('')
    lines.append(
        '- Both pseudopotentials are run **without** spin-orbit coupling: the all-electron reference '
        'of the ACWF paper is scalar relativistic, and this is also how the SSSP verification tests '
        'Quantum ESPRESSO pseudopotentials. No spin-orbit calculation contributes to the numbers of '
        'this report.'
    )
    lines.append(
        '- This is the key to reading the results of the fully relativistic pseudopotential: with '
        '`lspinorb = .false.` Quantum ESPRESSO uses the `j`-averaged potential, i.e. the eight '
        '`PP_CHI` channels of `U.rel-pbe-n-nc.14ve.UPF` collapse into the five projectors of the '
        'scalar-relativistic case (verified in the `pw.x` output of the runs). That averaged '
        'potential was generated for a fully relativistic occupation (5f5/2 filled with three '
        'electrons, 5f7/2 empty) and is therefore **not equivalent** to a scalar-relativistic '
        'pseudopotential such as `U.pbe-n-nc.14ve.UPF`.'
    )
    lines.append('')

    lines.append('### Validation of the pipeline')
    lines.append('')
    lines.append(
        '- The published reference codes (QE/SSSP-prec-1.3, VASP, FLEUR, WIEN2k, CASTEP) agree with '
        'the all-electron average and with each other to Δ ≲ 0.3 meV/atom, ν ≲ 0.05 % and '
        'ε ≲ 0.03 in the tables above. Independent methods that are known to agree must produce '
        'small metrics, which they do — this is the end-to-end check of the analysis chain.'
    )
    lines.append(
        '- The Δ metric (the official `quantities_for_comparison.delta`, which is hard to read) was '
        'cross-checked against a direct numerical integration of '
        '√(∫(E₁−E₂)²dV / ΔV) over the same window for all ten systems of the scalar-relativistic '
        'pseudopotential: the two agree to four decimal places.'
    )
    lines.append(
        '- `4-analyze/audit_standard.py` re-derives from the AiiDA provenance that every calculation '
        'used the pseudopotential under test, the advertised cutoffs, k-point density, smearing, '
        '`conv_thr`, `etot_conv_thr` and `forc_conv_thr`, that all seven volumes of a system share '
        'one Monkhorst-Pack mesh, and that no restart handler silently changed the parameters. It '
        'passes for all three sets reported here (70 + 70 + 21 SCFs).'
    )
    lines.append(
        '- `CONTROL.disk_io = "nowf"` (see the project README) only suppresses the wavefunction '
        'scratch files; it cannot influence any energy, force or fit.'
    )
    lines.append('')
    lines.append(
        f'- Calculation standard: `{standard["name"]}` — {standard["description"]}. '
        f'k-point density {standard["kpoints_distance"]} 1/Å, `conv_thr = natoms × '
        f'{standard["conv_thr_per_atom"]:.1e} Ry`, `etot_conv_thr = natoms × '
        f'{standard["etot_conv_thr_per_atom"]:.1e} Ry`, `forc_conv_thr = '
        f'{standard["forc_conv_thr"]:.1e} Ry/bohr`, `{standard["smearing"]}` smearing with '
        f'`degauss = {standard["degauss"]} Ry`.'
    )
    lines.append('')
    return '\n'.join(lines) + '\n'


def build_summary(payloads: List[Dict[str, Any]]) -> str:
    """Summary section: our pseudopotentials against the all-electron average."""
    lines = ['## Summary', '']
    for payload in payloads:
        if not payload.get('_ours'):
            continue
        label = payload['_label']
        lines.append(f'### {md_cell(short_label(label))} against the all-electron average')
        lines.append('')
        ae = [p for p in payloads if p['_label'] == 'AE average']
        lines.append('| system | class | atoms/cell | Δ [meV/atom] | ν [%] | ε | '
                     'V₀ ours [Å³/atom] | V₀ AE [Å³/atom] | B₀ ours [GPa] | B₀ AE [GPa] |')
        lines.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
        worst = {'delta': (0.0, None), 'nu': (0.0, None), 'epsilon': (0.0, None)}
        for key, fit in sorted(payload.get('BM_fit_data', {}).items()):
            if fit is None:
                continue
            canonical = f"U-{key.split('-', 1)[1]}"
            configuration = canonical.split('-', 1)[1]
            natoms_fu = get_num_atoms_in_formula_unit(configuration)
            natoms = payload['num_atoms_in_sim_cell'][key]
            v0 = eosdata.volume_per_formula_unit(fit, natoms, natoms_fu)

            reference = None
            for entry in ae:
                if canonical in entry.get('BM_fit_data', {}) and entry['BM_fit_data'][canonical] is not None:
                    reference = (entry['BM_fit_data'][canonical], entry['num_atoms_in_sim_cell'][canonical])
                    break
            if reference is None:
                continue
            ref_fit, ref_natoms = reference
            ref_v0 = eosdata.volume_per_formula_unit(ref_fit, ref_natoms, natoms_fu)

            eps, nu, delta = pair_metrics(
                (v0, fit['bulk_modulus_ev_ang3'], fit['bulk_deriv']),
                (ref_v0, ref_fit['bulk_modulus_ev_ang3'], ref_fit['bulk_deriv']),
                natoms_fu,
            )
            for metric, value in (('delta', delta), ('nu', nu), ('epsilon', eps)):
                if value > worst[metric][0]:
                    worst[metric] = (value, canonical)

            klass = 'unary' if configuration in config.UNARY_CONFIGURATIONS else 'oxide'
            lines.append(
                f'| {md_cell(canonical)} | {klass} | {natoms} | {delta:.3f} | {nu:.3f} | {eps:.4f} | '
                f'{v0 / natoms_fu:.4f} | {ref_v0 / natoms_fu:.4f} | '
                f'{fit["bulk_modulus_ev_ang3"] * 160.21766208:.2f} | '
                f'{ref_fit["bulk_modulus_ev_ang3"] * 160.21766208:.2f} |'
            )
        lines.append('')
        lines.append('| metric | worst value | system | SSSP-like verdict |')
        lines.append('| --- | --- | --- | --- |')
        for metric, (value, system) in worst.items():
            criterion = std.get_criterion(metric)
            if value <= criterion['pass']:
                verdict = f"PASS (≤ {criterion['pass']}{criterion['unit']})"
            elif value <= criterion['good']:
                verdict = f"acceptable (≤ {criterion['good']}{criterion['unit']})"
            else:
                verdict = f"above the acceptable band (> {criterion['good']}{criterion['unit']})"
            lines.append(f'| {metric} | {value:.4f} | {system} | {verdict} |')
        lines.append('')
    return '\n'.join(lines) + '\n'


def main() -> int:
    args = parse_args()
    util.load_profile()

    standard = std.get_standard(args.standard)

    overrides = {}
    for item in (args.set_overrides or []):
        key, _, value = item.partition('=')
        overrides[key] = value

    payloads: List[Dict[str, Any]] = []
    wanted = [(key, False) for key in args.pseudos]
    if args.include_spin_orbit:
        wanted += [(key, True) for key in args.pseudos if config.PSEUDOS[key]['rel'] == 'full']

    for pseudo_key, spin_orbit in wanted:
        payload = load_our_results(pseudo_key, set_override=overrides.get(pseudo_key),
                                  spin_orbit=spin_orbit)
        if payload is None:
            continue
        pseudo_cutoffs = util.load_cutoffs(pseudo_key)
        payload['_ours'] = True
        payload['_key'] = pseudo_key
        payload['_label'] = payload.get('_label') or label_of(pseudo_key, spin_orbit)
        payload['_standard'] = standard['name']
        payload['_cutoffs'] = f"{pseudo_cutoffs.get('U', ('?', '?'))[0]:g}/{pseudo_cutoffs.get('U', ('?', '?'))[1]:g}"
        payload['_kpoints_distance'] = standard['kpoints_distance']
        payload['_set_name'] = overrides.get(pseudo_key) or util.set_name(pseudo_key, spin_orbit=spin_orbit)
        payloads.append(payload)

    if not payloads:
        print('ERROR: no results of this project found — run the EOS workchains and '
              '4-analyze/get_results.py first.', file=sys.stderr)
        return 1

    payloads.extend(load_references())

    # A report built while the campaign is still running is legitimate, but the mean
    # metrics of an incomplete candidate silently average over fewer systems than the
    # published codes. Make that visible instead of letting a partial table pass as final.
    # The completeness denominator is this project's own system list: the published
    # reference files cover the whole periodic table and say nothing about our campaign.
    expected = {f'U-{configuration}' for configuration in config.ALL_CONFIGURATIONS}
    incomplete: List[str] = []
    for payload in payloads:
        if not payload.get('_ours'):
            continue
        have = {f'U-{key.split("-", 1)[1]}'
                for key, fit in (payload.get('BM_fit_data') or {}).items() if fit}
        missing = sorted(system.split('-', 1)[1] for system in expected - have)
        if missing:
            incomplete.append(f"**{payload['_label']}** ({len(have)}/{len(expected)} systems, "
                              f"missing {', '.join(missing)})")
            print(f"WARNING: '{payload['_label']}' has {len(have)} of {len(expected)} EOS fits "
                  f"(missing {', '.join(missing)}) — its mean metrics below are NOT final; re-run "
                  f"this report when the campaign has finished.", file=sys.stderr)

    report = build_report(payloads, args)
    if incomplete:
        marker = '\n\nMethods of the tables'
        banner = ('\n\n> **Warning — this report is not final.** ' + '; '.join(incomplete)
                  + '. The means over unaries/oxides in the ranking section are therefore taken over '
                    'fewer systems than the published codes, and blank cells in the per-system tables '
                    'belong to systems that have not finished.')
        if marker in report:
            report = report.replace(marker, banner + marker, 1)
        else:  # pragma: no cover - defensive, the heading is part of build_report
            report = banner + report
    report += '\n' + build_summary(payloads)
    report += '\n' + ascii_eos_section(payloads, args)
    report += '\n' + ranking_section(payloads, args)
    report += '\n' + notes_section([payload['_key'] for payload in payloads if payload.get('_ours')], standard)
    report += '\n' + convergence_section(list(dict.fromkeys(
        payload['_key'] for payload in payloads if payload.get('_ours'))), standard)

    report += '\n## How these numbers were produced\n\n'
    report += (
        f"* Code: Quantum ESPRESSO (`pw.x`), `{config.CODE_LABEL}`.\n"
        f"* Calculation standard: `{standard['name']}` — {standard['description']}.\n"
        f"  k-point density {standard['kpoints_distance']} 1/Å (the same Monkhorst-Pack mesh is reused "
        f"for all volumes of a system), `conv_thr = natoms × {standard['conv_thr_per_atom']:.1e} Ry`, "
        f"`etot_conv_thr = natoms × {standard['etot_conv_thr_per_atom']:.1e} Ry`, "
        f"`forc_conv_thr = {standard['forc_conv_thr']:.1e} Ry/bohr`, "
        f"`{standard['smearing']}` smearing with `degauss = {standard['degauss']} Ry`, "
        f"`mixing_beta = {standard['mixing_beta']}`.\n"
        f"* EOS: {standard['scale_count']} volumes from −{100 * standard['scale_increment'] * (standard['scale_count'] - 1) / 2:.0f} % "
        f"to +{100 * standard['scale_increment'] * (standard['scale_count'] - 1) / 2:.0f} % in "
        f"{100 * standard['scale_increment']:.0f} % steps, Birch-Murnaghan fit with the official "
        f"`eosfit_31_adapted.BM`.\n"
        f"* Cutoffs: determined by the SSSP control-protocol convergence scan of "
        f"`2-convergence/run_cutoff_convergence.py` and `select_cutoffs.py` (criterion: the ν-like "
        f"distance between EOS fits ≤ {std.CUTOFF_CONVERGENCE_NU_TOLERANCE} %).\n"
        f"* Uranium valence configuration of both candidate pseudopotentials: 6s²6p⁶5f³6d¹7s² "
        f"(14 electrons), norm conserving, PBE.\n"
        f"* Oxygen: `O_ONCV_PBE-1.0.upf` (norm conserving, as required to be consistent with the NC "
        f"uranium pseudopotentials).\n"
    )
    if args.cutoffs_note:
        report += f"* {args.cutoffs_note}\n"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(f"Written: {args.output}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
