# Performance Profiling Guide

This guide explains how to profile BirdNET-Pi to identify performance bottlenecks.

## Quick Start

### Enable Profiling in Docker

BirdNET-Pi uses a separate Docker container with profiling tools to keep the production image lean.

1. Start the profiling container:
   ```bash
   # Using Docker Compose profiles (recommended)
   docker compose --profile profiling up -d

   # Or explicitly by service name
   docker compose up -d birdnet-pi-profiling
   ```

2. Visit any page with `?profile=1` in your browser:
   - Dashboard: http://localhost:8000/?profile=1
   - Settings: http://localhost:8000/admin/settings?profile=1
   - API endpoints: http://localhost:8000/api/overview?profile=1

3. The browser will display an interactive flame graph showing performance data.

**Note**: The profiling container includes pyinstrument (~5MB) which is not included in the production image for size optimization.

### Save Profiling Output

To save the profiling output for analysis:

```bash
# Save dashboard profile
curl "http://localhost:8000/?profile=1" > dashboard_profile.html

# Save API endpoint profile
curl "http://localhost:8000/api/overview?profile=1" > api_profile.html

# Open in browser
open dashboard_profile.html  # macOS
xdg-open dashboard_profile.html  # Linux
```

## Understanding the Flame Graph

The pyinstrument profiler generates an interactive flame graph:

- **Width** represents the total time spent in a function (including child calls)
- **Height** shows the call stack depth
- **Colors** differentiate between modules/packages
- **Click** on any box to zoom into that function
- **Search** for specific functions using the search box

### Key Areas to Check

1. **Database Operations**
   - Look for `query_detections`, `get_species_counts`
   - Multiple small queries indicate N+1 problem
   - Long bars indicate slow queries needing optimization

2. **Analytics Calculations**
   - `get_dashboard_summary`, `get_temporal_patterns`
   - Check if operations run sequentially that could be parallel

3. **System Status**
   - `_get_system_status`, hardware checks
   - These might benefit from caching

## Common Performance Issues

### 1. Sequential Async Operations
**Problem**: Multiple `await` statements running one after another
```python
# Slow - sequential
summary = await analytics_manager.get_dashboard_summary()
frequency = await analytics_manager.get_species_frequency_analysis()
temporal = await analytics_manager.get_temporal_patterns()
```

**Solution**: Use `asyncio.gather()` for parallel execution
```python
# Fast - parallel
summary, frequency, temporal = await asyncio.gather(
    analytics_manager.get_dashboard_summary(),
    analytics_manager.get_species_frequency_analysis(),
    analytics_manager.get_temporal_patterns()
)
```

### 2. Missing Database Indexes
**Problem**: Slow queries on frequently filtered columns

**Solution**: Add indexes to commonly queried fields:
- `timestamp` for date range queries
- `scientific_name` for species lookups
- `confidence` for threshold filtering

### 3. Expensive Aggregations
**Problem**: Complex COUNT, GROUP BY queries on large datasets

**Solution**:
- Add materialized views or summary tables
- Implement caching for expensive calculations
- Use background tasks to pre-calculate metrics

## CLI Profiling Tool

For detailed profiling of the landing page without Docker:

```bash
# Install development dependencies (includes profiling tools)
uv sync --group dev

# Then run the profiling tool
uv run profile-landing-page

# Profile with verbose output
uv run profile-landing-page --verbose

# Profile a specific component
uv run profile-landing-page --component metrics
uv run profile-landing-page --component species_frequency
uv run profile-landing-page --component system_status

# Combine options
uv run profile-landing-page -v -c temporal_patterns
```

This tool provides:
- Detailed timing breakdown of each operation
- Performance grading (Excellent/Good/Warning/Critical)
- Specific optimization recommendations

**Note**: The profiling dependencies are automatically included with dev dependencies for local development, but kept separate for lean production Docker images.

## Testing with Realistic Data

Profiling requires realistic data to identify actual bottlenecks:

```bash
# Generate test data
docker exec -it birdnet-pi generate-dummy-data --days 30 --detections-per-day 1000

# Then profile
curl "http://localhost:8000/?profile=1" > profile_with_data.html
```

## Optimization Workflow

1. **Profile First**: Always profile before optimizing
2. **Identify Hotspots**: Focus on functions taking >10% of total time
3. **Optimize**: Apply appropriate optimization strategy
4. **Profile Again**: Verify the improvement
5. **Document**: Note what was changed and why

## Advanced Profiling

### Profile Specific Endpoints

```bash
# Profile detection queries
curl "http://localhost:8000/api/detections?limit=100&profile=1" > detections_profile.html

# Profile species analysis
curl "http://localhost:8000/api/detections/species?profile=1" > species_profile.html
```

### Continuous Profiling

For production monitoring, use the appropriate container based on your needs:

```bash
# Production (no profiling overhead)
docker compose up -d

# Development/debugging (with profiling tools)
docker compose --profile profiling up -d

# Switch from production to profiling
docker compose down
docker compose --profile profiling up -d

# Switch back to production
docker compose down
docker compose up -d
```

## Optimization Strategies

Based on common bottlenecks found in profiling:

### 1. Database Query Optimization
- Add appropriate indexes
- Use query optimization (EXPLAIN ANALYZE)
- Batch operations instead of individual queries
- Consider read replicas for heavy read loads

### 2. Caching
- Cache expensive calculations (species counts, daily summaries)
- Use Redis or in-memory caching for frequently accessed data
- Implement cache invalidation on data changes

### 3. Parallel Processing
- Use `asyncio.gather()` for independent operations
- Implement connection pooling for database
- Use background tasks for non-critical operations

### 4. Frontend Optimization
- Implement pagination for large datasets
- Use progressive loading with JavaScript
- Add loading indicators for slow operations

## Troubleshooting

### Profiling Not Working

If `?profile=1` returns normal page instead of flame graph:

1. Check you're using the profiling container:
   ```bash
   docker ps --format "table {{.Names}}\t{{.Image}}"
   # Should show: birdnet-pi-profiling
   ```

2. If not, start the profiling container:
   ```bash
   docker compose --profile profiling up -d
   ```

3. Verify profiling is enabled in the container:
   ```bash
   docker exec birdnet-pi-profiling env | grep ENABLE_PROFILING
   # Should show: ENABLE_PROFILING=1
   ```

### High Memory Usage

If profiling shows high memory consumption:
- Check for memory leaks in long-running queries
- Ensure database connections are properly closed
- Use streaming for large result sets

## Further Reading

- [pyinstrument documentation](https://pyinstrument.readthedocs.io/)
- [Python AsyncIO Performance](https://docs.python.org/3/library/asyncio-task.html#running-tasks-concurrently)
- [SQLite Query Optimization](https://www.sqlite.org/queryplanner.html)
