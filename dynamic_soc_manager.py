import appdaemon.plugins.hass.hassapi as hass
import datetime

class DynamicSOCManager(hass.Hass):
    
    # This app automatically sets SOC values. If large price difference tomorrow charge to 99% and discharge to 1%.
    # If small price difference tomorrow charge to 98% and discharge to 5%.
    # Every sunday set max SOC to 100% and min to 1% for battery balancing purposes.
    
    def initialize(self):
        """Initialize the app and schedule the daily check."""
        # Schedule daily at 01:01 to check and adjust SOC based on electricity prices
        self.run_daily(self.adjust_soc_based_on_prices, datetime.time(1, 1))

    def adjust_soc_based_on_prices(self, kwargs):
        """Evaluate electricity price and adjust SOC values accordingly."""
        
        # Get the current value from the sensor (today's electricity price)
        price_value = self.get_state("sensor.nordpool_mean_low_vs_high_price_today")
        
        try:
            price_value = float(price_value)  # Convert to float
        except (TypeError, ValueError):
            self.log("Error: Invalid price data from sensor.")
            return
        
        # Log the current price for reference
        self.log(f"Today's electricity price (sensor value): {price_value}")
        
        # Get the current day of the week (0=Monday, 6=Sunday)
        today = datetime.datetime.now().weekday()
        
        if today == 6:  # Check if it's Sunday (6 represents Sunday in Python's weekday())
            # On Sunday, set SOC values to 100% high and 1% low
            self.set_state("input_number.set_sg_min_soc", state=1)
            self.set_state("input_number.set_sg_max_soc", state=100)
            self.log("Today is Sunday. Min SOC set to 1% and Max SOC set to 100%.")
            self.call_service("logbook/log", 
                name="Dynamic SOC Manager", 
                message="Today is Sunday. Min SOC set to 1% and Max SOC set to 100%.",
                entity_id="input_number.set_sg_min_soc")
        else:
            # Check the price and adjust SOC values accordingly for Mon-Sat
            if price_value <= 75:
                # Set SOC values to 5% min and 98% max
                self.set_state("input_number.set_sg_min_soc", state=5)
                self.set_state("input_number.set_sg_max_soc", state=98)
                self.log("Electricity price difference is 75 or below. Min SOC set to 5% and Max SOC set to 98%.")
                self.call_service("logbook/log", 
                    name="Dynamic SOC Manager", 
                    message="Electricity price difference is 75 or below. Min SOC set to 5% and Max SOC set to 98%.",
                    entity_id="input_number.set_sg_min_soc")
            else:
                # Set SOC values to 1% min and 99% max
                self.set_state("input_number.set_sg_min_soc", state=1)
                self.set_state("input_number.set_sg_max_soc", state=99)
                self.log("Electricity price difference is above 75. Min SOC set to 1% and Max SOC set to 99%.")
                self.call_service("logbook/log", 
                    name="Dynamic SOC Manager", 
                    message="Electricity price difference is above 75. Min SOC set to 1% and Max SOC set to 99%.",
                    entity_id="input_number.set_sg_min_soc")
