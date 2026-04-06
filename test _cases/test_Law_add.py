from pathlib import Path
import sys

sys.path.append('.')

from import_classified import import_classified_results

# Path to your JSON file
json_path = Path("doc_processing_results/A_Digest_of_the_General_Laws_of_Kentucky-1866_results_classified.json")

# Run import ONLY ONCE
print("Starting single import...")
import_classified_results(json_path)
print("Import complete!")