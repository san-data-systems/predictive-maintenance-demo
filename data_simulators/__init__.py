# data_simulators/__init__.py

"""
Data Simulators Package
-----------------------
This package contains modules for simulating various data sources
for the AI-Driven Predictive Maintenance Demo.
"""

# Make the TurbineSensor class directly available when importing from data_simulators
# e.g., from data_simulators import TurbineSensor
from .iot_sensor_simulator import TurbineSensor

# You can also define what '*' imports if someone does 'from data_simulators import *'
# (though 'import *' is generally discouraged in production code, it can be okay for internal packages)
__all__ = ['TurbineSensor']