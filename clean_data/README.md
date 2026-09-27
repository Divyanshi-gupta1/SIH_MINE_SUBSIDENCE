# clean_data/

This folder is a tidy copy of the outputs from Part 1 of the project
(the elkcreek reference-data audit). Nothing here was regenerated —
these are plain copies of the files already produced in
`elkcreek/processed/`.

**Important: none of this is data from our own hardware.** It comes from
`niosh-mining/elkcreek`, a public dataset from an underground US coal mine
that used different sensor types (borehole pressure cells, wire
extensometers, seismic arrays) than our ESP32/LoRa surface mesh (tilt,
vibration, displacement/stretch, crack sensors). It's kept here only as a
**methodology reference** — to validate the general idea of detecting
precursor patterns before ground movement — not as training data for our
actual sensors. Real training data will come from `synthetic/` (Part 2,
shaped like our real hardware output) and eventually from the hardware
itself.

---

## elkcreek_source_audit.csv

An inventory of the raw elkcreek source files we looked at, one row per
file (or per sheet, for Excel files with multiple tabs).

| Column | Meaning |
|---|---|
| `file` | Path of the source file, relative to `elkcreek/data/raw/` |
| `sheet` | Excel sheet name (blank for parquet files, which don't have sheets) |
| `header_row` | Which row (0-indexed) the real column headers start on. Several of the Excel files have a title row and blank/metadata rows before the actual header, so this was auto-detected per sheet rather than assumed to be row 0 |
| `rows` | Number of data rows in that file/sheet |
| `n_cols` | Number of columns |
| `date_col` | Name of the column identified as the date/time column |
| `start_date` / `end_date` | Earliest and latest date found in that file/sheet |

Use this file to see what raw data exists and how much of it there is —
it's a map of the source material, not a dataset to train on directly.

## elkcreek_precursor_features.csv

A small engineered feature table (54 rows) built from the elkcreek raw
data, one row per actual closure-station reading at one of 4 mine panels
("sites").

| Column | Meaning |
|---|---|
| `site` | Mine panel name (e.g. "1 North Inby") |
| `date` | Timestamp of a closure-station reading |
| `seismic_event_rate` | Count of seismic events recorded mine-wide that day |
| `mean_magnitude` | Average magnitude of those seismic events |
| `closure_rate` | Rate of roof/floor closure movement (inches/day) between this reading and the previous one |
| `bpc_pressure_rate` | Rate of change in borehole pressure cell readings (psi/day) at that site |
| `label_closure_accel_next` | 1 if closure movement sped up (accelerated) by the *next* actual reading, 0 if not, blank if there wasn't a next reading to compare against |

**Known limitations of this table** (both are consequences of the source
data, not bugs):
- `seismic_event_rate` and `mean_magnitude` are mine-wide, not per-site —
  properly assigning each seismic event to a specific panel would require
  the mine's CAD/geometry data, which wasn't reproduced for this reference
  pass.
- The label is "accelerated by the next reading," not a fixed "6-24 hours
  ahead" window, because the real closure readings are sparse and
  irregular (roughly weekly, sometimes weeks apart). A true fixed-window
  label needs finer, regular sampling — which is exactly what our own
  hardware (and the Part 2 synthetic data standing in for it) provides.
