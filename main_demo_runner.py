# main_demo_runner.py

import subprocess
import time
import sys
import os

# --- Configuration ---
# Modules to run (these should be runnable using 'python -m <module_name>')
PCAI_APP_MODULE = "pcai_app.main_agent"
EDGE_SIMULATOR_MODULE = "edge_logic.aruba_edge_simulator"

# Delay to allow PCAI App server to start before Edge Sim tries to connect
SERVER_START_DELAY_SECONDS = 5

def print_header(title):
    """Prints a formatted header."""
    print("\n" + "=" * 60)
    print(f"🚀 {title} 🚀")
    print("=" * 60 + "\n")

def run_module_in_subprocess(module_name: str, cwd: str):
    """
    Runs a Python module in a new subprocess.

    Args:
        module_name (str): The name of the module to run (e.g., 'package.subpackage.module').
        cwd (str): The current working directory for the subprocess.

    Returns:
        subprocess.Popen: The Popen object for the started process, or None if failed.
    """
    try:
        # sys.executable gives the path to the current Python interpreter
        process = subprocess.Popen(
            [sys.executable, "-m", module_name],
            cwd=cwd,
            # stdout=subprocess.PIPE, # Optional: if you want to capture/redirect output
            # stderr=subprocess.PIPE  # Optional: if you want to capture/redirect output
        )
        print(f"INFO: Started module '{module_name}' with PID: {process.pid}")
        return process
    except FileNotFoundError:
        print(f"ERROR: Python interpreter '{sys.executable}' not found. Is Python installed and in PATH?")
    except Exception as e:
        print(f"ERROR: Could not start module '{module_name}': {e}")
    return None

def main():
    """
    Main function to orchestrate the demo components.
    """
    print_header("HPE AI-Driven Predictive Maintenance Demo Runner")

    # Get the project root directory (assuming this script is in the project root)
    project_root = os.path.dirname(os.path.abspath(__file__))
    print(f"INFO: Project root directory: {project_root}")
    print(f"INFO: Make sure your virtual environment is activated and all dependencies from requirements.txt are installed.")
    print(f"INFO: Ensure 'config/demo_config.yaml' is correctly set up, especially ServiceNow details if testing that part.")

    pcai_process = None
    edge_process = None

    try:
        # 1. Start the PCAI Agent Application (Flask Server)
        print(f"\n--- Starting PCAI Agent Application ({PCAI_APP_MODULE}) ---")
        print("This will start the Flask server. Output from the PCAI app will appear below.")
        pcai_process = run_module_in_subprocess(PCAI_APP_MODULE, cwd=project_root)
        if not pcai_process:
            print("CRITICAL: Failed to start PCAI Agent Application. Exiting.")
            return

        print(f"\nINFO: Waiting {SERVER_START_DELAY_SECONDS} seconds for the PCAI server to initialize...")
        time.sleep(SERVER_START_DELAY_SECONDS)

        # 2. Start the Edge Simulator (which also drives the IoT Sensor)
        print(f"\n--- Starting Edge & IoT Sensor Simulator ({EDGE_SIMULATOR_MODULE}) ---")
        print("This will start generating sensor data and processing it at the edge.")
        print("The edge simulator will attempt to send triggers to the PCAI application.")
        edge_process = run_module_in_subprocess(EDGE_SIMULATOR_MODULE, cwd=project_root)
        if not edge_process:
            print("CRITICAL: Failed to start Edge Simulator. The PCAI App might still be running.")
            # Optionally terminate pcai_process here if edge fails to start
            # if pcai_process:
            #     print("Terminating PCAI App...")
            #     pcai_process.terminate()
            #     pcai_process.wait(timeout=5)
            return

        print("\n--- Demo Components Running ---")
        print("Outputs from both applications will be interleaved in this console.")
        print(f"PCAI App (Flask) PID: {pcai_process.pid if pcai_process else 'N/A'}")
        print(f"Edge Simulator PID: {edge_process.pid if edge_process else 'N/A'}")
        print("\nPress Ctrl+C to stop all demo components.")

        # Wait for the edge simulator process to complete
        # The current edge_simulator runs for a fixed 20 cycles.
        if edge_process:
            edge_process.wait() # Wait for this process to finish
            print("\nINFO: Edge & IoT Sensor Simulator has completed its run.")
            if edge_process.returncode != 0:
                print(f"WARN: Edge Simulator exited with code {edge_process.returncode}")

        # After edge completes, PCAI app is still running.
        # User can Ctrl+C to stop it, or we can prompt for it.
        print("\nINFO: The PCAI Agent Application (Flask server) is still running.")
        print("Press Ctrl+C to stop the PCAI Application and exit the runner.")
        while pcai_process and pcai_process.poll() is None: # Keep alive until Ctrl+C
            time.sleep(1)


    except KeyboardInterrupt:
        print("\nINFO: Ctrl+C received. Shutting down demo components...")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred in the demo runner: {e}")
    finally:
        print("\n--- Cleaning up ---")
        if edge_process and edge_process.poll() is None: # If edge is somehow still running
            print(f"INFO: Terminating Edge Simulator (PID: {edge_process.pid})...")
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5) # Wait for graceful termination
            except subprocess.TimeoutExpired:
                print(f"WARN: Edge Simulator (PID: {edge_process.pid}) did not terminate gracefully, killing.")
                edge_process.kill()
            print("INFO: Edge Simulator terminated.")

        if pcai_process and pcai_process.poll() is None:
            print(f"INFO: Terminating PCAI Agent Application (PID: {pcai_process.pid})...")
            pcai_process.terminate()
            try:
                pcai_process.wait(timeout=5) # Wait for graceful termination
            except subprocess.TimeoutExpired:
                print(f"WARN: PCAI App (PID: {pcai_process.pid}) did not terminate gracefully, killing.")
                pcai_process.kill()
            print("INFO: PCAI Agent Application terminated.")
        
        print("\nDemo Runner finished.")

if __name__ == "__main__":
    main()