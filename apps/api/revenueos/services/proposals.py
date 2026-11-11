from io import BytesIO
from xml.sax.saxutils import escape
from docx import Document
from docx.shared import Inches
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas


def make_pdf(title: str, content: str, amount: float | None) -> bytes:
    buf = BytesIO()
    c = Canvas(buf, pagesize=letter)
    width, height = letter
    y = height - 55
    c.setTitle(title)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(50, y, title[:85])
    y -= 44
    c.setFont("Helvetica", 10)
    import textwrap
    lines = content.splitlines()
    if amount is not None:
        lines.extend(["", f"Proposed price: ${amount:,.2f} (requires client acceptance)"])
    for paragraph in lines:
        for line in textwrap.wrap(paragraph, 96, break_long_words=True) or [""]:
            if y < 52:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - 55
            c.drawString(50, y, line.encode("latin1", errors="replace").decode("latin1"))
            y -= 16
    c.save()
    return buf.getvalue()


def make_docx(title: str, content: str, amount: float | None) -> bytes:
    d = Document()
    d.add_heading(title, 0)
    for paragraph in content.splitlines():
        d.add_paragraph(paragraph)
    if amount is not None:
        d.add_paragraph(f"Proposed price: ${amount:,.2f} (requires client acceptance)")
    data = BytesIO()
    d.save(data)
    return data.getvalue()
