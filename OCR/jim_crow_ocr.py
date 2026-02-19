import os
from pathlib import Path
from dotenv import load_dotenv
from llama_parse import LlamaParse
from typing import List, Dict
import json
import tkinter as tk
from tkinter import filedialog

load_dotenv(Path(__file__).parent.parent / ".env")

def select_pdf():
    root = tk.Tk()
    root.withdraw() # Hide the main window
    file_path = filedialog.askopenfilename(
        title="Select a PDF file",
        filetypes=[("PDF files", "*.pdf")]
    )
    return file_path

class JimCrowOCR:
    def __init__(self, api_key: str):
        self.parser = LlamaParse(
            api_key=api_key,
            result_type="markdown", # Can also use other format
            verbose=True,
            language="en"
        )

    # Parse single pdf file and extract text
    def parse_pdf(self, pdf_path: str) -> str:
        print(f"Processing: {pdf_path}") # For testing can be removed later on
        
        try:
            # Parse the document
            documents = self.parser.load_data(pdf_path)

            # Combine all pages into a single text -- can be changed later during code refining
            full_text = "\n".join([doc.text for doc in documents]) 

            return full_text
        except Exception as e:
            print(f"Error parsing {pdf_path}: {str(e)}")
            return ""
    
    # For batch parsing
    def parse_multiple_pdfs(self, pdf_paths: List[str]) -> Dict[str, str]:
        results = {}

        for pdf_path in pdf_paths:
            filename = os.path.basename(pdf_path)
            text = self.parse_pdf(pdf_path)
            results[filename] = text

        return results
    
    def find_jim_crow_references(self, text: str) -> List[str]:
        # Need more keywords to be added later on
        keywords = [
            "jim crow",
            "segregation",
            "separate but equal",
            "colored",
            "negro",
            "white only",
            "colored only",
            "racial discrimination",
            "miscegenation",
            "poll tax",
            "literacy test",
            "grandfather clause"
        ]

        matches = []
        lines = text.split("\n")

        for i, line in enumerate(lines):
            line_lower = line.lower()
            for keyword in keywords:
                if keyword in line_lower:
                    # Get lines around the key word
                    start = max(0, i - 2) # 2 lines before
                    end = min(len(lines), i + 3) # 2 lines after
                    context = "\n".join(lines[start:end])
                    matches.append({
                        "keyword": keyword,
                        "context": context,
                        "line_number": i + 1
                    })
                    break # Avoid duplicate matches for same line
        return matches
    
    def save_results(self, results: Dict, output_path: str):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"results saved to {output_path}") # Can be commented out later
    

def main():
    API_KEY = os.getenv("LLAMA_API_KEY") # Set up api key in the .env file

    if not API_KEY:
        print("LLAMA_API_KEY not found in environment variables.")
        return
    
    # Initialize OCR
    ocr = JimCrowOCR(api_key=API_KEY)

    # select pdf from file
    print("Please select a pdf file")
    pdf_path = select_pdf()

    if not pdf_path:
        print("No file selected. Exiting.")
        return
    
    if os.path.exists(pdf_path):
        # Extract text from pdf and find references to Jim Crow
        extracted_text = ocr.parse_pdf(pdf_path)
        references = ocr.find_jim_crow_references(extracted_text)

        # Prepare results
        results = {
            "filename" : os.path.basename(pdf_path),
            "full_text": extracted_text,
            "jim_crow_references": references,
            "reference_count": len(references)
        }

        # Save result to ocr_results/
        out_dir = Path(__file__).parent.parent / "ocr_results"
        out_dir.mkdir(exist_ok=True)
        output_filename = str(out_dir / f"{os.path.splitext(os.path.basename(pdf_path))[0]}_results.json")
        ocr.save_results(results, output_filename)

        # Print summary
        print("Extraction complete!")
        print(f"Found {len(references)} references to Jim Crow in {pdf_path}")
    else:
        print(f"PDF file not found: {pdf_path}")

if __name__ == "__main__":    
    main()