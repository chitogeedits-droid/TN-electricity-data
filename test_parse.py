import pdfplumber
import json

pdf_path = 'peakdet.pdf'

with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    # Extract text to see raw format
    text = page.extract_text()
    
    # Extract table
    tables = page.extract_tables()

with open('output.txt', 'w', encoding='utf-8') as f:
    f.write("--- TEXT ---\n")
    f.write(text or "")
    f.write("\n\n--- TABLES ---\n")
    f.write(json.dumps(tables, indent=2))
