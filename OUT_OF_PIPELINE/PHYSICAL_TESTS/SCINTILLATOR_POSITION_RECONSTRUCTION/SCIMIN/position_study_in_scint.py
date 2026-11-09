#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Oct 1 2024

@author: csoneira
"""

globals().clear()

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Preamble --------------------------------------------------------------------
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

import struct
import numpy as np
import matplotlib.pyplot as plt
import sys
from scipy.optimize import curve_fit
import pandas as pd

# Function to load data from SiPMs_hitPoi.txt and handle inconsistent rows
def load_sipm_data(filename):
    data = []
    with open(filename, 'r') as f:
        for line in f:
            values = line.strip().split()
            if len(values) == num_sipms_row**2+9:  # Ensure we only keep rows with 25 columns
                data.append([float(x) for x in values])
            else:
                print(f"Skipping row with {len(values)} columns")
    return np.array(data)


def flatten_event(row):
    # Each part corresponds to a fixed size component of your row
    sipms_signal = row['signal_bot']   # (nsipms_bot * nsipms_bot) length
    sipm_top = row['signal_top']       # single value
    sipm_lat = row['signal_lat']       # 2 values
    en_hit = [row['en_hit']]           # single value
    xyz_hit = row['xyz_hit']           # 3 values
    photon_index = [row['photon_index']]  # single integer
    cristal_index = [row['cristal_index']] # single integer
    
    # Concatenate all the components into a single flat array
    return np.hstack([sipms_signal, sipm_top, sipm_lat, en_hit, xyz_hit, photon_index, cristal_index])

def read_binary_file(file_path):
    """Reads binary data from the file and returns a structured list of events."""
    
    event_data = []  # This will store all the events

    with open(file_path, 'rb') as f:
        while True:
            # Read the number of bytes corresponding to one event
            event_bytes = f.read(bytes_per_event)
            
            if not event_bytes:
                break  # Exit loop when no more data
            
            # Read and unpack the floating point and integer values
            floats_format = f'{floats_per_event}f'  # Format for float values
            int_format = '2I'  # Format for two unsigned integers
            
            # Unpack the floats (SiPM_bot, SiPM_top, SiPM_lat, en_hit, xyz_hit)
            unpacked_floats = struct.unpack(floats_format, event_bytes[:floats_per_event * 4])
            
            # Unpack the photon_index and cristal_index as integers
            photon_index, cristal_index = struct.unpack(int_format, event_bytes[floats_per_event * 4:])
            
            # Organize the unpacked data into a list for each event
            signal_bot = unpacked_floats[:num_sipms_row * num_sipms_row]
            signal_top = unpacked_floats[num_sipms_row * num_sipms_row:num_sipms_row * num_sipms_row + nsipms_top * nsipms_top]
            signal_lat = unpacked_floats[num_sipms_row * num_sipms_row + nsipms_top * nsipms_top:num_sipms_row * num_sipms_row + nsipms_top * nsipms_top + nsipms_lat]
            en_hit = unpacked_floats[num_sipms_row * num_sipms_row + nsipms_top * nsipms_top + nsipms_lat]
            xyz_hit = unpacked_floats[num_sipms_row * num_sipms_row + nsipms_top * nsipms_top + nsipms_lat + 1:]
            
            # Append all data of the current event into the list
            event_data.append({
                'signal_bot': signal_bot,
                'signal_top': signal_top,
                'signal_lat': signal_lat,
                'en_hit': en_hit,
                'xyz_hit': xyz_hit,
                'photon_index': photon_index,
                'cristal_index': cristal_index
            })
        
        # Apply this flattening function to all rows in event_df
        event_data = pd.DataFrame(event_data)
        flattened_data = np.array([flatten_event(row) for _, row in event_data.iterrows()])
        # signal_bot_data = np.array([event['signal_bot'] for event in event_data])
        # xyz_hit_data = np.array([event['xyz_hit'] for event in event_data])

    # return signal_bot_data, xyz_hit_data
    return flattened_data


def plot_predicted_vs_actual(calculated_positions, real_positions):
    plt.figure(figsize=(15, 5))
    for i, label in enumerate(['X', 'Y', 'Z']):
        plt.subplot(1, 3, i + 1)
        plt.scatter(real_positions[:, i], calculated_positions[:, i], alpha=0.5)
        plt.xlabel(f'True {label}')
        plt.ylabel(f'Predicted {label}')
        plt.title(f'{label} - True vs Predicted')
        if i == 2:
            plt.xlim([0,30])
            plt.ylim([0,30])
        else:
            plt.xlim([-150,150])
            plt.ylim([-150,150])
        plt.grid(True)
    plt.tight_layout()
    plt.show()
    
# Input parameters (example values)
crystal_size = 300  # mm (example)
num_sipms_row = 6  # Number of SiPMs along one axis (4x4 grid)
sipm_real_size = 1  # mm (example)

nsipms_top = 1
nsipms_lat = 2

# Calculate the total number of floats to be read for each event
floats_per_event = num_sipms_row * num_sipms_row + nsipms_top * nsipms_top + nsipms_lat + 1 + 3
# photon_index and cristal_index are integers, so 2 additional integers
total_values_per_event = floats_per_event + 2
# Total bytes to read per event (floats are 4 bytes, integers are 4 bytes)
bytes_per_event = total_values_per_event * 4

# filename = 'SiPMs_hitPoi.txt'
filename = 'SiPMs_hitPoi_5x5.txt'
filename_bin = 'SiPM_hit_Poi_6x6.raw'
# data = load_sipm_data(filename)
data = read_binary_file(filename_bin)
# data_bin = load_binary_data(filename, num_events, 4)

# a = 1/0

right_histo_plot_lim = 500


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Function definition ---------------------------------------------------------
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

# def calculate_xyz(sipm_signals, sipm_coordinates):

#     normalized_signals = sipm_signals / np.sum(sipm_signals) if np.sum(sipm_signals) > 0 else sipm_signals

#     # Calculate weighted sums for X and Y based on the permuted signals and SiPM positions
#     weighted_sum_x = np.sum(normalized_signals * sipm_coordinates[:, 0])  # X positions
#     weighted_sum_y = np.sum(normalized_signals * sipm_coordinates[:, 1])  # Y positions
    
#     # total_signals = np.sum(normalized_signals)
#     total_signals = np.sum(normalized_signals)

#     # Avoid division by zero if total_signals is too small
#     if total_signals == 0:
#         return 0, 0, 0

#     # Z value will be considered 0 in this case, as the SiPMs are on a 2D plane (Z=0)
#     return weighted_sum_x / total_signals, weighted_sum_y / total_signals, 0


def calculate_xyz(sipm_signals, sipm_coordinates):

    normalized_signals = sipm_signals / np.max(sipm_signals) if np.max(sipm_signals) > 0 else sipm_signals

    # Calculate weighted sums for X and Y based on the permuted signals and SiPM positions
    weighted_sum_x = np.sum(normalized_signals * sipm_coordinates[:, 0])  # X positions
    weighted_sum_y = np.sum(normalized_signals * sipm_coordinates[:, 1])  # Y positions
    
    # total_signals = np.sum(normalized_signals)
    total_signals = np.sum(normalized_signals)

    # Avoid division by zero if total_signals is too small
    if total_signals == 0:
        return 0, 0, 0

    # Z value will be considered 0 in this case, as the SiPMs are on a 2D plane (Z=0)
    return weighted_sum_x / total_signals, weighted_sum_y / total_signals, 0


def calculate_sipm_positions(crystal_size, num_sipms, sipm_real_size):
    region_size = crystal_size / num_sipms
    gap = region_size - sipm_real_size
    sipm_positions = np.linspace(-(crystal_size / 2) + (region_size / 2), (crystal_size / 2) - (region_size / 2), num_sipms)
    sipm_x, sipm_y = np.meshgrid(sipm_positions, sipm_positions)
    sipm_coordinates = np.vstack([sipm_x.ravel(), sipm_y.ravel()]).T
    return sipm_coordinates, gap


def gaussian_1d(x, A, mu, sigma):
    return A * np.exp(-0.5 * ((x - mu) / sigma)**2)


# Plot histograms for the SiPM channels
def plot_sipm_histograms(data):
    sipm_channels = data[:, :num_sipms_row**2]  # Assuming the first 16 columns are SiPM channels
    
    # plt.figure(figsize=(15, 10))
    # for i in range(num_sipms_row**2):
    #     plt.subplot(num_sipms_row, num_sipms_row, i + 1)
    #     plt.hist(sipm_channels[:, i], bins=100, alpha=0.75)
    #     plt.title(f'SiPM Channel {i + 1}')
    #     plt.xlabel('Signal')
    #     plt.xlim([0, right_histo_plot_lim])
    #     plt.ylabel('Frequency')
    # plt.tight_layout()
    # plt.show()
    
    total_signals = np.sum(sipm_channels, axis=1)
    
    plt.figure(figsize=(15, 10))
    for i in range(num_sipms_row**2):
        plt.subplot(num_sipms_row, num_sipms_row, i + 1)
        plt.hist(sipm_channels[:, i]/total_signals, bins=100, alpha=0.75)
        plt.title(f'SiPM Channel {i + 1}')
        plt.xlabel('Signal / %')
        # plt.xlim([0, 1000])
        plt.ylabel('Frequency')
    plt.tight_layout()
    plt.show()
    
    plt.figure(figsize=(12, 6))
    counts, bins, _ = plt.hist(total_signals, bins=100, alpha=0.75, label='Data')
    bin_centers = (bins[:-1] + bins[1:]) / 2  # Calculate bin centers
    popt, _ = curve_fit(gaussian_1d, bin_centers, counts, p0=[np.max(counts), np.mean(total_signals), np.std(total_signals)])
    x_values = np.linspace(min(total_signals), max(total_signals), 1000)
    plt.plot(x_values, gaussian_1d(x_values, *popt), 'r-', label=f'Fitted Gaussian:\nA={popt[0]:.1f},\nmu={popt[1]:.1f},\nsigma={popt[2]:.1f}')
    plt.title('Total signal summed with Gaussian fit')
    plt.xlabel('Signal')
    plt.ylabel('Frequency')
    plt.legend()
    plt.tight_layout()
    plt.show()
    

# 3D plot of XYZ coordinates with equal aspect ratio
def plot_3d_xyz(data, calculated_positions=None, sipm_positions=None):
    x_real = data[:, num_sipms_row**2+4]  # X
    y_real = data[:, num_sipms_row**2+5]  # Y
    z_real = data[:, num_sipms_row**2+6]  # Z

    fig = plt.figure(figsize=(12, 6))

    # Original 3D plot of real XYZ
    ax1 = fig.add_subplot(121, projection='3d')
    ax1.scatter(x_real, y_real, z_real, c='r', marker='o', label='Real XYZ')
    ax1.set_xlabel('X Coordinate')
    ax1.set_ylabel('Y Coordinate')
    ax1.set_zlabel('Z Coordinate')
    ax1.set_title('3D Plot of Real XYZ Coordinates')
    ax1.set_xlim3d(-150,150)
    ax1.set_ylim3d(-150,150)
    ax1.set_zlim3d(-30,30)
    
    # Set equal aspect ratio
    # set_axes_equal(ax1)

    if calculated_positions is not None:
        # Second plot for calculated XYZ
        x_calc, y_calc, z_calc = calculated_positions.T
        ax2 = fig.add_subplot(122, projection='3d')
        ax2.scatter(x_calc, y_calc, z_calc, c='b', marker='x', label='Calculated XYZ')
        ax2.set_xlabel('X Coordinate')
        ax2.set_ylabel('Y Coordinate')
        ax2.set_zlabel('Z Coordinate')
        ax2.set_title('3D Plot of Calculated XYZ Coordinates')
        ax2.set_xlim3d(-150,150)
        ax2.set_ylim3d(-150,150)
        ax2.set_zlim3d(-30,30)

        # Set equal aspect ratio
        # set_axes_equal(ax2)

    # Plot SiPMs at Z=0
    if sipm_positions is not None:
        for x in sipm_positions:
            for y in sipm_positions:
                ax1.scatter(x, y, 0, c='g', marker='o', s=100)  # SiPM positions
                ax2.scatter(x, y, 0, c='g', marker='o', s=100)  # SiPM positions
    
    ax1.invert_zaxis()
    plt.show()


# Set equal aspect ratio for 3D plot
def set_axes_equal(ax):
    """Set equal aspect ratio for a 3D plot."""
    limits = np.array([ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()])
    centers = np.mean(limits, axis=1)
    spans = 0.5 * (limits[:, 1] - limits[:, 0]).max()
    ax.set_xlim3d([centers[0] - spans, centers[0] + spans])
    ax.set_ylim3d([centers[1] - spans, centers[1] + spans])
    ax.set_zlim3d([centers[2] - spans, centers[2] + spans])


# Function to plot residual histograms and fit Gaussian
def plot_residual_histograms(real_positions, calculated_positions):
    residuals = real_positions - calculated_positions

    fig, axes = plt.subplots(3, 1, figsize=(8, 12))
    
    # Residuals in X
    try:
        counts, bins, _ = axes[0].hist(residuals[:, 0], bins=150, alpha=0.75)
        bin_centers = (bins[:-1] + bins[1:]) / 2  # Get bin centers for fitting
        popt, _ = curve_fit(gaussian_1d, bin_centers, counts, p0=[np.max(counts), np.mean(residuals[:, 0]), np.std(residuals[:, 0])])
        x_values = np.linspace(min(residuals[:, 0]), max(residuals[:, 0]), 1000)
        axes[0].plot(x_values, gaussian_1d(x_values, *popt), 'r-', label=f'Fitted Gaussian:\nA={popt[0]:.1f},\
                     \nmu={popt[1]:.1f},\nsigma={popt[2]:.1f}\nResolution={popt[2]/10/ np.sqrt(2):.1f} cm')
    except Exception as e:
        axes[0].text(0.5, 0.9, 'Fit did not work', transform=axes[0].transAxes, color='red', fontsize=12, ha='center')
        print(f"Fit failed for Residual X: {e}")
    axes[0].set_xlabel('Residual X')
    axes[0].set_ylabel('Frequency')
    axes[0].set_title('Histogram of Residuals in X')
    axes[0].legend()

    # Residuals in Y
    try:
        counts, bins, _ = axes[1].hist(residuals[:, 1], bins=150, alpha=0.75)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        popt, _ = curve_fit(gaussian_1d, bin_centers, counts, p0=[np.max(counts), np.mean(residuals[:, 1]), np.std(residuals[:, 1])])
        x_values = np.linspace(min(residuals[:, 1]), max(residuals[:, 1]), 1000)
        axes[1].plot(x_values, gaussian_1d(x_values, *popt), 'r-', label=f'Fitted Gaussian:\nA={popt[0]:.1f},\
                     \nmu={popt[1]:.1f},\nsigma={popt[2]:.1f}\nResolution={popt[2]/10/ np.sqrt(2):.1f} cm')
    except Exception as e:
        axes[1].text(0.5, 0.9, 'Fit did not work', transform=axes[1].transAxes, color='red', fontsize=12, ha='center')
        print(f"Fit failed for Residual Y: {e}")
    axes[1].set_xlabel('Residual Y')
    axes[1].set_ylabel('Frequency')
    axes[1].set_title('Histogram of Residuals in Y')
    axes[1].legend()

    # Residuals in Z
    try:
        counts, bins, _ = axes[2].hist(residuals[:, 2], bins=150, alpha=0.75)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        popt, _ = curve_fit(gaussian_1d, bin_centers, counts, p0=[np.max(counts), np.mean(residuals[:, 2]), np.std(residuals[:, 2])])
        x_values = np.linspace(min(residuals[:, 2]), max(residuals[:, 2]), 1000)
        axes[2].plot(x_values, gaussian_1d(x_values, *popt), 'r-', label=f'Fitted Gaussian:\nA={popt[0]:.1f},\
                     \nmu={popt[1]:.1f},\nsigma={popt[2]:.1f}\nResolution={popt[2]/10/ np.sqrt(2):.1f} cm')
    except Exception as e:
        axes[2].text(0.5, 0.9, 'Fit did not work', transform=axes[2].transAxes, color='red', fontsize=12, ha='center')
        print(f"Fit failed for Residual Z: {e}")
    axes[2].set_xlabel('Residual Z')
    axes[2].set_ylabel('Frequency')
    axes[2].set_title('Histogram of Residuals in Z')
    axes[2].legend()
    
    plt.tight_layout()
    plt.show()


# 3D surface plot of residuals in X+Y vs XY plane
def plot_residual_xy_surface(real_positions, residuals):
    x_real = real_positions[:, 0]  # X
    y_real = real_positions[:, 1]  # Y
    z_residual = np.sqrt( residuals[:, 0]**2 + residuals[:, 1]**2 )  # Residuals in X + Y

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection='3d')
    surf = ax.plot_trisurf(x_real, y_real, z_residual, cmap='viridis', edgecolor='none')
    ax.set_xlabel('X Coordinate')
    ax.set_ylabel('Y Coordinate')
    ax.set_zlabel('Residual (X + Y) in mm')
    ax.set_title('Residual (X + Y) vs XY Plane')
    
    # ax.view_init(elev=90, azim=0)
    
    # fig.colorbar(surf, ax=ax, shrink=0.5, aspect=5)
    fig.colorbar(surf, ax=ax)
    plt.show()


def plot_residual_xy_contour(real_positions, residuals):
    x_real = real_positions[:, 0]  # X
    y_real = real_positions[:, 1]  # Y
    z_residual = np.sqrt(residuals[:, 0]**2 + residuals[:, 1]**2)  # Residuals in X + Y

    # Create a 2D grid of x_real and y_real values
    grid_x, grid_y = np.meshgrid(
        np.linspace(min(x_real), max(x_real), 100),
        np.linspace(min(y_real), max(y_real), 100)
    )

    # Interpolate z_residual values onto the 2D grid
    from scipy.interpolate import griddata
    grid_z = griddata((x_real, y_real), z_residual, (grid_x, grid_y), method='cubic')

    # Plot the 2D contour
    plt.figure(figsize=(10, 7))
    contour = plt.contourf(grid_x, grid_y, grid_z, levels=10, cmap='viridis')
    plt.colorbar(contour)

    # Add labels and title
    plt.xlabel('X Coordinate')
    plt.ylabel('Y Coordinate')
    plt.gca().set_aspect('equal', adjustable='box')

    plt.title('Residual $\sqrt{X^{2} + Y^{2}}$ (in mm) vs XY Plane')
    plt.show()


def plot_histograms_with_sipms(data, calculated_positions, sipm_positions, bins=100):
    # Create the figure with four subplots side by side
    fig, axes = plt.subplots(1, 4, figsize=(20, 5))

    # Plot histogram for data X (first column)
    axes[0].hist(data[:, 0], bins=bins, alpha=0.75)
    axes[0].set_title('Data X')
    axes[0].set_xlabel('X')
    axes[0].set_ylabel('Frequency')

    # Plot SiPM positions as vertical lines
    for sipm_x in sipm_positions[:, 0]:
        axes[0].axvline(x=sipm_x, color='r', linestyle='--', label='SiPM Position' if sipm_x == sipm_positions[0, 0] else "")

    # Plot histogram for data Y (second column)
    axes[1].hist(data[:, 1], bins=bins, alpha=0.75)
    axes[1].set_title('Data Y')
    axes[1].set_xlabel('Y')
    axes[1].set_ylabel('Frequency')

    # Plot SiPM positions as vertical lines
    for sipm_y in sipm_positions[:, 1]:
        axes[1].axvline(x=sipm_y, color='r', linestyle='--', label='SiPM Position' if sipm_y == sipm_positions[0, 1] else "")

    # Plot histogram for calculated_positions X (first column)
    axes[2].hist(calculated_positions[:, 0], bins=bins, alpha=0.75)
    axes[2].set_title('Calculated X')
    axes[2].set_xlabel('X')
    axes[2].set_ylabel('Frequency')

    # Plot SiPM positions as vertical lines
    for sipm_x in sipm_positions[:, 0]:
        axes[2].axvline(x=sipm_x, color='r', linestyle='--', label='SiPM Position' if sipm_x == sipm_positions[0, 0] else "")

    # Plot histogram for calculated_positions Y (second column)
    axes[3].hist(calculated_positions[:, 1], bins=bins, alpha=0.75)
    axes[3].set_title('Calculated Y')
    axes[3].set_xlabel('Y')
    axes[3].set_ylabel('Frequency')

    # Plot SiPM positions as vertical lines
    for sipm_y in sipm_positions[:, 1]:
        axes[3].axvline(x=sipm_y, color='r', linestyle='--', label='SiPM Position' if sipm_y == sipm_positions[0, 1] else "")

    # Ensure legend only appears once for SiPM position
    handles, labels = axes[3].get_legend_handles_labels()
    if handles:
        axes[3].legend(handles[:1], labels[:1], loc='best')

    plt.tight_layout()
    plt.show()


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Code execution --------------------------------------------------------------
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

num_sipms = num_sipms_row**2

# Calculate SiPM positions and gaps
sipm_positions, gap = calculate_sipm_positions(crystal_size, num_sipms_row, sipm_real_size)

# For each event, calculate the estimated XYZ positions
calculated_positions = []
for event in data:
    sipm_signals = event[:num_sipms]  # Use the first 16 columns as SiPM channels
    estimated_xyz = calculate_xyz(sipm_signals, sipm_positions)
    calculated_positions.append(estimated_xyz)
calculated_positions = np.array(calculated_positions)

# Plot histograms for each SiPM channel
plot_sipm_histograms(data)

# Plot real and calculated XYZ positions with SiPMs overlaid
real_positions = data[:, num_sipms+4:num_sipms+7]  # Real XYZ columns
plot_3d_xyz(data, calculated_positions, sipm_positions)

plot_predicted_vs_actual(calculated_positions, real_positions)

# Plot residual histograms for X, Y, Z
plot_residual_histograms(real_positions, calculated_positions)

# Calculate and plot 3D surface of residual X + residual Y vs XY plane
residuals = real_positions - calculated_positions
plot_residual_xy_surface(real_positions, residuals)
plot_residual_xy_contour(real_positions, residuals)

plot_histograms_with_sipms(real_positions, calculated_positions, sipm_positions, bins=50)

