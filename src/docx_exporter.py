"""Word Document (.docx) Exporter for AI Accident Intelligence.
Formats official MEA Safety Analysis Reports (อบ.ปอ. 1-4) ready for print.
"""

import io
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def set_run_font(run, font_name="TH Sarabun PSK", size_pt=16, bold=False, color_rgb=(0, 0, 0)):
    """Sets exact font, size, and styling for Thai government documents."""
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.font.color.rgb = RGBColor(*color_rgb)

    # Ensure East Asia and Complex Script fonts are set for Thai rendering in Word
    rPr = run._r.get_or_add_rPr()
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)
    rFonts.set(qn('w:cs'), font_name)
    rPr.append(rFonts)


def create_safety_report_docx(
    report_title: str,
    target_form: str,
    incident_meta: str,
    incident_text: str,
    past_comparison: str,
    causes_text: str,
    wi_evaluation: str,
    prevention_text: str,
    analyst_name: str = "นายนฤเทพ อุบลรัศมี"
) -> bytes:
    """Generates an official A4 Microsoft Word document matching MEA standards.
    
    Returns:
        bytes: Raw docx file content for Streamlit download.
    """
    doc = Document()

    # Set Margins (Top/Bottom 1 inch, Left 1.25 inch, Right 1 inch)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.25)
        section.right_margin = Inches(1.0)

    # 1. Title (Centered)
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(2)
    p_title.paragraph_format.line_spacing = 1.15
    run_t1 = p_title.add_run("ผลการวิเคราะห์หาสาเหตุและวิธีการป้องกัน\n")
    set_run_font(run_t1, size_pt=18, bold=True)
    run_t2 = p_title.add_run(target_form)
    set_run_font(run_t2, size_pt=18, bold=True)

    # 2. Meta Info (Indent & Justified)
    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_before = Pt(8)
    p_meta.paragraph_format.space_after = Pt(10)
    p_meta.paragraph_format.line_spacing = 1.15
    run_meta = p_meta.add_run(incident_meta if incident_meta else f"อุบัติภัยราย: (ตามรายงานที่ส่งมา)")
    set_run_font(run_meta, size_pt=16, bold=False)

    def add_section(heading_title: str, body_text: str):
        p_head = doc.add_paragraph()
        p_head.paragraph_format.space_before = Pt(8)
        p_head.paragraph_format.space_after = Pt(2)
        run_h = p_head.add_run(heading_title)
        set_run_font(run_h, size_pt=16, bold=True)

        p_body = doc.add_paragraph()
        p_body.paragraph_format.space_before = Pt(0)
        p_body.paragraph_format.space_after = Pt(6)
        p_body.paragraph_format.line_spacing = 1.15
        p_body.paragraph_format.left_indent = Inches(0.25)
        run_b = p_body.add_run(body_text.strip())
        set_run_font(run_b, size_pt=16, bold=False)

    # 3. Sections
    if incident_text:
        add_section("ลักษณะการเกิดอุบัติเหตุ", incident_text)

    if past_comparison:
        add_section("การเปรียบเทียบเชิงลึกกับอุบัติเหตุในอดีต (วิเคราะห์เนื้อหาไส้ใน)", past_comparison)

    if causes_text:
        add_section("สาเหตุ", causes_text)

    if wi_evaluation:
        add_section("การตรวจสอบการละเมิดคู่มือปฏิบัติงาน (WI)", wi_evaluation)

    if prevention_text:
        add_section("วิธีการป้องกัน", prevention_text)

    # 4. Sign-off (Right-aligned)
    p_sign = doc.add_paragraph()
    p_sign.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_sign.paragraph_format.space_before = Pt(24)
    p_sign.paragraph_format.space_after = Pt(0)
    p_sign.paragraph_format.line_spacing = 1.15
    p_sign.paragraph_format.right_indent = Inches(0.5)

    run_s1 = p_sign.add_run(f"{analyst_name}\n")
    set_run_font(run_s1, size_pt=16, bold=False)
    run_s2 = p_sign.add_run("ผู้วิเคราะห์")
    set_run_font(run_s2, size_pt=16, bold=False)

    # Save to memory stream
    output_stream = io.BytesIO()
    doc.save(output_stream)
    output_stream.seek(0)
    return output_stream.getvalue()
