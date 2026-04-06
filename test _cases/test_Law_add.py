from pathlib import Path
import sys
import json

# Add the current directory to path so we can import import_classified
sys.path.append('.')

# Import the function from your existing module
from import_classified import import_classified_results

# Path to your JSON file
json_path = Path("doc_processing_results/A_Digest_of_the_General_Laws_of_Kentucky-1866_results_classified.json")

# Run the import
print(f"Importing from: {json_path}")
import_classified_results(json_path)
print("Import complete!")