"""GHP Parser - extract operational data from Excel"""
import pandas as pd
import re
from typing import List, Dict


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
        flight_match = re.search(r'QG\d+', str(route_str))
        if not flight_match:
            continue
        flight_no = flight_match.group(0)
        
        # Parse route: extract 3-letter codes
        routes = re.findall(r'\b([A-Z]{3})\b', str(route_str))
        if len(routes) < 2:
            continue
        origin, destination = routes[0], routes[1]
        
        # Parse date: "01/04" -> assume year from filename
        date_parts = str(date_str).split('/')
        if len(date_parts) == 2:
            day, month = date_parts
            year = '2026'  # ponytail: from filename, parse later if needed
            flight_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            continue
        
        records.append({
            'flight_number': flight_no,
            'origin': origin,
            'destination': destination,
            'flight_date': flight_date,
            'std': str(std) if pd.notna(std) else '',
            'atd': str(atd) if pd.notna(atd) else '',
            'aircraft': str(aircraft) if pd.notna(aircraft) else '',
        })
    
    return records
