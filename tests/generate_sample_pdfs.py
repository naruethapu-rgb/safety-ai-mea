"""Generates realistic sample PDF documents for testing AI Accident Intelligence.
Uses Windows system Thai font (Leelawadee) to generate multi-page documents
across all specified safety categories.
"""

from pathlib import Path
import pymupdf

FONT_PATH = "C:/Windows/Fonts/leelawad.ttf"

SAMPLE_DATA = [
    {
        "category": "Accidents_Personnel",
        "filename": "INC-2024-001_slip_fall.pdf",
        "pages": [
            (
                "รายงานอุบัติเหตุพนักงาน (Personnel Accident Report)\n"
                "เลขที่เอกสาร: INC-2024-001\n"
                "วันที่เกิดเหตุ: 15 มกราคม 2024\n"
                "แผนก: ฝ่ายผลิต (Production Line 2)\n"
                "ลักษณะการเกิดเหตุ: พนักงานลื่นล้มบนพื้นเปียกน้ำมันหล่อลื่น ขณะเดินตรวจเครื่องจักร\n"
                "อาการบาดเจ็บ: ข้อเท้าขวาเคล็ดและฟกช้ำ ต้องส่งตัวไปห้องพยาบาล\n"
            ),
            (
                "การสอบสวนอุบัติเหตุและมาตรการแก้ไข (Corrective Action)\n"
                "สาเหตุหลัก: มีน้ำมันหล่อลื่นหยดจากข้อต่อเครื่องปั๊ม และพนักงานไม่สวมรองเท้านิรภัยกันลื่น\n"
                "มาตรการป้องกันการเกิดซ้ำ:\n"
                "1. ซ่อมแซมข้อต่อน้ำมันทันที\n"
                "2. กำหนดให้สวมใส่อุปกรณ์คุ้มครองความปลอดภัยส่วนบุคคล (PPE) รองเท้านิรภัย มาตรฐาน EN ISO 20345\n"
                "3. ติดตั้งป้ายเตือนระวังพื้นลื่น\n"
            )
        ]
    },
    {
        "category": "Accidents_Road",
        "filename": "ROAD-2024-015_forklift_collision.pdf",
        "pages": [
            (
                "รายงานอุบัติเหตุยานพาหนะและจราจร (Traffic Incident Report)\n"
                "เลขที่เอกสาร: ROAD-2024-015\n"
                "สถานที่: ลานขนถ่ายสินค้า อาคาร C\n"
                "ยานพาหนะที่เกี่ยวข้อง: รถโฟล์กลิฟต์ (Forklift) หมายเลข FL-05 และ รถบรรทุกส่งของ\n"
                "รายละเอียด: รถโฟล์กลิฟต์ถอยหลังชนมุมกระบะรถบรรทุก เนื่องจากกระจกมองหลังชำรุด\n"
            ),
            (
                "ผลการประเมินความเสียหาย:\n"
                "ความเสียหาย: ไฟท้ายรถโฟล์กลิฟต์แตก และสีด้านข้างรถบรรทุกมีรอยถลอก ไม่มีผู้ได้รับบาดเจ็บ\n"
                "การดำเนินการ: ส่งพนักงานขับรถอบรมทบทวนกฎความปลอดภัยในการขับขี่ และติดตั้งเซนเซอร์เตือนถอยหลัง\n"
            )
        ]
    },
    {
        "category": "WI",
        "filename": "WI-SAF-002_confined_space.pdf",
        "pages": [
            (
                "คู่มือปฏิบัติงาน: ความปลอดภัยในสถานที่อับอากาศ (Work Instruction)\n"
                "รหัสเอกสาร: WI-SAF-002 ฉบับแก้ไขครั้งที่: 03\n"
                "ขอบเขต: ครอบคลุมการทำงานในบ่อบำบัดน้ำเสีย ถังไซโล และท่อระบายน้ำใต้ดิน\n"
                "ข้อกำหนดทั่วไป:\n"
                "1. ต้องมีใบอนุญาตทำงานในที่อับอากาศ (Confined Space Permit) ที่ได้รับการอนุมัติ\n"
                "2. ต้องมีผู้ควบคุมงาน ผู้ช่วยเหลือ และผู้เฝ้าปากทางเข้าออกตลอดเวลา\n"
            ),
            (
                "ขั้นตอนการตรวจวัดสภาพบรรยากาศ:\n"
                "1. ตรวจวัดปริมาณก๊าซออกซิเจน (O2) ต้องอยู่ระหว่าง 19.5% ถึง 23.5%\n"
                "2. ตรวจวัดก๊าซพิษ เช่น ก๊าซไฮโดรเจนซัลไฟด์ (H2S) และคาร์บอนมอนอกไซด์ (CO)\n"
                "3. หากพบก๊าซผิดปกติ ห้ามลงไปปฏิบัติงานโดยเด็ดขาด ให้ระบายอากาศด้วยพัดลมโบลเวอร์\n"
            )
        ]
    },
    {
        "category": "Work_Permit",
        "filename": "WP-2024-550_hot_work.pdf",
        "pages": [
            (
                "ใบอนุญาตทำงานที่มีความร้อนและประกายไฟ (Hot Work Permit)\n"
                "เลขที่ใบอนุญาต: WP-2024-550\n"
                "ผู้รับเหมา: บริษัท ไทยเอ็นจิเนียริ่ง จำกัด\n"
                "ลักษณะงาน: งานเชื่อมและตัดเหล็กโครงสร้างหลังคาโรงงาน\n"
                "ระยะเวลาที่อนุญาต: วันที่ 20 กุมภาพันธ์ 2024 เวลา 08:30 - 17:00 น.\n"
                "รายการตรวจสอบความปลอดภัย: เคลียร์สารไวไฟในรัศมี 11 เมตร มีผ้ากันไฟคลุมพื้นที่\n"
            ),
            (
                "การเตรียมความพร้อมเหตุฉุกเฉิน:\n"
                "1. จัดเตรียมถังดับเพลิงเคมีแห้งขนาด 15 ปอนด์ อย่างน้อย 2 ถัง\n"
                "2. มีผู้เฝ้าระวังไฟ (Fire Watch) ประจำจุดตลอดระยะเวลาที่มีการเชื่อม\n"
                "3. ตรวจสอบพื้นที่หลังเสร็จสิ้นงานอย่างน้อย 30 นาที เพื่อป้องกันประกายไฟคุ\n"
            )
        ]
    },
    {
        "category": "Other",
        "filename": "SOP-ENV-009_chemical_spill.pdf",
        "pages": [
            (
                "ขั้นตอนการระงับเหตุฉุกเฉินสารเคมีรั่วไหล (Chemical Spill Response)\n"
                "รหัส: SOP-ENV-009\n"
                "หมวดหมู่: สิ่งแวดล้อมและความปลอดภัยทั่วไป\n"
                "เมื่อเกิดเหตุสารเคมีหกหรือรั่วไหล ให้ปฏิบัติตามหลัก Stop - Evacuate - Notify\n"
                "1. ผู้พบเห็นแจ้งเตือนเพื่อนร่วมงานและหัวหน้างานทันที\n"
                "2. สวมใส่อุปกรณ์ป้องกันสารเคมี ถุงมือยางไนไตรล์ และแว่นตานิรภัย (Goggles)\n"
            ),
            (
                "การใช้ชุดอุปกรณ์ดูดซับสารเคมี (Spill Kit):\n"
                "1. ใช้วัสดุกั้นล้อมรอบขอบเขตของเหลวเพื่อป้องกันการไหลลงท่อระบายน้ำสาธารณะ\n"
                "2. นำแผ่นดูดซับสารเคมีมาซับสารที่รั่วไหลจนหมด\n"
                "3. รวบรวมขยะปนเปื้อนใส่ถุงขยะอันตรายสีแดงเพื่อนำไปกำจัดตามกฎหมาย\n"
            )
        ]
    }
]


def create_sample_pdf(filepath: Path, pages_text: list[str]) -> None:
    """Creates a sample PDF with Thai text."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page(width=595, height=842) # A4 size
        # Insert font
        if Path(FONT_PATH).exists():
            page.insert_font(fontname="thai_font", fontfile=FONT_PATH)
            font_to_use = "thai_font"
        else:
            font_to_use = "helv"

        # Insert title / body text using textbox for proper multi-line flow
        rect = pymupdf.Rect(50, 50, 545, 792)
        page.insert_textbox(rect, text, fontname=font_to_use, fontsize=12, lineheight=1.4)

    doc.save(str(filepath))
    doc.close()


def generate_all_samples(base_docs_dir: Path) -> list[Path]:
    """Generates all sample PDFs in their designated category folders."""
    created_files = []
    for item in SAMPLE_DATA:
        dest_dir = base_docs_dir / item["category"]
        dest_file = dest_dir / item["filename"]
        create_sample_pdf(dest_file, item["pages"])
        created_files.append(dest_file)
    return created_files


if __name__ == "__main__":
    import sys
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.config import DOCUMENTS_DIR
    files = generate_all_samples(DOCUMENTS_DIR)
    print(f"Generated {len(files)} sample PDFs in {DOCUMENTS_DIR}")
