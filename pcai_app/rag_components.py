# pcai_app/rag_components.py

import os
import re # For simple keyword matching

class RAGSystem:
    """
    A simplified Retrieval Augmented Generation system.
    It loads text files from a knowledge base and performs basic keyword searches.
    """
    def __init__(self, knowledge_base_path: str):
        self.knowledge_base_path = knowledge_base_path
        self.kb_data = {} # To store content of loaded files: {'filename': 'content'}
        self._load_knowledge_base()
        print(f"INFO: RAGSystem initialized. Knowledge base path: {self.knowledge_base_path}")

    def _load_knowledge_base(self):
        """
        Loads all .txt files from the specified knowledge base directory.
        """
        if not os.path.exists(self.knowledge_base_path):
            print(f"ERROR: Knowledge base path does not exist: {self.knowledge_base_path}")
            return

        loaded_files_count = 0
        for filename in os.listdir(self.knowledge_base_path):
            if filename.endswith(".txt"):
                file_path = os.path.join(self.knowledge_base_path, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.kb_data[filename] = f.read()
                    loaded_files_count +=1
                    print(f"INFO: RAGSystem loaded: {filename}")
                except Exception as e:
                    print(f"ERROR: RAGSystem failed to load {filename}: {e}")
        if loaded_files_count == 0:
             print(f"WARN: RAGSystem found no .txt files in {self.knowledge_base_path}")


    def query_knowledge_base(self, asset_id: str, live_sensor_data: dict, search_terms: list) -> list:
        """
        Searches the loaded knowledge base for lines containing any of the search terms.
        Also considers specific patterns from live_sensor_data as per demo plan.

        Returns a list of formatted strings like: "Source_File.txt: Relevant line content..."
        """
        found_snippets = []
        print(f"INFO: RAG Query for Asset {asset_id} with terms: {search_terms}")
        print(f"INFO: RAG Live Sensor Data Context: {live_sensor_data}")

        # --- Part 1: General search terms ---
        for term in search_terms:
            term_regex = re.compile(re.escape(term), re.IGNORECASE) # Case-insensitive search
            for filename, content in self.kb_data.items():
                for line_num, line in enumerate(content.splitlines()):
                    if term_regex.search(line):
                        snippet = f"{filename}:L{line_num+1}: {line.strip()}"
                        if snippet not in found_snippets: # Avoid duplicates from multiple terms on same line
                            found_snippets.append(snippet)
                            print(f"DEBUG: RAG found snippet for '{term}': {snippet}")
        
        # --- Part 2: Demo-specific "intelligent" lookups based on sensor data patterns ---
        # These simulate the AI finding highly relevant information based on specific data triggers.

        # Example: "High-frequency vibrations (115-125Hz)... gear tooth pitting."
        vib_anomaly_freq = live_sensor_data.get("vibration_anomaly_signature_freq_hz")
        if vib_anomaly_freq and 115 <= vib_anomaly_freq <= 125:
            for filename, content in self.kb_data.items():
                # Looking for a line that mentions both "115-125Hz" (or similar) AND "gear tooth pitting"
                if re.search(r"(115-125hz|high-frequency vibrations)", content, re.IGNORECASE) and \
                   re.search(r"gear tooth pitting", content, re.IGNORECASE):
                    # Find the specific line for demo purposes
                    for line_num, line in enumerate(content.splitlines()):
                         if "115-125Hz" in line and "gear tooth pitting" in line: # Be more specific for demo visual
                            snippet = f"{filename}:L{line_num+1}: {line.strip()} (Context: Matched {vib_anomaly_freq}Hz)"
                            if snippet not in found_snippets: found_snippets.append(snippet)
                            print(f"DEBUG: RAG demo-specific find (gear pitting rule): {snippet}")
                            break # Found for this file

        # Example: "Similar acoustic signature at 120Hz recorded ... P/N G-5432 bearing assembly failure."
        # This would require more complex acoustic signature matching. For sim, let's assume if anomaly freq is ~120Hz.
        if vib_anomaly_freq and 118 <= vib_anomaly_freq <= 122: # if ~120Hz vibration is the key
            for filename, content in self.kb_data.items():
                if re.search(r"(120hz|acoustic signature).*?(G-5432|bearing assembly failure)", content, re.IGNORECASE | re.DOTALL):
                    for line_num, line in enumerate(content.splitlines()):
                        if "120Hz" in line and ("G-5432" in line or "bearing assembly failure" in line):
                            snippet = f"{filename}:L{line_num+1}: {line.strip()} (Context: Matched {vib_anomaly_freq}Hz)"
                            if snippet not in found_snippets: found_snippets.append(snippet)
                            print(f"DEBUG: RAG demo-specific find (120Hz bearing rule): {snippet}")
                            break

        # Example: "Correlate 120Hz vibration spikes with oil temperature. A rise >5°C suggests accelerated wear."
        temp_c = live_sensor_data.get("temperature_c")
        # Assuming we can get a baseline temp from somewhere or calculate increase.
        # For now, let's say if temp itself is high and vibration is ~120Hz
        # A proper implementation would need base_temp + current_temp_increase_c from sensor_data
        # For now, we'll simulate this condition by looking for a temp field.
        # Let's assume 'temperature_increase_c' is passed in live_sensor_data if available
        temp_increase_c = live_sensor_data.get("temperature_increase_c", 0) # Need to ensure sensor sim provides this

        if vib_anomaly_freq and 118 <= vib_anomaly_freq <= 122 and temp_increase_c > 4.5: # Demo says >5°C, using 4.5 to catch 5-6°C
            for filename, content in self.kb_data.items():
                if re.search(r"(GRX-II|120hz vibration spikes).*(oil temperature).*(rise >5°C|accelerated wear)", content, re.IGNORECASE | re.DOTALL):
                     for line_num, line in enumerate(content.splitlines()):
                        if "GRX-II" in line and "oil temperature" in line and "rise >5°C" in line:
                            snippet = f"{filename}:L{line_num+1}: {line.strip()} (Context: Matched {vib_anomaly_freq}Hz & {temp_increase_c}°C rise)"
                            if snippet not in found_snippets: found_snippets.append(snippet)
                            print(f"DEBUG: RAG demo-specific find (temp correlation rule): {snippet}")
                            break
        
        if not found_snippets:
            print(f"INFO: RAGSystem found no direct matches for {search_terms} or specific demo patterns.")
        
        return found_snippets if found_snippets else ["No specific KB articles found matching the immediate query criteria."]