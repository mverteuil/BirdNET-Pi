-- Performance indexes for analytics queries
-- These indexes significantly improve the performance of the analysis page

-- 1. Expression index for date grouping on detections
-- Speeds up queries that group by date(timestamp)
CREATE INDEX IF NOT EXISTS idx_detections_date_timestamp_species
ON detections(date(timestamp), scientific_name);

-- 2. Expression index for hourly grouping on detections
-- Speeds up queries that group by hour
CREATE INDEX IF NOT EXISTS idx_detections_hour_timestamp
ON detections(strftime('%Y-%m-%d %H:00', timestamp), scientific_name);

-- 3. Expression index for weather JOIN operations
-- Speeds up JOIN between detections and weather on hourly basis
CREATE INDEX IF NOT EXISTS idx_weather_hour_timestamp
ON weather(strftime('%Y-%m-%d %H:00:00', timestamp));

-- 4. Additional index for weather correlation queries
CREATE INDEX IF NOT EXISTS idx_detections_timestamp_confidence_species
ON detections(timestamp, confidence, scientific_name);

-- 5. Index for species accumulation queries (ORDER BY timestamp)
-- This already exists but verify it's optimized
CREATE INDEX IF NOT EXISTS idx_detections_timestamp_id
ON detections(timestamp, id);

-- Analyze tables to update SQLite's query planner statistics
ANALYZE detections;
ANALYZE weather;
