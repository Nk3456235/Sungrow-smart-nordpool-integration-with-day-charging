import appdaemon.plugins.hass.hassapi as hass

    # This app exist to potentially stop discharging when next day Nordpool data becomes available.
    # Sometimes we have scheduled discharging but next night prices come in near level or higher than our scheduled discharging hours.
    # This most often mean higher prices the following day and we should save the power for these hours instead.
    # We stop discharging if sensor nordpool_mean_high_today_vs_low_tomorrow has a value below 40 since we cant recharge cheaper than our threshold value.
    # Repeats stop discharging every hour until midnight.

class BatteryDischargeMonitor(hass.Hass):
    def initialize(self):
        # Runs the check every hour between 14:00 and 23:00
        self.run_daily(self.check_battery_discharge, "14:00:00")
        self.run_daily(self.check_battery_discharge, "15:00:00")
        self.run_daily(self.check_battery_discharge, "16:00:00")
        self.run_daily(self.check_battery_discharge, "17:00:00")
        self.run_daily(self.check_battery_discharge, "18:00:00")
        self.run_daily(self.check_battery_discharge, "19:00:00")
        self.run_daily(self.check_battery_discharge, "20:00:00")
        self.run_daily(self.check_battery_discharge, "21:00:00")
        self.run_daily(self.check_battery_discharge, "22:00:00")
        self.run_daily(self.check_battery_discharge, "23:00:00")

    def check_battery_discharge(self, kwargs):
        # Get the current value of the sensor
        sensor_value = self.get_state("sensor.nordpool_mean_high_today_vs_low_tomorrow")
        
        # Ensure we have a valid sensor value and it's a number
        try:
            sensor_value = float(sensor_value)
        except ValueError:
            self.log("Invalid sensor value. Cannot proceed with discharging check.")
            return

        # If the sensor value is less than 40, stop discharging
        if sensor_value < 40:
            self.log(f"Sensor value is {sensor_value}, stopping battery discharging.")
            self.stop_discharging()

    def stop_discharging(self):
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
