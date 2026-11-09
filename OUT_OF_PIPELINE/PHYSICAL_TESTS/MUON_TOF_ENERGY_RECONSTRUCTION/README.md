# Muon TOF energy reconstruction

Ancillary detector-physics study of muon-energy reconstruction from time-of-flight measurements across equidistant detector planes.

This directory is intentionally outside the production analysis path. It is a standalone calculation used to understand how the achievable energy resolution scales with detector geometry and timing resolution.

## Main result

For `m` equidistant planes spanning a total distance `d`, with independent per-plane timing resolution `sigma_T`, the least-squares uncertainty of the fitted TOF slope is

\[
\sigma_{\mathrm{slope}} = \frac{\sigma_T}{\sqrt{S_{xx}}},
\qquad
S_{xx}=\frac{d^2 m(m+1)}{12(m-1)}.
\]

For moderate or large `m`, this becomes approximately

\[
\sigma_{\mathrm{slope}} \simeq \frac{\sqrt{12}\,\sigma_T}{d\sqrt{m}}.
\]

Therefore a useful leading detector figure of merit is

\[
\boxed{\mathrm{FOM}_{\mathrm{TOF}} \propto \frac{d\sqrt{m}}{\sigma_T}}
\]

Higher is better. Increasing the lever arm is especially powerful: doubling `d` gives approximately the same slope-precision improvement as quadrupling the number of planes.

## Physics limitation

The reconstructed total muon energy is

\[
E = \frac{m_\mu}{\sqrt{1-\beta^2}}.
\]

Near the relativistic limit, small velocity errors are strongly amplified:

\[
\frac{\delta E}{E} \approx \gamma^2\beta^2\frac{\delta v}{v}
\simeq \gamma^2\frac{\delta v}{v}.
\]

Consequently, TOF is naturally much more useful for lower-energy muons. Multi-GeV energy reconstruction becomes rapidly ill-conditioned unless both the timing resolution and detector lever arm are exceptional.

## Script

`muon_tof_energy_reconstruction.py` keeps the physical model and the four contour plots of the original March-2025 study, with two practical changes:

1. The default calculation uses the exact Gaussian distribution of the OLS TOF slope and Gauss-Hermite quadrature instead of explicitly generating an `m x num_samples` timing matrix for every parameter point.
2. The two variables not shown in each 2-D contour are averaged before plotting, avoiding repeated `(x, y)` coordinates with different residual values.

The original parameter ranges are retained. The default grid is reduced for routine execution; `--full-grid` restores the original `100 x 96 x 100 x 100` scan and is intentionally expensive.

### Typical run

```bash
python3 muon_tof_energy_reconstruction.py --no-show
```

### Monte Carlo mode

```bash
python3 muon_tof_energy_reconstruction.py --mode monte-carlo --samples 10000 --no-show
```

### Outputs

The output directory contains:

- `1_energy_vs_timing.png`
- `2_energy_vs_planes.png`
- `3_timing_vs_planes.png`
- `4_distance_vs_planes.png`
- `muon_tof_scan.npz`

The residual is clipped at 50% for plotting, following the original script. Thus a saturated region means **50% or worse**, not necessarily exactly 50%.

The energy variable is **total relativistic energy**, not kinetic energy.
