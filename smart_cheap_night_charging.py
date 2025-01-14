import appdaemon.plugins.hass.hassapi as hass
import datetime

class SmartCheapNightCharging(hass.Hass):
    def initialize(self):
        """Initialize the app and set up the routines for regular updates."""
        
        # Define sensor names
        self.sensor_name = "sensor.nordpool_kwh_se3_sek_3_10_025"
        self.output_selected_hours = "sensor.selected_charging_hours0"
        self.output_prices_for_selected_hours = "sensor.selected_charging_hours_prices"  # New sensor for prices

        # Trigger the update calculation every day at 23:58
        self.run_daily(self.update_charging_hours, datetime.time(23, 58))

        # Run the charging logic immediately at startup
        self.update_charging_hours()

    def update_charging_hours(self, *args):
        """Update the charging hours based on the cheapest hours and price differences."""
        
        # Fetch tomorrow's prices from the Nordpool sensor
        tomorrow_prices = self.get_state(self.sensor_name, attribute="tomorrow") or []

        # Ensure there are enough data points (7 night hours)
        if len(tomorrow_prices) >= 7:
            # Extract the night prices (first 7 hours)
            tomorrow_night_prices = tomorrow_prices[:7]

            # Create list of (hour, price) tuples for the night hours
            sorted_hours = sorted([(i, price) for i, price in enumerate(tomorrow_night_prices) if price is not None], key=lambda x: x[1])

            # Cheapest 5 hours
            cheapest_5 = sorted_hours[:5]

            # Calculate mean for the 5 cheapest hours
            mean_5 = sum(price for _, price in cheapest_5) / len(cheapest_5)

            # Log the results
            self.log(f"Tomorrow's calculated mean of the 5 cheapest night hours: {mean_5:.2f}")

            # Log the full state of 'sensor.battery_level_nominal' to see what data we are working with
            battery_state = self.get_state("sensor.battery_level_nominal")
            self.log(f"Full state of 'sensor.battery_level_nominal': {battery_state}")

            # Directly use the state value
            try:
                battery_level = float(battery_state)
                self.log(f"Battery level retrieved: {battery_level}%")  # Log the battery level value
            except ValueError:
                self.log(f"Invalid battery level '{battery_state}', using default of 100.")
                battery_level = 100

            # Check if battery level is under 90%
            if battery_level < 90:
                self.log("Battery level is below 90%, proceeding with charging.")
                # Only initiate charging if the mean price for the 5 cheapest hours is below 10 SEK
                if mean_5 < 10:
                    # Selected hours are the 5 cheapest hours
                    selected_hours = [hour for hour, _ in cheapest_5]
                    # Continue with scheduling charging...

                    # Sort the selected hours in order
                    selected_hours.sort()

                    # Store the validated selected hours for later checks
                    self.selected_hours = selected_hours

                    # Create the time range string for the selected hours
                    time_range_str = ", ".join([f"{hour:02d}:00" for hour in selected_hours])

                    # Log the selected time range for charging and its mean price
                    self.log(f"Tomorrow's selected time range for charging: {time_range_str}")
                    self.log(f"Tomorrow's mean price for selected hours: {mean_5:.2f}")

                    # Update the selected hours sensor with the formatted time range and mean price
                    self.set_state(
                        self.output_selected_hours,
                        state=f"{time_range_str} | Mean: {mean_5:.2f}",
                        attributes={
                            "selected_hours": selected_hours,
                            "mean_price_for_selected_hours": mean_5
                        }
                    )

                    # Update the new sensor for the mean price of the selected hours
                    self.set_state(
                        self.output_prices_for_selected_hours,
                        state=f"{mean_5:.2f}",
                        attributes={"mean_price_for_selected_hours": mean_5}
                    )

                    # Set max charging power for the selected hours (3800W for 5 hours)
                    self.set_max_charging_power(5)

                    # Schedule charging for the selected period
                    self.schedule_sequential_charging(selected_hours)
                else:
                    self.log("The mean price for the 5 cheapest hours is too high, not scheduling charging.")
                    self.set_state(self.output_selected_hours, state="Price too high")
            else:
                self.log(f"Battery level is above 90%: {battery_level}%, not scheduling charging.")
                self.set_state(self.output_selected_hours, state="Battery above 90%")

        else:
            # If not enough data is available, set the sensor to unknown
            self.set_state(self.output_selected_hours, state="unknown")
            self.log("Not enough data available for tomorrow's price calculation.")

    def set_max_charging_power(self, selected_hours_count):
        """Set max charging power based on selected hours count (always 5 hours here)."""
        if selected_hours_count == 5:
            max_power = 3800  # Power for 5 hours (updated to 3800W)
        else:
            max_power = 4000  # Fallback if no valid selection

        # Set max charging power
        self.call_service(
            "input_number/set_value",
            entity_id="input_number.set_sg_battery_max_charge_power",
            value=max_power
        )
        self.log(f"Setting max charging power to {max_power}W.")

    def schedule_sequential_charging(self, selected_hours):
        """Schedule charging for the selected hours."""
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)

        # Log when the function is called, including the selected hours
        self.log(f"Scheduling sequential charging for hours: {selected_hours}")

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

        # Log the ranges
        for range_ in sequential_ranges:
            start_hour = range_[0]
            end_hour = range_[-1]
            self.log(f"Scheduling charging between {start_hour:02d}:00-{end_hour+1:02d}:00")

            # Schedule charging start at the first hour of the range
            start_time = tomorrow.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            self.run_at(self.start_charging, start_time)  # Schedule start charging
            self.log(f"Scheduling charging start at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Schedule charging stop at the last hour of the range
            stop_time = tomorrow.replace(hour=end_hour + 1, minute=0, second=0, microsecond=0)
            self.run_at(self.stop_charging, stop_time)  # Schedule stop charging
            self.log(f"Scheduling charging stop at {stop_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # For non-sequential hours, schedule separately
        for hour in non_sequential_hours:
            target_time = tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
            self.run_at(self.start_charging, target_time)  # Schedule start charging
            self.log(f"Scheduling charging start at {target_time.strftime('%Y-%m-%d %H:%M:%S')}")

            stop_time = tomorrow.replace(hour=hour + 1, minute=0, second=0, microsecond=0)
            self.run_at(self.stop_charging, stop_time)  # Schedule stop charging
            self.log(f"Scheduling charging stop at {stop_time.strftime('%Y-%m-%d %H:%M:%S')}")

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
            name="Smart cheap night charging",
            message=message
        )
