#%%

import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from tqdm import tqdm

beta_max = 0 # -4
beta_min = -0.02 # -8

start = 1
end = 52
step = 10
time_windows = list(range(start, end, step))  # Weeks

# Create a suffix with the time windows start, end and step to add to the saving files
time_windows_suffix = f"{start}_{end}_{step}"

print(f"Time windows suffix: {time_windows_suffix}")

# load_filename = f'filtered_data_{time_windows_suffix}.csv'
load_filename = 'filtered_data_1_52_1.csv'

reload_data = False
linear_fit_condition = True
regression_plots = False  # Set to True to display individual regression plots for debugging

# Define the file paths
# pressure_file_path = 'pressure.csv'
# rate_file_path = 'rate.csv'
pressure_file_path = 'pressure_OULU.csv'
rate_file_path = 'rate_OULU.csv'

#%%

if reload_data:
    # Load the filtered data from the CSV file
    loaded_filtered_data = pd.read_csv(load_filename)

    # Convert numeric days back to datetime
    loaded_filtered_data['days_filtered'] = loaded_filtered_data['days_filtered'].map(
        lambda x: pd.Timestamp.fromordinal(int(x)))

    # Extract the loaded data into separate variables
    days_filtered = loaded_filtered_data['days_filtered'].map(pd.Timestamp.toordinal)
    ranges_filtered = loaded_filtered_data['ranges_filtered'].to_numpy()
    betas_filtered = loaded_filtered_data['betas_filtered'].to_numpy()
    beta_uncertainties_filtered = loaded_filtered_data['beta_uncertainties_filtered'].to_numpy()
    r_squared_values_filtered = loaded_filtered_data['r_squared_values_filtered'].to_numpy()
else:
    
    # Read and process the pressure data
    pressure_df = pd.read_csv(pressure_file_path, sep=';', skiprows=23, names=["start_date_time", "RPRESS"], comment='#')
    pressure_df['start_date_time'] = pressure_df['start_date_time'].str.strip()
    pressure_df['RPRESS'] = pd.to_numeric(pressure_df['RPRESS'], errors='coerce')
    pressure_df['start_date_time'] = pd.to_datetime(pressure_df['start_date_time'], errors='coerce')

    # Read and process the rate data
    rate_df = pd.read_csv(rate_file_path, sep=';', skiprows=23, names=["start_date_time", "RUNCORR"], comment='#')
    rate_df['start_date_time'] = rate_df['start_date_time'].str.strip()
    rate_df['RUNCORR'] = pd.to_numeric(rate_df['RUNCORR'], errors='coerce')
    rate_df['start_date_time'] = pd.to_datetime(rate_df['start_date_time'], errors='coerce')

    merged_df = pd.merge(pressure_df, rate_df, on='start_date_time', how='inner') # Merge the two dataframes on start_date_time
    merged_df = merged_df.dropna() # Drop rows with NaN values

    # Plot the time series of both columns
    plt.figure(figsize=(12, 6))

    plt.subplot(2, 1, 1)
    plt.plot(merged_df['start_date_time'], merged_df['RPRESS'], label='RPRESS', color='b')
    plt.xlabel('Time')
    plt.ylabel('RPRESS')
    plt.title('Time Series of RPRESS')
    plt.legend()

    plt.subplot(2, 1, 2)
    plt.plot(merged_df['start_date_time'], merged_df['RUNCORR'], label='RUNCORR', color='r')
    plt.xlabel('Time')
    plt.ylabel('RUNCORR')
    plt.title('Time Series of RUNCORR')
    plt.legend()

    plt.tight_layout()
    plt.show()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12))

    # First subplot: Time Series of RUNCORR
    scatter1 = ax1.scatter(merged_df['start_date_time'], merged_df['RUNCORR'], c=merged_df['start_date_time'].map(pd.Timestamp.toordinal), cmap='turbo', alpha=0.6, s=1)
    ax1.set_xlabel('Time')
    ax1.set_ylabel('RUNCORR')
    ax1.set_title('Time Series of RUNCORR')
    fig.colorbar(scatter1, ax=ax1, label='Date (Ordinal)')
    ax1.legend()

    # Second subplot: Rate vs Pressure
    scatter2 = ax2.scatter(merged_df['RPRESS'], merged_df['RUNCORR'], c=merged_df['start_date_time'].map(pd.Timestamp.toordinal), cmap='turbo', alpha=0.6, s=0.1)
    ax2.set_xlabel('RPRESS')
    ax2.set_ylabel('RUNCORR')
    ax2.set_title('Rate vs Pressure')
    fig.colorbar(scatter2, ax=ax2, label='Date (Ordinal)')
    ax2.grid(True)

    plt.tight_layout()
    plt.show()

    # Calculate the correlation of RPRESS and RUNCORR for each start_date_time
    correlation = merged_df[['RPRESS', 'RUNCORR']].corr().iloc[0, 1]
    print(f"Correlation between RPRESS and RUNCORR: {correlation:.3f}")

    # Define time windows in weeks and corresponding time deltas
    time_deltas = [pd.Timedelta(weeks=w) for w in time_windows]

    # Ensure the merged_df DataFrame is defined
    unique_dates = merged_df['start_date_time'].dt.date.unique()

    if linear_fit_condition:
        def fit_func(x, a, b):
            return a * x + b
    else:
        def fit_func(x, a, b):
            return a * np.exp(-b * x)
    
    # Lists to store results
    days = []
    ranges = []
    betas = []
    beta_uncertainties = []
    r_squared_values = []

    # Iterate over each unique date with a progress bar
    for current_date in tqdm(unique_dates, desc="Processing Dates"):
        current_date = pd.Timestamp(current_date)
        
        for delta in time_deltas:
            # Filter data within the time window around the current date
            start_date = current_date - delta
            end_date = current_date + delta
            window_data = merged_df[(merged_df['start_date_time'] >= start_date) & (merged_df['start_date_time'] <= end_date)]
            
            # Calculate and plot fit if sufficient data is available
            if len(window_data) > 2:
                # Calculate mean values
                rate_mean = window_data['RUNCORR'].mean()
                pressure_mean = window_data['RPRESS'].mean()
                
                # Calculate normalized rate and pressure deviations
                rate_norm = window_data['RUNCORR'] / rate_mean
                pressure_norm = (window_data['RPRESS'] - pressure_mean)
                rate_norm = np.log(rate_norm)
                
                # rate_norm = (window_data['RUNCORR'] - rate_mean)
                # pressure_norm = (window_data['RPRESS'] - pressure_mean)
                
                # Calculate uncertainties for each point
                # Assuming uncertainties are proportional to the square root of the counts
                rate_uncertainties = np.sqrt(window_data['RUNCORR']) / rate_mean
                
                # Perform weighted linear regression using curve_fit
                try:
                    popt, pcov = curve_fit(
                        fit_func, 
                        pressure_norm,
                        rate_norm,
                        sigma=rate_uncertainties,
                        absolute_sigma=True
                    )
                    slope, intercept = popt
                    # Extract uncertainty in the slope (standard error)
                    stderr = np.sqrt(np.diag(pcov))[0]
                    
                    # Calculate R²
                    residuals = rate_norm - fit_func(pressure_norm, *popt)
                    ss_res = np.sum(residuals**2)
                    ss_tot = np.sum((rate_norm - np.mean(rate_norm))**2)
                    r_squared = 1 - (ss_res / ss_tot)
                    
                    # Store results
                    days.append(current_date)
                    ranges.append(delta.days)
                    betas.append(slope)
                    beta_uncertainties.append(stderr)
                    r_squared_values.append(r_squared)
                    
                    # Print R² for debugging
                    if regression_plots:
                        print(f"R² for date {current_date} and range {delta.days} days: {r_squared:.3f}")
                    
                    # Generate regression plot for debugging
                    if regression_plots:
                        fit_line = fit_func(pressure_norm, *popt)
                        plt.figure(figsize=(8, 6))
                        plt.errorbar(
                            pressure_norm, rate_norm, 
                            yerr=rate_uncertainties, fmt='o', 
                            label='Data', color='blue', alpha=0.6
                        )
                        plt.plot(pressure_norm, fit_line, color='red', label=f'Fit (Beta={slope:.3f} ± {stderr:.3f})')
                        plt.title(f"Linear Fit for Date: {current_date.date()} | Range: {delta.days} days")
                        plt.xlabel("Normalized Pressure Deviation")
                        plt.ylabel("Normalized Rate Deviation")
                        plt.legend()
                        plt.grid()
                        plt.tight_layout()
                        plt.show()
                except Exception as e:
                    print(f"Fit failed for date {current_date} and range {delta.days} days: {e}")

    print("Data processing complete.")

    # Convert lists to arrays for 3D plotting
    days_numeric = pd.to_datetime(days).map(pd.Timestamp.toordinal)
    ranges_array = np.array(ranges)
    betas_array = np.array(betas)
    beta_uncertainties_array = np.array(beta_uncertainties)
    r_squared_values_array = np.array(r_squared_values)

    # Filter outliers in beta and beta uncertainties
    filtered_indices = (betas_array >= beta_min) & (betas_array <= beta_max)
    days_filtered = days_numeric[filtered_indices]
    ranges_filtered = ranges_array[filtered_indices]
    betas_filtered = betas_array[filtered_indices]
    beta_uncertainties_filtered = beta_uncertainties_array[filtered_indices]
    r_squared_values_filtered = r_squared_values_array[filtered_indices]
    
    # Save filtered vectors to a CSV file
    filtered_data = pd.DataFrame({
        'days_filtered': days_filtered,
        'ranges_filtered': ranges_filtered,
        'betas_filtered': betas_filtered,
        'beta_uncertainties_filtered': beta_uncertainties_filtered,
        'r_squared_values_filtered': r_squared_values_filtered
    })
    filtered_data.to_csv(f'filtered_data_{time_windows_suffix}.csv', index=False)

print('Ready to plot')

#%%

# Convert numeric days back to datetime
dates_filtered = [datetime.fromordinal(int(d)) for d in days_filtered]
ordinal_dates_filtered = [d.toordinal() for d in dates_filtered]  # Convert to ordinal for plotting

# Calculate mean and standard deviation of beta values for each unique time range
unique_ranges = np.unique(ranges_filtered)
mean_betas = []
std_betas = []

for r in unique_ranges:
    range_betas = betas_filtered[ranges_filtered == r]
    mean_betas.append(np.mean(range_betas))
    std_betas.append(np.std(range_betas))

# Create plots for Beta
fig = plt.figure(figsize=(24, 6))

# 3D scatter plot
ax1 = fig.add_subplot(131, projection='3d')
scatter = ax1.scatter(ordinal_dates_filtered, ranges_filtered, betas_filtered, c=betas_filtered, cmap='viridis', marker='o')
ax1.set_xlabel("Date")
ax1.set_ylabel("Data Range (days)")
ax1.set_zlabel("Pressure Coefficient (beta)")
ax1.set_title("3D Scatter Plot of Beta")
fig.colorbar(scatter, ax=ax1, pad=0.1, label='Beta')
ax1.set_xticks(ordinal_dates_filtered[::len(ordinal_dates_filtered)//5])  # Adjust tick frequency
ax1.set_xticklabels([d.strftime('%Y-%m-%d') for d in dates_filtered[::len(dates_filtered)//5]], rotation=45)

# Z vs. X (Beta vs. Date)
ax2 = fig.add_subplot(132)
ax2.scatter(dates_filtered, betas_filtered, c='b', alpha=0.6)
ax2.set_xlabel("Date")
ax2.set_ylabel("Pressure Coefficient (beta)")
ax2.set_title("Beta vs. Date")
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
ax2.tick_params(axis='x', rotation=45)

# Z vs. Y (Beta vs. Data Range with error bars)
ax3 = fig.add_subplot(133)
ax3.errorbar(unique_ranges, mean_betas, yerr=std_betas, fmt='o', color='r', ecolor='black', capsize=5, label='Mean ± Std Dev')
ax3.set_xlabel("Data Range (days)")
ax3.set_ylabel("Pressure Coefficient (beta)")
ax3.set_title("Beta vs. Data Range (Mean ± Std Dev)")
ax3.legend()

plt.tight_layout()
plt.show()

# Create plots for Beta Uncertainty
fig = plt.figure(figsize=(24, 6))

# 3D scatter plot
ax1 = fig.add_subplot(131, projection='3d')
scatter = ax1.scatter(ordinal_dates_filtered, ranges_filtered, beta_uncertainties_filtered, c=beta_uncertainties_filtered, cmap='plasma', marker='o')
ax1.set_xlabel("Date")
ax1.set_ylabel("Data Range (days)")
ax1.set_zlabel("Uncertainty of Beta")
ax1.set_title("3D Scatter Plot of Beta Uncertainty")
fig.colorbar(scatter, ax=ax1, pad=0.1, label='Uncertainty')
ax1.set_xticks(ordinal_dates_filtered[::len(ordinal_dates_filtered)//5])  # Adjust tick frequency
ax1.set_xticklabels([d.strftime('%Y-%m-%d') for d in dates_filtered[::len(dates_filtered)//5]], rotation=45)

# Z vs. X (Uncertainty vs. Date)
ax2 = fig.add_subplot(132)
ax2.scatter(dates_filtered, beta_uncertainties_filtered, c='b', alpha=0.6)
ax2.set_xlabel("Date")
ax2.set_ylabel("Uncertainty of Beta")
ax2.set_title("Uncertainty vs. Date")
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
ax2.tick_params(axis='x', rotation=45)

# Z vs. Y (Uncertainty vs. Data Range with error bars)
mean_uncertainties = []
std_uncertainties = []

for r in unique_ranges:
    range_uncertainties = beta_uncertainties_filtered[ranges_filtered == r]
    mean_uncertainties.append(np.mean(range_uncertainties))
    std_uncertainties.append(np.std(range_uncertainties))

ax3 = fig.add_subplot(133)
ax3.errorbar(unique_ranges, mean_uncertainties, yerr=std_uncertainties, fmt='o', color='r', ecolor='black', capsize=5, label='Mean ± Std Dev')
ax3.set_xlabel("Data Range (days)")
ax3.set_ylabel("Uncertainty of Beta")
ax3.set_title("Uncertainty vs. Data Range (Mean ± Std Dev)")
ax3.legend()

plt.tight_layout()
plt.show()


# Create plots for R² values
fig = plt.figure(figsize=(24, 6))

# 3D scatter plot
ax1 = fig.add_subplot(131, projection='3d')
scatter = ax1.scatter(ordinal_dates_filtered, ranges_filtered, r_squared_values_filtered, c=r_squared_values_filtered, cmap='plasma', marker='o')
ax1.set_xlabel("Date")
ax1.set_ylabel("Data Range (days)")
ax1.set_zlabel("R² Value")
ax1.set_title("3D Scatter Plot of R² Values")
fig.colorbar(scatter, ax=ax1, pad=0.1, label='R² Value')
ax1.set_xticks(ordinal_dates_filtered[::len(ordinal_dates_filtered)//5])  # Adjust tick frequency
ax1.set_xticklabels([d.strftime('%Y-%m-%d') for d in dates_filtered[::len(dates_filtered)//5]], rotation=45)

# Z vs. X (R² vs. Date)
ax2 = fig.add_subplot(132)
ax2.scatter(dates_filtered, r_squared_values_filtered, c='b', alpha=0.6)
ax2.set_xlabel("Date")
ax2.set_ylabel("R² Value")
ax2.set_title("R² vs. Date")
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
ax2.tick_params(axis='x', rotation=45)

# Z vs. Y (R² vs. Data Range with error bars)
mean_r_squared = []
std_r_squared = []

for r in unique_ranges:
    range_r_squared = r_squared_values_filtered[ranges_filtered == r]
    mean_r_squared.append(np.mean(range_r_squared))
    std_r_squared.append(np.std(range_r_squared))

ax3 = fig.add_subplot(133)
ax3.errorbar(unique_ranges, mean_r_squared, yerr=std_r_squared, fmt='o', color='r', ecolor='black', capsize=5, label='Mean ± Std Dev')
ax3.set_xlabel("Data Range (days)")
ax3.set_ylabel("R² Value")
ax3.set_title("R² vs. Data Range (Mean ± Std Dev)")
ax3.legend()

plt.tight_layout()
plt.show()

#%%

# Create 2D grids for plotting
X, Y = np.meshgrid(np.unique(days_filtered), np.unique(ranges_filtered))

# Initialize the result arrays
Z_beta = np.full(X.shape, np.nan, dtype=float)
Z_uncertainty = np.full(X.shape, np.nan, dtype=float)
Z_r_squared = np.full(X.shape, np.nan, dtype=float)

# Vectorized computation using numpy indexing
day_indices = np.searchsorted(np.unique(days_filtered), days_filtered)
range_indices = np.searchsorted(np.unique(ranges_filtered), ranges_filtered)

# Create a 2D histogram-like array to store values for each combination
beta_accumulator = np.zeros(X.shape)
uncertainty_accumulator = np.zeros(X.shape)
r_squared_accumulator = np.zeros(X.shape)
count_accumulator = np.zeros(X.shape)

# Populate the accumulators
for d, r, b, u, r2 in zip(day_indices, range_indices, betas_filtered, beta_uncertainties_filtered, r_squared_values_filtered):
    beta_accumulator[r, d] += b
    uncertainty_accumulator[r, d] += u
    r_squared_accumulator[r, d] += r2
    count_accumulator[r, d] += 1

# Avoid division by zero and calculate means
valid_mask = count_accumulator > 0
Z_beta[valid_mask] = beta_accumulator[valid_mask] / count_accumulator[valid_mask]
Z_uncertainty[valid_mask] = uncertainty_accumulator[valid_mask] / count_accumulator[valid_mask]
Z_r_squared[valid_mask] = r_squared_accumulator[valid_mask] / count_accumulator[valid_mask]

# # Plotting the Beta values, Beta Uncertainty, and R² contours in the same plot using subfigures
# fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 5))

# # Plotting the Beta values contour
# contour1 = ax1.contourf(X, Y, Z_beta, levels=20, cmap="viridis")
# fig.colorbar(contour1, ax=ax1, label="Beta Value")
# ax1.set_xlabel("Date (Ordinal)")
# ax1.set_ylabel("Range (days)")
# ax1.set_title("Contour Plot of Beta Values")

# # Plotting the Beta Uncertainty contour
# contour2 = ax2.contourf(X, Y, Z_uncertainty, levels=20, cmap="plasma")
# fig.colorbar(contour2, ax=ax2, label="Beta Uncertainty")
# ax2.set_xlabel("Date (Ordinal)")
# ax2.set_ylabel("Range (days)")
# ax2.set_title("Contour Plot of Beta Uncertainties")

# # Plotting the R² contour
# contour3 = ax3.contourf(X, Y, Z_r_squared, levels=20, cmap="inferno")
# fig.colorbar(contour3, ax=ax3, label="R² Value")
# ax3.set_xlabel("Date (Ordinal)")
# ax3.set_ylabel("Range (days)")
# ax3.set_title("Contour Plot of R² Values")

# # Adding iso Z lines
# iso_lines = ax3.contour(X, Y, Z_r_squared, levels=5, colors='black', linewidths=0.5)
# ax3.clabel(iso_lines, inline=True, fontsize=8)

# plt.tight_layout()
# plt.show()



#%%

# # Create 2D grids for plotting
# X, Y = np.meshgrid(np.unique(days_filtered), np.unique(ranges_filtered))
# Z_beta = np.zeros_like(X, dtype=float)
# Z_uncertainty = np.zeros_like(X, dtype=float)
# Z_r_squared = np.zeros_like(X, dtype=float)

# # Map data onto the grid for Beta and R²
# unique_days = np.unique(days_filtered)
# unique_ranges = np.unique(ranges_filtered)

# for i, day in enumerate(tqdm(unique_days, desc="Processing Days")):
#     for j, range_val in enumerate(tqdm(unique_ranges, desc="Processing Ranges", leave=False)):
#         mask = (days_filtered == day) & (ranges_filtered == range_val)
#         if np.any(mask):
#             Z_beta[j, i] = np.mean(betas_filtered[mask])
#             Z_uncertainty[j, i] = np.mean(beta_uncertainties_filtered[mask])
#             Z_r_squared[j, i] = np.mean(r_squared_values_filtered[mask])

# # Plotting the Beta values, Beta Uncertainty, and R² contours in the same plot using subfigures
# fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 5))

# # Plotting the Beta values contour
# contour1 = ax1.contourf(X, Y, Z_beta, levels=20, cmap="viridis")
# fig.colorbar(contour1, ax=ax1, label="Beta Value")
# ax1.set_xlabel("Date (Ordinal)")
# ax1.set_ylabel("Range (days)")
# ax1.set_title("Contour Plot of Beta Values")

# # Plotting the Beta Uncertainty contour
# contour2 = ax2.contourf(X, Y, Z_uncertainty, levels=20, cmap="plasma")
# fig.colorbar(contour2, ax=ax2, label="Beta Uncertainty")
# ax2.set_xlabel("Date (Ordinal)")
# ax2.set_ylabel("Range (days)")
# ax2.set_title("Contour Plot of Beta Uncertainties")

# # Plotting the R² contour
# contour3 = ax3.contourf(X, Y, Z_r_squared, levels=20, cmap="inferno")
# fig.colorbar(contour3, ax=ax3, label="R² Value")
# ax3.set_xlabel("Date (Ordinal)")
# ax3.set_ylabel("Range (days)")
# ax3.set_title("Contour Plot of R² Values")

# # Adding iso Z lines
# iso_lines = ax3.contour(X, Y, Z_r_squared, levels=5, colors='black', linewidths=0.5)
# ax3.clabel(iso_lines, inline=True, fontsize=8)

# plt.tight_layout()
# plt.show()


#%%
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# Clip the data for Beta values
Z_beta_clipped = np.clip(Z_beta, -0.0085, -0.0055)

# Plotting the Beta values contour
contour1 = ax1.contourf(X, Y, Z_beta_clipped, levels=100, cmap="viridis")
fig.colorbar(contour1, ax=ax1, label="Beta Value")
ax1.set_xlabel("Date (Ordinal)")
ax1.set_ylabel("Range (days)")
ax1.set_title("Contour Plot of Beta Values")

# Adding iso Z lines
beta_levels = np.linspace(-0.0076 - 0.0005, -0.0072 + 0.0005, 3)
iso_lines = ax1.contour(X, Y, Z_beta_clipped, levels=beta_levels, colors='black', linewidths=0.5)
ax2.clabel(iso_lines, inline=True, fontsize=8)

# Clip the data for R² values
Z_r_squared_clipped = np.clip(Z_r_squared, 0.7, 1)

# Plotting the R² contour
contour2 = ax2.contourf(X, Y, Z_r_squared_clipped, levels=100, cmap="inferno")
fig.colorbar(contour2, ax=ax2, label="R² Value")
ax2.set_xlabel("Date (Ordinal)")
ax2.set_ylabel("Range (days)")
ax2.set_title("Contour Plot of R² Values")

# Adding iso Z lines
iso_lines = ax2.contour(X, Y, Z_r_squared_clipped, levels=[0.9, 0.95, 0.99], colors='black', linewidths=0.5)
ax2.clabel(iso_lines, inline=True, fontsize=8)

plt.title("Barometric factor (exp. fit) and R² Contour Plots\nfor the Oulu dataset")
plt.tight_layout()
plt.show()

#%%

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# Clip the data for Beta values
Z_beta_clipped = np.clip(Z_beta, -0.0085, -0.0055)

# Plotting the Beta values contour
contour1 = ax1.contourf(X, Y, Z_beta_clipped, levels=100, cmap="viridis")
fig.colorbar(contour1, ax=ax1, label="Beta Value")
ax1.set_xlabel("Date (Ordinal)")
ax1.set_ylabel("Range (days)")
ax1.set_title("Contour Plot of Beta Values")

# Clip the data for R² values
Z_r_squared_clipped = np.clip(Z_r_squared, 0.7, 1)

# Plotting the R² contour
contour2 = ax2.contourf(X, Y, Z_r_squared_clipped, levels=100, cmap="inferno")
fig.colorbar(contour2, ax=ax2, label="R² Value")
ax2.set_xlabel("Date (Ordinal)")
ax2.set_ylabel("Range (days)")
ax2.set_title("Contour Plot of R² Values")

# Adding iso Z lines
beta_levels = np.linspace(-0.0076 - 0.0005, -0.0072 + 0.0005, 3)
iso_lines = ax1.contour(X, Y, Z_r_squared_clipped, levels=[0.9, 0.95, 0.99], colors='black', linewidths=0.5)

ax2.clabel(iso_lines, inline=True, fontsize=8)
iso_lines = ax2.contour(X, Y, Z_r_squared_clipped, levels=[0.9, 0.95, 0.99], colors='black', linewidths=0.5)
ax2.clabel(iso_lines, inline=True, fontsize=8)

plt.title("Barometric factor (exp. fit) and R² Contour Plots\nfor the Oulu dataset")
plt.tight_layout()
plt.show()

#%%



def extract_daily_beta_for_exact_r2(data, r2_values=[0.9, 0.95, 0.99], min_time_window=60):
    """
    Extracts beta values for specific exact R² values for every day, considering only time windows >= min_time_window.

    Parameters:
    - data: pd.DataFrame with columns ['days_filtered', 'ranges_filtered', 'betas_filtered', 'r_squared_values_filtered'].
    - r2_values: List of exact R² values to find the corresponding beta values.
    - min_time_window: Minimum range (in days) to consider.

    Returns:
    - result: Dictionary with R² values as keys and DataFrames (dates, beta values) as values.
    """
    result = {}

    for r2_target in r2_values:
        # Filter data to exclude small time windows
        filtered_data = data[data['ranges_filtered'] >= min_time_window]

        # Initialize storage for daily beta values
        daily_betas = []

        # Get the range of days
        all_days = np.arange(filtered_data['days_filtered'].min(), filtered_data['days_filtered'].max() + 1)

        for day in tqdm(all_days, desc=f"Processing R² = {r2_target}"):
            # Extract data for the current day
            day_data = filtered_data[filtered_data['days_filtered'] == day]

            if not day_data.empty:
                # Find the row where R² is closest to the target value
                best_match_idx = (day_data['r_squared_values_filtered'] - r2_target).abs().idxmin()
                best_match = day_data.loc[best_match_idx]

                # Append the beta value and day
                daily_betas.append({'day': day, 'beta': best_match['betas_filtered']})

        # Store results for this R² target
        result[r2_target] = pd.DataFrame(daily_betas)
    
    return result

# Define R² values to extract
r2_values_to_extract = [0.9, 0.95, 0.99]

# Extract daily beta values for exact R²
results = extract_daily_beta_for_exact_r2(filtered_data, r2_values=r2_values_to_extract, min_time_window=30)


#%%

def plot_daily_beta_for_r2(results):
    """
    Plots daily beta values for each R² target value.

    Parameters:
    - results: Dictionary with R² values as keys and DataFrames (days, betas) as values.
    """
    plt.figure(figsize=(10, 6))
    for r2_target, df in results.items():
        plt.scatter(df['day'], df['beta'], marker='o', label=f'R² = {r2_target}', s=0.1)
    plt.title("Beta Values for Different R² Targets")
    plt.xlabel("Date (Ordinal)")
    plt.ylabel("Beta Value")
    plt.grid(True)
    legend = plt.legend()
    for handle in legend.legendHandles:
        handle.set_sizes([30])  # Adjusted marker size for legend
    plt.tight_layout()
    plt.show()

# Plot the results
plot_daily_beta_for_r2(results)

#%%


from scipy.ndimage import gaussian_filter1d

def plot_daily_beta_for_r2(results, sigma):
    """
    Plots daily beta values for each R² target value with smoothed y vectors.

    Parameters:
    - results: Dictionary with R² values as keys and DataFrames (days, betas) as values.
    - sigma: Standard deviation for Gaussian kernel used in smoothing.
    """
    plt.figure(figsize=(10, 6))
    for r2_target, df in results.items():
        smoothed_beta = gaussian_filter1d(df['beta'], sigma=sigma)
        plt.scatter(df['day'], smoothed_beta, label=f'R² = {r2_target}', s = 0.1)
    plt.title("Smoothed Beta Values for Different R² Targets")
    plt.xlabel("Date (Ordinal)")
    plt.ylabel("Beta Value")
    plt.grid(True)
    legend = plt.legend()
    for handle in legend.legendHandles:
        handle.set_linewidth(2.5)  # Adjusted line width for legend
    plt.tight_layout()
    plt.show()

# Plot the results with smoothing
plot_daily_beta_for_r2(results, sigma = 30)

#%%


from scipy.ndimage import gaussian_filter

sigma_x = 30  # Smoothing for X-axis --> Date center
sigma_y = 1  # Smoothing for Y-axis --> Date range
sigma = (sigma_y, sigma_x)  # Note: First dimension is rows (Y), second is columns (X)

# Smooth the data with different sigmas for each dimension
Z_beta_smoothed = gaussian_filter(Z_beta, sigma=sigma)
Z_r_squared_smoothed = gaussian_filter(Z_r_squared, sigma=sigma)

# Clip the smoothed data
Z_beta_clipped = np.clip(Z_beta_smoothed, -0.0085, -0.0055)
Z_r_squared_clipped = np.clip(Z_r_squared_smoothed, 0.7, 1)

# Create the figure and axes
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# Plotting the Beta values contour
contour1 = ax1.contourf(X, Y, Z_beta_clipped, levels=100, cmap="viridis")
fig.colorbar(contour1, ax=ax1, label="Beta Value")
ax1.set_xlabel("Date (Ordinal)")
ax1.set_ylabel("Range (days)")
ax1.set_title("Contour Plot of Beta Values")

# Plotting the R² contour
contour2 = ax2.contourf(X, Y, Z_r_squared_clipped, levels=100, cmap="inferno")
fig.colorbar(contour2, ax=ax2, label="R² Value")
ax2.set_xlabel("Date (Ordinal)")
ax2.set_ylabel("Range (days)")
ax2.set_title("Contour Plot of R² Values")

# Adding iso Z lines
iso_lines = ax1.contour(X, Y, Z_r_squared_clipped, levels=[0.9, 0.95, 0.99], colors='black', linewidths=0.5)
ax1.clabel(iso_lines, inline=True, fontsize=8)

iso_lines = ax2.contour(X, Y, Z_r_squared_clipped, levels=[0.9, 0.95, 0.99], colors='black', linewidths=0.5)
ax2.clabel(iso_lines, inline=True, fontsize=8)

plt.tight_layout()
plt.show()


#%%


from scipy.ndimage import gaussian_filter
from tqdm import tqdm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def smooth_data_and_extract_beta(X, Y, Z_r_squared, Z_beta, r2_values=[0.9, 0.95, 0.99], sigma=(2, 1), min_time_window=60):
    """
    Smooths the R² and Beta datasets, then extracts Beta values for specific exact R² values.

    Parameters:
    - X, Y: Meshgrid arrays representing the independent variables (e.g., Date, Range).
    - Z_r_squared, Z_beta: 2D arrays representing R² and Beta values.
    - r2_values: List of target R² values.
    - sigma: Tuple for Gaussian smoothing (sigma_y, sigma_x).
    - min_time_window: Minimum range (in days) to consider.

    Returns:
    - result: Dictionary with R² values as keys and DataFrames (days, beta values) as values.
    """
    # Smooth the R² and Beta datasets
    Z_r_squared_smoothed = gaussian_filter(Z_r_squared, sigma=sigma)
    Z_beta_smoothed = gaussian_filter(Z_beta, sigma=sigma)
    
    # Initialize results storage
    result = {}
    
    for r2_target in r2_values:
        daily_betas = []

        # Iterate over each day in X
        for i, day in enumerate(X[0]):  # X[0] contains the day values
            # Ensure time_window condition is met
            valid_indices = Y[:, i] >= min_time_window  # Check valid time windows
            if not np.any(valid_indices):
                continue
            
            # Find the closest R² value to the target for this day
            r_squared_column = Z_r_squared_smoothed[:, i][valid_indices]
            beta_column = Z_beta_smoothed[:, i][valid_indices]
            closest_idx = np.argmin(np.abs(r_squared_column - r2_target))
            
            # Extract the corresponding Beta value
            beta_value = beta_column[closest_idx]
            daily_betas.append({'day': day, 'beta': beta_value})

        # Store results for this R² target
        result[r2_target] = pd.DataFrame(daily_betas)
    
    return result


def plot_daily_beta_for_smoothed_r2(results):
    """
    Plots smoothed Beta values for each R² target value.

    Parameters:
    - results: Dictionary with R² values as keys and DataFrames (days, betas) as values.
    """
    plt.figure(figsize=(10, 6))
    for r2_target, df in results.items():
        plt.plot(df['day'], df['beta'], label=f'R² = {r2_target}', lw=2)
    plt.title("Smoothed Beta Values for Different R² Targets")
    plt.xlabel("Date (Ordinal)")
    plt.ylabel("Beta Value")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()


# Define smoothing parameters and target R² values
sigma = (30, 1)  # Smoothing in Y (time_window) and X (days)
r2_values_to_extract = [0.9, 0.95, 0.99]
min_time_window = 60

# Smooth data and extract Beta values for exact R² targets
results = smooth_data_and_extract_beta(X, Y, Z_r_squared, Z_beta, r2_values=r2_values_to_extract, sigma=sigma, min_time_window=min_time_window)

# Plot the results
plot_daily_beta_for_smoothed_r2(results)



#%%


import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import datetime as dt

# Convert ordinal dates to datetime format (YYYY-MM)
unique_dates = np.unique(days_filtered)
date_labels = [dt.datetime.fromordinal(int(date)).strftime('%Y') for date in unique_dates]

# Create the plot
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))

# Clip the data for Beta values
Z_beta_clipped = np.clip(Z_beta, -0.0085, -0.0055)

# Plotting the Beta values contour
contour1 = ax1.contourf(unique_dates, np.unique(ranges_filtered), Z_beta_clipped, levels=100, cmap="viridis")
fig.colorbar(contour1, ax=ax1, label="Beta Value")
ax1.set_xlabel("Date (YYYY-MM)")
ax1.set_ylabel("Range (days)")
ax1.set_title("Contour Plot of Beta Values")

# Adding iso Z lines
beta_levels = np.linspace(-0.0076 - 0.0005, -0.0072 + 0.0005, 3)
iso_lines = ax1.contour(unique_dates, np.unique(ranges_filtered), Z_beta_clipped, levels=beta_levels, colors='black', linewidths=0.5)
ax1.clabel(iso_lines, inline=True, fontsize=8)

# Adjust the x-axis ticks for dates
ax1.set_xticks(unique_dates[::600])  # Adjust the step as needed to avoid overcrowding
ax1.set_xticklabels(date_labels[::600], rotation=45, ha='right')

# Clip the data for R² values
Z_r_squared_clipped = np.clip(Z_r_squared, 0.7, 1)

# Plotting the R² contour
contour2 = ax2.contourf(unique_dates, np.unique(ranges_filtered), Z_r_squared_clipped, levels=100, cmap="inferno")
fig.colorbar(contour2, ax=ax2, label="R² Value")
ax2.set_xlabel("Date (YYYY-MM)")
ax2.set_ylabel("Range (days)")
ax2.set_title("Contour Plot of R² Values")

# Adding iso Z lines
iso_lines = ax2.contour(unique_dates, np.unique(ranges_filtered), Z_r_squared_clipped, levels=[0.9, 0.95, 0.99], colors='black', linewidths=0.5)
ax2.clabel(iso_lines, inline=True, fontsize=8)

# Adjust the x-axis ticks for dates
ax2.set_xticks(unique_dates[::600])  # Adjust the step as needed to avoid overcrowding
ax2.set_xticklabels(date_labels[::600], rotation=45, ha='right')

plt.suptitle("Barometric factor (exp. fit) and R² Contour Plots for the Oulu dataset")
plt.tight_layout()
plt.show()






#%%


time_windows_days = np.array([7 * w for w in time_windows])


for i in range(len(time_windows_days) - 1):
    # Create the condition mask
    cond = (ranges_filtered == time_windows_days[i])  # Adjust as needed

    # Convert cond and dates_filtered to NumPy arrays
    cond = np.array(cond).astype(bool)
    dates_filtered = np.array(dates_filtered)  # Ensure dates_filtered is a NumPy array

    # Debug shapes
    print(f"cond shape: {cond.shape}, dates_filtered shape: {dates_filtered.shape}")

    # Flatten cond if necessary
    if cond.ndim > 1:
        cond = cond.flatten()

    # Ensure shape compatibility
    if len(dates_filtered) != len(cond):
        raise ValueError(f"Shape mismatch: dates_filtered({len(dates_filtered)}) vs cond({len(cond)})")

    # Perform filtering
    new_dates_filtered = dates_filtered[cond]
    new_betas_filtered = betas_filtered[cond]

    # Debug output
    print(f"Number of filtered dates: {len(new_dates_filtered)}")
    print(f"Number of filtered betas: {len(new_betas_filtered)}")

    # 2D scatter plot
    fig = plt.figure(figsize=(12, 6))

    # Create a scatter plot
    ax = fig.add_subplot(111)
    scatter = ax.scatter(new_dates_filtered, new_betas_filtered, c=new_betas_filtered, cmap='viridis', alpha=0.7, marker='o')

    # Add labels and title
    ax.set_xlabel("Date")
    ax.set_ylabel("Pressure Coefficient (Beta)")
    ax.set_title("2D Scatter Plot of Beta")

    # Format x-axis as dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.tick_params(axis='x', rotation=45)

    # Set axis limits to filter out points outside the range
    ax.set_xlim(min(dates_filtered), max(dates_filtered))

    # Add a colorbar
    cbar = fig.colorbar(scatter, ax=ax, pad=0.02, label='Pressure Coefficient (Beta)')

    plt.tight_layout()
    plt.show()



# %%


time_windows_days = np.array([7 * w for w in time_windows])

if len(time_windows_days) > 10:
    m = 10
else:
    m = len(time_windows_days) - 1
    
selection_time_window_days = time_windows_days[::max(1, len(time_windows_days) // m)]

# Number of subplots = len(time_windows_days) - 1
n_subplots = m

# Create a figure with subplots arranged in a single column
fig, axes = plt.subplots(n_subplots, 1, figsize=(12, 2 * n_subplots), sharex=True)

# Loop through each time window and create scatter plots
for i in range(n_subplots):
    # Create the condition mask
    cond = (ranges_filtered == time_windows_days[i])  # Adjust as needed

    # Convert cond and dates_filtered to NumPy arrays
    cond = np.array(cond).astype(bool)
    dates_filtered = np.array(dates_filtered)
    betas_filtered = np.array(betas_filtered)

    # Flatten cond if necessary
    if cond.ndim > 1:
        cond = cond.flatten()

    # Ensure shape compatibility
    if len(dates_filtered) != len(cond):
        raise ValueError(f"Shape mismatch: dates_filtered({len(dates_filtered)}) vs cond({len(cond)})")

    # Perform filtering
    new_dates_filtered = dates_filtered[cond]
    new_betas_filtered = betas_filtered[cond]

    # Plot on the current subplot axis
    ax = axes[i]
    scatter = ax.scatter(
        new_dates_filtered,
        new_betas_filtered,
        c=new_betas_filtered,
        cmap='viridis',
        alpha=0.7,
        marker='o',
        s = 0.1
    )

    # Add labels and title
    ax.set_ylabel("Pressure Coefficient (Beta)")
    
    if time_windows_days[i] < 30:
        ax.set_title(f"2D Scatter Plot for Time Window {time_windows_days[i]} days")
    if time_windows_days[i] >= 30 and time_windows_days[i] <= 365:
        ax.set_title(f"2D Scatter Plot for Time Window {time_windows_days[i] * (1/30):.1f} months")
    if time_windows_days[i] > 365:
        ax.set_title(f"2D Scatter Plot for Time Window {time_windows_days[i] * (1/365):.1f} years")

    # Format x-axis as dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.tick_params(axis='x', rotation=45)

    # Set axis limits
    ax.set_xlim(min(dates_filtered), max(dates_filtered))

    # Add a colorbar for each subplot
    cbar = fig.colorbar(scatter, ax=ax, pad=0.02)
    cbar.set_label('Pressure Coefficient (Beta)')

# Add common xlabel for the entire figure
fig.text(0.5, 0.04, "Date", ha='center', va='center', fontsize=12)

# Adjust layout to prevent overlapping
plt.tight_layout(rect=[0, 0.05, 1, 1])  # Leave space at the bottom for the common xlabel
plt.show()

# %%
