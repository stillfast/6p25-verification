"""The calculation standard applied to every QE run of this project.

The goal is that the two candidate uranium pseudopotentials are tested exactly
the way the *ACWF verification* and the *SSSP* verification test Quantum
ESPRESSO pseudopotentials, so that the numbers produced here can be compared
directly with the published all-electron reference EOS.

Two presets are provided:

``acwf-verification-PBE-v1`` (default)
    The ``verification-PBE-v1`` protocol of
    ``aiida-common-workflows/workflows/relax/quantum_espresso/protocol.yml``,
    which is the protocol used by the ``acwf-verification-scripts`` to produce
    the published SSSP reference data::

        pseudo_family            max of the recommended cutoffs
        kpoints_distance         0.06  1/Angstrom
        conv_thr_per_atom        0.1e-9 Ry
        etot_conv_thr_per_atom   0.5e-5 Ry
        forc_conv_thr            0.5e-4 Ry/bohr
        smearing / degauss       fd / 0.0045 Ry
        mixing_beta              0.4
        EOS                      7 volumes, +-2 % steps (0.94 ... 1.06)

``sssp-eos``
    The EOS protocol of the official SSSP verification workflow
    (``aiida-sssp-workflow``, ``protocol/eos.yml``, entry ``standard``), which
    differs from the ACWF protocol only in ``conv_thr_per_atom`` (1.0e-9 instead
    of 0.1e-9).  Same k-point density, same smearing and same 7-point EOS.

Both are intentionally *non*-spin-orbit standards: the ACWF all-electron
reference data describes a scalar-relativistic EOS, so the primary verification
must be run without spin-orbit coupling.  A fully relativistic pseudopotential
used without ``lspinorb`` is handled by Quantum ESPRESSO through the
``j``-averaged (i.e. scalar-relativistic-like) potential, which makes it
directly comparable with the same reference.  An additional, clearly separated
spin-orbit mode is available for the fully relativistic pseudo (see
``spin_orbit`` below), but its results must *not* be compared with the
scalar-relativistic ACWF references.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

import config

Cutoffs = Tuple[float, float]

# ---------------------------------------------------------------------------
# Standards
# ---------------------------------------------------------------------------

STANDARDS: Dict[str, Dict[str, Any]] = {
    'acwf-verification-PBE-v1': {
        'name': 'acwf-verification-PBE-v1',
        'description': (
            'ACWF verification-PBE-v1 protocol (the protocol behind the published '
            'SSSP/acwf-verification reference data)'
        ),
        'kpoints_distance': 0.06,
        'conv_thr_per_atom': 0.1e-9,
        'etot_conv_thr_per_atom': 0.5e-5,
        'forc_conv_thr': 0.5e-4,
        'smearing': 'fd',
        'degauss': 0.0045,
        'mixing_beta': 0.4,
        'electron_maxstep': 80,
        'scale_count': 7,
        'scale_increment': 0.02,
    },
    'sssp-eos': {
        'name': 'sssp-eos',
        'description': 'SSSP verification EOS protocol (aiida-sssp-workflow eos.yml / standard)',
        'kpoints_distance': 0.06,
        'conv_thr_per_atom': 1.0e-9,
        'etot_conv_thr_per_atom': 0.5e-5,
        'forc_conv_thr': 0.5e-4,
        'smearing': 'fd',
        'degauss': 0.0045,
        'mixing_beta': 0.4,
        'electron_maxstep': 80,
        'scale_count': 7,
        'scale_increment': 0.02,
    },
}

DEFAULT_STANDARD = 'acwf-verification-PBE-v1'


def get_standard(name: Optional[str] = None) -> Dict[str, Any]:
    """Return the requested standard (defaulting to :data:`DEFAULT_STANDARD`)."""
    name = name or DEFAULT_STANDARD
    try:
        return dict(STANDARDS[name])
    except KeyError:
        raise ValueError(
            f"Unknown standard {name!r}. Available: {', '.join(sorted(STANDARDS))}"
        ) from None


# ---------------------------------------------------------------------------
# PW input construction
# ---------------------------------------------------------------------------


def effective_cutoffs(
    cutoffs: Mapping[str, Cutoffs],
    o_cutoffs: Cutoffs,
) -> Cutoffs:
    """Return the ``(ecutwfc, ecutrho)`` of a mixed system.

    Quantum ESPRESSO applies one global pair of cutoffs to the whole cell, so the
    effective values are the maximum over the elements actually present, exactly
    as ``PseudoPotentialFamily.get_recommended_cutoffs`` computes them.
    """
    wfc = max([value[0] for value in cutoffs.values()] + [o_cutoffs[0]])
    rho = max([value[1] for value in cutoffs.values()] + [o_cutoffs[1]])
    return float(wfc), float(rho)


def build_pw_parameters(
    natoms: int,
    cutoffs: Cutoffs,
    standard: Mapping[str, Any],
    spin_orbit: bool = False,
) -> Dict[str, Any]:
    """Return the complete ``pw.x`` namelist dictionary of the standard.

    The dictionary is built from scratch (rather than by patching whatever the
    plugin protocol happens to produce) so that the recorded provenance is
    unambiguous and reproducible.

    :param natoms: number of atoms in the simulation cell; the per-atom
        convergence thresholds are extensive.
    :param cutoffs: ``(ecutwfc, ecutrho)`` in Ry.
    :param standard: one of the :data:`STANDARDS` entries.
    :param spin_orbit: add ``noncolin``/``lspinorb`` for a fully relativistic
        calculation.
    """
    ecutwfc, ecutrho = cutoffs
    parameters: Dict[str, Any] = {
        'CONTROL': {
            'calculation': 'scf',
            'tprnfor': True,
            'tstress': True,
            'disk_io': config.DISK_IO,
            'forc_conv_thr': standard['forc_conv_thr'],
            'etot_conv_thr': natoms * standard['etot_conv_thr_per_atom'],
        },
        'ELECTRONS': {
            'conv_thr': natoms * standard['conv_thr_per_atom'],
            'mixing_beta': standard['mixing_beta'],
            'electron_maxstep': standard['electron_maxstep'],
        },
        'SYSTEM': {
            'ecutwfc': float(ecutwfc),
            'ecutrho': float(ecutrho),
            'occupations': 'smearing',
            'smearing': standard['smearing'],
            'degauss': standard['degauss'],
            'nosym': False,
        },
    }

    if spin_orbit:
        parameters['SYSTEM']['noncolin'] = True
        parameters['SYSTEM']['lspinorb'] = True
        parameters['SYSTEM']['nspin'] = 4

    return parameters


def describe_standard(standard: Mapping[str, Any], cutoffs: Cutoffs) -> str:
    """Return a human readable summary used by the setup checks and the launcher.

    The convergence thresholds are quoted per atom; the values written to the
    ``pw.x`` input are ``natoms`` times larger (they are extensive quantities).
    """
    ecutwfc, ecutrho = cutoffs
    return (
        f"standard            : {standard['name']} -- {standard['description']}\n"
        f"  ecutwfc / ecutrho : {ecutwfc} / {ecutrho} Ry (dual {ecutrho / ecutwfc:.1f})\n"
        f"  k-points distance : {standard['kpoints_distance']} 1/Angstrom\n"
        f"  conv_thr          : natoms * {standard['conv_thr_per_atom']:.1e} Ry\n"
        f"  etot_conv_thr     : natoms * {standard['etot_conv_thr_per_atom']:.1e} Ry\n"
        f"  forc_conv_thr     : {standard['forc_conv_thr']:.1e} Ry/bohr\n"
        f"  smearing/degauss  : {standard['smearing']} / {standard['degauss']} Ry\n"
        f"  EOS               : {standard['scale_count']} volumes, "
        f"+-{100 * standard['scale_increment'] * (standard['scale_count'] - 1) / 2:.0f} % "
        f"in {100 * standard['scale_increment']:.0f} % steps"
    )


# ---------------------------------------------------------------------------
# SSSP-like acceptance criteria for the analysis
# ---------------------------------------------------------------------------

#: Bands used to colour-classify the three ACWF comparison metrics.
#:
#: ``delta``  energy difference between the pseudo and the all-electron EOS
#:            (meV/atom), evaluated over the +-6 % volume window
#: ``nu``     weighted relative difference of (V0, B0, B1) (%)
#: ``epsilon``  normalised area between the two EOS curves (dimensionless)
#:
#: The ``pass`` numbers are the widely quoted SSSP *precision* criteria
#: (delta <= 1 meV/atom, nu <= 0.5 %, epsilon <= 5 %); the ``good`` numbers are
#: the looser bands used to colour the ACWF verification plots.  They are
#: configurable because different publications quote slightly different
#: tolerances; see the README for the references.
CRITERIA: Dict[str, Dict[str, float]] = {
    'delta': {'pass': 1.0, 'good': 3.0, 'unit': 'meV/atom'},
    'nu': {'pass': 0.5, 'good': 2.0, 'unit': '%'},
    'epsilon': {'pass': 0.05, 'good': 0.20, 'unit': ''},
}

#: Weights of the ``nu`` metric, from ``quantities_for_comparison.py``.
WEIGHT_B0 = 1.0 / 20.0
WEIGHT_B1 = 1.0 / 400.0

#: SSSP cutoff-convergence criterion (``aiida-sssp-workflow`` ``criteria.yml``,
#: entry ``standard``: ``eos.bounds = [0.0, 0.2]``).  It is the ``nu``-like
#: distance between the EOS fit at a given cutoff and the EOS fit at the
#: reference (largest) cutoff, in percent.
CUTOFF_CONVERGENCE_NU_TOLERANCE = 0.2


def get_criterion(name: str) -> Dict[str, float]:
    """Return the acceptance criterion of a metric."""
    try:
        return dict(CRITERIA[name])
    except KeyError:
        raise ValueError(
            f"Unknown metric {name!r}. Available: {', '.join(sorted(CRITERIA))}"
        ) from None
