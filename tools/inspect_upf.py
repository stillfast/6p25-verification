#!/usr/bin/env python
"""Quick pre-flight of a norm-conserving UPF before spending cluster time on it.

Prints the header facts that decide whether a candidate is worth a production run:

* valence count, number of beta projectors vs number of pseudo-wavefunctions,
* the ``ld1.test`` eigenvalue errors of the generation directory, if present,
* the conditioning of the projector overlap matrix ``S`` and of ``PP_DIJ``.

The conditioning matters because a nearly linearly dependent projector set produces
the pathology seen with the first ``U.pbe-n-nc.UPF`` (cond(S) = 9.7e8): the nonlocal
term becomes numerically unstable and the equation of state comes out monotonic with
its minimum outside the volume window.  Reference values of this project:

    U.pbe-n-nc.14ve.UPF (SR)                 cond(S) = 5.3e4   cond(D) = 1.1e2
    U.pbe-n-nc.UPF      (defective, NC)      cond(S) = 9.7e8   cond(D) = 1.7e7
    rc_scan_type1/rc_best (RC1)              cond(S) = 4.2e3   cond(D) = 1.7e2

Usage
-----

    python tools/inspect_upf.py <file.upf> [<file2.upf> ...]
    python tools/inspect_upf.py --compare <file.upf> ...
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np


def _floats(block: str) -> np.ndarray:
    """All numbers of a UPF data block, ignoring the attribute lines."""
    body = [line for line in block.splitlines() if '=' not in line and not line.strip().startswith('<')]
    return np.array([float(value) for line in body for value in line.split()], dtype=float)


def _block(text: str, tag: str, index: int | None = None) -> str:
    """Body of a UPF block. The index is mandatory where given: an optional ``(?:\\.N)?``
    group would let ``PP_BETA.2`` match the ``PP_BETA.1`` block (and every later match
    would then carry the earlier blocks along)."""
    if index is None:
        pattern = rf'<{tag}\b[^>]*>(.*?)</{tag}>'
    else:
        pattern = rf'<{tag}\.{index}\b[^>]*>(.*?)</{tag}\.{index}>'
    match = re.search(pattern, text, re.S)
    return match.group(1) if match else ''


def inspect(path: Path) -> dict:
    text = path.read_text(errors='ignore')
    header = {key: (re.search(rf'{key}\s*=\s*"([^"]*)"', text) or [None, None])[1]
              for key in ('element', 'pseudo_type', 'relativistic', 'z_valence', 'functional',
                          'number_of_wfc', 'number_of_proj', 'core_correction')}

    r = _floats(_block(text, 'PP_R'))
    rab = _floats(_block(text, 'PP_RAB'))
    nproj = int(header['number_of_proj'] or 0)
    betas = [_floats(_block(text, 'PP_BETA', index + 1)) for index in range(nproj)]
    dij = _floats(_block(text, 'PP_DIJ'))
    chis = len(re.findall(r'<PP_CHI\.\d+', text))

    result = dict(path=path, header=header, natoms_beta=len(betas), nchi=chis,
                  r=r, rab=rab, dij=dij)
    if r.size and rab.size == r.size and all(beta.size == r.size for beta in betas) and betas:
        matrix = np.vstack(betas)
        # S_ij = \int dr r^2 beta_i(r) beta_j(r); the beta functions are stored without the r^l
        # factor, which is exactly how Quantum ESPRESSO builds the overlap of the KB projectors.
        overlap = (matrix * r ** 2 * rab) @ matrix.T
        result['cond_S'] = float(np.linalg.cond(overlap))
        result['smallest_eig_S'] = float(np.linalg.eigvalsh(overlap).min())
    if dij.size == nproj ** 2:
        matrix = dij.reshape(nproj, nproj)
        result['cond_D'] = float(np.linalg.cond(matrix))
    return result


def ld1_errors(path: Path) -> list[tuple[str, float]]:
    """``[(state, eigenvalue error in Ry)]`` from an ``ld1.test`` file.

    The columns are ``l  m  label  occupation  E_all_electron  E_pseudo  difference``;
    the difference is the last field, not the pseudo eigenvalue next to it.
    """
    rows = []
    for line in path.read_text(errors='ignore').splitlines():
        fields = line.split()
        if len(fields) >= 8 and 'Etot' not in line:
            try:
                rows.append((fields[2], float(fields[-1])))
            except ValueError:
                continue
    return rows


def natural_projectors(path: Path) -> list[str]:
    """``[(l, energy, occupancy)]`` of the beta projectors, from the generation input."""
    # Newest first: a generation directory also keeps the original input (`U.orgin.in`),
    # and the projector list that matters is the one that produced the current file.
    generations = sorted(path.parent.glob('*.in'), key=lambda item: item.stat().st_mtime,
                         reverse=True)
    for candidate in generations:
        text = candidate.read_text(errors='ignore')
        if 'file_pseudopw' not in text:
            continue
        rows = re.findall(r'^\s*(\w+)\s+(\d+)\s+(-?\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)',
                          text, re.M)
        if rows:
            # columns: label, n, l, occupation, reference energy, cutoff radius
            return [f'{label}(l={l}, occ={occ}, e_ref={energy}, rc={rc})'
                    for label, _n, l, occ, energy, rc in rows]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('upf', nargs='+', type=Path)
    parser.add_argument('--compare', action='store_true',
                        help='Print a one-row-per-file table instead of the full report.')
    args = parser.parse_args()

    results = [inspect(path) for path in args.upf]
    for result in results:
        header = result['header']
        if args.compare:
            continue
        print(f'== {result["path"]}')
        print(f'   element / type / rel : {header["element"]} / {header["pseudo_type"]} / '
              f'{header["relativistic"]}')
        print(f'   z_valence            : {header["z_valence"]}   ({header["functional"]}, '
              f'core correction {header["core_correction"]})')
        print(f'   PP_BETA / PP_CHI     : {result["natoms_beta"]} / {result["nchi"]}')
        ld1 = result['path'].parent / 'ld1.test'
        if ld1.exists():
            rows = ld1_errors(ld1)
            if rows:
                worst = max(rows, key=lambda item: abs(item[1]))
                print('   ld1.test errors [Ry] : ' + ', '.join(f'{name} {value:+.5f}'
                                                              for name, value in rows))
                print(f'   worst                : {worst[0]} {abs(worst[1]) * 1000:.2f} mRy')
        else:
            print('   ld1.test             : (not in this directory)')
        for key, label in (('cond_S', 'cond(projector overlap S)'),
                           ('cond_D', 'cond(PP_DIJ)')):
            if key in result:
                print(f'   {label:<24}: {result[key]:.3g}')
        projectors = natural_projectors(result['path'])
        if projectors:
            print('   projectors (from the generation input): ' + ', '.join(projectors))
        print()

    if args.compare and results:
        print(f'{"file":<46} {"z_val":>5} {"beta":>4} {"chi":>4} {"cond(S)":>10} {"cond(D)":>10} '
              f'{"ld1 worst [mRy]":>16}')
        for result in results:
            header = result['header']
            ld1 = result['path'].parent / 'ld1.test'
            worst = 'n/a'
            if ld1.exists():
                errors = [abs(value) for _, value in ld1_errors(ld1)]
                if errors:
                    worst = f'{max(errors) * 1000:.2f}'
            print(f'{str(result["path"]):<46} {header["z_valence"] or "?":>5} '
                  f'{result["natoms_beta"]:>4} {result["nchi"]:>4} '
                  f'{result.get("cond_S", float("nan")):>10.3g} '
                  f'{result.get("cond_D", float("nan")):>10.3g} {worst:>16}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
