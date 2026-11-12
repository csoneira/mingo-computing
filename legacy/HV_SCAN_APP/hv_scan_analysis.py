"""Analyze detector efficiency and operating conditions across an HV scan."""

#%%

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Created on Mon Jun 24 19:02:22 2024

@author: gfn
"""

# Print a banner before the HV scan results.
print("""
+-------------------------------------------------------------------+
|                                                                   |
|  HV Scan Analysis Script                                          |
|                                                                   |
|  This script reads the HV scan data from a CSV file, filters the  |
|  data based on the user input, and performs various calculations  |
|  and visualizations.                                              |
|                                                                   |
+-------------------------------------------------------------------+
""")


import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os
import gdown
from datetime import datetime

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Header ----------------------------------------------------------------------
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Function to safely get user input with a default value ----------------------
# -----------------------------------------------------------------------------

def get_input(prompt, default):
    user_input = input(f"{prompt} (default: {default}): ").strip()
    return user_input if user_input else default

def get_boolean_input(prompt, default):
    user_input = input(f"{prompt} (default: {'Yes' if default else 'No'}): ").strip().lower()
    return user_input in ["yes", "y", "true", "1"] if user_input else default


# -----------------------------------------------------------------------------
# Ask for user input ----------------------------------------------------------
# -----------------------------------------------------------------------------

station_number = get_input("Enter the station number (1-4)", "1")

# Validate station number
if not station_number.isdigit() or int(station_number) not in range(1, 5):
    print("Invalid station number. Please enter a number between 1 and 4.")
    exit(1)

station_number = int(station_number)

# Get start and end dates
start_date_str = get_input("Enter start date (YYYY-MM-DD HH:MM:SS)", "2025-02-25 17:30:00")
end_date_str = get_input("Enter end date (YYYY-MM-DD HH:MM:SS)", "2025-02-26 00:10:00")

# Reduced field selection
reduced_field = get_boolean_input("Enable reduced field? (Yes/No)", True)

plot_vs_hv = get_boolean_input("Plot vs HV? (Yes/No)", True)
plot_vs_time = get_boolean_input("Plot vs Time? (Yes/No)", True)
hv_vs_time = get_boolean_input("HV vs Time? (Yes/No)", True)

# HV step size
hv_step_size = get_input("Enter the HV step size", "0.01")

print()

# Convert dates to pandas datetime format
start_date = pd.to_datetime(start_date_str, format='%Y-%m-%d %H:%M:%S')
end_date = pd.to_datetime(end_date_str, format='%Y-%m-%d %H:%M:%S')

hv_step_size = float(hv_step_size)

# -----------------------------------------------------------------------------
# Construct the file path based on the station number -------------------------
# -----------------------------------------------------------------------------

def construct_file_path(station_number):
    """Construct the file path for the given station number."""
    data_folder = f"./DATA/MINGO0{station_number}"
    data_file = os.path.join(data_folder, f"data_{station_number}.csv")
    return data_folder, data_file


# -----------------------------------------------------------------------------
# Check if the file exists and needs to be downloaded -------------------------
# -----------------------------------------------------------------------------

def check_file_status(data_file):
    """Check if the file exists and if it needs to be downloaded."""
    download = False
    if not os.path.exists(data_file):
        print(f"Error: Data file {data_file} not found! Downloading from Google Drive...")
        download = True
    elif os.path.getmtime(data_file) < datetime.now().timestamp() - 3600:
        print(f"File {data_file} is older than 1 hour. Downloading a fresh copy...")
        download = True
    else:
        print(f"File {data_file} is up to date. No download needed.")
    return download


# -----------------------------------------------------------------------------
# Download the file from Google Drive -----------------------------------------
# -----------------------------------------------------------------------------

def download_file(station_number):
    """Download the file for the given station number from Google Drive."""
    file_links = {}
    try:
        # config_file_path = 
        with open(os.path.expanduser("~/HV_SCAN_APP/CONFIG/drive_links.txt"), "r") as f:
            for line in f:
                # print(line)
                parts = line.strip().split()  # Split by spaces
                if len(parts) > 1:  # Ensure the line is valid
                    station = int(parts[0])  # First column is the station number
                    url = parts[1]  # Second column is the Google Drive link
                    file_links[station] = url
                    
        # print("--------------------")
        # print(station_number)
        # print(file_links)
        # print("--------------------")
        
        if station_number in file_links:
            drive_url = file_links[station_number]
            destination_folder, destination_file = construct_file_path(station_number)
            
            # Create the directory if it doesn't exist
            os.makedirs(destination_folder, exist_ok=True)
            
            print(f"Downloading file for station {station_number}...")
            gdown.download(drive_url, destination_file, quiet=False, fuzzy=True)
            print(f"Download complete! File saved to {destination_file}")
        else:
            print(f"Error: Station number {station_number} not found in drive_links.txt.")
            exit(1)
    except Exception as e:
        print(f"Error during download: {e}")
        exit(1)

# Construct file path
data_folder, data_file = construct_file_path(station_number)

# Check if the file needs to be downloaded
download = check_file_status(data_file)

# Download the file if necessary
if download:
    download_file(station_number)

# Print execution details
# print(f"\nUsing data file: {data_file}")
# print(f"Start Date: {start_date}")
# print(f"End Date: {end_date}")
# print(f"Reduced field enabled: {reduced_field}")

# Load the selected data file
print()

try:
    data_df = pd.read_csv(data_file)
except Exception as e:
    print(f"Error loading data: {e}")

# --------------------------------------------------------------------------------------------------------------------------------------

# Convert the 'Time' column to datetime format
data_df['Time'] = pd.to_datetime(data_df['Time'].str.strip('"'), format='%Y-%m-%d %H:%M:%S')

# Filter data within the time range
data_df = data_df[(data_df['Time'] >= start_date) & (data_df['Time'] <= end_date)]

print("Data loaded and filtered by date successfully!")

# data_df["hv_mean"] = data_df["hv_mean"].round(2)

# -----------------------------------------------------------------------------
# Starting calculations -------------------------------------------------------
# -----------------------------------------------------------------------------

# Define the numeric columns based on the new CSV structure
numeric_cols = [
    'streamer_percent_1', 'streamer_percent_2', 'streamer_percent_3', 'streamer_percent_4', 
    'eff_global', 'unc_eff_global', 'count', 'pressure_lab', 'sensors_int_Temperature_int',
    'final_eff_1', 'final_eff_2', 'final_eff_3', 'final_eff_4', 'CRT_avg_mean'
]

data_df["t_in_K"] = data_df["sensors_int_Temperature_int"] + 273.15
data_df["p_in_Pa"] = data_df["pressure_lab"] * 1000

if reduced_field:
    # E/rho = V * T / P * cte
    data_df["hv_reduced"] = data_df["hv_mean"] * data_df["t_in_K"] / data_df["p_in_Pa"]
    step_size = hv_step_size * data_df["t_in_K"].median() / data_df["p_in_Pa"].median()
    
    # V * P / T, which is actually nothing
    # data_df["hv_reduced"] = data_df["hv_mean"] * data_df["t_in_K"] / data_df["p_in_Pa"]
    # step_size = hv_step_size * data_df["t_in_K"].median() / data_df["p_in_Pa"].median()
    
    data_grouped = data_df.groupby('hv_reduced')[numeric_cols].mean()
    label_hv = "$HV \\cdot T / P$"
    units_hv = "$(kV \\cdot K / Pa)$"
else:
    data_grouped = data_df.groupby('hv_mean')[numeric_cols].mean()
    step_size = hv_step_size
    label_hv = "HV"
    units_hv = "(kV)"

# Check if CRT_avg exists in the data_grouped columns
crt_avg = data_grouped.get('CRT_avg_mean', None)

efficiency_M1 = data_grouped.get('final_eff_1', None)
efficiency_M2 = data_grouped.get('final_eff_2', None)
efficiency_M3 = data_grouped.get('final_eff_3', None)
efficiency_M4 = data_grouped.get('final_eff_4', None)

# Extract the relevant columns for plotting
hv = data_grouped.index
streamer_percentage_M1 = data_grouped['streamer_percent_1']
streamer_percentage_M2 = data_grouped['streamer_percent_2']
streamer_percentage_M3 = data_grouped['streamer_percent_3']
streamer_percentage_M4 = data_grouped['streamer_percent_4']
global_efficiency = data_grouped['eff_global']
global_uncertainty = data_grouped['unc_eff_global']
count = data_grouped['count']
count_over_efficiency = count / global_efficiency

count_over_efficiency = count_over_efficiency.replace([np.inf, -np.inf], 0)
count_over_efficiency = count_over_efficiency.interpolate()
count_over_efficiency = count_over_efficiency.fillna(0)

pressure_lab = data_grouped['pressure_lab']
temp_lab = data_grouped['sensors_int_Temperature_int']

# Define the bin edges and center points for HV
hv_min, hv_max = hv.min(), hv.max()
hv_bins = np.arange(hv_min, hv_max + step_size, step_size)
hv_bin_centers = (hv_bins[:-1] + hv_bins[1:]) / 2

# Function to perform binning and averaging
def bin_and_average(hv, values):
    binned_values = np.zeros(len(hv_bin_centers))  # Initialize the output array
    for i in range(len(hv_bin_centers)):
        # Find values within the current bin
        in_bin = (hv >= hv_bins[i]) & (hv < hv_bins[i + 1])
        valid_values = values[in_bin]
        
        # Check if there are any valid (non-NaN) values in the bin
        if np.any(~np.isnan(valid_values)):
            binned_values[i] = np.nanmean(valid_values)  # Compute the mean, ignoring NaNs
        else:
            # This happens because during a HV scan only discrete values of HV are taken
            # print(hv_bins[i], hv_bins[i + 1])
            binned_values[i] = np.nan  # If no valid values, set to NaN
    
    return binned_values

# Smooth data for each series by averaging over bins
streamer_percentage_M1_smooth = bin_and_average(hv, streamer_percentage_M1)
streamer_percentage_M2_smooth = bin_and_average(hv, streamer_percentage_M2)
streamer_percentage_M3_smooth = bin_and_average(hv, streamer_percentage_M3)
streamer_percentage_M4_smooth = bin_and_average(hv, streamer_percentage_M4)
global_efficiency_smooth = bin_and_average(hv, global_efficiency)
global_uncertainty_smooth = bin_and_average(hv, global_uncertainty)
count_smooth = bin_and_average(hv, count)
count_over_efficiency_smooth = bin_and_average(hv, count_over_efficiency)
pressure_lab_smooth = bin_and_average(hv, pressure_lab)
temp_lab_smooth = bin_and_average(hv, temp_lab)

# Smooth normalized counts
mean_count_smooth = np.nanmean(count_smooth)
mean_count_over_eff_smooth = np.nanmean(count_over_efficiency_smooth)
normalized_count_smooth = (count_smooth - mean_count_smooth) / mean_count_smooth
normalized_count_over_eff_smooth = (count_over_efficiency_smooth - mean_count_over_eff_smooth) / mean_count_over_eff_smooth

if plot_vs_hv:
    # Create subplots, adding one more if CRT_avg exists
    fig, axs = plt.subplots(4, 1, figsize=(10, 12), sharex=True)

    # Plot 1: Efficiency of each plane (if the efficiency columns exist)
    axs[0].set_ylabel('Efficiency')
    if efficiency_M1 is not None:
        axs[0].scatter(hv_bin_centers, bin_and_average(hv, efficiency_M1), label='Efficiency P1', color='blue')
    if efficiency_M2 is not None:
        axs[0].scatter(hv_bin_centers, bin_and_average(hv, efficiency_M2), label='Efficiency P2', color='orange')
    if efficiency_M3 is not None:
        axs[0].scatter(hv_bin_centers, bin_and_average(hv, efficiency_M3), label='Efficiency P3', color='green')
    if efficiency_M4 is not None:
        axs[0].scatter(hv_bin_centers, bin_and_average(hv, efficiency_M4), label='Efficiency P4', color='red')
    axs[0].legend()
    axs[0].set_ylim(None,1)
    axs[0].grid(True)
    axs[0].set_title(f'Efficiency of Each Plane vs {label_hv}')

    # Plot 3: Streamer Percentages vs HV
    axs[1].set_ylabel('Streamer %', color='tab:blue')
    axs[1].scatter(hv_bin_centers, streamer_percentage_M1_smooth, label='Streamer P1', color='blue')
    axs[1].scatter(hv_bin_centers, streamer_percentage_M2_smooth, label='Streamer P2', color='orange', linestyle='--')
    axs[1].scatter(hv_bin_centers, streamer_percentage_M3_smooth, label='Streamer P3', color='green', linestyle='-.')
    axs[1].scatter(hv_bin_centers, streamer_percentage_M4_smooth, label='Streamer P4', color='red', linestyle=':')
    axs[1].legend(loc='upper left')
    axs[1].grid(True)
    axs[1].set_title(f'Streamer % vs {label_hv}')

    # Plot 4: Pressure and Temperature vs HV
    axs[2].set_ylabel('Pressure (Lab)', color='tab:orange')
    axs[2].scatter(hv_bin_centers, pressure_lab_smooth, label='Pressure', color='orange')
    axs[2].tick_params(axis='y', labelcolor='tab:orange')
    # Add second y-axis for temperature
    ax_temp = axs[2].twinx()
    ax_temp.set_ylabel('Temperature (Lab)', color='tab:red')
    ax_temp.scatter(hv_bin_centers, temp_lab_smooth, label='Temperature', color='red')
    ax_temp.tick_params(axis='y', labelcolor='tab:red')
    axs[2].grid(True)
    axs[2].set_title(f'Pressure and Temperature vs {label_hv}')

    # axs[3].scatter(hv_bin_centers, hv_bin_centers, label='CRT Avg', color='purple')
    axs[3].scatter(hv_bin_centers, bin_and_average(hv, crt_avg) * 1000, label='CRT', color='purple')
    axs[3].set_ylabel('Timing uncertainty (ps)')
    axs[3].grid(True)
    axs[3].legend()
    axs[3].set_title(f'CRT (ps) vs {label_hv}')

    # Set common x-axis label
    axs[-1].set_xlabel(f'{label_hv} {units_hv}')
    axs[-1].set_xlim(hv_min, hv_max)

    # Adjust layout
    plt.tight_layout()
    # plt.show()

# %%

streamer_cols = ['streamer_percent_1', 'streamer_percent_2', 'streamer_percent_3', 'streamer_percent_4']
efficiency_cols = ['final_eff_1', 'final_eff_2', 'final_eff_3', 'final_eff_4']
pressure_col = 'pressure_lab'
temperature_col = 'sensors_int_Temperature_int'
crt_col = 'CRT_avg_mean'
rate_col = 'rate'  # Assuming 'rate' exists in your dataset
hv_col = 'hv_mean'
hv_reduced = 'hv_reduced'

# Ensure only existing columns are used
selected_cols = streamer_cols + efficiency_cols + [pressure_col, temperature_col, crt_col, rate_col, hv_col, hv_reduced]
selected_cols = [col for col in selected_cols if col in data_df.columns]

data_df.set_index("Time", inplace=True)
data_resampled = data_df[selected_cols].resample("1min").mean()

# -----------------------------------------------------------------------------
# Multi-Plot with Proper Groupings --------------------------------------------
# -----------------------------------------------------------------------------

if plot_vs_time:
    fig, axs = plt.subplots(4, 1, figsize=(10, 12), sharex=True)

    colors = ['blue', 'orange', 'green', 'red']

    # **Plot all Efficiencies in One Plot (Blue, Orange, Green, Red)**
    for i, col in enumerate(efficiency_cols):
        if col in data_resampled:
            axs[0].plot(data_resampled.index, data_resampled[col], label=col, color=colors[i], marker="o", linestyle="-")
    axs[0].set_ylabel("Efficiency")
    axs[0].legend()
    axs[0].grid(True)
    axs[0].set_ylim(0, 1)
    axs[0].set_title("Efficiencies Over Time")

    # **Plot all Streamer Percentages in One Plot (Blue, Orange, Green, Red)**

    for i, col in enumerate(streamer_cols):
        if col in data_resampled:
            axs[1].plot(data_resampled.index, data_resampled[col], label=col, color=colors[i], marker="o", linestyle="-")
    axs[1].set_ylabel("Streamer %")
    axs[1].legend()
    axs[1].grid(True)
    axs[1].set_title("Streamer Percentages Over Time")

    # **Dual Y-Axis Plot: Pressure & Temperature (Orange, Red)**
    ax_temp = axs[2].twinx()  # Create a second y-axis

    # Plot Pressure on primary y-axis
    if pressure_col in data_resampled:
        axs[2].plot(data_resampled.index, data_resampled[pressure_col], label="Pressure", color='orange', marker="o", linestyle="-")
        axs[2].set_ylabel("Pressure (Lab)", color='orange')
        axs[2].tick_params(axis='y', labelcolor='orange')

    # Plot Temperature on secondary y-axis
    if temperature_col in data_resampled:
        ax_temp.plot(data_resampled.index, data_resampled[temperature_col], label="Temperature", color='red', marker="o", linestyle="-")
        ax_temp.set_ylabel("Temperature (Lab)", color='red')
        ax_temp.tick_params(axis='y', labelcolor='red')

    axs[2].set_title("Pressure and Temperature Over Time")
    axs[2].grid(True)

    # **Plot CRT (Purple)**
    if crt_col in data_resampled:
        axs[3].plot(data_resampled.index, data_resampled[crt_col] * 1000, label="CRT (ps)", color='purple', marker="o", linestyle="-")
        axs[3].set_ylabel("CRT (ps)", color='purple')
        axs[3].grid(True)
        axs[3].legend()
        axs[3].set_title("CRT Over Time")

    # # **Plot Rate (Blue)**
    # if rate_col in data_resampled:
    #     axs[4].plot(data_resampled.index, data_resampled[rate_col], label="Rate", color='blue', marker="o", linestyle="-")
    #     axs[4].set_ylabel("Rate")
    #     axs[4].grid(True)
    #     axs[4].legend()
    #     axs[4].set_title("Rate Over Time")

    # Set x-axis label and format
    axs[-1].set_xlabel("Time")

    # Adjust layout and show plot
    plt.tight_layout()
    # plt.show()

# %%

if hv_vs_time:
    fig, ax = plt.subplots(figsize=(10, 6))  # Single plot instead of 4 subplots

    if hv_col in data_resampled and not reduced_field:
        ax.plot(data_resampled.index, data_resampled[hv_col], label=f"{label_hv} {units_hv}", color='green', marker="o", linestyle="-")
        ax.set_ylabel(f"{label_hv} {units_hv}")
        ax.set_title("HV Over Time")

    elif hv_reduced in data_resampled and reduced_field:
        ax.plot(data_resampled.index, data_resampled[hv_reduced], label=f"{label_hv} {units_hv}", color='green', marker="o", linestyle="-")
        ax.set_ylabel(f"{label_hv} {units_hv}")
        ax.set_title("Reduced HV Over Time")

    ax.set_xlabel("Time")
    ax.grid(True)
    ax.legend()

    plt.tight_layout()
    # plt.show()

if not plot_vs_hv and not plot_vs_time and not hv_vs_time:
    print("No plots selected. Exiting...")
    exit(0)

# Show the plots (non-blocking)
plt.show(block=False)

# Wait for the user to press any key in the terminal
print("\nPlots are displayed. Press any key in the terminal to exit...")
input()

# Close all figures after the key press
plt.close('all')
# %%