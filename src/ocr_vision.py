"""AI Vision Smart Per-Page OCR Extractor using OpenAI GPT-4o / GPT-4o-mini.
Extracts printed text, handwriting, forms, and incident scene photos page-by-page.
Safely skips close-up medical/graphic wound photos so safety filters never block
the entire document extraction.
"""

import base64
import logging
import fitz  # PyMuPDF
from openai import OpenAI
from src.usage_tracker import record_api_usage

logger = logging.getLogger(__name__)


def extract_single_page_vision(client: OpenAI, page, page_num: int, model_name: str) -> tuple:
    """Renders one PDF page and extracts Thai text/details.
    Returns (page_text, prompt_tokens, completion_tokens).
    """
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    b64_img = base64.b64encode(img_bytes).decode("utf-8")

    prompt = (
        f"นี่คือหน้าที่ {page_num} ของเอกสารรายงานอุบัติเหตุความปลอดภัยทางราชการ (อบ.ปอ.) ของการไฟฟ้านครหลวง (กฟน.)\n"
        "เอกสารนี้ใช้สำหรับการสอบสวนความปลอดภัยในสถานที่ทำงาน กรุณาอ่านและถอดข้อความภาษาไทยทั้งหมด ทั้งตัวพิมพ์และลายมือเขียน\n"
        "ระบุรายละเอียดสำคัญ เช่น เลขที่เอกสาร, วันเวลาเกิดเหตุ, สถานที่, ชื่อผู้ประสบเหตุ, สังกัด, พฤติการณ์การเกิดเหตุ, "
        "คำชี้แจง, สาเหตุ, และแนวทางแก้ไข หากเป็นหน้าตารางหรือผัง ให้สรุปสาระสำคัญออกมาอย่างละเอียด"
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_img}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            temperature=0.1,
            max_tokens=1500
        )
        content = response.choices[0].message.content.strip() if response.choices else ""

        # Check if model returned a refusal string
        if "unable to assist" in content.lower() or "can't help" in content.lower():
            logger.warning(f"Page {page_num} triggered medical/content refusal. Skipping gracefully.")
            return f"[หน้า {page_num}: ภาพถ่ายทางการแพทย์/ภาพประกอบการบาดเจ็บ (ระบบข้ามอัตโนมัติ)]", 0, 0

        p_tokens = response.usage.prompt_tokens if response.usage else 0
        c_tokens = response.usage.completion_tokens if response.usage else 0
        return content, p_tokens, c_tokens

    except Exception as e:
        logger.warning(f"Error reading page {page_num}: {e}")
        return f"[หน้า {page_num}: ไม่สามารถอ่านได้ ({e})]", 0, 0


def extract_text_with_vision(pdf_path, api_key: str, model_name: str = "gpt-4o-mini", max_pages: int = 6):
    """Smart Per-Page Vision Extractor.
    Processes pages one by one to ensure medical/injury photos never fail the whole document.
    """
    if not api_key:
        raise ValueError("OpenAI API Key is required for AI Vision.")

    client = OpenAI(api_key=api_key)
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    pages_to_process = min(total_pages, max_pages)

    extracted_pages = []
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for idx in range(pages_to_process):
        page_num = idx + 1
        page = doc[idx]
        text, p_tok, c_tok = extract_single_page_vision(client, page, page_num, model_name)
        total_prompt_tokens += p_tok
        total_completion_tokens += c_tok

        if text.strip() and not text.startswith("[หน้า"):
            extracted_pages.append(f"--- หน้า {page_num} ---\n{text}")
        elif text.startswith("[หน้า"):
            extracted_pages.append(text)

    doc.close()

    full_text = "\n\n".join(extracted_pages)

    cost_info = record_api_usage(
        feature="AI Vision (Smart Per-Page)",
        model_name=model_name,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        incident_title=getattr(pdf_path, "name", str(pdf_path))
    )

    return full_text, cost_info
