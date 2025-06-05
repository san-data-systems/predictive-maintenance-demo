# utilities/common_utils.py

import datetime
import yaml
import os
import logging # Using standard logging for utilities

# Configure a basic logger for utility functions
logger = logging.getLogger(__name__)
# To see output from this logger if you run scripts that use it,
# you might need to configure basicConfig in your main script if it's not already showing.
# For example: logging.basicConfig(level=logging.INFO) in your main script.


def get_utc_timestamp(timespec: str = 'milliseconds') -> str:
    """
    Generates a standardized UTC timestamp string in ISO 8601 format.

    Args:
        timespec (str): Resolution of the timestamp ('microseconds', 'milliseconds', 'seconds').
                        Defaults to 'milliseconds'.

    Returns:
        str: ISO 8601 formatted UTC timestamp string ending with 'Z'.
    """
    return datetime.datetime.utcnow().isoformat(timespec=timespec) + "Z"


def _find_config_file(config_filename="demo_config.yaml", base_search_path="config"):
    """
    Tries to find the configuration file by checking a few common locations
    relative to the current working directory or script locations.
    """
    # Path 1: Directly under base_search_path (e.g., project_root/config/demo_config.yaml)
    path1 = os.path.join(base_search_path, config_filename)
    if os.path.exists(path1):
        return os.path.abspath(path1)

    # Path 2: Relative to a script that might be one level down (e.g., in src/ or pcai_app/)
    # ../config/demo_config.yaml
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__)) # Dir of this utils.py file
        path2 = os.path.join(script_dir, "..", base_search_path, config_filename)
        if os.path.exists(path2):
            return os.path.abspath(path2)
        
        # If utils is inside another folder (e.g. src/utilities)
        path3 = os.path.join(script_dir, "..", "..", base_search_path, config_filename)
        if os.path.exists(path3):
            return os.path.abspath(path3)

    except NameError: # __file__ might not be defined in some execution contexts
        pass

    # Path 4: Current working directory (less ideal but a fallback)
    path4 = os.path.join(os.getcwd(), config_filename)
    if os.path.exists(path4):
        return os.path.abspath(path4)
        
    # Path 5: Directly in current working directory's config folder
    path5 = os.path.join(os.getcwd(), base_search_path, config_filename)
    if os.path.exists(path5):
        return os.path.abspath(path5)


    logger.warning(f"Configuration file '{config_filename}' not found in standard search paths.")
    return None


CONFIG_CACHE = None

def get_full_config(config_filename="demo_config.yaml", config_base_dir="config", force_reload=False) -> dict:
    """
    Loads the entire YAML configuration file.
    Caches the loaded configuration to avoid redundant file I/O unless force_reload is True.

    Args:
        config_filename (str): The name of the configuration file.
        config_base_dir (str): The base directory where the config file is expected (e.g., "config").
        force_reload (bool): If True, reloads the config from disk even if cached.

    Returns:
        dict: The loaded configuration, or an empty dict if not found or error.
    """
    global CONFIG_CACHE
    if CONFIG_CACHE is not None and not force_reload:
        logger.debug("Returning cached full configuration.")
        return CONFIG_CACHE

    effective_config_path = _find_config_file(config_filename, config_base_dir)
    
    if not effective_config_path:
        logger.error(f"Critical: Full configuration file '{config_filename}' could not be found.")
        return {} # Return empty dict if not found

    try:
        with open(effective_config_path, 'r') as f:
            CONFIG_CACHE = yaml.safe_load(f)
        logger.info(f"Successfully loaded full configuration from: {effective_config_path}")
        return CONFIG_CACHE
    except FileNotFoundError:
        logger.error(f"Full configuration file not found at path: {effective_config_path}")
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML in full configuration file {effective_config_path}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading full configuration from {effective_config_path}: {e}")
    
    return {} # Return empty in case of any error


def load_app_config(config_section_name: str, 
                    config_filename="demo_config.yaml", 
                    config_base_dir="config") -> dict:
    """
    Loads a specific section from the main YAML configuration file.

    Args:
        config_section_name (str): The top-level key of the section to load (e.g., 'aruba_edge_simulator').
        config_filename (str): The name of the configuration file.
        config_base_dir (str): The base directory where the config file is expected.


    Returns:
        dict: The configuration for the specified section, or an empty dict if not found or error.
    """
    full_config = get_full_config(config_filename, config_base_dir)
    
    if not full_config: # If full_config loading failed
        return {}

    app_specific_config = full_config.get(config_section_name)

    if app_specific_config is None:
        logger.warning(f"Configuration section '{config_section_name}' not found in {config_filename}.")
        return {}
    
    logger.info(f"Successfully loaded configuration section '{config_section_name}'.")
    return app_specific_config


if __name__ == '__main__':
    # Example usage (assuming config/demo_config.yaml exists at project root)
    print(f"Current UTC Timestamp: {get_utc_timestamp()}")
    print(f"Current UTC Timestamp (microseconds): {get_utc_timestamp(timespec='microseconds')}")

    # Test loading full config (adjust path if your script is not in project root when testing)
    print("\n--- Testing Full Config Load ---")
    full_conf = get_full_config() # Uses default "demo_config.yaml" and "config" base dir
    if full_conf:
        print(f"Company Name from full config: {full_conf.get('company_name_short', 'N/A')}")
        # print(f"Full config loaded: {json.dumps(full_conf, indent=2)}")
    else:
        print("Failed to load full configuration.")

    print("\n--- Testing App Specific Config Load ---")
    iot_sensor_config = load_app_config('iot_sensor_simulator')
    if iot_sensor_config:
        print(f"IoT Sensor Config - Asset Prefix: {iot_sensor_config.get('asset_id_prefix')}")
    else:
        print("Failed to load 'iot_sensor_simulator' config section.")

    edge_config = load_app_config('aruba_edge_simulator')
    if edge_config:
        print(f"Aruba Edge Config - Device Template: {edge_config.get('device_id_template')}")
    else:
        print("Failed to load 'aruba_edge_simulator' config section.")

    pcai_config = load_app_config('pcai_app')
    if pcai_config:
        print(f"PCAI App Config - Listen Host: {pcai_config.get('listen_host')}")
    else:
        print("Failed to load 'pcai_app' config section.")

    non_existent_config = load_app_config('non_existent_section')
    if not non_existent_config:
        print("Correctly returned empty for 'non_existent_section'.")