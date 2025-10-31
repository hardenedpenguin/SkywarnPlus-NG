#!/usr/bin/env python3
"""
Parse CountyCodes.md and generate a JSON file with county code data.
"""

import json
import re
from pathlib import Path


def parse_county_codes(md_file: Path) -> dict:
    """Parse CountyCodes.md and return a structured dictionary."""
    counties = []
    current_state = None
    current_state_code = None
    
    with open(md_file, 'r') as f:
        lines = f.readlines()
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Check if this is a state header (## XX)
        state_match = re.match(r'^## ([A-Z]{2})$', line)
        if state_match:
            current_state_code = state_match.group(1)
            current_state = get_state_name(current_state_code)
            continue
        
        # Skip markdown table separators like |--------|------|
        if re.match(r'^\|[\s\-|]+\|$', line):
            continue
        
        # Check if this is a county table row
        # Expected format: | County Name | Code |
        match = re.match(r'\| (.+?) \| (.+?) \|$', line)
        if match:
            county_name = match.group(1).strip()
            county_code = match.group(2).strip()
            
            # Skip header row (if it matches "County | Code")
            if county_name.lower() in ['county', 'counties']:
                continue
            
            if county_name and county_code and current_state:
                counties.append({
                    'state': current_state,
                    'state_code': current_state_code,
                    'name': county_name,
                    'code': county_code,
                    'search_terms': county_name.lower(),
                    'display': f"{county_name}, {current_state_code}"
                })
    
    return counties


def get_state_name(state_code: str) -> str:
    """Convert state code to full state name."""
    states = {
        'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
        'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
        'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
        'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
        'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
        'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
        'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
        'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
        'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
        'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
        'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
        'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
        'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia'
    }
    return states.get(state_code, state_code)


def main():
    """Main entry point."""
    # Get script directory
    script_dir = Path(__file__).parent.resolve()
    repo_root = script_dir.parent
    
    # Set up file paths
    md_file = repo_root / 'CountyCodes.md'
    output_file = repo_root / 'src' / 'skywarnplus_ng' / 'web' / 'static' / 'county_codes.json'
    
    if not md_file.exists():
        print(f"Error: CountyCodes.md not found at {md_file}")
        return 1
    
    # Parse the county codes
    print(f"Parsing {md_file}...")
    counties = parse_county_codes(md_file)
    
    print(f"Found {len(counties)} counties")
    
    # Write JSON output
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(counties, f, indent=2)
    
    print(f"Wrote county codes to {output_file}")
    
    # Print summary by state
    state_counts = {}
    for county in counties:
        state_code = county['state_code']
        state_counts[state_code] = state_counts.get(state_code, 0) + 1
    
    print("\nCounties by state:")
    for state_code in sorted(state_counts.keys()):
        print(f"  {state_code}: {state_counts[state_code]}")
    
    return 0


if __name__ == '__main__':
    exit(main())

