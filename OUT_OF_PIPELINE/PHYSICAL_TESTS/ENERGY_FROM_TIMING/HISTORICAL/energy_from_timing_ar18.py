# %%
# ----------------------------------------------------------------
# MUON ENERGY RECONSTRUCTION SIMULATION
# ----------------------------------------------------------------
# This script simulates the time-of-flight (TOF) method for 
# estimating muon energy based on timing measurements across 
# equidistant detector planes. It evaluates the effect of 
# timing resolution on energy reconstruction accuracy.
# 
# Two simulation scenarios:
#   1. Standard Simulation: Fixed distance and number of planes.
#   2. Extended Simulation: Varies distance, number of planes,
#      and timing resolution to explore parameter dependencies.
#
# Key Variables:
#   - d_total: Total distance between first and last detector planes (m)
#   - m: Number of equidistant detector planes
#   - energies: Array of muon energies (eV)
#   - sigma_T_values: Array of timing resolution values (ns)
#   - num_samples: Number of simulated TOF measurements per energy point
#
# Output:
#   - Energy residuals computed as the difference between 
#     true and reconstructed muon energy.
#   - Contour plots showing the dependence of reconstruction 
#     accuracy on timing resolution, number of planes, and distance.
#
# Author: csoneira@ucm.es
# Date: March 2025
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# STANDARD SIMULATION
# ----------------------------------------------------------------
# Keeping distance and number of planes constant
# ----------------------------------------------------------------

# import numpy as np
# import matplotlib.pyplot as plt

# percentage = True

# # Variables ----------------------------------------------------------------------
# d_total = 2  # Total distance in meters
# m = 3  # Number of equidistant planes
# energies = np.logspace(np.log10(0.32e9), np.log10(1e9), 50)  # Energy in eV
# sigma_T_values = np.linspace(0.010, 0.400, 50)  # Timing resolution values in ns
# # --------------------------------------------------------------------------------

# # Number of simulated events per energy point
# num_samples = 100000

# epsilon = 1e-12  # Small value to prevent sqrt errors
# m_mu = 105.66e6  # Muon mass in eV/c^2
# c = 3.0e8  # Speed of light in m/s
# plane_positions = np.linspace(0, d_total, m).reshape(m, 1)  # Equidistant positions for planes

# v_true = c * np.sqrt(1 - (m_mu / energies) ** 2)  # Velocity in m/s
# tof_true = plane_positions / v_true  # True TOF for each plane
# tof_true_ns = tof_true * 1e9  # Convert to ns

# # Arrays to store results
# E_mesh, sigma_T_mesh, mean_residuals, std_residuals, rel_residuals = [], [], [], [], []

# # Precompute least squares matrix for fitting (for speedup)
# A = np.hstack([plane_positions, np.ones_like(plane_positions)])  # Design matrix
# ATA_inv = np.linalg.inv(A.T @ A)  # Precompute inverse for least squares

# # Simulation loop over sigma_T values
# for sigma_T in sigma_T_values:
#     for i, energy in enumerate(energies):
#         # Generate TOF values by applying Gaussian noise correctly (fixed broadcasting issue)
#         tof_sim = tof_true_ns[:, i].reshape(m, 1) + np.random.normal(scale=sigma_T, size=(m, num_samples))

#         # Fit a straight line using least squares (vectorized)
#         ATy = A.T @ tof_sim  # Precompute dot product
#         coefficients = ATA_inv @ ATy  # Solve for coefficients
#         v_sim = 1 / (coefficients[0] * 1e-9)  # Extract velocity directly from fit

#         # Ensure numerical stability in sqrt()
#         denom = np.maximum(1 - (v_sim / c) ** 2, epsilon)  # Always positive
#         energy_sim = m_mu / np.sqrt(denom)  # Stable energy calculation

#         # Compute residuals (real energy - simulated energy)
#         residuals = np.abs(energy - energy_sim)

#         # Store results
#         E_mesh.append(energy / 1e9)  # Convert to GeV
#         sigma_T_mesh.append(sigma_T)
#         mean_residuals.append(np.nanmean(residuals) / 1e9)  # Convert to GeV
#         rel_residuals.append(np.nanmean(residuals) / energy * 100)
#         std_residuals.append(np.nanstd(residuals) / 1e9)  # Convert to GeV
        
#         if sigma_T == sigma_T_values[4] and i % 20 == 0:
#             plt.figure(figsize=(6, 4))
            
#             # Corrected scatter plot: ensure plane positions match TOF samples
#             plt.scatter(
#                   np.repeat(plane_positions.flatten(), 20),  # Repeat plane positions to match TOF shape
#                   tof_sim[:, :20].flatten(),  # Flatten TOF values to match scatter input
#                   color='blue', alpha=0.2, label="Simulated TOF"
#             )
            
#             # Plot fitted line using the mean coefficients
#             plt.plot(
#                   plane_positions.flatten(),  # Ensure proper shape
#                   (coefficients[0].mean() * plane_positions + coefficients[1].mean()).flatten(),
#                   color='red', label="Fitted Line"
#             )
            
#             plt.xlabel("Plane Position (m)")
#             plt.ylabel("Time of Flight (ns)")
#             plt.title(f"TOF Fit for Energy {energy/1e9:.2f} GeV, σ_T = {sigma_T:.3f} ns\n"
#                         f"v_true = {v_true[i]:.2e} m/s, v_fit = {v_sim.mean():.2e} m/s")
            
#             plt.grid(True, linestyle="--", linewidth=0.5)
#             plt.show()


# # Convert lists to arrays for plotting
# E_mesh = np.array(E_mesh)
# sigma_T_mesh = np.array(sigma_T_mesh)
# mean_residuals = np.array(mean_residuals)
# std_residuals = np.array(std_residuals)

# if percentage:
#     print("Mean relative residuals (%) calculation...")
#     mean_residuals = rel_residuals
#     mean_residuals = np.clip(mean_residuals, 0, 50)  # Clip residuals to a reasonable range

# # Reshape data for contour plotting
# E_grid = np.reshape(E_mesh, (len(sigma_T_values), len(energies)))
# sigma_T_grid = np.reshape(sigma_T_mesh, (len(sigma_T_values), len(energies)))
# mean_residuals_grid = np.reshape(mean_residuals, (len(sigma_T_values), len(energies)))

# # Create contour plot
# plt.figure(figsize=(8, 6))
# contour = plt.contourf(E_grid, sigma_T_grid, mean_residuals_grid, levels=50, cmap="viridis_r")

# # Add contour lines
# plt.contour(E_grid, sigma_T_grid, mean_residuals_grid, levels=15, colors="black", linewidths=0.5)

# # Add color bar
# plt.colorbar(contour, label="Mean Energy Residual (%)" if percentage else "Mean Energy Residual (GeV)")

# # Labels and title
# plt.xlabel("Muon Energy (GeV)")
# plt.ylabel("Timing Resolution σ_T (ns)")
# plt.title("Energy Residual vs Timing Resolution and Muon Energy")

# # Show the plot
# plt.show()

# %%

import numpy as np
import matplotlib.pyplot as plt

percentage = True

# %%

# ----------------------------------------------------------------
# EXTENDED SIMULATION
# ----------------------------------------------------------------
# Extended simulation: vary energy, sigma_T, and number of planes,
# plotting rel_residual in contour plots
# ----------------------------------------------------------------

# Variables to scan over ---------------------------------------------------
d_total_values = np.linspace(0.5, 100, 100)  # Total distances in meters
m_values = np.arange(4, 100, 1)  # Number of equidistant planes as integers
energies_values = np.logspace(np.log10(0.32e9), np.log10(10e9), 100)  # Energy in eV
sigma_T_values = np.linspace(0.010, 0.500, 100)  # Timing resolution values in ns
# --------------------------------------------------------------------------

# Constants
m_mu = 105.66e6  # Muon mass in eV/c^2
c = 3.0e8  # Speed of light in m/s
epsilon = 1e-12  # Small value to prevent sqrt errors
num_samples = 10000  # Adjusted for efficiency

# Arrays to store results
E_mesh, sigma_T_mesh, plane_mesh, d_mesh, rel_residuals = [], [], [], [], []

from tqdm import tqdm  # Import progress bar

# Define total iterations
total_iterations = (
    len(d_total_values) * len(m_values) * len(sigma_T_values) * len(energies_values)
)

# Initialize progress bar
progress_bar = tqdm(total=total_iterations, desc="Running Simulation", unit="iter")

# Simulation loop over all variables
for d_total in d_total_values:
    for m in m_values:
        plane_positions = np.linspace(0, d_total, m).reshape(m, 1)  # Equidistant positions for planes
        
        # Precompute least squares matrix for fitting (for speedup)
        A = np.hstack([plane_positions, np.ones_like(plane_positions)])  # Design matrix
        ATA_inv = np.linalg.inv(A.T @ A)  # Precompute inverse for least squares

        for sigma_T in sigma_T_values:
            for i, energy in enumerate(energies_values):
                # Compute true velocity and TOF
                v_true = c * np.sqrt(1 - (m_mu / energy) ** 2)  # Velocity in m/s
                tof_true = plane_positions / v_true  # True TOF for each plane
                tof_true_ns = tof_true * 1e9  # Convert to ns
                
                # Generate TOF values by applying Gaussian noise
                tof_sim = tof_true_ns + np.random.normal(scale=sigma_T, size=(m, num_samples))

                # Fit a straight line using least squares (vectorized)
                ATy = A.T @ tof_sim  # Precompute dot product
                coefficients = ATA_inv @ ATy  # Solve for coefficients
                v_sim = 1 / (coefficients[0] * 1e-9)  # Extract velocity directly from fit

                # Ensure numerical stability in sqrt()
                denom = np.maximum(1 - (v_sim / c) ** 2, epsilon)  # Always positive
                energy_sim = m_mu / np.sqrt(denom)  # Stable energy calculation

                # Compute residuals (real energy - simulated energy)
                residuals = np.abs(energy - energy_sim)
                rel_res = np.nanmean(residuals) / energy * 100  # Relative residuals in %

                # Store results
                E_mesh.append(energy / 1e9)  # Convert to GeV
                sigma_T_mesh.append(sigma_T)
                plane_mesh.append(m)
                d_mesh.append(d_total)
                rel_residuals.append(rel_res)
                
                # Update progress bar
                progress_bar.update(1)

# Close progress bar after loop completes
progress_bar.close()

#%%

# Convert lists to arrays for plotting
E_mesh = np.array(E_mesh)
sigma_T_mesh = np.array(sigma_T_mesh)
plane_mesh = np.array(plane_mesh)
d_mesh = np.array(d_mesh)
rel_residuals = np.array(rel_residuals)

np.save("E_mesh.npy", E_mesh)
np.save("sigma_T_mesh.npy", sigma_T_mesh)
np.save("plane_mesh.npy", plane_mesh)
np.save("d_mesh.npy", d_mesh)
np.save("rel_residuals.npy", rel_residuals)

#%%

E_mesh = np.load("E_mesh.npy")
sigma_T_mesh = np.load("sigma_T_mesh.npy")
plane_mesh = np.load("plane_mesh.npy")
d_mesh = np.load("d_mesh.npy")
rel_residuals = np.load("rel_residuals.npy")

rel_residuals = np.clip(rel_residuals, 0, 50)  # Clip residuals to a reasonable range

# Plot contour plots for all parameter relationships ------------------------

# Energy vs Sigma_T
plt.figure(figsize=(8, 6))
contour = plt.tricontourf(E_mesh, sigma_T_mesh, rel_residuals, levels=50, cmap="viridis_r", extend="both")
plt.colorbar(label="Mean Energy Residual (%)")
plt.xlabel("Muon Energy (GeV)")
plt.ylabel("Timing Resolution σ_T (ns)")
plt.title("Energy Residual vs Energy and Timing Resolution")
plt.savefig("1.png", format = "png")
plt.show()

# Energy vs Number of Planes
plt.figure(figsize=(8, 6))
contour = plt.tricontourf(E_mesh, plane_mesh, rel_residuals, levels=50, cmap="viridis_r", extend="both")
plt.colorbar(label="Mean Energy Residual (%)")
plt.xlabel("Muon Energy (GeV)")
plt.ylabel("Number of Planes")
plt.title("Energy Residual vs Energy and Number of Planes")
plt.savefig("2.png", format = "png")
plt.show()

# Sigma_T vs Number of Planes
plt.figure(figsize=(8, 6))
contour = plt.tricontourf(sigma_T_mesh, plane_mesh, rel_residuals, levels=50, cmap="viridis_r", extend="both")
plt.colorbar(label="Mean Energy Residual (%)")
plt.xlabel("Timing Resolution σ_T (ns)")
plt.ylabel("Number of Planes")
plt.title("Energy Residual vs Timing Resolution and Number of Planes")
plt.savefig("3.png", format = "png")
plt.show()

# Distance vs Number of Planes
plt.figure(figsize=(8, 6))
contour = plt.tricontourf(d_mesh, plane_mesh, rel_residuals, levels=50, cmap="viridis_r", extend="both")
plt.colorbar(label="Mean Energy Residual (%)")
plt.xlabel("Distance (m)")
plt.ylabel("Number of Planes")
plt.title("Energy Residual vs Detector Distance and Number of Planes")
plt.savefig("4.png", format = "png")
plt.show()


# %%
