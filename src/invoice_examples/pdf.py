"""Wrap a CII invoice in a PDF, as Factur-X does: one readable page, the XML attached as factur-x.xml.

The page is drawn from the XML itself, so it shows exactly what the XML says, mistakes included. It is
marked SPECIMEN and says at the top that the invoice is fictitious. For an invalid variant, the top of the page
also states the rule it fails, and every value that differs from the valid invoice is drawn in the error colour.
The annotated page adds each value's business term number (BT-…) from EN 16931, for people learning to read an
e-invoice.

The PDF is deterministic (no dates, a fixed file identifier) so that regenerated examples do not change.
It is not PDF/A-3: these examples are for testing XML extraction and the XML rules, not PDF/A-3 validation.
The page uses IBM Plex (SIL Open Font License 1.1, fonts/OFL.txt).
"""

import io
import re
from pathlib import Path

from lxml import etree
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, ByteStringObject
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FILE_ID = ByteStringObject(b"invoice-examples")
FONTS = Path(__file__).parent / "fonts"
W, H, M = 595.28, 841.89, 42  # A4, in points; page margin
INK, MUTED, LINE, ACCENT, ERROR = (HexColor(c) for c in ("#171614", "#5A574F", "#CBC7BD", "#5C4632", "#A23A15"))
ERROR_FILL = HexColor("#F4E7E3")  # the error colour at 12 % over white
NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}
TITLES = {
    "380": "Facture",
    "381": "Avoir",
    "384": "Facture rectificative",
    "386": "Facture d'acompte",
    "389": "Autofacture",
    "261": "Autofacture d'avoir",
    "262": "Avoir de remise globale",
}
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_registered = []


def _fonts():
    if not _registered:
        for name, file in (
            ("Plex", "IBMPlexSans-Regular.ttf"),
            ("Plex-SemiBold", "IBMPlexSans-SemiBold.ttf"),
            ("Plex-Mono", "IBMPlexMono-Regular.ttf"),
        ):
            pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
        _registered.append(True)


def _text(root, path):
    found = root.xpath(path, namespaces=NS)
    if not found:
        return ""
    value = found[0] if isinstance(found[0], str) else found[0].text
    return (value or "").strip()


def _party(root, tag):
    p = f"//ram:{tag}"
    address = f"{p}/ram:PostalTradeAddress/ram:"
    return {
        "name": _text(root, f"{p}/ram:Name"),
        "street": _text(root, f"{address}LineOne"),
        "city": f"{_text(root, f'{address}PostcodeCode')} {_text(root, f'{address}CityName')}".strip(),
        "siren": _text(root, f"{p}/ram:SpecifiedLegalOrganization/ram:ID"),
        "siret": _text(root, f"{p}/ram:GlobalID[@schemeID='0009']"),
        "vat": _text(root, f"{p}/ram:SpecifiedTaxRegistration/ram:ID[@schemeID='VA']"),
        "address": _text(root, f"{p}/ram:URIUniversalCommunication/ram:URIID"),
    }


def _adjustments(node, path):
    """Allowances and charges under node: kind, reason (text, else code, else None) and amount."""
    return [
        {
            "charge": _text(ac, "ram:ChargeIndicator/udt:Indicator") == "true",
            "reason": _text(ac, "ram:Reason") or _text(ac, "ram:ReasonCode") or None,
            "amount": _text(ac, "ram:ActualAmount"),
        }
        for ac in node.xpath(path, namespaces=NS)
    ]


# The VAT categories other than the standard rate, as the page names them; the ones that need an exemption reason
# (BT-120 or BT-121: BR-E-10, BR-AE-10, BR-IC-10, BR-G-10, BR-O-10).
CATEGORIES = {
    "Z": "taux zéro",
    "E": "exonéré",
    "AE": "autoliquidation",
    "K": "intracommunautaire",
    "G": "export",
    "O": "hors champ",
    "L": "Canaries",
    "M": "Ceuta et Melilla",
}
NEEDS_REASON = {"E", "AE", "K", "G", "O"}


def _adjustment_label(a):
    """'Remise', 'Frais · Emballage', or 'Remise · sans motif' when it has neither reason nor reason code."""
    kind = "Frais" if a["charge"] else "Remise"
    if not a["reason"]:
        return f"{kind} · sans motif"
    return kind if a["reason"].lower() == kind.lower() else f"{kind} · {a['reason']}"


def read(xml_bytes):
    """The values the page shows, as strings, read from the invoice's XML."""
    root = etree.fromstring(xml_bytes)
    lines = []
    for item in root.xpath("//ram:IncludedSupplyChainTradeLineItem", namespaces=NS):
        lines.append(
            {
                "name": _text(item, ".//ram:SpecifiedTradeProduct/ram:Name"),
                "qty": _text(item, ".//ram:BilledQuantity"),
                "unit": _text(item, ".//ram:BilledQuantity/@unitCode"),
                "price": _text(item, ".//ram:NetPriceProductTradePrice/ram:ChargeAmount"),
                "rate": _text(
                    item, ".//ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent"
                ),
                "net": _text(item, ".//ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount"),
                "adjustments": _adjustments(item, "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeAllowanceCharge"),
            }
        )
    notes = []
    for note in root.xpath("//rsm:ExchangedDocument/ram:IncludedNote", namespaces=NS):
        code, content = _text(note, "ram:SubjectCode"), _text(note, "ram:Content")
        notes.append(f"Traitement (BAR) : {content}" if code == "BAR" else content)
    total = "//ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:"
    # document level allowances (BG-20) and charges (BG-21), in the order of the XML
    adjustments = _adjustments(root, "//ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradeAllowanceCharge")
    # the VAT breakdown (BG-23): one row per category and rate
    breakdown = [
        {
            "category": _text(tax, "ram:CategoryCode"),
            "rate": _text(tax, "ram:RateApplicablePercent"),
            "basis": _text(tax, "ram:BasisAmount"),
            "amount": _text(tax, "ram:CalculatedAmount"),
            "reason": _text(tax, "ram:ExemptionReason") or _text(tax, "ram:ExemptionReasonCode"),
        }
        for tax in root.xpath("//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax", namespaces=NS)
    ]
    return {
        "type": _text(root, "//rsm:ExchangedDocument/ram:TypeCode"),
        "number": _text(root, "//rsm:ExchangedDocument/ram:ID"),
        "date": _text(root, "//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString"),
        "due": _text(root, "//ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString"),
        "order": _text(root, "//ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID"),
        "framework": _text(
            root, "//rsm:ExchangedDocumentContext/ram:BusinessProcessSpecifiedDocumentContextParameter/ram:ID"
        ),
        "seller": _party(root, "SellerTradeParty"),
        "buyer": _party(root, "BuyerTradeParty"),
        "lines": lines,
        "terms": _text(root, "//ram:SpecifiedTradePaymentTerms/ram:Description"),
        "iban": _text(root, "//ram:PayeePartyCreditorFinancialAccount/ram:IBANID"),
        "bic": _text(root, "//ram:PayeeSpecifiedCreditorFinancialInstitution/ram:BICID"),
        "notes": notes,
        "lines_total": _text(root, f"{total}LineTotalAmount"),
        "adjustments": adjustments,
        "breakdown": breakdown,
        "allowance_total": _text(root, f"{total}AllowanceTotalAmount"),
        "charge_total": _text(root, f"{total}ChargeTotalAmount"),
        "net": _text(root, f"{total}TaxBasisTotalAmount"),
        "vat": _text(root, f"{total}TaxTotalAmount"),
        "gross": _text(root, f"{total}GrandTotalAmount"),
        "prepaid": _text(root, f"{total}TotalPrepaidAmount"),
        "rounding": _text(root, f"{total}RoundingAmount"),
        "payable": _text(root, f"{total}DuePayableAmount"),
    }


def _number(value, unit=""):
    """French formatting that keeps every decimal written in the XML, so a wrong precision stays visible."""
    if not value:
        return "absent"
    if not NUMBER.match(value):
        return value
    whole, _, decimals = value.lstrip("-").partition(".")
    grouped = f"{int(whole):,}".replace(",", " ")
    return ("−" if value.startswith("-") else "") + grouped + ("," + decimals if decimals else "") + unit


def _money(value):
    if value and NUMBER.match(value) and "." not in value:
        value += ".00"
    return _number(value, " €")


def _date(value):
    if re.match(r"^\d{8}$", value or ""):
        return f"{value[6:8]}/{value[4:6]}/{value[0:4]}"
    return value or "absent"


def _get(data, keys):
    for k in keys:
        if isinstance(data, dict):
            data = data.get(k)
        elif isinstance(data, list) and isinstance(k, int) and k < len(data):
            data = data[k]
        else:
            return None
    return data


class _Page:
    def __init__(self, c, data, reference, annotate):
        self.c, self.d, self.ref, self.annotate = c, data, reference, annotate

    def changed(self, keys):
        """True when this value differs from the valid invoice's."""
        return self.ref is not None and _get(self.d, keys) != _get(self.ref, keys)

    def text(self, x, y, s, font="Plex", size=8.5, color=INK, align="l"):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        (self.c.drawString if align == "l" else self.c.drawRightString)(x, y, s)
        return self.c.stringWidth(s, font, size)

    def value(self, x, y, s, keys, font="Plex", size=8.5, align="l", bad=None):
        """A value, in the error colour and underlined when it differs from the valid invoice."""
        bad = self.changed(keys) if bad is None else bad
        w = self.text(x, y, s, font, size, ERROR if bad else INK, align)
        if bad:
            x0 = x if align == "l" else x - w
            self.c.setStrokeColor(ERROR)
            self.c.setLineWidth(0.8)
            self.c.line(x0, y - 2, x0 + w, y - 2)
        return w

    def code(self, x, y, bt, align="l"):
        if self.annotate:
            self.text(x, y, bt, "Plex-Mono", 5.5, MUTED, align)

    def watermark(self):
        c = self.c
        c.saveState()
        c.translate(W / 2, H / 2)
        c.rotate(35)
        c.setFillColor(Color(0.36, 0.27, 0.20, alpha=0.08))
        c.setFont("Plex-SemiBold", 110)
        c.drawCentredString(0, -38, "SPÉCIMEN")
        c.restoreState()

    def party(self, x, y, title, key, codes):
        p = self.d[key]
        self.text(x, y, title.upper(), "Plex-SemiBold", 7.5, ACCENT)
        self.value(x, y - 16, p["name"] or "absent", (key, "name"), "Plex-SemiBold", 11)
        self.value(x, y - 29, p["street"], (key, "street"))
        self.value(x, y - 40, p["city"], (key, "city"))
        y -= 56
        fields = zip(
            ("SIREN", "SIRET", "N° TVA", "Adresse élec."), ("siren", "siret", "vat", "address"), codes, strict=True
        )
        for label, field, bt in fields:
            if not p[field] and not self.changed((key, field)):
                continue
            self.text(x, y, label, size=7.5, color=MUTED)
            w = self.value(x + 58, y, p[field] or "absent", (key, field), "Plex-Mono", 8.5)
            self.code(x + 62 + w, y + 0.5, bt)
            y -= 11.5
        return y

    def header(self, rule, description):
        """Above the invoice, before anything else: what this page is and, for an invalid variant, what is wrong.
        Returns the height it takes."""
        c = self.c
        y = H - 30
        self.text(
            M,
            y,
            "Spécimen : facture fictive, sans valeur, générée par lintvoice/invoice-examples (domaine public, CC0).",
            "Plex-SemiBold",
            7.5,
            MUTED,
        )
        second = "Cette page reprend les données du fichier factur-x.xml joint au PDF" + (
            ", erreur comprise." if rule else "."
        )
        if self.annotate:
            second += " Les petits codes BT-… sont les numéros des données dans la norme européenne EN 16931."
        self.text(M, y - 10, second, size=7.5, color=MUTED)
        y -= 22
        if rule:
            wrapped = simpleSplit(description or "", "Plex", 8.5, W - 2 * M - 20)
            height = 22 + 11 * len(wrapped)
            c.setFillColor(ERROR_FILL)
            c.setStrokeColor(ERROR)
            c.setLineWidth(0.8)
            c.roundRect(M, y - height, W - 2 * M, height, 4, stroke=1, fill=1)
            # "×" and a word: the status never relies on colour alone
            self.text(M + 10, y - 13, f"× Erreur · {rule}", "Plex-SemiBold", 8.5, ERROR)
            for i, line in enumerate(wrapped):
                self.text(M + 10, y - 26 - 11 * i, line, size=8.5)
            y -= height + 6
        return H - y

    def draw(self, rule=None, description=None):
        c, d = self.c, self.d
        self.watermark()
        top = self.header(rule, description)
        c.saveState()
        c.translate(0, -(top - 28))  # the invoice starts under the header
        c.setStrokeColor(ACCENT)
        c.setLineWidth(2)
        c.line(M, H - 40, W - M, H - 40)
        self.party(M, H - 60, "Vendeur", "seller", ("BT-30", "BT-29", "BT-31", "BT-34"))
        self.text(W - M, H - 66, TITLES.get(d["type"], "Facture").upper(), "Plex-SemiBold", 24, align="r")
        w = self.value(W - M, H - 84, d["number"] or "absent", ("number",), "Plex-Mono", 10, "r")
        self.code(W - M - w - 4, H - 84, "BT-1", "r")
        rows = (
            ("Date", _date(d["date"]), "date", "BT-2"),
            ("Échéance", _date(d["due"]), "due", "BT-9"),
            ("Commande", d["order"] or "absent", "order", "BT-13"),
            ("Cadre", d["framework"] or "absent", "framework", "BT-23"),
        )
        for i, (label, v, key, bt) in enumerate(rows):
            y = H - 102 - i * 12
            self.text(W - M - 80, y, label, size=8, color=MUTED, align="r")
            self.code(W - M - 84 - c.stringWidth(label, "Plex", 8), y, bt, "r")
            self.value(W - M, y, v, (key,), "Plex-Mono", 8.5, "r")
        y = min(self.party(340, H - 170, "Acheteur", "buyer", ("BT-47", "BT-46", "BT-48", "BT-49")), H - 250) - 14
        y = self.lines(y)
        y = min(self.totals(y - 14), self.breakdown(y - 14))
        self.notes(y - 24)
        c.restoreState()

    def lines(self, y):
        cols = (
            (M, "Désignation", "l", "BT-153"),
            (330, "Qté", "r", "BT-129"),
            (400, "Prix unit. HT", "r", "BT-146"),
            (450, "TVA", "r", "BT-152"),
            (W - M, "Montant HT", "r", "BT-131"),
        )
        for x, label, align, bt in cols:
            self.text(x, y, label, "Plex-SemiBold", 7.5, MUTED, align)
            self.code(x, y + 8, bt, align)
        self.c.setStrokeColor(INK)
        self.c.setLineWidth(0.8)
        self.c.line(M, y - 4, W - M, y - 4)
        y -= 18
        for i, line in enumerate(self.d["lines"]):
            self.value(M, y, line["name"] or "absent", ("lines", i, "name"), size=9)
            qty, unit = _number(line["qty"]), line.get("unit")
            changed = self.changed(("lines", i, "qty")) or self.changed(("lines", i, "unit"))
            self.value(330, y, qty if unit else f"{qty} sans unité", (), "Plex-Mono", 8.5, "r", bad=changed)
            self.value(400, y, _money(line["price"]), ("lines", i, "price"), "Plex-Mono", 8.5, "r")
            self.value(450, y, _number(line["rate"], " %"), ("lines", i, "rate"), "Plex-Mono", 8.5, "r")
            self.value(W - M, y, _money(line["net"]), ("lines", i, "net"), "Plex-Mono", 8.5, "r")
            for j, a in enumerate(line.get("adjustments") or []):
                y -= 13
                keys = ("lines", i, "adjustments", j)
                self.value(
                    M + 12, y, _adjustment_label(a), (*keys, "reason"), size=8, bad=None if a["reason"] else True
                )
                sign = "+ " if a["charge"] else "− "
                self.value(W - M, y, sign + _money(a["amount"]), (*keys, "amount"), "Plex-Mono", 8, "r")
            self.c.setStrokeColor(LINE)
            self.c.setLineWidth(0.5)
            self.c.line(M, y - 6, W - M, y - 6)
            y -= 20
        return y

    def totals(self, y):
        """The totals, from the sum of the lines to the amount due; the optional ones only when the invoice has them."""
        x = 360
        d = self.d
        rows = [("Total des lignes HT", ("lines_total",), "BT-106")]
        for i, a in enumerate(d["adjustments"]):
            rows.append((_adjustment_label(a), ("adjustments", i, "amount"), "BT-99" if a["charge"] else "BT-92"))
        if d["allowance_total"]:
            rows.append(("Total des remises", ("allowance_total",), "BT-107"))
        if d["charge_total"]:
            rows.append(("Total des frais", ("charge_total",), "BT-108"))
        rows += [("Total HT", ("net",), "BT-109"), ("TVA", ("vat",), "BT-110"), ("Total TTC", ("gross",), "BT-112")]
        if d["prepaid"]:
            rows.append(("Déjà payé", ("prepaid",), "BT-113"))
        if d["rounding"]:
            rows.append(("Arrondi", ("rounding",), "BT-114"))
        rows.append(("Net à payer", ("payable",), "BT-115"))
        for label, keys, bt in rows:
            key = keys[0]
            strong = key in ("gross", "payable")
            font, size = ("Plex-SemiBold", 9.5) if strong else ("Plex", 9)
            color = ERROR if label.endswith("sans motif") else INK if strong else MUTED  # a missing reason is an error
            w = self.text(x, y, label, font, size, color)
            self.code(x + w + 4, y + 0.5, bt)
            self.value(W - M, y, _money(_get(d, keys)), keys, "Plex-Mono", size, "r")
            if key == "vat":
                self.c.setStrokeColor(INK)
                self.c.setLineWidth(0.8)
                self.c.line(x, y - 6, W - M, y - 6)
            y -= 18
        return y

    def breakdown(self, y):
        """The VAT per rate, left of the totals: each category and rate with its taxable amount and VAT, and the
        exemption reason of the categories that need one."""
        d = self.d
        self.text(M, y, "TVA PAR TAUX", "Plex-SemiBold", 7.5, ACCENT)
        self.code(M + self.c.stringWidth("TVA PAR TAUX", "Plex-SemiBold", 7.5) + 4, y, "BG-23")
        y -= 14
        for x, label, bt in ((M, "Taux", "BT-119"), (M + 190, "Base HT", "BT-116"), (M + 262, "TVA", "BT-117")):
            align = "l" if x == M else "r"
            self.text(x, y, label, "Plex-SemiBold", 7.5, MUTED, align)
            self.code(x, y + 8, bt, align)
        y -= 13
        for i, row in enumerate(d["breakdown"]):
            keys = ("breakdown", i)
            name = CATEGORIES.get(row["category"])
            rate = _number(row["rate"], " %")
            self.value(M, y, f"{rate} · {name}" if name else rate, (*keys, "rate"), "Plex-Mono", 8.5)
            self.value(M + 190, y, _money(row["basis"]), (*keys, "basis"), "Plex-Mono", 8.5, "r")
            self.value(M + 262, y, _money(row["amount"]), (*keys, "amount"), "Plex-Mono", 8.5, "r")
            if row["category"] in NEEDS_REASON:
                y -= 11
                reason = row["reason"] or "Motif d'exonération absent"
                self.value(M + 12, y, reason, (*keys, "reason"), size=8, bad=None if row["reason"] else True)
                self.code(M + 16 + self.c.stringWidth(reason, "Plex", 8), y + 0.5, "BT-120")
            y -= 13
        return y

    def notes(self, y):
        d, ref = self.d, self.ref
        self.text(M, y, "CONDITIONS ET MENTIONS", "Plex-SemiBold", 7.5, ACCENT)
        self.code(M + self.c.stringWidth("CONDITIONS ET MENTIONS", "Plex-SemiBold", 7.5) + 4, y, "BT-20, BT-22, BT-84")
        y -= 13
        if d["terms"] or self.changed(("terms",)):
            self.value(M, y, d["terms"] or "Conditions de paiement absentes", ("terms",), size=8)
            y -= 11
        if d["iban"] or self.changed(("iban",)):
            self.value(M, y, f"IBAN {d['iban'] or 'absent'}   BIC {d['bic'] or 'absent'}", ("iban",), "Plex-Mono", 7.5)
            y -= 11
        for note in d["notes"]:
            self.value(M, y, note, (), size=8, bad=ref is not None and note not in ref["notes"])
            y -= 11
        for note in ref["notes"] if ref else ():
            if note not in d["notes"]:
                self.value(M, y, f"Mention absente : {note}", (), size=8, bad=True)
                y -= 11


def page_pdf(xml_bytes, reference=None, rule=None, description=None, annotate=False):
    """The readable page alone, as PDF bytes."""
    _fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H), invariant=1, pageCompression=1)
    _Page(c, read(xml_bytes), read(reference) if reference else None, annotate).draw(rule, description)
    c.showPage()
    c.save()
    return buf.getvalue()


def facturx_pdf(xml_bytes, name="factur-x.xml", reference=None, rule=None, description=None, annotate=False):
    """A Factur-X-style PDF: the readable page, with the XML attached. For an invalid variant, pass the valid
    invoice as reference, and the rule with what is wrong, so the page shows where the mistake is."""
    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(page_pdf(xml_bytes, reference, rule, description, annotate))).pages[0])
    writer.add_attachment(name, xml_bytes)
    writer._info = None  # no /Producer, no dates
    writer._ID = ArrayObject([FILE_ID, FILE_ID])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
