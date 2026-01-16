#!/usr/bin/env python3
"""
Import civic events from all_events.json to Supabase database.

This script:
1. Parses address strings into components
2. Enriches events with category hierarchy from CSV
3. Extracts media paths from URLs
4. Computes year and sequence fields
5. Bulk inserts to Supabase (skipping unmapped events)
"""

import json
import csv
import re
import os
from typing import Optional, Dict, List
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY in .env file")

# File paths
EVENTS_FILE = "all_events.json"
CATEGORIES_FILE = "sags_uns_categories_3level.csv"


def parse_address(address_string: str) -> Optional[Dict[str, Optional[str]]]:
    """
    Parse address string into components.

    Format: "{zip} {city}[ - {district}], {street} {number}"
    Examples:
        "50859 Köln - Lövenich, An der Ronne 174"
        "51103 Köln, Kalker Hauptstr. 78"

    Returns dict with: zip_code, city, district, street, house_number
    """
    pattern = r'^(\d{5})\s+([^,]+?)(?:\s+-\s+([^,]+))?,\s+(.+?)\s+(\S+)$'
    match = re.match(pattern, address_string)

    if match:
        return {
            'zip_code': match.group(1),
            'city': match.group(2),
            'district': match.group(3),  # Can be None
            'street': match.group(4),
            'house_number': match.group(5)
        }

    # Fallback for malformed addresses
    print(f"⚠️  Could not parse address: {address_string}")
    return None


def build_category_map(csv_path: str) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Build mapping from service_name to category hierarchy.

    Returns dict: service_name -> {category, subcategory, subcategory2}
    """
    category_map = {}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['subcategory2'] == 'none':
                # service_name matches subcategory
                category_map[row['subcategory']] = {
                    'category': row['category'],
                    'subcategory': row['subcategory'],
                    'subcategory2': None
                }
            else:
                # service_name matches subcategory2
                category_map[row['subcategory2']] = {
                    'category': row['category'],
                    'subcategory': row['subcategory'],
                    'subcategory2': row['subcategory2']
                }

    return category_map


def enrich_event(event: dict, category_map: Dict) -> Optional[Dict[str, Optional[str]]]:
    """
    Enrich event with category hierarchy from mapping.

    Returns category dict or None if unmapped (will be skipped).
    """
    service_name = event['service_name']

    # Try exact match
    if service_name in category_map:
        return category_map[service_name]

    # Return None for unmapped events (will be skipped)
    return None


def extract_media_path(media_url: Optional[str]) -> Optional[str]:
    """
    Extract relative media path from full URL.

    Example:
        Input: "https://sags-uns.stadt-koeln.de/system/files/2026-01/IMG_3744.jpeg"
        Output: "2026-01/IMG_3744.jpeg"
    """
    if not media_url:
        return None

    match = re.search(r'/files/(.+)$', media_url)
    return match.group(1) if match else None


def extract_year_sequence(service_request_id: str) -> tuple[int, int]:
    """
    Extract year and sequence from service_request_id.

    Example: "1039-2026" -> (2026, 1039)
    """
    sequence, year = service_request_id.split('-')
    return int(year), int(sequence)


def process_events(events: List[dict], category_map: Dict) -> tuple[List[dict], int]:
    """
    Process all events: parse, enrich, transform.

    Returns: (processed_events, skipped_count)
    """
    processed_events = []
    skipped_count = 0
    malformed_addresses = []

    for event in events:
        # Enrich categories
        categories = enrich_event(event, category_map)

        # Skip unmapped events
        if categories is None:
            skipped_count += 1
            continue

        # Parse address
        address_parts = parse_address(event['address_string'])
        if address_parts is None:
            malformed_addresses.append(event['address_string'])

        # Extract year and sequence
        year, sequence = extract_year_sequence(event['service_request_id'])

        # Build processed record
        processed_event = {
            'service_request_id': event['service_request_id'],
            'title': event['title'],
            'description': event.get('description'),
            'requested_at': event['requested_datetime'],
            'status': event['status'],
            'lat': float(event['lat']),
            'lon': float(event['long']),
            'address_string': event['address_string'],
            'zip_code': address_parts['zip_code'] if address_parts else None,
            'city': address_parts['city'] if address_parts else None,
            'district': address_parts['district'] if address_parts else None,
            'street': address_parts['street'] if address_parts else None,
            'house_number': address_parts['house_number'] if address_parts else None,
            'category': categories['category'],
            'subcategory': categories['subcategory'],
            'subcategory2': categories['subcategory2'],
            'service_name': event['service_name'],
            'media_path': extract_media_path(event.get('media_url')),
            'year': year,
            'sequence_number': sequence
        }

        processed_events.append(processed_event)

    if malformed_addresses:
        print(f"\n⚠️  Found {len(malformed_addresses)} malformed addresses (will store with NULL components):")
        for addr in malformed_addresses[:5]:  # Show first 5
            print(f"   - {addr}")
        if len(malformed_addresses) > 5:
            print(f"   ... and {len(malformed_addresses) - 5} more")

    return processed_events, skipped_count


def bulk_insert_events(supabase: Client, events: List[dict], batch_size: int = 1000):
    """
    Insert events in batches to avoid timeout/size limits.
    """
    total = len(events)
    print(f"\n📤 Inserting {total} events in batches of {batch_size}...")

    for i in range(0, total, batch_size):
        batch = events[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        try:
            supabase.table('events').insert(batch).execute()
            print(f"   ✅ Batch {batch_num}/{total_batches} inserted ({len(batch)} events)")
        except Exception as e:
            print(f"   ❌ Batch {batch_num} failed: {e}")
            raise


def main():
    """Main import workflow."""
    print("=" * 60)
    print("EVENT REGISTRY IMPORT")
    print("=" * 60)

    # 1. Load data
    print("\n📂 Loading data files...")
    with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
        raw_events = json.load(f)
    print(f"   ✅ Loaded {len(raw_events)} events from {EVENTS_FILE}")

    category_map = build_category_map(CATEGORIES_FILE)
    print(f"   ✅ Loaded {len(category_map)} category mappings from {CATEGORIES_FILE}")

    # 2. Process events
    print("\n⚙️  Processing events...")
    processed_events, skipped_count = process_events(raw_events, category_map)
    print(f"   ✅ Processed {len(processed_events)} events")
    print(f"   ⚠️  Skipped {skipped_count} unmapped events ({skipped_count/len(raw_events)*100:.2f}%)")

    # 3. Connect to Supabase
    print(f"\n🔌 Connecting to Supabase...")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"   ✅ Connected to {SUPABASE_URL}")

    # 4. Bulk insert
    bulk_insert_events(supabase, processed_events)

    # 5. Summary
    print("\n" + "=" * 60)
    print("✅ IMPORT COMPLETE")
    print("=" * 60)
    print(f"📊 Statistics:")
    print(f"   - Total events processed: {len(raw_events)}")
    print(f"   - Successfully imported: {len(processed_events)}")
    print(f"   - Skipped (unmapped): {skipped_count}")
    print(f"   - Success rate: {len(processed_events)/len(raw_events)*100:.2f}%")
    print("\n💡 Next steps:")
    print("   1. Run validation queries (see migrations/002_validate_data.sql)")
    print("   2. Check data quality in Supabase dashboard")
    print("   3. Test geospatial queries")


if __name__ == "__main__":
    main()
