"""Wrap a CII invoice in a PDF, as Factur-X does: one readable page, the XML attached as factur-x.xml.

The page is drawn from the XML itself, so it shows exactly what the XML says, mistakes included. It is
marked SPECIMEN and says at the top that the invoice is fictitious. For an invalid variant, the top of the page
also states the rule it fails, and every value it draws that differs from the invoice it is compared with (the valid
one, or the same invoice without the mistake) is in the error colour. When the mistake sits in data the page does not
draw, in the electronic data only, a box under the totals says so and lists what differs: each element with its
business term, its value, its place in the XML and its value in the file it is compared with.
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

from .differences import differences

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
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
# The page's words, by language: "fr" for the French target, "en" for the others. The VAT categories other than the
# standard rate are named as the page shows them; the document types as the title shows them.
LABELS = {
    "fr": {
        "titles": {
            "380": "Facture",
            "326": "Facture partielle",
            "381": "Avoir",
            "384": "Facture rectificative",
            "386": "Facture d'acompte",
            "389": "Autofacture",
            "261": "Autofacture d'avoir",
            "262": "Avoir de remise globale",
        },
        "categories": {
            "Z": "taux zéro",
            "E": "exonéré",
            "AE": "autoliquidation",
            "K": "intracommunautaire",
            "G": "export",
            "O": "hors champ",
            "L": "Canaries",
            "M": "Ceuta et Melilla",
        },
        "absent": "absent",
        "thousands": " ",  # a narrow no-break space
        "decimal": ",",
        "money": "{} €",  # an amount in euros; in another currency, its ISO 4217 code (BT-5) where the € goes
        "money_code": "{} {code}",
        "percent": " %",
        "date": "{d}/{m}/{y}",
        "watermark": "SPÉCIMEN",
        "specimen": "Spécimen : facture fictive, sans valeur, générée par lintvoice/invoice-examples (domaine public, CC0).",
        "source": "Cette page reprend les données du fichier factur-x.xml joint au PDF",
        "source_error": ", erreur comprise.",
        "codes": " Les petits codes BT-… sont les numéros des données dans la norme européenne EN 16931.",
        "error": "Erreur",
        "seller": "Vendeur",
        "buyer": "Acheteur",
        # the party's identifiers, label and value, in the order of the codes BT-30, BT-29, BT-31, BT-34
        "ids": (("SIREN", "legal"), ("SIRET", "siret"), ("N° TVA", "vat"), ("Adresse élec.", "address")),
        "rows": ("Date", "Échéance", "Commande", "Cadre"),
        "columns": ("Désignation", "Qté", "Prix unit. HT", "TVA", "Montant HT"),
        "no_unit": "{} sans unité",
        "allowance": "Remise",
        "charge": "Frais",
        "no_reason": "sans motif",
        "bar": "Traitement (BAR) : {}",
        "lines_total": "Total des lignes HT",
        "allowance_total": "Total des remises",
        "charge_total": "Total des frais",
        "net": "Total HT",
        "vat": "TVA",
        "gross": "Total TTC",
        "prepaid": "Déjà payé",
        "rounding": "Arrondi",
        "payable": "Net à payer",
        "breakdown": "TVA PAR TAUX",
        "breakdown_columns": ("Taux", "Base HT", "TVA"),
        "no_exemption_reason": "Motif d'exonération absent",
        "notes": "CONDITIONS ET MENTIONS",
        "no_terms": "Conditions de paiement absentes",
        "missing_note": "Mention absente : {}",
        "electronic": "Erreur dans les données électroniques seulement : le rendu de ce PDF ne la montre pas",
        "attached": "Les données électroniques sont le fichier XML joint à ce PDF sous le nom factur-x.xml (voir les pièces "
        "jointes du PDF).",
        "compared": "Par rapport à {} :",
        "in_reference": "dans {} : ",
        "not_in_reference": "absent de {}",
        "the_reference": "la facture valide",
        "blank": "vide",
        "no_dates": "sans dates",
        "scheme": "schéma {}",
        "no_scheme": "sans schéma",
    },
    "en": {
        "titles": {
            "380": "Invoice",
            "326": "Partial invoice",
            "381": "Credit note",
            "384": "Corrected invoice",
            "386": "Prepayment invoice",
            "389": "Self-billed invoice",
            "261": "Self-billed credit note",
            "262": "Consolidated credit note",
        },
        "categories": {
            "Z": "zero rated",
            "E": "exempt",
            "AE": "reverse charge",
            "K": "intra-EU supply",
            "G": "export",
            "O": "outside the scope of VAT",
            "L": "Canary Islands",
            "M": "Ceuta and Melilla",
        },
        "absent": "missing",
        "thousands": ",",
        "decimal": ".",
        "money": "€{}",
        "money_code": "{code} {}",
        "percent": "%",
        "date": "{y}-{m}-{d}",
        "watermark": "SPECIMEN",
        "specimen": "Specimen: a fictitious invoice, of no value, generated by lintvoice/invoice-examples (public domain, CC0).",
        "source": "This page shows the data of the factur-x.xml file attached to the PDF",
        "source_error": ", mistake included.",
        "codes": " The small BT-… codes number each piece of data in the European standard EN 16931.",
        "error": "Error",
        "seller": "Seller",
        "buyer": "Buyer",
        "ids": (("Legal ID", "legal"), ("ID", "global"), ("VAT ID", "vat"), ("E-address", "address")),
        "rows": ("Date", "Due", "Order", "Process"),
        "columns": ("Item", "Qty", "Unit price", "VAT", "Net amount"),
        "no_unit": "{} no unit",
        "allowance": "Allowance",
        "charge": "Charge",
        "no_reason": "no reason",
        "bar": "Processing (BAR): {}",
        "lines_total": "Lines total",
        "allowance_total": "Total allowances",
        "charge_total": "Total charges",
        "net": "Total without VAT",
        "vat": "VAT",
        "gross": "Total with VAT",
        "prepaid": "Paid",
        "rounding": "Rounding",
        "payable": "Amount due",
        "breakdown": "VAT PER RATE",
        "breakdown_columns": ("Rate", "Taxable amount", "VAT"),
        "no_exemption_reason": "Exemption reason missing",
        "notes": "TERMS AND NOTES",
        "no_terms": "Payment terms missing",
        "missing_note": "Note missing: {}",
        "electronic": "Mistake in the electronic data only: this PDF view does not show it",
        "attached": "The electronic data is the XML file attached to this PDF as factur-x.xml (see the PDF's attachments).",
        "compared": "Compared with {}:",
        "in_reference": "in {}: ",
        "not_in_reference": "not in {}",
        "the_reference": "the valid invoice",
        "blank": "blank",
        "no_dates": "no dates",
        "scheme": "scheme {}",
        "no_scheme": "no scheme",
    },
}
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
        "legal": _text(root, f"{p}/ram:SpecifiedLegalOrganization/ram:ID"),
        "siret": _text(root, f"{p}/ram:GlobalID[@schemeID='0009']"),
        "global": _text(root, f"{p}/ram:GlobalID"),
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


# The categories that need an exemption reason (BT-120 or BT-121: BR-E-10, BR-AE-10, BR-IC-10, BR-G-10, BR-O-10).
NEEDS_REASON = {"E", "AE", "K", "G", "O"}


def _adjustment_label(a, t):
    """'Remise', 'Frais · Emballage', or 'Remise · sans motif' when it has neither reason nor reason code."""
    kind = t["charge"] if a["charge"] else t["allowance"]
    if not a["reason"]:
        return f"{kind} · {t['no_reason']}"
    return kind if a["reason"].lower() == kind.lower() else f"{kind} · {a['reason']}"


def read(xml_bytes, t=LABELS["fr"]):
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
        notes.append(t["bar"].format(content) if code == "BAR" else content)
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
        "currency": _text(root, "//ram:ApplicableHeaderTradeSettlement/ram:InvoiceCurrencyCode"),
    }


def _number(value, t, unit=""):
    """The language's formatting that keeps every decimal written in the XML, so a wrong precision stays visible."""
    if not value:
        return t["absent"]
    if not NUMBER.match(value):
        return value
    whole, _, decimals = value.lstrip("-").partition(".")
    grouped = f"{int(whole):,}".replace(",", t["thousands"])
    return ("−" if value.startswith("-") else "") + grouped + (t["decimal"] + decimals if decimals else "") + unit


def _money(value, t, currency="EUR"):
    """An amount in the invoice's currency (BT-5): the € sign for euros, the currency's code otherwise."""
    if value and NUMBER.match(value) and "." not in value:
        value += ".00"
    if not value or not NUMBER.match(value):
        return _number(value, t)
    sign, number = ("−", _number(value[1:], t)) if value.startswith("-") else ("", _number(value, t))
    template = t["money"] if currency == "EUR" else t["money_code"] if currency else "{}"
    return sign + template.format(number, code=currency)


def _date(value, t):
    if re.match(r"^\d{8}$", value or ""):
        return t["date"].format(d=value[6:8], m=value[4:6], y=value[0:4])
    return value or t["absent"]


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
    def __init__(self, c, data, reference, annotate, t, box=None, reference_name=None):
        self.c, self.d, self.ref, self.annotate, self.t = c, data, reference, annotate, t
        self.box, self.reference_name = box, reference_name  # box: what differs, read only when the page needs it
        self.marked = False  # a value drawn in the error colour so far

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
            self.marked = True
            x0 = x if align == "l" else x - w
            self.c.setStrokeColor(ERROR)
            self.c.setLineWidth(0.8)
            self.c.line(x0, y - 2, x0 + w, y - 2)
        return w

    def money(self, value):
        return _money(value, self.t, self.d["currency"])

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
        c.drawCentredString(0, -38, self.t["watermark"])
        c.restoreState()

    def party(self, x, y, title, key, codes):
        p = self.d[key]
        self.text(x, y, title.upper(), "Plex-SemiBold", 7.5, ACCENT)
        self.value(x, y - 16, p["name"] or self.t["absent"], (key, "name"), "Plex-SemiBold", 11)
        self.value(x, y - 29, p["street"], (key, "street"))
        self.value(x, y - 40, p["city"], (key, "city"))
        y -= 56
        for (label, field), bt in zip(self.t["ids"], codes, strict=True):
            if not p[field] and not self.changed((key, field)):
                continue
            self.text(x, y, label, size=7.5, color=MUTED)
            w = self.value(x + 58, y, p[field] or self.t["absent"], (key, field), "Plex-Mono", 8.5)
            self.code(x + 62 + w, y + 0.5, bt)
            y -= 11.5
        return y

    def header(self, rule, description):
        """Above the invoice, before anything else: what this page is and, for an invalid variant, what is wrong.
        Returns the height it takes."""
        c, t = self.c, self.t
        y = H - 30
        self.text(M, y, t["specimen"], "Plex-SemiBold", 7.5, MUTED)
        self.text(M, y - 10, t["source"] + (t["source_error"] if rule else "."), size=7.5, color=MUTED)
        if self.annotate:  # on a line of its own: next to the line above, it would run past the margin
            y -= 10
            self.text(M, y - 10, t["codes"].strip(), size=7.5, color=MUTED)
        y -= 22
        if rule:
            wrapped = simpleSplit(description or "", "Plex", 8.5, W - 2 * M - 20)
            height = 22 + 11 * len(wrapped)
            c.setFillColor(ERROR_FILL)
            c.setStrokeColor(ERROR)
            c.setLineWidth(0.8)
            c.roundRect(M, y - height, W - 2 * M, height, 4, stroke=1, fill=1)
            # "×" and a word: the status never relies on colour alone
            self.text(M + 10, y - 13, f"× {t['error']} · {rule}", "Plex-SemiBold", 8.5, ERROR)
            for i, line in enumerate(wrapped):
                self.text(M + 10, y - 26 - 11 * i, line, size=8.5)
            y -= height + 6
        return H - y

    def draw(self, rule=None, description=None):
        c, d, t = self.c, self.d, self.t
        self.watermark()
        top = self.header(rule, description)
        c.saveState()
        c.translate(0, -(top - 28))  # the invoice starts under the header
        c.setStrokeColor(ACCENT)
        c.setLineWidth(2)
        c.line(M, H - 40, W - M, H - 40)
        self.party(M, H - 60, t["seller"], "seller", ("BT-30", "BT-29", "BT-31", "BT-34"))
        title = t["titles"].get(d["type"], t["titles"]["380"])
        self.value(W - M, H - 66, title.upper(), ("type",), "Plex-SemiBold", 24, "r")
        w = self.value(W - M, H - 84, d["number"] or t["absent"], ("number",), "Plex-Mono", 10, "r")
        self.code(W - M - w - 4, H - 84, "BT-1", "r")
        values = (
            (_date(d["date"], t), "date", "BT-2"),
            (_date(d["due"], t), "due", "BT-9"),
            (d["order"] or t["absent"], "order", "BT-13"),
            (d["framework"] or t["absent"], "framework", "BT-23"),
        )
        # a row empty here and in the valid invoice is left out (an optional value, BT-23 outside France)
        shown = [(label, v) for label, v in zip(t["rows"], values, strict=True) if d[v[1]] or self.changed((v[1],))]
        for i, (label, (v, key, bt)) in enumerate(shown):
            y = H - 102 - i * 12
            self.text(W - M - 80, y, label, size=8, color=MUTED, align="r")
            self.code(W - M - 84 - c.stringWidth(label, "Plex", 8), y, bt, "r")
            self.value(W - M, y, v, (key,), "Plex-Mono", 8.5, "r")
        y = min(self.party(340, H - 170, t["buyer"], "buyer", ("BT-47", "BT-46", "BT-48", "BT-49")), H - 250) - 14
        y = self.lines(y)
        y = min(self.totals(y - 14), self.breakdown(y - 14))
        notes = self.note_rows()
        if self.box is not None and not self.marked and not any(bad for *_, bad in notes):
            y = self.what_differs(y - 8)
        self.notes(y - 24, notes)
        c.restoreState()

    def lines(self, y):
        t = self.t
        cols = (
            (M, "l", "BT-153"),
            (330, "r", "BT-129"),
            (400, "r", "BT-146"),
            (450, "r", "BT-152"),
            (W - M, "r", "BT-131"),
        )
        for label, (x, align, bt) in zip(t["columns"], cols, strict=True):
            self.text(x, y, label, "Plex-SemiBold", 7.5, MUTED, align)
            self.code(x, y + 8, bt, align)
        self.c.setStrokeColor(INK)
        self.c.setLineWidth(0.8)
        self.c.line(M, y - 4, W - M, y - 4)
        y -= 18
        for i, line in enumerate(self.d["lines"]):
            self.value(M, y, line["name"] or t["absent"], ("lines", i, "name"), size=9)
            qty, unit = _number(line["qty"], t), line.get("unit")
            changed = self.changed(("lines", i, "qty")) or self.changed(("lines", i, "unit"))
            self.value(330, y, qty if unit else t["no_unit"].format(qty), (), "Plex-Mono", 8.5, "r", bad=changed)
            self.value(400, y, self.money(line["price"]), ("lines", i, "price"), "Plex-Mono", 8.5, "r")
            self.value(450, y, _number(line["rate"], t, t["percent"]), ("lines", i, "rate"), "Plex-Mono", 8.5, "r")
            self.value(W - M, y, self.money(line["net"]), ("lines", i, "net"), "Plex-Mono", 8.5, "r")
            for j, a in enumerate(line.get("adjustments") or []):
                y -= 13
                keys = ("lines", i, "adjustments", j)
                self.value(
                    M + 12, y, _adjustment_label(a, t), (*keys, "reason"), size=8, bad=None if a["reason"] else True
                )
                sign = "+ " if a["charge"] else "− "
                self.value(W - M, y, sign + self.money(a["amount"]), (*keys, "amount"), "Plex-Mono", 8, "r")
            self.c.setStrokeColor(LINE)
            self.c.setLineWidth(0.5)
            self.c.line(M, y - 6, W - M, y - 6)
            y -= 20
        return y

    def totals(self, y):
        """The totals, from the sum of the lines to the amount due; the optional ones only when the invoice has them."""
        x = 360
        d, t = self.d, self.t
        rows = [(t["lines_total"], ("lines_total",), "BT-106")]
        for i, a in enumerate(d["adjustments"]):
            rows.append((_adjustment_label(a, t), ("adjustments", i, "amount"), "BT-99" if a["charge"] else "BT-92"))
        if d["allowance_total"]:
            rows.append((t["allowance_total"], ("allowance_total",), "BT-107"))
        if d["charge_total"]:
            rows.append((t["charge_total"], ("charge_total",), "BT-108"))
        rows += [(t["net"], ("net",), "BT-109"), (t["vat"], ("vat",), "BT-110"), (t["gross"], ("gross",), "BT-112")]
        if d["prepaid"]:
            rows.append((t["prepaid"], ("prepaid",), "BT-113"))
        if d["rounding"]:
            rows.append((t["rounding"], ("rounding",), "BT-114"))
        rows.append((t["payable"], ("payable",), "BT-115"))
        for label, keys, bt in rows:
            key = keys[0]
            strong = key in ("gross", "payable")
            font, size = ("Plex-SemiBold", 9.5) if strong else ("Plex", 9)
            color = (
                ERROR if label.endswith(t["no_reason"]) else INK if strong else MUTED
            )  # a missing reason is an error
            self.marked |= color == ERROR
            w = self.text(x, y, label, font, size, color)
            self.code(x + w + 4, y + 0.5, bt)
            self.value(W - M, y, self.money(_get(d, keys)), keys, "Plex-Mono", size, "r")
            if key == "vat":
                self.c.setStrokeColor(INK)
                self.c.setLineWidth(0.8)
                self.c.line(x, y - 6, W - M, y - 6)
            y -= 18
        return y

    def breakdown(self, y):
        """The VAT per rate, left of the totals: each category and rate with its taxable amount and VAT, and the
        exemption reason of the categories that need one."""
        d, t = self.d, self.t
        self.text(M, y, t["breakdown"], "Plex-SemiBold", 7.5, ACCENT)
        self.code(M + self.c.stringWidth(t["breakdown"], "Plex-SemiBold", 7.5) + 4, y, "BG-23")
        y -= 14
        cols = ((M, "BT-119"), (M + 190, "BT-116"), (M + 262, "BT-117"))
        for label, (x, bt) in zip(t["breakdown_columns"], cols, strict=True):
            align = "l" if x == M else "r"
            self.text(x, y, label, "Plex-SemiBold", 7.5, MUTED, align)
            self.code(x, y + 8, bt, align)
        y -= 13
        for i, row in enumerate(d["breakdown"]):
            keys = ("breakdown", i)
            name = t["categories"].get(row["category"])
            rate = _number(row["rate"], t, t["percent"])
            self.value(M, y, f"{rate} · {name}" if name else rate, (*keys, "rate"), "Plex-Mono", 8.5)
            self.value(M + 190, y, self.money(row["basis"]), (*keys, "basis"), "Plex-Mono", 8.5, "r")
            self.value(M + 262, y, self.money(row["amount"]), (*keys, "amount"), "Plex-Mono", 8.5, "r")
            if row["category"] in NEEDS_REASON:
                y -= 11
                reason = row["reason"] or t["no_exemption_reason"]
                self.value(M + 12, y, reason, (*keys, "reason"), size=8, bad=None if row["reason"] else True)
                self.code(M + 16 + self.c.stringWidth(reason, "Plex", 8), y + 0.5, "BT-120")
            y -= 13
        return y

    def note_rows(self):
        """The lines of the terms and notes: (text, font, size, in the error colour)."""
        d, ref, t = self.d, self.ref, self.t
        rows = []
        if d["terms"] or self.changed(("terms",)):
            rows.append((d["terms"] or t["no_terms"], "Plex", 8, self.changed(("terms",))))
        if d["iban"] or self.changed(("iban",)):
            iban, bic = d["iban"] or t["absent"], d["bic"] or t["absent"]
            rows.append((f"IBAN {iban}   BIC {bic}", "Plex-Mono", 7.5, self.changed(("iban",))))
        for note in d["notes"]:
            rows.append((note, "Plex", 8, ref is not None and note not in ref["notes"]))
        for note in ref["notes"] if ref else ():
            if note not in d["notes"]:
                rows.append((t["missing_note"].format(note), "Plex", 8, True))
        return rows

    def notes(self, y, rows):
        t = self.t
        self.text(M, y, t["notes"], "Plex-SemiBold", 7.5, ACCENT)
        self.code(M + self.c.stringWidth(t["notes"], "Plex-SemiBold", 7.5) + 4, y, "BT-20, BT-22, BT-84")
        y -= 13
        for text, font, size, bad in rows:
            self.value(M, y, text, (), font, size, bad=bad)
            y -= 11

    def what_differs(self, y):
        """For a page that would show no value in the error colour, the mistake sitting in data it does not draw: a
        box that says the mistake is in the electronic data only, names the file it compares with, and lists each
        element that differs: its business term and its value in the error colour, then its place in the XML and its
        value in that file. Returns the y under the box."""
        c, t = self.c, self.t
        name = self.reference_name or t["the_reference"]
        right = W - M - 10
        rows = []  # each element's lines: the term, label and value; its place and the file's value, side by side
        for d, label in self.box():
            place = c.stringWidth(d.path, "Plex-Mono", 6.5)
            if d.reference_value is None:
                there = (t["not_in_reference"].format(name), "")
            else:
                there = (
                    t["in_reference"].format(name),
                    self.difference(d.kind, d.reference_value, d.reference_attributes),
                )
            width = c.stringWidth(" · " + there[0], "Plex", 7) + c.stringWidth(there[1], "Plex-Mono", 7)
            rows.append((d, label, there, M + 56 + place + width <= right))
        explained = simpleSplit(t["attached"], "Plex", 8, right - M - 10)
        top = 44 + 11 * len(explained)  # from the box's top to the first element's line
        height = top + sum(24 if inline else 34 for *_, inline in rows) - 6
        c.setStrokeColor(ERROR)
        c.setLineWidth(0.8)
        c.roundRect(M, y - height, W - 2 * M, height, 4, stroke=1, fill=0)
        self.text(M + 10, y - 14, t["electronic"], "Plex-SemiBold", 8.5)
        for i, line in enumerate(explained):
            self.text(M + 10, y - 27 - 11 * i, line, size=8, color=MUTED)
        before, after = t["compared"].split("{}")
        compared = y - 27 - 11 * len(explained)
        x = M + 10 + self.text(M + 10, compared, before, size=8, color=MUTED)
        x += self.text(x, compared, name, "Plex-Mono", 8)
        self.text(x, compared, after, size=8, color=MUTED)
        row = y - top
        for d, label, (said, value), inline in rows:
            self.text(M + 10, row, d.term or "", "Plex-Mono", 7, MUTED)
            self.text(M + 56, row, label, size=8, color=MUTED)
            self.value(M + 250, row, self.difference(d.kind, d.value, d.attributes), (), "Plex-Mono", 8.5, bad=True)
            x = M + 56 + self.text(M + 56, row - 11, d.path, "Plex-Mono", 6.5, MUTED)
            if inline:
                x += self.text(x, row - 11, " · " + said, size=7, color=MUTED)
                self.text(x, row - 11, value, "Plex-Mono", 7)
            else:
                x = M + 56 + self.text(M + 56, row - 21, said, size=7, color=MUTED)
                self.text(x, row - 21, value, "Plex-Mono", 7)
            row -= 24 if inline else 34
        return y - height

    def difference(self, kind, value, attributes):
        """An element's value as the box writes it."""
        t = self.t
        if value is None:
            return t["absent"]
        if kind == "period" and not value:
            return t["no_dates"]
        if not value:
            return t["blank"]
        if kind == "date":
            return _date(value, t)
        if kind == "amount":
            return _money(value, t, attributes.get("currencyID") or self.d["currency"])
        if kind == "percent":
            return _number(value, t, t["percent"])
        if kind == "quantity":
            unit = attributes.get("unitCode")
            return _number(value, t) + (f" {unit}" if unit else "")
        if kind == "id":
            scheme = attributes.get("schemeID") or attributes.get("listID")
            return f"{value} · " + (t["scheme"].format(scheme) if scheme else t["no_scheme"])
        if kind == "file":
            return f"{attributes.get('filename', '')} · {attributes.get('mimeCode', t['absent'])}"
        return value


def page_pdf(xml_bytes, reference=None, rule=None, description=None, annotate=False, lang="fr", reference_name=None):
    """The readable page alone, as PDF bytes, its words in lang ("fr" or "en"). reference_name is the file the reader
    can open to compare, named on the page when the mistake sits in data the page does not draw."""
    _fonts()
    t = LABELS[lang]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H), invariant=1, pageCompression=1)

    def box():
        return [(d, getattr(d, lang)) for d in differences(xml_bytes, reference)]

    _Page(
        c,
        read(xml_bytes, t),
        read(reference, t) if reference else None,
        annotate,
        t,
        box if reference else None,
        reference_name,
    ).draw(rule, description)
    c.showPage()
    c.save()
    return buf.getvalue()


def facturx_pdf(
    xml_bytes,
    name="factur-x.xml",
    reference=None,
    rule=None,
    description=None,
    annotate=False,
    lang="fr",
    reference_name=None,
):
    """A Factur-X-style PDF: the readable page, with the XML attached. For an invalid variant, pass the invoice it is
    compared with as reference (and its file's name), and the rule with what is wrong, so the page shows where the
    mistake is."""
    writer = PdfWriter()
    page = page_pdf(xml_bytes, reference, rule, description, annotate, lang, reference_name)
    writer.add_page(PdfReader(io.BytesIO(page)).pages[0])
    writer.add_attachment(name, xml_bytes)
    writer._info = None  # no /Producer, no dates
    writer._ID = ArrayObject([FILE_ID, FILE_ID])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
