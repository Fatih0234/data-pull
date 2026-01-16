-- Migration: Create events table with indexes
-- Created: 2026-01-16
-- Description: Single-table design for 35K+ civic events with geospatial support

-- Enable PostGIS extension for geospatial queries
CREATE EXTENSION IF NOT EXISTS earthdistance CASCADE;

-- Create events table
CREATE TABLE events (
    -- Primary identifier
    service_request_id VARCHAR(20) PRIMARY KEY,

    -- Basic info
    title TEXT NOT NULL,
    description TEXT,
    requested_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('open', 'closed')),

    -- Location data
    lat DECIMAL(10, 8) NOT NULL,
    lon DECIMAL(11, 8) NOT NULL,
    address_string TEXT NOT NULL,

    -- Parsed address components
    zip_code VARCHAR(10),
    city VARCHAR(100),
    district VARCHAR(100),
    street VARCHAR(255),
    house_number VARCHAR(20),

    -- Category hierarchy (enriched from CSV)
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(150) NOT NULL,
    subcategory2 VARCHAR(150),
    service_name VARCHAR(150) NOT NULL,

    -- Media
    media_path VARCHAR(500),

    -- Computed fields for easy querying
    year SMALLINT NOT NULL,
    sequence_number INTEGER NOT NULL,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT valid_coordinates CHECK (
        lat BETWEEN -90 AND 90 AND
        lon BETWEEN -180 AND 180
    ),
    CONSTRAINT valid_year CHECK (year >= 2000 AND year <= 2100)
);

-- Create indexes for common queries
CREATE INDEX idx_events_requested_at ON events(requested_at DESC);
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_year ON events(year);
CREATE INDEX idx_events_category ON events(category);
CREATE INDEX idx_events_subcategory ON events(subcategory);
CREATE INDEX idx_events_district ON events(district) WHERE district IS NOT NULL;
CREATE INDEX idx_events_zip_code ON events(zip_code);

-- Create geospatial index for radius queries
-- This enables queries like "find events within 1km of a point"
CREATE INDEX idx_events_location ON events USING GIST (
    ll_to_earth(lat::float, lon::float)
);

-- Add comments for documentation
COMMENT ON TABLE events IS 'Civic events from Stadt Köln Sag''s uns reporting system';
COMMENT ON COLUMN events.service_request_id IS 'Unique ID format: {sequence}-{year} (e.g., 1039-2026)';
COMMENT ON COLUMN events.requested_at IS 'When the event was originally reported';
COMMENT ON COLUMN events.media_path IS 'Relative path from files/ directory (e.g., 2026-01/IMG_3744.jpeg)';
COMMENT ON COLUMN events.year IS 'Extracted from service_request_id for fast filtering';
COMMENT ON COLUMN events.sequence_number IS 'Sequence number within the year';
