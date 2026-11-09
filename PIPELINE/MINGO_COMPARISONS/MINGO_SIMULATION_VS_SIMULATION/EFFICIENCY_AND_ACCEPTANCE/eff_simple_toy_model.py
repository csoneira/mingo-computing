import pandas as pd
import numpy as np

# Define detector parameters
plane_size = 300  # mm, width and height of each plane
plane_distance = 120  # mm, separation between planes
plane_efficiencies = [0.92, 0.94, 0.93, 0.95]  # Efficiency of each plane
plane_positions = [1, 2, 3, 4]  # Positions of the four detector planes in arbitrary units

# Number of muons to simulate
n_muons = 100000

# Step 1: Generate random entry positions and angles for each muon
angles = np.random.uniform(-np.pi / 4, np.pi / 4, n_muons)  # Angles for each muon
entry_positions = np.random.uniform(0, 10, n_muons)  # Entry positions in arbitrary range

# Step 2: Calculate if each muon passes through each plane based on geometry and applies efficiency
detected_passes = {
    f"Plane {i+1}": [
        (entry_positions[j] + np.tan(angles[j]) * plane_positions[i] >= 0) and
        (entry_positions[j] + np.tan(angles[j]) * plane_positions[i] <= 10) and
        (np.random.rand() < plane_efficiencies[i])
        for j in range(n_muons)
    ]
    for i in range(4)
}

# Step 3: Convert detections into a DataFrame and determine detection patterns
detected_df = pd.DataFrame(detected_passes)
detected_df['Detection Pattern'] = detected_df.apply(
    lambda row: ''.join([str(i + 1) for i, detected in enumerate(row) if detected]), axis=1
)

# Step 4: Count occurrences of each detection pattern
patterns = ["1234", "123", "234", "124", "134"]
pattern_counts = {pattern: (detected_df['Detection Pattern'] == pattern).sum() for pattern in patterns}

# Step 5: Calculate corrected counts for each pattern using the original efficiencies
pattern_efficiencies_comp = {
    "1234": plane_efficiencies[0] * plane_efficiencies[1] * plane_efficiencies[2] * plane_efficiencies[3],
    "123": plane_efficiencies[0] * plane_efficiencies[1] * plane_efficiencies[2] * (1 - plane_efficiencies[3]),
    "234": (1 - plane_efficiencies[0]) * plane_efficiencies[1] * plane_efficiencies[2] * plane_efficiencies[3],
    "124": plane_efficiencies[0] * plane_efficiencies[1] * (1 - plane_efficiencies[2]) * plane_efficiencies[3],
    "134": plane_efficiencies[0] * (1 - plane_efficiencies[1]) * plane_efficiencies[2] * plane_efficiencies[3]
}

# Step 8: Compute the "Total Corrected Rate" using complementary efficiencies for the final row
pattern_efficiencies = {
    "1234": plane_efficiencies[0] * plane_efficiencies[1] * plane_efficiencies[2] * plane_efficiencies[3],
    "123": plane_efficiencies[0] * plane_efficiencies[1] * plane_efficiencies[2],
    "234": plane_efficiencies[1] * plane_efficiencies[2] * plane_efficiencies[3],
    "124": plane_efficiencies[0] * plane_efficiencies[1] * plane_efficiencies[3],
    "134": plane_efficiencies[0] * plane_efficiencies[2] * plane_efficiencies[3]
}

# corrected_counts = {
#     pattern: ( pattern_counts["1234"] + pattern_counts[pattern] ) / pattern_efficiencies[pattern] if pattern_efficiencies[pattern] != 0 else 0
#     for pattern in patterns
# }

corrected_counts = {
    pattern: ( pattern_counts[pattern] ) / pattern_efficiencies[pattern] if pattern_efficiencies[pattern] != 0 else 0
    for pattern in patterns
}

# Step 6: Calculate geometric factor using cos² distribution for acceptance
n_samples = 100000
cos2_angles = np.arccos(np.sqrt(np.random.uniform(0, 1, n_samples)))

plane_combinations = { "1234": 0, "123": 0, "234": 0, "124": 0, "134": 0 }

for theta in cos2_angles:
    passes_planes = [
        np.random.rand() < plane_efficiencies[0],
        np.random.rand() < plane_efficiencies[1],
        np.random.rand() < plane_efficiencies[2],
        np.random.rand() < plane_efficiencies[3]
    ]
    pattern = ''.join([str(i + 1) for i, pass_through in enumerate(passes_planes) if pass_through])
    if pattern in plane_combinations:
        plane_combinations[pattern] += 1

geometric_factors = {pattern: count / n_samples for pattern, count in plane_combinations.items()}

# Step 7: Apply geometric factor to the corrected counts for each pattern
geometric_adjusted_counts = {
    pattern: corrected_counts[pattern] / geometric_factors[pattern] if geometric_factors[pattern] != 0 else 0
    for pattern in patterns
}



corrected_counts_comp = {
    pattern: pattern_counts[pattern] / pattern_efficiencies_comp[pattern] if pattern_efficiencies_comp[pattern] != 0 else 0
    for pattern in patterns
}

total_geometric_corrected_rate_comp = sum(
    corrected_counts_comp[pattern] / geometric_factors[pattern] if geometric_factors[pattern] != 0 else 0
    for pattern in patterns
)

# Calculate relative error for the total corrected rate using complementary efficiencies
total_relative_error_geometric_comp = abs((total_geometric_corrected_rate_comp - n_muons) / n_muons) * 100

# Step 9: Create DataFrame for comparison with original calculations for each pattern
comparison_df = pd.DataFrame({
    "Pattern": patterns,
    "Observed Count": [pattern_counts[pattern] for pattern in patterns],
    "Corrected Count": [corrected_counts[pattern] for pattern in patterns],
    "Efficiency": [pattern_efficiencies[pattern] for pattern in patterns],
    "Geometric Factor": [geometric_factors[pattern] for pattern in patterns],
    "Geometric Adjusted Count": [geometric_adjusted_counts[pattern] for pattern in patterns],
    "Relative Error (%)": [abs(geometric_adjusted_counts[pattern] - n_muons) / n_muons * 100 for pattern in patterns]
})

# Add the final corrected rate row with complementary efficiencies
final_row = pd.DataFrame({
    "Pattern": ["Total Corrected Rate"],
    "Observed Count": [sum(pattern_counts.values())],
    "Corrected Count": [sum(corrected_counts_comp.values())],
    "Efficiency": [None],
    "Geometric Factor": [None],
    "Geometric Adjusted Count": [total_geometric_corrected_rate_comp],
    "Relative Error (%)": [total_relative_error_geometric_comp]
})

# Append the final row to the DataFrame
comparison_df = pd.concat([comparison_df, final_row], ignore_index=True)

# Display the final DataFrame
print(comparison_df)
