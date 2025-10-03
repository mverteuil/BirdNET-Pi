import math
import random
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import TypedDict

import numpy as np

from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.utils.time_periods import calculate_period_boundaries, period_to_days


class DashboardSummaryDict(TypedDict):
    """Dashboard summary statistics."""

    species_total: int
    detections_today: int
    species_week: int
    storage_gb: float
    hours_monitored: float
    confidence_threshold: float


class SpeciesFrequencyDict(TypedDict):
    """Species frequency analysis result."""

    name: str
    scientific_name: str
    count: int
    percentage: float
    category: str


class TemporalPatternsDict(TypedDict):
    """Temporal pattern analysis result."""

    hourly_distribution: list[int]
    peak_hour: int | None
    periods: dict[str, int]


class ScatterDataDict(TypedDict):
    """Scatter plot data point."""

    time: float
    confidence: float
    species: str
    frequency_category: str


class AnalyticsManager:
    """Performs calculations and analysis on raw data using DetectionQueryService methods."""

    def __init__(self, detection_query_service: DetectionQueryService, config: BirdNETConfig):
        self.detection_query_service = detection_query_service
        self.config = config

    # --- Dashboard Analytics ---

    async def get_dashboard_summary(self) -> DashboardSummaryDict:
        """Calculate summary statistics for dashboard."""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)

        # Get counts using the new DataManager methods
        detections_today = await self.detection_query_service.get_detection_count(today_start, now)
        species_total = await self.detection_query_service.get_unique_species_count(
            datetime.min.replace(tzinfo=None), now
        )
        species_week = await self.detection_query_service.get_unique_species_count(week_ago, now)

        # Get storage metrics
        storage = await self.detection_query_service.get_storage_metrics()

        return {
            "species_total": species_total,
            "detections_today": detections_today,
            "species_week": species_week,
            "storage_gb": storage.get("total_bytes", 0) / (1024**3),
            "hours_monitored": storage.get("total_duration", 0) / 3600,
            "confidence_threshold": self.config.species_confidence_threshold,
        }

    async def get_species_frequency_analysis(self, hours: int = 24) -> list[SpeciesFrequencyDict]:
        """Analyze species frequency distribution."""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        # Get species counts from DataManager
        species_counts = await self.detection_query_service.get_species_counts(start_time, end_time)

        # Calculate total for percentages
        total = sum(s["count"] for s in species_counts)

        return [
            {
                "name": s["common_name"] or s["scientific_name"],
                "scientific_name": s["scientific_name"],
                "count": s["count"],
                "percentage": (s["count"] / total * 100) if total > 0 else 0,
                "category": self._categorize_frequency(s["count"]),
            }
            for s in species_counts
        ]

    async def get_temporal_patterns(self, date: date | None = None) -> TemporalPatternsDict:
        """Analyze temporal detection patterns."""
        if date is None:
            date = datetime.now().date()

        # Get hourly counts from DataManager
        hourly_data = await self.detection_query_service.get_hourly_counts(date)

        # Create 24-hour array with counts
        hourly_dist = [0] * 24
        for item in hourly_data:
            hour = item["hour"]
            hourly_dist[hour] = item["count"]

        # Identify peak periods
        max_count = max(hourly_dist) if hourly_dist else 0
        # Return 6 AM as default peak hour when no detections (typical bird activity time)
        peak_hour = hourly_dist.index(max_count) if max_count > 0 else 6

        # Categorize activity periods (6 equal 4-hour periods)
        night_early = sum(hourly_dist[0:4])  # 12am-4am
        dawn = sum(hourly_dist[4:8])  # 4am-8am
        morning = sum(hourly_dist[8:12])  # 8am-12pm
        afternoon = sum(hourly_dist[12:16])  # 12pm-4pm
        evening = sum(hourly_dist[16:20])  # 4pm-8pm
        night_late = sum(hourly_dist[20:24])  # 8pm-12am

        return {
            "hourly_distribution": hourly_dist,
            "peak_hour": peak_hour,
            "periods": {
                "night_early": night_early,  # 12am-4am
                "dawn": dawn,  # 4am-8am
                "morning": morning,  # 8am-12pm
                "afternoon": afternoon,  # 12pm-4pm
                "evening": evening,  # 4pm-8pm
                "night_late": night_late,  # 8pm-12am
            },
        }

    async def get_detection_scatter_data(self, hours: int = 24) -> list[ScatterDataDict]:
        """Prepare detection data for scatter visualization."""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        # Get detections in time range - always returns DetectionWithTaxa
        # Use a higher limit to avoid truncation in busy periods
        # 1000 detections should handle even very busy days
        detections = await self.detection_query_service.query_detections(
            start_date=start_time,
            end_date=end_time,
            order_by="timestamp",
            order_desc=True,
            limit=1000,
        )

        # Get species frequency counts from database aggregation
        species_counts = await self.detection_query_service.get_species_counts(
            start_time=start_time,
            end_time=end_time,
        )

        # Build a lookup map for frequency counts
        frequency_map = {
            species["common_name"]: species["count"]
            for species in species_counts
            if species["common_name"]
        }

        # Build scatter data with model_dump and frequency category
        result = []
        for d in detections:
            if d.timestamp:
                # Use model_dump to get all fields properly serialized
                detection_data = d.model_dump()
                # Add computed fields for scatter plot
                detection_data.update(
                    {
                        "time": d.timestamp.hour
                        + (d.timestamp.minute / 60),  # Decimal hour for charting
                        "frequency_category": self._categorize_frequency(
                            frequency_map.get(d.common_name, 0)
                        ),
                    }
                )
                result.append(detection_data)

        return result

    async def get_aggregate_hourly_pattern(self, days: int = 30) -> list[list[int]]:
        """Get aggregated hourly pattern over N days for heatmap.

        For periods longer than 7 days, aggregates all data by day-of-week
        and hour to show patterns like "Mondays at 8am" across the entire period.

        Returns:
            List of lists for heatmap (7 days-of-week x 24 hours)
        """
        if days <= 7:
            # For short periods, return daily data
            return await self.get_weekly_heatmap_data(days)

        # For longer periods, aggregate by day-of-week
        # Initialize 7x24 grid (Sunday=0 to Saturday=6)
        weekday_hourly = [[0] * 24 for _ in range(7)]

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # Iterate through all days in the period
        current_date = start_date
        while current_date <= end_date:
            # Get hourly counts for this day
            hourly_data = await self.detection_query_service.get_hourly_counts(current_date)

            # Get day of week (0=Monday, 6=Sunday in Python)
            # Convert to 0=Sunday, 6=Saturday for display
            weekday = (current_date.weekday() + 1) % 7

            # Add counts to the appropriate day-of-week
            for item in hourly_data:
                hour = int(item["hour"]) if isinstance(item["hour"], str) else item["hour"]
                count = item["count"]
                weekday_hourly[weekday][hour] += count

            current_date += timedelta(days=1)

        return weekday_hourly

    async def get_weekly_heatmap_data(self, days: int = 7) -> list[list[int]]:
        """Get hourly detection counts for heatmap visualization.

        For periods <= 7 days: Returns actual daily data (padded to 7 days if needed)
        For periods > 7 days: Returns averaged weekday patterns (Mon-Sun)

        Args:
            days: Number of days to analyze

        Returns:
            List of 7 lists, each with 24 hourly counts
        """
        end_date = datetime.now().date()

        if days <= 7:
            # For 7 days or less, show actual daily data
            heatmap_data = []

            # Always return 7 days of data, padding with zeros if needed
            for day_offset in range(7):
                if day_offset < days:
                    # Get actual data for this day
                    target_date = end_date - timedelta(days=day_offset)
                    hourly_data = await self.detection_query_service.get_hourly_counts(target_date)

                    # Create 24-hour array with counts
                    day_counts = [0] * 24
                    for item in hourly_data:
                        hour = item["hour"]
                        day_counts[hour] = item["count"]
                else:
                    # Pad with zeros for days outside the period
                    day_counts = [0] * 24

                # Insert at beginning to maintain chronological order
                heatmap_data.insert(0, day_counts)

            return heatmap_data
        else:
            # For more than 7 days, return averaged weekday patterns
            # Aggregate by weekday (0=Monday, 6=Sunday)
            weekday_hourly_totals = defaultdict(lambda: [0] * 24)
            weekday_day_counts = defaultdict(int)

            for day_offset in range(days):
                target_date = end_date - timedelta(days=day_offset)
                weekday = target_date.weekday()  # 0=Monday, 6=Sunday

                hourly_data = await self.detection_query_service.get_hourly_counts(target_date)
                weekday_day_counts[weekday] += 1

                for item in hourly_data:
                    hour = item["hour"]
                    weekday_hourly_totals[weekday][hour] += item["count"]

            # Average the counts and format for 7-day week display
            # Order: Sunday (6), Monday (0), Tuesday (1), ..., Saturday (5)
            weekday_order = [6, 0, 1, 2, 3, 4, 5]  # Sun, Mon, Tue, Wed, Thu, Fri, Sat
            heatmap_data = []

            for weekday in weekday_order:
                if weekday_day_counts[weekday] > 0:
                    # Calculate averages for this weekday
                    avg_counts = [
                        total // weekday_day_counts[weekday]
                        for total in weekday_hourly_totals[weekday]
                    ]
                else:
                    # No data for this weekday
                    avg_counts = [0] * 24

                heatmap_data.append(avg_counts)

            return heatmap_data

    async def get_weekly_patterns(self) -> dict[str, list[int]]:
        """Get detection patterns grouped by day of week.

        Returns:
            Dict with keys 'sun', 'mon', etc. and hourly count arrays
        """
        # Get past 28 days to have multiple samples per weekday
        days_to_analyze = 28
        end_date = datetime.now().date()

        # Aggregate by weekday
        weekday_patterns = defaultdict(lambda: [0] * 24)
        weekday_counts = defaultdict(int)

        for day_offset in range(days_to_analyze):
            target_date = end_date - timedelta(days=day_offset)
            weekday = target_date.weekday()  # 0=Monday, 6=Sunday

            hourly_data = await self.detection_query_service.get_hourly_counts(target_date)
            weekday_counts[weekday] += 1

            for item in hourly_data:
                hour = item["hour"]
                weekday_patterns[weekday][hour] += item["count"]

        # Average the counts and format for display
        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        result = {}

        for day_num, day_name in enumerate(day_names):
            if weekday_counts[day_num] > 0:
                # Average the counts
                avg_pattern = [
                    count // weekday_counts[day_num] for count in weekday_patterns[day_num]
                ]
                result[day_name] = avg_pattern
            else:
                result[day_name] = [0] * 24

        # Rearrange to start with Sunday
        result = {
            "sun": result["sun"],
            "mon": result["mon"],
            "tue": result["tue"],
            "wed": result["wed"],
            "thu": result["thu"],
            "fri": result["fri"],
            "sat": result["sat"],
        }

        return result

    async def get_detection_frequency_distribution(self, days: int = 7) -> list[dict[str, str]]:
        """Get stem-and-leaf plot data for detection frequency distribution.

        Returns:
            List of dicts with 'stem' and 'leaves' for display
        """
        # Collect all hourly counts for the period
        hourly_counts = []
        end_date = datetime.now().date()

        for day_offset in range(days):
            target_date = end_date - timedelta(days=day_offset)
            hourly_data = await self.detection_query_service.get_hourly_counts(target_date)

            for item in hourly_data:
                if item["count"] > 0:
                    hourly_counts.append(item["count"])

        if not hourly_counts:
            return [{"stem": "0", "leaves": "No data"}]

        # Create stem-and-leaf structure
        stem_leaf = defaultdict(list)
        for count in sorted(hourly_counts):
            stem = count // 10
            leaf = count % 10
            stem_leaf[stem].append(str(leaf))

        # Format for display
        result = []
        for stem in sorted(stem_leaf.keys()):
            result.append({"stem": str(stem), "leaves": " ".join(stem_leaf[stem])})

        return result

    async def get_species_hourly_patterns(self, species_name: str, days: int = 7) -> list[int]:
        """Get hourly detection pattern for a specific species.

        Args:
            species_name: Scientific or common name of species
            days: Number of days to analyze

        Returns:
            List of 24 hourly counts totaled over the period
        """
        hourly_totals = [0] * 24
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        # Get all detections for this species in the range - always returns DetectionWithTaxa
        detections = await self.detection_query_service.query_detections(
            start_date=start_time, end_date=end_time, order_by="timestamp", order_desc=True
        )

        # Filter for the species and aggregate by hour
        for d in detections:
            # Check against all name variants (scientific, common, IOC, translated)
            if (
                d.scientific_name == species_name
                or d.common_name == species_name
                or d.ioc_english_name == species_name
                or d.translated_name == species_name
            ):
                hour = d.timestamp.hour if d.timestamp else 0
                hourly_totals[hour] += 1

        # Return raw counts, not averaged (sparklines show patterns, not averages)
        return hourly_totals

    @staticmethod
    def _categorize_frequency(count: int) -> str:
        """Categorize species by detection frequency.

        Thresholds are calibrated for 24-hour periods:
        - Common: More than 20 detections (frequent visitor)
        - Regular: 6-20 detections (occasional visitor)
        - Uncommon: 5 or fewer detections (rare sighting)
        """
        if count > 20:
            return "common"
        elif count > 5:
            return "regular"
        else:
            return "uncommon"

    # === ECOLOGICAL ANALYSIS METHODS ===

    async def calculate_diversity_timeline(
        self, start_date: datetime, end_date: datetime, temporal_resolution: str = "daily"
    ) -> list[dict]:
        """Calculate diversity metrics over time.

        Includes Shannon diversity, Simpson diversity, species richness, and Pielou's evenness.
        """
        # Get raw species counts by period
        period_data = await self.detection_query_service.get_species_counts_by_period(
            start_date=start_date, end_date=end_date, temporal_resolution=temporal_resolution
        )

        metrics = []
        for period_info in period_data:
            species_counts = period_info["species_counts"]
            total = sum(species_counts.values())
            richness = len(species_counts)

            if total > 0:
                # Shannon diversity index: H' = -Σ(pi * ln(pi))
                shannon = -sum(
                    (count / total) * math.log(count / total)
                    for count in species_counts.values()
                    if count > 0
                )

                # Simpson diversity index: D = 1 - Σ(pi²)
                simpson = 1 - sum((count / total) ** 2 for count in species_counts.values())

                # Pielou's evenness: J = H' / ln(S)
                evenness = shannon / math.log(richness) if richness > 1 else 1.0
            else:
                shannon = simpson = evenness = 0.0

            metrics.append(
                {
                    "period": period_info["period"],
                    "richness": richness,
                    "shannon": round(shannon, 4),
                    "simpson": round(simpson, 4),
                    "evenness": round(evenness, 4),
                    "total_detections": total,
                }
            )

        return metrics

    async def calculate_species_accumulation(  # noqa: C901
        self, start_date: datetime, end_date: datetime, method: str = "collector"
    ) -> dict:
        """Generate species accumulation curve.

        Methods:
        - collector: Actual order of observation
        - random: Average over multiple random permutations
        - rarefaction: Expected species for given sample sizes
        """
        # Get raw detection data
        detections = await self.detection_query_service.get_detections_for_accumulation(
            start_date=start_date, end_date=end_date
        )

        if not detections:
            return {"samples": [], "species_counts": [], "method": method}

        if method == "collector":
            # Collector's curve - actual order of observation
            species_seen = set()
            accumulation = []

            for i, (_, species) in enumerate(detections, 1):
                species_seen.add(species)
                accumulation.append({"sample": i, "species_count": len(species_seen)})

            return {
                "samples": [a["sample"] for a in accumulation],
                "species_counts": [a["species_count"] for a in accumulation],
                "method": method,
            }

        elif method == "random":
            # Random accumulation - average over multiple permutations
            n_permutations = min(100, len(detections))
            all_species = [d[1] for d in detections]
            max_samples = len(all_species)

            accumulation_curves = []
            for _ in range(n_permutations):
                random.shuffle(all_species)
                species_seen = set()
                curve = []

                for species in all_species:
                    species_seen.add(species)
                    curve.append(len(species_seen))

                accumulation_curves.append(curve)

            # Average across permutations
            mean_curve = np.mean(accumulation_curves, axis=0)

            return {
                "samples": list(range(1, max_samples + 1)),
                "species_counts": mean_curve.tolist(),
                "method": method,
            }

        else:  # rarefaction
            # Rarefaction curve - expected species for given sample sizes
            all_species = [d[1] for d in detections]
            species_counts = defaultdict(int)
            for species in all_species:
                species_counts[species] += 1

            total_individuals = len(all_species)
            max_sample_size = min(total_individuals, 1000)

            rarefaction_curve = []
            for sample_size in range(1, max_sample_size + 1, max(1, max_sample_size // 100)):
                # Calculate expected species richness
                expected_species = 0
                for _species, count in species_counts.items():
                    # Probability that species is NOT in sample
                    prob_absent = 1.0
                    for i in range(sample_size):
                        prob_absent *= (total_individuals - count - i) / (total_individuals - i)
                        if prob_absent <= 0:
                            break
                    expected_species += 1 - max(0, prob_absent)

                rarefaction_curve.append(
                    {
                        "sample_size": sample_size,
                        "expected_species": expected_species,
                    }
                )

            return {
                "samples": [r["sample_size"] for r in rarefaction_curve],
                "species_counts": [r["expected_species"] for r in rarefaction_curve],
                "method": method,
            }

    async def calculate_community_similarity(
        self, periods: list[tuple[datetime, datetime]], index_type: str = "jaccard"
    ) -> dict:
        """Calculate community similarity between time periods.

        Index types:
        - jaccard: |A ∩ B| / |A U B|
        - sorensen: 2|A ∩ B| / (|A| + |B|)
        - bray_curtis: 2 * min_abundances / total_abundances
        """
        # Get species counts for each period
        period_data = await self.detection_query_service.get_species_counts_for_periods(periods)

        n_periods = len(periods)
        similarity_matrix = np.zeros((n_periods, n_periods))

        for i in range(n_periods):
            for j in range(n_periods):
                if i == j:
                    similarity_matrix[i, j] = 1.0
                elif j > i:
                    similarity = self._calculate_similarity(
                        period_data[i], period_data[j], index_type
                    )
                    similarity_matrix[i, j] = similarity
                    similarity_matrix[j, i] = similarity

        # Format for display with period labels
        period_labels = [f"Period {i + 1}" for i in range(len(periods))]
        return {
            "labels": period_labels,
            "matrix": similarity_matrix.tolist(),
            "index_type": index_type,
        }

    def _calculate_similarity(
        self,
        community1: dict[str, int],
        community2: dict[str, int],
        index_type: str,
    ) -> float:
        """Calculate similarity index between two communities."""
        species1 = set(community1.keys())
        species2 = set(community2.keys())

        if index_type == "jaccard":
            # Jaccard index: |A ∩ B| / |A U B|
            intersection = len(species1 & species2)
            union = len(species1 | species2)
            return intersection / union if union > 0 else 0.0

        elif index_type == "sorensen":
            # Sørensen-Dice index: 2|A ∩ B| / (|A| + |B|)
            intersection = len(species1 & species2)
            total = len(species1) + len(species2)
            return 2 * intersection / total if total > 0 else 0.0

        else:  # bray_curtis
            # Bray-Curtis similarity: 2 * min_abundances / total_abundances
            all_species = species1 | species2
            min_sum = sum(min(community1.get(sp, 0), community2.get(sp, 0)) for sp in all_species)
            total_sum = sum(community1.values()) + sum(community2.values())
            return 2 * min_sum / total_sum if total_sum > 0 else 0.0

    async def calculate_beta_diversity(
        self, start_date: datetime, end_date: datetime, window_size: timedelta
    ) -> list[dict]:
        """Calculate temporal beta diversity (species turnover).

        Beta diversity measures how species composition changes over time.
        Turnover rate = (species gained + species lost) / (2 * total species)
        """
        # Get species sets for sliding windows
        windows = await self.detection_query_service.get_species_sets_by_window(
            start_date=start_date, end_date=end_date, window_size=window_size
        )

        beta_diversity = []
        for i in range(len(windows) - 1):
            current_window = windows[i]
            next_window = windows[i + 1]

            current_species = set(current_window["species"])
            next_species = set(next_window["species"])

            # Calculate turnover
            gained = next_species - current_species
            lost = current_species - next_species
            total_species = len(current_species | next_species)

            turnover_rate = (
                (len(gained) + len(lost)) / (2 * total_species) if total_species > 0 else 0
            )

            beta_diversity.append(
                {
                    "period_start": current_window["period_start"],
                    "period_end": current_window["period_end"],
                    "turnover_rate": round(turnover_rate, 4),
                    "species_gained": len(gained),
                    "species_lost": len(lost),
                    "total_species": len(current_species),
                }
            )

        return beta_diversity

    async def get_weather_correlation_data(self, start_date: datetime, end_date: datetime) -> dict:
        """Get weather correlation data from DetectionQueryService."""
        return await self.detection_query_service.get_weather_correlations(
            start_date=start_date, end_date=end_date
        )

    def calculate_correlation(self, x: list, y: list) -> float:
        """Calculate Pearson correlation coefficient between two variables.

        Args:
            x: First variable values
            y: Second variable values

        Returns:
            Correlation coefficient between -1 and 1
        """
        # Remove None values
        pairs = [
            (xi, yi) for xi, yi in zip(x, y, strict=False) if xi is not None and yi is not None
        ]
        if len(pairs) < 2:
            return 0.0

        x_vals = [p[0] for p in pairs]
        y_vals = [p[1] for p in pairs]

        n = len(x_vals)
        if n == 0:
            return 0.0

        x_mean = sum(x_vals) / n
        y_mean = sum(y_vals) / n

        numerator = sum(
            (xi - x_mean) * (yi - y_mean) for xi, yi in zip(x_vals, y_vals, strict=False)
        )
        denominator = (
            sum((xi - x_mean) ** 2 for xi in x_vals) * sum((yi - y_mean) ** 2 for yi in y_vals)
        ) ** 0.5

        return round(numerator / denominator, 3) if denominator != 0 else 0.0

    # === COMPARISON AND ANALYSIS METHODS ===

    async def compare_period_diversity(
        self, period1: tuple[datetime, datetime], period2: tuple[datetime, datetime]
    ) -> dict:
        """Compare diversity metrics between two periods."""
        # Get metrics for both periods using our calculate method
        metrics1 = await self.calculate_diversity_timeline(
            start_date=period1[0], end_date=period1[1], temporal_resolution="daily"
        )

        metrics2 = await self.calculate_diversity_timeline(
            start_date=period2[0], end_date=period2[1], temporal_resolution="daily"
        )

        # Calculate averages and differences
        def avg_metric(metrics: list[dict], key: str) -> float:
            values = [m[key] for m in metrics if key in m]
            return sum(values) / len(values) if values else 0

        return {
            "period1": {
                "avg_shannon": avg_metric(metrics1, "shannon"),
                "avg_simpson": avg_metric(metrics1, "simpson"),
                "avg_richness": avg_metric(metrics1, "richness"),
                "avg_evenness": avg_metric(metrics1, "evenness"),
            },
            "period2": {
                "avg_shannon": avg_metric(metrics2, "shannon"),
                "avg_simpson": avg_metric(metrics2, "simpson"),
                "avg_richness": avg_metric(metrics2, "richness"),
                "avg_evenness": avg_metric(metrics2, "evenness"),
            },
            "changes": {
                "shannon_change": avg_metric(metrics2, "shannon") - avg_metric(metrics1, "shannon"),
                "simpson_change": avg_metric(metrics2, "simpson") - avg_metric(metrics1, "simpson"),
                "richness_change": avg_metric(metrics2, "richness")
                - avg_metric(metrics1, "richness"),
                "evenness_change": avg_metric(metrics2, "evenness")
                - avg_metric(metrics1, "evenness"),
            },
        }

    async def get_period_statistics(self, period: str, timezone: str = "UTC") -> dict:
        """Calculate statistics for a given period.

        Args:
            period: Time period (day, week, month, season, year, historical)
            timezone: Timezone for calculations

        Returns:
            Dictionary with period statistics
        """
        # Calculate period boundaries
        start_date, end_date = calculate_period_boundaries(period, timezone=timezone)

        # Convert to UTC for queries
        if timezone != "UTC":
            start_utc = start_date.astimezone(UTC)
            end_utc = end_date.astimezone(UTC)
        else:
            start_utc = start_date
            end_utc = end_date

        # Get species summary for the period
        species_summary = await self.detection_query_service.get_species_summary(
            since=start_utc.replace(tzinfo=None)
            if start_utc != datetime.min.replace(tzinfo=UTC)
            else None
        )

        # Calculate statistics
        total_detections = await self.detection_query_service.get_detection_count(
            start_time=start_utc.replace(tzinfo=None),
            end_time=end_utc.replace(tzinfo=None),
        )
        unique_species = len(species_summary) if species_summary else 0

        # Get peak activity
        peak_hour, peak_count = await self.calculate_peak_activity(start_utc, end_utc)

        return {
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "total_detections": total_detections,
            "unique_species": unique_species,
            "species_summary": species_summary,
            "peak_hour": peak_hour,
            "peak_count": peak_count,
        }

    async def calculate_peak_activity(
        self, start_date: datetime, end_date: datetime
    ) -> tuple[int, int]:
        """Calculate peak activity hour for a time period.

        Args:
            start_date: Start of period
            end_date: End of period

        Returns:
            Tuple of (peak_hour, detection_count)
        """
        # Get hourly counts for the period
        # get_hourly_counts expects a target_date (date object)
        hourly_counts = await self.detection_query_service.get_hourly_counts(
            target_date=start_date.date()
        )

        if not hourly_counts:
            return 12, 0  # Default to noon if no data

        # Find the hour with max detections
        peak_hour = 12
        peak_count = 0
        for entry in hourly_counts:
            if entry["count"] > peak_count:
                peak_count = entry["count"]
                peak_hour = entry["hour"]

        return peak_hour, peak_count

    async def get_detection_trends(self, period: str, timezone: str = "UTC") -> dict[str, float]:
        """Calculate detection trends compared to previous period.

        Args:
            period: Current time period
            timezone: Timezone for calculations

        Returns:
            Dictionary with trend percentages
        """
        # Get current period statistics
        current_stats = await self.get_period_statistics(period, timezone)

        # Calculate previous period dates
        days = period_to_days(period)
        if days is None:  # Historical period
            return {"detection_trend": 0, "species_trend": 0}

        # Get previous period by shifting back
        now = datetime.now(UTC)
        prev_start = now - timedelta(days=days * 2)
        prev_end = now - timedelta(days=days)

        # Get previous period counts
        prev_detections = await self.detection_query_service.get_detection_count(
            start_time=prev_start.replace(tzinfo=None),
            end_time=prev_end.replace(tzinfo=None),
        )
        prev_species = await self.detection_query_service.get_unique_species_count(
            start_time=prev_start.replace(tzinfo=None),
            end_time=prev_end.replace(tzinfo=None),
        )

        # Calculate trends
        detection_trend = 0
        if prev_detections > 0:
            detection_trend = (
                (current_stats["total_detections"] - prev_detections) / prev_detections
            ) * 100

        species_trend = 0
        if prev_species > 0:
            species_trend = ((current_stats["unique_species"] - prev_species) / prev_species) * 100

        return {
            "detection_trend": round(detection_trend, 1),
            "species_trend": round(species_trend, 1),
        }
