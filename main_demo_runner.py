# main_demo_runner.py

import subprocess
import time
import sys
import os

# --- Configuration ---
# All three modules that need to be run for the local demo
PCAI_APP_MODULE = "pcai_app.main_agent"
EDGE_SIMULATOR_MODULE = "edge_logic.aruba_edge_simulator"
IOT_SENSOR_MODULE = "data_simulators.iot_sensor_simulator" # <-- ADDED THIS

# Delay to allow PCAI App server to start before Edge Sim tries to connect
SERVER_START_DELAY_SECONDS = 5

def print_header(title):
    """Prints a formatted header."""
    print("\n" + "=" * 60)
    print(f"🚀 {title} 🚀")
    print("=" * 60 + "\n")

def run_module_in_subprocess(module_name: str, cwd: str):
    """Runs a Python module in a new subprocess."""
    try:
        process = subprocess.Popen([sys.executable, "-m", module_name], cwd=cwd)
        print(f"INFO: Started module '{module_name}' with PID: {process.pid}")
        return process
    except Exception as e:
        print(f"ERROR: Could not start module '{module_name}': {e}")
    return None

def main():
    """Main function to orchestrate the demo components."""
    print_header("HPE AI-Driven Predictive Maintenance Demo Runner")
    project_root = os.path.dirname(os.path.abspath(__file__))
    print(f"INFO: Project root directory: {project_root}")

    processes = []
    try:
        # 1. Start the PCAI Agent Application (Flask Server)
        print("\n--- [1/3] Starting PCAI Agent Application ---")
        pcai_process = run_module_in_subprocess(PCAI_APP_MODULE, cwd=project_root)
        if not pcai_process: return
        processes.append(pcai_process)
        print(f"\nINFO: Waiting {SERVER_START_DELAY_SECONDS} seconds for services to initialize...")
        time.sleep(SERVER_START_DELAY_SECONDS)

        # 2. Start the IoT Sensor Simulator
        print("\n--- [2/3] Starting IoT Sensor Simulator ---")
        iot_process = run_module_in_subprocess(IOT_SENSOR_MODULE, cwd=project_root)
        if not iot_process: return
        processes.append(iot_process)
        time.sleep(2) # Brief pause for MQTT connection

        # 3. Start the Edge Simulator
        print("\n--- [3/3] Starting Edge & IoT Sensor Simulator ---")
        edge_process = run_module_in_subprocess(EDGE_SIMULATOR_MODULE, cwd=project_root)
        if not edge_process: return
        processes.append(edge_process)

        print("\n--- ✅ All Demo Components Running ---")
        print("Outputs will be interleaved below. Press Ctrl+C to stop all.")
        
        # Wait for any process to exit. If one exits, we can stop the demo.
        while all(p.poll() is None for p in processes):
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nINFO: Ctrl+C received. Shutting down all demo components...")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred in the demo runner: {e}")
    finally:
        print("\n--- Cleaning up ---")
        for process in reversed(processes):
            if process.poll() is None:
                print(f"INFO: Terminating process PID: {process.pid}...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"WARN: PID {process.pid} did not terminate gracefully, killing.")
                    process.kill()
        print("\nDemo Runner finished.")

if __name__ == "__main__":
    main()