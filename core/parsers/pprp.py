"""PPRP Parser - extract schedule changes from official letter PDF"""
import pdfplumber
import re
from datetime import datetime
from typing import List, Dict


def parse_pprp(pdf_path: str) -> Dict:
    """Extract letter metadata and schedule changes from PPRP PDF"""
    
    with pdfplumber.open(pdf_path) as pdf:
        full_text = '\n'.join(p.extract_text() for p in pdf.pages)
        
        # Letter number
        letter_match = re.search(r'Nomor\s*:([A-Z0-9./-]+)', full_text)
        letter_number = letter_match.group(1).strip() if letter_match else ''
        
        # Letter date
        date_match = re.search(r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})', full_text)
        letter_date = date_match.group(1) if date_match else ''
        
        # Route
        route_match = re.search(r'Rute\s+([A-Z]+)\s+\(([A-Z]{3})\)\s*-\s*([A-Z]+)\s+\(([A-Z]{3})\)', full_text)
        origin = route_match.group(2) if route_match else ''
        destination = route_match.group(4) if route_match else ''
        
        # Schedule table
        flights = []
        for match in re.finditer(
            r'([A-Z]{3})-([A-Z]{3})\s+(\d{3})\s+\d+\s+(QG\d+)\s+(\d{2}:\d{2})\s+(\d{2}:\d{2})\s+([0-9-]{7})',
            full_text
        ):
            flights.append({
                'origin': match.group(1),
                'destination': match.group(2),
                'aircraft': match.group(3),
                'flight_number': match.group(4),
                'std': match.group(5),
                'sta': match.group(6),
                'day_pattern': match.group(7),
            })
        
        # Date range
        date_range = re.findall(r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})', full_text)
        start_date = date_range[-2] if len(date_range) >= 2 else ''
        end_date = date_range[-1] if len(date_range) >= 1 else ''
        
        return {
            'letter_number': letter_number,
            'letter_date': letter_date,
            'origin': origin,
            'destination': destination,
            'flights': flights,
            'start_date': start_date,
            'end_date': end_date,
        }
