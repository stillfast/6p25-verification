# Third-party notices

This repository redistributes two pseudopotential files and a small set of
reference data. Their terms are below; everything else is covered by the
repository's MIT `LICENSE`.

## `O_ONCV_PBE-1.0.upf`

- **Origin**: SG15 / ONCV norm-conserving pseudopotential set
  (M. Schlipf and F. Gygi, *Comput. Phys. Commun.* **196**, 36 (2015)),
  generated with ONCVPSP 2.1.1 by D. R. Hamann.
- **Author field in the UPF**: Martin Schlipf and Francois Gygi.
- **License**: Creative Commons Attribution-ShareAlike 4.0 International
  (CC BY-SA 4.0), as stated in the file's own `PP_INFO` header.
  See <https://creativecommons.org/licenses/by-sa/4.0/>.
- **md5**: `1322303c3d9d6d180a3549dee7f99d61`
- The file is redistributed **unmodified**; the CC BY-SA 4.0 terms apply to
  this file, not to the rest of the repository.

## `U.pbe-n-nc.UPF`

- Generated for this work with `ld1.x` (Quantum ESPRESSO 7.4) by Guozhou Li;
  no third-party rights are involved.
- **md5**: `024f9a435d4b4c50e9267d14ff369f4e`

## `data/reference/results-*-verification-PBE-v1-AE-average.json`

- Copied verbatim from the AiiDA common workflows verification project,
  [`aiidateam/acwf-verification-scripts`](https://github.com/aiidateam/acwf-verification-scripts)
  (MIT license), which accompanies E. Bosoni *et al.*, *Nat. Rev. Phys.* **6**,
  45 (2024).
- Only the two all-electron averages are vendored here (≈195 kB); the
  published per-code results are fetched separately by
  `tools/fetch_reference_data.sh`.

## `data/structures/uranium-verification-PBE-v1_structures.aiida`

- AiiDA archive of the ten ACWF `uranium-verification-PBE-v1` structures,
  derived from the same `acwf-verification-scripts` project (MIT license).
