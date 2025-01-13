import appdaemon.plugins.hass.hassapi as hass
import datetime

# This app triggers extra night discharging if still juice left in battery and price difference enough.

class ExtraNightDischarging(hass.Hass):
    def initialize(self):
        self.nordpool_sensor = "sensor.nordpool_kwh_se3_sek_3_10_025"
        self.battery_sensor = "sensor.battery_level"
        self.check_hours = [21, 22, 23]  # Adjust hourly triggers to check prices for the next day
        self.price_threshold_offset = 50

        # Schedule checks at specified hours
        for hour in self.check_hours:
            self.run_daily(self.check_conditions, datetime.time(hour, 0, 1))  # 1 second after each hour to fetch new prices

    def check_conditions(self, kwargs):
        """Check if the discharging conditions are met."""
        # Fetch the current price and battery level
        current_price = self.get_state(self.nordpool_sensor)
        battery_level = self.get_state(self.battery_sensor)

        # Validate and parse sensor values
        try:
            current_price = float(current_price)
            battery_level = float(battery_level)
        except (TypeError, ValueError):
            self.log_to_logbook("Error: Invalid sensor data for price or battery level")
            return

        # Fetch tomorrow's prices and calculate the mean of the 2 cheapest hours (00:00-06:00)
        tomorrow_prices = self.get_state(self.nordpool_sensor, attribute="tomorrow") or []
        if len(tomorrow_prices) >= 6:
            # Calculate the mean of the 2 cheapest hours directly from the first 6 hours (00:00-06:00)
            sorted_prices = sorted(tomorrow_prices[:6])  # Only use the first 6 hours for night time
            mean_cheapest_2 = sum(sorted_prices[:2]) / 2
        else:
            self.log_to_logbook("Insufficient price data for tomorrow. Discharge skipped.")
            return

        # Calculate the price difference
        price_difference = current_price - mean_cheapest_2

        # Check discharging conditions: current price vs. mean of the cheapest 2 hours + offset
        if battery_level > 1 and price_difference >= self.price_threshold_offset:
            self.start_discharging()
            # Schedule stop discharging at the end of the hour
            self.run_at(self.stop_discharging, self.calculate_end_of_hour())
        else:
            # Log specific reasons for not starting discharge
            if battery_level <= 1:
                self.log_to_logbook(
                    f"Discharge not started: Battery level too low ({battery_level}%)."
                )
            elif price_difference < self.price_threshold_offset:
                self.log_to_logbook(
                    f"Discharge not started: Price difference too low "
                    f"(Current price: {current_price:.2f}, Mean night hours price: {mean_cheapest_2:.2f}, "
                    f"Price difference: {price_difference:.2f}, Threshold: {self.price_threshold_offset})."
                )

    def start_discharging(self):
        """Start discharging the battery."""
        self.log_to_logbook("Night discharging conditions met, proceeding with discharge.")
        self.run_in(self.set_self_consumption_mode, 8)

    def set_self_consumption_mode(self, kwargs):
        """Set EMS mode to Self Consumption with delays for actions."""
        # Set EMS mode to "Self-consumption mode (default)"
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_ems_mode",
            option="Self-consumption mode (default)"
        )
        self.run_in(self.stop_forced_mode, 2)

    def stop_forced_mode(self, kwargs):
        """Stop forced charging/discharging after EMS mode is set."""
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Stop (default)"
        )
        self.log_to_logbook("EMS mode set to Self-consumption mode. Discharge started.")

    def stop_discharging(self, kwargs):
        """Stop discharging at the end of each hour."""
        # Set EMS mode back to "Forced mode"
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_ems_mode",
            option="Forced mode"
        )
        self.run_in(self.stop_forced_mode_at_hour_end, 2)

    def stop_forced_mode_at_hour_end(self, kwargs):
        """Stop forced mode at the end of the hour."""
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Stop (default)"
        )
        self.log_to_logbook("Discharge stopped for this hour.")

    def log_to_logbook(self, message):
        """Log messages to the Logbook in Home Assistant."""
        self.call_service(
            "logbook/log",
            name="Extra Night Discharging",
            message=message
        )

    def calculate_end_of_hour(self):
        """Calculate the time when the current hour ends (start of next hour)."""
        now = self.datetime()
        return self.datetime().replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
