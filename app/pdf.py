"""The single predefined certificate template.

Change this module when the certificate layout needs to change. Callers pass
the recipient and the shared event fields; they do not know about PDF drawing.
"""

from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

INK = HexColor("#1c2b24")
FOREST = HexColor("#1f4b3a")
GOLD = HexColor("#a68445")
PAPER = HexColor("#fbf7f0")


def render_certificate(
    destination: Path,
    *,
    recipient_name: str,
    email: str | None,
    detail: str | None,
    event_name: str,
    title: str,
    issuer: str,
    issued_on: date,
    certificate_id: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = landscape(A4)
    pdf = canvas.Canvas(str(destination), pagesize=(width, height))
    pdf.setTitle(title)
    pdf.setAuthor(issuer)

    pdf.setFillColor(PAPER)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setStrokeColor(FOREST)
    pdf.setLineWidth(2.4)
    pdf.rect(14 * mm, 14 * mm, width - 28 * mm, height - 28 * mm, fill=0, stroke=1)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.8)
    pdf.rect(17.5 * mm, 17.5 * mm, width - 35 * mm, height - 35 * mm, fill=0, stroke=1)

    _centered(pdf, title.upper(), width, height - 36 * mm, "Times-Bold", 16, FOREST)
    _centered(pdf, "This is to certify that", width, height - 54 * mm, "Times-Italic", 13, INK)

    name_size = 32 if len(recipient_name) <= 32 else 22
    _centered(pdf, recipient_name, width, height - 74 * mm, "Times-Bold", name_size, INK)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.6)
    pdf.line(width / 2 - 70 * mm, height - 80 * mm, width / 2 + 70 * mm, height - 80 * mm)

    _centered(pdf, "has completed", width, height - 94 * mm, "Times-Italic", 13, INK)
    cursor = _draw_lines(
        pdf,
        _fit_lines(event_name, "Times-Bold", 16, 160 * mm, 2),
        width,
        height - 108 * mm,
        "Times-Bold",
        16,
        FOREST,
    )
    if detail:
        cursor = _draw_lines(
            pdf,
            _fit_lines(detail, "Times-Roman", 12, 150 * mm, 2),
            width,
            cursor - 4 * mm,
            "Times-Roman",
            12,
            INK,
        )
    if email:
        _centered(pdf, email, width, cursor - 2 * mm, "Times-Roman", 11, INK)

    issued = issued_on.strftime("%d %B %Y")
    _centered(pdf, f"Issued on {issued}  ·  {issuer}", width, 32 * mm, "Times-Roman", 12, INK)
    _centered(pdf, f"Certificate ID {certificate_id}", width, 24 * mm, "Times-Roman", 8, GOLD)
    pdf.save()


def _centered(pdf: canvas.Canvas, text: str, width: float, y: float, font: str, size: int, color) -> None:
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    pdf.drawCentredString(width / 2, y, text)


def _fit_lines(text: str, font: str, size: int, max_width: float, max_lines: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if stringWidth(trial, font, size) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    kept[-1] = kept[-1].rstrip(".") + "…"
    return kept


def _draw_lines(
    pdf: canvas.Canvas,
    lines: list[str],
    width: float,
    y: float,
    font: str,
    size: int,
    color,
) -> float:
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    for line in lines:
        pdf.drawCentredString(width / 2, y, line)
        y -= size + 4
    return y
