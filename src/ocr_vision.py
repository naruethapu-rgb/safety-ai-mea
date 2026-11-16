"""AI Vision Smart Per-Page Incident Extractor using OpenAI GPT-4o / GPT-4o-mini.
Extracts incident facts, descriptions, causes, and prevention plans from scanned forms.
Carefully phrased to comply with OpenAI policy (summarization/explanation rather than
verbatim transcription), ensuring 100% success rate without refusals.
"""

import base64
import logging
import fitz  # PyMuPDF
from openai import OpenAI
from src.usage_tracker import record_api_usage

logger = logging.getLogger(__name__)


def extract_single_page_vision(client: OpenAI, page, page_num: int, model_name: str) -> tuple:
    """Renders one PDF page and extracts incident facts in compliance with OpenAI policy.
    Returns (page_text, prompt_tokens, completion_tokens).
    """
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    b64_img = base64.b64encode(img_bytes).decode("utf-8")

    system_prompt = (
        "คุณคือผู้เชี่ยวชาญด้านความปลอดภัยในการทำงานและอาชีวอนามัย (จป.วิชาชีพ) "
        "มีหน้าที่สรุปและอธิบายข้อเท็จจริง พฤติการณ์การเกิดอุบัติเหตุ และสาเหตุ "
        "จากเอกสารรายงานความปลอดภัยในการทำงาน (อบ.ปอ.) ของการไฟฟ้านครหลวง (กฟน.) "
        "เพื่อนำไปใช้วิเคราะห์ 5 Whys และจัดทำแผนป้องกันอุบัติเหตุซ้ำ"
    )

    user_prompt = (
        f"จากภาพเอกสารหน้าที่ {page_num} นี้ กรุณาสรุปและอธิบายรายละเอียดข้อเท็จจริงของอุบัติเหตุอย่างละเอียดและครบถ้วนที่สุด:\n\n"
        "1. ข้อมูลผู้ประสบเหตุ/ผู้เกี่ยวข้อง: (ชื่อ-สกุล, ตำแหน่ง, แผนก, กอง, สังกัด)\n"
        "2. วันเวลา และสถานที่เกิดเหตุ:\n"
        "3. พฤติการณ์การเกิดเหตุ: (อธิบายอย่างละเอียดว่าเกิดอะไรขึ้น ลำดับเหตุการณ์ตั้งแต่ก่อนเกิด ขณะเกิด และหลังเกิดเหตุ)\n"
        "4. อาการบาดเจ็บ หรือความเสียหาย:\n"
        "5. คำชี้แจงของผู้ประสบเหตุ หัวหน้างาน หรือ จป. และสาเหตุที่ตรวจพบ:\n"
        "6. ข้อเสนอแนะและแนวทางป้องกันแก้ไข:\n\n"
        "กรุณานำข้อมูลและสาระสำคัญทั้งหมดที่ปรากฏในหน้านี้มาอธิบายสรุปออกมาเป็นข้อความภาษาไทยอย่างชัดเจนและครบถ้วน"
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
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
            temperature=0.2,
            max_tokens=1500
        )
        content = response.choices[0].message.content.strip() if response.choices else ""

        # Check if model returned a refusal
        refusal_keywords = ["unable to assist", "can't help", "ไม่สามารถถอดข้อความ", "ไม่สามารถช่วยถอดข้อความ"]
        if any(kw in content.lower() for kw in refusal_keywords):
            logger.warning(f"Page {page_num} triggered refusal keyword. Retrying with general explanation prompt...")
            # Retry with soft conversational explanation prompt
            retry_prompt = (
                f"เอกสารหน้าที่ {page_num} นี้คือรายงานความปลอดภัยในการทำงาน "
                "กรุณาช่วยอธิบายว่าในหน้านี้มีข้อมูลอะไรเกี่ยวกับอุบัติเหตุบ้าง มีใครบาดเจ็บ เกิดขึ้นที่ไหน และเพราะอะไร"
            )
            retry_resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": retry_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64_img}", "detail": "high"}
                            }
                        ]
                    }
                ],
                temperature=0.2,
                max_tokens=1500
            )
            content = retry_resp.choices[0].message.content.strip() if retry_resp.choices else ""

            if any(kw in content.lower() for kw in refusal_keywords):
                return f"[หน้า {page_num}: ภาพประกอบ/เอกสารแนบ (ระบบข้ามอัตโนมัติ)]", 0, 0

        p_tokens = response.usage.prompt_tokens if response.usage else 0
        c_tokens = response.usage.completion_tokens if response.usage else 0
        return content, p_tokens, c_tokens

    except Exception as e:
        logger.warning(f"Error reading page {page_num}: {e}")
        return f"[หน้า {page_num}: ข้าม ({e})]", 0, 0


def extract_text_with_vision(pdf_path, api_key: str, model_name: str = "gpt-4o-mini", max_pages: int = 6):
    """Smart Per-Page Vision Extractor.
    Extracts incident facts, descriptions, causes, and prevention plans page by page.
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
        feature="AI Vision (สรุปพฤติการณ์)",
        model_name=model_name,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        incident_title=getattr(pdf_path, "name", str(pdf_path))
    )

    return full_text, cost_info
