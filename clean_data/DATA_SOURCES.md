# DATA_SOURCES.md — provenance for clean_data/

This document explains exactly what raw data and scripts produced the two
CSV files in this folder. It only describes what was actually run in this
session — nothing here is aspirational or planned.

## Repository cloned

- **URL:** https://github.com/niosh-mining/elkcreek.git
- **Branch:** main
- **Commit cloned:** `e08af5c89a3ac440458d2ac93fe40eb7996a33ea`
- **Commit date:** 2026-08-20 15:47:22 -0700
- **Local clone path:** `elkcreek/` (project root)

All raw file paths below are relative to `elkcreek/`.

---

## 1. elkcreek_source_audit.csv

**Built from:** every file in these four raw folders —

| Source folder | File type | Files used |
|---|---|---|
| `data/raw/events/rocksigma_events/` | `*.parquet` | 32 |
| `data/raw/events/ims_events/` | `*.parquet` | 42 |
| `data/raw/instrumentation/closures_and_mpbx_extensometers/` | `*.xlsx` | 5 (all sheets in each, 15 sheets total) |
| `data/raw/instrumentation/borehole_pressure_cells_and_string_pots/` | `*.xlsx` | 6 (all sheets in each, 18 sheets total) |

**Produced by:** `elkcreek/audit_sources.py`

**What the script does, in plain terms:** it lists every file in the four
folders above. For each parquet file, it reads it directly with pandas,
looks for a column whose name contains "date"/"time"/"timestamp" (or
failing that, a column already stored as a real datetime), and records the
row count, column count, and the min/max value of that date column. For
each Excel file, it opens every sheet and scans the first 20 rows to find
the header row automatically — it picks whichever of those rows has the
most non-empty cells, since a title row typically has only one filled
cell and the real header row has one filled cell per column. It then reads
the sheet using that detected header row and records the same statistics
(row count, column count, date column, date range). No values are
transformed, joined, or computed here — this file is a pure inventory.

**Output columns:**

| Column | Meaning |
|---|---|
| `file` | Path of the source file, relative to `elkcreek/data/raw/` |
| `sheet` | Excel sheet name (blank for parquet files) |
| `header_row` | 0-indexed row number auto-detected as the real header row |
| `rows` | Number of data rows found in that file/sheet |
| `n_cols` | Number of columns found |
| `date_col` | Name of the column identified as the date/time column |
| `start_date` | Earliest date value found in that column |
| `end_date` | Latest date value found in that column |

**Row count:** 107 rows total (32 rocksigma + 42 ims + 15 closures/MPBX
sheets + 18 BPC sheets — most Excel sheets beyond "Sheet1" in each
workbook are empty and show up as 0-row entries, which is expected: each
workbook in this dataset only uses its first sheet).

---

## 2. elkcreek_precursor_features.csv

**Built from:**

| Source folder | File type | Files used | Filter applied |
|---|---|---|---|
| `data/raw/events/rocksigma_events/` | `*.parquet` | 32 | columns `Date`, `ML` only |
| `data/raw/events/ims_events/` | `*.parquet` | 42 | columns `Date`, `Mag Local` only |
| `data/raw/instrumentation/closures_and_mpbx_extensometers/` | `*.xlsx` | 4 of the 5 files — only filenames matching `*closure stations measurements*.xlsx`; the 1 MPBX extensometer file was deliberately excluded (different instrument, multi-block date columns) | columns containing "closure" in the name, averaged per reading |
| `data/raw/instrumentation/borehole_pressure_cells_and_string_pots/` | `*.xlsx` | 6 | columns containing "pressure" in the name, averaged per reading |

**Produced by:** `elkcreek/build_features.py`

**What the script does, in plain terms:**

1. **Closure rate:** for each of the 4 closure-station files, it
   auto-detects the header row the same way as the audit script, pulls out
   every reading's timestamp and the average of all "closure" columns in
   that row, and tags it with a "site" name parsed from the filename
   (e.g. `1 North Inby closure stations measurements.xlsx` → site
   `1 North Inby`). It then sorts each site's readings by time and
   computes the rate of change (inches/day) between each reading and the
   one before it, and separately, between each reading and the one after
   it (used for the label — see below).
2. **BPC pressure rate:** same idea for the 6 borehole-pressure-cell
   files — average of all "pressure" columns per reading, tagged with a
   site parsed from the filename (the "Panel N" suffix is stripped so BPC
   readings roll up to the same site key as the closure files, e.g.
   `2 North Inby Panel 1 BPC...` and `2 North Inby closure stations...`
   both become site `2 North Inby`). Multiple BPC panel files that map to
   the same site are averaged together per day. Then day-over-day rate of
   change is computed the same way as closures.
3. **Seismic activity:** all 32 rocksigma files and all 42 ims files are
   concatenated into one combined events table (rocksigma's `ML` column
   and ims's `Mag Local` column are both renamed to a common `magnitude`
   column so they can sit in the same table). This combined table is
   grouped by calendar day to get a daily event count and daily mean
   magnitude — for the whole mine, not per site (see limitation below).
4. **Assembly:** for every actual closure reading (54 of them across the
   4 sites), the script attaches the most recently known daily seismic
   count/magnitude and the most recently known BPC pressure rate for that
   site, using an "as-of" join — i.e. it only pulls information dated at
   or before that closure reading's own timestamp, so nothing from the
   future leaks into the feature values.
5. **Label:** it compares the closure rate at each reading to the closure
   rate at the *next* reading. If the next reading's rate is faster
   (larger magnitude of change) than the current one by more than a small
   threshold (0.01 in/day), the label is 1 ("closure accelerated by the
   next reading"); otherwise 0. If there's no next reading for that site
   (i.e. it's the last reading), the label is left blank.

**Output columns:**

| Column | Meaning |
|---|---|
| `site` | Mine panel name parsed from the source filename (one of: `1 North Inby`, `1 North Outby`, `2 North Inby`, `2 North Outby`) |
| `date` | Timestamp of an actual closure-station reading |
| `seismic_event_rate` | Count of combined rocksigma+ims seismic events recorded mine-wide on the most recent day at or before this reading |
| `mean_magnitude` | Mean magnitude of those same mine-wide events |
| `closure_rate` | Rate of closure movement (inches/day) between this reading and the previous reading at this site |
| `bpc_pressure_rate` | Rate of change in mean borehole pressure (psi/day) at this site, most recently known at or before this reading |
| `label_closure_accel_next` | 1 if closure accelerated by the next actual reading at this site, 0 if not, blank if there was no next reading |

**Row count:** 54 rows (one per actual closure-station reading across the
4 sites: 9 + 11 + 19 + 15). 46 of the 54 rows have a non-blank label.

**Known limitations (carried over from when this table was built):**

- **Seismicity is mine-wide, not per-site.** Assigning individual seismic
  events to a specific panel would require the mine's CAD/geometry data
  (the elkcreek repo has scripts for this — `a020_filter_events.py`
  through `a050_add_longwall_info.py` — but they depend on heavier tooling
  like `pyrocko` and were not run in this session). As a result, all 4
  sites share the same `seismic_event_rate`/`mean_magnitude` value for any
  given as-of date.
- **The label is "accelerated by the next actual reading," not a fixed
  6-24-hour window.** Closure-station readings in this dataset are sparse
  and irregular — roughly weekly, sometimes with gaps of multiple weeks —
  so there usually isn't a reading exactly 6-24 hours later to compare
  against. The label instead compares each reading to whichever reading
  came next chronologically, which can be anywhere from a day to a few
  weeks later.

---

## 3. Provenance chain

```
GitHub: niosh-mining/elkcreek.git
commit e08af5c89a3ac440458d2ac93fe40eb7996a33ea
        |
        |-- data/raw/events/rocksigma_events/*.parquet (32 files)  --+
        |-- data/raw/events/ims_events/*.parquet (42 files)        --+--> audit_sources.py --> clean_data/elkcreek_source_audit.csv
        |-- data/raw/instrumentation/closures_and_mpbx_extensometers/*.xlsx (5 files, all sheets) --+
        |-- data/raw/instrumentation/borehole_pressure_cells_and_string_pots/*.xlsx (6 files, all sheets) --+
        |
        |-- data/raw/events/rocksigma_events/*.parquet  [Date, ML]              --+
        |-- data/raw/events/ims_events/*.parquet  [Date, Mag Local]             --+--> combined "events" table --> daily count/mean --> seismic_event_rate, mean_magnitude
        |-- data/raw/instrumentation/closures_and_mpbx_extensometers/
        |       *closure stations measurements*.xlsx (4 of 5 files, "closure" columns) --> per-site closure readings --> closure_rate
        |-- data/raw/instrumentation/borehole_pressure_cells_and_string_pots/
        |       *.xlsx (6 files, "pressure" columns)                            --> per-site daily pressure --> bpc_pressure_rate
        |
        +-- (closure_rate at reading N vs reading N+1) --> label_closure_accel_next
                                                            |
                                                    build_features.py --> clean_data/elkcreek_precursor_features.csv
```

Column-level trace for `elkcreek_precursor_features.csv`:

| Output column | Traces back to |
|---|---|
| `site` | Filename of a `*closure stations measurements*.xlsx` or BPC `*.xlsx` file |
| `date` | Detected date column in a closure-station Excel file |
| `seismic_event_rate` | `Date` column across all rocksigma + ims parquet files, grouped by day |
| `mean_magnitude` | `ML` (rocksigma) / `Mag Local` (ims) columns, grouped by day |
| `closure_rate` | Columns containing "closure" in a `*closure stations measurements*.xlsx` file |
| `bpc_pressure_rate` | Columns containing "pressure" in a BPC `*.xlsx` file |
| `label_closure_accel_next` | Derived from `closure_rate` at consecutive readings — not a raw source column |
