import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

show_plots = False
plot_trajectory = True

# Simulation parameters -------------------------------------------------------
num_angles = 100  # Adjust as needed
mesh_step = 10  # mm
mesh_range = 300  # mm it was 250
z_offset = 0
efficiency = True
# -----------------------------------------------------------------------------

# Define parameters
rpc_length = 300  # mm
half_rpc_length = rpc_length / 2
z_positions = np.array([0, 103, 206, 401]) + z_offset # mm

# Create mesh of points
x_points = np.arange(-mesh_range, mesh_range + mesh_step, mesh_step)
y_points = np.arange(-mesh_range, mesh_range + mesh_step, mesh_step)

# Function to check if a point (x, y) is inside an RPC module
def is_inside_rpc(x, y):
    return -half_rpc_length <= x <= half_rpc_length and -half_rpc_length <= y <= half_rpc_length

def is_inside_rpc_eff(x, y, eff):
    passes = -half_rpc_length <= x <= half_rpc_length and -half_rpc_length <= y <= half_rpc_length
    if passes:
        detected = np.random.binomial(n=1, p=eff)
        if detected ==1:
            return True
        else:
            return False
    else:
        return False 


# -----------------------------------------------------------------------------
if plot_trajectory:
    
    # Define constants and parameters
    plot_3d_scene_plane_x_min = -half_rpc_length
    plot_3d_scene_plane_x_max = half_rpc_length
    plot_3d_scene_plane_y_min = -half_rpc_length
    plot_3d_scene_plane_y_max = half_rpc_length
    plot_trajectories_xlim = (-mesh_range, mesh_range)
    plot_trajectories_ylim = (-mesh_range, mesh_range)
    plot_trajectories_zlim = (0, 450)
    
    # Function to plot the 3D scene
    def plot_3d_scene(origin, zenith_angles, azimuth_angles):
        """
        Plot in 3D the miniTRASGO with multiple lines originating from a single point.
        
        Parameters
        ----------
        origin : Three dimensional array of float64
            Origin point.
        zenith_angles : Array of float64
            Zenith angles of the trajectories.
        azimuth_angles : Array of float64
            Azimuth angles of the trajectories.
        
        Returns
        -------
        None.
        """
        plane_x_min = plot_3d_scene_plane_x_min
        plane_x_max = plot_3d_scene_plane_x_max
        plane_y_min = plot_3d_scene_plane_y_min
        plane_y_max = plot_3d_scene_plane_y_max
        
        # Generate points for the planes
        x_plane = np.linspace(plane_x_min, plane_x_max, 100)
        y_plane = np.linspace(plane_y_min, plane_y_max, 100)
        x_plane, y_plane = np.meshgrid(x_plane, y_plane)
        z_plane1 = np.ones_like(x_plane) * z_positions[0]
        z_plane2 = np.ones_like(x_plane) * z_positions[1]
        z_plane3 = np.ones_like(x_plane) * z_positions[2]
        z_plane4 = np.ones_like(x_plane) * z_positions[3]
        
        # Create the 3D plot
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection='3d')
    
        # Plot the planes
        ax.plot_surface(x_plane, y_plane, z_plane1, alpha=0.5, color='blue')
        ax.plot_surface(x_plane, y_plane, z_plane2, alpha=0.5, color='green')
        ax.plot_surface(x_plane, y_plane, z_plane3, alpha=0.5, color='orange')
        ax.plot_surface(x_plane, y_plane, z_plane4, alpha=0.5, color='magenta')
    
        # Plot trajectories
        for theta, phi in zip(zenith_angles, azimuth_angles):
            tan_theta = np.tan(theta)
            x = origin[0] + z_positions * tan_theta * np.cos(phi)
            y = origin[1] + z_positions * tan_theta * np.sin(phi)
            z = z_positions
        
            # Check how many planes the line passes through
            hits = [is_inside_rpc(x[i], y[i]) for i in range(4)]
            num_hits = sum(hits)
        
            # Set color based on the number of planes hit
            if num_hits >= 2:
                color = 'green'
            else:
                color = 'red'
        
            ax.plot(x, y, z, color=color)
    
        # Plot the origin point
        ax.scatter(origin[0], origin[1], origin[2], color='red', s=100)
    
        # Set the axes limits
        ax.set_xlim(plot_trajectories_xlim)
        ax.set_ylim(plot_trajectories_ylim)
        ax.set_zlim(plot_trajectories_zlim)
    
        # Set the axes labels
        ax.set_xlabel('X / mm')
        ax.set_ylabel('Y / mm')
        ax.set_zlabel('Z / mm')
        
        ax.set_zlim(ax.get_zlim()[::-1])
        ax.legend()
        
        plt.savefig("acc_visual.png", format="png")
        if show_plots: plt.show(); plt.close()

# -----------------------------------------------------------------------------

# positions = False
# if positions:
#     # Open the results file in write mode
#     with open('results.csv', 'w') as f:
#         # Write the header
#         f.write("x,y,total_lines,M1,M2,M3,M4,M1-M2,M2-M3,M3-M4,M1-M3,M2-M4,M1-M2-M3,M1-M2-M4,M2-M3-M4,M1-M2-M3-M4\n")
        
#         total_points = len(x_points) * len(y_points)
#         current_point = 0
        
#         for x0 in x_points:
#             for y0 in y_points:
#                 current_point += 1
#                 progress = current_point / total_points * 100
#                 print(f"\rProgress: {progress:.2f}%", end='')
                
#                 # Initialize counts for each (X, Y) point
#                 results = {
#                     'total_lines': 0,
#                     'M1': 0,
#                     'M2': 0,
#                     'M3': 0,
#                     'M4': 0,
#                     'M1-M2': 0,
#                     'M2-M3': 0,
#                     'M3-M4': 0,
#                     'M1-M3': 0,
#                     'M2-M4': 0,
#                     'M1-M2-M3': 0,
#                     'M1-M2-M4': 0,
#                     'M2-M3-M4': 0,
#                     'M1-M2-M3-M4': 0
#                 }
    
#                 # Iterate through all zenith and azimuth angles
#                 for theta, phi in zip(zenith, azimuth):
#                     results['total_lines'] += 1
    
#                     # Calculate the trajectory of the particle
#                     tan_theta = np.tan(theta)
#                     x = x0 + z_positions * tan_theta * np.cos(phi)
#                     y = y0 + z_positions * tan_theta * np.sin(phi)
    
#                     # Check which RPC modules the line passes through
#                     hits = [is_inside_rpc(x[i], y[i]) for i in range(4)]
    
#                     # Count the hits for each combination
#                     if hits[0]:
#                         results['M1'] += 1
#                     if hits[1]:
#                         results['M2'] += 1
#                     if hits[2]:
#                         results['M3'] += 1
#                     if hits[3]:
#                         results['M4'] += 1
                        
#                     if hits[0] and hits[1] and hits[2] and hits[3]:
#                         results['M1-M2-M3-M4'] += 1
#                     else:
#                         if hits[0] and hits[1] and hits[2]:
#                             results['M1-M2-M3'] += 1
#                         elif hits[0] and hits[1] and hits[3]:
#                             results['M1-M2-M4'] += 1
#                         elif hits[1] and hits[2] and hits[3]:
#                             results['M2-M3-M4'] += 1
#                         else:
#                             if hits[0] and hits[1]:
#                                 results['M1-M2'] += 1
#                             if hits[1] and hits[2]:
#                                 results['M2-M3'] += 1
#                             if hits[2] and hits[3]:
#                                 results['M3-M4'] += 1
#                             if hits[0] and hits[2]:
#                                 results['M1-M3'] += 1
#                             if hits[1] and hits[3]:
#                                 results['M2-M4'] += 1
                    
    
#                 # Write results to the file in CSV format for each (X, Y) point
#                 f.write(f"{x0},{y0},{results['total_lines']},{results['M1']},{results['M2']},{results['M3']},{results['M4']},"
#                         f"{results['M1-M2']},{results['M2-M3']},{results['M3-M4']},{results['M1-M3']},{results['M2-M4']},"
#                         f"{results['M1-M2-M3']},{results['M1-M2-M4']},{results['M2-M3-M4']},{results['M1-M2-M3-M4']}\n")

#     print("\nResults saved to results.csv")
    
    
#     # Read the CSV file
#     df = pd.read_csv('results.csv')
    
#     # Calculate the quotient for each (X, Y) point
#     df['sum_more_than_one_rpc'] = (df['M1-M2'] + df['M2-M3'] + df['M3-M4'] + 
#                                    df['M1-M3'] + df['M2-M4'] + df['M1-M2-M3'] + 
#                                    df['M1-M2-M4'] + df['M2-M3-M4'] + df['M1-M2-M3-M4'])
    
#     df['sum_more_than_one_rpc'] = (df['M1-M2-M3'] + df['M1-M2-M4'] + df['M2-M3-M4'] + df['M1-M2-M3-M4'])
    
#     df['quotient'] = df['sum_more_than_one_rpc'] / df['total_lines']
    
#     max_acc = df['quotient'][ (df['x'] == 0) & (df['y'] == 0) ].values[0] + 0.05
    
#     # Reshape the data for contour plotting
#     X = df['x'].unique()
#     Y = df['y'].unique()
#     Z = df.pivot_table(index='y', columns='x', values='quotient').values
    
#     # Create the contour plot
#     plt.figure(figsize=(10, 8))
#     contour = plt.contourf(X, Y, Z, levels=np.linspace(0, max_acc, 50), cmap='viridis')
#     plt.colorbar(contour, label='Quotient')
#     plt.xlabel('X (mm)')
#     plt.ylabel('Y (mm)')
#     plt.xlim([-200,200])
#     plt.ylim([-200,200])
#     plt.title('Contour Plot of Quotient (More than one RPC / Total lines)')
#     plt.savefig("acc_contour.png", format="png")
#     if show_plots: plt.show(); plt.close()
    
    
#     Z[Z == 0] = np.min(Z[Z != 0])
#     plt.figure(figsize=(10, 8))
#     contour = plt.contourf(X, Y, 1/Z, levels=np.linspace(0, 10, 50), cmap='viridis')
#     plt.colorbar(contour, label='Quotient')
#     plt.xlabel('X (mm)')
#     plt.ylabel('Y (mm)')
#     plt.xlim([-200,200])
#     plt.ylim([-200,200])
#     plt.title('Contour Plot of Quotient (More than one RPC / Total lines)')
#     plt.savefig("acc_contour_inv.png", format="png")
#     if show_plots: plt.show(); plt.close()



# from scipy import interpolate

# bins = np.linspace(-mesh_range, mesh_range, 100)  # Adjust the bin size as needed
# quotient_hist, x_edges, y_edges = np.histogram2d(df['X'], df['Y'], bins=[bins, bins], weights=df['quotient'])

# # Fit surface to quotient histogram
# x = np.linspace(-mesh_range, mesh_range, quotient_hist.shape[0])
# y = np.linspace(-mesh_range, mesh_range, quotient_hist.shape[1])
# quotient_surface = interpolate.interp2d(x, y, quotient_hist.T, kind='cubic')

# # Evaluate the surface on a dense grid
# x_dense = np.linspace(-mesh_range, mesh_range, 20)
# y_dense = np.linspace(-mesh_range, mesh_range, 20)
# x_grid, y_grid = np.meshgrid(x_dense, y_dense)
# quotient_eval = quotient_surface(x_dense, y_dense)

# # Plotting
# fig = plt.figure(figsize=(5, 5))

# # Plot quotient surface
# ax = fig.add_subplot(111, projection='3d')
# ax.plot_surface(x_grid, y_grid, quotient_eval, cmap='viridis')
# ax.set_xlabel('X (mm)')
# ax.set_ylabel('Y (mm)')
# ax.set_zlabel('Quotient (sum_more_than_one_rpc / total_lines)')
# ax.set_title('3D Surface Plot of Quotient (More than one RPC / Total lines)')
# # plt.tight_layout()
# plt.savefig("acc_3d.png", format="png")
# if show_plots: plt.show(); plt.close()


if efficiency:
    # eff = [0.7, 0.86, 0.86, 0.81]
    eff = [0.85, 0.89, 0.92, 0.83]
    # eff = [1,1,1,1]
else:
    eff = [1,1,1,1]
    
angles_acceptance = False
if angles_acceptance:
    
    azimuth = np.random.uniform(0, 2 * np.pi, num_angles)
    cos_theta = np.random.uniform(0, 1, num_angles)
    zenith = np.arccos(cos_theta)
    
    y, bin_edges = np.histogram(zenith * 180 / np.pi, bins=30)
    y = y / np.max(y)
    x = (bin_edges[:-1] + bin_edges[1:]) / 2
    plt.plot(x, y)
    plt.plot(x, np.cos(x * np.pi / 180))

    plt.xlabel('x')
    plt.ylabel('Density')
    plt.title('Histogram of values generated using cos^n(x) distribution')
    plt.show()

    v=(8,5)
    fig = plt.figure(figsize=v)
    plt.scatter(azimuth, zenith,s=1)
    plt.xlabel("Azimuth / rad")
    plt.ylabel("Zenith / rad")
    plt.title(f"Angles used for the simulation, {len(zenith)} angles")
    plt.savefig("acc_angles.png", format="png")
    if show_plots: plt.show(); plt.close()
    
    
    # Example usage
    origin = [250, 50, 0]  # Single point in the z=0 plane
    num_angles = 100  # Number of lines
    azimuth_angles = azimuth[:num_angles]
    zenith_angles = zenith[:num_angles]
    
    plot_3d_scene(origin, zenith_angles, azimuth_angles)
    
    # Open the results file in write mode
    with open('results_ang_acc.csv', 'w') as f:
        # Write the header
        f.write("theta,phi,total_lines,M1,M2,M3,M4,M1-M2,M2-M3,M3-M4,M1-M3,M2-M4,M1-M2-M3,M1-M2-M4,M2-M3-M4,M1-M2-M3-M4\n")
        
        total_points = len(zenith)
        current_point = 0
        
        for theta, phi in zip(zenith, azimuth):
            current_point += 1
            progress = current_point / total_points * 100
            print(f"\rProgress: {progress:.2f}%", end='')
            
            # Initialize counts for each (X, Y) point
            results = {
                'total_lines': 0,
                'M1': 0,
                'M2': 0,
                'M3': 0,
                'M4': 0,
                'M1-M2': 0,
                'M2-M3': 0,
                'M3-M4': 0,
                'M1-M3': 0,
                'M2-M4': 0,
                'M1-M2-M3': 0,
                'M1-M2-M4': 0,
                'M2-M3-M4': 0,
                'M1-M2-M3-M4': 0
            }

            # Iterate through all zenith and azimuth angles
            for x0 in x_points:
                for y0 in y_points:
                    results['total_lines'] += 1
    
                    # Calculate the trajectory of the particle
                    tan_theta = np.tan(theta)
                    x = x0 + z_positions * tan_theta * np.cos(phi)
                    y = y0 + z_positions * tan_theta * np.sin(phi)
    
                    # Check which RPC modules the line passes through
                    hits = [is_inside_rpc_eff(x[i], y[i], eff[i]) for i in range(4)]
    
                    # Count the hits for each combination
                    if hits[0]:
                        results['M1'] += 1
                    if hits[1]:
                        results['M2'] += 1
                    if hits[2]:
                        results['M3'] += 1
                    if hits[3]:
                        results['M4'] += 1
                        
                    if hits[0] and hits[1] and hits[2] and hits[3]:
                        results['M1-M2-M3-M4'] += 1
                    
                    if hits[0] and hits[1] and hits[2] and not hits[3]:
                        results['M1-M2-M3'] += 1
                    
                    if hits[0] and hits[1] and not hits[2] and hits[3]:
                        results['M1-M2-M4'] += 1
                    
                    if not hits[0] and hits[1] and hits[2] and hits[3]:
                        results['M2-M3-M4'] += 1
                    
                    if hits[0] and hits[1] and not hits[2] and not hits[3]:
                        results['M1-M2'] += 1
                    
                    if not hits[0] and hits[1] and hits[2] and not hits[3]:
                        results['M2-M3'] += 1
                    
                    if not hits[0] and not hits[1] and hits[2] and hits[3]:
                        results['M3-M4'] += 1
                    
                    if hits[0] and not hits[1] and hits[2] and not hits[3]:
                        results['M1-M3'] += 1
                    
                    if not hits[0] and hits[1] and not hits[2] and hits[3]:
                        results['M2-M4'] += 1

                    
            # Write results to the file in CSV format for each (X, Y) point
            f.write(f"{theta},{phi},{results['total_lines']},{results['M1']},{results['M2']},{results['M3']},{results['M4']},"
f"{results['M1-M2']},{results['M2-M3']},{results['M3-M4']},{results['M1-M3']},{results['M2-M4']},"
f"{results['M1-M2-M3']},{results['M1-M2-M4']},{results['M2-M3-M4']},{results['M1-M2-M3-M4']}\n")

    print("\nResults saved to results_ang_acc.csv")
    
    # Read the CSV file
    df = pd.read_csv('results_ang_acc.csv')
    
    df['sum_more_than_one_rpc'] = (df['M1-M2'] + df['M2-M3'] + df['M3-M4'] + 
                                    df['M1-M3'] + df['M2-M4'] + df['M1-M2-M3'] + 
                                    df['M1-M2-M4'] + df['M2-M3-M4'])
    
    df['quotient'] = df['sum_more_than_one_rpc'] / df['total_lines']
    df['quotient'] = df['quotient'] / df['quotient'].max()
    
    # -------------------------------    
    columns_to_combine = ['M1-M2', 'M2-M3', 'M3-M4', 'M1-M3', 'M2-M4', 'M1-M2-M3', 'M1-M2-M4', 'M2-M3-M4', 'M1-M2-M3-M4']
    
    for comb in columns_to_combine:
        df[f'sum_{comb}'] = df[f'{comb}']  # Initialize the sum column
    
    # Select only the numerical columns for summation
    numerical_columns = [f'sum_{comb}' for comb in columns_to_combine] + ['total_lines']
    
    # Group by 'theta' and 'phi', then sum only the numerical columns
    theta_sum = df.groupby('theta')[numerical_columns].sum().reset_index()
    phi_sum = df.groupby('phi')[numerical_columns].sum().reset_index()
    
    # Calculate the quotient
    for comb in columns_to_combine:
        theta_sum[f'quotient_{comb}'] = theta_sum[f'sum_{comb}'] / theta_sum['total_lines']
        phi_sum[f'quotient_{comb}'] = phi_sum[f'sum_{comb}'] / phi_sum['total_lines']
    
    result_df = pd.DataFrame()
    fig, axs = plt.subplots(3, 3, figsize=(14, 10))
    
    for idx, combination in enumerate(columns_to_combine):
        row = idx // 3
        col = idx % 3
        
        # Number of bins
        num_bins_theta = 100
        num_bins_phi = 100
        
        # Create bins for theta and phi
        df['theta_bin'] = pd.cut(df['theta'], bins=num_bins_theta)
        df['phi_bin'] = pd.cut(df['phi'], bins=num_bins_phi)
        
        # Calculate average for theta and phi bins
        theta_avg = df.groupby('theta_bin')[f'{combination}'].mean().reset_index()
        phi_avg = df.groupby('phi_bin')[f'{combination}'].mean().reset_index()
        
        theta_avg['theta_mid'] = theta_avg['theta_bin'].apply(lambda x: x.mid)
        phi_avg['phi_mid'] = phi_avg['phi_bin'].apply(lambda x: x.mid)
        
        theta_avg['theta_mid'] = theta_avg['theta_mid'].astype(float)
        phi_avg['phi_mid'] = phi_avg['phi_mid'].astype(float)
        
        # Plotting
        axs[row, col].plot(theta_sum['theta'] * 180/np.pi, theta_sum[f'quotient_{combination}'], marker='.', label='Sum')
        axs[row, col].plot(theta_avg['theta_mid'] * 180 / np.pi, theta_avg[f'{combination}'], marker='.', c="r", label='Avg')
        axs[row, col].set_xlabel('Theta / º')
        axs[row, col].set_ylabel(f'Quotient {combination}')
        axs[row, col].set_title(f'{combination} acceptance')
        axs[row, col].grid(True)
        axs[row, col].legend()
        
        result_df[f'theta_mid_{combination}'] = theta_avg['theta_mid']
        result_df[f'quotient_avg_{combination}'] = theta_avg[f'{combination}']
    
    # Create bins for theta and phi
    df['theta_bin'] = pd.cut(df['theta'], bins=num_bins_theta)
    df['phi_bin'] = pd.cut(df['phi'], bins=num_bins_phi)
    
    # Calculate average for theta and phi bins
    theta_avg = df.groupby('theta_bin')['total_lines'].mean().reset_index()
    phi_avg = df.groupby('phi_bin')['total_lines'].mean().reset_index()
    
    theta_avg['theta_mid'] = theta_avg['theta_bin'].apply(lambda x: x.mid)
    phi_avg['phi_mid'] = phi_avg['phi_bin'].apply(lambda x: x.mid)
    
    theta_avg['theta_mid'] = theta_avg['theta_mid'].astype(float)
    phi_avg['phi_mid'] = phi_avg['phi_mid'].astype(float)
    
    result_df['theta_mid'] = theta_avg['theta_mid']
    result_df['quotient_avg'] = theta_avg['total_lines']
    
    # Save the result to CSV
    result_df.to_csv('zenith_acceptance_acc.csv', index=False)
    
    # Adjust the layout and show the plot
    plt.tight_layout()
    plt.show()
    
    # for combination in columns_to_combine:
    #     # Summing the quotient values for unique theta and phi combinations
    #     theta_sum = df.groupby('theta')[f'quotient_{combination}'].sum().reset_index()
    #     phi_sum = df.groupby('phi')[f'quotient_{combination}'].sum().reset_index()
    #     num_bins_theta = 100
    #     num_bins_phi = 100
    #     df['theta_bin'] = pd.cut(df['theta'], bins=num_bins_theta)
    #     df['phi_bin'] = pd.cut(df['phi'], bins=num_bins_phi)
    #     theta_avg = df.groupby('theta_bin')[f'quotient_{combination}'].mean().reset_index()
    #     phi_avg = df.groupby('phi_bin')[f'quotient_{combination}'].mean().reset_index()
    #     theta_avg['theta_mid'] = theta_avg['theta_bin'].apply(lambda x: x.mid)
    #     phi_avg['phi_mid'] = phi_avg['phi_bin'].apply(lambda x: x.mid)
    #     theta_avg['theta_mid'] = theta_avg['theta_mid'].astype(float)
    #     phi_avg['phi_mid'] = phi_avg['phi_mid'].astype(float)
        
    #     plt.figure(figsize=(10, 6))
    #     plt.plot(theta_sum['theta'] * 180/np.pi, theta_sum[f'quotient_{combination}'], marker='.')
    #     plt.plot(theta_avg['theta_mid'] * 180 / np.pi, theta_avg[f'quotient_{combination}'], marker='.', c="r")
    #     plt.xlabel('Theta')
    #     plt.ylabel(f'quotient_{combination}')
    #     plt.title(f'quotient_{combination} vs Theta')
    #     plt.grid(True)
    #     plt.show()
        
    #     plt.figure(figsize=(10, 6))
    #     plt.plot(phi_sum['phi'] * 180/np.pi, phi_sum[f'quotient_{combination}'], marker='.')
    #     plt.plot(phi_avg['phi_mid'] * 180 / np.pi, phi_avg[f'quotient_{combination}'], marker='.', c="r")
    #     plt.xlabel('Phi')
    #     plt.ylabel(f'quotient_{combination}')
    #     plt.title(f'quotient_{combination} vs Phi')
    #     plt.grid(True)
    #     plt.show()
        

    # OG -----------------------
    # Summing the quotient values for unique theta and phi combinations
    # theta_sum = df.groupby('theta')['quotient'].sum().reset_index()
    # phi_sum = df.groupby('phi')['quotient'].sum().reset_index()
    
    # # Define the number of bins for theta and phi
    # num_bins_theta = 100
    # num_bins_phi = 100
    
    # # Create bins for theta and phi
    # df['theta_bin'] = pd.cut(df['theta'], bins=num_bins_theta)
    # df['phi_bin'] = pd.cut(df['phi'], bins=num_bins_phi)
    
    # # Calculate the average quotient for each bin
    # theta_avg = df.groupby('theta_bin')['quotient'].mean().reset_index()
    # phi_avg = df.groupby('phi_bin')['quotient'].mean().reset_index()
    
    # # Convert bin intervals to midpoints for plotting
    # theta_avg['theta_mid'] = theta_avg['theta_bin'].apply(lambda x: x.mid)
    # phi_avg['phi_mid'] = phi_avg['phi_bin'].apply(lambda x: x.mid)
    
    # # Convert midpoints to numeric values
    # theta_avg['theta_mid'] = theta_avg['theta_mid'].astype(float)
    # phi_avg['phi_mid'] = phi_avg['phi_mid'].astype(float)
    
    
    # # Plotting quotient vs theta
    # plt.figure(figsize=(10, 6))
    # plt.plot(theta_sum['theta'] * 180/np.pi, theta_sum['quotient'], marker='.')
    # plt.plot(theta_avg['theta_mid'] * 180 / np.pi, theta_avg['quotient'], marker='.', c="r")
    # plt.xlabel('Theta')
    # plt.ylabel('Quotient')
    # plt.title('Quotient vs Theta')
    # plt.grid(True)
    # plt.show()
    
    # # Plotting quotient vs phi
    # plt.figure(figsize=(10, 6))
    # plt.plot(phi_sum['phi'] * 180/np.pi, phi_sum['quotient'], marker='.')
    # plt.plot(phi_avg['phi_mid'] * 180 / np.pi, phi_avg['quotient'], marker='.', c="r")
    # plt.xlabel('Phi')
    # plt.ylabel('Quotient')
    # plt.title('Quotient vs Phi')
    # plt.grid(True)
    # plt.show()
    
    
    
    # # Reshape the data for contour plotting
    # X = df['theta'].unique()
    # Y = df['phi'].unique()
    
    # # Get unique values of theta and phi
    # X = np.sort(df['theta'].unique())
    # Y = np.sort(df['phi'].unique())
    
    # # Create a MultiIndex for all combinations of theta and phi
    # index = pd.MultiIndex.from_product([Y, X], names=['phi', 'theta'])
    
    # # Reindex the DataFrame to include all combinations
    # df_full = df.set_index(['phi', 'theta']).reindex(index)
    
    # # Fill missing values in 'quotient' column with 0 (or any appropriate value)
    # df_full['quotient'].fillna(0, inplace=True)
    
    # # Pivot the DataFrame to create the Z matrix
    # Z = df_full['quotient'].unstack().values
    
    
    # # Z = df.pivot_table(index='phi', columns='theta', values='quotient').values
    
    # # Create the contour plot
    # plt.figure(figsize=(10, 8))
    # # contour = plt.contourf(X, Y, Z, levels=np.linspace(0, max_acc, 50), cmap='viridis')
    # contour = plt.contourf(X, Y, Z, cmap='viridis')
    # plt.colorbar(contour, label='Quotient')
    # plt.xlabel('Theta (rad)')
    # plt.ylabel('Phi (rad)')
    # # plt.xlim([-200,200])
    # # plt.ylim([-200,200])
    # plt.title('Contour Plot of Quotient (More than one RPC / Total lines)')
    # plt.savefig("acc_contour_ang.png", format="png")
    # if show_plots: plt.show(); plt.close()
    
    
    # Z[Z == 0] = np.min(Z[Z != 0])
    # plt.figure(figsize=(10, 8))
    # contour = plt.contourf(X, Y, 1/Z, levels=np.linspace(0, 10, 50), cmap='viridis')
    # plt.colorbar(contour, label='Quotient')
    # plt.xlabel('Theta (rad)')
    # plt.ylabel('Phi (rad)')
    # # plt.xlim([-200,200])
    # # plt.ylim([-200,200])
    # plt.title('Contour Plot of Quotient (More than one RPC / Total lines)')
    # plt.savefig("acc_contour_inv_ang.png", format="png")
    # if show_plots: plt.show(); plt.close()




# Simulate angular acceptance
angles_acceptance = False
show_plots = True

if angles_acceptance:
    # Generate random angles
    azimuth = np.random.uniform(0, 2 * np.pi, num_angles)
    cos_theta = np.random.uniform(0, 1, num_angles)
    zenith = np.arccos(cos_theta)

    # Plot histogram of generated angles
    y, bin_edges = np.histogram(zenith * 180 / np.pi, bins=30)
    y = y / np.max(y)
    x = (bin_edges[:-1] + bin_edges[1:]) / 2
    plt.plot(x, y, label='Simulated')
    plt.plot(x, np.cos(np.radians(x)), label='Cosine')
    plt.xlabel('Zenith Angle (degrees)')
    plt.ylabel('Density')
    plt.title('Histogram of Simulated Angles')
    plt.legend()
    plt.show()

    # Scatter plot of angles
    fig = plt.figure(figsize=(8, 5))
    plt.scatter(azimuth, zenith, s=1)
    plt.xlabel("Azimuth (radians)")
    plt.ylabel("Zenith (radians)")
    plt.title(f"Angles used for the simulation, {len(zenith)} angles")
    plt.savefig("acc_angles.png", format="png")
    if show_plots:
        plt.show()
    else:
        plt.close()

    # Example usage
    origin = [250, 50, 0]
    num_angles = 100
    azimuth_angles = azimuth[:num_angles]
    zenith_angles = zenith[:num_angles]

    # Function plot_3d_scene should be defined
    # plot_3d_scene(origin, zenith_angles, azimuth_angles)

    # Write results to CSV file
    with open('results_ang_acc.csv', 'w') as f:
        f.write("theta,phi,total_lines,M1,M2,M3,M4,M1-M2,M2-M3,M3-M4,M1-M3,M2-M4,M1-M2-M3,M1-M2-M4,M2-M3-M4,M1-M2-M3-M4\n")

        total_points = len(zenith)
        current_point = 0

        for theta, phi in zip(zenith, azimuth):
            current_point += 1
            progress = current_point / total_points * 100
            print(f"\rProgress: {progress:.2f}%", end='')

            results = {
                'total_lines': 0,
                'M1': 0,
                'M2': 0,
                'M3': 0,
                'M4': 0,
                'M1-M2': 0,
                'M2-M3': 0,
                'M3-M4': 0,
                'M1-M3': 0,
                'M2-M4': 0,
                'M1-M2-M3': 0,
                'M1-M2-M4': 0,
                'M2-M3-M4': 0,
                'M1-M2-M3-M4': 0
            }
            
            # x_points = np.linspace(95, 105, 20)
            # y_points = np.linspace(95, 105, 20)
            
            for x0 in x_points:
                for y0 in y_points:
                    results['total_lines'] += 1
                    tan_theta = np.tan(theta)
                    x = x0 + z_positions * tan_theta * np.cos(phi)
                    y = y0 + z_positions * tan_theta * np.sin(phi)

                    hits = [is_inside_rpc_eff(x[i], y[i], eff[i]) for i in range(4)]

                    if hits[0]:
                        results['M1'] += 1
                    if hits[1]:
                        results['M2'] += 1
                    if hits[2]:
                        results['M3'] += 1
                    if hits[3]:
                        results['M4'] += 1

                    if hits[0] and hits[1] and hits[2] and hits[3]:
                        results['M1-M2-M3-M4'] += 1

                    if hits[0] and hits[1] and hits[2] and not hits[3]:
                        results['M1-M2-M3'] += 1

                    if hits[0] and hits[1] and not hits[2] and hits[3]:
                        results['M1-M2-M4'] += 1

                    if not hits[0] and hits[1] and hits[2] and hits[3]:
                        results['M2-M3-M4'] += 1

                    if hits[0] and hits[1] and not hits[2] and not hits[3]:
                        results['M1-M2'] += 1

                    if not hits[0] and hits[1] and hits[2] and not hits[3]:
                        results['M2-M3'] += 1

                    if not hits[0] and not hits[1] and hits[2] and hits[3]:
                        results['M3-M4'] += 1

                    if hits[0] and not hits[1] and hits[2] and not hits[3]:
                        results['M1-M3'] += 1

                    if not hits[0] and hits[1] and not hits[2] and hits[3]:
                        results['M2-M4'] += 1

            f.write(f"{theta},{phi},{results['total_lines']},{results['M1']},{results['M2']},{results['M3']},{results['M4']},"
                    f"{results['M1-M2']},{results['M2-M3']},{results['M3-M4']},{results['M1-M3']},{results['M2-M4']},"
                    f"{results['M1-M2-M3']},{results['M1-M2-M4']},{results['M2-M3-M4']},{results['M1-M2-M3-M4']}\n")

    print("\nResults saved to results_ang_acc.csv")

    df = pd.read_csv('results_ang_acc.csv')

    df['sum_more_than_one_rpc'] = (df['M1-M2'] + df['M2-M3'] + df['M3-M4'] +
                                   df['M1-M3'] + df['M2-M4'] + df['M1-M2-M3'] +
                                   df['M1-M2-M4'] + df['M2-M3-M4'])

    df['quotient'] = df['sum_more_than_one_rpc'] / df['total_lines']
    df['quotient'] = df['quotient'] / df['quotient'].max()

    columns_to_combine = ['M1-M2', 'M2-M3', 'M3-M4', 'M1-M3', 'M2-M4', 'M1-M2-M3', 'M1-M2-M4', 'M2-M3-M4', 'M1-M2-M3-M4']

    for comb in columns_to_combine:
        df[f'sum_{comb}'] = df[f'{comb}']

    numerical_columns = [f'sum_{comb}' for comb in columns_to_combine] + ['total_lines']

    theta_sum = df.groupby('theta')[numerical_columns].mean().reset_index()
    phi_sum = df.groupby('phi')[numerical_columns].mean().reset_index()

    for comb in columns_to_combine:
        theta_sum[f'quotient_{comb}'] = theta_sum[f'sum_{comb}'] / theta_sum['total_lines']
        phi_sum[f'quotient_{comb}'] = phi_sum[f'sum_{comb}'] / phi_sum['total_lines']

    result_df = pd.DataFrame()
    fig, axs = plt.subplots(3, 3, figsize=(14, 10))

    for idx, combination in enumerate(columns_to_combine):
        row = idx // 3
        col = idx % 3

        num_bins_theta = 100
        num_bins_phi = 100

        df['theta_bin'] = pd.cut(df['theta'], bins=num_bins_theta)
        df['phi_bin'] = pd.cut(df['phi'], bins=num_bins_phi)

        theta_avg = df.groupby('theta_bin')[f'{combination}'].mean().reset_index()
        phi_avg = df.groupby('phi_bin')[f'{combination}'].mean().reset_index()

        theta_avg['theta_mid'] = theta_avg['theta_bin'].apply(lambda x: x.mid)
        phi_avg['phi_mid'] = phi_avg['phi_bin'].apply(lambda x: x.mid)

        theta_avg['theta_mid'] = theta_avg['theta_mid'].astype(float)
        phi_avg['phi_mid'] = phi_avg['phi_mid'].astype(float)

        axs[row, col].plot(theta_sum['theta'] * 180/np.pi, theta_sum[f'quotient_{combination}'], marker='.', label='Sum')
        axs[row, col].plot(theta_avg['theta_mid'] * 180 / np.pi, theta_avg[f'{combination}'], marker='.', c="r", label='Avg')
        axs[row, col].set_xlabel('Theta (degrees)')
        axs[row, col].set_ylabel(f'Quotient {combination}')
        axs[row, col].set_title(f'{combination} acceptance')
        axs[row, col].grid(True)
        axs[row, col].legend()

        result_df[f'theta_mid_{combination}'] = theta_avg['theta_mid']
        result_df[f'quotient_avg_{combination}'] = theta_avg[f'{combination}']

    df['theta_bin'] = pd.cut(df['theta'], bins=num_bins_theta)
    df['phi_bin'] = pd.cut(df['phi'], bins=num_bins_phi)

    theta_avg = df.groupby('theta_bin')['total_lines'].mean().reset_index()
    phi_avg = df.groupby('phi_bin')['total_lines'].mean().reset_index()

    theta_avg['theta_mid'] = theta_avg['theta_bin'].apply(lambda x: x.mid)
    phi_avg['phi_mid'] = phi_avg['phi_bin'].apply(lambda x: x.mid)

    theta_avg['theta_mid'] = theta_avg['theta_mid'].astype(float)
    phi_avg['phi_mid'] = phi_avg['phi_mid'].astype(float)

    result_df['theta_mid'] = theta_avg['theta_mid']
    result_df['quotient_avg'] = theta_avg['total_lines']

    result_df.to_csv('zenith_acceptance_acc.csv', index=False)

    plt.tight_layout()
    plt.show()





# Quick two planes test -------------------------------------------------------

# rpc_side = np.linspace(-half_rpc_length, half_rpc_length, mesh_step * 2)

num_points = 20

import numpy as np
import matplotlib.pyplot as plt

big_zenith = []

import itertools
range_values = [1, 2, 3, 4]
pairs = list(itertools.combinations(range_values, 2))
print(pairs)

# Example use case in a loop
for (i, j) in pairs:
    
    rpc_side_1 = np.random.uniform(-half_rpc_length, half_rpc_length, num_points)
    rpc_side_2 = np.random.uniform(-half_rpc_length, half_rpc_length, num_points)
    rpc_side_3 = np.random.uniform(-half_rpc_length, half_rpc_length, num_points)
    rpc_side_4 = np.random.uniform(-half_rpc_length, half_rpc_length, num_points)
    
    # Define the points on the two planes
    plane1_points = np.array([(x, y, z_positions[i-1]) for x in rpc_side_1 for y in rpc_side_2])
    plane2_points = np.array([(x, y, z_positions[j-1]) for x in rpc_side_3 for y in rpc_side_4])
    
    zenith_angles = []
    total_points = len(plane1_points)*len(plane2_points)
    
    print(f"{total_points} trajectories to calculate\n")
    
    # Calculate zenith angles
    current_point = 0
    for p1 in plane1_points:
        for p2 in plane2_points:
            current_point += 1
            progress = current_point / total_points * 100
            print(f"\rProgress: {progress:.2f}%", end='')
            
            vector = p2 - p1
            zenith_angle = np.arccos(vector[2] / np.linalg.norm(vector))
            zenith_angles.append(zenith_angle)
    
    # Convert angles to degrees
    zenith_angles_deg = np.degrees(zenith_angles)
    big_zenith.append(zenith_angles_deg)

plt.figure(figsize = (12,8))
for i in range(len(big_zenith)):
    zenith = big_zenith[i]
    # Plot the histogram
    plt.hist(zenith, bins=100, density=True, alpha=1, histtype='step', label = f"{pairs[i]} combination")
    # plt.hist(zenith, bins=100, density=True, alpha=0.6, label = f"{pairs[i]} combination")
    
plt.xlabel('Zenith Angle (degrees)')
plt.ylabel('Density')
plt.legend(fontsize="small")
plt.title(f'Zenith Angle Distribution, {len(zenith_angles_deg)} evs.')
plt.grid(True)
plt.show()



binning = 50
plt.figure(figsize = (12,8))
for i in range(len(big_zenith)):
    zenith = big_zenith[i]
    
    y_flux, bin_edges = np.histogram(zenith, bins=binning)
    bin_cos = np.cos(np.radians(bin_edges))
    bin_cos_dif = -np.diff(bin_cos)
    y_flux = y_flux / bin_cos_dif
    y_flux = y_flux / np.max(y_flux)
    x_flux = (bin_edges[:-1] + bin_edges[1:]) / 2
    plt.plot(x_flux, y_flux)
    
    # plt.hist(zenith, bins=100, density=True, alpha=0.6, label = f"{pairs[i]} combination")
    
plt.xlabel('Zenith Angle (degrees)')
plt.ylabel('Density')
plt.legend(fontsize="small")
plt.title(f'Zenith Angle Distribution, {len(zenith_angles_deg)} evs.')
plt.grid(True)
plt.show()

# -----------------------------------------------------------------------------


# Quick two planes test -------------------------------------------------------

# rpc_side = np.linspace(-half_rpc_length, half_rpc_length, mesh_step * 2)

num_points = 25

import numpy as np
import matplotlib.pyplot as plt

big_zenith = []

import itertools
range_values = [1, 2, 3, 4]
pairs = list(itertools.combinations(range_values, 2))
print(pairs)

# Set up the subplots
fig, axs = plt.subplots(2, 3, figsize=(18, 12))
axs = axs.flatten()

# Iterate over pairs of planes
for index, (i, j) in enumerate(pairs):
    rpc_side = np.linspace(-half_rpc_length, half_rpc_length, num_points)
    
    # Define the points on the midplane between the two planes
    # mid_z = (z_positions[i-1] + z_positions[j-1]) / 2
    mid_z = z_positions[i-1]
    plane_points = np.array([(x, y, mid_z) for x in rpc_side for y in rpc_side])

    zenith_counts = np.zeros(180)
    total_points = len(plane_points) * num_angles
    
    print(f"{total_points} trajectories to calculate for pair {i}-{j}\n")
    
    current_point = 0
    
    for point in plane_points:
        azimuth = np.random.uniform(0, 2 * np.pi, num_angles)
        cos_theta = np.random.uniform(0, 1, num_angles)
        zenith = np.arccos(cos_theta)
        
        for k in range(num_angles):
            theta = zenith[k]
            phi = azimuth[k]
            current_point += 1
            progress = current_point / total_points * 100
            print(f"\rProgress: {progress:.2f}%", end='')
            
            # Calculate the trajectory of the particle
            tan_theta = np.tan(theta)
            delta_x = tan_theta * np.cos(phi)
            delta_y = tan_theta * np.sin(phi)
            
            # Calculate intersection points with both planes
            z1 = z_positions[i-1]
            z2 = z_positions[j-1]
            x1 = point[0] + delta_x * (z1 - point[2])
            y1 = point[1] + delta_y * (z1 - point[2])
            x2 = point[0] + delta_x * (z2 - point[2])
            y2 = point[1] + delta_y * (z2 - point[2])
            
            # Check if the trace passes through both planes
            if is_inside_rpc(x1, y1) and is_inside_rpc(x2, y2):
                zenith_counts[int(np.degrees(theta))] += 1
    
    # Plot the results for this pair
    axs[index].plot(np.arange(len(zenith_counts)), zenith_counts, marker='o', linestyle='-', color='b')
    axs[index].set_xlim(0,90)
    axs[index].set_xlabel('Zenith Angle (degrees)')
    axs[index].set_ylabel('Number of Traces')
    axs[index].set_title(f'Number of Traces Respect to Zenith Angle for Planes {i} and {j}')
    axs[index].grid(True)

# Adjust layout and show the plot
plt.tight_layout()
plt.show()







# NOW DIVIDING BY THE NUMBER OF TRACES WITH THAT ZENITH ANGLE INSTEAD OF
# DIVIDING BY THE TOTAL NUMBER OF EVENTS.

num_points = 25

import numpy as np
import matplotlib.pyplot as plt

big_zenith = []

import itertools
range_values = [1, 2, 3, 4]
pairs = list(itertools.combinations(range_values, 2))
print(pairs)

# Set up the subplots
fig, axs = plt.subplots(2, 3, figsize=(18, 12))
axs = axs.flatten()

# Iterate over pairs of planes
for index, (i, j) in enumerate(pairs):
    rpc_side = np.linspace(-half_rpc_length, half_rpc_length, num_points)
    
    # Define the points on the midplane between the two planes
    # mid_z = (z_positions[i-1] + z_positions[j-1]) / 2
    mid_z = z_positions[i-1]
    plane_points = np.array([(x, y, mid_z) for x in rpc_side for y in rpc_side])

    detected_counts = np.zeros(180)
    total_counts = np.zeros(180)
    total_points = len(plane_points) * num_angles
    
    print(f"{total_points} trajectories to calculate for pair {i}-{j}\n")
    
    current_point = 0
    
    for point in plane_points:
        azimuth = np.random.uniform(0, 2 * np.pi, num_angles)
        cos_theta = np.random.uniform(0, 1, num_angles)
        zenith = np.arccos(cos_theta)
        
        for k in range(num_angles):
            theta = zenith[k]
            phi = azimuth[k]
            theta_deg = int(np.degrees(theta))
            current_point += 1
            progress = current_point / total_points * 100
            print(f"\rProgress: {progress:.2f}%", end='')
            
            # Calculate the trajectory of the particle
            tan_theta = np.tan(theta)
            delta_x = tan_theta * np.cos(phi)
            delta_y = tan_theta * np.sin(phi)
            
            # Calculate intersection points with both planes
            z1 = z_positions[i-1]
            z2 = z_positions[j-1]
            x1 = point[0] + delta_x * (z1 - point[2])
            y1 = point[1] + delta_y * (z1 - point[2])
            x2 = point[0] + delta_x * (z2 - point[2])
            y2 = point[1] + delta_y * (z2 - point[2])
            
            # Increment the total count for the current theta range
            total_counts[theta_deg] += 1
            
            # Check if the trace passes through both planes
            if is_inside_rpc(x1, y1) and is_inside_rpc(x2, y2):
                detected_counts[theta_deg] += 1
    
    # Calculate the ratio for each theta range
    with np.errstate(divide='ignore', invalid='ignore'):
        zenith_ratios = np.true_divide(detected_counts, total_counts)
        zenith_ratios[~np.isfinite(zenith_ratios)] = 0  # set infinities and NaNs to 0

    # Debug prints
    print(f"\nDetected counts for pair {i}-{j}: {detected_counts[:91]}")
    print(f"Total counts for pair {i}-{j}: {total_counts[:91]}")
    print(f"Zenith ratios for pair {i}-{j}: {zenith_ratios[:91]}\n")

    # Plot the results for this pair, limited to 0-90 degrees
    axs[index].plot(np.arange(91), zenith_ratios[:91], marker='o', linestyle='-', color='b')
    axs[index].plot(np.arange(91), np.cos(np.arange(91)*np.pi/180), color='g')
    axs[index].set_xlabel('Zenith Angle (degrees)')
    axs[index].set_ylabel('Detection Ratio')
    axs[index].set_title(f'Detection Ratio Respect to Zenith Angle for Planes {i} and {j}')
    axs[index].grid(True)
    axs[index].set_xlim(0, 90)

# Adjust layout and show the plot
plt.tight_layout()
plt.show()
plt.show()

# -----------------------------------------------------------------------------




if efficiency:
    eff = [0.7, 0.86, 0.86, 0.81]
else:
    eff = [1,1,1,1]
    
pos_ang = False
if pos_ang:
    # Open the results file in write mode
    with open('results_pos_ang.csv', 'w') as f:
        # Write the header
        f.write("x,y,theta,phi,total_lines,M1,M2,M3,M4,M1-M2,M2-M3,M3-M4,M1-M3,M2-M4,M1-M2-M3,M1-M2-M4,M2-M3-M4,M1-M2-M3-M4\n")
        
        total_points = len(zenith)
        current_point = 0
        
        for theta, phi in zip(zenith, azimuth):
            current_point += 1
            progress = current_point / total_points * 100
            print(f"\rProgress: {progress:.2f}%", end='')

            # Iterate through all zenith and azimuth angles
            for x0 in x_points:
                for y0 in y_points:
                    
                    # Initialize counts for each (X, Y) point
                    results = {
                        'total_lines': 0,
                        'M1': 0,
                        'M2': 0,
                        'M3': 0,
                        'M4': 0,
                        'M1-M2': 0,
                        'M2-M3': 0,
                        'M3-M4': 0,
                        'M1-M3': 0,
                        'M2-M4': 0,
                        'M1-M2-M3': 0,
                        'M1-M2-M4': 0,
                        'M2-M3-M4': 0,
                        'M1-M2-M3-M4': 0
                    }
                    
                    results['total_lines'] += 1
                    
                    # Calculate the trajectory of the particle
                    tan_theta = np.tan(theta)
                    x = x0 + z_positions * tan_theta * np.cos(phi)
                    y = y0 + z_positions * tan_theta * np.sin(phi)
    
                    # Check which RPC modules the line passes through
                    hits = [is_inside_rpc_eff(x[i], y[i], eff[i]) for i in range(4)]
    
                    # Count the hits for each combination
                    if hits[0]:
                        results['M1'] += 1
                    if hits[1]:
                        results['M2'] += 1
                    if hits[2]:
                        results['M3'] += 1
                    if hits[3]:
                        results['M4'] += 1
                        
                    if hits[0] and hits[1] and hits[2] and hits[3]:
                        results['M1-M2-M3-M4'] += 1
                    else:
                        if hits[0] and hits[1] and hits[2]:
                            results['M1-M2-M3'] += 1
                        elif hits[0] and hits[1] and hits[3]:
                            results['M1-M2-M4'] += 1
                        elif hits[1] and hits[2] and hits[3]:
                            results['M2-M3-M4'] += 1
                        else:
                            if hits[0] and hits[1]:
                                results['M1-M2'] += 1
                            if hits[1] and hits[2]:
                                results['M2-M3'] += 1
                            if hits[2] and hits[3]:
                                results['M3-M4'] += 1
                            if hits[0] and hits[2]:
                                results['M1-M3'] += 1
                            if hits[1] and hits[3]:
                                results['M2-M4'] += 1
                    
                    # Write results to the file in CSV format for each (X, Y) point
                    f.write(f"{x0},{y0},{theta},{phi},{results['total_lines']},{results['M1']},{results['M2']},{results['M3']},{results['M4']},"
f"{results['M1-M2']},{results['M2-M3']},{results['M3-M4']},{results['M1-M3']},{results['M2-M4']},"
f"{results['M1-M2-M3']},{results['M1-M2-M4']},{results['M2-M3-M4']},{results['M1-M2-M3-M4']}\n")

    print("\nResults saved to results_pos_ang.csv")
    
    # Load the DataFrame
    df = pd.read_csv('results_pos_ang.csv')
    
    # Compute sum_more_than_one_rpc and quotient columns
    df['sum_more_than_one_rpc'] = (
        df['M1-M2'] + df['M2-M3'] + df['M3-M4'] + 
        df['M1-M3'] + df['M2-M4'] + df['M1-M2-M3'] + 
        df['M1-M2-M4'] + df['M2-M3-M4']
    )
    df['quotient'] = df['sum_more_than_one_rpc'] / df['total_lines']
    df['quotient'] = df['quotient'] / df['quotient'].max()
    
    # Create quotient columns for combinations
    columns_to_combine = ['M1-M2', 'M2-M3', 'M3-M4', 'M1-M3', 'M2-M4', 'M1-M2-M3', 'M1-M2-M4', 'M2-M3-M4', 'M1-M2-M3-M4']
    for comb in columns_to_combine:
        df[f'quotient_{comb}'] = df[f'{comb}'] / df['total_lines']
        df[f'quotient_{comb}'] = df[f'quotient_{comb}'] / df[f'quotient_{comb}'].max()
    
    # Define the number of bins
    num_bins = 15
    
    # Define a function to generate unique bin edges
    def unique_bins(arr, num_bins):
        bins = np.linspace(np.min(arr), np.max(arr), num_bins + 1)
        return np.unique(bins)
    
    # Define bin edges for x, y, theta, phi, ensuring unique bin edges
    x_bins = unique_bins(df['x'], num_bins)
    y_bins = unique_bins(df['y'], num_bins)
    theta_bins = unique_bins(df['theta'], num_bins)
    phi_bins = unique_bins(df['phi'], num_bins)
    
    # Ensure that we have more than one unique bin edge
    if len(x_bins) < 2:
        x_bins = np.array([df['x'].min(), df['x'].max()])
    if len(y_bins) < 2:
        y_bins = np.array([df['y'].min(), df['y'].max()])
    if len(theta_bins) < 2:
        theta_bins = np.array([df['theta'].min(), df['theta'].max()])
    if len(phi_bins) < 2:
        phi_bins = np.array([df['phi'].min(), df['phi'].max()])
    
    # Bin the data
    df['x_bin'] = pd.cut(df['x'], bins=x_bins, labels=False, include_lowest=True)
    df['y_bin'] = pd.cut(df['y'], bins=y_bins, labels=False, include_lowest=True)
    df['theta_bin'] = pd.cut(df['theta'], bins=theta_bins, labels=False, include_lowest=True)
    df['phi_bin'] = pd.cut(df['phi'], bins=phi_bins, labels=False, include_lowest=True)
    
    # Group by the bins and sum the values of the other columns
    grouped_df = df.groupby(['x_bin', 'y_bin', 'theta_bin', 'phi_bin']).sum().reset_index()
    
    # Calculate the mid value and bin width for x, y, theta, phi
    x_bin_mid = (x_bins[:-1] + x_bins[1:]) / 2
    y_bin_mid = (y_bins[:-1] + y_bins[1:]) / 2
    theta_bin_mid = (theta_bins[:-1] + theta_bins[1:]) / 2
    phi_bin_mid = (phi_bins[:-1] + phi_bins[1:]) / 2
    
    x_bin_width = x_bins[1] - x_bins[0] if len(x_bins) > 1 else 0
    y_bin_width = y_bins[1] - y_bins[0] if len(y_bins) > 1 else 0
    theta_bin_width = theta_bins[1] - theta_bins[0] if len(theta_bins) > 1 else 0
    phi_bin_width = phi_bins[1] - phi_bins[0] if len(phi_bins) > 1 else 0
    
    # Assign the mid values to the grouped DataFrame
    grouped_df['x'] = grouped_df['x_bin'].apply(lambda x: x_bin_mid[int(x)] if not pd.isna(x) else np.nan)
    grouped_df['y'] = grouped_df['y_bin'].apply(lambda y: y_bin_mid[int(y)] if not pd.isna(y) else np.nan)
    grouped_df['theta'] = grouped_df['theta_bin'].apply(lambda theta: theta_bin_mid[int(theta)] if not pd.isna(theta) else np.nan)
    grouped_df['phi'] = grouped_df['phi_bin'].apply(lambda phi: phi_bin_mid[int(phi)] if not pd.isna(phi) else np.nan)
    
    # Calculate the area in the binning for x and y
    grouped_df['DeltaX'] = x_bin_width
    grouped_df['DeltaY'] = y_bin_width
    grouped_df['Area'] = grouped_df['DeltaX'] * grouped_df['DeltaY']
    
    # Calculate the solid angle subtended for theta and phi
    def solid_angle(theta_bin_width, phi_bin_width, theta_mid):
        theta_min = theta_mid - theta_bin_width / 2
        theta_max = theta_mid + theta_bin_width / 2
        phi_min = -phi_bin_width / 2
        phi_max = phi_bin_width / 2
        return (phi_max - phi_min) * (np.cos(np.deg2rad(theta_min)) - np.cos(np.deg2rad(theta_max)))
    
    # Calculate solid angle for each row in the grouped DataFrame
    grouped_df['SolidAngle'] = grouped_df.apply(
        lambda row: solid_angle(theta_bin_width, phi_bin_width, row['theta']),
        axis=1
    )
    
    # Drop the bin columns and rename the index columns to original names
    grouped_df.drop(columns=['x_bin', 'y_bin', 'theta_bin', 'phi_bin'], inplace=True)
    
