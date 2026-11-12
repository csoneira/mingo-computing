"""Analyze waiting-time measurements from the historical test."""

#%%

import numpy as np
import scipy.io
import scipy.sparse
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.stats import poisson
from scipy.stats import nbinom
from tqdm import tqdm
from scipy.stats import expon

# Set the maximum number of particles for waiting time calculations
max_particles = 3  # Change this to any number of particles you want

# Load the .mat file
filename = 'mi0324311141342.mat'
data = scipy.io.loadmat(filename)

# List of 'T' and 'Q' variables of interest for signal selection
T_vars = ['T1_F', 'T1_B', 'T2_F', 'T2_B', 'T3_F', 'T3_B', 'T4_F', 'T4_B']
Q_vars = ['Q1_F', 'Q1_B', 'Q2_F', 'Q2_B', 'Q3_F', 'Q3_B', 'Q4_F', 'Q4_B']

event_times = []  # Initialize a list to store one event time per row

# Convert sparse matrices to dense arrays once, outside the loop
T_front_matrices = [data[T_vars[idx * 2]].toarray() if scipy.sparse.issparse(data[T_vars[idx * 2]]) else data[T_vars[idx * 2]] for idx in range(4)]
T_back_matrices = [data[T_vars[idx * 2 + 1]].toarray() if scipy.sparse.issparse(data[T_vars[idx * 2 + 1]]) else data[T_vars[idx * 2 + 1]] for idx in range(4)]
Q_front_matrices = [data[Q_vars[idx * 2]].toarray() if scipy.sparse.issparse(data[Q_vars[idx * 2]]) else data[Q_vars[idx * 2]] for idx in range(4)]
Q_back_matrices = [data[Q_vars[idx * 2 + 1]].toarray() if scipy.sparse.issparse(data[Q_vars[idx * 2 + 1]]) else data[Q_vars[idx * 2 + 1]] for idx in range(4)]

event_times = []  # Initialize a list to store one event time per row

# Loop through each row (event)
for i in tqdm(range(T_front_matrices[0].shape[0]), desc="Processing events"):
    all_high_values = []  # Collect high values across all strips and channels for this row

    # Loop through each strip in the detector
    for strip_idx in range(4):
        # Get timing and charge data for the current strip's front and back channels
        T_front = T_front_matrices[strip_idx]
        T_back = T_back_matrices[strip_idx]
        Q_front = Q_front_matrices[strip_idx]
        Q_back = Q_back_matrices[strip_idx]

        # Mask to check if there's a valid signal in both front and back, directly applying high-value filter
        mask_front = (Q_front[i, :] != 0) & (T_front[i, :] > 1e4)
        mask_back = (Q_back[i, :] != 0) & (T_back[i, :] > 1e4)

        # Only consider rows where there's exactly one non-zero charge in both front and back
        if np.sum(mask_front & mask_back) == 1:
            # Collect all valid high timing values
            high_values_front = T_front[i, mask_front]
            high_values_back = T_back[i, mask_back]
            
            # Append high values to all_high_values
            all_high_values.extend(high_values_front)
            all_high_values.extend(high_values_back)

    # Store the average of high values or NaN if no high values were found
    event_times.append(np.mean(all_high_values) if all_high_values else np.nan)

# Verify lengths match
print("Length of T1_F data:", T_front_matrices[0].shape[0])
print("Length of event_times:", len(event_times))

#%%

# Show some rows of event_times
print("First 10 event times:", event_times[:20])
print("Last 10 event times:", event_times[-20:])

# Plot event times according to the index
plt.figure(figsize=(10, 5))
plt.plot(event_times, '.-')
plt.title('Event Times')
plt.xlabel('Event Index')
plt.ylabel('Event Time (µs)')
plt.grid(True)
plt.tight_layout()
plt.savefig('event_times.png', format='png')
plt.show()

# Count and remove NaNs from event_times
nan_count = np.isnan(event_times).sum()
print(f"Number of NaNs in event_times: {nan_count}")

# Remove NaNs from event_times and corresponding indices
valid_indices = ~np.isnan(event_times)
event_times = np.array(event_times)[valid_indices]
x = np.arange(len(event_times))

# Fit a line to the event times
slope, intercept = np.polyfit(x, event_times, 1)
fitted_line = slope * x + intercept

# Print the fit parameters
print(f"Slope: {slope}")
print(f"Intercept: {intercept}")

# Calculate residuals
residuals = event_times - fitted_line

# Define a threshold for residuals (e.g., 3 standard deviations)
threshold = 5 * np.std(residuals)

# Filter out events outside the threshold
filtered_event_times = np.array(event_times)[np.abs(residuals) <= threshold]

# Plot the filtered event times
plt.figure(figsize=(10, 5))
plt.plot(filtered_event_times, '.-', label='Filtered Event Times')
plt.plot(x, fitted_line, 'r--', label='Fitted Line')
plt.title('Filtered Event Times with Fitted Line')
plt.xlabel('Event Index')
plt.ylabel('Event Time (µs)')
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig('filtered_event_times_with_fitted_line.png', format='png')
plt.show()

# Plot the relative residuals
relative_residuals = residuals / event_times

plt.figure(figsize=(10, 5))
plt.plot(x, relative_residuals, '.-', label='Relative Residuals')
plt.fill_between(x, relative_residuals, where=np.abs(residuals) > threshold, color='red', alpha=0.2, label='Removed Residuals')
plt.axhline(threshold / np.mean(event_times), color='red', linestyle='--', alpha=0.7, label='Upper Threshold')
plt.axhline(-threshold / np.mean(event_times), color='red', linestyle='--', alpha=0.7, label='Lower Threshold')
plt.title('Relative Residuals of Event Times')
plt.xlabel('Event Index')
plt.ylabel('Relative Residual')
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig('relative_residuals.png', format='png')
plt.show()

#%%

# Sort event times
event_times = np.sort(event_times)

# Initialize lists to store waiting times, labels, and counts for each particle count
waiting_times_list = []
labels = []
bulk_counts = []

# Calculate waiting times for the next `k` particles where `k` ranges from 1 to max_particles
for k in range(1, max_particles + 1):
    waiting_times = (event_times[k:] - event_times[:-k]) / 1000  # Convert to microseconds
    waiting_times_list.append(waiting_times)
    labels.append(f'{k} adjacent')

    bulk_count = np.sum(waiting_times > 0.5)
    bulk_counts.append(bulk_count)


# Define bins for waiting time histograms (exponential-like distribution)
waiting_time_bins = np.logspace(np.log10(np.min(waiting_times_list[0][waiting_times_list[0] > 0])), 
                                np.log10(np.max(waiting_times_list[0])), 50)


# waiting_time_bins = np.linspace(np.min(waiting_times_list[0][waiting_times_list[0] > 0]), 
#                                 np.max(waiting_times_list[0]), 50)


# Plot all waiting time histograms ---------------------------------------------------------------------------
plt.figure(figsize=(10, 7))

n = len(waiting_times_list)  # Number of datasets/plots
# Generate n colors from the 'turbo' colormap
colors = plt.cm.turbo(np.linspace(0, 1, n + 2)[1:-1])
for i, waiting_times in enumerate(waiting_times_list):
    waiting_counts, _ = np.histogram(waiting_times, bins=waiting_time_bins)
    waiting_counts = waiting_counts / np.diff(waiting_time_bins)  # Normalize counts by bin width
    plt.plot(waiting_time_bins[:-1], waiting_counts, '.-', color=colors[i], label=labels[i])

# Print summary of waiting times
for i, (waiting_times, label) in enumerate(zip(waiting_times_list, labels)):
      print(f"Summary for {label}:")
      print(f"  Mean: {np.mean(waiting_times):.2f} µs")
      print(f"  Median: {np.median(waiting_times):.2f} µs")
      print(f"  Standard Deviation: {np.std(waiting_times):.2f} µs")
      print(f"  Minimum: {np.min(waiting_times):.2f} µs")
      print(f"  Maximum: {np.max(waiting_times):.2f} µs")
      print(f"  Bulk Count (> 0.5 µs): {bulk_counts[i]}")
      print()

# Add a horizontal line at 10 counts per bin for reference
# plt.plot(waiting_time_bins[:-1], 10 / waiting_time_bins[:-1], color='black', alpha=0.5, linestyle='--', linewidth=1, label='10 Counts/Bin')
# plt.plot(waiting_time_bins[:-1], 1 / waiting_time_bins[:-1], color='green', alpha=0.5, linestyle='--', linewidth=1, label='1 Count/Bin')

# Add the blue semitransparent region using axvspan
# plt.axvspan(0, 0.5, color='blue', alpha=0.3, label="Muon Bulk Sim. Bound.")

# Add the vertical dashed line at 0.5 microseconds
# plt.axvline(0.5, color='blue', linestyle='--', alpha=0.7)
# plt.text(0.5 + 0.5*0.2, plt.ylim()[1]*0.9, '0.5 µs', color='blue', ha='left', alpha=0.7)

# uncertainty = 3*10**(-4)
# plt.axvline(uncertainty, color='red', linestyle='--', alpha=0.7)
# plt.text(uncertainty + uncertainty*0.2, plt.ylim()[1]*0.9, 'Time uncertainty\nthreshold (300 ps)', color='red', ha='left', alpha=0.7)

dead_time = 3*10**(0)
plt.axvline(dead_time, color='red', linestyle='--', alpha=0.7)
plt.text(dead_time + dead_time*0.2, plt.ylim()[1]*0.9, 'Dead time\nthreshold (3 µs)', color='red', ha='left', alpha=0.7)

# coincidence_window = 2*10**(-1)
# plt.axvline(coincidence_window, color='green', linestyle='--', alpha=0.7)
# plt.text(coincidence_window + coincidence_window*0.2, plt.ylim()[1]*0.1, 'Coincidence window\nthreshold (200 ns)', color='green', ha='left', alpha=0.7)


# Set log scale and labels
plt.xscale('log')
plt.yscale('log')
# plt.ylim([1e-4, None])
plt.title(f'Waiting Time Histograms for 1 to {max_particles} adjacent events')
plt.xlabel('Waiting Time (µs)')
plt.ylabel('Frequency Density (Counts / Bin Width)')
# plt.xlim([1e-4, 0.1])
plt.legend()

plt.tight_layout()
plt.savefig('waiting.png', format='png')
plt.show()


#%%


#%%
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.stats import poisson, expon
from tqdm import tqdm

# Convert event times to seconds
event_times_s = event_times / 1e9

# Calculate the number of events in each second
time_bins = np.arange(np.floor(event_times_s[0]), np.ceil(event_times_s[-1]) + 1)
event_counts, _ = np.histogram(event_times_s, bins=time_bins)

# Plot the event counts per second as bars
plt.figure(figsize=(10, 5))
plt.bar(time_bins[:-1], event_counts, width=1, align='edge', edgecolor='black', label='Event Counts per Second')
plt.title('Event Counts per Second')
plt.xlabel('Time (s)')
plt.ylabel('Event Count')
plt.grid(True)
plt.tight_layout()
plt.show()

# Fit a Poisson distribution to the event counts per second
mean_event_count = np.mean(event_counts)
poisson_dist = poisson(mu=mean_event_count)

# Plot the Poisson fit
x = np.arange(0, np.max(event_counts) + 1)
poisson_pmf = poisson_dist.pmf(x)

plt.figure(figsize=(10, 5))
plt.hist(event_counts, bins=np.arange(np.max(event_counts) + 2) - 0.5, density=True, alpha=0.7, edgecolor='black', label='Event Counts Data')
plt.plot(x, poisson_pmf, 'r--', linewidth=2, label=f'Poisson Fit (μ={mean_event_count:.2f})')
plt.title('Poisson Fit to Event Counts per Second')
plt.xlabel('Event Count')
plt.ylabel('Probability')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

# Print the mean event count
print(f"Mean event count per second: {mean_event_count:.2f}")

# Set initial guess for exponential fit using the Poisson rate
initial_guess_lambda = 1.0 / mean_event_count  # Initial guess for lambda based on Poisson fit

# Fit exponential distribution to the waiting times and plot the data along with the fit
for i, waiting_times in enumerate(waiting_times_list):
    # Define the exponential function
    def exponential_func(x, lambd):
        return lambd * np.exp(-lambd * x)
    
    # Calculate histogram data for waiting times
    waiting_counts, waiting_time_bins = np.histogram(waiting_times, bins=50, density=True)
    bin_centers = (waiting_time_bins[:-1] + waiting_time_bins[1:]) / 2
    
    # Fit exponential function to the waiting times using the initial Poisson guess
    params, _ = curve_fit(exponential_func, bin_centers, waiting_counts, p0=[initial_guess_lambda])
    lambd = params[0]
    scale = 1 / lambd  # Mean waiting time in microseconds

    # Print the fit parameters
    print(f"Exponential fit for {labels[i]}:")
    print(f"  Rate (lambda): {lambd:.2e} events/µs")
    print(f"  Mean waiting time: {scale:.2e} µs")
    print()

    # Plot the waiting times histogram as bars
    plt.figure(figsize=(10, 5))
    plt.hist(waiting_times, bins=50, density=True, alpha=0.6, edgecolor='black', label=f'{labels[i]} Data')
    
    # Plot the exponential fit as a line
    x_fit = np.linspace(np.min(waiting_times), np.max(waiting_times), 100)
    y_fit = exponential_func(x_fit, lambd)
    plt.plot(x_fit, y_fit, 'r--', linewidth=2, label=f'Exponential Fit (λ={lambd:.2e})')

    # Set log scale and labels
    plt.xscale('log')
    plt.yscale('log')
    plt.title(f'Waiting Time Distribution and Exponential Fit for {labels[i]}')
    plt.xlabel('Waiting Time (µs)')
    plt.ylabel('Frequency Density')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()
