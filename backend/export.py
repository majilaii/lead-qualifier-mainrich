"""
Export Utilities

Convert output CSVs into shareable formats:
  - Excel (.xlsx) with separate sheets for Hot / Review / Rejected
  - Google Sheets (requires service account credentials)
  - Watch mode: auto-sync when files change

Usage:
  python export.py excel    # Export to Excel
  python export.py sheets   # Upload to Google Sheets
  python export.py watch    # Auto-sync on changes
"""

import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def export_to_excel(output_path: Optional[Path] = None):
    """
    Combine all CSV outputs into a single Excel file with multiple sheets.
    
    Args:
        output_path: Path for the Excel file. Defaults to output/leads_YYYY-MM-DD.xlsx
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        output_path = OUTPUT_DIR / f"leads_{timestamp}.xlsx"
    
    # Read all CSV files
    files = {
        "🔥 Hot Leads": OUTPUT_DIR / "qualified_hot_leads.csv",
        "🔍 Review": OUTPUT_DIR / "review_manual_check.csv",
        "❌ Rejected": OUTPUT_DIR / "rejected_with_reasons.csv",
    }
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        any_data = False
        for sheet_name, csv_path in files.items():
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                if not df.empty:
                    any_data = True
                    # Write whatever columns the CSV actually has
                    df.to_excel(writer, sheet_name=sheet_name[:31], index=False)  # Excel sheet name limit

        if not any_data:
            logger.warning("No CSV data found to export")
            return None
    
    logger.info("Exported to: %s", output_path)
    return output_path


def export_to_google_sheets(spreadsheet_name: str = "Lead Qualifier Results"):
    """
    Export results to Google Sheets.
    
    Requires:
    1. Create a Google Cloud project
    2. Enable Google Sheets API
    3. Create a service account and download credentials.json
    4. Share the spreadsheet with the service account email
    
    Args:
        spreadsheet_name: Name of the Google Sheet to create/update
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error("Install: pip install gspread google-auth")
        return
    
    # Look for credentials file
    creds_path = Path("credentials.json")
    if not creds_path.exists():
        creds_path = Path.home() / ".config" / "gspread" / "credentials.json"
    
    if not creds_path.exists():
        logger.error(
            "Google credentials not found! "
            "Setup steps: 1) Go to https://console.cloud.google.com/ "
            "2) Create a project 3) Enable 'Google Sheets API' "
            "4) Create Service Account credentials 5) Download JSON key "
            "6) Save as 'credentials.json' 7) Share sheet with service account email"
        )
        return
    
    # Authenticate
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(creds)
    
    # Try to open existing or create new
    try:
        sheet = client.open(spreadsheet_name)
        logger.info("Updating existing sheet: %s", spreadsheet_name)
    except gspread.SpreadsheetNotFound:
        sheet = client.create(spreadsheet_name)
        logger.info("Created new sheet: %s", spreadsheet_name)
    
    # Upload each tier
    files = {
        "Hot Leads": OUTPUT_DIR / "qualified_hot_leads.csv",
        "Review": OUTPUT_DIR / "review_manual_check.csv",
        "Rejected": OUTPUT_DIR / "rejected_with_reasons.csv",
    }
    
    for sheet_name, csv_path in files.items():
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            if not df.empty:
                # Get or create worksheet
                try:
                    worksheet = sheet.worksheet(sheet_name)
                    worksheet.clear()
                except gspread.WorksheetNotFound:
                    worksheet = sheet.add_worksheet(sheet_name, rows=1000, cols=20)
                
                # Upload data
                worksheet.update([df.columns.tolist()] + df.values.tolist())
    
    logger.info("Uploaded to Google Sheets!")
    logger.info("URL: %s", sheet.url)
    return sheet.url


def watch_and_sync(interval_seconds: int = 60, target: str = "excel"):
    """
    Watch for changes and auto-export.
    
    Args:
        interval_seconds: Polling interval
        target: 'excel' or 'sheets'
    """
    import time
    
    export_fn = export_to_excel if target == "excel" else export_to_google_sheets
    logger.info("Watching for changes every %ds -> %s", interval_seconds, target)
    logger.info("Press Ctrl+C to stop")
    
    last_modified: dict[Path, float] = {}
    
    while True:
        try:
            files = list(OUTPUT_DIR.glob("*.csv"))
            changed = False
            
            for f in files:
                mtime = f.stat().st_mtime
                if f not in last_modified or last_modified[f] != mtime:
                    last_modified[f] = mtime
                    changed = True
                    logger.info("Change detected: %s", f.name)
            
            if changed:
                try:
                    export_fn()
                except Exception as e:
                    logger.warning("Export failed: %s", e)
            
            time.sleep(interval_seconds)
            
        except KeyboardInterrupt:
            logger.info("Stopped watching")
            break


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "excel":
            export_to_excel()
        elif sys.argv[1] == "sheets":
            export_to_google_sheets()
        elif sys.argv[1] == "watch":
            watch_and_sync()
    else:
        print("""
Export Utilities for Lead Qualifier

Usage:
    python export.py excel    # Export to Excel file
    python export.py sheets   # Export to Google Sheets
    python export.py watch    # Watch for changes
""")
