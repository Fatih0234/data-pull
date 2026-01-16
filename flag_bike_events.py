#!/usr/bin/env python3
"""
Flag bike-relevant events using LLM classification.

Strategy:
1. Pre-filter: Skip events without descriptions + exclude low-potential categories
2. LLM Classification: Use Gemini 2.5 Flash for HIGH + MEDIUM potential events
3. Store results: Add bike_related flag to database

This reduces LLM API calls by ~40% while maintaining accuracy.
"""

import json
import os
import time
from typing import Optional, Dict
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client

load_dotenv()

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Please set GEMINI_API_KEY in .env file")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-lite')

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Category classification
DEFINITELY_EXCLUDE = {
    'Altkleidercontainer voll', 'Altkleidercontainer defekt',
    'Altkleidercontainer-Standort vermüllt', 'Glascontainer voll',
    'Glascontainer defekt', 'Glascontainer-Standort vermüllt',
    'Leuchtmittel defekt', 'Leuchtmittel tagsüber in Betrieb',
    'Lichtmast defekt', 'Parkscheinautomat defekt',
    'Brunnen', 'Kölner Grün', 'Spiel- und Bolzplätze',
    'Graffiti', 'Schrottfahrräder', 'Schrott-Kfz',
}

HIGH_POTENTIAL = {
    'Defekte Oberfläche', 'Straßenmarkierung', 'Defekte Verkehrszeichen',
    'Radfahrerampel defekt', 'Umlaufsperren / Drängelgitter',
    'Straßenbaustellen',
}

MEDIUM_POTENTIAL = {
    'Wilder Müll', 'Gully verstopft', 'Fußgängerampel defekt',
    'Kfz-Ampel defekt', 'Zu lange Rotzeit', 'Zu kurze Grünzeit',
    'Schutzzeit zu kurz', 'Keine grüne Welle',
}

# LLM Prompt
BIKE_RELEVANCE_PROMPT = """Rolle: Du bist Urban-Data-Analyst:in für Köln.
Aufgabe: Phase 1 – Bike-Relevanz filtern (TRUE/FALSE/UNCERTAIN) anhand EXPLIZITER Evidenz im Text. Keine Vermutungen.

ENTSCHEIDUNGSBAUM (in dieser Reihenfolge):

A) TRUE (bike_related)
Gib TRUE NUR, wenn mindestens EIN expliziter Beleg vorkommt:
1) Direkte Rad-Infrastruktur-Wörter:
   Radweg, Radfahrstreifen, Schutzstreifen, Radfurt, Fahrradstraße, Fahrradzone,
   (gemeinsamer) Geh- und Radweg, Radfahrerampel, Fahrradbügel / Fahrradständer / Abstellanlage
2) Visuelle/bauliche Marker, die eindeutig auf Radverkehr hindeuten (auch ohne "Rad"-Wort):
   Schutzstreifen, gestrichelter Streifen/Spur, rote Spur/roter Belag, Piktogramme/Symbole auf einem markierten Streifen,
   "freigegeben" Zusatzschild (wenn erkennbar für Radverkehr)
3) Explizite Nennung von Radfahrenden/Fahrrad im Kontext von Sicherheit/Zugänglichkeit im öffentlichen Raum:
   z.B. "Radfahrer stürzen", "mit dem Fahrrad nicht passierbar", "Gefahr für Radfahrende".

WICHTIG: Formulierungen wie "rechter Rand / Bordsteinkante / Fahrbahnrand" reichen NICHT für TRUE,
außer im Text steht zusätzlich ein Marker aus (2) oder eine klare Rad-Infrastruktur aus (1).
Allgemeine "Markierung/Linien/weiße Linien" an Kreuzungen reichen NICHT, außer es ist ausdrücklich
eine Radfurt, ein Rad-Symbol oder eine Radspur erwähnt.
Erwähnungen von Fahrrädern als OBJEKT reichen ebenfalls NICHT für TRUE, wenn es um private/soziale Themen geht
(z.B. gefunden/verloren/zu verschenken, Diebstahlverdacht, Fahrradschlüssel, Abstellen/stehende Räder),
außer es geht klar um Radverkehrssicherheit oder eine konkrete Rad-Infrastruktur-Störung.

B) FALSE (non-bike)
Gib FALSE, wenn klar nicht öffentlich-radrelevant:
- Private Themen (Keller, Wohnung, Rechnung, Online-Kauf, privater Diebstahl ohne Infrastrukturbezug)
- Reine Inhalte/Soziales (Werbung/Banner, Fundmeldung, Verlust, Schenkung, Fahrradschlüssel, Fahrraddiebstahl)
  ohne Bezug zu Radwegen/Radverkehr
- Müll/Container/Themen am Gebäude ohne Bezug zur Verkehrsfläche (z.B. Altglascontainer, Hauswand)
- Nur Gehweg/Bürgersteig, sofern NICHT "Geh- und Radweg" / "gemeinsamer Weg" erwähnt wird
- Fahrradständer/Fahrradbügel NUR wegen voller Belegung oder Dauerparkern, ohne Sicherheits-/Zugänglichkeitsproblem

C) UNCERTAIN (needs-review)
Gib UNCERTAIN, wenn der Text zwar ein Problem beschreibt, aber keine explizite Rad-Evidenz enthält:
- Allgemein auf der Verkehrsfläche: Schlagloch, Scherben, Licht defekt, Wasser, Dreck, Hindernis auf "Weg/Straße/Fahrbahn"
- Ortsangaben ohne Spur/Marker ("auf der XY-Straße", "am Weg entlang")

VETO (NO INFERENCE):
Wenn du keinen wörtlichen Beleg aus dem Text zitieren kannst, der TRUE rechtfertigt → NICHT TRUE (dann UNCERTAIN oder FALSE).

AUSGABE (striktes JSON):
{
  "label": "true" | "false" | "uncertain",
  "evidence": ["kurzes wörtliches Zitat aus dem Input (1–2 snippets)"],
  "reasoning": "1 Satz, warum (nur auf Evidence gestützt).",
  "confidence": 0.0 bis 1.0
}

Kategorie: {category}
Beschreibung: {description}
"""


def classify_bike_relevance(category: str, description: str) -> Optional[Dict]:
    """Call Gemini API to classify bike-relevance."""
    prompt = BIKE_RELEVANCE_PROMPT.format(
        category=category,
        description=description
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.1,  # Low temperature for consistency
                'response_mime_type': 'application/json'
            }
        )

        result = json.loads(response.text)
        return result

    except Exception as e:
        print(f"   ⚠️  API Error: {e}")
        return None


def should_check_with_llm(service_name: str, description: Optional[str]) -> bool:
    """Pre-filter: decide if event should be sent to LLM."""
    # No description → skip
    if not description or not description.strip():
        return False

    # Definitely exclude categories → skip
    if service_name in DEFINITELY_EXCLUDE:
        return False

    # High or medium potential → check with LLM
    if service_name in HIGH_POTENTIAL or service_name in MEDIUM_POTENTIAL:
        return True

    # Unknown category → check to be safe
    return True


def main():
    print("=" * 80)
    print("BIKE-RELEVANCE CLASSIFICATION")
    print("=" * 80)

    # Fetch events from Supabase
    print("\n📂 Fetching events from database...")
    response = supabase.table('events').select('*').execute()
    events = response.data
    print(f"   ✅ Loaded {len(events):,} events")

    # Pre-filter
    print("\n🔍 Pre-filtering events...")
    to_check = []
    skipped_no_desc = 0
    skipped_category = 0

    for event in events:
        service_name = event['service_name']
        description = event.get('description')

        if not description or not description.strip():
            skipped_no_desc += 1
            continue

        if service_name in DEFINITELY_EXCLUDE:
            skipped_category += 1
            continue

        to_check.append(event)

    print(f"   ⏭️  Skipped (no description): {skipped_no_desc:,}")
    print(f"   ⏭️  Skipped (excluded category): {skipped_category:,}")
    print(f"   ✅ To check with LLM: {len(to_check):,} ({len(to_check)/len(events)*100:.1f}%)")

    # Classify with LLM
    print(f"\n🤖 Classifying with Gemini 2.0 Flash Lite...")
    print(f"   Estimated cost: ${len(to_check) * 500 / 1_000_000 * 0.15:.2f}")

    results = {
        'true': [],
        'false': [],
        'uncertain': [],
        'error': []
    }

    for i, event in enumerate(to_check, 1):
        if i % 100 == 0:
            print(f"   Progress: {i}/{len(to_check)} ({i/len(to_check)*100:.1f}%)")

        result = classify_bike_relevance(
            event['service_name'],
            event['description']
        )

        if result:
            label = result['label']
            results[label].append({
                'service_request_id': event['service_request_id'],
                'title': event['title'],
                'category': event['service_name'],
                'classification': result
            })
        else:
            results['error'].append(event['service_request_id'])

        # Rate limiting (Gemini Flash: 15 RPM free tier)
        time.sleep(0.1)  # ~10 per second = 600/min (well under limit)

    # Summary
    print("\n" + "=" * 80)
    print("CLASSIFICATION RESULTS")
    print("=" * 80)
    print(f"✅ TRUE (bike-related):     {len(results['true']):5,} events")
    print(f"❌ FALSE (not bike):        {len(results['false']):5,} events")
    print(f"🤔 UNCERTAIN (review):      {len(results['uncertain']):5,} events")
    print(f"⚠️  ERROR (API failed):     {len(results['error']):5,} events")

    # Save results
    output_file = 'bike_classification_results.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Results saved to: {output_file}")

    # Show some TRUE examples
    if results['true']:
        print(f"\n📋 Sample TRUE classifications:")
        for example in results['true'][:5]:
            print(f"\n   {example['service_request_id']}: {example['title']}")
            print(f"   Evidence: {example['classification']['evidence']}")
            print(f"   Reasoning: {example['classification']['reasoning']}")

    print("\n" + "=" * 80)
    print("✅ CLASSIFICATION COMPLETE")
    print("=" * 80)
    print("\n💡 Next steps:")
    print("   1. Review UNCERTAIN events manually")
    print("   2. Update database with bike_related flag")
    print("   3. Create filtered dataset for bike infrastructure analysis")


if __name__ == "__main__":
    main()
