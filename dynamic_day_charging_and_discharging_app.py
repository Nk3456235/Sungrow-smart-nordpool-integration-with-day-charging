import appdaemon.plugins.hass.hassapi as hass
import datetime
import re  
    
    # This app dynamically sets discharging hours before and after a cheap charging hour during the day meeting a 40 öre price threshold.
    # For app to run we need at least 3 hours before and after the cheap day hour that meets the threshold. If less hours than this not a big value in day charging and certain price fluctuance situations may lead to discharge at suboptimal hours with the other methods i tried. I then found it better to just run the regular discharging app.
    # We set a dynamic battery charging goal depending on how many hours that meet price threshold after the charging hour.
    # We set charging w speed dynamically depending on how much we need to recharge battery after morning discharge.
    # App tracks battery level to stop charging at battery goal level or at hour end. 
    # ctrl+f CHANGEME will display all price thresholds, battery charge goal for adjustment and charging speed.
    # App outputs sensor.cheap_hour_comparison1, sensor.cheap_chosen_hour_day_charging3 and sensor.dynamic_discharging_hours for display


class DynamicDayChargingAndDischargingApp(hass.Hass):
    def initialize(self):
        self.charging_started_by_app = False
        self.monitoring = False
        self.battery_threshold = 60  # Fallback battery threshold value
        self.monitor_interval = 60  # Interval for battery monitoring in seconds
        self.selected_hours = []  # List to store selected hours for charging
        self.expensive_hours = []  # List to store expensive hours for discharging

        self.log("DynamicDayChargingAndDischargingApp initialized. Running immediate price check.")
        
        self.update_cheap_hour() # Trigger the update calculation at startup

        # Trigger the update calculation every day at 00:05
        self.run_daily(self.update_cheap_hour, datetime.time(0, 5))

    def update_cheap_hour(self, kwargs=None):
        """Calculates the cheapest hour for charging from 10:00 to 15:00."""
        self.log("Starting price evaluation for cheapest hour.")
        
        today_prices = self.get_state("sensor.nordpool_kwh_se3_sek_3_10_025", attribute="today")
        
        if not today_prices:
            self.log("No prices available from Nordpool sensor. No charge.")
            return

        # Get prices for hours 10:00 to 15:00
        hours_10_to_16 = today_prices[10:16]
        self.log_to_logbook(f"Prices for 10:00-15:00: {hours_10_to_16}")
        self.log(f"Prices for 10:00-15:00: {hours_10_to_16}")
        
        # Sort and select the cheapest hour (index)
        cheapest_hour = min(enumerate(hours_10_to_16, start=10), key=lambda x: x[1])
        self.log(f"Cheapest hour is {cheapest_hour[0]}:00 with a price of {cheapest_hour[1]:.2f} öre.")

        if not cheapest_hour:
            self.log("No cheap hours found between 10:00-15:00.")
            return

        selected_hour = cheapest_hour[0]
        
        # Get prices from 06:00 to the selected hour (exclusive)
        hours_06_to_selected = today_prices[6:selected_hour]
        # Get prices from the selected hour to 23:00
        hours_selected_to_23 = today_prices[selected_hour:23]
        
        # Identify the 3 most expensive hours before the selected hour
        most_expensive_before = sorted([(price, index + 6) for index, price in enumerate(hours_06_to_selected)], reverse=True)[:3]
        # Identify the 3 most expensive hours after the selected hour
        most_expensive_after = sorted([(price, index + selected_hour) for index, price in enumerate(hours_selected_to_23)], reverse=True)[:3]
        
        # Log the most expensive hours before and after the selected hour
        self.log(f"Most expensive hours before selected: {[(index, price) for price, index in most_expensive_before]}")
        self.log(f"Most expensive hours after selected: {[(index, price) for price, index in most_expensive_after]}")

        # Check price difference for the most expensive hours before and after
        for price, before_index in most_expensive_before:
            price_diff_before = price - cheapest_hour[1]
            if price_diff_before < 40: #CHANGEME
                self.log(f"Price difference too low {before_index}:00 and {selected_hour}:00 is only {price_diff_before:.2f} öre, not scheduling day charging.")
                self.set_state("sensor.cheap_hour_comparison1", state=f"Price difference too low")
                self.set_state("sensor.dynamic_discharging_hours", state="No day charging scheduled")
                self.set_state("sensor.cheap_chosen_hour_day_charging3", state="No day charging scheduled")
                return

        for price, after_index in most_expensive_after:
            price_diff_after = price - cheapest_hour[1]
            if price_diff_after < 40:  #CHANGEME
                self.log(f"Price difference between {after_index}:00 and {selected_hour}:00 is only {price_diff_after:.2f} öre, not scheduling day charging.")
                self.set_state("sensor.cheap_hour_comparison1", state=f"Price difference too low")
                self.set_state("sensor.dynamic_discharging_hours", state="No day charging scheduled")
                self.set_state("sensor.cheap_chosen_hour_day_charging3", state="No day charging scheduled")
                return

        # If all checks pass, log the final decision
        self.log(f"Selected cheapest hour: {selected_hour}:00 with price {cheapest_hour[1]:.2f} öre.")
        self.set_state("sensor.cheap_hour_comparison1", state=f"{selected_hour}:00 | {cheapest_hour[1]:.2f} Öre/kWh")

        
        # If the price difference is sufficient, proceed with evaluating the price differences
        self.evaluate_price_differences(selected_hour, today_prices)


    def evaluate_price_differences(self, selected_hour, today_prices):
        """Evaluates price differences for both before and after the selected charging hour."""

        # Ensure we discard the first 6 hours (00:00 to 05:00) from the prices
        today_prices = today_prices[6:]  # Remove the first 6 hours (00:00-05:00)
        
        # Generate list of hours from 06:00 to 23:00
        hours = [f"{hour}:00" for hour in range(6, 24)]  # From 06:00 to 23:00
        
        # The selected hour price (this is the benchmark price we compare against)
        selected_hour_price = today_prices[selected_hour - 6]  # The price at the selected hour (e.g., 13:00)
        
        # Step 1: Get the state of the sensor (fetching selected_charging_hours_prices)
        selected_charging_hours_prices_state = self.get_state("sensor.selected_charging_hours_prices")
        
        # Ensure the state is valid 
        if not selected_charging_hours_prices_state:
            self.log("Error: Sensor state for 'sensor.selected_charging_hours_prices' is unavailable.")
            return

        try:
            # Convert the sensor state to a float (it represents the mean price from 00:00 to 06:00)
            mean_price_first_six_hours = float(selected_charging_hours_prices_state)
        except ValueError as e:
            self.log(f"Error: Failed to convert sensor state to float: {e}")
            return
        
        self.log(f"Mean night charging price (5 cheapest hours between from 00:00 and 06:00): {mean_price_first_six_hours} öre")

        # Step 2: Split prices into before and after selected hour
        # Before selected hour
        hours_before_selected = hours[:selected_hour - 6]  # From 06:00 to just before selected hour
        prices_before_selected = today_prices[:selected_hour - 6]
        
        # After selected hour
        hours_after_selected = hours[selected_hour - 6 + 1:]  # From selected hour to 23:00
        prices_after_selected = today_prices[selected_hour - 6 + 1:]

        # Step 3: Identify expensive hours before the selected hour (at least 40 öre more expensive than selected hour)
        self.log(f"Evaluating prices before {hours[selected_hour - 6]}.")
        self.log(f"Hours before {hours[selected_hour - 6]}: {prices_before_selected}")

        # Identify expensive hours before the selected hour (at least 40 öre more expensive than selected hour)
        expensive_hours_before_selected = [
            (hours_before_selected[i], prices_before_selected[i] - selected_hour_price)
            for i in range(len(prices_before_selected))
            if (prices_before_selected[i] - selected_hour_price) >= 40  # 40 öre threshold for before hours CHANGEME
        ]
        
        # Log expensive hours before the selected hour
        for hour, diff in expensive_hours_before_selected:
            self.log(f"Expensive hour identified (before {hours[selected_hour - 6]}): {hour} with price difference: {diff} öre")

        # Step 4: Identify expensive hours after the selected hour, based on mean price from sensor.selected_charging_hours_prices
        self.log(f"Evaluating prices after {hours[selected_hour - 6 + 1]}.")
        self.log(f"Hours after {hours[selected_hour - 6 + 1]}: {prices_after_selected}")

        # Identify expensive hours after the selected hour (at least 40 öre more expensive than selected hour)
        expensive_hours_after_selected = [
            (hours_after_selected[i], prices_after_selected[i] - selected_hour_price)
            for i in range(len(prices_after_selected))
            if (prices_after_selected[i] - selected_hour_price) >= 40  # 40 öre threshold for after hours CHANGEME
        ]
        
        # Log expensive hours after the selected hour
        for hour, diff in expensive_hours_after_selected:
            self.log(f"Expensive hour identified (after {hours[selected_hour - 6 + 1]}): {hour} with price difference: {diff} öre")

        # Step 5: Sort Expensive Hours Separately
        expensive_hours_before_selected.sort(key=lambda x: x[1], reverse=True)
        expensive_hours_after_selected.sort(key=lambda x: x[1], reverse=True)

        # Log sorted expensive hours
        self.log(f"Expensive hours before {hours[selected_hour - 6]}: {', '.join([hour for hour, _ in expensive_hours_before_selected])} (most expensive to least expensive)")
        self.log(f"Expensive hours after {hours[selected_hour - 6 + 1]}: {', '.join([hour for hour, _ in expensive_hours_after_selected])}  (most expensive to least expensive)")

        # Count the number of expensive hours after selected hour (based on 40 öre threshold)
        num_expensive_hours_after_selected_40_ore = len(expensive_hours_after_selected)

        # Log the number of expensive hours after selected hour
        self.log(f"Number of hours after {hours[selected_hour - 6 + 1]} that are at least 40 öre more expensive: {num_expensive_hours_after_selected_40_ore}")

        # Set Battery Goal Based on the Number of Expensive Hours (at least 40 öre more expensive)
        self.battery_goal = {0: 0, 1: 15, 2: 30, 3: 45, 4: 60, 5: 75, 6: 90, 7: 95}.get(num_expensive_hours_after_selected_40_ore, 95)

        # Log the battery goal
        self.log(f"Battery goal based on expensive hours (40 öre threshold): {self.battery_goal}%")

        # Step 6: Set the charging goal and log it
        self.set_state("sensor.number_of_day_hours", state=f"Charging goal: {self.battery_goal}%")
        self.log(f"Setting battery charge goal to {self.battery_goal}% based on {num_expensive_hours_after_selected_40_ore} qualifying hours after the charging hour.")

        # Dynamically adjust the battery threshold to the calculated battery goal
        self.log(f"Evaluating price differences. Current battery_goal: {self.battery_goal}")
        self.adjust_battery_threshold()  

        # Step 7: Set the Charging Schedule
        self.set_state(
            "sensor.cheap_chosen_hour_day_charging3", 
            state=hours[selected_hour - 6],  # Using the hour from the hours list
            attributes={"description": "Chosen cheap hour for battery charging during the day"}
        )

        # Proceed with charging schedule 
        if num_expensive_hours_after_selected_40_ore > 0:
            self.schedule_charging_at_selected_hour(selected_hour)

            self.log(f"Scheduling discharging as price difference is above threshold")
            
            # Dynamically schedule discharging based on the number of expensive hours before and after
            discharging_hours = self.schedule_discharging(expensive_hours_before_selected, expensive_hours_after_selected)
            
            # Create or update the dynamic discharging hours sensor
            self.create_discharging_hours_sensor(discharging_hours)
            

    def schedule_discharging(self, expensive_hours_before_selected, expensive_hours_after_selected):
        """Schedules discharging for the most expensive hours before and after the selected hour, limiting to 6 hours each."""

        # Step 1: Limit the number of hours before and after to 6 most expensive ones
        expensive_hours_before_selected = sorted(expensive_hours_before_selected, key=lambda x: x[1], reverse=True)[:6]
        expensive_hours_after_selected = sorted(expensive_hours_after_selected, key=lambda x: x[1], reverse=True)[:6]

        # Log the selected expensive hours before and after (after sorting)
        self.log(f"Up to 6 most expensive hours before selected: {', '.join([hour[0] for hour in expensive_hours_before_selected])}")
        self.log(f"Up to 6 most expensive hours after selected: {', '.join([hour[0] for hour in expensive_hours_after_selected])}")

        # Step 2: Generate list of discharging hours before and after
        discharging_hours = []

        # Add expensive hours before the selected hour
        discharging_hours.extend([hour for hour, _ in expensive_hours_before_selected])

        # Add expensive hours after the selected hour
        discharging_hours.extend([hour for hour, _ in expensive_hours_after_selected])

        # Step 3: Sort the discharging hours list by time (ascending order)
        discharging_hours = sorted(discharging_hours, key=lambda x: int(x.split(':')[0]))

        # Log the discharging schedule
        self.log(f"Scheduling discharging at the following hours: {', '.join(discharging_hours)}")

        # Step 4: Identify consecutive hours and schedule accordingly
        grouped_hours = self.group_consecutive_hours(discharging_hours)

        # Step 5: Schedule start and stop discharging for each group of consecutive hours
        for group in grouped_hours:
            # Schedule start discharging at the beginning of each group
            start_hour = int(group[0].split(':')[0])  # First hour in the group
            self.schedule_start_stop_discharging(start_hour, group)

        # Return the discharging hours for further action (if needed)
        return discharging_hours



    def schedule_start_stop_discharging(self, start_hour, group):
        """Schedules the start and stop of discharging, with date included for correct triggering."""

        now = datetime.datetime.now()  # Get the current date

        # Calculate the start time for discharging
        start_time = datetime.datetime.combine(now.date(), datetime.time(start_hour, 0))  # Set date + hour
        if start_time > now:
            self.run_at(self.start_discharging, start_time)  
            self.log(f"Scheduling start discharging at {start_time.strftime('%H:%M')}")
        else:
            self.log(f"Start time {start_time} is in the past today. Skipping start scheduling.")

        # Calculate the stop time for discharging (last hour + 1)
        end_hour = int(group[-1].split(':')[0])  # Last hour in the group
        
        # Handle cases where stop time crosses midnight
        if end_hour == 23:
            stop_time = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), datetime.time(0, 0))
        else:
            stop_time = datetime.datetime.combine(now.date(), datetime.time(end_hour + 1, 0))

        # Schedule stop discharging without passing kwargs
        if stop_time > now:
            self.run_at(self.stop_discharging, stop_time)  
            self.log(f"Scheduling stop discharging at {stop_time.strftime('%H:%M')}")
        else:
            self.log(f"Stop time {stop_time} is in the past today. Skipping stop scheduling.")


    def create_discharging_hours_sensor(self, discharging_hours):
        """Create or update a sensor to show the discharging hours."""
        if discharging_hours:
            # Format the discharging hours into readable ranges
            ranges = self.format_discharging_hours(discharging_hours)
            self.set_state("sensor.dynamic_discharging_hours", state=ranges)
        else:
            self.set_state("sensor.dynamic_discharging_hours", state="No discharging hours scheduled")

    def format_discharging_hours(self, discharging_hours):
        """Formats discharging hours into ranges like '9-12' or '15-21'."""
        ranges = []
        start_hour = None
        end_hour = None

        for i, hour in enumerate(discharging_hours):
            hour_int = int(hour.split(':')[0])  # Convert hour to integer
            if start_hour is None:
                start_hour = hour_int
                end_hour = hour_int
            elif hour_int == end_hour + 1:
                # If consecutive hour, extend the range
                end_hour = hour_int
            else:
                # If not consecutive, finish the previous range and start a new one
                ranges.append(f"{start_hour}:00-{end_hour + 1}:00")  # Add +1 to last hour for correct range
                start_hour = hour_int
                end_hour = hour_int
        
        # Append the last range (don't forget to add +1 to the last hour)
        if start_hour is not None:
            ranges.append(f"{start_hour}:00-{end_hour + 1}:00")  # Add +1 to last hour for correct range

        return ', '.join(ranges)


    def group_consecutive_hours(self, hours):
        """Groups consecutive hours into sequences."""
        grouped = []
        current_group = []

        for i, hour in enumerate(hours):
            if not current_group:  # If the current group is empty, start a new group
                current_group.append(hour)
            elif int(hour.split(':')[0]) == int(current_group[-1].split(':')[0]) + 1:  # If hour is consecutive, add it to the group
                current_group.append(hour)
            else:
                # If the hour is not consecutive, finalize the current group and start a new one
                grouped.append(current_group)
                current_group = [hour]
        
        # Add the last group if it exists
        if current_group:
            grouped.append(current_group)
        
        return grouped



    def start_discharging(self, kwargs=None):
        """Start discharging the battery at the beginning of the hour."""
        now = datetime.datetime.now()  # Just use current time for log
        self.log(f"Starting battery discharging at {now.strftime('%H:%M')}.")
        self.log_to_logbook(f"Starting battery discharging at {now.strftime('%H:%M')}.")
        # Actions for starting discharging
        self.run_in(self.set_self_consumption_mode, 8)
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Stop (default)"
        )


    def stop_discharging(self, kwargs=None):
        """Stop discharging the battery at the end stop hour."""
        now = datetime.datetime.now()  # Just use current time for log
        self.log(f"Stopping battery discharging at {now.strftime('%H:%M')}.")
        self.log_to_logbook(f"Stopping battery discharging at {now.strftime('%H:%M')}.")
        # Actions for stopping discharging)
        self.run_in(self.set_forced_mode, 2)
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Stop (default)"
        )


    def adjust_battery_threshold(self, kwargs=None):
        """Dynamically adjust the battery threshold based on the charging goal."""
        self.battery_threshold = self.battery_goal  # Use the instance's battery_goal
        self.log(f"Battery threshold set to {self.battery_threshold}% based on price evaluation.")


    def schedule_charging_at_selected_hour(self, selected_hour):
        """Schedule the start of charging at the selected hour."""
        self.selected_hours = [selected_hour]
        self.log(f"Scheduling charging at {selected_hour}:00.")

        now = datetime.datetime.now()  # Get the current date
        start_time = datetime.datetime.combine(now.date(), datetime.time(selected_hour, 0))  # Set date + hour

        # Schedule charging start using run_in with the time difference from now
        delay_until_start = (start_time - now).total_seconds()
        if delay_until_start > 0:
            self.run_in(self.start_charging, delay_until_start)
            self.log(f"Charging will start at {start_time}")
        else:
            self.log(f"Selected hour {selected_hour}:00 is in the past today. Skipping scheduling.")

        # Schedule stop charging 1 hour after the selected start time
        stop_time = start_time + datetime.timedelta(hours=1)
        delay_until_stop = (stop_time - now).total_seconds()
        if delay_until_stop > 0:
            self.run_in(self.stop_charging, delay_until_stop)
            self.log(f"Charging will stop at {stop_time}")
        else:
            self.log(f"Stop time {stop_time} is in the past today. Skipping stop scheduling.")

    def start_charging(self, kwargs):
        """Start charging the battery when the current hour matches the selected hour."""
        current_hour = datetime.datetime.now().hour
        self.log(f"Current hour: {current_hour}, Selected hour: {self.selected_hours[0]}")  # Log both values for clarity
        
        if current_hour == self.selected_hours[0]:
            battery_level = float(self.get_state("sensor.battery_level_nominal", default=100))
            self.log(f"Battery level at the start: {battery_level}%.")
            
            # Use the previously calculated battery_goal
            battery_goal = self.battery_goal  # We use the already calculated battery goal

            self.log(f"Battery goal: {battery_goal}%.")

            # Calculate the charging level (goal - current battery level)
            charging_level = battery_goal - battery_level
            self.log(f"Charging level (goal - current level): {charging_level}%.")

            # Get the appropriate charging speed based on the charging level
            max_power = self.get_charging_speed()
            self.log(f"Calculated charging power: {max_power}W.")

            # Set max charging power
            self.call_service(
                "input_number/set_value",
                entity_id="input_number.set_sg_battery_max_charge_power",
                value=max_power
            )
            self.log(f"Setting max charging power to {max_power}W.")

            if battery_level < battery_goal:
                # Start charging
                self.charging_started_by_app = True
                self.monitoring = True
                self.log(f"Charging started. Monitoring flag set to: {self.monitoring}")
                self.log_to_logbook(f"Charging started. Monitoring flag set to: {self.monitoring}")
                
                # Start monitoring battery level
                self.run_in(self.monitor_battery_level, self.monitor_interval)
                self.log(f"Battery level at start of monitoring: {battery_level}%")
                self.log_to_logbook(f"Battery level at start of monitoring: {battery_level}%")
                
                # Set forced mode and schedule charging stop
                self.run_in(self.set_forced_mode, 2)
                self.run_in(self.set_forced_charge, 4)
                self.run_in(self.stop_charging, self.calculate_seconds_until_end(current_hour))
            else:
                self.log_to_logbook(f"Battery level too high ({battery_level}%). No charging started.")
                self.log(f"Battery level too high ({battery_level}%). No charging started.")
                self.set_state("sensor.cheap_chosen_hour_day_charging3", state="Battery level too high")
        else:
            self.log(f"Current hour {current_hour} does not match the selected charging hour {self.selected_hours[0]}.")

    def get_charging_speed(self, kwargs=None):
        """Determine the charging speed based on the difference between current battery level and goal."""
        # Use the battery_goal from the instance (self)
        battery_goal = self.battery_goal  # Get the already calculated battery goal
        
        # Get the current battery level
        current_battery_level = float(self.get_state("sensor.battery_level_nominal", default=100))  # Assuming 100% is the default if not available

        # Calculate the charging level (percentage needed to reach the battery goal)
        charging_level = battery_goal - current_battery_level
        
        # Determine the charging power based on the charging level % CHANGEME
        if charging_level > 55:
            max_power = 9000
        elif charging_level >= 45:
            max_power = 8400
        elif charging_level >= 35:
            max_power = 7000
        elif charging_level >= 25:
            max_power = 5600
        elif charging_level >= 15:
            max_power = 4200
        elif charging_level >= 5:
            max_power = 2800
        else:
            max_power = 3800  # Fallback charging value

        self.log(f"Charging speed set to {max_power}W for a charging level of {charging_level}%.")
        
        return max_power



    def monitor_battery_level(self, kwargs):
        """Monitor the battery level every 60 seconds and stop charging when above 97%."""
        battery_level = float(self.get_state("sensor.battery_level_nominal", default=100))
        self.log(f"Monitoring - Current battery level: {battery_level}%")

        if battery_level >= self.battery_threshold:
            if self.charging_started_by_app:
                self.stop_charging()  # Stop charging
                self.log(f"Battery level has reached threshold {battery_level}%, stopping charging.")
                self.log_to_logbook(f"Battery level has reached threshold {battery_level}%, stopping charging.")
                self.monitoring = False  # Stop monitoring once the threshold is reached
        else:
            if not self.monitoring:
                self.monitoring = True
            self.run_in(self.monitor_battery_level, self.monitor_interval)

    def stop_charging(self, kwargs=None):
        """Stops charging after the hour ends or if battery level reaches threshold %."""
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

    def set_self_consumption_mode(self, kwargs):
        """Set EMS mode to Self consumption (default)."""
        self.log_to_logbook("Setting EMS mode to Self consumption (default).")
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_ems_mode",
            option="Self-consumption mode (default)"
        )

    def calculate_seconds_until_end(self, hour):
        """Calculates the seconds until the selected hour ends."""
        now = datetime.datetime.now()
        end_time = datetime.datetime.combine(now.date(), datetime.time(hour)) + datetime.timedelta(hours=1) - datetime.timedelta(seconds=1)
        delta = end_time - now
        self.log(f"Calculated time until the end of hour: {delta.total_seconds()} seconds")
        return max(delta.total_seconds(), 0)


    def format_time(self, hour_index):
        """Helper function to format the timestamp to local time."""
        today_date = datetime.datetime.now().date()  # Get today's date
        formatted_time = datetime.datetime.combine(today_date, datetime.time(hour_index))  # Combine with the hour
        return formatted_time.strftime("%H:%M")  # Return as HH:MM format

    
    def log_to_logbook(self, message):
        """Logs a message to the Home Assistant Logbook."""
        self.call_service(
            "logbook/log",
            name="Dynamic day charging and discharging",
            message=message
        )
