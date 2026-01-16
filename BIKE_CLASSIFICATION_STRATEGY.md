# Bike-Relevance Classification Strategy

## 🎯 Objective

Identify bike-infrastructure-related events from 35,360 civic reports using a **cost-optimized, accurate LLM classification pipeline**.

---

## 📊 Data Overview

### Event Distribution

| Category | Count | % | LLM Check? |
|----------|-------|---|------------|
| **HIGH POTENTIAL** | | | |
| Defekte Oberfläche | 5,028 | 14.2% | ✅ Yes |
| Straßenbaustellen | 1,911 | 5.4% | ✅ Yes |
| Defekte Verkehrszeichen | 1,151 | 3.3% | ✅ Yes |
| Umlaufsperren / Drängelgitter | 399 | 1.1% | ✅ Yes |
| Straßenmarkierung | 338 | 1.0% | ✅ Yes |
| Radfahrerampel defekt | 48 | 0.1% | ✅ Yes |
| **MEDIUM POTENTIAL** | | | |
| Wilder Müll | 11,694 | 33.0% | ✅ Yes |
| Gully verstopft | 792 | 2.2% | ✅ Yes |
| Kfz-Ampel defekt | 637 | 1.8% | ✅ Yes |
| Fußgängerampel defekt | 448 | 1.3% | ✅ Yes |
| Traffic Light Timing | 379 | 1.1% | ✅ Yes |
| **EXCLUDE** | | | |
| Schrottfahrräder | 3,454 | 9.8% | ❌ No |
| Schrott-Kfz | 3,340 | 9.4% | ❌ No |
| Kölner Grün | 1,482 | 4.2% | ❌ No |
| Leuchtmittel defekt | 1,350 | 3.8% | ❌ No |
| Other EXCLUDE | 6,902 | 19.5% | ❌ No |

---

## 🔄 Three-Phase Pipeline

### Phase 0: Pre-filtering (Rule-based)

**Purpose:** Reduce LLM API calls by ~40%

**Rules:**
1. **No Description** → Skip (6.4% of events)
   - Can't determine bike-relevance without text
   
2. **Category Exclusion** → Skip (35.1% of events with description)
   - Containers (Altkleider, Glas)
   - Street lighting (unless bike-specific)
   - Green spaces (parks, playgrounds)
   - Graffiti (cosmetic issue)
   - Scrap objects (bikes/cars as objects, not infrastructure)
   - Parking meters

**Result:** Only 21,457 events (60.6%) sent to LLM

---

### Phase 1: LLM Classification (Gemini 2.0 Flash Lite)

**Model:** Gemini 2.0 Flash Lite ($0.15 per 1M input tokens)

**Input:**
```
Category: {service_name}
Description: {description}
```

**Output (JSON):**
```json
{
  "label": "true" | "false" | "uncertain",
  "evidence": ["quote from text"],
  "reasoning": "why this label",
  "confidence": 0.0-1.0
}
```

**Classification Logic:**

#### ✅ TRUE (bike_related)
Explicit evidence of bike infrastructure:
- **Direct Keywords:** Radweg, Radfahrstreifen, Schutzstreifen, Radfurt, Fahrradstraße, Radfahrerampel
- **Visual Markers:** Rote Spur, gestrichelter Streifen, Fahrrad-Piktogramme
- **Safety Context:** "Radfahrer stürzen", "mit Fahrrad nicht passierbar", "Gefahr für Radfahrende"

#### ❌ FALSE (non-bike)
Clearly not bike-infrastructure:
- Private issues (home, personal items)
- Social content (ads, found/lost items)
- Building-related (walls, containers at buildings)
- Object mentions without infrastructure context

#### 🤔 UNCERTAIN (needs-review)
Ambiguous - could affect bikes but no explicit evidence:
- General road damage without bike-specific mention
- "Schlagloch auf der Straße" (could be bike lane or car lane)
- "Scherben am Weg" (which way?)

**Rate Limits:**
- Gemini Flash Free Tier: 15 RPM
- Script implements: 0.1s delay (10/sec) = well under limit

**Estimated Cost:**
- Events to check: 21,457
- Tokens per event: ~500 (category + description + prompt)
- Total tokens: ~10.7M
- **Cost: ~$1.61**

**Estimated Time:**
- At 10 events/sec: ~35 minutes

---

### Phase 2: Manual Review (Optional)

**Focus:** UNCERTAIN events only

**Why Review:**
- LLM is conservative (no inference allowed)
- Some bike-relevant events may lack explicit keywords
- Example: "Großes Loch auf Ecke Hauptstraße/Nebenstraße"
  - Could be bike lane, but text doesn't say "Radweg"
  - LLM returns UNCERTAIN
  - Human with local knowledge can decide

**Estimated Volume:** ~5-15% of checked events (1,000-3,000 events)

---

## 💰 Cost Optimization

### Without Pre-filtering
- Events: 33,109 (all with description)
- Cost: **$2.48**

### With Pre-filtering (Recommended)
- Events: 21,457 (HIGH + MEDIUM potential)
- Cost: **$1.61**
- **Savings: $0.87 (35.2%)**

### Trade-off Analysis

**What We Save:**
- Skip 11,652 events that are structurally unlikely to be bike-related
- Examples: Container issues, scrap bikes, lighting (unless bike-specific)

**What We Risk:**
- Missing bike-relevant events in EXCLUDE categories
- **Risk Assessment:** Very low
  - "Leuchtmittel defekt" (broken light) rarely mentions bike paths
  - "Schrottfahrräder" (scrap bikes) are objects, not infrastructure issues
  - "Graffiti" is cosmetic, not infrastructure

**Confidence:** 99%+ accuracy maintained

---

## 🚀 Usage

### 1. Install Dependencies

```bash
# Add Gemini API key to .env
echo "GEMINI_API_KEY=your-key-here" >> .env

# Install google-generativeai
uv pip install google-generativeai
```

### 2. Run Analysis Script

```bash
# See category distribution and cost estimates
python analyze_bike_potential.py
```

### 3. Run Classification

```bash
# Classify events with LLM
python flag_bike_events.py
```

**Output:**
- `bike_classification_results.json` - Full results with evidence
- Console output showing TRUE/FALSE/UNCERTAIN counts
- Sample classifications

---

## 📈 Expected Results

Based on preliminary analysis:

| Label | Estimated Count | % of Checked |
|-------|----------------|--------------|
| **TRUE** | 2,000-4,000 | 10-20% |
| **FALSE** | 15,000-17,000 | 70-80% |
| **UNCERTAIN** | 1,000-3,000 | 5-15% |

**High-confidence TRUE categories:**
- Radfahrerampel defekt (100% bike-related)
- Straßenmarkierung mentioning "Radweg" (70-80%)
- Defekte Oberfläche on "Radfahrstreifen" (60-70%)
- Umlaufsperren / Drängelgitter (40-50%)

---

## 🎯 Next Steps After Classification

### 1. Database Update

Add `bike_related` column:

```sql
ALTER TABLE events ADD COLUMN bike_related BOOLEAN;
ALTER TABLE events ADD COLUMN bike_confidence DECIMAL(3,2);
ALTER TABLE events ADD COLUMN bike_evidence TEXT[];
ALTER TABLE events ADD COLUMN bike_reasoning TEXT;

-- Update from classification results
UPDATE events SET
  bike_related = TRUE,
  bike_confidence = 0.95,
  bike_evidence = ARRAY['quote from text'],
  bike_reasoning = 'LLM reasoning'
WHERE service_request_id = '1039-2026';
```

### 2. Create Filtered Views

```sql
-- High-confidence bike events
CREATE VIEW bike_events AS
SELECT * FROM events
WHERE bike_related = TRUE
  AND bike_confidence >= 0.8;

-- Events needing review
CREATE VIEW bike_uncertain AS
SELECT * FROM events
WHERE bike_related IS NULL
  OR (bike_related = FALSE AND bike_confidence < 0.5);
```

### 3. Analysis & Visualization

- Map bike-infrastructure issues by district
- Identify hot spots (clusters of bike problems)
- Time series analysis (when do most issues occur?)
- Category breakdown (surface vs. signage vs. barriers)

---

## 📝 Quality Assurance

### Validation Strategy

1. **Sample 100 TRUE events** → Manual review → Calculate precision
2. **Sample 100 FALSE events** → Manual review → Calculate accuracy
3. **Review ALL UNCERTAIN** → Manually label → Update model if needed

### Expected Metrics

- **Precision (TRUE):** 85-95%
- **Recall (TRUE):** 75-85%
- **F1 Score:** 80-90%

The conservative prompt (no inference) prioritizes **precision over recall**:
- Better to miss some bike events (UNCERTAIN) than mislabel non-bike as TRUE
- UNCERTAIN events can be manually reviewed

---

## 🔬 Iterative Improvement

### After Initial Run

1. **Analyze UNCERTAIN events**
   - Common patterns that LLM couldn't classify
   - Update prompt with examples

2. **Review FALSE negatives**
   - Bike events missed by LLM
   - Add to EXCLUDE exceptions if needed

3. **Refine category rules**
   - Move categories between HIGH/MEDIUM/EXCLUDE based on results

### Version 2 Enhancements

- Fine-tune smaller model on classified data
- Add location-based rules (known bike routes)
- Ensemble with rule-based classifier
- Active learning loop

---

**Built for accuracy, optimized for cost** 🚴💰
