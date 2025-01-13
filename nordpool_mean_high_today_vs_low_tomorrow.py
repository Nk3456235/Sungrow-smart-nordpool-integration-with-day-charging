import appdaemon.plugins.hass.hassapi as hass
import datetime

class NordpoolMeanHighTodayVsLowTomorrow(hass.Hass):
    def initialize(self):
        self.sensor_name = "sensor.nordpool_kwh_se3_sek_3_10_025"
        self.output_sensor = "sensor.nordpool_mean_high_today_vs_low_tomorrow"

        # Run the calculation every day at 13:59
        self.run_daily(self.calculate_mean_difference, datetime.time(13, 59))

        # Reset the sensor at midnight
        self.run_daily(self.reset_sensor, datetime.time(00, 00))

        # Optionally, you can call the calculation at startup as well
        self.calculate_mean_difference()

    def calculate_mean_difference(self, *args):
        today_prices = self.get_state(self.sensor_name, attribute="today") or []
        tomorrow_prices = self.get_state(self.sensor_name, attribute="tomorrow") or []

        # Ensure there are enough data points for both today and tomorrow
        if len(today_prices) >= 24 and len(tomorrow_prices) >= 6:  # Ensure at least 24 prices for today and 6 for tomorrow
            
            # Filter today's prices for hours between 14:00 and 23:00 (indices 14-23)
            today_prices_filtered = today_prices[14:24]

            # Filter tomorrow's prices for hours between 00:00 and 06:00 (indices 0-5)
            tomorrow_prices_filtered = tomorrow_prices[:6]

            # Top 5 most expensive hours for today
            today_top_5 = sorted(today_prices_filtered, reverse=True)[:5]

            # Bottom 5 cheapest hours for tomorrow (00:00 - 06:00)
            tomorrow_bottom_5 = sorted(tomorrow_prices_filtered)[:5]

            # Calculate the means
            mean_today_top_5 = sum(today_top_5) / len(today_top_5)
            mean_tomorrow_bottom_5 = sum(tomorrow_bottom_5) / len(tomorrow_bottom_5)

            # Set the output sensor with the result
            self.set_state(self.output_sensor, state=mean_today_top_5 - mean_tomorrow_bottom_5, attributes={
                "mean_today_top_5": mean_today_top_5,
                "mean_tomorrow_bottom_5": mean_tomorrow_bottom_5,
                "today_top_5": today_top_5,
                "tomorrow_bottom_5": tomorrow_bottom_5
            })
        else:
            self.set_state(self.output_sensor, state="unknown", attributes={
                "error": "Not enough data for calculation",
                "today_prices": today_prices,
                "tomorrow_prices": tomorrow_prices
            })

    def reset_sensor(self, *args):
        # Reset the output sensor at midnight to clear previous data
        self.set_state(self.output_sensor, state="unknown", attributes={
            "error": "Sensor reset at midnight",
            "mean_today_top_5": None,
            "mean_tomorrow_bottom_5": None,
            "today_top_5": [],
            "tomorrow_bottom_5": []
        })
