#!/usr/bin/env python3
"""
Analyze which categories are worth checking for bike-relevance.
This helps optimize LLM API costs by pre-filtering.
"""

import json
from collections import defaultdict

# Load events
with open('all_events.json', 'r') as f:
    events = json.load(f)

# Category analysis
stats = defaultdict(lambda: {
    'total': 0,
    'with_description': 0,
    'without_description': 0
})

for event in events:
    cat = event['service_name']
    stats[cat]['total'] += 1
    
    if event.get('description') and event['description'].strip():
        stats[cat]['with_description'] += 1
    else:
        stats[cat]['without_description'] += 1

# Sort by total count
sorted_cats = sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True)

print("=" * 80)
print("CATEGORY ANALYSIS FOR BIKE-RELEVANCE FILTERING")
print("=" * 80)

# Calculate totals
total_events = len(events)
total_with_desc = sum(s['with_description'] for s in stats.values())
total_without_desc = sum(s['without_description'] for s in stats.values())

print(f"\n📊 Overall Statistics:")
print(f"   Total events: {total_events:,}")
print(f"   With description: {total_with_desc:,} ({total_with_desc/total_events*100:.1f}%)")
print(f"   Without description: {total_without_desc:,} ({total_without_desc/total_events*100:.1f}%)")

# Categorize by bike-relevance potential
DEFINITELY_EXCLUDE = {
    # Container/waste (never bike-infrastructure)
    'Altkleidercontainer voll',
    'Altkleidercontainer defekt',
    'Altkleidercontainer-Standort vermüllt',
    'Glascontainer voll',
    'Glascontainer defekt',
    'Glascontainer-Standort vermüllt',
    
    # Lighting (rarely bike-specific)
    'Leuchtmittel defekt',
    'Leuchtmittel tagsüber in Betrieb',
    'Lichtmast defekt',
    
    # Parking
    'Parkscheinautomat defekt',
    
    # Green spaces (unless path-related)
    'Brunnen',
    'Kölner Grün',
    'Spiel- und Bolzplätze',
    
    # Graffiti (cosmetic, not infrastructure)
    'Graffiti',
    
    # Scrap bikes/cars (objects, not infrastructure)
    'Schrottfahrräder',
    'Schrott-Kfz',
}

HIGH_POTENTIAL = {
    # Road surface (bike infrastructure!)
    'Defekte Oberfläche',
    'Straßenmarkierung',
    'Defekte Verkehrszeichen',
    
    # Bike-specific
    'Radfahrerampel defekt',
    
    # Barriers (often affect bikes)
    'Umlaufsperren / Drängelgitter',
    
    # Construction (can block bike paths)
    'Straßenbaustellen',
}

MEDIUM_POTENTIAL = {
    # Could affect shared spaces
    'Wilder Müll',
    'Gully verstopft',
    
    # Pedestrian infrastructure (often shared)
    'Fußgängerampel defekt',
    
    # Traffic lights (if on bike route)
    'Kfz-Ampel defekt',
    'Zu lange Rotzeit',
    'Zu kurze Grünzeit',
    'Schutzzeit zu kurz',
    'Keine grüne Welle',
}

print("\n" + "=" * 80)
print("🚴 HIGH POTENTIAL (Check with LLM)")
print("=" * 80)
high_total = 0
high_with_desc = 0
for cat in sorted_cats:
    name, data = cat
    if name in HIGH_POTENTIAL:
        high_total += data['total']
        high_with_desc += data['with_description']
        pct = data['with_description'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f"{name:40} {data['total']:5,} total | {data['with_description']:5,} with desc ({pct:5.1f}%)")

print(f"\n{'Subtotal HIGH':40} {high_total:5,} total | {high_with_desc:5,} with desc")

print("\n" + "=" * 80)
print("🤔 MEDIUM POTENTIAL (Check with LLM)")
print("=" * 80)
medium_total = 0
medium_with_desc = 0
for cat in sorted_cats:
    name, data = cat
    if name in MEDIUM_POTENTIAL:
        medium_total += data['total']
        medium_with_desc += data['with_description']
        pct = data['with_description'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f"{name:40} {data['total']:5,} total | {data['with_description']:5,} with desc ({pct:5.1f}%)")

print(f"\n{'Subtotal MEDIUM':40} {medium_total:5,} total | {medium_with_desc:5,} with desc")

print("\n" + "=" * 80)
print("❌ DEFINITELY EXCLUDE (Skip LLM)")
print("=" * 80)
exclude_total = 0
exclude_with_desc = 0
for cat in sorted_cats:
    name, data = cat
    if name in DEFINITELY_EXCLUDE:
        exclude_total += data['total']
        exclude_with_desc += data['with_description']
        pct = data['with_description'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f"{name:40} {data['total']:5,} total | {data['with_description']:5,} with desc ({pct:5.1f}%)")

print(f"\n{'Subtotal EXCLUDE':40} {exclude_total:5,} total | {exclude_with_desc:5,} with desc")

# Calculate LLM workload
llm_candidates = high_with_desc + medium_with_desc
total_with_desc = sum(s['with_description'] for s in stats.values())

print("\n" + "=" * 80)
print("💰 LLM API COST OPTIMIZATION")
print("=" * 80)
print(f"Total events with description:     {total_with_desc:6,} (100.0%)")
print(f"Pre-filtered (HIGH + MEDIUM):      {llm_candidates:6,} ({llm_candidates/total_with_desc*100:5.1f}%)")
print(f"Excluded by category:              {exclude_with_desc:6,} ({exclude_with_desc/total_with_desc*100:5.1f}%)")
print(f"Excluded (no description):         {total_without_desc:6,} ({total_without_desc/total_events*100:5.1f}%)")

reduction = (1 - llm_candidates / total_events) * 100
print(f"\n🎯 API Call Reduction: {reduction:.1f}% (only {llm_candidates/total_events*100:.1f}% of events need LLM)")

# Estimate costs (Gemini 2.5 Flash: $0.15 per 1M input tokens)
# Assuming ~500 tokens per event (category + description + prompt)
tokens_per_event = 500
total_tokens_if_all = total_with_desc * tokens_per_event
optimized_tokens = llm_candidates * tokens_per_event

cost_per_1m = 0.15
cost_if_all = (total_tokens_if_all / 1_000_000) * cost_per_1m
cost_optimized = (optimized_tokens / 1_000_000) * cost_per_1m

print(f"\n💵 Estimated API Costs (Gemini 2.5 Flash):")
print(f"   If checking all with desc: ${cost_if_all:.2f}")
print(f"   With pre-filtering:        ${cost_optimized:.2f}")
print(f"   Savings:                   ${cost_if_all - cost_optimized:.2f} ({(1-cost_optimized/cost_if_all)*100:.1f}%)")

print("\n" + "=" * 80)
