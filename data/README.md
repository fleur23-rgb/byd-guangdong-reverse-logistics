# Data

`raw/` contains the versioned V2.1 research case workbook. `processed/` is
generated from that workbook with `scripts/build_inputs.py` and is committed so
the optimization can run without Excel preprocessing.

The data are public-data estimates, spatial proxies, literature-calibrated
parameters, and scenario assumptions. They are not BYD operational records.
Facility coordinates use city-level proxies unless otherwise stated. The V2.1
arc table retains both the Haversine-derived proxy layer and the OSRM
`driving/car` road-distance layer. Official scenarios use OSRM; the proxy layer
is retained for comparison and diagnostics.
