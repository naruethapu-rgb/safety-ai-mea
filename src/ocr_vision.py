"""AI Vision PDF OCR Extractor using OpenAI GPT-4o / GPT-4o-mini.
Extracts printed text, handwriting, and tables from scanned PDF documents
by rendering PDF pages to images and sending them to OpenAI Vision API.
"""

import base64
import fitz  # PyMuPDF
from openai import OpenAI


def extract_text_with_vision(pdf_path, api_key: str, model_name: str = "gpt-4o-mini", max_pages: int = 4) -> str:
    """Renders the first `max_pages` of a PDF to images and uses OpenAI Vision
    to extract Thai handwriting and printed text accurately.
    """
    if not api_key:
        raise ValueError("OpenAI API Key is required for AI Vision.")

    client = OpenAI(api_key=api_key)
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    pages_to_process = min(total_pages, max_pages)

    image_contents = []
    for page_idx in range(pages_to_process):
        page = doc[page_idx]
        # Render page at 150 DPI for high OCR clarity while keeping payload compact
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        image_contents.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64_img}",
                "detail": "high"
            }
        })
    doc.close()

    prompt = (
        "คุณคือผู้เชี่ยวชาญการถอดข้อความรายงานอุบัติเหตุความปลอดภัย (อบ.ปอ.) ของการไฟฟ้านครหลวง (กฟน.)\n"
        "ภาพที่แนบมาคือหน้าเอกสารรายงานอุบัติเหตุ บันทึกข้อความ หรือแบบฟอร์ม อบ.ปอ. 1-4\n"
        "กรุณาอ่านทั้งตัวพิมพ์และลายมือเขียนภาษาไทยทั้งหมด แล้วสรุปข้อมูลพฤติการณ์อุบัติเหตุออกมาตามโครงสร้างนี้อย่างละเอียดและครบถ้วน:\n\n"
        "ประเภทรายงาน: (เช่น อบ.ปอ. 1-2, อบ.ปอ. 3, หรือ อบ.ปอ. 4)\n"
        "วันเวลาเกิดเหตุ:\n"
        "สถานที่เกิดเหตุ:\n"
        "ผู้ประสบอันตราย/ผู้ขับขี่: (ชื่อ-สกุล, ตำแหน่ง, แผนก, กอง, สังกัด)\n"
        "ลักษณะการบาดเจ็บ / ความเสียหาย:\n"
        "พฤติการณ์การเกิดเหตุ: (เล่าลำดับเหตุการณ์ตั้งแต่ก่อนเกิด ขณะเกิด และหลังเกิดเหตุอย่างละเอียด)\n"
        "คำชี้แจงของผู้บาดเจ็บและหัวหน้างาน:\n"
        "สาเหตุการเกิดเหตุ: (ทั้งด้านสภาพแวดล้อม และการกระทำที่ไม่ปลอดภัย)\n"
        "แนวทางการป้องกันและแก้ไข:"
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                *image_contents
            ]
        }
    ]

    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.2,
        max_tokens=2500
    )

    return response.choices[0].message.content.strip()
