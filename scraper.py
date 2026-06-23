import os
import re
import json
import requests
import pdfplumber
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

PDF_URL = "https://tnebsldc.org/reports1/peakdet.pdf"
LOCAL_PDF = "peakdet.pdf"

def clean_num(val):
    if not val: 
        return None
    # Take only the first line if cells were merged by pdfplumber
    val = str(val).split('\n')[0]
    # Remove any non-numeric characters except dot and minus
    val = re.sub(r'[^\d\.\-]', '', str(val))
    # Some numbers in the PDF might be parsed with multiple dots due to OCR/extraction glitches
    if val.count('.') > 1:
        parts = val.split('.')
        val = parts[0] + '.' + ''.join(parts[1:])
    try:
        return float(val) if val else None
    except ValueError:
        return None

def download_pdf():
    print(f"Downloading {PDF_URL}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    response = requests.get(PDF_URL, headers=headers, timeout=30, verify=False)
    response.raise_for_status()
    with open(LOCAL_PDF, "wb") as f:
        f.write(response.content)
    print("Download complete.")

def parse_pdf():
    print("Parsing PDF...")
    data = {"top_level": {}, "generation": []}
    
    with pdfplumber.open(LOCAL_PDF) as pdf:
        page = pdf.pages[0]
        text = page.extract_text()
        
        # Extract Date (e.g. "Date : 23-Jun-26")
        date_match = re.search(r"Date\s*:\s*(\d{2}-[A-Za-z]{3}-\d{2})", text)
        if date_match:
            date_str = date_match.group(1)
            # convert to YYYY-MM-DD
            parsed_date = datetime.strptime(date_str, "%d-%b-%y").date()
            data["top_level"]["report_date"] = parsed_date
        else:
            # Fallback to today if not found, though we should prefer the PDF's date
            print("Warning: Could not find the report date in the PDF text. Using current date.")
            data["top_level"]["report_date"] = datetime.now().date()
            
        tables = page.extract_tables()
        if not tables:
            raise ValueError("No tables found in the PDF.")
            
        table = tables[0]
        
        for row in table:
            # Clean row of None
            clean_row = [str(cell).strip() if cell else "" for cell in row]
            
            # Ensure row has enough columns
            while len(clean_row) < 8:
                clean_row.append("")
                
            row_text = " ".join(clean_row).lower()
            
            # Identify frequency row
            if "frequency hz" in row_text:
                data["top_level"]["frequency_hz"] = clean_num(clean_row[4])
            
            # Identify "Total" row (the one before Load Shedding usually)
            if clean_row[2] == "Total":
                data["top_level"]["total_capacity_mw"] = clean_num(clean_row[3])
                data["top_level"]["total_lighting_peak_mw"] = clean_num(clean_row[4])
                data["top_level"]["total_minimum_load_mw"] = clean_num(clean_row[5])
                data["top_level"]["total_morning_peak_mw"] = clean_num(clean_row[6])
                data["top_level"]["total_consumption_mu"] = clean_num(clean_row[7])

            # Now, for generation details, collect rows with numerical data
            # Combine col 1 and 2 if 2 is empty but 1 is an index or partial name
            cat_name = clean_row[2]
            if not cat_name and clean_row[1]: 
                cat_name = clean_row[1]
                
            # Clean up newlines in category name
            cat_name = cat_name.replace("\n", " ").strip()
            
            ignore_list = ["details", "time hrs.", "frequency hz.", "total", "load shedding", "ht relief & r&c", "date", "demand"]
            
            if cat_name and cat_name.lower() not in ignore_list and "all time high" not in cat_name.lower():
                cap = clean_num(clean_row[3])
                lp = clean_num(clean_row[4])
                ml = clean_num(clean_row[5])
                mp = clean_num(clean_row[6])
                cons = clean_num(clean_row[7])
                
                # Only append if at least one metric is present
                if any(x is not None for x in [cap, lp, ml, mp, cons]):
                    data["generation"].append({
                        "category": cat_name,
                        "capacity_mw": cap,
                        "lighting_peak_mw": lp,
                        "minimum_load_mw": ml,
                        "morning_peak_mw": mp,
                        "consumption_mu": cons
                    })
                            
    return data

def save_to_db(data):
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found. Skipping DB insertion.")
        return
        
    print("Connecting to DB...")
    # Add sslmode=require for Neon/Supabase if not present
    if "?" not in db_url and "localhost" not in db_url:
        db_url += "?sslmode=require"
    elif "sslmode" not in db_url and "localhost" not in db_url:
        db_url += "&sslmode=require"
        
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    
    report_date = data["top_level"]["report_date"]
    
    # Upsert daily_reports
    print(f"Upserting top level data for {report_date}")
    cursor.execute("""
        INSERT INTO daily_reports (
            report_date, frequency_hz, total_capacity_mw, total_lighting_peak_mw, 
            total_minimum_load_mw, total_morning_peak_mw, total_consumption_mu
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (report_date) DO UPDATE SET
            frequency_hz = EXCLUDED.frequency_hz,
            total_capacity_mw = EXCLUDED.total_capacity_mw,
            total_lighting_peak_mw = EXCLUDED.total_lighting_peak_mw,
            total_minimum_load_mw = EXCLUDED.total_minimum_load_mw,
            total_morning_peak_mw = EXCLUDED.total_morning_peak_mw,
            total_consumption_mu = EXCLUDED.total_consumption_mu
    """, (
        report_date,
        data["top_level"].get("frequency_hz"),
        data["top_level"].get("total_capacity_mw"),
        data["top_level"].get("total_lighting_peak_mw"),
        data["top_level"].get("total_minimum_load_mw"),
        data["top_level"].get("total_morning_peak_mw"),
        data["top_level"].get("total_consumption_mu")
    ))
    
    # Upsert generation_details
    print(f"Upserting {len(data['generation'])} generation records...")
    insert_query = """
        INSERT INTO generation_details (
            report_date, category, capacity_mw, lighting_peak_mw, 
            minimum_load_mw, morning_peak_mw, consumption_mu
        ) VALUES %s
        ON CONFLICT (report_date, category) DO UPDATE SET
            capacity_mw = EXCLUDED.capacity_mw,
            lighting_peak_mw = EXCLUDED.lighting_peak_mw,
            minimum_load_mw = EXCLUDED.minimum_load_mw,
            morning_peak_mw = EXCLUDED.morning_peak_mw,
            consumption_mu = EXCLUDED.consumption_mu
    """
    
    gen_data = data["generation"]
    values = [
        (
            report_date,
            g["category"],
            g["capacity_mw"],
            g["lighting_peak_mw"],
            g["minimum_load_mw"],
            g["morning_peak_mw"],
            g["consumption_mu"]
        ) for g in gen_data
    ]
    
    execute_values(cursor, insert_query, values)
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Data saved successfully.")

if __name__ == "__main__":
    download_pdf()
    parsed_data = parse_pdf()
    print("--- Extracted Data ---")
    print(json.dumps(parsed_data, indent=2, default=str))
    print("----------------------")
    save_to_db(parsed_data)
