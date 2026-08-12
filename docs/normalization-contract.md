# Normalization Contract

**Project:** Automated Flight Schedule Reporting System  
**Date:** 2026-08-12

## Flight Number

- **Input:** `QG 123`, `QG-123`, `qg123`
- **Output:** `QG123`
- **Rule:** Uppercase, strip spaces/hyphens, preserve alphanumeric only

## Route

- **Input:** `sub-cgk`, `SUB - CGK`, `SUB/CGK`
- **Output:** `SUB-CGK`
- **Rule:** Uppercase, normalize to `ORIGIN-DESTINATION`, strip whitespace

## Date

- **Input:** Various formats in WTT/PPRP/GHP
- **Output:** `YYYY-MM-DD` (ISO 8601)
- **Rule:** Parse local format, convert to ISO string for storage

## Time

- **Input:** Local time (WIB assumed unless stated)
- **Output:** `HH:MM` 24-hour format
- **Rule:** Store as local time string, explicit timezone policy: WIB (UTC+7)

## Matching Key

```python
key = f"{flight_num}|{flight_date}|{origin}|{destination}"
# Example: "QG123|2026-03-15|SUB|CGK"
```

## Project Identity

```python
project = {
    "project_id": str,         # User-defined or auto-generated
    "period": str,             # e.g., "Winter 2026", "S26"
    "year": int,               # 2026
    "month": int,              # 1-12
    "template_path": str,      # Path to final output template
}
```

## Version Identity

```python
version = {
    "parent_version_id": int | None,  # NULL for initial WTT row
    "version_number": int,             # Sequential: 1, 2, 3...
    "is_active": bool,                 # Only latest version = True
    "pprp_letter": str | None,         # From PPRP if applicable
    "created_at": datetime,
}
```
