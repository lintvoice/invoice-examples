"""Target "fr": a French Factur-X EN 16931 invoice that passes EN 16931, the Factur-X EN 16931 profile rules
and BR-FR, plus one invalid variant per rule.

Each variant changes the baseline as little as possible. Its `fires` lists every rule id the official
rules report on it, so a variant documents its side effects too (for example BR-54 next to BR-FR-27).
"""

import copy
from dataclasses import dataclass, field

from lxml import etree

from .. import cii
from ..cii import BUYER_SIREN, BUYER_SIRET, NS, PAYEE_SIREN, PAYEE_SIRET, SELLER_SIREN, el, gln, luhn_complete

RULES = {
    "EN 16931": "1.3.17 (CII)",
    "Factur-X": "1.09.2, EN 16931 profile",
    "BR-FR": "1.4.0.04 (France_RFE, FNFE-MPE)",
}


@dataclass(frozen=True)
class Variant:
    id: str  # file stem, e.g. "BR-FR-10"
    rule: str  # the rule this variant is about
    fires: tuple  # every rule id the official rules report on it
    en: str  # what is wrong, in English
    fr: str  # the same, in French
    changes: dict = field(default_factory=dict)  # baseline keys to replace
    edit: object = None  # optional function(root) applied to the XML tree


def _ram(tag):
    return f"{{{NS['ram']}}}{tag}"


def _agreement(root):
    return root.find(f".//{_ram('ApplicableHeaderTradeAgreement')}")


def _add_documents(*docs):
    """Add AdditionalReferencedDocument elements (BG-24, BT-18): (issuer id, type code, name or None, reference type or None)."""

    def edit(root):
        agreement = _agreement(root)
        for issuer_id, type_code, name, reference_type in docs:
            d = el(agreement, "ram:AdditionalReferencedDocument")
            el(d, "ram:IssuerAssignedID", issuer_id)
            el(d, "ram:TypeCode", type_code)
            if name:
                el(d, "ram:Name", name)
            if reference_type:
                el(d, "ram:ReferenceTypeCode", reference_type)

    return edit


def _add_characteristic(description, value):
    """Add an item attribute (BG-32) to the first line."""

    def edit(root):
        product = root.find(f".//{_ram('SpecifiedTradeProduct')}")
        ch = el(product, "ram:ApplicableProductCharacteristic")
        if description is not None:
            el(ch, "ram:Description", description)
        if value is not None:
            el(ch, "ram:Value", value)

    return edit


def _add_invoice_reference(issuer_id, date="20260915"):
    """Reference a preceding invoice (BG-3: BT-25, BT-26), at the end of the header settlement."""

    def edit(root):
        settlement = root.find(f".//{_ram('ApplicableHeaderTradeSettlement')}")
        ref = el(settlement, "ram:InvoiceReferencedDocument")
        el(ref, "ram:IssuerAssignedID", issuer_id)
        el(el(ref, "ram:FormattedIssueDateTime"), "qdt:DateTimeString", date, format="102")

    return edit


def _drop_scheme(party_tag):
    """Remove the schemeID of a party's GlobalID."""

    def edit(root):
        for gid in root.iter(_ram("GlobalID")):
            if gid.getparent().tag == _ram(party_tag):
                gid.attrib.pop("schemeID", None)

    return edit


def _rewrite_amount(tag, text):
    """Write a header monetary total with another notation (e.g. 3 decimals)."""

    def edit(root):
        for node in root.iter(_ram(tag)):
            if node.getparent().tag == _ram("SpecifiedTradeSettlementHeaderMonetarySummation"):
                node.text = text

    return edit


def _set_amount(tag, delta):
    """Add delta to a header monetary total (e.g. GrandTotalAmount)."""

    def edit(root):
        for node in root.iter(_ram(tag)):
            if node.getparent().tag == _ram("SpecifiedTradeSettlementHeaderMonetarySummation"):
                node.text = f"{float(node.text) + delta:.2f}"

    return edit


def _edit_all(*edits):
    def edit(root):
        for e in edits:
            e(root)

    return edit


def _new(tag, text=None, **attrs):
    prefix, name = tag.split(":")
    node = etree.Element(f"{{{NS[prefix]}}}{name}", attrs)
    if text is not None:
        node.text = text
    return node


def _sub(parent, tag, text=None, **attrs):
    node = _new(tag, text, **attrs)
    parent.append(node)
    return node


def _first(root, *path):
    """The first element at the end of a chain of ram: tags."""
    return root.find(".//" + "/".join(_ram(t) for t in path))


def _insert(parent, node, before=None, after=None):
    """Insert node before the first child named `before`, or after the last child named `after`, else at the end."""
    if before is not None and parent.find(_ram(before)) is not None:
        parent.find(_ram(before)).addprevious(node)
    elif after is not None and parent.findall(_ram(after)):
        parent.findall(_ram(after))[-1].addnext(node)
    else:
        parent.append(node)


def _party(tag, name, global_ids, legal_id=None):
    node = _new(f"ram:{tag}")
    for value, scheme in global_ids:
        _sub(node, "ram:GlobalID", value, **({"schemeID": scheme} if scheme else {}))
    _sub(node, "ram:Name", name)
    if legal_id:
        _sub(_sub(node, "ram:SpecifiedLegalOrganization"), "ram:ID", legal_id, schemeID="0002")
    return node


def _add_payee(global_ids, legal_id=None):
    """Add a payee (BG-10), a factoring company, before the payment means."""

    def edit(root):
        _insert(
            _first(root, "ApplicableHeaderTradeSettlement"),
            _party("PayeeTradeParty", "Affacturage Exemple", global_ids, legal_id),
            before="SpecifiedTradeSettlementPaymentMeans",
        )

    return edit


def _add_ship_to(global_ids):
    """Add a deliver-to party (BG-13) with location identifiers (BT-71)."""

    def edit(root):
        _first(root, "ApplicableHeaderTradeDelivery").insert(
            0, _party("ShipToTradeParty", "Médiathèque d'Exemple", global_ids)
        )

    return edit


def _add_global_id(party_tag, value, scheme):
    """Add a second GlobalID to a party, after the first one."""

    def edit(root):
        _insert(_first(root, party_tag), _new("ram:GlobalID", value, schemeID=scheme), after="GlobalID")

    return edit


def _billing_period(start, end):
    """Add the invoicing period (BG-14: BT-73, BT-74) after the VAT breakdown."""

    def edit(root):
        period = _new("ram:BillingSpecifiedPeriod")
        _sub(_sub(period, "ram:StartDateTime"), "udt:DateTimeString", start, format="102")
        _sub(_sub(period, "ram:EndDateTime"), "udt:DateTimeString", end, format="102")
        _insert(_first(root, "ApplicableHeaderTradeSettlement"), period, after="ApplicableTradeTax")

    return edit


def _tax_point_date(value):
    """Give each VAT breakdown a VAT point date (BT-7); use with due_date_type None (BT-7 and BT-8 exclude each other)."""

    def edit(root):
        for tax in _first(root, "ApplicableHeaderTradeSettlement").iterfind(_ram("ApplicableTradeTax")):
            point = _new("ram:TaxPointDate")
            _sub(point, "udt:DateString", value, format="102")
            _insert(tax, point, before="RateApplicablePercent")

    return edit


def _set_text(*path, text):
    """Rewrite the text of the first element at the end of a ram: path."""

    def edit(root):
        _first(root, *path).text = text

    return edit


def _add_element(path, tag, text, before=None, after=None, **attrs):
    """Add a ram: element inside the first element at the end of path."""

    def edit(root):
        _insert(_first(root, *path), _new(f"ram:{tag}", text, **attrs), before=before, after=after)

    return edit


def _prepaid(amount, due):
    """Add a paid amount (BT-113) and set the amount due (BT-115)."""

    def edit(root):
        sums = _first(root, "SpecifiedTradeSettlementHeaderMonetarySummation")
        _insert(sums, _new("ram:TotalPrepaidAmount", amount), before="DuePayableAmount")
        sums.find(_ram("DuePayableAmount")).text = due

    return edit


def _paid_without_due_date(root):
    """Already paid: paid amount = total with VAT, nothing due, and no payment due date (BT-9)."""
    sums = _first(root, "SpecifiedTradeSettlementHeaderMonetarySummation")
    _prepaid(sums.find(_ram("GrandTotalAmount")).text, "0.00")(root)
    terms = _first(root, "SpecifiedTradePaymentTerms")
    terms.remove(terms.find(_ram("DueDateDateTime")))


def _gross_price(gross, discount):
    """Give the first line a gross price (BT-148) and a price discount (BT-147); the net price stays."""

    def edit(root):
        price = _new("ram:GrossPriceProductTradePrice")
        _sub(price, "ram:ChargeAmount", gross)
        ac = _sub(price, "ram:AppliedTradeAllowanceCharge")
        _sub(_sub(ac, "ram:ChargeIndicator"), "udt:Indicator", "false")
        _sub(ac, "ram:ActualAmount", discount)
        _insert(_first(root, "SpecifiedLineTradeAgreement"), price, before="NetPriceProductTradePrice")

    return edit


NOTES = cii.FRENCH["notes"]
BAR_B2B = ("BAR", "B2B")
SELLER, BUYER = cii.FRENCH["seller"], cii.FRENCH["buyer"]
ALLOWANCE = [("10.25", "95", "Remise commerciale", "S", "20")]  # 1 % of 1025.00
CHARGE = [("15.00", "FC", "Frais de port", "S", "20")]
DISCOUNTED_LINES = [
    ("Atelier de formation", "2", "450.00", "S", "20", "50.00"),
    ("Support de cours", "10", "12.50", "S", "20"),
]
SELLER_SIRET_2 = luhn_complete(SELLER_SIREN + "0002")
BUYER_SIRET_2 = luhn_complete(BUYER_SIREN + "0003")  # also the deliver-to establishment
SPACED_SIRET = f"{BUYER_SIRET_2[:3]} {BUYER_SIRET_2[3:6]} {BUYER_SIRET_2[6:9]} {BUYER_SIRET_2[9:]}"

VARIANTS = (
    Variant(
        "BR-FR-01",
        "BR-FR-01",
        ("BR-FR-01_BT-1",),
        "The invoice number (BT-1) is longer than 35 characters.",
        "Le numéro de facture (BT-1) dépasse 35 caractères.",
        {"number": "F2026-" + "0" * 30},
    ),
    Variant(
        "BR-FR-02",
        "BR-FR-02",
        ("BR-FR-02_BT-1",),
        "The invoice number (BT-1) contains a character outside letters, digits and + - _ /.",
        "Le numéro de facture (BT-1) contient un caractère autre que lettres, chiffres et + - _ /.",
        {"number": "F2026.0042"},
    ),
    Variant(
        "BR-FR-03",
        "BR-FR-03",
        ("BR-FR-03_BT-2",),
        "The issue date (BT-2) has a year outside 2000-2099.",
        "La date d'émission (BT-2) a une année hors de 2000-2099.",
        {"issue_date": "19991231"},
    ),
    Variant(
        "BR-FR-04",
        "BR-FR-04",
        ("BR-FR-04_BT-3",),
        "The document type code (BT-3) is 326 (partial invoice), valid in EN 16931 but not in the French list.",
        "Le code type de document (BT-3) est 326 (facture partielle), valide en EN 16931 mais absent de la liste française.",
        {"type_code": "326"},
    ),
    Variant(
        "BR-FR-05-PMT",
        "BR-FR-05",
        ("BR-FR-05_BT-22_PMT",),
        "The note about the fixed recovery fee (subject code PMT) is missing.",
        "La mention de l'indemnité forfaitaire pour frais de recouvrement (code PMT) est absente.",
        {"notes": [n for n in NOTES if n[0] != "PMT"]},
    ),
    Variant(
        "BR-FR-05-PMD",
        "BR-FR-05",
        ("BR-FR-05_BT-22_PMD",),
        "The note about late payment penalties (subject code PMD) is missing.",
        "La mention des pénalités de retard (code PMD) est absente.",
        {"notes": [n for n in NOTES if n[0] != "PMD"]},
    ),
    Variant(
        "BR-FR-05-AAB",
        "BR-FR-05",
        ("BR-FR-05_BT-22_AAB",),
        "The note about early payment discount (subject code AAB) is missing.",
        "La mention relative à l'escompte (code AAB) est absente.",
        {"notes": [n for n in NOTES if n[0] != "AAB"]},
    ),
    Variant(
        "BR-FR-06",
        "BR-FR-06",
        ("BR-FR-06_BT-21_PMT",),
        "Two notes have the subject code PMT.",
        "Deux mentions ont le code sujet PMT.",
        {"notes": [*NOTES, ("PMT", "Indemnité forfaitaire : 40 EUR.")]},
    ),
    Variant(
        "BR-FR-08",
        "BR-FR-08",
        ("BR-FR-08_BT-23",),
        "The billing framework (BT-23, cadre de facturation) is missing.",
        "Le cadre de facturation (BT-23) est absent.",
        {"billing_frame": None},
    ),
    Variant(
        "BR-FR-09",
        "BR-FR-09",
        ("BR-FR-09_BT-29",),
        "The seller's SIRET (BT-29) does not start with its SIREN (BT-30).",
        "Le SIRET du vendeur (BT-29) ne commence pas par son SIREN (BT-30).",
        {"seller": {**SELLER, "global_id": (BUYER_SIRET, "0009")}},
    ),
    Variant(
        "BR-FR-10",
        "BR-FR-10",
        ("BR-FR-10_BT-30",),
        "The seller's SIREN (BT-30) is missing (and so is its SIRET, BT-29).",
        "Le SIREN du vendeur (BT-30) est absent (son SIRET, BT-29, aussi).",
        {"seller": {**SELLER, "legal_id": None, "global_id": None}},
    ),
    Variant(
        "BR-FR-11",
        "BR-FR-11",
        ("BR-FR-11_BT-47",),
        "The invoice is B2B (note BAR = B2B) but the buyer's SIREN (BT-47) is missing.",
        "La facture est B2B (mention BAR = B2B) mais le SIREN de l'acheteur (BT-47) est absent.",
        {"notes": [*NOTES, BAR_B2B], "buyer": {**BUYER, "legal_id": None, "global_id": None}},
    ),
    Variant(
        "BR-FR-12",
        "BR-FR-12",
        ("BR-FR-12_BT-49",),
        "The buyer's electronic address (BT-49) is missing.",
        "L'adresse électronique de l'acheteur (BT-49) est absente.",
        {"buyer": {**BUYER, "endpoint": None}},
    ),
    Variant(
        "BR-FR-13",
        "BR-FR-13",
        ("BR-FR-13_BT-34",),
        "The seller's electronic address (BT-34) is missing.",
        "L'adresse électronique du vendeur (BT-34) est absente.",
        {"seller": {**SELLER, "endpoint": None}},
    ),
    Variant(
        "BR-FR-16",
        "BR-FR-16",
        ("BR-FR-16_BT-119", "BR-FR-16_BT-152"),
        "The VAT rate is 21 %, which is not a French rate (lines BT-152 and breakdown BT-119).",
        "Le taux de TVA est 21 %, qui n'est pas un taux français (lignes BT-152 et ventilation BT-119).",
        {"lines": [("Atelier de formation", "2", "450.00", "S", "21")]},
    ),
    Variant(
        "BR-FR-17",
        "BR-FR-17",
        ("BR-FR-17_BT-123",),
        "An attachment (BT-123) is qualified with a code outside the French list.",
        "Une pièce jointe (BT-123) est qualifiée par un code hors de la liste française.",
        edit=_add_documents(("PJ-1", "916", "CONTRAT", None)),
    ),
    Variant(
        "BR-FR-18",
        "BR-FR-18",
        ("BR-FR-18_BT-123",),
        "Two attachments are described as LISIBLE (BT-123): only one readable copy is allowed.",
        "Deux pièces jointes sont décrites LISIBLE (BT-123) : une seule version lisible est permise.",
        edit=_add_documents(("PJ-1", "916", "LISIBLE", None), ("PJ-2", "916", "LISIBLE", None)),
    ),
    Variant(
        "BR-FR-20",
        "BR-FR-20",
        ("BR-FR-20_BT-21",),
        "The note BAR (BT-21) has a value outside B2B, B2BINT, B2C, B2CINT, OUTOFSCOPE, ARCHIVEONLY.",
        "La mention BAR (BT-21) a une valeur hors de B2B, B2BINT, B2C, B2CINT, OUTOFSCOPE, ARCHIVEONLY.",
        {"notes": [*NOTES, ("BAR", "B2G")]},
    ),
    Variant(
        "BR-FR-21",
        "BR-FR-21",
        ("BR-FR-21_BT-49",),
        "The invoice is B2B but the buyer's electronic address (BT-49) does not start with its SIREN.",
        "La facture est B2B mais l'adresse électronique de l'acheteur (BT-49) ne commence pas par son SIREN.",
        {"notes": [*NOTES, BAR_B2B], "buyer": {**BUYER, "endpoint": ("999999999", "0225")}},
    ),
    Variant(
        "BR-FR-23",
        "BR-FR-23",
        ("BR-FR-23_BT-34",),
        "The seller's electronic address (BT-34) contains a character outside letters, digits and - _ .",
        "L'adresse électronique du vendeur (BT-34) contient un caractère autre que lettres, chiffres et - _ .",
        {"seller": {**SELLER, "endpoint": (SELLER["legal_id"][0] + "@factures", "0225")}},
    ),
    Variant(
        "BR-FR-25",
        "BR-FR-25",
        ("BR-FR-25_BT-34",),
        "The seller's electronic address (BT-34) is longer than 125 characters.",
        "L'adresse électronique du vendeur (BT-34) dépasse 125 caractères.",
        {"seller": {**SELLER, "endpoint": (SELLER["legal_id"][0] + "_" + "x" * 120, "0225")}},
    ),
    Variant(
        "BR-FR-27",
        "BR-FR-27",
        ("BR-FR-27_BT-160",),
        "An item attribute (BG-32) has an empty name (BT-160).",
        "Un attribut d'article (BG-32) a un nom vide (BT-160).",
        edit=_add_characteristic(" ", "Bleu"),
    ),
    Variant(
        "BR-FR-29",
        "BR-FR-29",
        ("BR-FR-29_BT-18",),
        "Two invoiced object identifiers (BT-18) use the reference type AFL.",
        "Deux identifiants d'objet facturé (BT-18) utilisent le type de référence AFL.",
        edit=_add_documents(("OBJ-1", "130", None, "AFL"), ("OBJ-2", "130", None, "AFL")),
    ),
    Variant(
        "BR-FR-31",
        "BR-FR-31",
        ("BR-FR-31_BT-21",),
        "Two notes have the subject code BAR.",
        "Deux mentions ont le code sujet BAR.",
        {"notes": [*NOTES, BAR_B2B, ("BAR", "B2C")]},
    ),
    Variant(
        "BR-FR-32",
        "BR-FR-32",
        ("BR-FR-32-LEGALID",),
        "The buyer's identifier with scheme 0002 (SIREN, BT-47) does not have 9 digits.",
        "L'identifiant de l'acheteur au schéma 0002 (SIREN, BT-47) n'a pas 9 chiffres.",
        {"buyer": {**BUYER, "legal_id": (BUYER_SIREN + "0", "0002"), "global_id": None}},
    ),
    Variant(
        "BR-FR-CO-07",
        "BR-FR-CO-07",
        ("BR-FR-CO-07_BT-9",),
        "The payment due date (BT-9) is before the issue date (BT-2).",
        "La date d'échéance (BT-9) est antérieure à la date d'émission (BT-2).",
        {"due_date": "20261001"},
    ),
    Variant(
        "BR-FR-CO-12",
        "BR-FR-CO-12",
        ("BR-FR-CO-12_BT-5",),
        "The invoice is in USD but gives no VAT accounting currency EUR (BT-6) and no VAT total in EUR.",
        "La facture est en USD mais n'indique ni devise de comptabilisation de la TVA en EUR (BT-6) ni total de TVA en EUR.",
        {"currency": "USD"},
    ),
    Variant(
        "BR-FR-DEC-02",
        "BR-FR-DEC-02",
        ("BR-FR-DEC-02_BT-129",),
        "The invoiced quantity (BT-129) has more than 4 decimals.",
        "La quantité facturée (BT-129) a plus de 4 décimales.",
        {"lines": [("Atelier de formation", "2.00001", "450.00", "S", "20")]},
    ),
    Variant(
        "BR-FR-09-buyer",
        "BR-FR-09",
        ("BR-FR-09_BT-46",),
        "The buyer's SIRET (BT-46) does not start with its SIREN (BT-47).",
        "Le SIRET de l'acheteur (BT-46) ne commence pas par son SIREN (BT-47).",
        {"buyer": {**BUYER, "global_id": (SELLER["global_id"][0], "0009")}},
    ),
    Variant(
        "BR-FR-23-buyer",
        "BR-FR-23",
        ("BR-FR-23_BT-49",),
        "The buyer's electronic address (BT-49) contains a character outside letters, digits and - _ .",
        "L'adresse électronique de l'acheteur (BT-49) contient un caractère autre que lettres, chiffres et - _ .",
        {"buyer": {**BUYER, "endpoint": (BUYER["legal_id"][0] + "/compta", "0225")}},
    ),
    Variant(
        "BR-FR-24",
        "BR-FR-24",
        ("BR-FR-24_BT-29",),
        "The seller's private identifier (BT-29, scheme 0224) contains a space.",
        "L'identifiant privé du vendeur (BT-29, schéma 0224) contient une espace.",
        {"seller": {**SELLER, "global_id": ("ATELIER 42", "0224")}},
    ),
    Variant(
        "BR-FR-26",
        "BR-FR-26",
        ("BR-FR-26_BT-29",),
        "The seller's private identifier (BT-29, scheme 0224) is longer than 100 characters.",
        "L'identifiant privé du vendeur (BT-29, schéma 0224) dépasse 100 caractères.",
        {"seller": {**SELLER, "global_id": ("A" * 101, "0224")}},
    ),
    Variant(
        "BR-FR-CO-05",
        "BR-FR-CO-05",
        ("BR-FR-CO-05_BT-3",),
        "A credit note (BT-3 = 381) does not reference the invoice it corrects (BT-25).",
        "Un avoir (BT-3 = 381) ne référence pas la facture qu'il corrige (BT-25).",
        {"type_code": "381"},
    ),
    Variant(
        "BR-FR-DEC-04",
        "BR-FR-DEC-04",
        ("BR-FR-DEC-04_BT-119", "BR-FR-DEC-04_BT-152", "BR-FR-16_BT-119", "BR-FR-16_BT-152"),
        "The VAT rate is written with 3 decimals (20.000): more than 2, and not in the list of French rates as written.",
        "Le taux de TVA est écrit avec 3 décimales (20.000) : plus de 2, et absent de la liste des taux français tel qu'écrit.",
        {"lines": [("Atelier de formation", "2", "450.00", "S", "20.000")]},
    ),
    Variant(
        "BR-FR-01-BT-25",
        "BR-FR-01",
        ("BR-FR-01_BT-25",),
        "The preceding invoice reference (BT-25) is longer than 35 characters.",
        "La référence de la facture antérieure (BT-25) dépasse 35 caractères.",
        edit=_add_invoice_reference("F2026-" + "0" * 30),
    ),
    Variant(
        "BR-FR-02-BT-25",
        "BR-FR-02",
        ("BR-FR-02_BT-25",),
        "The preceding invoice reference (BT-25) contains a character outside letters, digits and + - _ /.",
        "La référence de la facture antérieure (BT-25) contient un caractère autre que lettres, chiffres et + - _ /.",
        edit=_add_invoice_reference("F2026.0001"),
    ),
    Variant(
        "BR-FR-03-BT-9",
        "BR-FR-03",
        ("BR-FR-03_BT-9",),
        "The payment due date (BT-9) has a year outside 2000-2099.",
        "La date d'échéance (BT-9) a une année hors de 2000-2099.",
        {"due_date": "21000101"},
    ),
    Variant(
        "BR-FR-03-BT-26",
        "BR-FR-03",
        ("BR-FR-03_BT-26",),
        "The preceding invoice issue date (BT-26) has a year outside 2000-2099.",
        "La date d'émission de la facture antérieure (BT-26) a une année hors de 2000-2099.",
        edit=_add_invoice_reference("F2026-0001", "19990915"),
    ),
    Variant(
        "BR-FR-03-BT-72",
        "BR-FR-03",
        ("BR-FR-03_BT-72",),
        "The actual delivery date (BT-72) has a year outside 2000-2099.",
        "La date de livraison effective (BT-72) a une année hors de 2000-2099.",
        {"delivery_date": "19991015"},
    ),
    Variant(
        "BR-FR-06-PMD",
        "BR-FR-06",
        ("BR-FR-06_BT-21_PMD",),
        "Two notes have the subject code PMD.",
        "Deux mentions ont le code sujet PMD.",
        {"notes": [*NOTES, ("PMD", "Pénalités de retard : taux légal majoré.")]},
    ),
    Variant(
        "BR-FR-06-AAB",
        "BR-FR-06",
        ("BR-FR-06_BT-21_AAB",),
        "Two notes have the subject code AAB.",
        "Deux mentions ont le code sujet AAB.",
        {"notes": [*NOTES, ("AAB", "Escompte : néant.")]},
    ),
    Variant(
        "BR-FR-25-buyer",
        "BR-FR-25",
        ("BR-FR-25_BT-49",),
        "The buyer's electronic address (BT-49) is longer than 125 characters.",
        "L'adresse électronique de l'acheteur (BT-49) dépasse 125 caractères.",
        {"buyer": {**BUYER, "endpoint": (BUYER["legal_id"][0] + "_" + "x" * 120, "0225")}},
    ),
    Variant(
        "BR-FR-29-AFL",
        "BR-FR-29",
        ("BR-FR-29_AFL", "BR-52"),
        "An invoiced object identifier (BT-18) of type AFL is blank (EN 16931 BR-52 fires too: a document reference is required).",
        "Un identifiant d'objet facturé (BT-18) de type AFL est vide (la règle EN 16931 BR-52 se déclenche aussi : une référence est exigée).",
        edit=_add_documents((" ", "130", None, "AFL")),
    ),
    Variant(
        "BR-FR-32-GLOBALID",
        "BR-FR-32",
        ("BR-FR-32-GLOBALID",),
        "The seller's identifier with scheme 0002 (BT-29) does not have 9 digits.",
        "L'identifiant du vendeur au schéma 0002 (BT-29) n'a pas 9 chiffres.",
        {"seller": {**SELLER, "global_id": (SELLER_SIREN[:8], "0002")}},
    ),
    Variant(
        "BR-FR-CO-04",
        "BR-FR-CO-04",
        ("BR-FR-CO-04_BT-4",),
        "A corrective invoice (BT-3 = 384) does not reference exactly one preceding invoice (BT-25).",
        "Une facture rectificative (BT-3 = 384) ne référence pas exactement une facture antérieure (BT-25).",
        {"type_code": "384"},
    ),
    Variant(
        "BR-FR-CO-08",
        "BR-FR-CO-08",
        ("BR-FR-CO-08_BT-23",),
        "A prepayment invoice (BT-3 = 386) uses a final-invoice-after-deposit framework (BT-23 = S4).",
        "Une facture d'acompte (BT-3 = 386) utilise un cadre de facture définitive après acompte (BT-23 = S4).",
        {"type_code": "386", "billing_frame": "S4"},
    ),
    Variant(
        "BR-FR-CO-09",
        "BR-FR-CO-09",
        ("BR-FR-CO-09_BT-23-1", "BR-FR-CO-09_BT-23-2"),
        "The framework says already paid (BT-23 = S2), but the paid amount (BT-113) is not the total and the amount due (BT-115) is not 0.",
        "Le cadre indique une facture déjà payée (BT-23 = S2), mais le montant payé (BT-113) n'est pas le total et le net à payer (BT-115) n'est pas 0.",
        {"billing_frame": "S2"},
    ),
    Variant(
        "BR-FR-DEC-03",
        "BR-FR-DEC-03",
        ("BR-FR-DEC-03_BT-146",),
        "The item net price (BT-146) has more than 6 decimals.",
        "Le prix net de l'article (BT-146) a plus de 6 décimales.",
        {"lines": [("Atelier de formation", "2", "450.0000001", "S", "20")]},
    ),
    Variant(
        "BR-FR-15",
        "BR-FR-15",
        ("BR-FR-15_BT-95_BT-151", "BR-FR-15_BT-95_BT-151_LM", "BR-FR-15_BT-95_BT-118", "BR-FR-15_BT-95_BT-118_LM"),
        "The line and the VAT breakdown use VAT category L (Canary Islands), which does not apply in France.",
        "La ligne et la ventilation de TVA utilisent la catégorie L (îles Canaries), qui ne s'applique pas en France.",
        {"lines": [("Atelier de formation", "2", "450.00", "L", "7")]},
    ),
    Variant(
        "BR-FR-22",
        "BR-FR-22",
        ("BR-FR-22_BT-34",),
        "A B2B self-billed invoice (BT-3 = 389): the seller's electronic address (BT-34) does not start with its SIREN.",
        "Une autofacture B2B (BT-3 = 389) : l'adresse électronique du vendeur (BT-34) ne commence pas par son SIREN.",
        {"type_code": "389", "notes": [*NOTES, BAR_B2B], "seller": {**SELLER, "endpoint": ("999999999", "0225")}},
    ),
    Variant(
        "BR-FR-CO-03",
        "BR-FR-CO-03",
        ("BR-FR-CO-03_BT-3",),
        "A document of type 262 gives no contract reference (BT-12) and no billing period (BT-73, BT-74).",
        "Un document de type 262 n'indique ni référence de contrat (BT-12) ni période de facturation (BT-73, BT-74).",
        {"type_code": "262"},
    ),
    Variant(
        "BR-FR-CO-10",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-29-1", "FX-SCH-A-000440"),
        "The seller's identifier (BT-29) has no scheme identifier (BT-29-1); the Factur-X profile rules reject it too.",
        "L'identifiant du vendeur (BT-29) n'a pas d'identifiant de schéma (BT-29-1) ; les règles du profil Factur-X le refusent aussi.",
        edit=_drop_scheme("SellerTradeParty"),
    ),
    Variant(
        "BR-FR-DEC-01",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-112", "BR-FR-DEC-01_BT-115", "BR-DEC-14", "BR-DEC-18"),
        "The total with VAT (BT-112) and the amount due (BT-115) are written with 3 decimals (EN 16931 BR-DEC-14 and BR-DEC-18 fire too).",
        "Le total TTC (BT-112) et le net à payer (BT-115) sont écrits avec 3 décimales (les règles EN 16931 BR-DEC-14 et BR-DEC-18 se déclenchent aussi).",
        edit=_edit_all(
            _rewrite_amount("GrandTotalAmount", "1230.000"), _rewrite_amount("DuePayableAmount", "1230.000")
        ),
    ),
    Variant(
        "BR-CO-15",
        "BR-CO-15",
        ("BR-CO-15",),
        "The invoice total with VAT (BT-112) is not the total without VAT (BT-109) plus the VAT total (BT-110).",
        "Le total TTC (BT-112) n'est pas égal au total HT (BT-109) plus le total de TVA (BT-110).",
        edit=_edit_all(_set_amount("GrandTotalAmount", 1), _set_amount("DuePayableAmount", 1)),
    ),
    Variant(
        "BR-FR-03-BT-7",
        "BR-FR-03",
        ("BR-FR-03_BT-7",),
        "The VAT point date (BT-7) has a year outside 2000-2099.",
        "La date d'exigibilité de la TVA (BT-7) a une année hors de 2000-2099.",
        {"due_date_type": None},
        edit=_tax_point_date("19991020"),
    ),
    Variant(
        "BR-FR-03-BT-73",
        "BR-FR-03",
        ("BR-FR-03_BT-73",),
        "The invoicing period start date (BT-73) has a year outside 2000-2099.",
        "La date de début de la période de facturation (BT-73) a une année hors de 2000-2099.",
        edit=_billing_period("19991001", "20261031"),
    ),
    Variant(
        "BR-FR-03-BT-74",
        "BR-FR-03",
        ("BR-FR-03_BT-74",),
        "The invoicing period end date (BT-74) has a year outside 2000-2099.",
        "La date de fin de la période de facturation (BT-74) a une année hors de 2000-2099.",
        edit=_billing_period("20261001", "21001031"),
    ),
    Variant(
        "BR-FR-06-TXD",
        "BR-FR-06",
        ("BR-FR-06_BT-21_TXD",),
        "Two notes have the subject code TXD.",
        "Deux mentions ont le code sujet TXD.",
        {"notes": [*NOTES, ("TXD", "TVA acquittée sur les débits."), ("TXD", "TVA acquittée sur les débits.")]},
    ),
    Variant(
        "BR-FR-09-payee",
        "BR-FR-09",
        ("BR-FR-09_BT-60",),
        "The payee's SIRET (BT-60) does not start with its SIREN: it is the seller's SIRET.",
        "Le SIRET du bénéficiaire (BT-60) ne commence pas par son SIREN : c'est celui du vendeur.",
        edit=_add_payee([(SELLER["global_id"][0], "0009")], PAYEE_SIREN),
    ),
    Variant(
        "BR-FR-09-ship-to",
        "BR-FR-09",
        ("BR-FR-09_BT-71",),
        "The deliver-to location identifier with scheme 0009 (SIRET, BT-71) is not 14 digits: it has spaces.",
        "L'identifiant du lieu de livraison au schéma 0009 (SIRET, BT-71) n'a pas 14 chiffres : il contient des espaces.",
        edit=_add_ship_to([(SPACED_SIRET, "0009")]),
    ),
    Variant(
        "BR-FR-15-allowance",
        "BR-FR-15",
        ("BR-FR-15_BT-95_BT-102", "BR-FR-15_BT-95_BT-102_LM", "BR-FR-15_BT-95_BT-118", "BR-FR-15_BT-95_BT-118_LM"),
        "A document level allowance (BT-95), and so its VAT breakdown (BT-118), has the VAT category L (Canary Islands), not used in France.",
        "Une remise au niveau du document (BT-95), et donc sa ventilation de TVA (BT-118), a la catégorie L (îles Canaries), non utilisée en France.",
        {"allowances": [("10.25", "95", "Remise commerciale", "L", "7")]},
    ),
    Variant(
        "BR-FR-16-allowance",
        "BR-FR-16",
        ("BR-FR-16_BT-96_BT-103", "BR-FR-16_BT-119"),
        "A document level allowance (BT-96), and so its VAT breakdown (BT-119), has a VAT rate of 21 %, not a French rate.",
        "Une remise au niveau du document (BT-96), et donc sa ventilation de TVA (BT-119), a un taux de 21 %, qui n'est pas un taux français.",
        {"allowances": [("10.25", "95", "Remise commerciale", "S", "21")]},
    ),
    Variant(
        "BR-FR-DEC-04-allowance",
        "BR-FR-DEC-04",
        ("BR-FR-DEC-04_BT-96_BT-103", "BR-FR-16_BT-96_BT-103"),
        "A document level allowance's VAT rate (BT-96) has 3 decimals (20.000); BR-FR-16 rejects it too, as 20.000 is not in its list of rates.",
        "Le taux de TVA d'une remise au niveau du document (BT-96) a 3 décimales (20.000) ; BR-FR-16 le refuse aussi, 20.000 n'étant pas dans sa liste de taux.",
        {"allowances": ALLOWANCE},
        edit=_set_text("SpecifiedTradeAllowanceCharge", "CategoryTradeTax", "RateApplicablePercent", text="20.000"),
    ),
    Variant(
        "BR-FR-24-buyer",
        "BR-FR-24",
        ("BR-FR-24_BT-46",),
        "The buyer's identifier with scheme 0224 (BT-46) contains a space.",
        "L'identifiant de l'acheteur au schéma 0224 (BT-46) contient une espace.",
        {"buyer": {**BUYER, "global_id": ("MAIRIE 42", "0224")}},
    ),
    Variant(
        "BR-FR-26-buyer",
        "BR-FR-26",
        ("BR-FR-26_BT-46",),
        "The buyer's identifier with scheme 0224 (BT-46) is longer than 100 characters.",
        "L'identifiant de l'acheteur au schéma 0224 (BT-46) dépasse 100 caractères.",
        {"buyer": {**BUYER, "global_id": ("M" * 101, "0224")}},
    ),
    Variant(
        "BR-FR-29-AVV",
        "BR-FR-29",
        ("BR-FR-29_AVV", "BR-52"),
        "An invoiced object identifier (BT-18) with reference type AVV is blank (EN 16931 rule BR-52 fires too: a reference is required).",
        "Un identifiant d'objet facturé (BT-18) de type AVV est vide (la règle EN 16931 BR-52 se déclenche aussi : une référence est exigée).",
        edit=_add_documents((" ", "130", None, "AVV")),
    ),
    Variant(
        "BR-FR-CO-09-BT-9",
        "BR-FR-CO-09",
        ("BR-FR-CO-09_BT-23-3",),
        "An already paid invoice (billing frame S2) has no payment due date (BT-9).",
        "Une facture déjà payée (cadre de facturation S2) n'a pas de date d'échéance (BT-9).",
        {"billing_frame": "S2"},
        edit=_paid_without_due_date,
    ),
    Variant(
        "BR-FR-CO-10-BT-29-2",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-29-2",),
        "The seller has two identifiers (BT-29) with the same scheme 0009.",
        "Le vendeur a deux identifiants (BT-29) au même schéma 0009.",
        edit=_add_global_id("SellerTradeParty", SELLER_SIRET_2, "0009"),
    ),
    Variant(
        "BR-FR-CO-10-BT-46-1",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-46-1", "FX-SCH-A-000420"),
        "The buyer's identifier (BT-46) has no scheme identifier; the Factur-X profile rules reject it too.",
        "L'identifiant de l'acheteur (BT-46) n'a pas d'identifiant de schéma ; les règles du profil Factur-X le refusent aussi.",
        edit=_drop_scheme("BuyerTradeParty"),
    ),
    Variant(
        "BR-FR-CO-10-BT-46-2",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-46-2", "FX-SCH-A-000164"),
        "The buyer has two identifiers (BT-46) with the same scheme 0009; the Factur-X profile rules reject it too.",
        "L'acheteur a deux identifiants (BT-46) au même schéma 0009 ; les règles du profil Factur-X le refusent aussi.",
        edit=_add_global_id("BuyerTradeParty", BUYER_SIRET_2, "0009"),
    ),
    Variant(
        "BR-FR-CO-10-BT-60-1",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-60-1", "FX-SCH-A-000470"),
        "The payee's identifier (BT-60) has no scheme identifier; the Factur-X profile rules reject it too.",
        "L'identifiant du bénéficiaire (BT-60) n'a pas d'identifiant de schéma ; les règles du profil Factur-X le refusent aussi.",
        edit=_add_payee([(PAYEE_SIRET, None)], PAYEE_SIREN),
    ),
    Variant(
        "BR-FR-CO-10-BT-60-2",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-60-2", "FX-SCH-A-000468"),
        "The payee has two identifiers (BT-60) with the same scheme 0009; the Factur-X profile rules reject it too.",
        "Le bénéficiaire a deux identifiants (BT-60) au même schéma 0009 ; les règles du profil Factur-X le refusent aussi.",
        edit=_add_payee([(PAYEE_SIRET, "0009"), (luhn_complete(PAYEE_SIREN + "0002"), "0009")], PAYEE_SIREN),
    ),
    Variant(
        "BR-FR-CO-10-BT-71-1",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-71-1", "FX-SCH-A-000453"),
        "The deliver-to location identifier (BT-71) has no scheme identifier; the Factur-X profile rules reject it too.",
        "L'identifiant du lieu de livraison (BT-71) n'a pas d'identifiant de schéma ; les règles du profil Factur-X le refusent aussi.",
        edit=_add_ship_to([(BUYER_SIRET_2, None)]),
    ),
    # Two SIRETs (0009) here would stop France_RFE 1.4.0.04's BR-FR-09 rule with an error (its $siren variable calls
    # substring() on both): two GLNs instead.
    Variant(
        "BR-FR-CO-10-BT-71-2",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-71-2", "FX-SCH-A-000452"),
        "The deliver-to party has two location identifiers (BT-71) with the same scheme 0088 (GLN); the Factur-X profile rules reject it too.",
        "Le lieu de livraison a deux identifiants (BT-71) au même schéma 0088 (GLN) ; les règles du profil Factur-X le refusent aussi.",
        edit=_add_ship_to([(gln("200000000001"), "0088"), (gln("200000000002"), "0088")]),
    ),
    # Amounts with 3 decimals (BR-FR-DEC-01): the value is unchanged, only its notation.
    Variant(
        "BR-FR-DEC-01-BT-92",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-92_BT-99", "BR-DEC-01"),
        "A document level allowance amount (BT-92) has 3 decimals (EN 16931 BR-DEC-01 fires too).",
        "Le montant d'une remise au niveau du document (BT-92) a 3 décimales (la règle EN 16931 BR-DEC-01 se déclenche aussi).",
        {"allowances": ALLOWANCE},
        edit=_set_text(
            "ApplicableHeaderTradeSettlement", "SpecifiedTradeAllowanceCharge", "ActualAmount", text="10.250"
        ),
    ),
    Variant(
        "BR-FR-DEC-01-BT-93",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-93_BT-100", "BR-DEC-02"),
        "A document level allowance base amount (BT-93) has 3 decimals (EN 16931 BR-DEC-02 fires too).",
        "L'assiette d'une remise au niveau du document (BT-93) a 3 décimales (la règle EN 16931 BR-DEC-02 se déclenche aussi).",
        {"allowances": ALLOWANCE},
        edit=_edit_all(
            _add_element(
                ("ApplicableHeaderTradeSettlement", "SpecifiedTradeAllowanceCharge"),
                "CalculationPercent",
                "1.00",
                before="ActualAmount",
            ),
            _add_element(
                ("ApplicableHeaderTradeSettlement", "SpecifiedTradeAllowanceCharge"),
                "BasisAmount",
                "1025.000",
                before="ActualAmount",
            ),
        ),
    ),
    Variant(
        "BR-FR-DEC-01-BT-106",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-106", "BR-DEC-09"),
        "The sum of the invoice line net amounts (BT-106) has 3 decimals (EN 16931 BR-DEC-09 fires too).",
        "La somme des montants nets des lignes (BT-106) a 3 décimales (la règle EN 16931 BR-DEC-09 se déclenche aussi).",
        edit=_rewrite_amount("LineTotalAmount", "1025.000"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-107",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-107", "BR-DEC-10"),
        "The sum of allowances on document level (BT-107) has 3 decimals (EN 16931 BR-DEC-10 fires too).",
        "La somme des remises au niveau du document (BT-107) a 3 décimales (la règle EN 16931 BR-DEC-10 se déclenche aussi).",
        {"allowances": ALLOWANCE},
        edit=_rewrite_amount("AllowanceTotalAmount", "10.250"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-108",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-108", "BR-DEC-11"),
        "The sum of charges on document level (BT-108) has 3 decimals (EN 16931 BR-DEC-11 fires too).",
        "La somme des frais au niveau du document (BT-108) a 3 décimales (la règle EN 16931 BR-DEC-11 se déclenche aussi).",
        {"charges": CHARGE},
        edit=_rewrite_amount("ChargeTotalAmount", "15.000"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-109",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-109", "BR-DEC-12"),
        "The total without VAT (BT-109) has 3 decimals (EN 16931 BR-DEC-12 fires too).",
        "Le total HT (BT-109) a 3 décimales (la règle EN 16931 BR-DEC-12 se déclenche aussi).",
        edit=_rewrite_amount("TaxBasisTotalAmount", "1025.000"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-110",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-110",),
        "The VAT total (BT-110) has 3 decimals.",
        "Le total de TVA (BT-110) a 3 décimales.",
        edit=_rewrite_amount("TaxTotalAmount", "205.000"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-113",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-113", "BR-DEC-16"),
        "The paid amount (BT-113) has 3 decimals (EN 16931 BR-DEC-16 fires too).",
        "Le montant déjà payé (BT-113) a 3 décimales (la règle EN 16931 BR-DEC-16 se déclenche aussi).",
        edit=_prepaid("200.000", "1030.00"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-114",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-114", "BR-DEC-17"),
        "The rounding amount (BT-114) has 3 decimals (EN 16931 BR-DEC-17 fires too).",
        "Le montant d'arrondi (BT-114) a 3 décimales (la règle EN 16931 BR-DEC-17 se déclenche aussi).",
        edit=_add_element(
            ("SpecifiedTradeSettlementHeaderMonetarySummation",), "RoundingAmount", "0.000", before="GrandTotalAmount"
        ),
    ),
    Variant(
        "BR-FR-DEC-01-BT-116",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-116", "BR-DEC-19"),
        "A VAT category taxable amount (BT-116) has 3 decimals (EN 16931 BR-DEC-19 fires too).",
        "La base d'imposition d'une catégorie de TVA (BT-116) a 3 décimales (la règle EN 16931 BR-DEC-19 se déclenche aussi).",
        edit=_set_text("ApplicableHeaderTradeSettlement", "ApplicableTradeTax", "BasisAmount", text="1025.000"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-117",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-117", "BR-DEC-20"),
        "A VAT category tax amount (BT-117) has 3 decimals (EN 16931 BR-DEC-20 fires too).",
        "Le montant de TVA d'une catégorie (BT-117) a 3 décimales (la règle EN 16931 BR-DEC-20 se déclenche aussi).",
        edit=_set_text("ApplicableHeaderTradeSettlement", "ApplicableTradeTax", "CalculatedAmount", text="205.000"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-131",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-131", "BR-DEC-23"),
        "An invoice line net amount (BT-131) has 3 decimals (EN 16931 BR-DEC-23 fires too).",
        "Le montant net d'une ligne (BT-131) a 3 décimales (la règle EN 16931 BR-DEC-23 se déclenche aussi).",
        edit=_set_text("SpecifiedTradeSettlementLineMonetarySummation", "LineTotalAmount", text="900.000"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-136",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-136_BT-141", "BR-DEC-24"),
        "An invoice line allowance amount (BT-136) has 3 decimals (EN 16931 BR-DEC-24 fires too).",
        "Le montant d'une remise de ligne (BT-136) a 3 décimales (la règle EN 16931 BR-DEC-24 se déclenche aussi).",
        {"lines": DISCOUNTED_LINES},
        edit=_set_text("SpecifiedLineTradeSettlement", "SpecifiedTradeAllowanceCharge", "ActualAmount", text="50.000"),
    ),
    Variant(
        "BR-FR-DEC-01-BT-137",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-137_BT-142", "BR-DEC-25"),
        "An invoice line allowance base amount (BT-137) has 3 decimals (EN 16931 BR-DEC-25 fires too).",
        "L'assiette d'une remise de ligne (BT-137) a 3 décimales (la règle EN 16931 BR-DEC-25 se déclenche aussi).",
        {"lines": DISCOUNTED_LINES},
        edit=_add_element(
            ("SpecifiedLineTradeSettlement", "SpecifiedTradeAllowanceCharge"),
            "BasisAmount",
            "900.000",
            before="ActualAmount",
        ),
    ),
    Variant(
        "BR-FR-DEC-02-BT-149",
        "BR-FR-DEC-02",
        ("BR-FR-DEC-02_BT-149",),
        "An item price base quantity (BT-149) has 5 decimals.",
        "La quantité de base du prix d'un article (BT-149) a 5 décimales.",
        edit=_add_element(
            ("SpecifiedLineTradeAgreement", "NetPriceProductTradePrice"),
            "BasisQuantity",
            "1.00000",
            after="ChargeAmount",
            unitCode="C62",
        ),
    ),
    Variant(
        "BR-FR-DEC-03-BT-147",
        "BR-FR-DEC-03",
        ("BR-FR-DEC-03_BT-147",),
        "An item price discount (BT-147) has 7 decimals.",
        "La remise sur le prix d'un article (BT-147) a 7 décimales.",
        edit=_gross_price("500.00", "50.0000000"),
    ),
    Variant(
        "BR-FR-DEC-03-BT-148",
        "BR-FR-DEC-03",
        ("BR-FR-DEC-03_BT-148",),
        "An item gross price (BT-148) has 7 decimals.",
        "Le prix brut d'un article (BT-148) a 7 décimales.",
        edit=_gross_price("500.0000000", "50.00"),
    ),
)


def baseline():
    return copy.deepcopy(cii.FRENCH)


def build(variant=None):
    """The baseline, or a variant of it, as an lxml root."""
    conf = baseline()
    if variant:
        conf.update(copy.deepcopy(variant.changes))
    root = cii.build(conf)
    if variant and variant.edit:
        variant.edit(root)
    return root
