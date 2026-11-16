"""One-Click Master Sync & Cloud Updater for SafetyAI.
Scans all documents folders (อบ.ปอ. 1-2, 3, 4, WI), indexes new Thai text into SQLite FTS5,
and automatically pushes the updated database to GitHub to refresh Streamlit Cloud.
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.error
import ssl
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.config import DOCUMENTS_DIR, DB_PATH
from src.database import init_db, sync_documents, get_database_stats

# Token loader from local uncommitted file or environment variable
TOKEN_FILE = ROOT_DIR / ".github_token"
if TOKEN_FILE.exists():
    TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()
else:
    TOKEN = os.environ.get("GITHUB_TOKEN", "")

OWNER = "naruethapu-rgb"
REPO = "safety-ai-mea"
BASE_URL = f"https://api.github.com/repos/{OWNER}/{REPO}"

ctx = ssl._create_unverified_context()

def github_request(endpoint, data=None, method="GET"):
    url = f"{BASE_URL}/{endpoint}"
    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "SafetyAI-AutoSync",
        "Content-Type": "application/json"
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))

def create_blob(content_bytes):
    b64 = base64.b64encode(content_bytes).decode("utf-8")
    payload = {"content": b64, "encoding": "base64"}
    res = github_request("git/blobs", data=payload, method="POST")
    return res["sha"]

def main():
    print("=" * 65)
    print("🔄 AI ACCIDENT INTELLIGENCE — ระบบอัปเดตข้อมูลอัตโนมัติ (1-CLICK)")
    print("=" * 65)
    print("\n[ขั้นตอนที่ 1/3] กำลังสแกนเอกสารทั้งหมดในเครื่อง...")
    print("  📁 อบ.ปอ. 1-2 (คนบาดเจ็บ/ของเสียหาย)")
    print("  📁 อบ.ปอ. 3   (ยานพาหนะ/เฉี่ยวชน)")
    print("  📁 อบ.ปอ. 4   (บุคคลภายนอก/ประชาชน)")
    print("  📁 WI         (คู่มือขั้นตอนความปลอดภัย)")
    
    init_db(DB_PATH)
    sync_res = sync_documents(DOCUMENTS_DIR, DB_PATH)
    
    print("\n📊 ผลการสแกนเอกสารในเครื่อง:")
    print(f"  ✅ ไฟล์ใหม่ที่เพิ่ม:       {sync_res['added']} ไฟล์")
    print(f"  🔄 ไฟล์ที่มีการแก้ไข:      {sync_res['updated']} ไฟล์")
    print(f"  ⏭️ ไฟล์เดิม (ข้าม):        {sync_res['skipped']} ไฟล์")
    
    stats = get_database_stats(DB_PATH)
    print(f"  💾 สรุปฐานข้อมูลปัจจุบัน:  {stats['total_files']} ไฟล์ | {stats['total_pages']} หน้า")

    print("\n[ขั้นตอนที่ 2/3] กำลังเตรียมข้อมูลเพื่อส่งขึ้น GitHub...")
    parent_sha = github_request("git/refs/heads/main")["object"]["sha"]
    commit_info = github_request(f"git/commits/{parent_sha}")
    base_tree_sha = commit_info["tree"]["sha"]
    
    # Upload the updated database (this contains ALL new indexed documents and text)
    tree_items = []
    
    print("  + กำลังส่งฐานข้อมูลความปลอดภัย (accident_intel.db)...")
    with open(DB_PATH, "rb") as f:
        db_bytes = f.read()
    db_blob_sha = create_blob(db_bytes)
    tree_items.append({
        "path": "database/accident_intel.db",
        "mode": "100644",
        "type": "blob",
        "sha": db_blob_sha
    })
    
    # Also upload code files (app.py and src/*.py)
    code_files = ["app.py", "requirements.txt"]
    for cf in code_files:
        cfp = ROOT_DIR / cf
        if cfp.exists():
            with open(cfp, "rb") as f:
                content = f.read()
            b_sha = create_blob(content)
            tree_items.append({"path": cf, "mode": "100644", "type": "blob", "sha": b_sha})
            print(f"  + อัปเดตไฟล์ระบบ: {cf}")

    src_dir = ROOT_DIR / "src"
    if src_dir.exists():
        for sp in src_dir.glob("*.py"):
            rel_path = sp.relative_to(ROOT_DIR).as_posix()
            with open(sp, "rb") as f:
                content = f.read()
            b_sha = create_blob(content)
            tree_items.append({"path": rel_path, "mode": "100644", "type": "blob", "sha": b_sha})
            print(f"  + อัปเดตโมดูล: {sp.name}")

    # Also upload any new WI documents
    wi_dir = DOCUMENTS_DIR / "WI"
    if wi_dir.exists():
        for p in wi_dir.glob("*.pdf"):
            rel_path = p.relative_to(ROOT_DIR).as_posix()
            with open(p, "rb") as f:
                content = f.read()
            b_sha = create_blob(content)
            tree_items.append({
                "path": rel_path,
                "mode": "100644",
                "type": "blob",
                "sha": b_sha
            })
            print(f"  + คู่มือ WI: {p.name}")

    print("\n[ขั้นตอนที่ 3/3] กำลังบันทึกการอัปเดตเข้าสู่ GitHub...")
    tree_res = github_request("git/trees", data={"base_tree": base_tree_sha, "tree": tree_items}, method="POST")
    tree_sha = tree_res["sha"]
    
    commit_res = github_request("git/commits", data={
        "message": f"Update safety database: {stats['total_files']} documents, {stats['total_pages']} pages",
        "tree": tree_sha,
        "parents": [parent_sha]
    }, method="POST")
    new_commit = commit_res["sha"]
    
    github_request("git/refs/heads/main", data={"sha": new_commit, "force": True}, method="PATCH")
    
    print("\n" + "=" * 65)
    print("🎉 อัปเดตข้อมูลขึ้นระบบคลาวด์สำเร็จเรียบร้อย 100%!")
    print(f"🌐 เว็บไซต์ Streamlit Cloud กำลังรีโหลดข้อมูลใหม่ทันที")
    print("=" * 65)

if __name__ == "__main__":
    main()
