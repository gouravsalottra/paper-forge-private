from __future__ import annotations

from io import BytesIO
from typing import Iterable


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _fallback_pdf(title: str, lines: Iterable[str]) -> bytes:
    text_lines = [title, ""] + [str(line) for line in lines]
    lines_per_page = 45
    pages = [text_lines[i : i + lines_per_page] for i in range(0, len(text_lines), lines_per_page)] or [[title]]
    objects: list[bytes] = []
    page_object_ids: list[int] = []
    next_id = 3
    font_id = 0
    content_objects: list[tuple[int, bytes]] = []
    for page_lines in pages:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_object_ids.append(page_id)
        commands = ["BT", "/F1 12 Tf", "72 760 Td"]
        first = True
        for line in page_lines:
            if first:
                first = False
            else:
                commands.append("0 -16 Td")
            commands.append(f"({_escape_pdf_text(line[:110])}) Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("utf-8")
        objects.append(
            f"{page_id} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {next_id} 0 R >> >> /Contents {content_id} 0 R >> endobj\n".encode("utf-8")
        )
        content_objects.append((content_id, f"{content_id} 0 obj << /Length {len(stream)} >> stream\n".encode("utf-8") + stream + b"\nendstream endobj\n"))
    font_id = next_id
    kids = " ".join(f"{pid} 0 R" for pid in page_object_ids)
    base_objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        f"2 0 obj << /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >> endobj\n".encode("utf-8"),
    ]
    font_object = f"{font_id} 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n".encode("utf-8")
    all_objects = base_objects + objects + [obj for _, obj in content_objects] + [font_object]
    # Sort by object id to keep xref straightforward.
    def object_id(obj: bytes) -> int:
        return int(obj.split(b" ", 1)[0])
    all_objects = sorted(all_objects, key=object_id)
    buffer = BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in all_objects:
        offsets.append(buffer.tell())
        buffer.write(obj)
    xref = buffer.tell()
    max_id = max(object_id(obj) for obj in all_objects)
    offset_by_id = {object_id(obj): offset for obj, offset in zip(all_objects, offsets[1:])}
    buffer.write(f"xref\n0 {max_id + 1}\n".encode("utf-8"))
    buffer.write(b"0000000000 65535 f \n")
    for obj_id in range(1, max_id + 1):
        buffer.write(f"{offset_by_id.get(obj_id, 0):010d} 00000 n \n".encode("utf-8"))
    buffer.write(f"trailer << /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("utf-8"))
    return buffer.getvalue()


def render_pdf(title: str, lines: Iterable[str]) -> bytes:
    """Render a simple PDF. Uses reportlab when available, otherwise a tiny PDF writer."""
    try:  # pragma: no cover - reportlab is optional in the local test image
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception:
        return _fallback_pdf(title, lines)

    out = BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    width, height = letter
    y = height - 72
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, title[:90])
    y -= 28
    c.setFont("Helvetica", 10)
    for line in lines:
        c.drawString(72, y, str(line)[:115])
        y -= 14
        if y < 72:
            c.showPage()
            y = height - 72
            c.setFont("Helvetica", 10)
    c.save()
    return out.getvalue()
