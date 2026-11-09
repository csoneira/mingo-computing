import numpy as np
import matplotlib.pyplot as plt


import matplotlib.pyplot as plt
import os
from PyPDF2 import PdfMerger
from scipy.stats import norm

global output_order
output_order = 1


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
    # ax.set_aspect("equal")
    ax.set_facecolor('#440454')
    ax.set_title(f"Fig. {output_order}, {title}, {len(xdat)} counts")
    plt.colorbar(label='Counts')
    
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    output_order = output_order + 1
    plt.show(); plt.close()
    return

def hist_1d(vdat, vbins, title, axis_label, name_of_file):
    global output_order
    # plt.close()
    v=(8,5)
    fig = plt.figure(figsize=v)
    ax = fig.add_subplot(1, 1, 1)
    
    vdat = vdat[ (vdat > vbins[0]) & (vdat < vbins[-1]) ]
    
    bin_number = len(vbins)
    
    # Plot histograms on the single axis
    ax.hist(vdat, bins=bin_number, alpha=0.5, color="red", \
            label=f"All hits, {len(vdat)} events", density = False)
    ax.legend()
    # ax.set_xlim(-5, x_axes_limit_plots)
    ax.set_title(f"Fig. {output_order}, {title}")
    plt.xlabel(axis_label)
    plt.ylabel("Counts")
    # plt.xlim([log_low_lim_fig, None])
    # plt.xscale("log"); plt.yscale("log");
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    output_order = output_order + 1
    plt.show(); plt.close()
    return

def hist_1d_log(vdat, vbins, title, axis_label, name_of_file):
    global output_order
    # plt.close()
    v=(8,5)
    fig = plt.figure(figsize=v)
    ax = fig.add_subplot(1, 1, 1)
    
    vdat = vdat[ (vdat > vbins[0]) & (vdat < vbins[-1]) ]
    
    bin_number = len(vbins)
    
    # Plot histograms on the single axis
    ax.hist(vdat, bins=bin_number, alpha=0.5, color="red", \
            label=f"All hits, {len(vdat)} events", density = False)
    ax.legend()
    # ax.set_xlim(-5, x_axes_limit_plots)
    ax.set_title(f"Fig. {output_order}, {title}")
    plt.xlabel(axis_label)
    plt.ylabel("Counts")
    # plt.xlim([log_low_lim_fig, None])
    # plt.xscale("log");
    plt.yscale("log");
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    output_order = output_order + 1
    plt.show(); plt.close()
    return

def hist_1d_log_log(vdat, vbins, title, axis_label, name_of_file):
    global output_order
    # plt.close()
    v=(8,5)
    fig = plt.figure(figsize=v)
    ax = fig.add_subplot(1, 1, 1)
    
    bin_number = len(vbins)
    
    # Plot histograms on the single axis
    ax.hist(vdat, bins=bin_number, alpha=0.5, color="red", \
            label=f"All hits, {len(vdat)} events", density = False)
    ax.legend()
    # ax.set_xlim(-5, x_axes_limit_plots)
    ax.set_title(f"Fig. {output_order}, {title}")
    plt.xlabel(axis_label)
    plt.ylabel("Counts")
    # plt.xlim([log_low_lim_fig, None])
    plt.xscale("log");
    plt.yscale("log");
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    output_order = output_order + 1
    plt.show(); plt.close()
    return


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
    # ax.set_aspect("equal")
    ax.set_facecolor('#440454')
    ax.set_title(f"Fig. {output_order}, {title}, {len(xdat)} counts")
    plt.colorbar(label='Counts')
    
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    output_order = output_order + 1
    plt.show(); plt.close()
    return

def hist_2d_hex_equal(xdat, ydat, x_bins, y_bins, title, x_label, y_label, name_of_file):
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
    ax.set_aspect("equal")
    ax.set_facecolor('#440454')
    ax.set_title(f"Fig. {output_order}, {title}, {len(xdat)} counts")
    plt.colorbar(label='Counts')
    
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    output_order = output_order + 1
    plt.show(); plt.close()
    return

# hist_2d_hex(slow, vcharge, x_bins, y_bins,  title, x_label, y_label, f"{name_of_file}_hist")


def scatter_2d(xdat, ydat, title, x_label, y_label, name_of_file):
    global output_order
    
    plt.close()
    
    # fig = plt.figure(figsize=(8, 5))  # Use plt.subplots() to create figure and axis
    plt.figure(figsize=(8, 5))  # Use plt.subplots() to create figure and axis
    
    plt.scatter(xdat, ydat, s=1)
    plt.title(f"Fig. {output_order}, {title}")
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    # plt.axis("equal")
    
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    plt.show()
    plt.close()
    output_order = output_order + 1
    return

def scatter_2d_deltas(xdat, ydat, title, x_label, y_label, name_of_file):
    global output_order
    
    xlim_val = 1600
    ylim_val = 1000
    
    plt.figure(figsize=(5, 5))  # Set figure size explicitly to ensure aspect ratio is respected
    
    xdat = abs(xdat)
    ydat = abs(ydat)
    
    cond = (xdat < xlim_val) & (ydat < ylim_val)  # Adjusted condition
    xdat = xdat[cond]
    ydat = ydat[cond]
    
    plt.scatter(xdat, ydat, s=1)
    plt.title(f"Fig. {output_order}, {title}")
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    xlim = [-5, xlim_val]
    ylim = [-5, ylim_val]
    plt.xlim(xlim)
    plt.ylim(ylim)
    # plt.axis("equal")
    
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    plt.show()
    plt.close()

    output_order += 1  # Incrementing output order
    return

def scatter_slew_2d(xdat, ydat, title, x_label, y_label, name_of_file):
    global output_order
    
    plt.close()
    
    cond = (abs(xdat) < 0.4) & (ydat < 75)
    xdat = xdat[ cond ]
    ydat = ydat[ cond ]
    
    # fig = plt.figure(figsize=(8, 5))  # Use plt.subplots() to create figure and axis
    plt.figure(figsize=(8, 5))  # Use plt.subplots() to create figure and axis
    
    plt.scatter(xdat, ydat, s=1)
    plt.title(f"Fig. {output_order}, {title}")
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    # plt.axis("equal")
    
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    plt.show()
    plt.close()
    output_order = output_order + 1
    return

def scatter_2d_equal(xdat, ydat, title, x_label, y_label, name_of_file):
    global output_order
    
    plt.close()
    
    # fig = plt.figure(figsize=(8, 5))  # Use plt.subplots() to create figure and axis
    plt.figure(figsize=(8, 5))  # Use plt.subplots() to create figure and axis
    
    plt.scatter(xdat, ydat, s=1)
    plt.title(f"Fig. {output_order}, {title}")
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.axis("equal")
    
    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    plt.show()
    plt.close()
    output_order = output_order + 1
    return

def summary(vector):
    if len(vector) < 100:
        # print("Not enough events.")
        return np.nan
    
    # Calculate the 5th and 95th percentiles
    try:
        percentile_left = np.percentile(vector, 20)
        percentile_right = np.percentile(vector, 80)
    except IndexError:
        print("Gave issue:")
        print(vector)
        
    # Filter values inside the 5th and 95th percentiles
    vector = [x for x in vector if percentile_left <= x <= percentile_right]
    
    value = np.nanmean(vector)
    return value

def hist_1d_fit(vdat, bin_number, title, axis_label, name_of_file):
    global output_order
    v = (8, 5)
    fig = plt.figure(figsize=v)
    ax = fig.add_subplot(1, 1, 1)

    # Plot histogram
    n, bins, patches = ax.hist(vdat, bins=bin_number, alpha=0.5, color="red",
                               label=f"All hits, {len(vdat)} events", density=False)
    ax.legend()

    # Fit Gaussian
    bin_centers = 0.5 * (bins[:-1] + bins[1:])
    fit_params = norm.fit(vdat)
    mu, std = fit_params
    p = norm.pdf(bin_centers, mu, std)
    # Scale Gaussian to match histogram count
    scale_factor = np.sum(n) / np.sum(p)
    ax.plot(bin_centers, scale_factor * p, 'k', linewidth=2, label=f'Gaussian Fit: μ={mu:.2f}, σ={std:.2f}')

    ax.set_title(f"Fig. {output_order}, {title}")
    plt.xlabel(axis_label)
    plt.ylabel("Counts")
    plt.legend()

    plt.tight_layout()
    plt.savefig(f"{output_order}_{name_of_file}.pdf", format="pdf")
    output_order += 1
    plt.show()
    plt.close()
   
    


# Load data from file
# filename = 'naive_deltas.txt'
filename = "naive_deltas_lead.txt"
data = np.loadtxt(filename)

# Separate data into four cases based on the first value
cases = {}
for i in range(1, 5):
    cases[i] = data[data[:, 1] == i][:, 1:]

# Calculate product of second and third components for each case
product_cases = {}
for i in range(1, 5):
    # product = cases[i][:, 1] * cases[i][:, 2]
    product = cases[i][:, 1]
    # product = cases[i][:, 1]
    product_cases[i] = product[(product < 1000) & (product != 0)]

# Plot the product for each case with different colors in the same plot
plt.figure(figsize=(10, 6))

colors = ['blue', 'red', 'green', 'orange']
labels = ['T1', 'T2', 'T3', 'T4']

density_cond = False
for i in range(1, 5):
    plt.hist(product_cases[i], bins=400, color=colors[i-1], alpha=0.7, label=labels[i-1], density=density_cond, histtype='step')

plt.xlabel('$\Delta X$ / mm')
plt.ylabel('Frequency')
# plt.yscale('log')  # Set y-axis to logarithmic scale
# plt.ylim(bottom=1)  # Set minimum y-axis limit to 1 to avoid log(0)
plt.xlim([-5,75])
plt.title('$\Delta X$ directly from difference in position in different strips')
plt.legend()

plt.tight_layout()
plt.show()






import numpy as np
import matplotlib.pyplot as plt

# Load data from file
filename1 = "naive_deltas.txt"
filename2 = "naive_deltas_lead.txt"
data1 = np.loadtxt(filename1)
data2 = np.loadtxt(filename2)

# Separate data into four cases based on the first value
cases1 = {}
cases2 = {}
for i in range(1, 5):
    cases1[i] = data1[data1[:, 1] == i][:, 1:]
    cases2[i] = data2[data2[:, 1] == i][:, 1:]

# Calculate product of second and third components for each case
product_cases1 = {}
product_cases2 = {}
for i in range(1, 5):
    product1 = cases1[i][:, 1]
    product_cases1[i] = product1[(product1 < 1000) & (product1 != 0)]
    
    product2 = cases2[i][:, 1]
    product_cases2[i] = product2[(product2 < 1000) & (product2 != 0)]

# Plot the product for each case with different colors in two subplots
fig, axs = plt.subplots(1, 2, figsize=(14, 6))

colors = ['blue', 'red', 'green', 'orange']
labels = ['T1', 'T2', 'T3', 'T4']

density_cond = False
for i in range(1, 5):
    axs[0].hist(product_cases1[i], bins=250, color=colors[i-1], alpha=0.7, label=labels[i-1], density=density_cond, histtype='step')
    axs[1].hist(product_cases2[i], bins=250, color=colors[i-1], alpha=0.7, label=labels[i-1], density=density_cond, histtype='step')

axs[0].set_xlabel('$\Delta X$ / mm')
axs[0].set_ylabel('Frequency')
axs[0].set_xlim([-5,75])
axs[0].set_title('$\Delta X$ directly from difference in position in different strips - File 1')
axs[0].legend()

axs[1].set_xlabel('$\Delta X$ / mm')
axs[1].set_ylabel('Frequency')
axs[1].set_xlim([-5,75])
axs[1].set_title('$\Delta X$ directly from difference in position in different strips - File 2')
axs[1].legend()

plt.tight_layout()
plt.show()





import numpy as np
import matplotlib.pyplot as plt
import warnings

# Load data from files
filename1 = "naive_deltas.txt"
filename2 = "naive_deltas_lead.txt"
data1 = np.loadtxt(filename1)
data2 = np.loadtxt(filename2)

# Separate data into four cases based on the first value
cases1 = {}
cases2 = {}
for i in range(1, 5):
    cases1[i] = data1[data1[:, 1] == i][:, 1:]
    cases2[i] = data2[data2[:, 1] == i][:, 1:]

# Calculate product of second and third components for each case
product_cases1 = {}
product_cases2 = {}
for i in range(1, 5):
    product1 = cases1[i][:, 1]
    product_cases1[i] = product1[(product1 < 1000) & (product1 != 0)]
    
    product2 = cases2[i][:, 1]
    product_cases2[i] = product2[(product2 < 1000) & (product2 != 0)]

# Suppressing runtime warning
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Create four subplots
fig, axs = plt.subplots(2, 2, figsize=(14, 10))

colors = ['blue', 'red', 'green', 'orange']
labels = ['T1', 'T2', 'T3', 'T4']

norm_cond = True
bin_number = 100

for i in range(1, 5):
    row = (i - 1) // 2
    col = (i - 1) % 2
    
    axs[row, col].hist(product_cases1[i], bins=bin_number, color='blue', alpha=0.5, label='Thin lead', density=norm_cond, histtype='step')
    axs[row, col].hist(product_cases2[i]+0.05, bins=bin_number, color='red', alpha=0.5, label='Thick lead', density=norm_cond, histtype='step')
    
    axs[row, col].set_xlabel('$\Delta X$ / mm')
    axs[row, col].set_ylabel('Frequency')
    # axs[row, col].set_xlim([-5, 100])
    # axs[row, col].set_ylim([0, 0.055])
    axs[row, col].set_title(f'{labels[i-1]} Comparison')
    axs[row, col].legend()

plt.suptitle("$\Delta X\cdot$ fired strips")
plt.tight_layout()
plt.show()



# -------------------------------------------------------------------------------


# Determine the maximum number of events and values within each event
max_events = int(np.max(data[:, 0]))
max_values = int(np.max(data[:, 1]))

# Initialize matrix with zeros
matrix = np.zeros((max_events, max_values * 2))

# Fill the matrix with values from the data file
for row in data:
    event_num = int(row[0]) - 1  # Adjust index to start from 0
    value_num = int(row[1]) - 1  # Adjust index to start from 0
    matrix[event_num, value_num * 2: value_num * 2 + 2] = row[2:]

columns_to_process = np.array([0, 2, 4, 6])
mean_diffs = []
diffs_12 = []
diffs_23 = []
diffs_34 = []
diffs_14 = []
diff_big = []
for row in matrix:
    diffs = np.mean(np.diff(row[columns_to_process]))
    diffs_1 = row[columns_to_process][1] - row[columns_to_process][0]  # Difference between T1 and T2
    diffs_2 = row[columns_to_process][1] - row[columns_to_process][0]  # Difference between T2 and T3
    diffs_3 = row[columns_to_process][2] - row[columns_to_process][0]  # Difference between T3 and T4
    diffs_4 = row[columns_to_process][3] - row[columns_to_process][0]  # Difference between T1 and T4
    if diffs != 0:
        mean_diffs.append(np.mean(diffs))
        diffs_12.append(np.mean(diffs_1))
        diffs_23.append(np.mean(diffs_2))
        diffs_34.append(np.mean(diffs_3))
        diffs_14.append(np.mean(diffs_4))
        
        diff_big.append(row[columns_to_process])

# Filter out zero and extreme values
filter_value = 50
filtered_diffs_12 = [val for val in diffs_12 if val != 0 and val > -filter_value and val < filter_value]
filtered_diffs_23 = [val for val in diffs_23 if val != 0 and val > -filter_value and val < filter_value]
filtered_diffs_34 = [val for val in diffs_34 if val != 0 and val > -filter_value and val < filter_value]
filtered_diffs_14 = [val for val in diffs_14 if val != 0 and val > -filter_value and val < filter_value]

# Plot histograms of filtered differences
bin_number = 150
norm_cond = False
plt.figure(figsize=(10, 6))
# plt.hist(filtered_diffs_12, bins=bin_number, color='red', alpha=0.5, density=norm_cond, histtype='step', label='Differences between T1 and T2')
plt.hist(filtered_diffs_23, bins=bin_number, color='green', alpha=0.5, density=norm_cond, histtype='step', label='Differences between T1 and T2')
plt.hist(filtered_diffs_34, bins=bin_number, color='blue', alpha=0.5, density=norm_cond, histtype='step', label='Differences between T1 and T3')
plt.hist(filtered_diffs_14, bins=bin_number, color='orange', alpha=0.5, density=norm_cond, histtype='step', label='Differences between T1 and T4')

plt.xlabel('Difference')
plt.ylabel('Frequency')
plt.title('Histogram of Differences')
plt.legend()  # Show legend with labels
plt.grid(True)
plt.tight_layout()
plt.show()



delt = np.array(diff_big)

# # Promising ------------------------------------
# xdat = np.std(delt, axis = 1)
# ydat = np.std(np.diff(delt, axis = 1), axis = 1)

# xdat = np.std(delt, axis = 1)
# ydat = np.mean(np.diff(delt, axis = 1), axis = 1)

# xdat = np.mean(delt, axis = 1)
# ydat = np.mean(np.diff(delt, axis = 1), axis = 1)

# xdat = np.mean(delt, axis = 1)
# ydat = np.std(np.diff(delt, axis = 1), axis = 1)

xdat = np.mean(delt, axis = 1)
ydat = np.std(delt, axis = 1)

# xdat = np.diff(delt, axis = 1)[:,2]
# ydat = np.diff(delt, axis = 1)[:,2]
# ydat = np.array(delt[:,0])

# xdat = np.mean(delt, axis = 1)
# ydat = np.max(delt, axis = 1)

# xdat = np.mean(delt, axis = 1)
# xdat = np.diff(delt, axis = 1)[:,0]
# ydat = np.diff(delt, axis = 1)[:,1]
# ----------------------------------------------

show_plots = True
bins_delta_tests = np.linspace(-160, 160, 100)
cond = True
# cond = (xdat < 15) & (ydat < 25)
cond = cond & (xdat != 0) & (ydat != 0)
xdat = xdat[ cond ]
ydat = ydat[ cond ]
if show_plots:
    hist_1d(xdat, bins_delta_tests, f"...", "...", "...")
    hist_1d(ydat, bins_delta_tests, f"...", "...", "...")
    
    scatter_2d(xdat, ydat, f"...", "...", "...", "scatter_spreads")
    
    scatter_2d(xdat, ydat, f"...", "...", "...", "scatter_spreads")
    hist_2d_hex(xdat, ydat, bins_delta_tests, bins_delta_tests, f"...", "...", "...", "hex_hist_spreads")












import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares

# Define a function for the sum of three Gaussian distributions truncated at 0
def sum_of_gaussians(params, x):
    a1, mu1, sigma1, a2, mu2, sigma2, a3, mu3, sigma3 = params
    gauss1 = np.maximum(a1 * np.exp(-(x - mu1)**2 / (2 * sigma1**2)), 0)
    gauss2 = np.maximum(a2 * np.exp(-(x - mu2)**2 / (2 * sigma2**2)), 0)
    gauss3 = np.maximum(a3 * np.exp(-(x - mu3)**2 / (2 * sigma3**2)), 0)
    return gauss1, gauss2, gauss3, gauss1 + gauss2 + gauss3

# Filter mean differences
mean_diffs = np.array(mean_diffs)
v = mean_diffs[np.abs(mean_diffs) < 50]

# Calculate histogram
hist, bin_edges = np.histogram(v, bins=300, density=True)

# Calculate bin centers
bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

# Initial guess for parameters
initial_guess = [0.075, -2, 6,
                 0.048, 1, 6,
                 0.001, 0, 20]

# Bounds for parameters
bounds = ([0.07, -5, 0,
           0.045, 0, 0,
           0, -5, 15],
          [0.08, 0, 50,
           0.05, 2, 50,
           0.01, 5, 23])

# Define residual function for least squares
def residual(params):
    gauss1, gauss2, gauss3, sum_of_gaussians_fit = sum_of_gaussians(params, bin_centers)
    return hist - sum_of_gaussians_fit

# Fit the data using least squares
result = least_squares(residual, initial_guess, bounds=bounds)

# Get the fitted parameters
popt = result.x

# Calculate the individual Gaussian components and their sum
gauss1, gauss2, gauss3, sum_of_gaussians_fit = sum_of_gaussians(popt, bin_centers)

# Format the fitted parameters for display in the legend
params_str = [f'Gaussian 1: a={popt[0]:.2f}, mu={popt[1]:.2f}, sigma={popt[2]:.2f}',
              f'Gaussian 2: a={popt[3]:.2f}, mu={popt[4]:.2f}, sigma={popt[5]:.2f}',
              f'Gaussian 3: a={popt[6]:.2f}, mu={popt[7]:.2f}, sigma={popt[8]:.2f}']

# Plot the histogram and the individual Gaussian components
plt.figure(figsize=(10, 6))
plt.hist(v, bins=300, color='blue', alpha=0.7, density=True, label='Histogram')
plt.plot(bin_centers, gauss1, 'r--', label=params_str[0])
plt.plot(bin_centers, gauss2, 'g--', label=params_str[1])
plt.plot(bin_centers, gauss3, 'b--', label=params_str[2])
plt.plot(bin_centers, sum_of_gaussians_fit, 'k-', label='Fitted Curve')
plt.xlabel('Mean Difference')
plt.ylabel('Frequency (Normalized)')
plt.title('Histogram of Mean Differences and Fitted Curve')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()












# Define a function for the sum of three truncated Gaussian distributions
def sum_of_truncated_gaussians(params, x):
    a1, mu1, sigma1, a2, mu2, sigma2, a3, mu3, sigma3, left_trunc1, right_trunc1, left_trunc2, right_trunc2 = params
    gauss1 = a1 * truncated_gaussian(x, mu1, sigma1, left_trunc1, right_trunc1)
    gauss2 = a2 * truncated_gaussian(x, mu2, sigma2, left_trunc2, right_trunc2)
    gauss3 = a3 * gaussian(x, mu3, sigma3)
    return gauss1, gauss2, gauss3, gauss1 + gauss2 + gauss3

# Define a truncated Gaussian function
def truncated_gaussian(x, mu, sigma, left_trunc, right_trunc):
    # Calculate the standard Gaussian distribution
    gaussian = 1 / (sigma * np.sqrt(2 * np.pi)) * np.exp(-0.5 * ((x - mu) / sigma)**2)
    # Truncate the distribution at the specified points
    gaussian[(x - mu) < left_trunc] = 0
    gaussian[(x - mu) > right_trunc] = 0
    return gaussian

# Define a standard Gaussian function
def gaussian(x, mu, sigma):
    return 1 / (sigma * np.sqrt(2 * np.pi)) * np.exp(-0.5 * ((x - mu) / sigma)**2)


# Calculate histogram
hist, bin_edges = np.histogram(v, bins=300, density=True)

# Calculate bin centers
bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

# Initial guess for parameters
initial_guess = [0.3, -5, 10,
                 0.3, 5, 10,
                 0.01, 0, 20,
                 -50, 0,
                 0, 50]

# Bounds for parameters
bounds = ([0, -50, 0,
           0, 0, 0,
           0, -50, 0,
           -100, -50,
           -100, 0],
          [1, 50, 50,
           1, 5, 50,
           0.02, 50, 50,
           100, 0,
           0, 50])

# Define residual function for least squares
def residual(params):
    gauss1, gauss2, gauss3, sum_of_gaussians_fit = sum_of_truncated_gaussians(params, bin_centers)
    return hist - sum_of_gaussians_fit

# Fit the data using least squares
result = least_squares(residual, initial_guess, bounds=bounds)

# Get the fitted parameters
popt = result.x

# Calculate the individual Gaussian components and their sum
gauss1, gauss2, gauss3, sum_of_gaussians_fit = sum_of_truncated_gaussians(popt, bin_centers)

# Plot the histogram and the individual Gaussian components
plt.figure(figsize=(10, 6))
plt.hist(v, bins=300, color='blue', alpha=0.7, density=True, label='Histogram')
plt.plot(bin_centers, gauss1, 'r--', label='Gaussian 1')
plt.plot(bin_centers, gauss2, 'g--', label='Gaussian 2')
plt.plot(bin_centers, gauss3, 'b--', label='Gaussian 3')
plt.plot(bin_centers, sum_of_gaussians_fit, 'k-', label='Fitted Curve')
plt.xlabel('Mean Difference')
plt.ylabel('Frequency (Normalized)')
plt.title('Histogram of Mean Differences and Fitted Curve')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
