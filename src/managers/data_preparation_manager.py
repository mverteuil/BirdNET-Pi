import datetime

import pandas as pd


class DataPreparationManager:
    """Manages data preparation and manipulation for reporting and plotting."""

    @staticmethod
    def hms_to_dec(time_obj: datetime.time) -> float:
        """Convert a datetime.time object to its decimal hour representation."""
        hour = time_obj.hour
        minute = time_obj.minute / 60
        second = time_obj.second / 3600
        result = hour + minute + second
        return result

    @staticmethod
    def hms_to_str(time_obj: datetime.time) -> str:
        """Convert a datetime.time object to a formatted string (HH:MM)."""
        hour = time_obj.hour
        minute = time_obj.minute
        return f"{hour:02d}:{minute:02d}"

    def get_species_counts(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the counts of each common name in the DataFrame."""
        return df["Com_Name"].value_counts()

    def get_hourly_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a crosstabulation of common names by hour."""
        return pd.crosstab(df["Com_Name"], df.index.hour, dropna=True, margins=True)

    def get_daily_crosstab(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a crosstabulation of common names by date."""
        return pd.crosstab(df["Com_Name"], df.index.date, dropna=True, margins=True)

    def time_resample(self, df: pd.DataFrame, resample_time: str) -> pd.DataFrame:
        """Resample the DataFrame based on the given time interval."""
        if resample_time == "Raw":
            df_resample = df["Com_Name"]
        else:
            df_resample = (
                df.resample(resample_time)["Com_Name"].aggregate("unique").explode()
            )
        return df_resample
