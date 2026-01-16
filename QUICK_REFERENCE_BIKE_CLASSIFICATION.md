# Quick Reference: Bike Event Classification

> **TL;DR:** Filter 35K events → 21K LLM checks → ~2-4K bike-related events for $1.61

---

## 📋 Quick Facts

| Metric | Value |
|--------|-------|
| Total events | 35,388 |
| Events with description | 33,109 (93.6%) |
| **After pre-filter** | **21,457 (60.6%)** |
| **Estimated TRUE** | **2,000-4,000 (10-20%)** |
| **API cost** | **$1.61** |
| **Time** | **~36 minutes** |

---

## 🚦 Decision Tree (30 second version)

```
Event
  ├─ No description? → SKIP
  ├─ Container/Graffiti/Scrap/Lighting? → SKIP
  └─ Check with LLM
      ├─ Mentions "Radweg/Schutzstreifen/Radfurt"? → TRUE
      ├─ Clearly not bike-infrastructure? → FALSE  
      └─ Road issue, unclear if bike? → UNCERTAIN
```

---

## 🎯 Classification Rules (2 minute version)

### ✅ TRUE = Bike Infrastructure

**Must have explicit evidence:**
- Keywords: Radweg, Radfahrstreifen, Schutzstreifen, Radfurt, Radfahrerampel
- Visual: rote Spur, gestrichelter Streifen, Fahrrad-Piktogramme
- Safety: "Radfahrer stürzen", "mit Fahrrad nicht passierbar"

**Example:**
> "Der Schutzstreifen ist kaum sichtbar, Piktogramme fehlen"
→ **TRUE** (explicit bike infrastructure keywords)

### ❌ FALSE = Not Bike Infrastructure

- Containers, graffiti, scrap objects, parks
- "Fahrrad" as object (found, lost, stolen) without infrastructure context
- Building-related issues

**Example:**
> "Drei Fahrräder stehen herrenlos am Straßenrand"
→ **FALSE** (scrap bikes = objects, not infrastructure)

### 🤔 UNCERTAIN = Needs Review

- Road issues without bike-specific mention
- Generic "Schlagloch", "Scherben", "defekte Ampel"

**Example:**
> "Großes Loch auf Musterstraße"
→ **UNCERTAIN** (could be bike lane or car lane)

---

## 🔧 Pre-Filter Rules (Copy-Paste Ready)

```python
SKIP_THESE_CATEGORIES = {
    'Altkleidercontainer voll', 'Altkleidercontainer defekt',
    'Glascontainer voll', 'Glascontainer defekt',
    'Leuchtmittel defekt', 'Lichtmast defekt',
    'Parkscheinautomat defekt',
    'Brunnen', 'Kölner Grün', 'Spiel- und Bolzplätze',
    'Graffiti',
    'Schrottfahrräder', 'Schrott-Kfz',
}

CHECK_THESE_CATEGORIES = {
    # HIGH
    'Defekte Oberfläche', 'Straßenmarkierung',
    'Defekte Verkehrszeichen', 'Radfahrerampel defekt',
    'Umlaufsperren / Drängelgitter', 'Straßenbaustellen',

    # MEDIUM
    'Wilder Müll', 'Gully verstopft',
    'Fußgängerampel defekt', 'Kfz-Ampel defekt',
}
```

---

## 💻 Implementation Checklist

```bash
# 1. Setup
pip install google-generativeai supabase python-dotenv
export GEMINI_API_KEY="your-key"

# 2. Database schema
ALTER TABLE events ADD COLUMN bike_related BOOLEAN;
ALTER TABLE events ADD COLUMN bike_confidence DECIMAL(3,2);
ALTER TABLE events ADD COLUMN bike_evidence TEXT[];

# 3. Run classification
python run_classification.py

# 4. Review uncertain
SELECT * FROM events WHERE bike_related IS NULL;
```

---

## 📊 Expected Output

```
Total events:              35,388
└─ No description:          2,279 (skip)
└─ Excluded categories:    11,652 (skip)
└─ To check with LLM:      21,457

LLM Classification:
├─ TRUE (bike):             2,500  (12%)
├─ FALSE (not bike):       17,500  (82%)
└─ UNCERTAIN (review):      1,500   (7%)

Cost: $1.61 | Time: 36 min
```

---

## 🚨 Common Pitfalls

| Mistake | Impact | Fix |
|---------|--------|-----|
| Include "Schrottfahrräder" | False positives | Skip (objects, not infrastructure) |
| Infer from context | Low precision | Require explicit evidence |
| Skip UNCERTAIN review | Miss ~5% bike events | Manual review recommended |
| Use high temperature | Inconsistent results | Use temp=0.1 |

---

## 🎓 Key Concepts

**Conservative Approach:**
- Precision > Recall
- Better UNCERTAIN than false TRUE
- No inference without evidence

**Why Pre-filter?**
- Saves 35% API cost ($0.87)
- Saves 20 minutes
- No accuracy loss (excluded categories = 0% bike-relevant)

**Why UNCERTAIN category?**
- LLM can't infer without explicit keywords
- Example: "Loch auf Straße" (which part of street?)
- Allows manual review with local knowledge

---

## 📖 Full Documentation

For complete implementation guide:
→ `BIKE_FLAGGING_IMPLEMENTATION_GUIDE.md`

For strategy details:
→ `BIKE_CLASSIFICATION_STRATEGY.md`

For analysis code:
→ `analyze_bike_potential.py`, `flag_bike_events.py`

---

**Use this in your `flag-the-event` project for quick reference while implementing!**
