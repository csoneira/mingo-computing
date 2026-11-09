# TRASGO_TESTS_AND_TOOLS legacy archive

> **LEGACY / HISTORICAL ONLY.** This directory keeps studies that have not been promoted elsewhere, plus provenance documentation. Exact duplicate source files were removed after copies were placed in their classified locations. It is not part of the active `mingo-computing` pipeline and should not be imported or executed by production tooling.

## Provenance

- Original repository: `https://github.com/csoneira/TRASGO_TESTS_AND_TOOLS`
- Source branch: `main`
- Source commit: `01f2bb487dcea8d06417377543d70c91a7a469d9`
- Source commit date: 2025-04-02
- Archived into `mingo-computing`: 2026-10-21

The remaining files are historical source snapshots. The archive manifest records original paths, current dispositions, and source Git blob SHAs so relocated copies remain auditable against the source repository.

## Archive policy

The purpose of this archive is **concept recovery, not data preservation**. The original repository mixed analysis/source code with generated numerical products, model/tuner outputs and large working artifacts. This legacy copy intentionally keeps representative human-written source for each distinct study/tool family while omitting data and generated products.

### Intentionally excluded

- NumPy data products such as `*.npy` and `*.npz`.
- Keras/model products such as `*.h5` and tuner/trial output directories.
- The hidden `.fuse_hidden...` temporary file.
- CSV/MAT/raw/input datasets and generated plots/results. These were never the objective of this archival migration.
- `CFD Simulation/CFD_notebook.ipynb` (about 789 kB), intentionally skipped as a comparatively large notebook. The compact `CFD_simulation.py` concept script is retained instead.
- Numerous scratch, `test`, `untitled`, `trash`, near-duplicate and intermediate variants when a clearer representative script for the same concept is retained.

This means this directory is **not a byte-for-byte mirror of the former repository**. It is the durable conceptual/source subset requested for consolidation into `mingo-computing`.

## Main retained concepts

- constant-fraction / CFD timing simulation;
- geometrical acceptance and detector efficiency simulations;
- energy/velocity inference from timing;
- MIP energy loss and Molière-scattering studies;
- geomagnetic cutoff-rigidity calculation;
- neutron energy/rate analysis;
- PID and PSD exploratory analyses;
- azimuth/phi and atmospheric-pressure studies;
- SCIMIN SiPM-position reconstruction and neural-network prototype;
- slewing correction;
- TimTrack fitting/analysis;
- system-clock timing precision;
- waiting-time / Poisson-process study;
- XY extraction and strip-width/Y-position resolution studies.

See `ARCHIVE_MANIFEST.md` for the original paths, current locations, and source blob SHAs. The original repository README is stored as `ORIGINAL_README.md`.

## Revival rule

Do not repair these files in place merely to make them runnable. If an old idea becomes useful, copy or reimplement that idea in the active `mingo-computing` structure, add tests/documentation there, and leave this legacy snapshot as provenance.
