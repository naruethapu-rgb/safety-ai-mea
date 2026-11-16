"""Database management module for AI Accident Intelligence.
Implements SQLite schema with FTS5, document sync, deduplication, 
search, and live online backup.
"""

import os
import sqlite3
import datetime
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from src.config import DB_PATH, BACKUP_DIR, DOCUMENTS_DIR, CATEGORY_MAP, FOLDER_TO_CATEGORY, SUPPORTED_EXTENSIONS
from src.pdf_parser import compute_sha256, extract_pdf_data
from src.thai_indexer import tokenize_for_fts, prepare_search_query

logger = logging.getLogger(__name__)


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Creates a connection to the SQLite database with Foreign Keys enabled."""
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    """Initializes the database schema and FTS5 virtual tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        # Files metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                category TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                total_pages INTEGER NOT NULL,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );
        """)

        # Indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_active ON files(is_active);")

        # Document pages table (stores raw, unmodified page text)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                raw_text TEXT NOT NULL,
                char_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES files (id) ON DELETE CASCADE,
                UNIQUE(file_id, page_number)
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pages_file ON document_pages(file_id);")

        # FTS5 Virtual Table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
                page_id UNINDEXED,
                file_id UNINDEXED,
                filename,
                category,
                tokenized_content
            );
        """)

        conn.commit()
        logger.info("Database initialized successfully at %s", db_path)
    finally:
        conn.close()


def determine_category(relative_path: Path) -> str:
    """Determines document category from folder structure."""
    parts = [p.lower() for p in relative_path.parts[:-1]]
    for part in parts:
        if part in FOLDER_TO_CATEGORY:
            return FOLDER_TO_CATEGORY[part]
    return "Other"


def backup_database(db_path: Path = DB_PATH, backup_dir: Path = BACKUP_DIR) -> str:
    """Performs a live online backup of the SQLite database.
    
    Safe to execute while users or indexing jobs are running.
    
    Returns:
        Path string of the newly created backup file.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database does not exist at {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"accident_intel_backup_{timestamp}.db"

    source_conn = get_connection(db_path)
    dest_conn = get_connection(backup_file)
    try:
        source_conn.backup(dest_conn)
    finally:
        source_conn.close()
        dest_conn.close()

    logger.info("Backup successfully created at %s", backup_file)
    return str(backup_file)


def list_backups(backup_dir: Path = BACKUP_DIR) -> List[Dict[str, Any]]:
    """Lists existing database backup files with size and creation time."""
    if not backup_dir.exists():
        return []

    backups = []
    for file in sorted(backup_dir.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True):
        stat = file.stat()
        backups.append({
            "filename": file.name,
            "filepath": str(file),
            "size_kb": round(stat.st_size / 1024, 2),
            "created_at": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        })
    return backups


def sync_documents(
    docs_dir: Path = DOCUMENTS_DIR, 
    db_path: Path = DB_PATH,
    progress_callback = None
) -> Dict[str, Any]:
    """Scans documents directory, processes additions, updates, duplicates, and deletions.
    
    Adheres strictly to constraints:
    - Never modifies or deletes any original PDF file.
    - Uses streaming SHA-256 for duplicate detection.
    - Re-indexes changed files automatically.
    """
    stats = {
        "added": 0,
        "updated": 0,
        "skipped": 0,
        "duplicates": 0,
        "deactivated": 0,
        "errors": []
    }

    if not docs_dir.exists():
        docs_dir.mkdir(parents=True, exist_ok=True)
        return stats

    # Collect all PDF files in directory recursively (Read-Only)
    disk_pdf_files: List[Path] = []
    for root, _, files in os.walk(docs_dir):
        for file in files:
            if Path(file).suffix.lower() in SUPPORTED_EXTENSIONS:
                disk_pdf_files.append(Path(root) / file)

    total_files = len(disk_pdf_files)
    init_db(db_path)

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        # Step 1: Detect removed files that were previously indexed
        cursor.execute("SELECT id, filepath FROM files WHERE is_active = 1")
        existing_records = {row["filepath"]: row["id"] for row in cursor.fetchall()}
        
        current_relative_paths = set()
        for pdf_path in disk_pdf_files:
            try:
                rel_path = str(pdf_path.relative_to(docs_dir)).replace("\\", "/")
                current_relative_paths.add(rel_path)
            except Exception:
                current_relative_paths.add(str(pdf_path).replace("\\", "/"))

        for old_rel_path, old_id in existing_records.items():
            if old_rel_path not in current_relative_paths:
                cursor.execute("UPDATE files SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (old_id,))
                stats["deactivated"] += 1

        conn.commit()

        # Step 2: Process each PDF file
        for idx, pdf_path in enumerate(disk_pdf_files):
            try:
                rel_path = str(pdf_path.relative_to(docs_dir)).replace("\\", "/")
            except Exception:
                rel_path = str(pdf_path).replace("\\", "/")

            if progress_callback:
                progress_callback(idx + 1, total_files, pdf_path.name)

            try:
                stat = pdf_path.stat()
                file_size = stat.st_size
                mtime = stat.st_mtime
                category = determine_category(pdf_path.relative_to(docs_dir) if docs_dir in pdf_path.parents else pdf_path)

                # Check if file already exists in database by filepath
                cursor.execute("SELECT id, sha256, mtime, file_size, is_active FROM files WHERE filepath = ?", (rel_path,))
                existing_file = cursor.fetchone()

                # If file exists and mtime/file_size are unchanged, skip re-indexing
                if existing_file and existing_file["is_active"] == 1:
                    if abs(existing_file["mtime"] - mtime) < 0.001 and existing_file["file_size"] == file_size:
                        stats["skipped"] += 1
                        continue

                # Compute current SHA-256
                current_sha256 = compute_sha256(pdf_path)

                # Check if this exact file content already exists under a different path (Deduplication)
                cursor.execute(
                    "SELECT id, filepath, filename FROM files WHERE sha256 = ? AND filepath != ? AND is_active = 1",
                    (current_sha256, rel_path)
                )
                duplicate_file = cursor.fetchone()

                if duplicate_file and not existing_file:
                    # Record duplicate without re-extracting text
                    stats["duplicates"] += 1
                    logger.info(f"Duplicate content detected: '{pdf_path.name}' matches '{duplicate_file['filename']}'")
                    continue

                # Extract PDF text
                extracted = extract_pdf_data(pdf_path)
                if extracted.get("error"):
                    stats["errors"].append(f"{pdf_path.name}: {extracted['error']}")
                    continue

                if existing_file:
                    # Update existing record
                    file_id = existing_file["id"]
                    cursor.execute("""
                        UPDATE files 
                        SET sha256 = ?, file_size = ?, mtime = ?, total_pages = ?, 
                            category = ?, is_active = 1, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (current_sha256, file_size, mtime, extracted["total_pages"], category, file_id))

                    # Remove old pages from tables and FTS
                    cursor.execute("DELETE FROM document_pages WHERE file_id = ?", (file_id,))
                    cursor.execute("DELETE FROM pages_fts WHERE file_id = ?", (file_id,))
                    stats["updated"] += 1
                else:
                    # Insert new record
                    cursor.execute("""
                        INSERT INTO files (filepath, filename, category, sha256, file_size, mtime, total_pages, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """, (rel_path, pdf_path.name, category, current_sha256, file_size, mtime, extracted["total_pages"]))
                    file_id = cursor.lastrowid
                    stats["added"] += 1

                # Insert extracted pages and build FTS5 token index
                for page in extracted["pages"]:
                    page_num = page["page_number"]
                    raw_text = page["raw_text"]
                    char_count = page["char_count"]

                    cursor.execute("""
                        INSERT INTO document_pages (file_id, page_number, raw_text, char_count)
                        VALUES (?, ?, ?, ?)
                    """, (file_id, page_num, raw_text, char_count))
                    page_id = cursor.lastrowid

                    # Tokenize Thai/English text for FTS5 index
                    tokenized_content = tokenize_for_fts(raw_text)

                    cursor.execute("""
                        INSERT INTO pages_fts (page_id, file_id, filename, category, tokenized_content)
                        VALUES (?, ?, ?, ?, ?)
                    """, (page_id, file_id, pdf_path.name, category, tokenized_content))

                conn.commit()

            except Exception as e:
                logger.error(f"Error processing {pdf_path}: {e}")
                stats["errors"].append(f"{pdf_path.name}: {str(e)}")

        conn.commit()
    finally:
        conn.close()

    return stats


def search_documents(
    query: str,
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
    db_path: Path = DB_PATH
) -> List[Dict[str, Any]]:
    """Performs full-text search across indexed documents in Thai and English.
    
    Returns structured results including filename, page number, category,
    imported date, and generated snippet with query terms highlighted.
    """
    if not query or not query.strip():
        return []

    init_db(db_path)
    fts_query = prepare_search_query(query.strip())
    if not fts_query:
        return []

    results: List[Dict[str, Any]] = []

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        sql = """
            SELECT 
                fts.page_id,
                fts.file_id,
                fts.filename,
                fts.category,
                dp.page_number,
                dp.raw_text,
                f.filepath,
                f.imported_at,
                f.sha256,
                f.total_pages,
                bm25(pages_fts) as rank_score
            FROM pages_fts fts
            JOIN document_pages dp ON fts.page_id = dp.id
            JOIN files f ON fts.file_id = f.id
            WHERE pages_fts MATCH ?
              AND f.is_active = 1
        """
        params: List[Any] = [fts_query]

        if category and category != "All":
            sql += " AND f.category = ?"
            params.append(category)

        if start_date:
            sql += " AND date(f.imported_at) >= date(?)"
            params.append(start_date)

        if end_date:
            sql += " AND date(f.imported_at) <= date(?)"
            params.append(end_date)

        sql += " ORDER BY rank_score ASC LIMIT ?"
        params.append(limit)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            for row in rows:
                raw_text = row["raw_text"]
                snippet = create_natural_snippet(raw_text, query)

                results.append({
                    "page_id": row["page_id"],
                    "file_id": row["file_id"],
                    "filename": row["filename"],
                    "filepath": row["filepath"],
                    "category": row["category"],
                    "category_th": CATEGORY_MAP.get(row["category"], row["category"]),
                    "page_number": row["page_number"],
                    "total_pages": row["total_pages"],
                    "imported_at": row["imported_at"],
                    "sha256": row["sha256"],
                    "snippet": snippet,
                    "rank_score": row["rank_score"]
                })

        except sqlite3.OperationalError as e:
            logger.error(f"Search query error for '{fts_query}': {e}")
            # Fallback to simple LIKE search if FTS5 query syntax has any issue
            return fallback_like_search(query, category, limit, conn)
    finally:
        conn.close()

    return results


def fallback_like_search(
    query: str, 
    category: Optional[str], 
    limit: int, 
    conn: sqlite3.Connection
) -> List[Dict[str, Any]]:
    """Fallback search using standard LIKE for broad matching."""
    cursor = conn.cursor()
    sql = """
        SELECT 
            dp.id as page_id,
            dp.file_id,
            f.filename,
            f.category,
            dp.page_number,
            dp.raw_text,
            f.filepath,
            f.imported_at,
            f.sha256,
            f.total_pages
        FROM document_pages dp
        JOIN files f ON dp.file_id = f.id
        WHERE dp.raw_text LIKE ?
          AND f.is_active = 1
    """
    params: List[Any] = [f"%{query.strip()}%"]

    if category and category != "All":
        sql += " AND f.category = ?"
        params.append(category)

    sql += " LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    results = []
    for row in rows:
        results.append({
            "page_id": row["page_id"],
            "file_id": row["file_id"],
            "filename": row["filename"],
            "filepath": row["filepath"],
            "category": row["category"],
            "category_th": CATEGORY_MAP.get(row["category"], row["category"]),
            "page_number": row["page_number"],
            "total_pages": row["total_pages"],
            "imported_at": row["imported_at"],
            "sha256": row["sha256"],
            "snippet": create_natural_snippet(row["raw_text"], query),
            "rank_score": 0.0
        })
    return results


def create_natural_snippet(text: str, query: str, window: int = 120) -> str:
    """Generates an authentic preview snippet highlighting the matched terms in raw text."""
    if not text:
        return ""

    import re
    # Extract query words
    words = [w for w in re.findall(r'[\w\u0E00-\u0E7F]+', query) if len(w) > 1]
    if not words:
        words = [query.strip()]

    # Find the position of the first matched word
    first_idx = -1
    matched_word = ""
    for w in words:
        idx = text.lower().find(w.lower())
        if idx != -1 and (first_idx == -1 or idx < first_idx):
            first_idx = idx
            matched_word = w

    if first_idx == -1:
        # If not directly found in raw text (e.g. whitespace variation), show start of text
        snippet = text[:window * 2].replace("\n", " ").strip()
        return snippet + ("..." if len(text) > len(snippet) else "")

    start = max(0, first_idx - window)
    end = min(len(text), first_idx + len(matched_word) + window)

    snippet = text[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    # Highlight all matched words with HTML mark tag
    for w in sorted(words, key=len, reverse=True):
        pattern = re.compile(re.escape(w), re.IGNORECASE)
        snippet = pattern.sub(lambda m: f"<mark style='background-color:#ffe066; padding:0 3px; border-radius:3px;'><b>{m.group(0)}</b></mark>", snippet)

    return snippet


def get_page_detail(page_id: int, db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
    """Fetches the complete raw text and metadata of a specific page."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                dp.id as page_id,
                dp.page_number,
                dp.raw_text,
                dp.char_count,
                f.id as file_id,
                f.filename,
                f.filepath,
                f.category,
                f.sha256,
                f.file_size,
                f.total_pages,
                f.imported_at,
                f.updated_at
            FROM document_pages dp
            JOIN files f ON dp.file_id = f.id
            WHERE dp.id = ?
        """, (page_id,))
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "page_id": row["page_id"],
            "page_number": row["page_number"],
            "raw_text": row["raw_text"],
            "char_count": row["char_count"],
            "file_id": row["file_id"],
            "filename": row["filename"],
            "filepath": row["filepath"],
            "category": row["category"],
            "category_th": CATEGORY_MAP.get(row["category"], row["category"]),
            "sha256": row["sha256"],
            "file_size": row["file_size"],
            "total_pages": row["total_pages"],
            "imported_at": row["imported_at"],
            "updated_at": row["updated_at"]
        }
    finally:
        conn.close()


def get_file_pages(file_id: int, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieves all pages for a given file ordered by page number."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id as page_id, page_number, raw_text, char_count
            FROM document_pages
            WHERE file_id = ?
            ORDER BY page_number ASC
        """, (file_id,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_database_stats(db_path: Path = DB_PATH) -> Dict[str, Any]:
    """Retrieves high-level statistics for the dashboard."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM files WHERE is_active = 1")
        total_files = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM document_pages dp JOIN files f ON dp.file_id = f.id WHERE f.is_active = 1")
        total_pages = cursor.fetchone()[0]

        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM files 
            WHERE is_active = 1 
            GROUP BY category
        """)
        category_counts = {r["category"]: r["count"] for r in cursor.fetchall()}

        db_size_bytes = db_path.stat().st_size if db_path.exists() else 0

        return {
            "total_files": total_files,
            "total_pages": total_pages,
            "db_size_kb": round(db_size_bytes / 1024, 2),
            "category_counts": category_counts
        }
    finally:
        conn.close()
