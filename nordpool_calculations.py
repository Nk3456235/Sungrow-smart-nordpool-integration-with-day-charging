import appdaemon.plugins.hass.hassapi as hass

class NordpoolCalculation(hass.Hass):

    def initialize(self):
        self.sensor_name = "sensor.nordpool_kwh_se3_sek_3_10_025"

        # Run the calculation once every day at 14:00 to ensure 'tomorrow' data is updated
        self.run_daily(self.update_tomorrow_data, "14:00:00")

    def update_tomorrow_data(self, *args):
        tomorrow_prices = self.get_state(self.sensor_name, attribute="tomorrow") or []
        tomorrow_valid = self.get_state(self.sensor_name, attribute="tomorrow_valid")

        self.log(f"Tomorrow prices: {tomorrow_prices}")
        self.log(f"Tomorrow valid: {tomorrow_valid}")

        if not tomorrow_valid or not tomorrow_prices:
            self.log("Tomorrow prices not yet available. Triggering update.")
            # You can add logic here to trigger any update mechanism (like refreshing or requesting the data) if needed.
        else:
            self.log("Tomorrow prices are available and valid.")
