from __future__ import annotations

from io import BytesIO
from typing import Iterable


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _fallback_pdf(title: str, lines: Iterable[str]) -> bytes:
    text_lines = [title, ""] + [str(line) for line in lines]
    commands = ["BT", "/F1 12 Tf", "72 760 Td"]
    first = True
    for line in text_lines[:48]:
        if first:
            first = False
        else:
            commands.append("0 -16 Td")
        commands.append(f"({_escape_pdf_text(line[:110])}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("utf-8")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode("utf-8") + stream + b"\nendstream endobj\n",
    ]
    buffer = BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(buffer.tell())
        buffer.write(obj)
    xref = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("utf-8"))
    buffer.write(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("utf-8"))
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
