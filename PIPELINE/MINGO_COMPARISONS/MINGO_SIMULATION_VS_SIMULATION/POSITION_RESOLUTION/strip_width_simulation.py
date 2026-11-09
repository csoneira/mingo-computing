import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# Gaussian function definition
def gaussian(x, A, mu, sigma):
    return A * np.exp(-((x - mu)**2) / (2 * sigma**2))

# Function to fit a Gaussian to sampled points with error handling
def fit_gaussian(x, y):
    try:
        # Provide better initial guesses for mu and sigma
        initial_guess = [np.max(y), np.mean(x), np.std(x)]
        popt, _ = curve_fit(gaussian, x, y, p0=initial_guess, maxfev=2000)
        return popt  # returns A, mu, sigma
    except RuntimeError as e:
        # Return None if fitting fails
        print(f"Fitting failed: {e}")
        return None

# Function to fit a Gaussian to histogram data
def fit_gaussian_histogram(data, bins):
    hist, bin_edges = np.histogram(data, bins=bins, density=True)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # Provide better initial guesses for A, mu, sigma
    p0 = [np.max(hist), np.mean(data), np.std(data)]

    try:
        popt, _ = curve_fit(gaussian, bin_centers, hist, p0=p0)
        return popt  # returns A, mu, sigma
    except RuntimeError as e:
        print(f"Fitting failed: {e}")
        return None

# Function to simulate and compute errors in mean and sigma
def simulate_gaussian(strip_width, induction_area, num_strips, num_events, epsilon):
    # Set up strip positions
    strip_positions = np.linspace(-strip_width * num_strips / 2, strip_width * num_strips / 2, num_strips + 1)  # Strip edges
    strip_centers = (strip_positions[:-1] + strip_positions[1:]) / 2  # Strip centers for fitting

    mean_errors = []
    sigma_errors = []

    # Simulate events
    for _ in range(num_events):
        # Random modulation of induction area
        current_sigma = induction_area * (1 + epsilon * (2 * np.random.rand() - 1))
        true_mean = np.random.uniform(-induction_area / 2, induction_area / 2)  # Random mean between -w/2 and w/2

        # Introduce the variation factor theta from 0.99 to 1.01
        theta = 0.99 + 0.02 * np.random.rand()

        # Randomly sample within each strip, but save as if sampled at strip center
        sampled_values = []
        for i in range(num_strips):
            # Random point inside the strip
            random_point_in_strip = np.random.uniform(strip_positions[i], strip_positions[i + 1])
            sampled_value = gaussian(random_point_in_strip, theta, true_mean, current_sigma)
            sampled_values.append(sampled_value)  # Store the height as if measured at the center

        # Fit the Gaussian to the sampled values
        params = fit_gaussian(strip_centers, sampled_values)

        # If fitting was successful, calculate the errors
        if params is not None:
            A_fit, mu_fit, sigma_fit = params
            mean_errors.append(mu_fit - true_mean)
            sigma_errors.append(sigma_fit - current_sigma)
        else:
            # Skip the event if fitting fails
            continue

    return mean_errors, sigma_errors


# Function to run the simulation for different strip widths and induction areas
def run_simulation(strip_widths, induction_areas, num_strips, num_events, epsilon):
    all_mean_errors = []
    all_sigma_errors = []
    labels = []

    # Simulate data
    for strip_width in strip_widths:
        for induction_area in induction_areas:
            mean_errors, sigma_errors = simulate_gaussian(strip_width, induction_area, num_strips, num_events, epsilon)
            all_mean_errors.append(mean_errors)
            all_sigma_errors.append(sigma_errors)
            labels.append(f"Strip width={strip_width}, Induction area={induction_area}")

    # Create subplots: each row will have a pair of subplots (mean and sigma errors)
    num_plots = len(strip_widths) * len(induction_areas)
    fig, axs = plt.subplots(num_plots, 2, figsize=(14, 6 * num_plots))

    for i, (mean_error, sigma_error) in enumerate(zip(all_mean_errors, all_sigma_errors)):
        # Fitting Gaussian to mean error data
        mean_fit_params = fit_gaussian_histogram(mean_error, bins=100)
        if mean_fit_params is not None:
            A_mean, mu_mean, sigma_mean = mean_fit_params
            label_mean = f"{labels[i]}\nFit: Position precision = {sigma_mean:.2f} cm"
            # label_mean = f"{labels[i]}\nFit: mu_error={mu_mean:.2f}, sigma_error={sigma_mean:.2f}"
        else:
            label_mean = f"{labels[i]}\nFit failed"

        # Plot mean error histogram and Gaussian fit
        ax_mean = axs[i, 0] if num_plots > 1 else axs[0]
        ax_mean.hist(mean_error, bins=100, alpha=0.5, density=True, label=label_mean)
        if mean_fit_params is not None:
            x_vals = np.linspace(min(mean_error), max(mean_error), 1000)
            ax_mean.plot(x_vals, gaussian(x_vals, *mean_fit_params), 'r-', lw=2)

        ax_mean.set_title("Mean Errors")
        ax_mean.set_xlabel("Mean Error")
        ax_mean.set_ylabel("Density")
        ax_mean.legend(loc='upper right')

        # Fitting Gaussian to sigma error data
        sigma_fit_params = fit_gaussian_histogram(sigma_error, bins=100)
        if sigma_fit_params is not None:
            A_sigma, mu_sigma, sigma_sigma = sigma_fit_params
            label_sigma = f"{labels[i]}\nFit: Position precision = {sigma_sigma:.2f} cm"
        else:
            label_sigma = f"{labels[i]}\nFit failed"

        # Plot sigma error histogram and Gaussian fit
        ax_sigma = axs[i, 1] if num_plots > 1 else axs[1]
        ax_sigma.hist(sigma_error, bins=100, alpha=0.5, density=True, label=label_sigma)
        if sigma_fit_params is not None:
            x_vals = np.linspace(min(sigma_error), max(sigma_error), 1000)
            ax_sigma.plot(x_vals, gaussian(x_vals, *sigma_fit_params), 'r-', lw=2)

        ax_sigma.set_title("Sigma Errors")
        ax_sigma.set_xlabel("Sigma Error")
        ax_sigma.set_ylabel("Density")
        ax_sigma.legend(loc='upper right')

    # Adjust layout and show the plots
    plt.tight_layout()
    plt.savefig('sim.png', format='png')
    plt.show()

# Parameters (example values, you can modify them)
strip_widths = [6.3]  # List of strip widths to test
induction_areas = [4.0]  # List of induction areas to test
num_strips = 10  # Number of strips
num_events = 10000  # Number of events per configuration
epsilon = 0  # Modulation factor for induction area

# Run the simulation
run_simulation(strip_widths, induction_areas, num_strips, num_events, epsilon)
