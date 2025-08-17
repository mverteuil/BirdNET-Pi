"""Analytics domain for data analysis, reporting, and visualization.

This module handles all analytics-related functionality including:
- Data preparation and manipulation
- Statistical analysis and reporting
- Plotting and visualization
- Metrics calculation and aggregation
"""

from birdnetpi.analytics.data_preparation_manager import DataPreparationManager
from birdnetpi.analytics.plotting_manager import PlottingManager
from birdnetpi.analytics.reporting_manager import ReportingManager

__all__ = ["DataPreparationManager", "PlottingManager", "ReportingManager"]
