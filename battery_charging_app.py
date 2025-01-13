import appdaemon.plugins.hass.hassapi as hass

class BatteryChargingApp(hass.Hass):

    # This app is a safeguard to recharge battery to 5% when discharged to 1% the day before, no matter tomorrow prices. 
    # Dynamic SOC manager also trigger this charge at 01:00 if setting min SOC to 5%.
    
    def initialize(self):
        """Initialize the app and schedule the battery check at 03:00."""
        self.battery_entity = "sensor.battery_level_nominal"  # Adjust if needed
        self.battery_threshold = 5  # Battery threshold to start/stop charging
        self.monitor_interval = 60  # Interval for checking battery level in seconds
        self.monitoring = False  # Flag to track if we are currently monitoring the battery level
        self.charging_started_by_app = False  # Flag to track if charging was started by this app

        # Trigger to check battery level at 03:00 every day
        self.run_daily(self.check_battery_level, "03:00:00")

    def check_battery_level(self, kwargs=None):
        """Check the battery level at 03:00 and take action."""
        battery_level = self.get_battery_level()

        # Log the initial battery level
        self.log(f"Battery level at 03:00: {battery_level}%")

        # If battery is below threshold, start charging and begin monitoring
        if battery_level < self.battery_threshold:
            self.start_charging()
            self.log(f"Battery level is below {self.battery_threshold}%, starting charging.")
            self.charging_started_by_app = True
            self.monitoring = True
            self.run_in(self.monitor_battery_level, self.monitor_interval)
        else:
            self.log(f"Battery level is above {self.battery_threshold}%, no action taken.")

    def get_battery_level(self):
        """Get the battery level from the sensor."""
        return float(self.get_state(self.battery_entity))

    def start_charging(self):
        """Start charging the battery."""
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_ems_mode",
            option="Forced mode"
        )
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Forced charge"
        )

    def stop_charging(self):
        """Stop charging the battery."""
        self.call_service(
            "input_select/select_option",
            entity_id="input_select.set_sg_battery_forced_charge_discharge_cmd",
            option="Stop (default)"
        )

    def monitor_battery_level(self, kwargs):
        """Monitor the battery level every 60 seconds and stop charging when above 5%."""
        battery_level = self.get_battery_level()

        # Log the current battery level for debugging
        self.log(f"Monitoring - Current battery level: {battery_level}%")

        # If the battery level is above or equal to the threshold, stop charging
        if battery_level >= self.battery_threshold:
            # Only stop charging if it was started by this app
            if self.charging_started_by_app:
                self.stop_charging()
                self.log(f"Battery level has reached {battery_level}%, stopping charging.")
                self.monitoring = False  # Stop monitoring once the threshold is reached
        else:
            # Continue monitoring every 60 seconds if battery is still below threshold
            self.run_in(self.monitor_battery_level, self.monitor_interval)
