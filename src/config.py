"""Configuration module for AI Accident Intelligence.
Defines directory paths, categories, and application constants.
Updated for OB_PO forms (1-4) and Work Instructions (WI).
"""

from pathlib import Path

# Base directories - auto-detect project root dynamically (works on Windows, Linux, Streamlit Cloud)
BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = BASE_DIR / "documents"
DATABASE_DIR = BASE_DIR / "database"
DB_PATH = DATABASE_DIR / "accident_intel.db"
BACKUP_DIR = DATABASE_DIR / "backups"
OUTPUT_DIR = BASE_DIR / "output"

# Ensure essential directories exist
for path in [DATABASE_DIR, BACKUP_DIR, OUTPUT_DIR, DOCUMENTS_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# Document categories and Thai descriptive names
CATEGORY_MAP = {
    "OB_PO_1_2": "อบ.ปอ. 1-2 (คนบาดเจ็บ และ ทรัพย์สินเสียหาย)",
    "OB_PO_3": "อบ.ปอ. 3 (อุบัติเหตุทางถนน / รถเฉี่ยวชน)",
    "OB_PO_4": "อบ.ปอ. 4 (ประชาชน / บุคคลภายนอกได้รับบาดเจ็บ)",
    "Accidents_Personnel": "อุบัติเหตุบุคคล (Personnel Accidents)",
    "Accidents_Road": "อุบัติเหตุทางถนน (Road & Traffic Accidents)",
    "WI": "WI (คู่มือขั้นตอนการปฏิบัติงานด้านความปลอดภัย)",
    "New_Incidents": "รายงานอุบัติเหตุเคสใหม่ (New Incidents)",
    "Work_Permit": "ใบอนุญาตทำงาน (Work Permit)",
    "Other": "เอกสารความปลอดภัยอื่นๆ (Other Documents)",
}

# Subfolder names mapped to standard category keys
FOLDER_TO_CATEGORY = {
    "ob_po_1_2": "OB_PO_1_2",
    "ob_po_3": "OB_PO_3",
    "ob_po_4": "OB_PO_4",
    "accidents_personnel": "Accidents_Personnel",
    "accidents_road": "Accidents_Road",
    "wi": "WI",
    "new_incidents": "New_Incidents",
    "work_permit": "Work_Permit",
    "other": "Other",
}

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf"}
