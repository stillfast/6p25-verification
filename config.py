"""Central configuration for the U-14ve `ai_v1/6p25` NC pseudopotential verification.

This project verifies **one** pseudopotential — ``U.pbe-n-nc.UPF`` from
``uranium-ppgen/ai_v1/nc6``: 14 valence electrons, norm-conserving,
scalar-relativistic, NLCC, generated with ld1.x, with **six** projectors
(6S/7S at 1.40, 6P 1.60, 6D 2.20, 5F 2.00 bohr, plus a second 5F at occupation 0
and reference energy +0.05 Ry).  Scope: **all ten** ACWF systems (4 unaries + 6 oxides), one 7-point EOS each,
under the ACWF ``verification-PBE-v1`` standard.

Provenance note: this file is byte-identical to the current
``v13/pp/U.pbe-n-nc.UPF`` and differs from the file that the ``v13`` campaign of
``../u14ve-verification`` verified (``v13/rd/runs/rlderiv/rlderiv_5p0/U.pbe-n-nc.UPF``,
md5 ``3df70b81…``) only in one echoed line inside ``<PP_INFO>`` (``nld = 4`` vs
``6``); outside ``PP_INFO`` the two files are byte-identical, i.e. **the
pseudopotential data is the same**.  This campaign therefore also serves as an
independent replication of the ``v13`` result, from a different file and a
different AiiDA set.

Everything a user is likely to want to change lives here: the pseudopotential
under test, the code / computer, the structure group, the calculation standard
and the SSSP-like acceptance criteria.

Nothing in this file imports AiiDA at module level, so it can be inspected
with a plain ``python`` interpreter.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
#: Directory holding the pseudopotential under test.  By default it is expected in
#: the project root: symlink or copy ``U.pbe-n-nc.UPF`` next to this ``config.py``
#: (the delivered file is shipped in the repository root, generated in the
#: ``uranium-ppgen/ai_v1/6p25/`` directory), or point
#: ``AI6P25V_PSEUDO_DIR`` at the folder that contains it together with
#: ``O_ONCV_PBE-1.0.upf``.
PSEUDO_DIR = Path(os.environ.get('AI6P25V_PSEUDO_DIR', PROJECT_ROOT))

#: The NC oxygen pseudopotential used for the oxide systems.  It has to be a
#: norm-conserving pseudo to be consistent with the NC uranium pseudopotential
#: (mixing NC and PAW/USPP would break the comparison).  ``O_ONCV_PBE-1.0.upf``
#: comes from http://www.pseudo-dojo.org/ (PseudoDojo, Hamann ONCV, PBE, 6 valence
#: electrons).  Override the whole path with ``AI6P25V_O_PSEUDO_FILE``.
O_PSEUDO_FILE = Path(
    os.environ.get('AI6P25V_O_PSEUDO_FILE', PSEUDO_DIR / 'O_ONCV_PBE-1.0.upf')
)

#: Where the EOS / analysis results are written.
OUTPUTS_DIR = PROJECT_ROOT / '4-analyze' / 'outputs'

# ---------------------------------------------------------------------------
# AiiDA
# ---------------------------------------------------------------------------

AIIDA_PROFILE = os.environ.get('AIIDA_PROFILE', 'aiida_profile')

#: Prefix of every AiiDA set / group / results file name of this project
#: (``<SET_PREFIX>-<pseudo key>-verification-PBE-v1``).  ``ai6p25`` is taken by
#: ``../rcbest-verification``, which verifies the *other* file of the same folder
#: (``6p25/rc_best/U.pbe-n-nc.UPF``, md5 ``c61b6ebf…``), so this project uses
#: ``ai6p25v`` and the two can never share a group or a results file.
SET_PREFIX = os.environ.get('AI6P25V_SET_PREFIX', 'ai6p25v')

#: AiiDA code label (``label@computer``) used for every ``pw.x`` calculation.
CODE_LABEL = os.environ.get('AI6P25V_CODE', 'qe@yeesuan')

#: Metadata options attached to every ``pw.x`` calculation.
COMPUTER_OPTIONS = {
    'resources': {
        'num_machines': 1,
        'num_mpiprocs_per_machine': 56,
        'tot_num_mpiprocs': 56,
    },
    'max_wallclock_seconds': 7200,
    'queue_name': 'q_ysuan',
    'withmpi': True,
}

#: Maximum number of EOS workchains submitted in parallel by the controller.
MAX_CONCURRENT = 24

# ---------------------------------------------------------------------------
# Pseudopotentials under test
# ---------------------------------------------------------------------------

#: The uranium pseudopotential under test: ``U.pbe-n-nc.UPF`` from
#: ``uranium-ppgen/ai_v1/6p25/`` (ld1.x route, 14 valence
#: electrons, scalar-relativistic, NLCC, PBE; md5 ``024f9a435d4b4c50e9267d14ff369f4e``,
#: numerically identical to the verified ``v13`` content — see the module docstring).
#:
#: ``key``       short identifier, used in set names, group labels and filenames
#: ``upf``       file name inside :data:`PSEUDO_DIR`, or an absolute path
#: ``rel``       ``scalar`` or ``full``
#: ``family``    label of the ``CutoffsPseudoPotentialFamily`` that is created
#: ``default_cutoffs`` fallback ``(ecutwfc, ecutrho)`` in Ry, used until the
#:               cutoff-convergence step (folder ``2-convergence``) has written
#:               a ``cutoffs.json`` file with converged values; 150 Ry here is a
#:               placeholder inherited from the v13 scan of the same pseudopotential
#:               data, **not** yet an EOS-verified cutoff for this set.  The UPF
#:               header carries no recommendation (``wfc_cutoff = 0``)
PSEUDOS = {
    '6p25': {
        'key': '6p25',
        'tag': '6P25',
        'z_valence': 14,
        'upf': 'U.pbe-n-nc.UPF',
        'rel': 'scalar',
        'description': (
            'U, PBE, NC, 14 valence electrons, scalar-relativistic, from `ai_v1/6p25` '
            '(rcut 6s 1.50 / 7s 1.20 / 6p 1.60 / 6d 2.40 / 5f 1.30 bohr; 6 projectors: 6S, 7S, '
            '6P, 6D, 5F and a second 6P at occupation 0 with reference energy -0.25 Ry)'
        ),
        'family': 'U-6p25+O_ONCV-1.0/QE/PBE',
        'default_cutoffs': {'U': (150.0, 600.0)},
    },
}

# ---------------------------------------------------------------------------
# Scope of this project
# ---------------------------------------------------------------------------

#: This project runs the **full** ten-system campaign (4 unaries + 6 oxides), so the
#: default of every script that walks configurations is all ten systems.  (The
#: two-system screen used elsewhere in this workspace is the cheap pre-filter; here
#: the aim is the published comparison, and the campaign doubles as a replication
#: of the v13 numbers.)
VERIFICATION_CONFIGURATIONS = ('X/SC', 'X/BCC', 'X/FCC', 'X/Diamond',
                               'XO', 'XO2', 'XO3', 'X2O', 'X2O3', 'X2O5')

#: Value written to ``CONTROL.disk_io`` of every ``pw.x`` input.
#:
#: ``'nowf'`` tells Quantum ESPRESSO not to write the wavefunction files of the
#: scratch directory.  It has **no effect on any computed quantity** (the SCF is
#: entirely in memory); it only removes the restart files that this project never
#: uses.  It is essential in practice: with the default (``'low'``) each SCF of
#: this project writes several GB, which exhausts the Lustre user quota of the
#: account after a few dozen calculations.
DISK_IO = 'nowf'

#: Ask the sub-workchain to delete the remote scratch of each calculation once
#: it has been retrieved (AiiDA's ``clean_workdir``).  With ``DISK_IO = 'nowf'``
#: only a few MB per calculation are left behind, but cleaning keeps the shared
#: filesystem tidy in any case.
CLEAN_REMOTE_SCRATCH = True

#: Recommended cutoffs of the oxygen pseudopotential (Ry).  Taken from the
#: PseudoDojo / ONCV tables shipped with ``O_ONCV_PBE-1.0.upf``.  The effective
#: plane-wave cutoff of a mixed U/O system is the maximum over its elements, so
#: a uranium cutoff below 60 Ry would still be pushed up by oxygen.
O_CUTOFFS = (60.0, 480.0)

# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------

#: AiiDA group holding the ten uranium verification structures.  It was imported
#: from the published ACWF *uranium-verification-PBE-v1* archive and contains the
#: four unaries (X/SC, X/BCC, X/FCC, X/Diamond) plus the six oxides (XO, XO2,
#: XO3, X2O, X2O3, X2O5).
SOURCE_STRUCTURES_GROUP = os.environ.get(
    'U14VE_SOURCE_STRUCTURES_GROUP',
    'acwf-verification/uranium-verification-PBE-v1/structures/quantum_espresso',
)

#: Configurations to run, in the order used for reporting.
UNARY_CONFIGURATIONS = ('X/SC', 'X/BCC', 'X/FCC', 'X/Diamond')
OXIDE_CONFIGURATIONS = ('XO', 'XO2', 'XO3', 'X2O', 'X2O3', 'X2O5')
ALL_CONFIGURATIONS = UNARY_CONFIGURATIONS + OXIDE_CONFIGURATIONS

# ---------------------------------------------------------------------------
# ACWF / SSSP reference data (all-electron EOS fits)
# ---------------------------------------------------------------------------

#: The official ``acwf-verification-scripts`` checkout of this machine.  Only the
#: ``acwf_paper_plots/code-data`` sub-folder is read (the all-electron averages).
#: A sibling checkout named ``acwf-verification-scripts`` is found by default.
ACWF_SCRIPTS_DIR = Path(
    os.environ.get(
        'U14VE_ACWF_SCRIPTS',
        PROJECT_ROOT.parent / 'acwf-verification-scripts',
    )
)
REFERENCE_DATA_DIR = ACWF_SCRIPTS_DIR / 'acwf_paper_plots' / 'code-data'

#: ``{set_kind: filename}`` with the all-electron reference EOS fits.
REFERENCE_FILES = {
    'unaries': 'results-unaries-verification-PBE-v1-AE-average.json',
    'oxides': 'results-oxides-verification-PBE-v1-AE-average.json',
}

#: The official, published ACWF runs of the *other* codes, one AiiDA set per code and
#: per structure kind.  Unlike :data:`REFERENCE_FILES` -- the all-electron averages,
#: which ship Birch-Murnaghan fits only -- these files also contain the seven computed
#: ``eos_data`` points, so a reference code can be drawn exactly like one of our
#: pseudopotentials (points + fit) and its ``delta`` against the all-electron average
#: can be computed with the same code path.
#:
#: ``{kind}`` is ``unaries`` or ``oxides``.  The list is the same one used by
#: ``4-analyze/make_comparison_report.py`` (``EXTERNAL_METHODS``); keep the two in step.
ACWF_REFERENCE_OUTPUTS_DIR = ACWF_SCRIPTS_DIR / '3-analyze' / 'outputs'

REFERENCE_CODES = {
    'qe-sssp': {
        'label': 'QE (SSSP-prec-1.3)',
        'filename': 'results-{kind}-verification-PBE-v1-Quantum ESPRESSO@PW|SSSP-prec-v1.3.json',
    },
    'vasp': {
        'label': 'VASP (PW|GW-PAW54*)',
        'filename': 'results-{kind}-verification-PBE-v1-VASP@PW|GW-PAW54*.json',
    },
    'fleur': {
        'label': 'FLEUR (LAPW+LO)',
        'filename': 'results-{kind}-verification-PBE-v1-FLEUR@LAPW+LO.json',
    },
    'wien2k': {
        'label': 'WIEN2k ((L)APW+lo+LO)',
        'filename': 'results-{kind}-verification-PBE-v1-WIEN2k@(L)APW+lo+LO.json',
    },
    'castep': {
        'label': 'CASTEP (PW|C19MK2)',
        'filename': 'results-{kind}-verification-PBE-v1-CASTEP@PW|C19MK2.json',
    },
}
