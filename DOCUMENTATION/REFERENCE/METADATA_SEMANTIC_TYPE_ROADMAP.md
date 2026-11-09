# TASKS

## Metadata semantic type system

This document records the proposed direction for restructuring and documenting the Stage 1 metadata outputs. It is intentionally placed at the repository root so that the work remains visible before implementation begins.

The immediate objective is **not** to change the existing metadata CSV files. The first goal is to define a semantic schema above the current storage representation, so that code can understand whether a group of CSV columns represents a scalar, flag, timestamp, vector, distribution, matrix, categorical value, or identifier.

## Motivation

The current metadata system contains scientifically meaningful structures, but CSV serialization flattens most of them into ordinary columns. This creates a distinction between:

- the **semantic type** of a metadata quantity; and
- the **physical CSV representation** used to store it.

For example:

- a Boolean may be stored as `0` or `1`;
- a coefficient vector may be stored as `name__0`, `name__1`, `name__2`, ...;
- a sampled efficiency curve may be stored as repeated bin-center, efficiency, and uncertainty columns;
- a histogram may be stored as one count column per bin;
- a conditional-probability matrix may be stored as one scalar column per matrix element;
- a timestamp may be stored as text.

The CSV layout is useful for interoperability and should remain available, but downstream tools should not need to infer scientific structure independently from column names every time.

## Proposed canonical metadata types

Use a deliberately small set of top-level semantic types.

### 1. `scalar`

A single numerical quantity.

Examples include:

- rates;
- efficiencies;
- percentages;
- thresholds;
- fit parameters;
- calibration constants;
- execution time;
- event counts;
- denominator counts or denominator seconds.

Integer/count quantities remain scalars, with their numerical representation described separately.

Example schema fragment:

```yaml
type: scalar
dtype: integer
unit: events
```

A duration should normally also remain a scalar:

```yaml
type: scalar
dtype: float
unit: s
semantic_role: duration
```

### 2. `digital`

A binary logical state.

Examples include:

- available / unavailable;
- enabled / disabled;
- passed / failed;
- converged / not converged;
- correction applied / not applied.

The CSV representation may remain `0` / `1`, even when the value originates in Python as `True` / `False`.

### 3. `datetime`

A date or timestamp.

Examples include execution timestamps and acquisition-related timestamps when they are stored in metadata.

The physical CSV representation may remain textual, but the semantic schema should identify the field as a datetime and define its format or timezone convention where relevant.

### 4. `vector`

An ordered one-dimensional collection of homogeneous values with no separate independent coordinate.

Typical examples are calibration or polynomial coefficient vectors.

A vector such as

```text
P1_s1_Q_FB_coeffs__0
P1_s1_Q_FB_coeffs__1
P1_s1_Q_FB_coeffs__2
```

should be understood semantically as one object rather than as three unrelated scalar quantities.

The term `vector` should be reserved for this case. A sampled function `(x_i, y_i)` should instead be represented as a distribution.

### 5. `distribution`

A one-dimensional structure in which values are associated with an independent coordinate, binning, quantile position, or similar ordering variable.

This type should cover:

- histograms;
- sampled curves;
- profiles;
- quantile scans;
- efficiency versus position;
- efficiency versus angle;
- categorical distributions when the categories define the independent coordinate.

Examples currently present in the metadata include the events-per-second histogram and the Task 4 efficiency-versus-X/Y/theta products.

A sampled efficiency object can conceptually be represented as:

```yaml
type: distribution
representation: sampled_curve
x: bin_center
y: efficiency
uncertainty: efficiency_uncertainty
```

A histogram can use the same top-level type with a different representation:

```yaml
type: distribution
representation: histogram
x: events_per_second
y: seconds
```

This avoids creating separate top-level types for every one-dimensional scientific structure while preserving their differences through attributes.

### 6. `matrix`

A genuinely two-dimensional structured object.

Examples include conditional-probability matrices such as streamer-contagion metadata, where rows and columns correspond to source and destination detector elements and each CSV field represents one matrix cell.

Conceptually:

```yaml
type: matrix
rows: source_strip
columns: destination_strip
values: conditional_probability
```

Undefined matrix elements should remain representable as missing values rather than being forced to zero.

### 7. `categorical`

A value selected from a finite or descriptive set of labels.

Examples include topology labels, status/reason codes, trigger categories, or other symbolic classifications.

Free descriptive text can also remain under this family initially unless a future use case requires a separate `text` top-level type.

### 8. `identifier`

A value whose main role is identity, provenance, or traceability rather than measurement.

Examples include:

- `filename_base`;
- `param_hash`;
- run/file identifiers;
- processing provenance identifiers.

These should not be treated as ordinary categorical measurements.

## Type attributes

The top-level type should remain small. Additional meaning should be expressed through attributes rather than by continually creating new fundamental types.

Candidate attributes include:

```text
dtype
unit
description
semantic_role
axis
uncertainty
representation
binning
labels
shape
source_task
source_metadata_family
```

Examples:

```yaml
type: scalar
dtype: float
unit: Hz
description: Global event rate
```

```yaml
type: distribution
representation: histogram
x_unit: events/s
y_unit: s
```

```yaml
type: vector
dtype: float
shape: [3]
semantic_role: calibration_coefficients
```

## Semantic object versus CSV storage

The schema should explicitly separate the logical object from its serialized columns.

Conceptually:

```text
CSV columns
    -> field-group recognition
    -> semantic metadata object
```

For example, columns of the form

```text
efficiency_vector_p1_x_bin_003_center_mm
efficiency_vector_p1_x_bin_003_eff
efficiency_vector_p1_x_bin_003_unc
```

belong to one sampled distribution, not three unrelated values.

The reconstructed object should look conceptually like:

```yaml
name: efficiency_vector_p1_x
type: distribution
representation: sampled_curve
x: [bin centers]
y: [efficiencies]
uncertainty: [uncertainties]
```

Likewise, flattened coefficient columns should reconstruct one vector, and flattened streamer-contagion fields should reconstruct one matrix.

## Important design decisions

### Keep CSV compatibility

Do not remove or immediately redesign the existing CSV metadata outputs. The current wide CSV representation is useful for inspection, interoperability, simple plotting, and historical compatibility.

The semantic schema should initially be an additional layer that describes how existing columns are grouped and interpreted.

### Do not confuse array shape with scientific meaning

Vectors, curves, histograms, and matrices may all be represented internally using arrays, but they are not semantically equivalent.

In particular:

- `(a0, a1, a2)` is a vector of coefficients;
- `(x_i, y_i)` is a sampled distribution/curve;
- `(bin_i, count_i)` is a histogram distribution;
- `M_ij` is a matrix.

This distinction should be preserved in the schema and plotting APIs.

### Treat uncertainty as metadata about a value

Uncertainty should not initially be a top-level type. It is normally associated with a scalar, vector element, distribution value, or other measured quantity.

For example, Task 4 efficiency curves naturally contain `x`, `efficiency`, and `uncertainty` fields within one distribution object.

### Treat counts and durations as scalar roles

Counts, denominator seconds, execution durations, and similar quantities should normally remain `scalar` values with appropriate `dtype`, `unit`, and/or `semantic_role` attributes.

### Preserve missingness

Missing or undefined values should remain distinguishable from physical zero. This is especially important for conditional probabilities, unavailable fits, unavailable efficiency bins, and other partially defined structures.

## Initial mapping to existing Stage 1 metadata

The current metadata output families already contain examples of nearly every proposed semantic type.

| Existing metadata concept | Proposed semantic type |
| --- | --- |
| rates, efficiencies, percentages, thresholds | `scalar` |
| event counts, denominator seconds, bin counts | `scalar` |
| availability / enabled flags | `digital` |
| execution timestamp | `datetime` |
| calibration coefficient arrays | `vector` |
| events-per-second rate histogram | `distribution` |
| efficiency versus X/Y/theta | `distribution` |
| quantile-response scan | `distribution` |
| trigger-type/count distributions | `distribution` or `categorical`, depending on use |
| streamer-contagion conditional probabilities | `matrix` |
| reason/status labels | `categorical` |
| selected TT lists and descriptive labels | `categorical` initially |
| `filename_base`, `param_hash`, run IDs | `identifier` |

This table is a starting point. Before implementation, every Task 0-5 metadata family should be audited and assigned explicitly.

## Implementation roadmap

### Phase 1: inventory

- Enumerate every metadata CSV produced by Stage 1 Tasks 0-5.
- Enumerate all columns generated by each metadata family.
- Record units, meanings, allowed missingness, and current physical representation.
- Detect repeated naming patterns that already encode vectors, distributions, matrices, uncertainties, and flags.

### Phase 2: schema specification

- Define a machine-readable schema format, probably YAML or JSON.
- Define the required fields for each top-level semantic type.
- Define optional attributes such as units, axis information, uncertainty, labels, and source task.
- Define naming and versioning rules for schema entries.
- Define how grouped CSV columns map to one semantic object.

### Phase 3: parser / reconstruction layer

Implement shared code that can read existing metadata CSV rows and reconstruct semantic objects without changing the metadata writers.

Target API direction:

```python
metadata = load_metadata(...)

metadata.scalar("global_rate")
metadata.digital("efficiency_metadata_available")
metadata.vector("P1_s1_Q_FB_coeffs")
metadata.distribution("efficiency_vector_p1_x")
metadata.matrix("streamer_contagion_streamer_to_signal_tt1234")
```

The exact API remains to be designed.

### Phase 4: validation

- Validate CSV columns against the semantic schema.
- Detect missing required components.
- Detect unexpected vector lengths or matrix shapes.
- Validate units and dtypes where practical.
- Preserve backward compatibility with historical metadata files.

### Phase 5: plotting integration

Refactor metadata plotters gradually so that they consume semantic objects instead of independently decoding column-name conventions.

This should simplify plotting code for:

- rates;
- histograms;
- efficiencies;
- calibration coefficients;
- activation and contagion matrices;
- future metadata products.

### Phase 6: documentation generation

Use the schema as a source for automatically generated metadata documentation, including:

- field name;
- semantic type;
- physical columns;
- unit;
- description;
- source task;
- missing-value rules;
- shape or binning information.

This would reduce divergence between implementation and documentation.

### Phase 7: optional future storage changes

Only after the semantic layer is stable should alternative physical storage formats be considered. Possible future directions include structured Parquet/Arrow fields, nested JSON, or a database representation.

No storage migration should be required merely to introduce the semantic schema.

## First concrete work package

When implementation begins, the first practical task should be a complete audit table for Stage 1 Tasks 0-5 with one row per semantic metadata object, not merely one row per CSV column.

Suggested columns for that audit table:

```text
object_name
source_task
metadata_family
semantic_type
dtype
unit
representation
physical_columns
shape_or_bins
uncertainty
missing_value_rule
description
```

The audit should be completed before changing writers or plotters. It will establish the authoritative map between the current metadata system and the proposed semantic model.

## Current proposed top-level hierarchy

```text
scalar
digital
datetime
vector
distribution
matrix
categorical
identifier
```

This hierarchy is intentionally compact. New top-level types should only be introduced when an existing type plus attributes cannot represent the scientific meaning cleanly.
