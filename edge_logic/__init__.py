# edge_logic/__init__.py

"""
Edge Logic Package
------------------
This package contains modules simulating the edge processing logic,
such as the Aruba Edge component, for the predictive maintenance demo.
"""

# Make the ArubaEdgeSimulator class directly available
# e.g., from edge_logic import ArubaEdgeSimulator
from .aruba_edge_simulator import ArubaEdgeSimulator

__all__ = ['ArubaEdgeSimulator']