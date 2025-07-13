import datetime
import subprocess
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from suntime import Sun

from services.database_manager import DatabaseManager
from utils.config_file_parser import ConfigFileParser
from utils.file_path_resolver import FilePathResolver


class ReportingManager:
    def __init__(
        self, db_manager: DatabaseManager, file_path_resolver: FilePathResolver
    ):
        self.db_manager = db_manager
        self.file_path_resolver = file_path_resolver
        self.config = ConfigFileParser(
            self.file_path_resolver.get_birdnet_pi_config_path()
        ).load_config()

    def get_data(self):
        df = self.db_manager.get_all_detections()
        df["DateTime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
        df = df.set_index("DateTime")
        return df

    def get_weekly_report_data(self):
        today = datetime.date.today()
        # Sunday of the week that just finished
        last_sunday = today - datetime.timedelta(days=today.weekday() + 1)
        start_date = last_sunday - datetime.timedelta(days=6)
        end_date = last_sunday

        # Calculate dates for the prior week
        prior_start_date = start_date - datetime.timedelta(days=7)
        prior_end_date = end_date - datetime.timedelta(days=7)

        # Connect to the database
        self.db_manager.connect()

        # Get stats for the current week
        current_week_stats_query = """
            SELECT COUNT(*) as total_count, COUNT(DISTINCT Com_Name) as unique_species
            FROM detections
            WHERE Date BETWEEN ? AND ?
        """
        current_week_stats = self.db_manager.fetch_one(
            current_week_stats_query, (str(start_date), str(end_date))
        )

        # Get stats for the prior week
        prior_week_stats_query = """
            SELECT COUNT(*) as total_count, COUNT(DISTINCT Com_Name) as unique_species
            FROM detections
            WHERE Date BETWEEN ? AND ?
        """
        prior_week_stats = self.db_manager.fetch_one(
            prior_week_stats_query, (str(prior_start_date), str(prior_end_date))
        )

        # Get top 10 species for the current week with their counts from the prior week
        top_species_query = """
        WITH CurrentWeekCounts AS (
            SELECT Com_Name, COUNT(*) as count
            FROM detections
            WHERE Date BETWEEN ? AND ?
            GROUP BY Com_Name
        ),
        PriorWeekCounts AS (
            SELECT Com_Name, COUNT(*) as count
            FROM detections
            WHERE Date BETWEEN ? AND ?
            GROUP BY Com_Name
        )
        SELECT
            c.Com_Name,
            c.count as current_count,
            COALESCE(p.count, 0) as prior_count
        FROM CurrentWeekCounts c
        LEFT JOIN PriorWeekCounts p ON c.Com_Name = p.Com_Name
        ORDER BY current_count DESC
        LIMIT 10
        """
        top_10_species_rows = self.db_manager.fetch_all(
            top_species_query,
            (
                str(start_date),
                str(end_date),
                str(prior_start_date),
                str(prior_end_date),
            ),
        )

        top_10_species = []
        if top_10_species_rows:
            for row in top_10_species_rows:
                current_count = row["current_count"]
                prior_count = row["prior_count"]
                percentage_diff = 0
                if prior_count > 0:
                    percentage_diff = round(
                        ((current_count - prior_count) / prior_count) * 100
                    )

                top_10_species.append(
                    {
                        "com_name": row["Com_Name"],
                        "count": current_count,
                        "percentage_diff": percentage_diff,
                    }
                )

        # Get new species for the current week
        new_species_query = """
        SELECT Com_Name, COUNT(*) as count
        FROM detections
        WHERE Date BETWEEN ? AND ?
          AND Com_Name NOT IN (
            SELECT DISTINCT Com_Name
            FROM detections
            WHERE Date < ?
          )
        GROUP BY Com_Name
        ORDER BY count DESC
        """
        new_species_rows = self.db_manager.fetch_all(
            new_species_query, (str(start_date), str(end_date), str(start_date))
        )
        new_species = (
            [
                {"com_name": row["Com_Name"], "count": row["count"]}
                for row in new_species_rows
            ]
            if new_species_rows
            else []
        )

        # Disconnect from the database
        self.db_manager.disconnect()

        # Extract counts
        total_detections_current = (
            current_week_stats["total_count"] if current_week_stats else 0
        )
        unique_species_current = (
            current_week_stats["unique_species"] if current_week_stats else 0
        )
        total_detections_prior = (
            prior_week_stats["total_count"] if prior_week_stats else 0
        )
        unique_species_prior = (
            prior_week_stats["unique_species"] if prior_week_stats else 0
        )

        # Calculate percentage differences
        percentage_diff_total = 0
        if total_detections_prior > 0:
            percentage_diff_total = round(
                (
                    (total_detections_current - total_detections_prior)
                    / total_detections_prior
                )
                * 100
            )

        percentage_diff_unique_species = 0
        if unique_species_prior > 0:
            percentage_diff_unique_species = round(
                ((unique_species_current - unique_species_prior) / unique_species_prior)
                * 100
            )

        return {
            "start_date": str(start_date),
            "end_date": str(end_date),
            "week_number": start_date.isocalendar()[1],
            "total_detections_current": total_detections_current,
            "unique_species_current": unique_species_current,
            "total_detections_prior": total_detections_prior,
            "unique_species_prior": unique_species_prior,
            "percentage_diff_total": percentage_diff_total,
            "percentage_diff_unique_species": percentage_diff_unique_species,
            "top_10_species": top_10_species,
            "new_species": new_species,
        }

    def generate_multi_day_species_and_hourly_plot(
        self, df, resample_sel, start_date, end_date, top_N, specie
    ):
        df5 = self.time_resample(df, resample_sel)
        hourly = self.get_hourly_crosstab(df5)
        top_N_species = self.get_species_counts(df5)[:top_N]

        df_counts = int(hourly[hourly.index == specie]["All"].iloc[0])
        fig = make_subplots(
            rows=3,
            cols=2,
            specs=[
                [{"type": "xy", "rowspan": 3}, {"type": "polar", "rowspan": 2}],
                [{"rowspan": 1}, {"rowspan": 1}],
                [None, {"type": "xy", "rowspan": 1}],
            ],
            subplot_titles=(
                "<b>Top "
                + str(top_N)
                + " Species in Date Range "
                + str(start_date)
                + " to "
                + str(end_date)
                + "<br>for "
                + str(resample_sel)
                + " sampling interval."
                + "</b>",
                "Total Detect:" + str("{:,}".format(df_counts)),
            ),
        )
        fig.layout.annotations[1].update(x=0.7, y=0.25, font_size=15)

        fig.add_trace(
            go.Bar(
                y=top_N_species.index,
                x=top_N_species,
                orientation="h",
                marker_color="seagreen",
            ),
            row=1,
            col=1,
        )

        fig.update_layout(
            margin=dict(l=0, r=0, t=50, b=0),
            yaxis={"categoryorder": "total ascending"},
        )

        theta = np.linspace(0.0, 360, 24, endpoint=False)

        detections = hourly.loc[specie]
        fig.add_trace(
            go.Barpolar(r=detections, theta=theta, marker_color="seagreen"),
            row=1,
            col=2,
        )
        fig.update_layout(
            autosize=False,
            width=1000,
            height=500,
            showlegend=False,
            polar=dict(
                radialaxis=dict(
                    tickfont_size=15,
                    showticklabels=False,
                    hoverformat="#%{theta}: <br>Popularity: %{percent} </br> %{r}",
                ),
                angularaxis=dict(
                    tickfont_size=15,
                    rotation=-90,
                    direction="clockwise",
                    tickmode="array",
                    tickvals=[
                        0,
                        15,
                        35,
                        45,
                        60,
                        75,
                        90,
                        105,
                        120,
                        135,
                        150,
                        165,
                        180,
                        195,
                        210,
                        225,
                        240,
                        255,
                        270,
                        285,
                        300,
                        315,
                        330,
                        345,
                    ],
                    ticktext=[
                        "12am",
                        "1am",
                        "2am",
                        "3am",
                        "4am",
                        "5am",
                        "6am",
                        "7am",
                        "8am",
                        "9am",
                        "10am",
                        "11am",
                        "12pm",
                        "1pm",
                        "2pm",
                        "3pm",
                        "4pm",
                        "5pm",
                        "6pm",
                        "7pm",
                        "8pm",
                        "9pm",
                        "10pm",
                        "11pm",
                    ],
                    hoverformat="#%{theta}: <br>Popularity: %{percent} </br> %{r}",
                ),
            ),
        )

        daily = self.get_daily_crosstab(df5)
        fig.add_trace(
            go.Bar(
                x=daily.columns[:-1],
                y=daily.loc[specie][:-1],
                marker_color="seagreen",
            ),
            row=3,
            col=2,
        )
        return fig

    def _prepare_daily_detection_data(self, df, resample_sel, specie):
        df4 = df["Com_Name"][df["Com_Name"] == specie].resample("15min").count()
        df4.index = [df4.index.date, df4.index.time]
        day_hour_freq = df4.unstack().fillna(0)

        saved_time_labels = [self.hms_to_str(h) for h in day_hour_freq.columns.tolist()]
        fig_dec_y = [self.hms_to_dec(h) for h in day_hour_freq.columns.tolist()]
        fig_x = [d.strftime("%d-%m-%Y") for d in day_hour_freq.index.tolist()]

        return day_hour_freq, saved_time_labels, fig_dec_y, fig_x

    def generate_daily_detections_plot(
        self, df, resample_sel, start_date, specie, num_days_to_display, selected_pal
    ):
        day_hour_freq, saved_time_labels, fig_dec_y, fig_x = (
            self._prepare_daily_detection_data(df, resample_sel, specie)
        )

        day_hour_freq.columns = fig_dec_y
        fig_z = day_hour_freq.values.transpose()

        heatmap = go.Heatmap(
            x=fig_x,
            y=day_hour_freq.columns,
            z=fig_z,
            showscale=False,
            texttemplate="%{text}",
            autocolorscale=False,
            colorscale=selected_pal,
        )

        sunrise_week_list, sunrise_list, sunrise_text_list = (
            self.get_sunrise_sunset_data(num_days_to_display)
        )
        daysback_range = fig_x
        daysback_range.append(None)
        daysback_range.extend(daysback_range)
        daysback_range = daysback_range[:-1]

        sunrise_sunset = go.Scatter(
            x=daysback_range,
            y=sunrise_list,
            mode="lines",
            hoverinfo="text",
            text=sunrise_text_list,
            line_color="orange",
            line_width=1,
            name=" ",
        )

        fig = go.Figure(data=[heatmap, sunrise_sunset])
        number_of_y_ticks = 12
        y_downscale_factor = int(len(saved_time_labels) / number_of_y_ticks)
        fig.update_layout(
            yaxis=dict(
                tickmode="array",
                tickvals=day_hour_freq.columns[::y_downscale_factor],
                ticktext=saved_time_labels[::y_downscale_factor],
                nticks=6,
            )
        )
        return fig

    def get_species_counts(self, df):
        # This will eventually replace the Specie_Count logic
        return df["Com_Name"].value_counts()

    def get_hourly_crosstab(self, df):
        # This will eventually replace the hourly crosstab logic
        return pd.crosstab(df["Com_Name"], df.index.hour, dropna=True, margins=True)

    def get_daily_crosstab(self, df):
        # This will eventually replace the daily crosstab logic
        return pd.crosstab(df["Com_Name"], df.index.date, dropna=True, margins=True)

    def date_filter(self, df, start_date, end_date):
        # This will eventually replace the date_filter function
        filt = (df.index >= pd.Timestamp(start_date)) & (
            df.index <= pd.Timestamp(end_date + timedelta(days=1))
        )
        df = df[filt]
        return df

    def time_resample(self, df, resample_time):
        # This will eventually replace the time_resample function
        if resample_time == "Raw":
            df_resample = df["Com_Name"]
        else:
            df_resample = (
                df.resample(resample_time)["Com_Name"].aggregate("unique").explode()
            )
        return df_resample

    def get_sunrise_sunset_data(self, num_days_to_display: int):
        latitude = self.config.latitude
        longitude = self.config.longitude

        sun = Sun(latitude, longitude)

        sunrise_list = []
        sunset_list = []
        sunrise_week_list = []
        sunset_week_list = []
        sunrise_text_list = []
        sunset_text_list = []

        now = datetime.datetime.now()

        for past_day in range(num_days_to_display):
            d = timedelta(days=num_days_to_display - past_day - 1)

            current_date = now - d
            sun_rise = sun.get_local_sunrise_time(current_date)
            sun_dusk = sun.get_local_sunset_time(current_date)

            sun_rise_time = float(sun_rise.hour) + float(sun_rise.minute) / 60.0
            sun_dusk_time = float(sun_dusk.hour) + float(sun_dusk.minute) / 60.0

            temp_time = str(sun_rise)[-14:-9] + " Sunrise"
            sunrise_text_list.append(temp_time)
            temp_time = str(sun_dusk)[-14:-9] + " Sunset"
            sunset_text_list.append(temp_time)
            sunrise_list.append(sun_rise_time)
            sunset_list.append(sun_dusk_time)
            sunrise_week_list.append(past_day)
            sunset_week_list.append(past_day)

        sunrise_week_list.append(None)
        sunrise_list.append(None)
        sunrise_text_list.append(None)
        sunrise_list.extend(sunset_list)
        sunrise_week_list.extend(sunset_week_list)
        sunrise_text_list.extend(sunset_text_list)

        return sunrise_week_list, sunrise_list, sunrise_text_list

    @staticmethod
    def hms_to_dec(t):
        h = t.hour
        m = t.minute / 60
        s = t.second / 3600
        result = h + m + s
        return result

    @staticmethod
    def hms_to_str(t):
        h = t.hour
        m = t.minute
        return "%02d:%02d" % (h, m)

    def get_most_recent_detections(self, limit: int = 10):
        self.db_manager.connect()
        query = "SELECT * FROM detections ORDER BY Date DESC, Time DESC LIMIT ?"
        recent_detections = self.db_manager.fetch_all(query, (limit,))
        self.db_manager.disconnect()
        return recent_detections

    def generate_spectrogram(self, audio_file_path: str, output_image_path: str):
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    audio_file_path,
                    "-lavfi",
                    "showspectrumpic=s=1280x720",  # Adjust size as needed
                    "-frames:v",
                    "1",
                    output_image_path,
                ],
                check=True,
            )
            print(f"Spectrogram generated successfully at {output_image_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error generating spectrogram: {e}")
        except FileNotFoundError:
            print("Error: ffmpeg command not found. Please ensure ffmpeg is installed.")
