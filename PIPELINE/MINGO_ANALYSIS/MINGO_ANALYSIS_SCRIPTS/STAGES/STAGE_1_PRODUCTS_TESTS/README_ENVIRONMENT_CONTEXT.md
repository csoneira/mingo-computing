# TEST 3 environment context

`test_3_configurable_event_gates.py` writes `00_ENVIRONMENT_CONTEXT` beside
`00_CALIBRATION_CONTEXT`. The environment window follows the exact first and last selected Parquet-Lake
products. `environment_context_fraction` (default: `0.10`) adds 10% of the
selected duration on each side; a 24-hour selection therefore gets 2.4 hours
before and 2.4 hours after. The synchronized values used by every panel are retained in
`00_environment_data.csv`.

The generated files are:

- `01_environment_overview.png`: temperature, pressure, and humidity in three separate panels; HV and current in
  separate panels; the requested reduced-field proxy; trigger
  rates; and four gas-flow channels.
- `02_rates_and_reduced_field.png`: the reduced-field proxy, trigger rates,
  multiplexer rates, and coincidence-matrix rates.
- `03_odroid_disk_fill.png`: DiskFill1 and DiskFill2 together, with DiskFillX in
  a separate second panel.

In the sensor panel temperature is red, pressure is green, and humidity is blue.
External sensors use filled circles and internal sensors use open circles. The
colors are deliberately translucent so coincident readings remain visible.

The plotted reduced-field proxy follows the requested expression exactly:

```text
((hv_HVneg + hv_HVpos) / 2)
* sensors_ext_Temperature_ext
/ sensors_ext_Pressure_ext
```

It uses the numerical temperature stored by the logger; it does not silently
convert Celsius to kelvin or apply a gas-gap normalization. The CSV column is
named `derived_ReducedField` to make the derivation explicit.

The source is the Stage-1 daily LAB_LOG product under
`STAGE_1_PRODUCTS/LOG_DATA/OUTPUT_FILES`. Historical MINGO01 products can be
rebuilt from `OPERATIONS_RUNTIME/REMOTE_LOG_BACKUP`. That restoration now parses
HV, rates, external and internal sensors, Odroid, and flow logs; a daily CSV is
considered complete only when the full environment schema is present.
