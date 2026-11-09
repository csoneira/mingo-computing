#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct  2 09:42:54 2024

@author: cayesoneira
"""

import sys
sys.path.append('/media/cayesoneira/Caye/python_packages')

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Flatten
from sklearn.model_selection import train_test_split
import struct
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy import stats

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


crystal_size = 300  # mm (example)
num_sipms_row = 6  # Number of SiPMs along one axis (4x4 grid)
sipm_real_size = 1  # mm (example)
num_events = 10000

# filename = 'SiPMs_hitPoi.txt'
filename = 'SiPMs_hitPoi_5x5.txt'
filename_bin = 'example_3.txt'
data = load_sipm_data(filename)
# data_bin = load_binary_data(filename, num_events, 4)

right_histo_plot_lim = 500

num_sipms = num_sipms_row**2
sipm_signals = data[:, 0:num_sipms] 
real_positions = data[:, num_sipms+4:num_sipms+7]  # Real XYZ columns

def remove_outliers_zscore(sipm_signals, real_positions, threshold=10):
    print(f"From {len(sipm_signals)} events...")
    z_scores = np.abs(stats.zscore(sipm_signals, axis=0))  # Calculate z-scores for each column in sipm_signals
    non_outlier_indices = (z_scores < threshold).all(axis=1)  # Keep rows where all z-scores are below the threshold
    sipm_signals_clean = sipm_signals[non_outlier_indices, :]
    real_positions_clean = real_positions[non_outlier_indices, :]
    print(f"... to {len(sipm_signals_clean)} events")
    return sipm_signals_clean, real_positions_clean

# Remove outliers from both sipm_signals and real_positions
sipm_signals, real_positions = remove_outliers_zscore(sipm_signals, real_positions)

X_train, X_test, y_train, y_test = train_test_split(sipm_signals, real_positions, test_size=0.2, random_state=42)

# def remove_outliers(X, y):
#     # Define the outlier conditions for x, y, z coordinates
#     condition = (
#         (y[:, 0] >= -150) & (y[:, 0] <= 150) &  # Condition for X in [-150, 150]
#         (y[:, 1] >= -150) & (y[:, 1] <= 150) &  # Condition for Y in [-150, 150]
#         (y[:, 2] >= -30) & (y[:, 2] <= 30)     # Condition for Z in [-30, 30]
#     )
    
#     # Apply the condition to filter out outliers
#     return X[condition], y[condition]

# # Remove outliers from both training and test data
# X_train, y_train = remove_outliers(X_train, y_train)
# X_test, y_test = remove_outliers(X_test, y_test)

# Create a neural network model
model = Sequential([
    Dense(128, activation='relu', input_shape=(36,)),  # Input layer for 36 SiPM signals
    Dense(64, activation='relu'),
    Dense(32, activation='relu'),
    Dense(3)  # Output layer for x, y, z positions
])

# Compile the model
model.compile(optimizer='adam', loss='mse')

# Train the model
history = model.fit(X_train, y_train, epochs=10, validation_split=0.2, verbose=0)

# Evaluate the model
test_loss = model.evaluate(X_test, y_test)
test_loss


from tensorflow.keras.utils import plot_model

# Code to plot the training history
def plot_training_history(history):
    # Plot loss over epochs
    plt.figure(figsize=(10, 6))
    plt.plot(history.history['loss'], label='Training Loss')
    plt.plot(history.history['val_loss'], label='Validation Loss')
    plt.title('Training and Validation Loss over Epochs')
    plt.xlabel('Epochs')
    plt.ylabel('Loss (MSE)')
    plt.legend()
    plt.grid(True)
    plt.show()

# Code to visualize the model architecture
def plot_nn_architecture(model):
    # Plotting the architecture of the model
    plot_model(model, to_file='model_architecture.png', show_shapes=True, show_layer_names=True)
    print("Model architecture plot saved as 'model_architecture.png'.")

# Code to plot the predicted vs actual function after evaluation
def plot_predicted_vs_actual(model, X_test, y_test):
    y_pred = model.predict(X_test)
    plt.figure(figsize=(10, 6))
    
    # Plot the actual vs predicted positions for x, y, z
    for i, label in enumerate(['X', 'Y', 'Z']):
        plt.subplot(1, 3, i + 1)
        plt.scatter(y_test[:, i], y_pred[:, i], alpha=0.5)
        plt.xlabel(f'True {label}')
        plt.ylabel(f'Predicted {label}')
        plt.title(f'{label} - True vs Predicted')
        plt.grid(True)

    plt.tight_layout()
    plt.show()

# Assuming you have already trained the model and stored the history object, 
# you can call these functions as follows:

plot_training_history(history)  # To plot training and validation loss
plot_nn_architecture(model)     # To plot and save the architecture
plot_predicted_vs_actual(model, X_test, y_test)  # To plot predicted vs actual results


# Define Gaussian function for fitting
def gaussian_1d(x, A, mu, sigma):
    return A * np.exp(-(x - mu)**2 / (2 * sigma**2))

# Function to plot residual histograms and fit Gaussian
def plot_residual_histograms(y_test, y_pred):
    residuals = y_test - y_pred  # Calculating residuals

    fig, axes = plt.subplots(3, 1, figsize=(8, 12))
    
    for i, label in enumerate(['X', 'Y', 'Z']):
        try:
            counts, bins, _ = axes[i].hist(residuals[:, i], bins=150, alpha=0.75)
            bin_centers = (bins[:-1] + bins[1:]) / 2  # Get bin centers for fitting
            popt, _ = curve_fit(gaussian_1d, bin_centers, counts, p0=[np.max(counts), np.mean(residuals[:, i]), np.std(residuals[:, i])])
            x_values = np.linspace(min(residuals[:, i]), max(residuals[:, i]), 1000)
            axes[i].plot(x_values, gaussian_1d(x_values, *popt), 'r-', label=f'Fitted Gaussian:\nA={popt[0]:.1f},\
                         \nmu={popt[1]:.1f},\nsigma={popt[2]:.1f}\nResolution={popt[2]/10/ np.sqrt(2):.1f} cm')
        except Exception as e:
            axes[i].text(0.5, 0.9, 'Fit did not work', transform=axes[i].transAxes, color='red', fontsize=12, ha='center')
            print(f"Fit failed for Residual {label}: {e}")
        axes[i].set_xlabel(f'Residual {label}')
        axes[i].set_ylabel('Frequency')
        axes[i].set_title(f'Histogram of Residuals in {label}')
        axes[i].legend()

    plt.tight_layout()
    plt.show()


# Usage after neural network evaluation
y_pred = model.predict(X_test)
plot_residual_histograms(y_test, y_pred)

from scipy.interpolate import griddata

def plot_residual_xy_contour(y_test, residuals):
    x_real = y_test[:, 0]  # X
    y_real = y_test[:, 1]  # Y
    z_residual = np.sqrt(residuals[:, 0]**2 + residuals[:, 1]**2)  # Residuals in X + Y

    # Create a 2D grid of x_real and y_real values (with less heavy interpolation)
    grid_x, grid_y = np.meshgrid(
        np.linspace(min(x_real), max(x_real), 20),
        np.linspace(min(y_real), max(y_real), 20)
    )

    # Interpolate z_residual values onto the 2D grid
    grid_z = griddata((x_real, y_real), z_residual, (grid_x, grid_y), method='linear')

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

# Usage after calculating residuals
residuals = y_test - y_pred
plot_residual_xy_contour(y_test, residuals)




