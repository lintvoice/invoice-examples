"""Wrap a CII invoice in a PDF, as Factur-X does: one page, the XML attached as factur-x.xml.

The PDF is deterministic (no dates, a fixed file identifier) so that regenerated examples do not change.
It is not PDF/A-3: these examples are for testing XML extraction and the XML rules, not PDF/A-3 validation.
"""

import io

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, ByteStringObject

FILE_ID = ByteStringObject(b"invoice-examples")


def facturx_pdf(xml_bytes, name="factur-x.xml"):
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)  # A4
    writer.add_attachment(name, xml_bytes)
    writer._info = None  # no /Producer, no dates
    writer._ID = ArrayObject([FILE_ID, FILE_ID])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
