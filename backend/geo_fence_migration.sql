-- =============================================
-- Geo-Fence Migration: Add geographic + map-bounds
-- columns to the searches table so geo-fencing
-- state persists per chat/hunt session.
-- =============================================

-- 1. AI-extracted geographic region (e.g. "Midwest US", "Germany")
ALTER TABLE searches
ADD COLUMN IF NOT EXISTS geographic_region TEXT;

-- 2. ISO country code (e.g. "US", "DE")
ALTER TABLE searches
ADD COLUMN IF NOT EXISTS country_code VARCHAR(2);

-- 3. AI-extracted geo bounding box [sw_lat, sw_lng, ne_lat, ne_lng]
ALTER TABLE searches
ADD COLUMN IF NOT EXISTS geo_bounds JSONB;

-- 4. User-drawn map bounding box (distinct from AI-extracted)
ALTER TABLE searches
ADD COLUMN IF NOT EXISTS map_bounds JSONB;

-- 5. Whether the map panel was open (restore on resume)
ALTER TABLE searches
ADD COLUMN IF NOT EXISTS show_map BOOLEAN DEFAULT false;
