"""PDF Extraction and Cryptographic Hash Module.
Strictly Read-Only access to original files. Never alters or removes source PDFs.
Uses PyMuPDF (fitz) for fast, reliable local text extraction.
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.error("PyMuPDF (fitz) is not installed. PDF extraction will fail.")


def compute_sha256(filepath: str | Path) -> str:
    """Computes SHA-256 hash of a file in streaming chunks (Read-Only).
    
    Args:
        filepath: Path to the target file.
        
    Returns:
        Hexadecimal SHA-256 hash string.
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    hasher = hashlib.sha256()
    # Read-only binary mode with 64KB chunk size for low memory footprint
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
            
    return hasher.hexdigest()


def extract_pdf_data(filepath: str | Path) -> Dict[str, Any]:
    """Extracts text and page-by-page information from a PDF file.
    
    Ensures safe, read-only extraction without modifying the original document.
    
    Args:
        filepath: Path to the PDF file.
        
    Returns:
        Dictionary containing:
            - total_pages: Total number of pages
            - pages: List of dicts { page_number, raw_text, char_count }
            - file_size: Size in bytes
            - error: Error string if any, otherwise None
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF (fitz) is required but not installed.")

    path = Path(filepath)
    if not path.is_file():
        return {
            "total_pages": 0,
            "pages": [],
            "file_size": 0,
            "error": f"File not found: {path}"
        }

    file_size = path.stat().st_size
    pages_data: List[Dict[str, Any]] = []

    try:
        # Open PDF in read-only mode using PyMuPDF
        with fitz.open(str(path)) as doc:
            total_pages = len(doc)
            for page_idx in range(total_pages):
                page = doc[page_idx]
                page_num = page_idx + 1
                raw_text = page.get_text("text") or ""
                
                pages_data.append({
                    "page_number": page_num,
                    "raw_text": raw_text.strip(),
                    "char_count": len(raw_text.strip())
                })
                
        return {
            "total_pages": total_pages,
            "pages": pages_data,
            "file_size": file_size,
            "error": None
        }

    except Exception as e:
        logger.error(f"Failed to read PDF {path}: {e}")
        return {
            "total_pages": 0,
            "pages": [],
            "file_size": file_size,
            "error": str(e)
        }
