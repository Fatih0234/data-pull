-- Data Quality Validation Queries
-- Run these after importing events to verify data integrity

-- 1. Check total records
SELECT COUNT(*) as total_events FROM events;
-- Expected: 35,360 (skipped 28 unmapped)

-- 2. Check year distribution
SELECT
    year,
    COUNT(*) as event_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM events
GROUP BY year
ORDER BY year;
-- Expected: 2025: ~34,349 | 2026: ~1,011

-- 3. Check NULL rates
SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE description IS NULL) as null_descriptions,
    ROUND(COUNT(*) FILTER (WHERE description IS NULL) * 100.0 / COUNT(*), 2) as desc_null_pct,
    COUNT(*) FILTER (WHERE media_path IS NULL) as null_media,
    ROUND(COUNT(*) FILTER (WHERE media_path IS NULL) * 100.0 / COUNT(*), 2) as media_null_pct,
    COUNT(*) FILTER (WHERE district IS NULL) as null_districts,
    ROUND(COUNT(*) FILTER (WHERE district IS NULL) * 100.0 / COUNT(*), 2) as district_null_pct,
    COUNT(*) FILTER (WHERE subcategory2 IS NULL) as null_subcategory2,
    ROUND(COUNT(*) FILTER (WHERE subcategory2 IS NULL) * 100.0 / COUNT(*), 2) as sub2_null_pct
FROM events;
-- Expected: ~7% NULL descriptions, ~32% NULL media, variable districts/subcategory2

-- 4. Check category distribution
SELECT
    category,
    COUNT(*) as event_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM events
GROUP BY category
ORDER BY COUNT(*) DESC;

-- 5. Check top 10 subcategories
SELECT
    category,
    subcategory,
    COUNT(*) as event_count
FROM events
GROUP BY category, subcategory
ORDER BY COUNT(*) DESC
LIMIT 10;

-- 6. Check for duplicate IDs (should be 0)
SELECT
    service_request_id,
    COUNT(*) as duplicates
FROM events
GROUP BY service_request_id
HAVING COUNT(*) > 1;
-- Expected: 0 rows

-- 7. Check status distribution
SELECT
    status,
    COUNT(*) as event_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM events
GROUP BY status;
-- Expected: ~90% closed, ~10% open

-- 8. Check most recent events
SELECT
    service_request_id,
    title,
    requested_at,
    status,
    category
FROM events
ORDER BY requested_at DESC
LIMIT 10;

-- 9. Check oldest events
SELECT
    service_request_id,
    title,
    requested_at,
    status,
    category
FROM events
ORDER BY requested_at ASC
LIMIT 10;

-- 10. Check district distribution (top 10)
SELECT
    district,
    COUNT(*) as event_count
FROM events
WHERE district IS NOT NULL
GROUP BY district
ORDER BY COUNT(*) DESC
LIMIT 10;

-- 11. Check zip code distribution (top 10)
SELECT
    zip_code,
    city,
    COUNT(*) as event_count
FROM events
GROUP BY zip_code, city
ORDER BY COUNT(*) DESC
LIMIT 10;

-- 12. Check coordinate ranges (should all be in Köln area)
SELECT
    MIN(lat) as min_lat,
    MAX(lat) as max_lat,
    MIN(lon) as min_lon,
    MAX(lon) as max_lon,
    AVG(lat) as avg_lat,
    AVG(lon) as avg_lon
FROM events;
-- Expected: lat ~50.8-51.1, lon ~6.7-7.2 (Köln region)

-- 13. Sample 5 random complete events
SELECT
    service_request_id,
    title,
    category,
    subcategory,
    district,
    requested_at,
    status
FROM events
ORDER BY RANDOM()
LIMIT 5;

-- 14. Test geospatial query (events within 1km of Köln city center)
-- Köln center coordinates: 50.9375, 6.9603
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

-- 15. Check for any records with invalid data
SELECT
    COUNT(*) FILTER (WHERE lat NOT BETWEEN 50 AND 52) as invalid_lat,
    COUNT(*) FILTER (WHERE lon NOT BETWEEN 6 AND 8) as invalid_lon,
    COUNT(*) FILTER (WHERE year NOT BETWEEN 2024 AND 2026) as invalid_year,
    COUNT(*) FILTER (WHERE sequence_number < 1) as invalid_sequence
FROM events;
-- Expected: All should be 0
