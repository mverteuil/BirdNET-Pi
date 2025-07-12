import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from suntime import Sun

from managers.reporting_manager import ReportingManager
from services.database_manager import DatabaseManager
from utils.config_file_parser import ConfigFileParser
from utils.file_path_resolver import FilePathResolver


class ReportingDashboard:
    def __init__(self):
        self.config = ConfigFileParser(
            os.path.join(
                os.path.dirname(__file__), "..", "etc", "birdnet_pi_config.yaml"
            )
        ).parse()
        self.file_path_resolver = FilePathResolver(self.config.base_data_path)
        self.db_manager = DatabaseManager(self.file_path_resolver.get_birds_db_path())
        self.reporting_manager = ReportingManager(self.db_manager)

    def get_data(self):
        # This will eventually replace the direct pandas.read_sql
        # For now, we'll simulate it using the ReportingManager
        df = self.reporting_manager.get_all_detections()
        df["DateTime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
        df = df.set_index("DateTime")
        return df

    def get_species_counts(self, df):
        # This will replace the Specie_Count logic
        return df["Com_Name"].value_counts()

    def get_hourly_crosstab(self, df):
        # This will replace the hourly crosstab logic
        return pd.crosstab(df["Com_Name"], df.index.hour, dropna=True, margins=True)

    def get_daily_crosstab(self, df):
        # This will replace the daily crosstab logic
        return pd.crosstab(df["Com_Name"], df.index.date, dropna=True, margins=True)

    def date_filter(self, df, start_date, end_date):
        # This will replace the date_filter function
        filt = (df.index >= pd.Timestamp(start_date)) & (
            df.index <= pd.Timestamp(end_date + timedelta(days=1))
        )
        df = df[filt]
        return df

    def time_resample(self, df, resample_time):
        # This will replace the time_resample function
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

        now = datetime.now()

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

    def generate_multi_day_species_and_hourly_plot(
        self, df, resample_sel, start_date, end_date, top_N, specie
    ):
        df5 = self.time_resample(df, resample_sel)
        hourly = self.get_hourly_crosstab(df5)
        top_N_species = self.get_species_counts(df5)[:top_N]

        df_counts = int(hourly[hourly.index == specie]["All"])
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

    def generate_daily_detections_plot(
        self, df, resample_sel, start_date, specie, num_days_to_display, selected_pal
    ):
        df4 = df["Com_Name"][df["Com_Name"] == specie].resample("15min").count()
        df4.index = [df4.index.date, df4.index.time]
        day_hour_freq = df4.unstack().fillna(0)

        saved_time_labels = [self.hms_to_str(h) for h in day_hour_freq.columns.tolist()]
        fig_dec_y = [self.hms_to_dec(h) for h in day_hour_freq.columns.tolist()]
        fig_x = [d.strftime("%d-%m-%Y") for d in day_hour_freq.index.tolist()]

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


if __name__ == "__main__":
    dashboard = ReportingDashboard()
    df = dashboard.get_data()
    print(df.head())
    print(dashboard.get_species_counts(df).head())
