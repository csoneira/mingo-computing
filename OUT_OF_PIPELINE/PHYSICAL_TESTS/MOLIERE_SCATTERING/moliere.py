#%%

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.colors as mcolors
import sys

pdg_more_than_100GeV = False
reyna_parametrization = True

uniform_spectrum = False
degrees = True
read_layout_from_file = True
load_data = False
save_to_file = False
save_plots = True
show_plots = False
create_plots = True
article_format = True

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
N_muons = 100000       # Number of muons to simulate
E_min = 0.1           # Minimum muon energy (GeV). 0.001
E_max = 10          # Maximum muon energy (GeV). 100
E_min_plot = 0.1      # Minimum energy for plotting (GeV)
E_max_plot = 10      # Maximum energy for plotting (GeV)
theta_min_plot = 5 * ( np.pi/180 if degrees == False else 1)
theta_max_plot = 50 * ( np.pi/180 if degrees == False else 1)
n_cos_theta = 2      # Power of cos(theta) distribution
angle_limit_degrees = 40
      
if load_data:
      print("Loding data from file.")
      
      # Load data from file
      df = pd.read_csv('generated_data.csv')
      cos_thetas = df['cos_theta'].values
      energies_GeV = df['energy'].values
      print('Reloading data...')
else:
      if pdg_more_than_100GeV:
            print("PDG parametrization for > 100 GeV muons")
            
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
                              match_point = 0.14 * (1 / (1 + 1.1 * 1 * cos_theta / 115) + 0.054 / (1 + 1.1 * 1 * cos_theta / 850))
                              return match_point * E**-0.01
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
      
      if reyna_parametrization:
            print("Reyna parametrization for low energy.")
            
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
                  # Define the energy spectrum function using the Reyna (2006) parameterization
                  def energy_spectrum(E, cos_theta):
                        if E < 1:
                              E = 1
                        
                        # Momentum calculation from Energy value
                        p = np.sqrt(E**2 - ( m_muon_MeV / 1000)**2)
                        zeta = p * cos_theta
                        
                        # Vertical intensity Iv(zeta) (Reyna 2006 parameterization)
                        I_v = 0.00253 * zeta ** (-1 * (0.2455 + 1.288 * np.log10(zeta) - 0.2555 * (np.log10(zeta))**2 + 0.0209 * (np.log10(zeta))**3 ) )

                        # Full angular dependence
                        I_p_theta = cos_theta**3 * I_v

                        return I_p_theta

                  # Rejection sampling for energy distribution
                  # Generate energy and angle samples using the new energy spectrum
                  def generate_energy_angle_distribution(N_samples, E_min, E_max, cos_theta_samples):
                        energies = []
                        cos_thetas = []

                        while len(energies) < N_samples:
                              # Randomly sample energy and cos(theta)
                              E = np.random.uniform(E_min, E_max)
                              cos_theta = cos_theta_samples[len(energies)]  # Use pre-sampled cos(theta)
                              r = np.random.uniform(0, 1)

                              # Rejection sampling condition using the new energy spectrum
                              if r < energy_spectrum(E, cos_theta) / energy_spectrum(E_min, 1.0):
                                    energies.append(E)
                                    cos_thetas.append(cos_theta)

                        return np.array(energies), np.array(cos_thetas)


                  # Generate energy and angle samples
                  energies_GeV, cos_thetas = generate_energy_angle_distribution(N_muons, E_min, E_max, cos_theta_samples)
      else:
            print("No energy selected.")
            sys.exit(1)
            
# Save to file the generated data
if save_to_file:
      data = {'cos_theta': cos_thetas, 'energy': energies_GeV}
      df = pd.DataFrame(data)
      df.to_csv('generated_data.csv', index=False)
      print('Data saved to file.')

# Plot histogram
plt.figure(figsize=(10, 6))
plt.hist(np.arccos(cos_thetas) * 180/np.pi, bins='auto', density=False, alpha=0.5, color = 'green')
plt.xlabel('Angular distribution (theta)', fontsize=12)
plt.ylabel('Counts', fontsize=12)
plt.title('Theta (º)', fontsize=14)
plt.grid(True, alpha=0.3)
plt.tight_layout()
if save_plots:
      plt.savefig('muon_generated_angle.png', format='png')
if show_plots:
      plt.show()
plt.close()

# Convert energies to MeV and calculate relativistic parameters
E_kin_MeV = energies_GeV * 1000  # GeV -> MeV
E_total_MeV = E_kin_MeV + m_muon_MeV
p_MeV = np.sqrt(E_total_MeV**2 - m_muon_MeV**2)  # Momentum (MeV/c)
beta = p_MeV / E_total_MeV  # Relativistic beta

# Molière scattering formula
# Applying the cosine to make the path longer if the angles are more grazing
L_over_X0 = L_over_X0 / np.abs(cos_thetas)

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
if create_plots:
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

cond = E_kin_GeV < E_max_plot
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
if create_plots:
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

cond = (energy < E_max_plot) & (theta_dev < 10)
energy = energy[cond]
thetas = thetas[cond]
theta_dev = theta_dev[cond]

energy_event = energy
angle_event = thetas - np.random.normal(thetas, theta_dev, len(thetas))

cond = (energy_event < E_max_plot) & (abs(angle_event) < 10)
energy_event = energy_event[cond]
angle_event = angle_event[cond]

# Plot histogram
if create_plots:
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

cond = (energy < E_max_plot) & (theta_dev < 10) & (thetas < 15)
energy = energy[cond]
thetas = thetas[cond]
theta_dev = theta_dev[cond]

energy_event = energy
angle_event = thetas - np.random.normal(thetas, theta_dev, len(thetas))

cond = (energy_event < E_max_plot) & (abs(angle_event) < 10)
energy_event = energy_event[cond]
angle_event = angle_event[cond]

# Plot histogram
if create_plots:
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

cond = (energy < E_max_plot) & (theta_dev < 10) & (thetas > 15) & (thetas < 90)
energy = energy[cond]
thetas = thetas[cond]
theta_dev = theta_dev[cond]

energy_event = energy
angle_event = thetas - np.random.normal(thetas, theta_dev, len(thetas))

cond = (energy_event < E_max_plot) & (abs(angle_event) < 10)
energy_event = energy_event[cond]
angle_event = angle_event[cond]

# Plot histogram
if create_plots:
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


# ---------------------------------------------------------
# ---------------------------------------------------------
# The total banana plot
# ---------------------------------------------------------
# ---------------------------------------------------------

# Define the angle filtering parameters
low = 4.5
step = 15
width = 1
max_angle = 90

# Initialize empty lists to accumulate filtered data
energy_events_all = []
angle_events_all = []
center_angles = []  # To store center angles for annotation

# Filter data for multiple angle ranges
for theta_min in np.arange(low, max_angle, step):
    theta_max = theta_min + width

    center_angle = theta_min + width / 2  # Calculate center angle
    center_angles.append(center_angle)

    cond = (E_kin_GeV_og < E_max_plot) & (theta_dev_og < 30) & (thetas_og > theta_min) & (thetas_og < theta_max)
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
font_size = None
plt.figure(figsize=(6, 4))
h = plt.hist2d(energy_events_all, angle_events_all, bins=500, density=True, cmap='turbo')
plt.xlabel('Energy (GeV)', fontsize=font_size)
plt.ylabel('Scattering Angle (º)', fontsize=font_size)
if article_format == False:
      plt.title('Muon energy vs Scattering Angle (Filtered Muons)', fontsize=14)
plt.grid(True, alpha=0.3)
cbar = plt.colorbar(h[3])  # `h[3]` is the mappable from plt.hist2d
cbar.set_label('Normalized Counts', labelpad=15)  # Add the label with padding
# plt.tight_layout()
plt.xlim(min(energy_events_all), E_max_plot)
# plt.xscale('log')
plt.ylim(0, max([max(angle_events_all), 90]))

for center_angle in center_angles:
    plt.text(4.5, center_angle + width*3, f"{center_angle:.0f}º", color="white", fontsize=font_size, ha="right", va="center")

if save_plots:
    plt.savefig('moliere_banana_oblique_combined.png', dpi=300, format='png')
if show_plots:
    plt.show()
plt.close()


# ---------------------------------------------------------
# The total banana plot pt. 2
# ---------------------------------------------------------

# Initialize empty lists to accumulate filtered data
energy_events_all = []
angle_events_all = []
center_angles = []  # To store center angles for annotation

# Filter data for multiple angle ranges
for theta_min in np.arange(low, max_angle, step):
    theta_max = theta_min + width
    
    center_angle = theta_min + width / 2  # Calculate center angle
    center_angles.append(center_angle)
    
    cond = (E_kin_GeV_og < E_max_plot) & (theta_dev_og < 30) & (thetas_og > theta_min) & (thetas_og < theta_max)
    energy_filtered = E_kin_GeV_og[cond]
    thetas_filtered = thetas_og[cond]
    theta_dev_filtered = theta_dev_og[cond]

    energy_event = energy_filtered
    angle_event = np.random.normal(thetas_filtered, 0.5 * np.ones(len(thetas_filtered)), len(thetas_filtered))

    cond = (abs(angle_event) < 90)
    energy_event = energy_event[cond]
    angle_event = angle_event[cond]

    # Accumulate the filtered data
    energy_events_all.extend(energy_event)
    angle_events_all.extend(angle_event)

energy_events_all.append(0)  # x-axis point
angle_events_all.append(0)   # y-axis point

energy_events_all.append(0)  # x-axis point
angle_events_all.append(90)  # y-axis point

# Convert accumulated data to numpy arrays
energy_events_all = np.array(energy_events_all)
angle_events_all = np.array(angle_events_all)

# Plot all filtered data in a single histogram
font_size = None
plt.figure(figsize=(6, 4))
h = plt.hist2d(energy_events_all, angle_events_all, bins=500, density=True, cmap='turbo')
plt.xlabel('Energy (GeV)', fontsize=font_size)
plt.ylabel('Scattering Angle (º)', fontsize=font_size)
if article_format == False:
      plt.title('Muon energy vs Scattering Angle (Filtered Muons)', fontsize=14)
plt.grid(True, alpha=0.3)
cbar = plt.colorbar(h[3])  # `h[3]` is the mappable from plt.hist2d
cbar.set_label('Normalized Counts', labelpad=15)  # Add the label with padding
# plt.tight_layout()
plt.xlim(min(energy_events_all), E_max_plot)
# plt.xscale('log')
plt.ylim(0, max([max(angle_events_all), 90]))

for center_angle in center_angles:
    plt.text(4.5, center_angle + width*3, f"{center_angle:.0f}º", color="white", fontsize=font_size, ha="right", va="center")

if save_plots:
    plt.savefig('moliere_banana_oblique_combined_in.png', dpi=300, format='png')
if show_plots:
    plt.show()
plt.close()



# %%

# ---------------------------------------------------------------------
# Together ------------------------------------------------------------
# ---------------------------------------------------------------------

# Define the angle filtering parameters
low = 4.5
step = 15
width = 1
max_angle = 90

e_right_lim = E_max_plot

# Initialize empty lists to accumulate filtered data
energy_events_all_1 = []
angle_events_all_1 = []
center_angles_1 = []  # To store center angles for annotation

energy_events_all_2 = []
angle_events_all_2 = []
center_angles_2 = []  # To store center angles for annotation

# Filter data for multiple angle ranges for the first plot
for theta_min in np.arange(low, max_angle, step):
    theta_max = theta_min + width
    center_angle = theta_min + width / 2  # Calculate center angle
    center_angles_1.append(center_angle)

    cond = (E_kin_GeV_og < e_right_lim) & (theta_dev_og < 30) & (thetas_og > theta_min) & (thetas_og < theta_max)
    energy_filtered = E_kin_GeV_og[cond]
    thetas_filtered = thetas_og[cond]
    theta_dev_filtered = theta_dev_og[cond]

    energy_event = energy_filtered
    angle_event = np.random.normal(thetas_filtered, theta_dev_filtered, len(thetas_filtered))

    cond = (abs(angle_event) < 90)
    energy_event = energy_event[cond]
    angle_event = angle_event[cond]

    # Accumulate the filtered data
    energy_events_all_1.extend(energy_event)
    angle_events_all_1.extend(angle_event)

# Filter data for multiple angle ranges for the second plot
for theta_min in np.arange(low, max_angle, step):
    theta_max = theta_min + width
    center_angle = theta_min + width / 2  # Calculate center angle
    center_angles_2.append(center_angle)

    cond = (E_kin_GeV_og < e_right_lim) & (theta_dev_og < 30) & (thetas_og > theta_min) & (thetas_og < theta_max)
    energy_filtered = E_kin_GeV_og[cond]
    thetas_filtered = thetas_og[cond]

    energy_event = energy_filtered
    angle_event = np.random.normal(thetas_filtered, 0.5 * np.ones(len(thetas_filtered)), len(thetas_filtered))

    cond = (abs(angle_event) < 90)
    energy_event = energy_event[cond]
    angle_event = angle_event[cond]

    # Accumulate the filtered data
    energy_events_all_2.extend(energy_event)
    angle_events_all_2.extend(angle_event)
    
energy_events_all_2.append(0)  # x-axis point
angle_events_all_2.append(0)   # y-axis point

energy_events_all_2.append(0)  # x-axis point
angle_events_all_2.append(90)  # y-axis point

# Convert accumulated data to numpy arrays
energy_events_all_1 = np.array(energy_events_all_1)
angle_events_all_1 = np.array(angle_events_all_1)

energy_events_all_2 = np.array(energy_events_all_2)
angle_events_all_2 = np.array(angle_events_all_2)


fig, axes = plt.subplots(1, 2, figsize=(7, 3), sharey=True)

# Plot first histogram
h1 = axes[0].hist2d(energy_events_all_2, angle_events_all_2, bins=500, density=True, cmap='turbo')
axes[0].set_xlabel('$\mu$ energy (GeV)')
axes[0].set_ylabel('$\mu$ angle (º)')
axes[0].grid(True, alpha=0.3)
axes[0].set_xlim(min(energy_events_all_1), e_right_lim)
axes[0].set_ylim(0, max([max(angle_events_all_1), 90]))

# Plot second histogram
h2 = axes[1].hist2d(energy_events_all_1, angle_events_all_1, bins=500, density=True, cmap='turbo')
axes[1].set_xlabel('$\mu$ energy (GeV)')
axes[1].grid(True, alpha=0.3)
axes[1].set_xlim(min(energy_events_all_2), e_right_lim)
axes[1].set_ylim(0, max([max(angle_events_all_2), 90]))

# Add titles if not in article format
if not article_format:
    axes[0].set_title('Incident Muon Angle')
    axes[1].set_title('Scattered Muon Angle')

# Set center angles as y-axis ticks and add grid lines
axes[0].set_yticks(center_angles_1)
axes[1].set_yticks(center_angles_2)

axes[0].yaxis.grid(True, linestyle='--', alpha=0.5)  # Dashed grid lines
axes[1].yaxis.grid(True, linestyle='--', alpha=0.5)


# Add a common colorbar
# cbar_ax = fig.add_axes([0.92, 0.15, 0.02, 0.7])  # Position for colorbar
# fig.colorbar(h1[3], cax=cbar_ax, label='Normalized Counts')

# plt.tight_layout(rect=[0, 0, 0.9, 1])  # Adjust layout to fit colorbar
plt.tight_layout()  # Adjust layout to fit colorbar

save_plots = True
if save_plots:
    plt.savefig('0_moliere_in_out_total.png', dpi=300, format='png')
if show_plots:
    plt.show()
plt.close()

# %%



fig, axes = plt.subplots(2, 1, figsize=(7, 3), sharex=True)  # Transposed layout

# Plot first histogram
h1 = axes[0].hist2d(angle_events_all_2, energy_events_all_2, bins=500, density=True, cmap='turbo')
axes[0].set_ylabel('$\mu$ energy (GeV)')

axes[0].grid(True, alpha=0.3)
axes[0].set_ylim(min(energy_events_all_1), e_right_lim)
axes[0].set_xlim(0, max([max(angle_events_all_1), 90]))

# Plot second histogram
h2 = axes[1].hist2d(angle_events_all_1, energy_events_all_1, bins=500, density=True, cmap='turbo')
axes[1].set_ylabel('$\mu$ energy (GeV)')
axes[1].set_xlabel('$\mu$ angle (º)')
axes[1].grid(True, alpha=0.3)
axes[1].set_ylim(min(energy_events_all_2), e_right_lim)
axes[1].set_xlim(0, max([max(angle_events_all_2), 90]))

# Add titles if not in article format
if not article_format:
    axes[0].set_title('Incident Muon Angle')
    axes[1].set_title('Scattered Muon Angle')

# Set center angles as x-axis ticks and add grid lines
axes[0].set_xticks(center_angles_1)
axes[1].set_xticks(center_angles_2)

axes[0].xaxis.grid(True, linestyle='--', alpha=0.5)  # Dashed grid lines
axes[1].xaxis.grid(True, linestyle='--', alpha=0.5)

# Adjust layout
plt.tight_layout()

save_plots = True
if save_plots:
    plt.savefig('0_transposed_moliere_in_out_total.png', dpi=300, format='png')
if show_plots:
    plt.show()
plt.close()

# %%
