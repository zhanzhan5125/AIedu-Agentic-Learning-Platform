from __future__ import annotations

from io import BytesIO

from docx import Document
from pptx import Presentation
from pptx.util import Inches

from app.integrations.rag import DocumentBlock, _estimated_tokens, chunk_blocks, extract_blocks


def test_structured_chunks_keep_locator_and_token_limit():
    blocks = [DocumentBlock(
        block_type="paragraph", heading_path="第一章 > 长文本", page_number=3,
        text=("递归用于把复杂问题分解为规模更小的同类问题。" * 120),
    )]
    values = chunk_blocks(blocks)
    assert len(values) > 1
    assert all(_estimated_tokens(item["text"]) <= 800 for item in values)
    assert all(item["page_number"] == 3 for item in values)
    assert all(item["heading_path"] == "第一章 > 长文本" for item in values)


def test_docx_and_pptx_extract_structured_blocks():
    document = Document()
    document.add_heading("数据结构", level=1)
    document.add_paragraph("线性表是有限序列。")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "结构"
    table.cell(0, 1).text = "特点"
    docx_bytes = BytesIO()
    document.save(docx_bytes)
    docx_blocks, _ = extract_blocks(
        docx_bytes.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert any(item.block_type == "heading" and item.heading_path == "数据结构" for item in docx_blocks)
    assert any(item.block_type == "table" and "特点" in item.text for item in docx_blocks)

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "排序算法"
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(2))
    box.text = "快速排序通过枢轴完成分区。"
    pptx_bytes = BytesIO()
    presentation.save(pptx_bytes)
    pptx_blocks, slide_count = extract_blocks(
        pptx_bytes.getvalue(),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    assert slide_count == 1
    assert any(item.slide_number == 1 and item.heading_path == "排序算法" for item in pptx_blocks)
    assert any(item.block_type == "slide" and "快速排序" in item.text for item in pptx_blocks)
