import appdaemon.plugins.hass.hassapi as hass
import datetime

    # This app creates additional sensors needed for display and other apps working properly.

class SmartNightChargingSensors(hass.Hass):
    def initialize(self):
        """Initialize the app and set up the routines for regular updates."""
        
        # Define sensor names
        self.sensor_name = "sensor.nordpool_kwh_se3_sek_3_10_025"
        self.output_selected_hours = "sensor.mock_selected_charging_hours"
        self.output_comparison_sensor = "sensor.mock_night_charging_day_prices_comparison"
        self.output_prices_for_selected_hours = "sensor.mock_selected_charging_hours_prices"  # New sensor for prices
        
        # Trigger the update calculation every day at 06:01 and 14:00
        self.run_daily(self.update_charging_hours, datetime.time(14, 0))
        self.run_daily(self.update_charging_hours, datetime.time(6, 1))

        # Run the calculation once at startup
        self.update_charging_hours()

    def update_charging_hours(self, *args):
        """Update the charging hours based on the cheapest hours and price differences."""
        
        # Fetch tomorrow's prices from the Nordpool sensor (assumed to be "tomorrow")
        tomorrow_prices = self.get_state(self.sensor_name, attribute="tomorrow") or []

        # Ensure there are enough data points (7 night hours)
        if len(tomorrow_prices) >= 7:
            # Extract the night prices (first 7 hours) and day prices (next hours)
            tomorrow_night_prices = tomorrow_prices[:7]
            tomorrow_day_prices = tomorrow_prices[7:]

            # Create list of (hour, price) tuples for the night hours
            sorted_hours = sorted([(i, price) for i, price in enumerate(tomorrow_night_prices) if price is not None], key=lambda x: x[1])

            # Cheapest 3, 4, and 5 hours
            cheapest_3 = sorted_hours[:3]
            cheapest_4 = sorted_hours[:4]
            cheapest_5 = sorted_hours[:5]

            # Calculate means for each set of hours
            mean_3 = sum(price for _, price in cheapest_3) / len(cheapest_3)
            mean_4 = sum(price for _, price in cheapest_4) / len(cheapest_4)
            mean_5 = sum(price for _, price in cheapest_5) / len(cheapest_5)

            # Update the mock sensors with the calculated means
            self.set_state(
                "sensor.mock_chosen_3_hours",
                state=mean_3,
                attributes={"cheapest_3_hours": [hour for hour, _ in cheapest_3]}
            )
            self.set_state(
                "sensor.mock_chosen_4_hours",
                state=mean_4,
                attributes={"cheapest_4_hours": [hour for hour, _ in cheapest_4]}
            )
            self.set_state(
                "sensor.mock_chosen_5_hours",
                state=mean_5,
                attributes={"cheapest_5_hours": [hour for hour, _ in cheapest_5]}
            )

            # Calculate the mean of the 7 most expensive day hours
            if len(tomorrow_prices) >= 7:
                tomorrow_day_prices = tomorrow_prices[7:]
                tomorrow_day_sorted = sorted(tomorrow_day_prices, reverse=True)
                expensive_7_day = tomorrow_day_sorted[:7]
                mean_7_expensive_tomorrow = sum(expensive_7_day) / 7
                comparison_tomorrow = mean_7_expensive_tomorrow - mean_3

                # Update the comparison sensor with the calculated price difference
                self.set_state(
                    self.output_comparison_sensor,
                    state=comparison_tomorrow
                )

                # Check if day prices are at least 50 öre/kWh more expensive than night prices
                if comparison_tomorrow < 40:
                    self.log("Tomorrow's day prices are not sufficiently more expensive than night prices. Charging will not be scheduled.")
                    # Update the sensor to indicate the price difference is too low
                    self.set_state(
                        self.output_selected_hours,
                        state="Price difference too low",
                        attributes={
                            "price_difference": comparison_tomorrow,
                            "mean_7_expensive_tomorrow": mean_7_expensive_tomorrow,
                            "mean_3_cheapest_night": mean_3,
                        }
                    )
                    self.stop_charging({})
                    return

                # Log the results
                self.log(f"Tomorrow's calculated mean of the 3 cheapest night hours: {mean_3:.2f}")
                self.log(f"Tomorrow's calculated mean of the 4 cheapest night hours: {mean_4:.2f}")
                self.log(f"Tomorrow's calculated mean of the 5 cheapest night hours: {mean_5:.2f}")
                self.log(f"Tomorrow's price comparison (day vs night): {comparison_tomorrow:.2f}")

                # Now determine the hours to use for charging based on price differences
                selected_hours = []
                if mean_5 - mean_3 <= 10:  # If the difference between 5 and 3 is small, choose 5 hours
                    selected_hours = [hour for hour, _ in cheapest_5]
                    selected_mean_price = mean_5  # Use the mean price for 5 hours
                elif mean_4 - mean_3 <= 5:  # If the difference between 4 and 3 is small, choose 4 hours
                    selected_hours = [hour for hour, _ in cheapest_4]
                    selected_mean_price = mean_4  # Use the mean price for 4 hours
                else:  # Otherwise, choose the 3 cheapest hours
                    selected_hours = [hour for hour, _ in cheapest_3]
                    selected_mean_price = mean_3  # Use the mean price for 3 hours

                # Sort the selected hours in order
                selected_hours.sort()

                # Create the time range string for the selected hours
                time_range_str = self.format_selected_hours(selected_hours)

                # Log the selected time range for charging and its mean price
                self.log(f"Tomorrow's selected time range for charging: {time_range_str}")
                self.log(f"Tomorrow's mean price for selected hours: {selected_mean_price:.2f}")

                # Update the selected hours sensor with the formatted time range, hours, and mean price
                self.set_state(
                    self.output_selected_hours,
                    state=f"{time_range_str} | Mean: {selected_mean_price:.2f}",
                    attributes={
                        "selected_hours": selected_hours,
                        "mean_price_for_selected_hours": selected_mean_price
                    }
                )

                # Update the new sensor for the mean price of the selected hours
                self.set_state(
                    self.output_prices_for_selected_hours,
                    state=f"{selected_mean_price:.2f}",
                    attributes={"mean_price_for_selected_hours": selected_mean_price}
                )

        else:
            # If not enough data is available, set the sensor to unknown
            self.set_state(self.output_selected_hours, state="unknown")
            self.set_state(self.output_comparison_sensor, state="unknown")
            self.log("Not enough data available for tomorrow's price calculation.")

    def format_selected_hours(self, selected_hours):
        """Formats selected charging hours into sequential and non-sequential ranges."""
        if not selected_hours:
            return "No valid charging hours"
        
        # Convert selected_hours into sequential and non-sequential ranges
        ranges = []
        current_range = [selected_hours[0]]

        for i in range(1, len(selected_hours)):
            if selected_hours[i] == selected_hours[i - 1] + 1:
                current_range.append(selected_hours[i])
            else:
                ranges.append(current_range)
                current_range = [selected_hours[i]]
        
        # Add the last range
        ranges.append(current_range)

        # Format the ranges
        formatted_ranges = []
        for r in ranges:
            if len(r) == 1:
                formatted_ranges.append(f"{r[0]:02d}:00")
            else:
                formatted_ranges.append(f"{r[0]:02d}:00-{r[-1] + 1:02d}:00")

        return " , ".join(formatted_ranges)
