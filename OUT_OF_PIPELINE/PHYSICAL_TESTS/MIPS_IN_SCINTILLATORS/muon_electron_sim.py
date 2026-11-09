#%%

import numpy as np

# Constants
AVOGADRO = 6.022e23  # Avogadro's number [1/mol]
ELECTRON_MASS = 0.511  # Electron mass [MeV/c^2]
PROTON_MASS = 938.272  # Proton mass [MeV/c^2]
ELEMENTARY_CHARGE = 1.60218e-19  # Elementary charge [C]
LIGHT_YIELD = 20000  # Photons produced per MeV deposited
BC400_DENSITY = 1.023  # BC400 density [g/cm^3]
SCINT_WIDTH = 1.0  # Scintillator width [cm], changeable parameter

# Material properties (BC400 is primarily C9H10)
ATOMIC_MASS_C = 12.011  # g/mol
ATOMIC_MASS_H = 1.008  # g/mol
NUM_C_ATOMS = 9
NUM_H_ATOMS = 10
MOLECULAR_MASS = (NUM_C_ATOMS * ATOMIC_MASS_C + NUM_H_ATOMS * ATOMIC_MASS_H)  # g/mol
EFFECTIVE_Z = (NUM_C_ATOMS * 6 + NUM_H_ATOMS * 1) / (NUM_C_ATOMS + NUM_H_ATOMS)  # Approx. effective Z

# Bethe-Bloch constants
MEAN_EXCITATION_ENERGY = 68.7e-6  # Mean excitation energy for plastic [MeV]
K_CONST = 0.307075  # Bethe constant [MeV·cm^2/g]


def bethe_bloch(energy, particle_mass, charge=1, particle_type='electron'):
    """
    Calculate energy loss (dE/dx) using the Bethe-Bloch formula.
    For muons, uses a fixed stopping power of 2.2 MeV·cm²/g.
    :param energy: Kinetic energy of the particle [MeV]
    :param particle_mass: Mass of the particle [MeV/c^2]
    :param charge: Charge of the particle [integer, multiples of e]
    :param particle_type: Type of particle ('electron' or 'muon')
    :return: Energy loss per unit length [MeV/cm]
    """
    if particle_type == 'muon':
        # Fixed stopping power for muons
        stopping_power_muon = 2.2  # MeV·cm²/g
        dE_dx = stopping_power_muon * BC400_DENSITY  # Convert to MeV/cm using density
        return dE_dx
    
    elif particle_type == 'electron':
        # Energy loss for electrons using Bethe-Bloch formula with corrections
        gamma = (energy + particle_mass) / particle_mass
        beta = np.sqrt(1 - 1 / gamma**2)
        W_max = energy / 2  # Approximation for maximum energy transfer in collisions
        term1 = (K_CONST * BC400_DENSITY * charge**2 * EFFECTIVE_Z) / (MOLECULAR_MASS * beta**2)
        term2 = np.log(W_max / MEAN_EXCITATION_ENERGY**2) - beta**2
        dE_dx = term1 * term2
        
        # Handle high-energy Bremsstrahlung losses (for simplicity, add linear scaling)
        critical_energy = 100  # Approximate critical energy [MeV]
        if energy > critical_energy:
            radiative_loss = (energy - critical_energy) * BC400_DENSITY * 0.002  # Simplified radiative loss
            dE_dx += radiative_loss
        
        return max(dE_dx, 0)  # Ensure non-negative values
    
    else:
        raise ValueError("Particle type must be 'electron' or 'muon'.")



def calculate_photons(energy, particle_mass, scint_width, charge=1):
    """
    Calculate the total number of photons produced in the scintillator.
    :param energy: Kinetic energy of the particle [MeV]
    :param particle_mass: Mass of the particle [MeV/c^2]
    :param scint_width: Thickness of the scintillator [cm]
    :param charge: Charge of the particle [integer, multiples of e]
    :return: Total photons produced
    """
    dE_dx = bethe_bloch(energy, particle_mass, charge)
    energy_deposited = dE_dx * scint_width  # Total energy deposited [MeV]
    photons = energy_deposited * LIGHT_YIELD
    return photons



# Example calculations
muon_energy = 4000  # Muon energy [MeV]
electron_energy = 40  # Electron energy [MeV]

# Calculate photons for muons
photons_muon = calculate_photons(muon_energy, PROTON_MASS, SCINT_WIDTH)

# Calculate photons for electrons
photons_electron = calculate_photons(electron_energy, ELECTRON_MASS, SCINT_WIDTH)

print(f"Photons produced by a {muon_energy} MeV muon: {photons_muon:.2f}")
print(f"Photons produced by a {electron_energy} MeV electron: {photons_electron:.2f}")

# %%


import matplotlib.pyplot as plt

# Define a range of scintillator widths in cm
scintillator_widths = np.arange(0.1, 10, 0.5)  # From 0.1 cm to 5.0 cm in steps of 0.5 cm

# Initialize lists to store results
muon_photons = []
electron_photons = []

# Loop through widths and calculate photons
for width in scintillator_widths:
    muon_photons.append(calculate_photons(muon_energy, PROTON_MASS, width))
    electron_photons.append(calculate_photons(electron_energy, ELECTRON_MASS, width))

# Plotting
plt.figure(figsize=(8, 6))
plt.plot(scintillator_widths, muon_photons, label='Muons (1000 MeV)', marker='o')
plt.plot(scintillator_widths, electron_photons, label='Electrons (10 MeV)', marker='s')

# Adding labels and legend
plt.title('Photons Produced vs Scintillator Width')
plt.xlabel('Scintillator Width (cm)')
plt.ylabel('Photons Produced')
plt.legend()
plt.grid(True)
plt.show()

#%%


import matplotlib.pyplot as plt

# Define a range of scintillator widths in cm
scintillator_widths = np.arange(0.1, 200, 0.5)  # From 0.1 cm to 5.0 cm in steps of 0.5 cm

# Initialize lists to store results
muon_photons = []
electron_photons = []

# Loop through widths and calculate photons
for width in scintillator_widths:
    muon_photons.append(calculate_photons(muon_energy, PROTON_MASS, width))
    electron_photons.append(calculate_photons(electron_energy, ELECTRON_MASS, width))

# Plotting
plt.figure(figsize=(8, 6))
muon_photons_derivative = np.gradient(muon_photons, scintillator_widths)
electron_photons_derivative = np.gradient(electron_photons, scintillator_widths)

plt.plot(scintillator_widths, muon_photons_derivative, label='Muons (1000 MeV) Derivative', marker='o')
plt.plot(scintillator_widths, electron_photons_derivative, label='Electrons (10 MeV) Derivative', marker='s')

# Adding labels and legend
plt.title('Photons Produced vs Scintillator Width')
plt.xlabel('Scintillator Width (cm)')
plt.ylabel('Photons Produced')
plt.legend()
plt.grid(True)
plt.show()



#%%



#%%