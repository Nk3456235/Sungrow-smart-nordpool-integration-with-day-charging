import appdaemon.plugins.hass.hassapi as hass

    # This app exist to potentially stop discharging when next day Nordpool data becomes available.
    # Sometimes we have scheduled discharging but next night prices come in near level or higher than our scheduled discharging hours.
    # This most often mean higher prices the following day and we should save the power for these hours instead.
    # We stop discharging if current hour price compared to night charging prices has a difference of 40 or lower since we cant recharge cheaper than our threshold value.
    # Repeats stop discharging every hour until midnight.

class BatteryDischargeMonitor(hass.Hass):
    def initialize(self):
        # Schedule the check for 1 second after each hour between 14:00 and 23:00
        self.run_daily(self.check_battery_discharge, "14:00:01")
        self.run_daily(self.check_battery_discharge, "15:00:01")
        self.run_daily(self.check_battery_discharge, "16:00:01")
        self.run_daily(self.check_battery_discharge, "17:00:01")
        self.run_daily(self.check_battery_discharge, "18:00:01")
        self.run_daily(self.check_battery_discharge, "19:00:01")
        self.run_daily(self.check_battery_discharge, "20:00:01")
        self.run_daily(self.check_battery_discharge, "21:00:01")
        self.run_daily(self.check_battery_discharge, "22:00:01")
        self.run_daily(self.check_battery_discharge, "23:00:01")

    def check_battery_discharge(self, kwargs):
        # Fetch value from the "nordpool_kwh_se3_sek_3_10_025" sensor
        nordpool_value = self.get_state("sensor.nordpool_kwh_se3_sek_3_10_025")

        # Ensure we have a valid sensor value for nordpool
        try:
            nordpool_value = float(nordpool_value)
        except ValueError:
            self.log("Invalid nordpool value. Cannot proceed with discharging check.")
            return

        # Fetch the value from "sensor.mock_selected_charging_hours_prices"
        charging_hours_value = self.get_state("sensor.mock_selected_charging_hours_prices")

        # If mock_selected_charging_hours_prices has an invalid state, use mock_chosen_3_hours
        if charging_hours_value is None or charging_hours_value == "unavailable" or charging_hours_value == "unknown":
            charging_hours_value = self.get_state("sensor.mock_chosen_3_hours")

        # Ensure we have a valid value for charging_hours_value
        try:
            charging_hours_value = float(charging_hours_value)
        except ValueError:
            self.log("Invalid charging hours value. Cannot proceed with discharging check.")
            return

        # Perform the calculation: nordpool_value - charging_hours_value
        price_difference = nordpool_value - charging_hours_value

        # Log the calculation
        self.log(f"Price difference between current hour and cheapest next night {price_difference}")

        # If the result is below 40, stop discharging
        if price_difference < 40:
            self.log(f"Price difference is low: {price_difference}, stopping discharging if currently discharging.")
            self.set_state(self.output_selected_hours, state="Price difference too low")
            self.stop_discharging()

    def stop_discharging(self, kwargs):
        """Stop discharging the battery."""
        self.run_in(self.set_forced_mode, 10)
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Stop (default)"
        )

    def set_forced_mode(self, kwargs):
        """Set EMS mode to Forced mode."""
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_ems_mode",
            option="Forced mode"
        )

    def log_to_logbook(self, message):
        """Logs a message to the Home Assistant Logbook."""
        self.call_service(
            "logbook/log",
            name="Battery discharge monitor",
            message=message,
            entity_id="sensor.battery_discharge_monitor"  
        )

