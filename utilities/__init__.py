# utilities/__init__.py

"""
Utilities Package
-----------------
This package provides common utility functions and classes shared across
different components of the predictive maintenance demo.

Currently includes helpers for:
- Generating standardized UTC timestamps.
- Loading application-specific sections from the main YAML configuration file.
"""

from .common_utils import get_utc_timestamp, load_app_config, get_full_config

__all__ = [
    'get_utc_timestamp',
    'load_app_config',
    'get_full_config'
]

print("INFO: Utilities package initialized.")