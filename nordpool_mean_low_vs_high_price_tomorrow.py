import appdaemon.plugins.hass.hassapi as hass
import datetime

class NordpoolMeanLowVsHighPriceTomorrow(hass.Hass):
    def initialize(self):
        self.sensor_name = "sensor.nordpool_kwh_se3_sek_3_10_025"
        self.output_sensor = "sensor.nordpool_mean_low_vs_high_price_tomorrow"

        # Listen to state changes of the Nordpool sensor
        self.listen_state(self.calculate_mean_difference, self.sensor_name)

        # Run the calculation once at startup
        self.calculate_mean_difference()

    def calculate_mean_difference(self, *args):
        """Calculates the mean price difference between the cheapest 3 hours (00:00-06:00)
        and the most expensive 7 hours (entire day) for tomorrow's prices."""
        
        # Fetch the "tomorrow" prices from the Nordpool sensor
        tomorrow_prices = self.get_state(self.sensor_name, attribute="tomorrow") or []

        # Ensure there are enough data points for the calculation
        if len(tomorrow_prices) >= 6:  # At least 6 hours of data required
            # Extract the first 6 hours (00:00-06:00) and the full day's prices
            tomorrow_prices_00_06 = tomorrow_prices[:6]
            
            # Find the cheapest 3 hours and the most expensive 7 hours
            tomorrow_bottom_3 = sorted(tomorrow_prices_00_06)[:3]
            tomorrow_top_7 = sorted(tomorrow_prices, reverse=True)[:7]

            # Calculate the mean prices
            mean_bottom_3 = sum(tomorrow_bottom_3) / len(tomorrow_bottom_3)
            mean_top_7 = sum(tomorrow_top_7) / len(tomorrow_top_7)

            # Calculate the price difference
            mean_difference = mean_top_7 - mean_bottom_3

            # Format the results to 2 decimal places
            formatted_mean_difference = f"{mean_difference:.2f}"
            formatted_mean_bottom_3 = f"{mean_bottom_3:.2f}"
            formatted_mean_top_7 = f"{mean_top_7:.2f}"

            # Update the custom sensor with the calculated result
            self.set_state(
                self.output_sensor,
                state=f"{formatted_mean_difference} Öre/kWh",
                attributes={
                    "mean_bottom_3": formatted_mean_bottom_3,
                    "mean_top_7": formatted_mean_top_7,
                    "tomorrow_bottom_3": [f"{price:.2f}" for price in tomorrow_bottom_3],
                    "tomorrow_top_7": [f"{price:.2f}" for price in tomorrow_top_7],
                }
            )
            self.log(f"Updated sensor with mean difference: {formatted_mean_difference}")
        else:
            # If not enough data is available, set the state to unknown
            self.set_state(
                self.output_sensor,
                state="unknown",
                attributes={
                    "error": "Not enough data for calculation",
                    "tomorrow_prices": tomorrow_prices
                }
            )
            self.log("Not enough data available for tomorrow's price calculation.")
