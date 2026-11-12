"""Simulate Molière scattering and compare the angular distribution with the model."""

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.colors as mcolors

uniform_spectrum = False
degrees = True
read_layout_from_file = True
load_data = False
save_plots = True
show_plots = False

colormap_name = 'turbo'

# Constants
m_muon_MeV = 105.658  # Muon rest mass (MeV/c²)

if read_layout_from_file:
      # Read detector layout from CSV file
      df = pd.read_csv('rpc_layout.csv')
      L_in_mm = df['L_in_mm'].values
      X0_in_mm = df['X0_in_mm'].values
      L_over_X0 = np.sum( L_in_mm / X0_in_mm ) * 4 # By 4 becase it is made by 4 RPC planes

      print(f"Detector layout read from file: L/X0 = {L_over_X0}")
else:
      L_over_X0 = 0.249 * 4      # Total radiation length (L/X₀) for the detector
      print(f"Detector layout NOT from file: L/X0 = {L_over_X0}")

# Parameters
N_muons = 10000000       # Number of muons to simulate
E_min = 0.001           # Minimum muon energy (GeV)
E_max = 100          # Maximum muon energy (GeV)
E_min_plot = 0.5      # Minimum energy for plotting (GeV)
E_max_plot = 4      # Maximum energy for plotting (GeV)
theta_min_plot = 5 * ( np.pi/180 if degrees == False else 1)
theta_max_plot = 50 * ( np.pi/180 if degrees == False else 1)
n_cos_theta = 2      # Power of cos(theta) distribution
angle_limit_degrees = 5

if load_data:
      # Load data from file
      df = pd.read_csv('generated_data.csv')
      cos_thetas = df['cos_theta'].values
      energies_GeV = df['energy'].values
      print('Reloading data...')
else:
      # Generate random cos(theta) samples from cos^n(theta) distribution
      def generate_cos_theta_samples(N, n):
            u = np.random.uniform(0, 1, N)
            cos_theta_samples = u**(1 / (n + 1))
            return cos_theta_samples

      # Generate cos(theta) samples
      cos_theta_samples = generate_cos_theta_samples(N_muons, n_cos_theta)

      if uniform_spectrum:
            # Generate cosmic muon energies (uniform spectrum)
            energies_GeV = np.random.uniform(E_min, E_max, N_muons)
      else:
            # Define the energy spectrum function
            def energy_spectrum(E, cos_theta):
                  if E < 1:
                        # Make the spectrum nearly flat for E < 1 GeV
                        match_point = 0.14 * (1 / (1 + 1.1 * E * cos_theta / 115) + 0.054 / (1 + 1.1 * E * cos_theta / 850))
                        return match_point * E**-0.001
                  else:
                        # Use the original formula for E >= 1 GeV
                        return 0.14 * E**-2.7 * (1 / (1 + 1.1 * E * cos_theta / 115) + 0.054 / (1 + 1.1 * E * cos_theta / 850))

            # Rejection sampling for energy distribution
            def generate_energy_angle_distribution(N_samples, E_min, E_max, cos_theta_samples):
                  energies = []
                  cos_thetas = []

                  while len(energies) < N_samples:
                        # Randomly sample energy and cos(theta)
                        E = np.random.uniform(E_min, E_max)
                        cos_theta = cos_theta_samples[len(energies)]  # Use pre-sampled cos(theta)
                        r = np.random.uniform(0, 1)

                        # Rejection sampling condition
                        if r < energy_spectrum(E, cos_theta) / energy_spectrum(E_min, 1.0):
                              energies.append(E)
                              cos_thetas.append(cos_theta)

                  return np.array(energies), np.array(cos_thetas)

            # Generate energy and angle samples
            energies_GeV, cos_thetas = generate_energy_angle_distribution(N_muons, E_min, E_max, cos_theta_samples)

# Save to file the generated data
data = {'cos_theta': cos_thetas, 'energy': energies_GeV}
df = pd.DataFrame(data)
df.to_csv('generated_data.csv', index=False)

# Plot histogram
# plt.figure(figsize=(10, 6))
# plt.hist(np.arccos(cos_thetas) * 180/np.pi, bins='auto', density=False, alpha=0.5, color = 'green')
# plt.xlabel('Angular distribution (theta)', fontsize=12)
# plt.ylabel('Counts', fontsize=12)
# plt.title('Theta (º)', fontsize=14)
# plt.grid(True, alpha=0.3)
# plt.show()

# # Plot histogram
# plt.figure(figsize=(10, 6))
# plt.hist(energies_GeV, bins='auto', density=False, alpha=0.5, color = 'green')
# plt.xlabel('Energy spectrum (GeV)', fontsize=12)
# plt.ylabel('Counts', fontsize=12)
# plt.title('Energy (GeV)', fontsize=14)
# plt.grid(True, alpha=0.3)
# plt.show()

# Convert energies to MeV and calculate relativistic parameters
E_kin_MeV = energies_GeV * 1000  # GeV -> MeV
E_total_MeV = E_kin_MeV + m_muon_MeV
p_MeV = np.sqrt(E_total_MeV**2 - m_muon_MeV**2)  # Momentum (MeV/c)
beta = p_MeV / E_total_MeV  # Relativistic beta

# Molière scattering formula
sqrt_term = np.sqrt(L_over_X0)
log_term = np.log(L_over_X0)
theta_0 = (13.6 / (beta * p_MeV)) * sqrt_term * (1 + 0.038 * log_term)

# Filter out invalid values (if any)
# theta_0 = theta_0[~np.isnan(theta_0)]

# Filter values above 10º in theta_0 and so in E_kin_MeV
angle_limit = angle_limit_degrees * np.pi / 180
cond = theta_0 < angle_limit
theta_0 = theta_0[cond]
E_kin_MeV = E_kin_MeV[cond]

# For the latter plots
thetas = np.arccos(cos_thetas)
thetas = thetas[cond]

thetas_og = thetas * 180/np.pi
theta_dev_og = theta_0 * 180/np.pi
E_kin_GeV_og = E_kin_MeV / 1000

if degrees:
      # Convert scattering angle to degrees
      theta_0 = 180/np.pi*theta_0
      unit = 'º'
else:
      unit = 'rad'

# # Plot histogram
# plt.figure(figsize=(10, 6))
# plt.hist(theta_0, bins='auto', density=False, alpha=0.5)
# plt.xlabel(f'Scattering Angle Standard Deviation ({unit})', fontsize=12)
# plt.ylabel('Counts', fontsize=12)
# plt.title(f'Multiple Coulomb Scattering of Cosmic Muons ({unit})', fontsize=14)
# plt.grid(True, alpha=0.3)
# plt.show()


# ---------------------------------------------------------
# Theta using the Energy as colorbar
# ---------------------------------------------------------

# Define bins for the histogram
bins = np.histogram_bin_edges(theta_0, bins='auto')

# Compute digitized indices to map colors
indices = np.digitize(theta_0, bins) - 1
bin_centers = 0.5 * (bins[:-1] + bins[1:])

# Compute mean energy per bin
energy_means = [np.mean(E_kin_MeV[indices == i]) for i in range(len(bin_centers))]
energy_means = np.array(energy_means) / 1000

# Normalize energy values for colormap
norm = mcolors.Normalize(vmin=E_min_plot, vmax=E_max_plot)
cmap = plt.get_cmap(colormap_name)
colors = [cmap(norm(e)) for e in energy_means]

# Plot histogram with colors
fig, ax = plt.subplots(figsize=(10, 6))
for i in range(len(bin_centers)):
    ax.bar(bin_centers[i], np.sum(indices == i), width=(bins[i+1] - bins[i]), color=colors[i], alpha=0.8)

# Add colorbar
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])
cbar = plt.colorbar(sm, ax=ax)
cbar.set_label('Mean Muon Energy (GeV)')

# quant = np.quantile(theta_0, 0.95, interpolation='nearest')
# ax.axvline(quant, color='g', alpha = 0.5, linestyle='--', label=f'95% quantile ({quant:.2g} {unit})')
unc = 3 * (np.pi / 180 if degrees == False else 1) # 3 degrees in radians
ax.axvline(unc, color='g', alpha = 0.5, linestyle='--', label=f'Simulated uncertainty of the telescope ({unc:.2g} {unit})')

# Labels and title
ax.set_xlabel(f'Scattering Angle Standard Deviation ({unit})', fontsize=12)
ax.set_ylabel('Counts', fontsize=12)
ax.set_title(f'Multiple Coulomb Scattering of Cosmic Muons (angle)', fontsize=14)
# ax.set_xscale('log')
# ax.set_yscale('log')
ax.grid(True, alpha=0.3)
ax.legend()

plt.tight_layout()
if save_plots:
      plt.savefig('moliere_angle.png', format='png')
if show_plots:
      plt.show()
plt.close()


# ---------------------------------------------------------
# Theta using the Energy as colorbar
# ---------------------------------------------------------

E_kin_GeV = E_kin_MeV / 1000 # MeV -> GeV

cond = E_kin_GeV < 10
theta_0 = theta_0[cond]
E_kin_GeV = E_kin_GeV[cond]

if degrees:
      theta_0 = theta_0 * 180/np.pi
      unit = 'º'
else:
      unit = 'rad'


# Define bins for the histogram
bins = np.histogram_bin_edges(E_kin_GeV, bins='auto')

# Compute digitized indices to map colors
indices = np.digitize(E_kin_GeV, bins) - 1
bin_centers = 0.5 * (bins[:-1] + bins[1:])

# Compute mean theta per bin
theta_means = [np.mean(theta_0[indices == i]) for i in range(len(bin_centers))]
theta_means = np.array(theta_means)

# Normalize theta values for colormap
norm = mcolors.Normalize(vmin=theta_min_plot, vmax=theta_max_plot)
cmap = plt.get_cmap(colormap_name)
colors = [cmap(norm(theta)) for theta in theta_means]

# Plot histogram with colors
fig, ax = plt.subplots(figsize=(10, 6))
for i in range(len(bin_centers)):
    ax.bar(bin_centers[i], np.sum(indices == i), width=(bins[i+1] - bins[i]), color=colors[i], alpha=0.8)

# Add colorbar
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])
cbar = plt.colorbar(sm, ax=ax)
cbar.set_label(f'Mean Scattering Angle ({unit})')

# Labels and title
ax.set_xlabel('Muon Energy (GeV)', fontsize=12)
ax.set_ylabel('Counts', fontsize=12)
ax.set_title('Multiple Coulomb Scattering of Cosmic Muons (energy)', fontsize=14)
ax.grid(True, alpha=0.3)
ax.set_yscale('log')
# ax.legend()

plt.tight_layout()
if save_plots:
      plt.savefig('moliere_energy.png', format='png')
if show_plots:
      plt.show()
plt.close()


# ---------------------------------------------------------
# A banana plot
# ---------------------------------------------------------

energy = E_kin_GeV_og
thetas = thetas_og
theta_dev = theta_dev_og

cond = (energy < 4) & (theta_dev < 10)
energy = energy[cond]
thetas = thetas[cond]
theta_dev = theta_dev[cond]

energy_event = energy
angle_event = thetas - np.random.normal(thetas, theta_dev, len(thetas))

cond = (energy_event < 4) & (abs(angle_event) < 10)
energy_event = energy_event[cond]
angle_event = angle_event[cond]

# Plot histogram
plt.figure(figsize=(10, 6))
plt.hist2d(energy_event, angle_event, bins=300, density=False, cmap='turbo')
plt.xlabel('Energy spectrum (GeV)', fontsize=12)
plt.ylabel('Scattering Angle (º)', fontsize=12)
plt.title('Energy vs Scattering Angle', fontsize=14)
plt.grid(True, alpha=0.3)
plt.colorbar()
plt.tight_layout()
if save_plots:
      plt.savefig('moliere_banana_all.png', format='png')
if show_plots:
      plt.show()
plt.close()


# Vertical muons only
energy = E_kin_GeV_og
thetas = thetas_og
theta_dev = theta_dev_og

cond = (energy < 4) & (theta_dev < 10) & (thetas < 15)
energy = energy[cond]
thetas = thetas[cond]
theta_dev = theta_dev[cond]

energy_event = energy
angle_event = thetas - np.random.normal(thetas, theta_dev, len(thetas))

cond = (energy_event < 4) & (abs(angle_event) < 10)
energy_event = energy_event[cond]
angle_event = angle_event[cond]

# Plot histogram
plt.figure(figsize=(10, 6))
plt.hist2d(energy_event, angle_event, bins=300, density=False, cmap='turbo')
plt.xlabel('Energy spectrum (GeV)', fontsize=12)
plt.ylabel('Scattering Angle (º)', fontsize=12)
plt.title('Energy vs Scattering Angle (vertical muons only)', fontsize=14)
plt.grid(True, alpha=0.3)
plt.colorbar()
plt.tight_layout()
if save_plots:
      plt.savefig('moliere_banana_vertical.png', format='png')
if show_plots:
      plt.show()
plt.close()


# Oblique muons only
energy = E_kin_GeV_og
thetas = thetas_og
theta_dev = theta_dev_og

cond = (energy < 4) & (theta_dev < 10) & (thetas > 15) & (thetas < 90)
energy = energy[cond]
thetas = thetas[cond]
theta_dev = theta_dev[cond]

energy_event = energy
angle_event = thetas - np.random.normal(thetas, theta_dev, len(thetas))

cond = (energy_event < 4) & (abs(angle_event) < 10)
energy_event = energy_event[cond]
angle_event = angle_event[cond]

# Plot histogram
plt.figure(figsize=(10, 6))
plt.hist2d(energy_event, angle_event, bins=300, density=False, cmap='turbo')
plt.xlabel('Energy spectrum (GeV)', fontsize=12)
plt.ylabel('Scattering Angle (º)', fontsize=12)
plt.title('Energy vs Scattering Angle (oblique muons only)', fontsize=14)
plt.grid(True, alpha=0.3)
plt.colorbar()
plt.tight_layout()
if save_plots:
      plt.savefig('moliere_banana_oblique.png', format='png')
if show_plots:
      plt.show()
plt.close()


# # 0-15º muons only
# low = 0
# high = 15

# energy = E_kin_GeV_og
# thetas = thetas_og
# theta_dev = theta_dev_og

# cond = (energy < 4) & (theta_dev < 10) & (thetas > low) & (thetas < high)
# energy = energy[cond]
# thetas = thetas[cond]
# theta_dev = theta_dev[cond]

# energy_event = energy
# angle_event = np.random.normal(thetas, theta_dev, len(thetas))

# cond = (energy_event < 4) & (abs(angle_event) < 90)
# energy_event = energy_event[cond]
# angle_event = angle_event[cond]

# # Plot histogram
# plt.figure(figsize=(10, 6))
# plt.hist2d(energy_event, angle_event, bins=300, density=False, cmap='turbo')
# plt.xlabel('Energy spectrum (GeV)', fontsize=12)
# plt.ylabel('Scattering Angle (º)', fontsize=12)
# plt.title('Energy vs Scattering Angle (oblique muons only)', fontsize=14)
# plt.grid(True, alpha=0.3)
# plt.colorbar()
# plt.tight_layout()
# if save_plots:
#       plt.savefig(f'moliere_banana_oblique_{low}_{high}.png', format='png')
# if show_plots:
#       plt.show()
# plt.close()



# # 15-30º muons only
# low = 15
# high = 30

# energy = E_kin_GeV_og
# thetas = thetas_og
# theta_dev = theta_dev_og

# cond = (energy < 4) & (theta_dev < 10) & (thetas > low) & (thetas < high)
# energy = energy[cond]
# thetas = thetas[cond]
# theta_dev = theta_dev[cond]

# energy_event = energy
# angle_event = np.random.normal(thetas, theta_dev, len(thetas))

# cond = (energy_event < 4) & (abs(angle_event) < 90)
# energy_event = energy_event[cond]
# angle_event = angle_event[cond]

# # Plot histogram
# plt.figure(figsize=(10, 6))
# plt.hist2d(energy_event, angle_event, bins=300, density=False, cmap='turbo')
# plt.xlabel('Energy spectrum (GeV)', fontsize=12)
# plt.ylabel('Scattering Angle (º)', fontsize=12)
# plt.title('Energy vs Scattering Angle (oblique muons only)', fontsize=14)
# plt.grid(True, alpha=0.3)
# plt.colorbar()
# plt.tight_layout()
# if save_plots:
#       plt.savefig(f'moliere_banana_oblique_{low}_{high}.png', format='png')
# if show_plots:
#       plt.show()
# plt.close()



# # 30-45º muons only
# low = 30
# high = 45

# energy = E_kin_GeV_og
# thetas = thetas_og
# theta_dev = theta_dev_og

# cond = (energy < 4) & (theta_dev < 10) & (thetas > low) & (thetas < high)
# energy = energy[cond]
# thetas = thetas[cond]
# theta_dev = theta_dev[cond]

# energy_event = energy
# angle_event = np.random.normal(thetas, theta_dev, len(thetas))

# cond = (energy_event < 4) & (abs(angle_event) < 90)
# energy_event = energy_event[cond]
# angle_event = angle_event[cond]

# # Plot histogram
# plt.figure(figsize=(10, 6))
# plt.hist2d(energy_event, angle_event, bins=300, density=False, cmap='turbo')
# plt.xlabel('Energy spectrum (GeV)', fontsize=12)
# plt.ylabel('Scattering Angle (º)', fontsize=12)
# plt.title('Energy vs Scattering Angle (oblique muons only)', fontsize=14)
# plt.grid(True, alpha=0.3)
# plt.colorbar()
# plt.tight_layout()
# if save_plots:
#       plt.savefig(f'moliere_banana_oblique_{low}_{high}.png', format='png')
# if show_plots:
#       plt.show()
# plt.close()




# # 45-60º muons only
# low = 45
# high = 60

# energy = E_kin_GeV_og
# thetas = thetas_og
# theta_dev = theta_dev_og

# cond = (energy < 4) & (theta_dev < 10) & (thetas > low) & (thetas < high)
# energy = energy[cond]
# thetas = thetas[cond]
# theta_dev = theta_dev[cond]

# energy_event = energy
# angle_event = np.random.normal(thetas, theta_dev, len(thetas))

# cond = (energy_event < 4) & (abs(angle_event) < 90)
# energy_event = energy_event[cond]
# angle_event = angle_event[cond]

# # Plot histogram
# plt.figure(figsize=(10, 6))
# plt.hist2d(energy_event, angle_event, bins=300, density=False, cmap='turbo')
# plt.xlabel('Energy spectrum (GeV)', fontsize=12)
# plt.ylabel('Scattering Angle (º)', fontsize=12)
# plt.title('Energy vs Scattering Angle (oblique muons only)', fontsize=14)
# plt.grid(True, alpha=0.3)
# plt.colorbar()
# plt.tight_layout()
# if save_plots:
#       plt.savefig(f'moliere_banana_oblique_{low}_{high}.png', format='png')
# if show_plots:
#       plt.show()
# plt.close()


# Function to process and plot muons
# def plot_muons(low, high, energy, thetas, theta_dev, save_plots=False, show_plots=True):
#       """Filters muons in the given angle range, generates Gaussian angle deviations,
#       and plots energy vs scattering angle."""

#       energy_high = 5

#       cond = (energy < energy_high) & (theta_dev < 10) & (thetas > low) & (thetas < high)
#       energy_filtered = energy[cond]
#       thetas_filtered = thetas[cond]
#       theta_dev_filtered = theta_dev[cond]

#       energy_event = energy_filtered
#       angle_event = np.random.normal(thetas_filtered, theta_dev_filtered, len(thetas_filtered))

#       cond = (abs(angle_event) < 90)
#       energy_event = energy_event[cond]
#       angle_event = angle_event[cond]
#       # thetas_filtered = thetas_filtered[cond]
#       # theta_dev_filtered = theta_dev_filtered[cond]

#       # Plot histogram
#       plt.figure(figsize=(10, 6))
#       plt.hist2d(energy_event, angle_event, bins=300, density=False, cmap='turbo')
#       # plt.plot(energy_event, thetas_filtered, 'r.', markersize=1)
#       plt.xlabel('Energy spectrum (GeV)', fontsize=12)
#       plt.ylabel('Scattering Angle (º)', fontsize=12)
#       plt.title(f'Energy vs Scattering Angle ({low}º-{high}º muons only)', fontsize=14)
#       plt.grid(True, alpha=0.3)
#       plt.colorbar()
#       plt.tight_layout()
#       plt.xlim(0, energy_high)
#       plt.ylim(0, 65)

#       if save_plots:
#             plt.savefig(f'moliere_banana_oblique_{low}_{high}.png', format='png')
#       if show_plots:
#             plt.show()
#       plt.close()

# # Loop through angle ranges in 5º steps
# for low in range(5, 60, 5):
#       high = low + 1
#       plot_muons(low, high, E_kin_GeV_og, thetas_og, theta_dev_og, save_plots, show_plots)







# ---------------------------------------------------------
# The total banana plot
# ---------------------------------------------------------

# Define the angle filtering parameters
low = 3
step = 15
width = 1
max_angle = 90

# Initialize empty lists to accumulate filtered data
energy_events_all = []
angle_events_all = []

# Filter data for multiple angle ranges
for theta_min in range(low, max_angle, step):
    theta_max = theta_min + width

    cond = (E_kin_GeV_og < 5) & (theta_dev_og < 10) & (thetas_og > theta_min) & (thetas_og < theta_max)
    energy_filtered = E_kin_GeV_og[cond]
    thetas_filtered = thetas_og[cond]
    theta_dev_filtered = theta_dev_og[cond]

    energy_event = energy_filtered
    angle_event = np.random.normal(thetas_filtered, theta_dev_filtered, len(thetas_filtered))

    cond = (abs(angle_event) < 90)
    energy_event = energy_event[cond]
    angle_event = angle_event[cond]

    # Accumulate the filtered data
    energy_events_all.extend(energy_event)
    angle_events_all.extend(angle_event)

# Convert accumulated data to numpy arrays
energy_events_all = np.array(energy_events_all)
angle_events_all = np.array(angle_events_all)

# Plot all filtered data in a single histogram
plt.figure(figsize=(10, 6))
plt.hist2d(energy_events_all, angle_events_all, bins=250, density=False, cmap='turbo')
plt.xlabel('Energy spectrum (GeV)', fontsize=12)
plt.ylabel('Scattering Angle (º)', fontsize=12)
plt.title('Energy vs Scattering Angle (Filtered Muons)', fontsize=14)
plt.grid(True, alpha=0.3)
plt.colorbar()
plt.tight_layout()
plt.xlim(0, 5)
plt.ylim(0, 90)

if save_plots:
    plt.savefig('moliere_banana_oblique_combined.png', format='png')
if show_plots:
    plt.show()
plt.close()
