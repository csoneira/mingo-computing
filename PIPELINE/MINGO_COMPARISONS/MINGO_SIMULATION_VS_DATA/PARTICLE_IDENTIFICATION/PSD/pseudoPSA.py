#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Mar  4 14:11:04 2024

@author: cayesoneira
"""

globals().clear()

import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3D
from scipy.ndimage import gaussian_filter
from PyPDF2 import PdfMerger
import time
import shutil
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Image, Table, TableStyle
from reportlab.lib import colors
import numpy as np

from scipy.optimize import curve_fit

figures = False
show_plot = False
global output_order
output_order = 0

def hist_2d_hex(xdat, ydat, x_bins, y_bins, title, x_label, y_label, name_of_file):
    global output_order
    
    # print("xdat dimension:", xdat.shape)
    # print("ydat dimension:", ydat.shape)
    
    # Filtering ydat based on xdat
    ydat_filt = ydat[(xdat > x_bins[0]) & (xdat < x_bins[-1])]
    xdat_filt = xdat[(xdat > x_bins[0]) & (xdat < x_bins[-1])]
    ydat_filt_filt = ydat_filt[(ydat_filt > y_bins[0]) & (ydat_filt < y_bins[-1])]
    xdat_filt_filt = xdat_filt[(ydat_filt > y_bins[0]) & (ydat_filt < y_bins[-1])]
    
    xdat = xdat_filt_filt
    ydat = ydat_filt_filt
    
    hex_grid = int( 2/3 * np.sqrt( len(x_bins) * len(y_bins) ) )
    
    fig, ax = plt.subplots(figsize=(8, 5))
    # plt.hexbin(xdat, ydat, gridsize=hex_grid, cmap='viridis', marginals = True)
    plt.hexbin(xdat, ydat, gridsize=hex_grid, cmap='viridis')
    
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_facecolor('#440454')
    ax.set_title(f"Fig. {output_order}, {title}, {len(xdat)} counts")
    plt.colorbar(label='Counts')
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    output_order = output_order + 1
    plt.show(); plt.close()
    return


PSA = []
with open('charge_per_event_only_muons.dat', "rb") as file:
    while True:
        try:
            event = np.load(file)
            PSA.append(event)
        except ValueError:
            break  # Reached end of file

print(f"{len(PSA)} events to analyze.")

PSA = np.array(PSA)
matrix = PSA

fit_parameters = []
residues = []
charge_0 = 0

# Plotting
for i in range(matrix.shape[0]):  # Iterate over each row
    x = np.array([0, 100, 200, 400])  # X values are z in mm
    # x = np.array([1, 2, 3, 4])  # X values are z in mm
    y = matrix[i]  # Y values are the values in the current row
    
    if np.any(y == 0):
        charge_0 += 1
        continue
    
    def fit_function(x, a, b, c, d):
        return d * x**3 + c * x**2 + b * x + a
    
    popt, _ = curve_fit(fit_function, x, y)  # Fit data to fit_function
    fit_parameters.append(popt)  # Save fit parameters
    
    res = np.sum( (y - fit_function(x, *popt) )**2 )
    residues.append(res)
    
    if figures:
        # x_fit = np.linspace(x[0]-10, x[-1]+10)
        x_fit = np.linspace(x[0], x[-1])

        plt.plot(x, y, marker='o', alpha = 0.3, label=f'Row {i+1}')  # Plotting each row
        plt.plot(x_fit, fit_function(x_fit, *popt), alpha = 0.3, label=f'Fit {i//4 + 1}')
        
        plt.ylim([0, 80])
        plt.legend()
        plt.grid()
        plt.show()  # Show the plot for every 4th row or last row

# plt.grid()
# plt.show()  # Show the plot for every 4th row or last row

print(f"{charge_0} events had one layer with 0.")


# Convert fit_parameters to numpy array for further processing
fit_parameters = np.array(fit_parameters)
residues = np.array(residues)
print("Fit Parameters:")
# print(fit_parameters)

bin_number = 100

# Histograms for the fitted parameters
plt.figure(figsize=(15, 8))

plt.subplot(2, 2, 1)
plt.grid()
plt.hist(fit_parameters[:, 0], bins=bin_number, alpha=0.75)
plt.legend([f'Mean: {np.mean(fit_parameters[:, 0]):.2g}\nStd: {np.std(fit_parameters[:, 0]):.2g}\nMedian: {np.median(fit_parameters[:, 0]):.2g}'])
plt.xlabel('Parameter a')
plt.ylabel('Frequency')

plt.subplot(2, 2, 2)
plt.grid()
plt.hist(fit_parameters[:, 1], bins=bin_number, alpha=0.75)
plt.legend([f'Mean: {np.mean(fit_parameters[:, 1]):.2g}\nStd: {np.std(fit_parameters[:, 1]):.2g}\nMedian: {np.median(fit_parameters[:, 1]):.2g}'])
plt.xlabel('Parameter b')
plt.ylabel('Frequency')

plt.subplot(2, 2, 3)
plt.grid()
plt.hist(fit_parameters[:, 2], bins=bin_number, alpha=0.75)
plt.legend([f'Mean: {np.mean(fit_parameters[:, 2]):.2g}\nStd: {np.std(fit_parameters[:, 2]):.2g}\nMedian: {np.median(fit_parameters[:, 2]):.2g}'])
plt.xlabel('Parameter c')
plt.ylabel('Frequency')

plt.subplot(2, 2, 4)
plt.grid()
plt.hist(fit_parameters[:, 3], bins=bin_number, alpha=0.75)
plt.legend([f'Mean: {np.mean(fit_parameters[:, 3]):.2g}\nStd: {np.std(fit_parameters[:, 3]):.2g}\nMedian: {np.median(fit_parameters[:, 3]):.2g}'])
plt.xlabel('Parameter d')
plt.ylabel('Frequency')

# Create a legend
plt.suptitle("Parameters in $y = a + b \cdot x + c \cdot x^{2} + d \cdot x^{3}$")

plt.tight_layout()
plt.show()


# Scatter now --------------------
# Histograms for the fitted parameters
plt.figure(figsize=(15, 8))
plt.scatter(fit_parameters[:, 0], fit_parameters[:, 1], s=1)
plt.tight_layout()
plt.show()

x_bins = np.linspace(-10, 100, 150)
y_bins = np.linspace(-10, 100, 150)
hist_2d_hex(fit_parameters[:, 0], fit_parameters[:, 1], x_bins, y_bins, "title", "Residues", "a parameter", "name_of_file")


# a parameter
plt.figure(figsize=(15, 8))
plt.scatter(residues, fit_parameters[:, 0], s=5)
plt.xlim([-10, 1000])
plt.ylim([0, 50])
plt.tight_layout()
plt.show()

x_bins = np.linspace(-10, 100, 150)
y_bins = np.linspace(0, 50, 150)
hist_2d_hex(residues, fit_parameters[:, 0], x_bins, y_bins, "title", "Residues", "a parameter", "name_of_file")


x_bins = np.linspace(-10, 100, 150)
y_bins = np.linspace(-0.1, 0.1, 150)
hist_2d_hex(residues, fit_parameters[:, 1], x_bins, y_bins, "title", "Residues", "b parameter", "name_of_file")


# -----------------------------------------------------------------------------

# figures = True

# Fitting parabolas

fit_parameters = []
residues = []
charge_0 = 0

# Plotting
for i in range(matrix.shape[0]):  # Iterate over each row
    x = np.array([0, 100, 200, 400])  # X values are z in mm
    y = matrix[i]  # Y values are the values in the current row
    
    if np.any(y == 0):
        charge_0 += 1
        continue
    
    def fit_function(x, a, b, c):
        return c * x**2 + b * x + a
    
    popt, _ = curve_fit(fit_function, x, y)  # Fit data to fit_function
    fit_parameters.append(popt)  # Save fit parameters
    
    res = np.sum( (y - fit_function(x, *popt) )**2 )
    residues.append(res)
    
    if figures:
        x_fit = np.linspace(x[0]-10, x[-1]+10)

        plt.plot(x, y, marker='o', alpha = 0.3, label=f'Row {i+1}')  # Plotting each row
        plt.plot(x_fit, fit_function(x_fit, *popt), alpha = 0.3, label=f'Fit {i//4 + 1}')
        
        plt.ylim([0, 80])
        plt.legend()
        plt.grid()
        plt.show()  # Show the plot for every 4th row or last row

# plt.grid()
# plt.show()  # Show the plot for every 4th row or last row

# figures = False


print(f"{charge_0} events had one layer with 0.")
# Convert fit_parameters to numpy array for further processing
fit_parameters = np.array(fit_parameters)
residues = np.array(residues)
print("Fit Parameters:")
# print(fit_parameters)

bin_number = 100

# Histograms for the fitted parameters
plt.figure(figsize=(15, 8))

plt.subplot(1, 3, 1)
plt.grid()
plt.hist(fit_parameters[:, 0], bins=bin_number, alpha=0.75)
plt.legend([f'Mean: {np.mean(fit_parameters[:, 0]):.2g}\nStd: {np.std(fit_parameters[:, 0]):.2g}\nMedian: {np.median(fit_parameters[:, 0]):.2g}'])
plt.xlabel('Parameter a')
plt.ylabel('Frequency')

plt.subplot(1, 3, 2)
plt.grid()
plt.hist(fit_parameters[:, 1], bins=bin_number, alpha=0.75)
plt.legend([f'Mean: {np.mean(fit_parameters[:, 1]):.2g}\nStd: {np.std(fit_parameters[:, 1]):.2g}\nMedian: {np.median(fit_parameters[:, 1]):.2g}'])
plt.xlabel('Parameter b')
plt.ylabel('Frequency')

plt.subplot(1, 3, 3)
plt.grid()
plt.hist(fit_parameters[:, 2], bins=bin_number, alpha=0.75)
plt.legend([f'Mean: {np.mean(fit_parameters[:, 2]):.2g}\nStd: {np.std(fit_parameters[:, 2]):.2g}\nMedian: {np.median(fit_parameters[:, 2]):.2g}'])
plt.xlabel('Parameter c')
plt.ylabel('Frequency')

# Create a legend
plt.suptitle("Parameters in $y = a + b \cdot x + c \cdot x^{2}$")

plt.tight_layout()
plt.show()


# Scatter now -----------------------------------------------------------------
# Histograms for the fitted parameters
plt.figure(figsize=(15, 8))
x = fit_parameters[:, 0]
y = fit_parameters[:, 1]
cond = ( -50 < x ) & ( x < 200 ) & ( -10 < y ) & ( y < 4 )
x = x[cond]
y = y[cond]
plt.scatter(x, y, s=3)
plt.tight_layout()
plt.show()


# a parameter
plt.figure(figsize=(15, 8))
plt.scatter(residues, fit_parameters[:, 0], s=5)
plt.xlim([-10, 1000])
plt.ylim([0, 50])
plt.tight_layout()
plt.show()

x_bins = np.linspace(-10, 10, 150)
y_bins = np.linspace(0, 50, 150)
hist_2d_hex(residues, fit_parameters[:, 0], x_bins, y_bins, "title", "Residues", "a parameter", "name_of_file")


x_bins = np.linspace(-10, 10, 150)
y_bins = np.linspace(-0.1, 0.1, 150)
hist_2d_hex(residues, fit_parameters[:, 1], x_bins, y_bins, "title", "Residues", "b parameter", "name_of_file")


x_bins = np.linspace(-10, 10, 150)
y_bins = np.linspace(-0.001, 0.001, 150)
plt.scatter(residues, fit_parameters[:, 2], s=1)
hist_2d_hex(residues, fit_parameters[:, 2], x_bins, y_bins, "title", "Residues", "c parameter", "name_of_file")







# -----------------------------------------------------------------------------

# Fitting lines
fit_parameters = []
residues = []
means = []
charge_0 = 0

# Plotting
for i in range(matrix.shape[0]):  # Iterate over each row
    x = np.array([0, 100, 200, 400])  # X values are z in mm
    y = matrix[i]  # Y values are the values in the current row
    
    if np.any(y == 0):
        charge_0 += 1
        continue
    
    means.append(np.mean(y))
    
    def fit_function(x, a, b):
        return b * x + a
    
    popt, _ = curve_fit(fit_function, x, y)  # Fit data to fit_function
    fit_parameters.append(popt)  # Save fit parameters
    
    res = np.sum( (y - fit_function(x, *popt) )**2 )
    residues.append(res)
    
    if figures:
        x_fit = np.linspace(x[0]-10, x[-1]+10)

        plt.plot(x, y, marker='o', alpha = 0.3, label=f'Row {i+1}')  # Plotting each row
        plt.plot(x_fit, fit_function(x_fit, *popt), alpha = 0.3, label=f'Fit {i//4 + 1}')
        
        plt.ylim([0, 80])
        plt.legend()
        plt.grid()
        plt.show()  # Show the plot for every 4th row or last row


print(f"{charge_0} events had one layer with 0.")
means = np.array(means)
residues = np.array(residues)
fit_parameters = np.array(fit_parameters)
# Create a legend
plt.suptitle("Parameters in $y = a + b \cdot x$")

plt.tight_layout()
plt.show()


# Histograms for the fitted parameters
plt.figure(figsize=(15, 8))

plt.subplot(2, 2, 1)
plt.grid()
plt.hist(fit_parameters[:, 0], bins=bin_number, alpha=0.75)
plt.legend([f'Mean: {np.mean(fit_parameters[:, 0]):.2g}\nStd: {np.std(fit_parameters[:, 0]):.2g}\nMedian: {np.median(fit_parameters[:, 0]):.2g}'])
plt.xlabel('Parameter a')
plt.ylabel('Frequency')

plt.subplot(2, 2, 2)
plt.grid()
plt.hist(fit_parameters[:, 1], bins=bin_number, alpha=0.75)
plt.legend([f'Mean: {np.mean(fit_parameters[:, 1]):.2g}\nStd: {np.std(fit_parameters[:, 1]):.2g}\nMedian: {np.median(fit_parameters[:, 1]):.2g}'])
plt.xlabel('Parameter b')
plt.ylabel('Frequency')

# Scatter now -----------------------------------------------------------------
# Histograms for the fitted parameters
plt.figure(figsize=(15, 8))
x = fit_parameters[:, 0]
y = fit_parameters[:, 1]
cond = ( -50 < x ) & ( x < 100 ) & ( -0.5 < y ) & ( y < 0.5 )
x = x[cond]
y = y[cond]
plt.scatter(x, y, s=3)
plt.grid()
plt.tight_layout()
plt.show()

plt.figure(figsize=(15, 8))
plt.scatter(residues, fit_parameters[:, 1], s=3)
plt.xlim([-10, 1000])
plt.ylim([-0.1, 0.1])
plt.tight_layout()
plt.show()

x_bins = np.linspace(-10, 1000, 150)
y_bins = np.linspace(-0.1, 0.1, 150)
hist_2d_hex(residues, fit_parameters[:, 1], x_bins, y_bins, "title", "x_label", "y_label", "name_of_file")


# a parameter
plt.figure(figsize=(15, 8))
plt.scatter(residues, fit_parameters[:, 0], s=5)
plt.xlim([-10, 1000])
plt.ylim([0, 50])
plt.tight_layout()
plt.show()

x_bins = np.linspace(-10, 1000, 150)
y_bins = np.linspace(0, 50, 150)
hist_2d_hex(residues, fit_parameters[:, 0], x_bins, y_bins, "title", "Residues", "a parameter", "name_of_file")



# mean charges
plt.figure(figsize=(15, 8))
plt.scatter(residues, means, s=5)
plt.xlim([-10, 1000])
plt.ylim([0, 100])
plt.tight_layout()
plt.show()

x_bins = np.linspace(-10, 1000, 150)
y_bins = np.linspace(0, 50, 150)
hist_2d_hex(residues, means, x_bins, y_bins, "title", "Residues", "a parameter", "name_of_file")


# b parameter
plt.figure(figsize=(15, 8))
plt.scatter(means, fit_parameters[:, 1], s=5)
plt.xlim([0, 100])
plt.ylim([-0.3, 0.3])
plt.tight_layout()
plt.show()

x_bins = np.linspace(0, 100, 150)
y_bins = np.linspace(-0.3, 0.3, 150)
hist_2d_hex(means, fit_parameters[:, 1], x_bins, y_bins, "title", "Residues", "a parameter", "name_of_file")


# a parameter
plt.figure(figsize=(15, 8))
plt.scatter(means, fit_parameters[:, 0], s=5)
plt.xlim([0, 100])
plt.ylim([0, 80])
plt.tight_layout()
plt.show()

x_bins = np.linspace(0, 100, 150)
y_bins = np.linspace(0, 80, 150)
hist_2d_hex(means, fit_parameters[:, 0], x_bins, y_bins, "title", "Residues", "a parameter", "name_of_file")
