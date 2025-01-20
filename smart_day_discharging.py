import appdaemon.plugins.hass.hassapi as hass
import datetime

    # This app triggers non sequential discharging during day hours if price condition is met.

class SmartDayDischarging(hass.Hass):
    def initialize(self):
        """Initialize the app and set up the routines for regular updates."""
        # Define sensor names
        self.sensor_name = "sensor.nordpool_kwh_se3_sek_3_10_025"  # Nordpool sensor for prices
        self.mean_price_sensor = "sensor.selected_charging_hours_prices"  # Mean price sensor
        self.output_selected_hours = "sensor.selected_discharging_hours"
        self.output_prices_for_selected_hours = "sensor.selected_discharging_hours_prices"

        # Trigger the update calculation every day at 02:00
        self.run_daily(self.update_discharging_hours, datetime.time(2, 0))
        # Run the calculation once at startup
        self.update_discharging_hours()

    def update_discharging_hours(self, *args):
        """Update the discharging hours based on the 7 most expensive hours."""
        # Clear previous state and attributes of selected_discharging_hours
        self.set_state(self.output_selected_hours, state="unknown", attributes={})
        self.set_state(self.output_prices_for_selected_hours, state="unknown", attributes={})

        # Fetch today's prices from the Nordpool sensor (hourly prices for today)
        today_prices = self.get_state(self.sensor_name, attribute="today") or []
        if not today_prices or len(today_prices) != 24:
            self.log("Error: Not enough data for price calculation")
            return

        # Extract relevant price data for different time ranges
        morning_prices = today_prices[6:10]  # hours 6-9
        midday_prices = today_prices[10:17]  # hours 10-16
        evening_prices = today_prices[17:23]  # hours 17-22

        self.log(f"Morning prices (6:00-9:00): {morning_prices}")
        self.log(f"Midday prices (10:00-16:00): {midday_prices}")
        self.log(f"Evening prices (17:00-22:00): {evening_prices}")

        # Step 1: Find the cheapest hour between 10:00 and 16:00
        cheapest_hour = min(enumerate(midday_prices, 10), key=lambda x: x[1], default=(None, None))
        if cheapest_hour[0] is None:
            self.log("Error: No valid prices found between 10:00 and 16:00")
            return
        cheapest_hour_time, cheapest_price = cheapest_hour
        self.log(f"Cheapest hour between 10:00 and 16:00: {cheapest_hour_time}: {cheapest_price:.2f} öre")

        # Step 2: Check the 3rd most expensive hour before the selected cheapest hour (06:00 to selected hour - 1)
        morning_prices_dynamic = today_prices[6:cheapest_hour_time]  # from 6:00 to selected hour - 1
        self.log(f"Dynamic morning prices (6:00-{cheapest_hour_time-1}:00): {morning_prices_dynamic}")
        
        if not morning_prices_dynamic:
            self.log("Error: No morning prices available for comparison")
            return
        
        # Sort the morning prices in descending order and get the 3rd most expensive hour
        sorted_morning_prices = sorted(enumerate(morning_prices_dynamic, 6), key=lambda x: x[1], reverse=True)

        if len(sorted_morning_prices) < 3:
            self.log("Error: Not enough morning prices to find the 3rd most expensive hour")
            return

        # Select the 3rd most expensive hour (index 2 after sorting)
        third_most_expensive_morning_hour, third_most_expensive_morning_price = sorted_morning_prices[2]
        self.log(f"3rd most expensive hour before the cheapest midday hour: {third_most_expensive_morning_hour}: {third_most_expensive_morning_price:.2f} öre")

        # Step 3: Check the 3rd most expensive hour after the selected cheapest hour (selected hour + 1 to 23:00)
        evening_prices_dynamic = today_prices[cheapest_hour_time+1:23]  # from selected hour + 1 to 23:00
        self.log(f"Dynamic evening prices ({cheapest_hour_time+1}:00-23:00): {evening_prices_dynamic}")
        
        if not evening_prices_dynamic:
            self.log("Error: No evening prices available for comparison")
            return
        
        # Sort the evening prices in descending order and get the 3rd most expensive hour
        sorted_evening_prices = sorted(enumerate(evening_prices_dynamic, cheapest_hour_time+1), key=lambda x: x[1], reverse=True)

        if len(sorted_evening_prices) < 3:
            self.log("Error: Not enough evening prices to find the 3rd most expensive hour")
            return

        # Select the 3rd most expensive hour (index 2 after sorting)
        third_most_expensive_evening_hour, third_most_expensive_evening_price = sorted_evening_prices[2]
        self.log(f"3rd most expensive hour after the cheapest midday hour: {third_most_expensive_evening_hour}: {third_most_expensive_evening_price:.2f} öre")

        # Step 4: Check the price differences and set the conditions for continuing
        # Morning price condition: 3rd most expensive before should be less than 40 öre more expensive than the cheapest midday hour
        price_diff_morning = third_most_expensive_morning_price - cheapest_price
        self.log(f"Price difference (morning 3rd most expensive vs midday cheapest): {price_diff_morning:.2f} öre")
        
        is_morning_valid = price_diff_morning <= 40  # 40 öre condition CHANGEME
        self.log(f"Morning price condition met: {is_morning_valid}")

        # Evening price condition: 3rd most expensive after should be less than 40 öre more expensive than the cheapest midday hour
        price_diff_evening = third_most_expensive_evening_price - cheapest_price
        self.log(f"Price difference (evening 3rd most expensive vs midday cheapest): {price_diff_evening:.2f} öre")
        
        is_evening_valid = price_diff_evening <= 40  # 40 öre condition CHANGEME
        self.log(f"Evening price condition met: {is_evening_valid}")

        # Step 5: If at least one condition is true (either morning or evening), continue. Otherwise, stop.
        if is_morning_valid or is_evening_valid:
            self.log("Conditions met. Continuing with discharging scheduling.")
        else:
            self.log("App will not run. Day charging scheduled.")
            self.set_state(self.output_selected_hours, state=f"Dynamic discharging")
            return

        # Proceed with selecting discharging hours
        # Only consider the hours between 6:00 and 22:00 (indices 6 to 22)
        filtered_prices = today_prices[6:23]  # hours 6 to 22 (inclusive)
        self.log(f"Filtered prices (6:00-22:00): {filtered_prices}")

        # Calculate the mean price of the 7 most expensive hours
        mean_price_value = float(self.get_state(self.mean_price_sensor, state=None) or 0)

        # If the mean_price_value is 0, use the value from sensor.chosen_3_hours instead
        if mean_price_value == 0:
            mean_price_value = float(self.get_state('sensor.mock_chosen_3_hours', state=None) or 0)
            self.log(f"Missing value of last charge, using value from sensor.mock_chosen_3_hours: {mean_price_value:.2f} öre")
        else:
            self.log(f"Mean price of last charge: {mean_price_value:.2f} öre")

        # Select hours where the price is at least 40 öre more expensive than the mean price
        selected_hours = []
        for i, price in enumerate(filtered_prices):
            if price is not None and price >= mean_price_value + 40:
                selected_hours.append((i + 6, price))  # Store the hour (adjusting for index) and the price

        # Sort the selected hours by price (descending) to pick the most expensive ones
        selected_hours.sort(key=lambda x: x[1], reverse=True)

        # Limit the number of selected hours to a maximum of 7
        selected_hours = selected_hours[:7]
        self.log(f"Selected hours (most expensive, at least 40 öre more expensive than mean price of last charge): {selected_hours}")

        # If we have selected any hours
        if selected_hours:
            # Extract the hours for scheduling
            selected_hour_indices = [hour for hour, _ in selected_hours]
            selected_hour_indices.sort()  # Ensure hours are sorted in order

            # Format the time range string for selected hours
            time_range_str = self.split_into_ranges(selected_hour_indices)
            self.log(f"Today's selected time range for discharging: {time_range_str}")
            
            # Calculate the mean price of the selected hours
            mean_selected_price = sum(price for _, price in selected_hours) / len(selected_hours)

            # Update the state with the selected hours and the mean price for the selected hours
            self.set_state(self.output_selected_hours, state=f"{time_range_str} | Mean: {mean_selected_price:.2f}",
                        attributes={"selected_hours": selected_hour_indices, "mean_price_for_selected_hours": mean_selected_price})

            # Update the new sensor for the mean price of the selected hours
            self.set_state(self.output_prices_for_selected_hours, state=f"{mean_selected_price:.2f}",
                        attributes={"mean_price_for_selected_hours": mean_selected_price})

            # Schedule discharging for the selected hours
            self.schedule_discharging(selected_hour_indices)
        else:
            self.log("No hours found with a price at least 40 öre more expensive than the mean price.")
            self.log_to_logbook("No hours found with a price at least 40 öre more expensive than the mean price.")
            self.set_state(self.output_selected_hours, state="No suitable hours found")
            self.set_state(self.output_prices_for_selected_hours, state="No suitable hours found")


    def split_into_ranges(self, selected_hours):
        """Split selected hours into continuous ranges and output as start-end format."""
        ranges = self.group_sequential_hours(selected_hours)
        
        # Format each group of hours into a readable string
        formatted_ranges = []
        for r in ranges:
            start_hour = r[0]
            end_hour = r[-1]
            formatted_ranges.append(f"{start_hour:02}:00-{end_hour + 1:02}:00")
        
        return ", ".join(formatted_ranges)

    def group_sequential_hours(self, selected_hours):
        """Groups consecutive hours into continuous blocks."""
        ranges = []
        current_range = [selected_hours[0]]  # Start with the first hour

        for i in range(1, len(selected_hours)):
            # If current hour is consecutive to the previous one, add it to the current range
            if selected_hours[i] == selected_hours[i - 1] + 1:
                current_range.append(selected_hours[i])
            else:
                # If not consecutive, push the current range and start a new one
                ranges.append(current_range)
                current_range = [selected_hours[i]]

        # Don't forget to add the last range
        ranges.append(current_range)
        
        return ranges

    def schedule_discharging(self, selected_hours):
        """Schedule discharging for the selected hours, preventing stop if following hour is part of the sequence."""
        now = self.datetime()  # Get the current datetime object for logging
        today_date = now.date()  # Get today's date

        # Group selected hours into continuous ranges (sequences of hours)
        ranges = self.group_sequential_hours(selected_hours)

        # Loop through the ranges and schedule start and stop times for discharging
        for r in ranges:
            start_hour = r[0]  # First hour of the range
            end_hour = r[-1]  # Last hour of the range
            
            # Schedule the start time (at the start of the range)
            start_time = datetime.datetime.combine(today_date, datetime.time(start_hour, 0))
            self.log(f"Scheduling start discharging at {start_time}")
            self.run_at(self.start_discharging, start_time)
            
            # Schedule the stop time (at the last hour + 1, since discharging needs to stop after the last hour)
            stop_time = datetime.datetime.combine(today_date, datetime.time((end_hour + 1) % 24, 0))
            self.log(f"Scheduling stop discharging at {stop_time}")
            self.run_at(self.stop_discharging, stop_time)

        # Log the ranges to the logbook
        self.log_to_logbook(f"Discharging scheduled for the following time ranges: {ranges}")

    def start_discharging(self, kwargs):
        """Start discharging the battery only if current time is within selected hours."""
        now = self.datetime()  # Get the current datetime object for validation
        
        # Fetch today's dynamic range for discharging
        selected_hours_str = self.get_state(self.output_selected_hours, state=None)
        if selected_hours_str:
            # Parse the selected hours into a list
            selected_hours = [int(h.split(':')[0]) for h in selected_hours_str.split(',')]  # Assuming format: "15:00,17:00,19:00"
        else:
            # If no dynamic range is set, log an error and do not trigger discharging
            self.log(f"Error: No dynamic discharging range found for today. Discharging will not be triggered.")
            self.log_to_logbook("Error: No dynamic discharging range found for today. Discharging will not be triggered.")
            return  # Exit, do not trigger discharging

        # Ensure the current time is within the selected range for today (non-sequential hours)
        current_hour = now.hour

        # Check if the current hour is one of the selected discharging hours
        if current_hour in selected_hours:
            # Proceed with discharging
            self.log_to_logbook(f"Starting battery discharging")
            self.run_in(self.set_self_consumption_mode, 2)  # Start discharging after 2 seconds delay
            self.call_service(
                "input_select/select_option",
                entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
                option="Stop (default)"  # Start discharging action
            )
        else:
            # Log that the discharging attempt was outside the selected hours
            self.log(f"Discharging triggered at but current hour {current_hour} is outside of the selected hours ({selected_hours}).")
            self.log_to_logbook(f"Discharging attempt outside of selected hours ({selected_hours}).")


    def stop_discharging(self, kwargs):
        """Stop discharging the battery."""
        self.log_to_logbook(f"Stopping battery discharging.")
        self.run_in(self.set_forced_mode, 2)
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Stop (default)"
        )

    def set_self_consumption_mode(self, kwargs):
        """Set EMS mode to Self consumption (default)."""
        self.log_to_logbook("Setting EMS mode to Self consumption (default).")
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_ems_mode",
            option="Self-consumption mode (default)"
        )

    def set_forced_mode(self, kwargs):
        """Set EMS mode to Forced mode."""
        self.log_to_logbook("Setting EMS mode to Forced mode.")
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_ems_mode",
            option="Forced mode"
        )

    def log_to_logbook(self, message):
        """Logs a message to the Home Assistant Logbook."""
        self.call_service(
            "logbook/log",
            name="Smart day discharge",
            message=message,
            entity_id="sensor.selected_discharging_hours"  
        )

