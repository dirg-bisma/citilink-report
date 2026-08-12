# Domain Glossary

**Project:** Automated Flight Schedule Reporting System  
**Date:** 2026-08-12

## Sources

| Term | Definition |
|------|------------|
| **WTT** | Working Time Table (PDF). Schedule baseline: flight number, route, aircraft, dates, ATD, ATA |
| **PPRP** | Perubahan Perencanaan Penerbangan (PDF). Official schedule changes: letter number, date, new flight date/time |
| **GHP** | Ground Handling Performance (Excel). Operational status: actual STD/ATD, delay codes, for dashboard only |
| **Template** | `form_realisasi_winter26.xlsx`. Rigid output format from airport authority |

## Schedule Fields

| Term | Definition |
|------|------------|
| **Flight Number** | Airline code + numeric (e.g., QG123). Normalized: uppercase, no separators |
| **Route** | Origin-Destination IATA pair (e.g., SUB-CGK). Normalized: uppercase |
| **STD** | Scheduled Time of Departure. Local time |
| **STA** | Scheduled Time of Arrival. Local time |
| **ATD** | Actual Time of Departure. Local time |
| **ATA** | Actual Time of Arrival. Local time |
| **Flight Date** | Operating date. Normalized: `YYYY-MM-DD` |

## Processing Concepts

| Term | Definition |
|------|------------|
| **Project** | Work unit: project ID + period/season + year + month + template |
| **Schedule Version** | Row lineage: parent version ID + version number + active flag |
| **Matching Key** | `flight_num + flight_date + origin + destination` |
| **Operational Flag** | `1` if GHP match found, `0` if no match |
| **Immutable Row** | Historical schedule version never updated or deleted |

## Source-of-Truth Matrix

| Data | Source |
|------|--------|
| Final report schedule context | WTT/PPRP |
| Final report ATD/ATA | WTT only (never GHP) |
| Final report operational flag `1/0` | GHP match via key |
| Dashboard STD/ATD | GHP only |
| Dashboard delay analysis | GHP delay fields |
