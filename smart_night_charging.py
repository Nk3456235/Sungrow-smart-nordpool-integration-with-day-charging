import appdaemon.plugins.hass.hassapi as hass
import datetime

class SmartNightCharging(hass.Hass):
    def initialize(self):
        """Initialize the app and set up the routines for regular updates."""
        
        # Define sensor names
        self.sensor_name = "sensor.nordpool_kwh_se3_sek_3_10_025"
        self.output_selected_hours = "sensor.selected_charging_hours"
        self.output_comparison_sensor = "sensor.night_charging_day_prices_comparison"
        self.output_prices_for_selected_hours = "sensor.selected_charging_hours_prices"  # New sensor for prices

        # Trigger the update calculation every day at 23:59
        self.run_daily(self.update_charging_hours, datetime.time(23, 59))

        # Run the calculation once at startup
        self.update_charging_hours()

    def update_charging_hours(self, *args):
        """Update the charging hours based on the cheapest hours and price differences."""
        
        # Fetch tomorrow's prices from the Nordpool sensor
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

            # Update the sensors with the calculated means
            self.set_state(
                "sensor.chosen_3_hours",
                state=mean_3,
                attributes={"cheapest_3_hours": [hour for hour, _ in cheapest_3]}
            )
            self.set_state(
                "sensor.chosen_4_hours",
                state=mean_4,
                attributes={"cheapest_4_hours": [hour for hour, _ in cheapest_4]}
            )
            self.set_state(
                "sensor.chosen_5_hours",
                state=mean_5,
                attributes={"cheapest_5_hours": [hour for hour, _ in cheapest_5]}
            )

            # Calculate the mean of the 7 most expensive day hours
            if len(tomorrow_day_prices) >= 7:
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
                    self.log("Day prices are not sufficiently more expensive than night prices. Charging will not be scheduled.")
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

                # Validate the selected hours before proceeding
                if not selected_hours or any(hour < 0 or hour > 23 for hour in selected_hours):
                    self.log("Invalid selected hours. Stopping all charging.")
                    self.stop_charging({})
                    return

                # Sort the selected hours in order
                selected_hours.sort()

                # Store the validated selected hours for later checks
                self.selected_hours = selected_hours

                # Create a time range string for the selected hours
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

                # Store the number of selected hours and call set_max_charging_power
                selected_hours_count = len(selected_hours)
                self.set_max_charging_power(selected_hours_count)

                # Schedule charging
                self.schedule_sequential_charging(selected_hours)

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

    def set_max_charging_power(self, selected_hours_count):
        """Set max charging power based on selected hours count."""
        if selected_hours_count == 3:
            max_power = 6200
        elif selected_hours_count == 4:
            max_power = 4700
        elif selected_hours_count == 5:
            max_power = 3800
        else:
            max_power = 4000  # Fallback if no valid selection

        # Set max charging power
        self.call_service(
            "input_number/set_value",
            entity_id="input_number.set_sg_battery_max_charge_power",
            value=max_power
        )
        self.log(f"Setting max charging power to {max_power}W.")
        self.log_to_logbook(f"Max charging power set to {max_power}W.")

    def schedule_sequential_charging(self, selected_hours):
        """Schedule charging for the selected hours."""
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)

        # Identify sequential ranges and non-sequential hours
        sequential_ranges = []
        non_sequential_hours = []

        # Create the ranges for sequential hours
        temp_range = [selected_hours[0]]
        for i in range(1, len(selected_hours)):
            if selected_hours[i] == selected_hours[i-1] + 1:
                temp_range.append(selected_hours[i])
            else:
                if len(temp_range) > 1:
                    sequential_ranges.append(temp_range)
                else:
                    non_sequential_hours.append(temp_range[0])
                temp_range = [selected_hours[i]]
        
        # Append the last range or non-sequential hour
        if len(temp_range) > 1:
            sequential_ranges.append(temp_range)
        else:
            non_sequential_hours.append(temp_range[0])

        # To avoid scheduling the same hour twice, track scheduled hours
        scheduled_hours = set()

        # Log and schedule charging for sequential ranges
        for range_ in sequential_ranges:
            start_hour = range_[0]
            end_hour = range_[-1]

            # Log the range
            self.log(f"Charging scheduled between {start_hour:02d}:00-{end_hour + 1:02d}:00")

            # Schedule charging start at the first hour of the range
            start_time = tomorrow.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            if start_hour not in scheduled_hours:
                self.run_at(self.start_charging, start_time)  # Schedule start charging
                self.log(f"Charging start scheduled at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                scheduled_hours.add(start_hour)  # Add start hour to the set

            # Schedule charging stop at the last hour of the range
            stop_time = tomorrow.replace(hour=end_hour + 1, minute=0, second=0, microsecond=0)
            if end_hour + 1 not in scheduled_hours:
                self.run_at(self.stop_charging, stop_time)  # Schedule stop charging
                self.log(f"Charging stop scheduled at {stop_time.strftime('%Y-%m-%d %H:%M:%S')}")
                scheduled_hours.add(end_hour + 1)  # Add stop hour to the set

        # For non-sequential hours, schedule separately
        for hour in non_sequential_hours:
            # Only schedule if the hour has not been scheduled already
            if hour not in scheduled_hours:
                target_time = tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
                self.run_at(self.start_charging, target_time)  # Schedule start charging
                self.log(f"Charging start scheduled at {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
                scheduled_hours.add(hour)  # Add the hour to the set

                stop_time = tomorrow.replace(hour=hour + 1, minute=0, second=0, microsecond=0)
                self.run_at(self.stop_charging, stop_time)  # Schedule stop charging
                self.log(f"Charging stop scheduled at {stop_time.strftime('%Y-%m-%d %H:%M:%S')}")
                scheduled_hours.add(hour + 1)  # Add the stop hour to the set



    def start_charging(self, kwargs):
        """Start charging the battery."""
        current_hour = datetime.datetime.now().hour
        if current_hour in self.selected_hours:
            self.log_to_logbook("Starting battery charging.")
            self.run_in(self.set_forced_mode, 2)
            self.run_in(self.set_forced_charge, 4)
        else:
            self.log_to_logbook("Charging attempt outside selected hours prevented.")

    def stop_charging(self, kwargs):
        """Stop charging the battery."""
        self.log_to_logbook("Stopping battery charging.")
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Stop (default)"
        )

    def set_forced_mode(self, kwargs):
        """Set EMS mode to Forced mode and start charging."""
        self.log_to_logbook("Setting EMS mode to Forced mode.")
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_ems_mode",
            option="Forced mode"
        )

    def set_forced_charge(self, kwargs):
        """Force battery to charge."""
        self.log_to_logbook("Forcing battery to charge.")
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Forced charge"
        )

    def log_to_logbook(self, message):
        """Logs a message to the Home Assistant Logbook."""
        self.call_service(
            "logbook/log",
            name="Smart night charging",
            message=message
        )