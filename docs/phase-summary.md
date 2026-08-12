# Phase 1 & 2 Summary

✅ **Phase 1: Discovery & Contract**
- Domain glossary: `docs/glossary.md`
- Normalization rules: `docs/normalization-contract.md`
- Decision log: `docs/decision-log.md`

✅ **Phase 2: Foundation**
- Django 6.1 + MySQL connected
- Models: `Project`, `SourceFile`, `ScheduleVersion`
- DB migrated, superuser created

✅ **Phase 3: Parsers**
- **WTT parser**: 842 flights from April 2026 WTT
- **PPRP parser**: Letter AU.012/47/3, 8 schedule changes
- **GHP parser**: 807 operational records from April 2026

## Parser Output

```python
# WTT
{'flight_number': 'QG460', 'origin': 'AAP', 'destination': 'SUB', 
 'flight_date': '2026-04-07', 'std': '7:50', 'sta': '10:30', 
 'aircraft': '320', 'atd': '7:50', 'ata': '10:30'}

# PPRP
{'letter_number': 'AU.012/47/3/DJPU-DAU-2026', 'flights': [...]}

# GHP
{'flight_number': 'QG172', 'origin': 'HLP', 'destination': 'SUB',
 'flight_date': '2026-04-01', 'std': '05:10', 'atd': '05:10'}
```

## Next: Phase 4
Schedule processing engine: version rows, PPRP changes, GHP matching, immutability.
