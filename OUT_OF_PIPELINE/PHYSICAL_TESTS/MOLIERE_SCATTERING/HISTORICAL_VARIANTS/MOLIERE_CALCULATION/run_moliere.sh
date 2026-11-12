#!/bin/bash
# Purpose: Run the Molière-scattering calculation repeatedly for the configured sample.

for i in {1..1000}
do
    echo "Run #$i"
    python3 ./moliere.py
done
