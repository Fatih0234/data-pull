# Bike Event Flagging: Implementation Guide

> **Purpose:** Complete guide for implementing bike-infrastructure event classification in a separate project.
> **Use Case:** Filter 35,388 civic events to identify bike-related infrastructure issues using LLM + rule-based pre-filtering.

---

## 🎯 Problem Statement

You have 35,388 civic event reports from Köln's "Sag's uns" system stored in a Supabase database. You need to identify which events are related to **bike infrastructure** (bike lanes, bike signals, bike parking, etc.) for further analysis.

**Challenge:** Not all events explicitly mention "bike" or "Radweg" but may still affect cyclists (e.g., "defekte Oberfläche" could be a bike lane surface).

---

## 📊 Data Context

### Database Schema

```sql
CREATE TABLE events (
    service_request_id VARCHAR(20) PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,                     -- 93.6% have description
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(150) NOT NULL,
    subcategory2 VARCHAR(150),
    service_name VARCHAR(150) NOT NULL,   -- Used for pre-filtering
    status VARCHAR(20) NOT NULL,
    lat DECIMAL(10, 8) NOT NULL,
    lon DECIMAL(11, 8) NOT NULL,
    -- ... other fields
);
```

### Event Categories Distribution

| service_name | Count | Bike Potential | Strategy |
|--------------|-------|----------------|----------|
| **HIGH POTENTIAL** | | | |
| Defekte Oberfläche | 5,028 | High | ✅ Check with LLM |
| Straßenbaustellen | 1,911 | High | ✅ Check with LLM |
| Defekte Verkehrszeichen | 1,151 | Medium-High | ✅ Check with LLM |
| Radfahrerampel defekt | 48 | Very High | ✅ Check with LLM |
| Straßenmarkierung | 338 | High | ✅ Check with LLM |
| Umlaufsperren / Drängelgitter | 399 | Medium | ✅ Check with LLM |
| **MEDIUM POTENTIAL** | | | |
| Wilder Müll | 11,694 | Low-Medium | ✅ Check with LLM |
| Gully verstopft | 792 | Low-Medium | ✅ Check with LLM |
| Fußgängerampel defekt | 448 | Low-Medium | ✅ Check with LLM |
| Kfz-Ampel defekt | 637 | Low | ✅ Check with LLM |
| Traffic light timing | 379 | Low | ✅ Check with LLM |
| **EXCLUDE (Never bike-related)** | | | |
| Schrottfahrräder | 3,454 | Zero* | ❌ Skip (scrap bikes as objects) |
| Schrott-Kfz | 3,340 | Zero | ❌ Skip |
| Leuchtmittel defekt | 1,350 | Zero* | ❌ Skip (street lights) |
| Kölner Grün | 1,482 | Zero | ❌ Skip (parks/green spaces) |
| Graffiti | 663 | Zero | ❌ Skip (cosmetic) |
| Container issues | 1,013 | Zero | ❌ Skip (waste containers) |
| Parking meters | 98 | Zero | ❌ Skip |
| Playgrounds/fountains | 590 | Zero | ❌ Skip |

*Zero bike-infrastructure relevance. "Schrottfahrräder" are abandoned bikes (objects), not bike lane issues.

---

## 🔄 Three-Phase Classification Strategy

### Phase 0: Rule-Based Pre-Filtering

**Objective:** Reduce LLM API calls by 39.4% while maintaining 99%+ accuracy

**Rules:**

```python
DEFINITELY_EXCLUDE = {
    # Container/waste management
    'Altkleidercontainer voll',
    'Altkleidercontainer defekt',
    'Altkleidercontainer-Standort vermüllt',
    'Glascontainer voll',
    'Glascontainer defekt',
    'Glascontainer-Standort vermüllt',

    # Street lighting (rarely bike-specific unless "Radweg" mentioned)
    'Leuchtmittel defekt',
    'Leuchtmittel tagsüber in Betrieb',
    'Lichtmast defekt',

    # Other infrastructure (not bike-related)
    'Parkscheinautomat defekt',
    'Brunnen',
    'Kölner Grün',
    'Spiel- und Bolzplätze',
    'Graffiti',

    # Objects (not infrastructure)
    'Schrottfahrräder',  # Abandoned bikes as objects
    'Schrott-Kfz',       # Abandoned cars
}

HIGH_POTENTIAL = {
    'Defekte Oberfläche',
    'Straßenmarkierung',
    'Defekte Verkehrszeichen',
    'Radfahrerampel defekt',
    'Umlaufsperren / Drängelgitter',
    'Straßenbaustellen',
}

MEDIUM_POTENTIAL = {
    'Wilder Müll',
    'Gully verstopft',
    'Fußgängerampel defekt',
    'Kfz-Ampel defekt',
    'Zu lange Rotzeit',
    'Zu kurze Grünzeit',
    'Schutzzeit zu kurz',
    'Keine grüne Welle',
}

def should_check_with_llm(service_name: str, description: Optional[str]) -> bool:
    """Decide if event needs LLM classification."""
    # No description → cannot classify
    if not description or not description.strip():
        return False

    # Definitely exclude → skip LLM
    if service_name in DEFINITELY_EXCLUDE:
        return False

    # High or medium potential → check with LLM
    return True
```

**Pre-filtering Results:**
- **Total events:** 35,388
- **With description:** 33,109 (93.6%)
- **After pre-filter:** 21,457 (60.6%) → **Saves 39.4% of LLM calls**

---

### Phase 1: LLM Classification with Gemini 2.0 Flash Lite

**Model Choice:** Gemini 2.0 Flash Lite
- **Cost:** $0.15 per 1M input tokens
- **Speed:** ~10 events/sec (with 0.1s delay)
- **Rate Limit:** 15 RPM (free tier)

**Classification Prompt:**

```python
BIKE_RELEVANCE_PROMPT = """Rolle: Du bist Urban-Data-Analyst:in für Köln.
Aufgabe: Phase 1 – Bike-Relevanz filtern (TRUE/FALSE/UNCERTAIN) anhand EXPLIZITER Evidenz im Text. Keine Vermutungen.

ENTSCHEIDUNGSBAUM (in dieser Reihenfolge):

A) TRUE (bike_related)
Gib TRUE NUR, wenn mindestens EIN expliziter Beleg vorkommt:

1) Direkte Rad-Infrastruktur-Wörter:
   - Radweg, Radfahrstreifen, Schutzstreifen, Radfurt
   - Fahrradstraße, Fahrradzone
   - (gemeinsamer) Geh- und Radweg
   - Radfahrerampel
   - Fahrradbügel / Fahrradständer / Abstellanlage

2) Visuelle/bauliche Marker für Radverkehr (auch ohne "Rad"-Wort):
   - Schutzstreifen
   - gestrichelter Streifen/Spur
   - rote Spur/roter Belag
   - Piktogramme/Symbole auf markiertem Streifen
   - "freigegeben" Zusatzschild (wenn erkennbar für Radverkehr)

3) Explizite Nennung von Radfahrenden/Fahrrad im Sicherheitskontext:
   - "Radfahrer stürzen"
   - "mit dem Fahrrad nicht passierbar"
   - "Gefahr für Radfahrende"

WICHTIG - NICHT ausreichend für TRUE:
- "rechter Rand / Bordsteinkante / Fahrbahnrand" (zu allgemein)
- "Markierung/Linien/weiße Linien" an Kreuzungen (außer explizit Radfurt)
- Fahrräder als OBJEKT (gefunden/verloren/Diebstahl/Schlüssel)
- Fahrradständer nur wegen Belegung (ohne Sicherheitsproblem)

B) FALSE (non-bike)
Gib FALSE, wenn klar nicht öffentlich-radrelevant:
- Private Themen (Keller, Wohnung, Rechnung, Online-Kauf)
- Soziales (Werbung, Fundmeldung, Verlust, Schenkung)
- Müll/Container ohne Verkehrsflächenbezug
- Nur Gehweg/Bürgersteig (außer "Geh- und Radweg")

C) UNCERTAIN (needs-review)
Gib UNCERTAIN, wenn Problem auf Verkehrsfläche, aber KEINE explizite Rad-Evidenz:
- Schlagloch, Scherben, defektes Licht, Wasser, Dreck
- Ortsangaben ohne Spur-Marker ("auf XY-Straße")

VETO (NO INFERENCE):
Wenn du keinen wörtlichen Beleg zitieren kannst → NICHT TRUE.

AUSGABE (striktes JSON):
{
  "label": "true" | "false" | "uncertain",
  "evidence": ["kurzes Zitat aus Input (1-2 snippets)"],
  "reasoning": "1 Satz, warum (nur auf Evidence gestützt)",
  "confidence": 0.0 bis 1.0
}

Kategorie: {category}
Beschreibung: {description}
"""
```

**Key Principles:**
1. **Evidence-based only** - No inference or assumptions
2. **Conservative** - Prioritize precision over recall
3. **Explicit keywords required** - "Radweg", "Schutzstreifen", bike symbols
4. **Context matters** - "Fahrrad" as object ≠ bike infrastructure

**Expected Output:**

```json
{
  "label": "true",
  "evidence": [
    "Der Schutzstreifen ist kaum noch sichtbar",
    "Radfahrer-Piktogramme fehlen komplett"
  ],
  "reasoning": "Explizite Erwähnung von Schutzstreifen (Rad-Infrastruktur) und Radfahrer-Piktogrammen.",
  "confidence": 0.95
}
```

---

### Phase 2: Manual Review (Optional)

**Focus:** UNCERTAIN events only (estimated 5-15% of checked events)

**Why UNCERTAIN exists:**
- LLM cannot infer without explicit evidence
- Example: "Großes Loch auf Musterstraße Ecke Beispielweg"
  - Could be bike lane, car lane, or sidewalk
  - No explicit "Radweg" mention
  - → UNCERTAIN

**Review Process:**
1. Export UNCERTAIN events to CSV/spreadsheet
2. Add columns: `manual_label`, `manual_reasoning`
3. Use local knowledge, map, or street view to classify
4. Update database with manual labels

---

## 💰 Cost Analysis

### Gemini 2.0 Flash Lite Pricing

| Metric | Value |
|--------|-------|
| **Input tokens per event** | ~500 (category + description + prompt) |
| **Events to check** | 21,457 |
| **Total input tokens** | ~10.7M |
| **Cost per 1M tokens** | $0.15 |
| **Total cost** | **$1.61** |

### Cost Comparison

| Strategy | Events Checked | Cost | Savings |
|----------|---------------|------|---------|
| Check all with description | 33,109 | $2.48 | - |
| **With pre-filtering (recommended)** | **21,457** | **$1.61** | **35%** |

### Time Estimate

- **Rate:** 10 events/sec (with 0.1s delay for rate limiting)
- **Total time:** ~36 minutes for 21,457 events

---

## 🛠️ Implementation Architecture

### Recommended Project Structure

```
flag-the-event/
├── config/
│   ├── category_rules.py          # HIGH/MEDIUM/EXCLUDE categories
│   └── prompts.py                  # LLM prompts
│
├── src/
│   ├── prefilter.py                # Phase 0: Rule-based filtering
│   ├── llm_classifier.py           # Phase 1: Gemini API calls
│   ├── result_processor.py         # Parse LLM responses
│   └── database_updater.py         # Write results to Supabase
│
├── scripts/
│   ├── run_classification.py       # Main pipeline
│   └── analyze_results.py          # Generate statistics
│
└── outputs/
    ├── classification_results.json # Full results with evidence
    └── uncertain_for_review.csv    # UNCERTAIN events for manual review
```

### Database Schema Updates

Add columns to store classification results:

```sql
-- Add bike classification columns
ALTER TABLE events ADD COLUMN bike_related BOOLEAN;
ALTER TABLE events ADD COLUMN bike_confidence DECIMAL(3,2);
ALTER TABLE events ADD COLUMN bike_evidence TEXT[];
ALTER TABLE events ADD COLUMN bike_reasoning TEXT;
ALTER TABLE events ADD COLUMN bike_reviewed_manually BOOLEAN DEFAULT FALSE;
ALTER TABLE events ADD COLUMN bike_classification_date TIMESTAMPTZ;

-- Create indexes for filtering
CREATE INDEX idx_events_bike_related ON events(bike_related) WHERE bike_related IS TRUE;
CREATE INDEX idx_events_bike_uncertain ON events(bike_related) WHERE bike_related IS NULL;

-- Create views
CREATE VIEW bike_events AS
SELECT * FROM events
WHERE bike_related = TRUE
  AND bike_confidence >= 0.8;

CREATE VIEW bike_uncertain AS
SELECT * FROM events
WHERE bike_related IS NULL
  OR bike_confidence < 0.5;
```

---

## 📝 Implementation Steps

### Step 1: Setup

```bash
# Install dependencies
pip install google-generativeai supabase python-dotenv

# Configure environment
cat > .env << EOF
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
GEMINI_API_KEY=your-gemini-api-key
EOF
```

Get Gemini API key: https://aistudio.google.com/app/apikey

### Step 2: Implement Pre-filter

```python
# src/prefilter.py
from typing import List, Dict

DEFINITELY_EXCLUDE = {...}  # See category lists above
HIGH_POTENTIAL = {...}
MEDIUM_POTENTIAL = {...}

def prefilter_events(events: List[Dict]) -> Dict:
    """Pre-filter events before LLM classification."""
    results = {
        'to_check': [],
        'skipped_no_desc': [],
        'skipped_category': []
    }

    for event in events:
        service_name = event['service_name']
        description = event.get('description', '').strip()

        # Skip if no description
        if not description:
            results['skipped_no_desc'].append(event['service_request_id'])
            continue

        # Skip if excluded category
        if service_name in DEFINITELY_EXCLUDE:
            results['skipped_category'].append(event['service_request_id'])
            continue

        # Check with LLM
        results['to_check'].append(event)

    return results
```

### Step 3: Implement LLM Classifier

```python
# src/llm_classifier.py
import google.generativeai as genai
import json
import time

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.0-flash-lite')

def classify_event(category: str, description: str) -> Dict:
    """Classify single event with Gemini."""
    prompt = BIKE_RELEVANCE_PROMPT.format(
        category=category,
        description=description
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.1,
                'response_mime_type': 'application/json'
            }
        )

        result = json.loads(response.text)
        return result

    except Exception as e:
        print(f"Error: {e}")
        return None

def batch_classify(events: List[Dict], batch_size: int = 100) -> List[Dict]:
    """Classify events in batches with rate limiting."""
    results = []

    for i, event in enumerate(events):
        result = classify_event(
            event['service_name'],
            event['description']
        )

        if result:
            results.append({
                'service_request_id': event['service_request_id'],
                'classification': result
            })

        # Rate limiting (10 per second)
        time.sleep(0.1)

        # Progress logging
        if (i + 1) % 100 == 0:
            print(f"Processed {i + 1}/{len(events)} events")

    return results
```

### Step 4: Update Database

```python
# src/database_updater.py
from supabase import create_client

def update_event_classification(supabase, event_id: str, classification: Dict):
    """Update single event with classification results."""
    update_data = {
        'bike_related': classification['label'] == 'true',
        'bike_confidence': classification['confidence'],
        'bike_evidence': classification['evidence'],
        'bike_reasoning': classification['reasoning'],
        'bike_classification_date': 'now()'
    }

    supabase.table('events').update(update_data).eq(
        'service_request_id', event_id
    ).execute()

def batch_update(supabase, results: List[Dict], batch_size: int = 100):
    """Batch update database with classification results."""
    for i in range(0, len(results), batch_size):
        batch = results[i:i + batch_size]

        for result in batch:
            update_event_classification(
                supabase,
                result['service_request_id'],
                result['classification']
            )

        print(f"Updated {min(i + batch_size, len(results))}/{len(results)}")
```

### Step 5: Main Pipeline

```python
# scripts/run_classification.py
import os
from supabase import create_client
from src.prefilter import prefilter_events
from src.llm_classifier import batch_classify
from src.database_updater import batch_update

def main():
    # Connect to database
    supabase = create_client(
        os.getenv('SUPABASE_URL'),
        os.getenv('SUPABASE_KEY')
    )

    # Fetch events
    print("Fetching events...")
    response = supabase.table('events').select('*').execute()
    events = response.data
    print(f"Loaded {len(events):,} events")

    # Pre-filter
    print("\nPre-filtering...")
    filtered = prefilter_events(events)
    print(f"To check: {len(filtered['to_check']):,}")
    print(f"Skipped (no desc): {len(filtered['skipped_no_desc']):,}")
    print(f"Skipped (category): {len(filtered['skipped_category']):,}")

    # Classify with LLM
    print("\nClassifying with Gemini...")
    results = batch_classify(filtered['to_check'])

    # Update database
    print("\nUpdating database...")
    batch_update(supabase, results)

    # Summary
    true_count = sum(1 for r in results if r['classification']['label'] == 'true')
    false_count = sum(1 for r in results if r['classification']['label'] == 'false')
    uncertain_count = sum(1 for r in results if r['classification']['label'] == 'uncertain')

    print("\n" + "=" * 60)
    print("CLASSIFICATION COMPLETE")
    print("=" * 60)
    print(f"TRUE (bike-related):  {true_count:,}")
    print(f"FALSE (not bike):     {false_count:,}")
    print(f"UNCERTAIN (review):   {uncertain_count:,}")

if __name__ == "__main__":
    main()
```

---

## 📊 Expected Results

Based on analysis of event categories:

| Label | Count | % of Checked | Notes |
|-------|-------|--------------|-------|
| **TRUE** | 2,000-4,000 | 10-20% | High-confidence bike events |
| **FALSE** | 15,000-17,000 | 70-80% | Clearly not bike-related |
| **UNCERTAIN** | 1,000-3,000 | 5-15% | Needs manual review |

### High-Confidence TRUE Categories

- **Radfahrerampel defekt:** ~100% TRUE (48 events)
- **Straßenmarkierung (with "Radweg"):** ~70-80% TRUE
- **Defekte Oberfläche (on bike lanes):** ~60-70% TRUE
- **Umlaufsperren / Drängelgitter:** ~40-50% TRUE

### Typical FALSE Examples

- Container issues
- Graffiti on buildings
- Scrap bikes/cars (objects, not infrastructure)
- Park/playground issues
- Street lighting (unless on bike path)

### Typical UNCERTAIN Examples

- "Schlagloch auf der Musterstraße" (no bike-specific mention)
- "Scherben am Weg" (which way?)
- "Defekte Ampel Ecke X/Y" (which signal?)

---

## ✅ Quality Assurance

### Validation Strategy

1. **Sample 100 TRUE events** → Manual review → Calculate precision
2. **Sample 100 FALSE events** → Manual review → Calculate accuracy
3. **Review ALL UNCERTAIN** → Manually label

### Expected Metrics

- **Precision (TRUE):** 85-95%
- **Recall (TRUE):** 75-85%
- **F1 Score:** 80-90%

The conservative approach (no inference) prioritizes **precision over recall**:
- Better to classify as UNCERTAIN than false positive TRUE
- UNCERTAIN events can be manually reviewed

---

## 🔧 Troubleshooting

### Issue: LLM returns unexpected format

**Solution:** Add retry logic with format validation

```python
def classify_with_retry(category, description, max_retries=3):
    for attempt in range(max_retries):
        result = classify_event(category, description)

        # Validate format
        if result and all(k in result for k in ['label', 'evidence', 'reasoning', 'confidence']):
            return result

        print(f"Retry {attempt + 1}/{max_retries}")
        time.sleep(1)

    return None  # Failed after retries
```

### Issue: Rate limit exceeded

**Solution:** Increase delay between requests

```python
time.sleep(4)  # 15 per minute max (free tier)
```

### Issue: High cost

**Solution:** Start with smaller sample

```python
# Test on 100 events first
test_events = filtered['to_check'][:100]
results = batch_classify(test_events)
```

---

## 📈 Next Steps After Classification

1. **Create filtered dataset**
   ```sql
   SELECT * FROM bike_events WHERE bike_confidence >= 0.8;
   ```

2. **Geospatial analysis**
   - Map bike issues by district
   - Identify hot spots

3. **Time series analysis**
   - When do most bike issues occur?
   - Seasonal patterns?

4. **Category breakdown**
   - Surface issues vs. signage vs. barriers
   - Priority ranking

5. **Reporting dashboard**
   - Track open vs. closed bike issues
   - Response time analysis

---

## 📚 Reference Data

### Example Event (Bike-Related = TRUE)

```json
{
  "service_request_id": "1234-2025",
  "title": "#1234-2025 Defekte Oberfläche",
  "description": "Der Radweg auf der Musterstraße hat ein großes Loch. Radfahrer müssen in den Autoverkehr ausweichen. Sehr gefährlich!",
  "service_name": "Defekte Oberfläche",
  "category": "Straßen und Verkehrsanlagen",
  "subcategory": "Straßen-, Geh- und Radwegschäden",

  "classification": {
    "label": "true",
    "evidence": [
      "Der Radweg auf der Musterstraße hat ein großes Loch",
      "Radfahrer müssen in den Autoverkehr ausweichen"
    ],
    "reasoning": "Explizite Erwähnung von 'Radweg' und Sicherheitsproblem für 'Radfahrer'",
    "confidence": 0.95
  }
}
```

### Example Event (Bike-Related = FALSE)

```json
{
  "service_request_id": "5678-2025",
  "title": "#5678-2025 Schrottfahrräder",
  "description": "Drei Fahrräder stehen seit Monaten herrenlos am Straßenrand. Bitte entfernen.",
  "service_name": "Schrottfahrräder",

  "classification": {
    "label": "false",
    "evidence": [
      "Fahrräder stehen seit Monaten herrenlos"
    ],
    "reasoning": "Fahrräder als Objekte (Müll), kein Bezug zur Radverkehrsinfrastruktur",
    "confidence": 0.90
  }
}
```

### Example Event (Bike-Related = UNCERTAIN)

```json
{
  "service_request_id": "9012-2025",
  "title": "#9012-2025 Defekte Oberfläche",
  "description": "Großes Schlagloch auf der Hauptstraße Ecke Nebenstraße. Gefährlich!",
  "service_name": "Defekte Oberfläche",

  "classification": {
    "label": "uncertain",
    "evidence": [
      "Großes Schlagloch auf der Hauptstraße"
    ],
    "reasoning": "Schlagloch erwähnt, aber unklar ob auf Radweg, Fahrbahn oder Gehweg",
    "confidence": 0.50
  }
}
```

---

## 🎯 Summary Checklist

Before implementing in `flag-the-event` project:

- [ ] Understand the three-phase strategy
- [ ] Review category exclusion rules (DEFINITELY_EXCLUDE)
- [ ] Get Gemini API key from Google AI Studio
- [ ] Plan database schema updates (bike_related columns)
- [ ] Decide on UNCERTAIN event review process
- [ ] Budget for API costs (~$1.61 for full dataset)
- [ ] Allocate time for classification (~36 minutes)

---

**Ready to implement!** This guide contains everything needed to build the classification pipeline in your separate project.

For questions or clarification, refer to:
- Source project: `/Volumes/T7/eventRegistryApi`
- Analysis script: `analyze_bike_potential.py`
- Example implementation: `flag_bike_events.py`
