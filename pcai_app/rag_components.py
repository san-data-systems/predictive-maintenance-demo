# pcai_app/rag_components.py

import os
import re
import logging

logger = logging.getLogger(__name__)

class RAGSystem:
    """
    A simplified Retrieval Augmented Generation system.
    It loads text files from a knowledge base and performs basic keyword searches.
    """
    def __init__(self, knowledge_base_path: str):
        self.knowledge_base_path = knowledge_base_path
        self.kb_data = {} # To store content of loaded files: {'filename': 'content'}
        self._load_knowledge_base()
        logger.info(f"RAGSystem initialized. Knowledge base path: {self.knowledge_base_path}")

    def _load_knowledge_base(self):
        """
        Loads all .txt files from the specified knowledge base directory.
        Includes fallback for local execution vs. container execution.
        """
        effective_path = self.knowledge_base_path
        if not os.path.exists(effective_path):
            # If the absolute container path doesn't exist, try a relative path for local runs
            logger.info(f"Path {effective_path} not found. Trying relative path for local execution.")
            # Assumes the script is run from the project root
            relative_path = os.path.join(os.getcwd(), 'knowledge_base_files')
            if os.path.exists(relative_path):
                effective_path = relative_path
            else:
                logger.error(f"CRITICAL: Knowledge base path does not exist at '{self.knowledge_base_path}' or relative path '{relative_path}'")
                return

        loaded_files_count = 0
        for filename in os.listdir(effective_path):
            if filename.endswith(".txt"):
                file_path = os.path.join(effective_path, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.kb_data[filename] = f.read()
                    loaded_files_count +=1
                    logger.info(f"RAGSystem loaded: {filename}")
                except Exception as e:
                    logger.error(f"RAGSystem failed to load {filename}: {e}")
        if loaded_files_count == 0:
            logger.warning(f"RAGSystem found no .txt files in {effective_path}")


    def query_knowledge_base(self, asset_id: str, live_sensor_data: dict, search_terms: list) -> list:
        """
        Searches the loaded knowledge base for lines containing any of the search terms.
        Also considers specific patterns from live_sensor_data as per demo plan.
        """
        found_snippets = []
        logger.info(f"RAG Query for Asset {asset_id} with terms: {search_terms}")
        logger.info(f"RAG Live Sensor Data Context: {live_sensor_data}")

        # Basic keyword search across all content
        for term in search_terms:
            term_regex = re.compile(re.escape(term), re.IGNORECASE)
            for filename, content in self.kb_data.items():
                for line_num, line in enumerate(content.splitlines()):
                    if term_regex.search(line):
                        snippet = f"{filename}:L{line_num+1}: {line.strip()}"
                        if snippet not in found_snippets:
                            found_snippets.append(snippet)
        
        # Enhanced contextual search based on sensor data patterns (aligns with demo narrative)
        vib_anomaly_freq = live_sensor_data.get("vibration_anomaly_signature_freq_hz")
        
        # Contextual Search Block 1: High-frequency vibrations & gear tooth pitting (115-125Hz)
        if vib_anomaly_freq and 115 <= vib_anomaly_freq <= 125: # Range covers 121.38Hz
            for filename, content in self.kb_data.items():
                # Check for "gear tooth pitting" in the whole file first for efficiency
                if re.search(r"gear tooth pitting", content, re.IGNORECASE):
                    for line_num, line in enumerate(content.splitlines()):
                        if "115-125Hz" in line and "gear tooth pitting" in line:
                            snippet = f"{filename}:L{line_num+1}: {line.strip()} (Context: Matched {vib_anomaly_freq}Hz)"
                            if snippet not in found_snippets: found_snippets.append(snippet)
                            break # Found relevant line in this file, move to next file

        # Contextual Search Block 2: 120Hz spikes and bearing assembly failure (widened range for 121.38Hz)
        # Assuming "120Hz" in KB snippet implies ~115-125Hz contextually
        if vib_anomaly_freq and 115 <= vib_anomaly_freq <= 125: # Widened range to catch 121.38Hz
            for filename, content in self.kb_data.items():
                if re.search(r"(G-5432|bearing assembly failure)", content, re.IGNORECASE):
                    for line_num, line in enumerate(content.splitlines()):
                        # Checking for "120Hz" as a literal string in the line itself, along with parts/failure.
                        if "120Hz" in line and ("G-5432" in line or "bearing assembly failure" in line):
                            snippet = f"{filename}:L{line_num+1}: {line.strip()} (Context: Matched {vib_anomaly_freq}Hz)"
                            if snippet not in found_snippets: found_snippets.append(snippet)
                            break # Found relevant line in this file, move to next file

        # Contextual Search Block 3: Oil temperature correlation (widened range for 121.38Hz and temp increase)
        temp_increase_c = live_sensor_data.get("temperature_increase_c", 0)
        if vib_anomaly_freq and 115 <= vib_anomaly_freq <= 125 and temp_increase_c > 4.5: # Widened freq range, checks temp increase
            for filename, content in self.kb_data.items():
                if re.search(r"rise >5°C|accelerated wear", content, re.IGNORECASE):
                    for line_num, line in enumerate(content.splitlines()):
                        if "GRX-II" in line and "oil temperature" in line and "rise >5°C" in line:
                            snippet = f"{filename}:L{line_num+1}: {line.strip()} (Context: Matched {vib_anomaly_freq}Hz & {temp_increase_c}°C rise)"
                            if snippet not in found_snippets: found_snippets.append(snippet)
                            break # Found relevant line in this file, move to next file
        
        if not found_snippets:
            logger.info("RAGSystem found no direct matches for the query.")
            return ["No specific KB articles found matching the immediate query criteria."]
        
        return found_snippets