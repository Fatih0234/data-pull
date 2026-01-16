#!/usr/bin/env python3
"""
Clean Data Fetcher for Stadt Köln Open311 API

Efficient fetching strategy to get ALL events from a date range.

Strategy:
1. Fetch using date ranges (fast, gets ~80%)
2. Identify missing IDs by checking sequential gaps
3. Fetch missing IDs directly (gets remaining 20%)

This solves the API's quirky behavior where date queries miss ~20% of records.
"""

import json
import httpx
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Set, Optional
from collections import defaultdict
import time


# Configuration
API_BASE_URL = "https://sags-uns.stadt-koeln.de/georeport/v2"
TIMEOUT = 30
MAX_WORKERS = 10  # Parallel requests for ID-based fetching


class CleanFetcher:
    """Clean, efficient data fetcher"""

    def __init__(self, start_date: str, end_date: str):
        """
        Initialize fetcher.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        self.start_date = date.fromisoformat(start_date)
        self.end_date = date.fromisoformat(end_date)
        self.client = httpx.Client(timeout=TIMEOUT)
        self.all_events = {}  # Dict: service_request_id -> event
        self.stats = {
            "date_fetch_count": 0,
            "id_fetch_count": 0,
            "total_events": 0,
            "date_fetch_duration": 0,
            "id_fetch_duration": 0
        }

    def close(self):
        """Close HTTP client"""
        self.client.close()

    def fetch_by_date_range(self, start: date, end: date) -> List[Dict[str, Any]]:
        """
        Fetch events for a specific date range.

        Args:
            start: Start date
            end: End date

        Returns:
            List of events
        """
        url = f"{API_BASE_URL}/requests.json"
        events = []
        page = 1

        print(f"  Fetching {start} to {end}...", end=" ", flush=True)

        while True:
            params = {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "extensions": "true",
                "page": page
            }

            try:
                response = self.client.get(url, params=params)
                response.raise_for_status()
                page_events = response.json()

                if not page_events:
                    break

                events.extend(page_events)
                page += 1

                if len(page_events) < 100:
                    break

            except Exception as e:
                print(f"\n  ⚠️  Error on page {page}: {e}")
                break

        print(f"({len(events)} events)")
        return events

    def phase1_date_based_fetch(self):
        """
        Phase 1: Fetch using date ranges.
        Split into 7-day windows for efficiency.
        """
        print("\n" + "="*80)
        print("PHASE 1: Date-Based Fetching")
        print("="*80)
        print(f"Date range: {self.start_date} to {self.end_date}")

        # Split into 7-day windows
        window_days = 7
        current = self.start_date
        windows = []

        while current <= self.end_date:
            window_end = min(current + timedelta(days=window_days - 1), self.end_date)
            windows.append((current, window_end))
            current = window_end + timedelta(days=1)

        print(f"Split into {len(windows)} windows of ~{window_days} days each\n")

        # Fetch each window
        start_time = time.time()

        for i, (start, end) in enumerate(windows, 1):
            print(f"  Window {i}/{len(windows)}: ", end="")
            events = self.fetch_by_date_range(start, end)

            # Store events
            for event in events:
                event_id = event.get("service_request_id")
                if event_id:
                    self.all_events[event_id] = event

        self.stats["date_fetch_duration"] = time.time() - start_time
        self.stats["date_fetch_count"] = len(self.all_events)

        print(f"\n✓ Phase 1 complete: {len(self.all_events)} unique events")
        print(f"  Duration: {self.stats['date_fetch_duration']:.1f} seconds")

    def analyze_missing_ids(self) -> Dict[str, Set[int]]:
        """
        Analyze which IDs are missing by checking for gaps in the sequence.

        Returns:
            Dictionary: {year -> set of missing IDs}
        """
        print("\n" + "="*80)
        print("ANALYZING MISSING IDs")
        print("="*80)

        # Group existing IDs by year
        ids_by_year = defaultdict(set)
        for event_id in self.all_events.keys():
            if "-" in event_id:
                parts = event_id.split("-")
                id_num = int(parts[0])
                year = parts[1]
                ids_by_year[year].add(id_num)

        # Find missing IDs for each year
        missing_by_year = {}

        for year in sorted(ids_by_year.keys()):
            ids = ids_by_year[year]
            if not ids:
                continue

            max_id = max(ids)
            min_id = min(ids)

            # All IDs that should exist in this range
            expected = set(range(1, max_id + 1))

            # Missing IDs
            missing = expected - ids
            missing_by_year[year] = missing

            coverage_pct = (len(ids) / len(expected)) * 100 if expected else 100
            print(f"  Year {year}: {len(ids)} events (IDs 1-{max_id})")
            print(f"    Coverage: {coverage_pct:.1f}% ({len(missing)} missing IDs)")

        return missing_by_year

    def fetch_by_id(self, id_num: int, year: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific event by ID.

        Args:
            id_num: ID number
            year: Year

        Returns:
            Event dict or None if not found
        """
        service_request_id = f"{id_num}-{year}"
        url = f"{API_BASE_URL}/requests/{service_request_id}.json"

        try:
            response = self.client.get(url)
            response.raise_for_status()
            events = response.json()

            # API returns a list with one event
            if events and len(events) > 0:
                return events[0]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Event doesn't exist (was deleted)
                return None
            print(f"\n  ⚠️  Error fetching {service_request_id}: {e}")

        except Exception as e:
            print(f"\n  ⚠️  Error fetching {service_request_id}: {e}")

        return None

    def phase2_id_based_fetch(self, missing_by_year: Dict[str, Set[int]]):
        """
        Phase 2: Fetch missing events by ID.

        Args:
            missing_by_year: Dictionary of {year -> set of missing IDs}
        """
        print("\n" + "="*80)
        print("PHASE 2: ID-Based Gap Filling")
        print("="*80)

        total_missing = sum(len(ids) for ids in missing_by_year.values())

        if total_missing == 0:
            print("✓ No missing IDs - date-based fetch got everything!")
            return

        print(f"Fetching {total_missing} missing events...\n")

        start_time = time.time()
        fetched_count = 0
        not_found_count = 0

        for year in sorted(missing_by_year.keys()):
            missing_ids = sorted(missing_by_year[year])

            if not missing_ids:
                continue

            print(f"  Year {year}: {len(missing_ids)} missing IDs...")

            year_fetched = 0
            year_not_found = 0

            # Process in batches of 100 for progress reporting
            batch_size = 100
            total_ids = len(missing_ids)

            for i in range(0, total_ids, batch_size):
                batch = missing_ids[i:i+batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_ids + batch_size - 1) // batch_size

                print(f"    Batch {batch_num}/{total_batches} (IDs {batch[0]}-{batch[-1]})...", end=" ", flush=True)

                batch_fetched = 0
                batch_not_found = 0

                for id_num in batch:
                    try:
                        event = self.fetch_by_id(id_num, year)

                        if event:
                            service_request_id = event.get("service_request_id")
                            self.all_events[service_request_id] = event
                            batch_fetched += 1
                            year_fetched += 1
                            fetched_count += 1
                        else:
                            batch_not_found += 1
                            year_not_found += 1
                            not_found_count += 1

                    except Exception as e:
                        print(f"\n      Error fetching {id_num}-{year}: {e}")
                        batch_not_found += 1
                        year_not_found += 1
                        not_found_count += 1

                print(f"fetched {batch_fetched}, not found {batch_not_found}")

            print(f"    Year {year} total: fetched {year_fetched}, not found {year_not_found}")

        self.stats["id_fetch_duration"] = time.time() - start_time
        self.stats["id_fetch_count"] = fetched_count

        print(f"\n✓ Phase 2 complete: {fetched_count} additional events fetched")
        print(f"  Duration: {self.stats['id_fetch_duration']:.1f} seconds")
        print(f"  Not found: {not_found_count} (likely deleted from API)")

    def save_to_file(self, filename: str = "all_events.json"):
        """
        Save all events to JSON file.

        Args:
            filename: Output filename
        """
        events_list = list(self.all_events.values())

        # Sort by requested_datetime (most recent first)
        events_list.sort(
            key=lambda e: e.get("requested_datetime", ""),
            reverse=True
        )

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(events_list, f, indent=2, ensure_ascii=False)

        print(f"✓ Saved {len(events_list)} events to {filename}")

    def print_summary(self):
        """Print final summary"""
        print("\n" + "="*80)
        print("FETCH SUMMARY")
        print("="*80)

        total_duration = self.stats["date_fetch_duration"] + self.stats["id_fetch_duration"]

        print(f"Date range: {self.start_date} to {self.end_date}")
        print(f"\nPhase 1 (Date-based):")
        print(f"  Events fetched: {self.stats['date_fetch_count']}")
        print(f"  Duration: {self.stats['date_fetch_duration']:.1f}s")

        print(f"\nPhase 2 (ID-based gap filling):")
        print(f"  Events fetched: {self.stats['id_fetch_count']}")
        print(f"  Duration: {self.stats['id_fetch_duration']:.1f}s")

        print(f"\nTotal:")
        print(f"  Events: {len(self.all_events)}")
        print(f"  Duration: {total_duration:.1f}s")

        # Date range analysis
        if self.all_events:
            dates = [e.get("requested_datetime", "") for e in self.all_events.values()]
            dates = [d for d in dates if d]

            if dates:
                print(f"\nActual event date range:")
                print(f"  Earliest: {min(dates)}")
                print(f"  Latest: {max(dates)}")

        # Coverage by year
        years = defaultdict(int)
        for event_id in self.all_events.keys():
            if "-" in event_id:
                year = event_id.split("-")[1]
                years[year] += 1

        print(f"\nEvents by year:")
        for year in sorted(years.keys()):
            print(f"  {year}: {years[year]} events")

        print("="*80)


def main():
    """Main execution"""
    print("="*80)
    print("Clean Data Fetcher - Stadt Köln Open311 API")
    print("="*80)

    # Configuration
    START_DATE = "2025-01-01"
    END_DATE = date.today().isoformat()  # Today (2026-01-16)

    print(f"\nFetching events from {START_DATE} to {END_DATE}")
    print("This will take a few minutes...\n")

    fetcher = CleanFetcher(START_DATE, END_DATE)

    try:
        # Phase 1: Date-based fetching
        fetcher.phase1_date_based_fetch()

        # Analyze what's missing
        missing_by_year = fetcher.analyze_missing_ids()

        # Phase 2: Fill gaps with ID-based fetching
        fetcher.phase2_id_based_fetch(missing_by_year)

        # Save results
        print("\n" + "="*80)
        print("SAVING RESULTS")
        print("="*80)
        fetcher.save_to_file("all_events.json")

        # Save stats
        with open("fetch_stats.json", 'w', encoding='utf-8') as f:
            json.dump(fetcher.stats, f, indent=2)
        print("✓ Saved statistics to fetch_stats.json")

        # Print summary
        fetcher.print_summary()

        print("\n✅ Fetch complete!")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")

    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        raise

    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
