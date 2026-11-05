import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Input LUT uploaded by the user
lut_path = "/mnt/data/Pasted text.txt"

# Output files
out_png = "/mnt/data/scale_factor_four_plane_robust_vs_eff2_binned_linear_eff05to1.png"
out_pdf = "/mnt/data/scale_factor_four_plane_robust_vs_eff2_binned_linear_eff05to1.pdf"
out_csv = "/mnt/data/scale_factor_four_plane_robust_vs_eff2_binned_linear_eff05to1_curves.csv"

df = pd.read_csv(lut_path)

eff_cols = [
    "eff_empirical_1",
    "eff_empirical_2",
    "eff_empirical_3",
    "eff_empirical_4",
]
target = "scale_factor__four_plane_robust_hz"

lut = df.dropna(subset=eff_cols + [target]).copy()

# Keep only the display/domain region requested for plane-2 efficiency
lut_plot = lut[(lut["eff_empirical_2"] >= 0.5) & (lut["eff_empirical_2"] <= 1.0)].copy()

# Group coordinate for the three non-varied planes
lut["eff_134_mean"] = lut[["eff_empirical_1", "eff_empirical_3", "eff_empirical_4"]].mean(axis=1)
lut_plot["eff_134_mean"] = lut_plot[["eff_empirical_1", "eff_empirical_3", "eff_empirical_4"]].mean(axis=1)

# Bins restricted to 0.5-1.0
eff2_bin_width = 0.08
eff2_edges = np.arange(0.50, 1.0001, eff2_bin_width)
eff2_centers = 0.5 * (eff2_edges[:-1] + eff2_edges[1:])

fixed_efficiencies = [0.50, 0.60, 0.70, 0.80, 0.90]
fixed_band_half_width = 0.06

rows = []

plt.figure(figsize=(7.4, 4.9), dpi=300)
ax = plt.gca()

# Background LUT samples restricted to requested range
ax.scatter(
    lut_plot["eff_empirical_2"],
    lut_plot[target],
    s=14,
    alpha=0.17,
    color="0.35",
    linewidths=0,
    label="LUT samples"
)

colors = plt.cm.viridis(np.linspace(0.15, 0.88, len(fixed_efficiencies)))

for fixed, color in zip(fixed_efficiencies, colors):
    band = lut[
        (lut["eff_134_mean"] >= fixed - fixed_band_half_width)
        & (lut["eff_134_mean"] < fixed + fixed_band_half_width)
    ].copy()

    x_vals, y_vals, y_low, y_high = [], [], [], []

    for left, right, center in zip(eff2_edges[:-1], eff2_edges[1:], eff2_centers):
        subset = band[
            (band["eff_empirical_2"] >= left)
            & (band["eff_empirical_2"] < right)
        ]

        if len(subset) >= 2:
            values = subset[target].to_numpy(float)

            median = np.nanmedian(values)
            q25 = np.nanpercentile(values, 25)
            q75 = np.nanpercentile(values, 75)

            x_vals.append(center)
            y_vals.append(median)
            y_low.append(q25)
            y_high.append(q75)

            rows.append({
                "fixed_efficiency_band_center_for_planes_1_3_4": fixed,
                "fixed_efficiency_band_half_width": fixed_band_half_width,
                "eff_empirical_2_bin_left": left,
                "eff_empirical_2_bin_right": right,
                "eff_empirical_2_bin_center": center,
                "median_scale_factor__four_plane_robust_hz": median,
                "q25_scale_factor__four_plane_robust_hz": q25,
                "q75_scale_factor__four_plane_robust_hz": q75,
                "n_lut_points": len(subset),
            })

    if x_vals:
        x_vals = np.array(x_vals)
        y_vals = np.array(y_vals)
        y_low = np.array(y_low)
        y_high = np.array(y_high)

        ax.plot(
            x_vals,
            y_vals,
            marker="o",
            markersize=5.0,
            linewidth=2.6,
            color=color,
            label=fr"$\langle\varepsilon_1,\varepsilon_3,\varepsilon_4\rangle \approx {fixed:.2f}$"
        )

        ax.fill_between(
            x_vals,
            y_low,
            y_high,
            color=color,
            alpha=0.13,
            linewidth=0
        )

ax.set_xlabel(r"Plane-2 efficiency, $\varepsilon_2$", fontsize=12)
ax.set_ylabel("Scale factor from four-plane robust rate", fontsize=12)
ax.set_title("Binned scale factor vs plane-2 efficiency", fontsize=13, pad=10)

# Linear scale and requested efficiency range
ax.set_xlim(0.50, 1.00)

# Use the visible samples and curves to set a more useful linear y-range.
visible_values = []
if len(lut_plot):
    visible_values.extend(lut_plot[target].to_numpy(float))
for row in rows:
    visible_values.append(row["q75_scale_factor__four_plane_robust_hz"])
visible_values = np.array([v for v in visible_values if np.isfinite(v)])
ax.set_ylim(0, max(np.nanpercentile(visible_values, 98) * 1.15, 10))

ax.grid(True, which="major", alpha=0.28, linewidth=0.7)
ax.tick_params(axis="both", labelsize=10)

ax.legend(
    fontsize=8.0,
    loc="upper right",
    frameon=True,
    framealpha=0.92,
    borderpad=0.6
)

ax.text(
    0.02, 0.03,
    f"Binned medians; ε₂ bin width = {eff2_bin_width:.2f}\n"
    f"Bands use mean(ε₁, ε₃, ε₄) ± {fixed_band_half_width:.2f}; shaded region = IQR",
    transform=ax.transAxes,
    fontsize=8.1,
    va="bottom",
    ha="left",
    bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="0.8", alpha=0.92)
)

plt.tight_layout()
plt.savefig(out_png, bbox_inches="tight", dpi=300)
plt.savefig(out_pdf, bbox_inches="tight")
plt.show()

pd.DataFrame(rows).to_csv(out_csv, index=False)

out_png, out_pdf, out_csv
