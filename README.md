# Köln Civic Events Registry

A complete data pipeline for importing and managing 35,000+ civic event reports from [Stadt Köln's "Sag's uns" system](https://sags-uns.stadt-koeln.de) into a Supabase PostgreSQL database.

## 📊 Project Overview

This project fetches, processes, and stores civic event data (street damage, graffiti, broken lights, etc.) reported by Köln citizens. The data includes:

- **35,360+ events** spanning 2025-2026
- **Geographic coordinates** for mapping
- **3-level category hierarchy** (category → subcategory → subcategory2)
- **Status tracking** (open/closed)
- **Media attachments** (images)
- **Parsed address components** (zip code, city, district, street, house number)

### Key Features

✅ **Single-table normalized design** - Fast queries, simple schema  
✅ **Geospatial indexing** - Find events within radius using PostGIS  
✅ **99.3% address parsing accuracy** - Automatic extraction of address components  
✅ **Category enrichment** - 3-level hierarchy from CSV mapping  
✅ **8 database indexes** - Optimized for common query patterns  
✅ **Batch import** - Processes 35K+ events in ~2-5 minutes  

---

## 🗂️ Project Structure

```
eventRegistryApi/
├── README.md                          # This file
├── SUMMARY.md                         # Import results and data quality report
├── .env.example                       # Template for Supabase credentials
├── pyproject.toml                     # Python dependencies
├── uv.lock                           # Lockfile for uv package manager
│
├── Data Files
│   ├── all_events.json               # 35,388 raw events from API
│   └── sags_uns_categories_3level.csv # Category hierarchy mapping
│
├── Scripts
│   ├── clean_fetch.py                # Fetch latest events from API
│   ├── import_events.py              # Main import script (run this!)
│   └── run_migration.py              # Create database table (manual fallback)
│
└── migrations/
    ├── 001_create_events_table.sql   # Table DDL + indexes
    ├── 002_validate_data.sql         # Data quality checks
    └── 003_disable_rls_for_import.sql # Permissions setup
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager
- Supabase account ([create free account](https://supabase.com))

### 1. Clone Repository

```bash
git clone https://github.com/Fatih0234/data-pull.git
cd data-pull
```

### 2. Install Dependencies

```bash
# Create virtual environment and install packages
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -r pyproject.toml
```

### 3. Configure Supabase

Create `.env` file with your credentials:

```bash
cp .env.example .env
# Edit .env with your Supabase URL and key
```

Get credentials from: https://supabase.com/dashboard/project/YOUR_PROJECT/settings/api

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-or-service-role-key
```

### 4. Create Database Table

**Option A: Supabase Dashboard (Recommended)**

1. Go to [SQL Editor](https://supabase.com/dashboard)
2. Copy contents of `migrations/001_create_events_table.sql`
3. Paste and click **Run**
4. Run `migrations/003_disable_rls_for_import.sql` (for permissions)

**Option B: Command Line (if direct connection works)**

```bash
python run_migration.py
# Enter your database password when prompted
```

### 5. Import Events

```bash
python import_events.py
```

**Expected output:**
```
============================================================
EVENT REGISTRY IMPORT
============================================================

📂 Loading data files...
   ✅ Loaded 35388 events from all_events.json
   ✅ Loaded 33 category mappings from sags_uns_categories_3level.csv

⚙️  Processing events...
   ✅ Processed 35360 events
   ⚠️  Skipped 28 unmapped events (0.08%)

🔌 Connecting to Supabase...
   ✅ Connected to https://your-project.supabase.co

📤 Inserting 35360 events in batches of 1000...
   ✅ Batch 1/36 inserted (1000 events)
   ...
   ✅ Batch 36/36 inserted (360 events)

============================================================
✅ IMPORT COMPLETE
============================================================
📊 Statistics:
   - Total events processed: 35388
   - Successfully imported: 35360
   - Skipped (unmapped): 28
   - Success rate: 99.92%
```

---

## 📊 Database Schema

### `events` Table (35,360 rows, 21 columns)

```sql
CREATE TABLE events (
    -- Identity
    service_request_id VARCHAR(20) PRIMARY KEY,  -- "1039-2026"
    title TEXT NOT NULL,
    description TEXT,
    
    -- Location
    lat DECIMAL(10, 8) NOT NULL,
    lon DECIMAL(11, 8) NOT NULL,
    address_string TEXT NOT NULL,
    zip_code VARCHAR(10),
    city VARCHAR(100),
    district VARCHAR(100),
    street VARCHAR(255),
    house_number VARCHAR(20),
    
    -- Categories (enriched from CSV)
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(150) NOT NULL,
    subcategory2 VARCHAR(150),
    service_name VARCHAR(150) NOT NULL,
    
    -- Metadata
    status VARCHAR(20) NOT NULL,           -- 'open' or 'closed'
    requested_at TIMESTAMPTZ NOT NULL,
    media_path VARCHAR(500),
    year SMALLINT NOT NULL,
    sequence_number INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Indexes

- **Primary Key:** `service_request_id`
- **B-tree indexes:** requested_at, status, year, category, subcategory, zip_code
- **Partial index:** district (where NOT NULL)
- **GIST index:** Geospatial (lat/lon) for radius queries

---

## 🔍 Example Queries

### Find Events by Category

```sql
SELECT * FROM events 
WHERE category = 'Stadtbild' 
ORDER BY requested_at DESC 
LIMIT 10;
```

### Recent Open Events

```sql
SELECT service_request_id, title, district, requested_at
FROM events
WHERE status = 'open'
ORDER BY requested_at DESC
LIMIT 20;
```

### Events in Specific District

```sql
SELECT * FROM events
WHERE district = 'Lövenich'
ORDER BY requested_at DESC;
```

### Geospatial Query (Within 1km Radius)

```sql
-- Events within 1km of Köln city center (50.9375, 6.9603)
SELECT
    service_request_id,
    title,
    district,
    ROUND(earth_distance(
        ll_to_earth(lat::float, lon::float),
        ll_to_earth(50.9375, 6.9603)
    )::numeric, 0) as distance_meters
FROM events
WHERE earth_box(ll_to_earth(50.9375, 6.9603), 1000) @> ll_to_earth(lat::float, lon::float)
ORDER BY distance_meters
LIMIT 10;
```

### Events with Media

```sql
SELECT service_request_id, title, media_path
FROM events
WHERE media_path IS NOT NULL
LIMIT 10;
```

### Category Distribution

```sql
SELECT 
    category,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM events
GROUP BY category
ORDER BY count DESC;
```

---

## 📈 Data Quality

See `SUMMARY.md` for detailed data quality report.

### Import Results

- **Total Events:** 35,360 (99.92% success rate)
- **Skipped:** 28 unmapped events (0.08%)

### Breakdown

| Metric | Value | Percentage |
|--------|-------|------------|
| **Year 2025** | 34,321 events | 97.06% |
| **Year 2026** | 1,039 events | 2.94% |
| **Closed Status** | 31,332 events | 88.61% |
| **Open Status** | 4,028 events | 11.39% |
| **Addresses Parsed** | 35,111 | 99.30% |
| **With Media** | ~24,000 | 68% |

### Top Categories

1. **Stadtbild** (City Image): 17,623 events (49.84%)
2. **Straßen und Verkehrsanlagen** (Streets): 15,665 events (44.30%)
3. **Spielplätze und Grünanlagen** (Parks): 2,072 events (5.86%)

---

## 🔄 Updating Data

To fetch the latest events from the API:

```bash
python clean_fetch.py
```

This will update `all_events.json`. Then re-run `import_events.py` to update the database.

**Note:** The import script skips duplicates based on `service_request_id`.

---

## 🛠️ Development

### Running Validation Queries

```bash
# In Supabase SQL Editor, run:
cat migrations/002_validate_data.sql
```

### Testing Geospatial Queries

The database includes PostGIS extensions for geospatial queries. Test with:

```sql
-- Check if extensions are enabled
SELECT * FROM pg_extension WHERE extname IN ('cube', 'earthdistance');
```

---

## 📝 API Reference

The data comes from Stadt Köln's Open311-compatible API:

- **Base URL:** https://sags-uns.stadt-koeln.de
- **Endpoint:** `/open311/v2/requests.json`
- **Documentation:** [Open311 GeoReport v2](http://wiki.open311.org/GeoReport_v2/)

### Event Structure

```json
{
  "service_request_id": "1039-2026",
  "title": "#1039-2026 Defekte Oberfläche",
  "description": "...",
  "lat": 50.947720164706,
  "long": 6.8203955247904,
  "address_string": "50859 Köln - Lövenich, An der Ronne 174",
  "service_name": "Defekte Oberfläche",
  "requested_datetime": "2026-01-15T23:34:39+01:00",
  "status": "closed",
  "media_url": "https://sags-uns.stadt-koeln.de/system/files/2026-01/IMG_3754.jpeg"
}
```

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is open source and available under the MIT License.

---

## 🙏 Acknowledgments

- **Stadt Köln** for providing the Open311 API
- **Supabase** for database hosting
- **PostGIS** for geospatial capabilities

---

## 📧 Contact

For questions or issues, please open a GitHub issue or contact the maintainer.

**Project Link:** https://github.com/Fatih0234/data-pull

---

**Built with ❤️ for the Köln community**
