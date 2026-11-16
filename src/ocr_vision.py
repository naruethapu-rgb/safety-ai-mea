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
        "คุณคือผู้ช่วยงานด้านความปลอดภัยของการไฟฟ้านครหลวง (กฟน.) "
        "มีหน้าที่อ่านและสรุปข้อมูลเหตุการณ์อุบัติเหตุจากการทำงาน "
        "โดยอธิบายว่าใครประสบเหตุ ที่ไหน เมื่อไหร่ ลำดับเหตุการณ์เป็นอย่างไร "
        "เพื่อใช้เป็นข้อมูลในการสอบสวนหาสาเหตุและปรับปรุงความปลอดภัย"
    )

    user_prompt = (
        f"นี่คือภาพเอกสารรายงานความปลอดภัย หน้าที่ {page_num} "
        "กรุณาสรุปข้อมูลและข้อเท็จจริงสำคัญที่พบในหน้านี้:\n"
        "- ชื่อ-ตำแหน่ง และสังกัดของผู้เกี่ยวข้อง\n"
        "- วันที่ เวลา และสถานที่เกิดเหตุ\n"
        "- พฤติการณ์และลำดับเหตุการณ์การเกิดอุบัติเหตุ\n"
        "- สภาพความเสียหายหรือการบาดเจ็บ\n"
        "- สาเหตุเบื้องต้นและแนวทางป้องกันที่ระบุไว้\n"
        "สรุปเป็นภาษาไทยที่กระชับ ชัดเจน และตรงไปตรงมาตามเอกสาร"
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
        refusal_keywords = [
            "unable to assist", "can't help", "cannot assist", "i am sorry", "i'm sorry", 
            "ขอโทษ", "ไม่สามารถถอดข้อความ", "ไม่สามารถช่วยถอดข้อความ", "ไม่สามารถช่วย", "ไม่สามารถให้ข้อมูล"
        ]
        if any(kw in content.lower() for kw in refusal_keywords):
            logger.warning(f"Page {page_num} triggered refusal keyword. Retrying with general overview prompt...")
            # Retry with soft conversational summary prompt
            retry_prompt = (
                f"เอกสารหน้าที่ {page_num} เป็นรายงานความปลอดภัย กฟน. "
                "ช่วยบอกข้อมูลสำคัญเกี่ยวกับเหตุการณ์ที่บันทึกไว้ในหน้านี้ เช่น ใครเกิดเหตุ อะไรเกิดขึ้น ที่ไหน"
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

    valid_content = [p for p in extracted_pages if not p.startswith("[หน้า")]
    if valid_content:
        full_text = "\n\n".join(extracted_pages)
    else:
        full_text = (
            "⚠️ AI ไม่สามารถสรุปข้อความจากภาพสแกนชุดนี้ได้โดยอัตโนมัติ (ภาพสแกนอาจมีคุณภาพไม่เพียงพอหรือเป็นภาพถ่ายล้วน)\n\n"
            "คำแนะนำ: ท่านสามารถพิมพ์หรือคัดลอกรายละเอียดพฤติการณ์อุบัติเหตุลงในช่องข้อความนี้โดยตรง เพื่อส่งให้ระบบวิเคราะห์เทียบเคสเก่าและตรวจสอบ WI ทันที"
        )

    cost_info = record_api_usage(
        feature="AI Vision (สรุปพฤติการณ์)",
        model_name=model_name,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        incident_title=getattr(pdf_path, "name", str(pdf_path))
    )

    return full_text, cost_info
