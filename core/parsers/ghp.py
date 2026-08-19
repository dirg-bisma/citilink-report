"""GHP Parser - extract operational data from Excel"""
import pandas as pd
import re
from typing import List, Dict


def detect_ghp_period(excel_path: str) -> int:
    """Detect month from GHP Excel date column (DD/MM)"""
    df = pd.read_excel(excel_path, header=None)
    for idx, row in df.iterrows():
        if idx < 7:
            continue
        date_str = row[0]
        if pd.isna(date_str):
            continue
        date_parts = str(date_str).strip().split('/')
        if len(date_parts) >= 2:
            try:
                month = int(date_parts[1])
                if 1 <= month <= 12:
                    return month
            except (ValueError, TypeError):
                continue
    raise ValueError("Tidak dapat mendeteksi bulan pada file GHP Excel.")


def parse_ghp(excel_path: str) -> List[Dict]:
    """Extract normalized operational records from GHP Excel"""
    df = pd.read_excel(excel_path, header=None)
    
    records = []
    for idx, row in df.iterrows():
        if idx < 7:  # Skip header rows
            continue
        
        date_str = row[0]
        route_str = row[1]
        aircraft = row[3]
        std = row[6]  # Scheduled departure
        atd = row[9]  # Actual departure
        
        if pd.isna(date_str) or pd.isna(route_str):
            continue
        
        # Parse flight number from route string
        flight_matches = re.findall(r'QG\d+', str(route_str))
        if not flight_matches:
            continue
            
        # Parse route: extract 3-letter codes
        routes = re.findall(r'\b([A-Z]{3})\b', str(route_str))
        if len(routes) < 2:
            continue
            
        # Jika ada multileg (misal: QG435 -QG486 /BPN -SUB -BDJ)
        # flight_matches = ['QG435', 'QG486']
        # routes = ['BPN', 'SUB', 'BDJ']
        # Pasangkan masing-masing flight dengan rutenya
        legs = []
        for i in range(min(len(flight_matches), len(routes) - 1)):
            legs.append({
                'flight': flight_matches[i],
                'origin': routes[i],
                'dest': routes[i+1]
            })
        
        # Parse date: "01/04" -> assume year from filename
        date_parts = str(date_str).split('/')
        if len(date_parts) == 2:
            day, month = date_parts
            year = '2026'  # ponytail: from filename, parse later if needed
            flight_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            continue
        
        for leg in legs:
            records.append({
                'flight_number': leg['flight'],
                'origin': leg['origin'],
                'destination': leg['dest'],
                'flight_date': flight_date,
                'std': str(std) if pd.notna(std) else '',
                'atd': str(atd) if pd.notna(atd) else '',
                'aircraft': str(aircraft) if pd.notna(aircraft) else '',
            })
    
    return records
