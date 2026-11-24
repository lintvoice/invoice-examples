"""Target "en16931": a domestic invoice between two companies in Germany, in the Factur-X EN 16931 profile (in Germany,
ZUGFeRD), that passes EN 16931 and the Factur-X EN 16931 profile rules, with no national field; plus one invalid
variant per EN 16931 rule.

The variants are written once, here, as a function of a base: this target builds them on its German invoice, and the
"fr" target on its French one, where the French rules sometimes fail next to them.
"""

import base64
from decimal import Decimal

from .. import cii, edits
from ..edits import (
    Variant,
    account_name_only,
    add_attachment,
    add_card,
    add_classification,
    add_documents,
    add_invoice_reference,
    add_note,
    add_origin,
    add_payee,
    add_product_id,
    add_ship_to,
    add_tax_currency,
    add_tax_representative,
    accounting_vat_total,
    add_breakdown,
    add_exemption_reason,
    breakdown_basis,
    breakdown_per_line,
    breakdown_vat,
    drop_breakdown,
    no_exemption,
    set_rate,
    add_element,
    allowance_as_negative_line,
    billing_period,
    gross_price,
    insert,
    new,
    remove,
    set_attribute,
    set_value,
    edit_all,
    empty_period,
    line_charge,
    line_tax_type,
    no_exemption_reason,
    no_reasons,
    no_seller_identifiers,
    no_unit_code,
    one_more_decimal,
    paid_amount,
    set_amount,
    shift,
    tax_point_with_code,
    vat_amount,
    vat_basis,
)

LANG = "en"
RULES = {
    "EN 16931": "1.3.17 (CII)",
    "Factur-X": "1.09.2, EN 16931 profile",
}

# Fictitious companies. The seller's GLN is in GS1's restricted circulation range (no company's number); its VAT
# number passes its check digit, and VIES answers that no company holds it (ec.europa.eu/taxation_customs/vies,
# checked 2026-11-20); the IBAN is the Bundesbank's bank code in Berlin (10000000, BIC MARKDEF1100) with an all-zero
# account.
GERMAN = {
    "profile": "urn:cen.eu:en16931:2017",
    "billing_frame": None,
    "number": "INV-2026-0042",  # BT-1
    "type_code": "380",  # BT-3
    "issue_date": "20261020",  # BT-2
    "issue_date_format": "102",
    "notes": [],
    "buyer_reference": None,
    "seller": {
        "name": "Musterlieferant GmbH",
        "global_id": (cii.gln("299999999901"), "0088"),  # BT-29, a GLN
        "address": ("10115", "Musterstraße 12", "Berlin", "DE"),
        "vat": cii.vat_de("99999999"),  # BT-31
    },
    "buyer": {
        "name": "Musterkunde AG",
        "address": ("80331", "Beispielweg 3", "München", "DE"),
    },
    "invoicee": None,
    "order_reference": "PO-2026-118",  # BT-13
    "delivery_date": "20261015",
    "currency": "EUR",  # BT-5
    "tax_currency": None,
    "payment_code": "58",  # BT-81, SEPA credit transfer
    "iban": cii.iban_de("10000000", "0000000000"),  # BT-84
    "proprietary_account": None,
    "bic": "MARKDEF1100",  # BT-86
    "due_date": "20261119",
    "due_date_type": None,
    "tax_type": "VAT",
    "lines": [
        ("Training workshop", "2", "450.00", "S", "19"),
        ("Course handbook", "10", "12.50", "S", "19"),
    ],
    "allowances": [],
    "charges": [],
    "payment_terms": "Payment within 30 days by bank transfer.",
    "exemption_reason": "Exempt from VAT",
    "line_allowance_reason": "Discount",
    "words": {
        "allowance": "Discount",
        "trade_allowance": "Trade discount",
        "charge": "Shipping",
        "loyalty_allowance": "Loyalty discount",
        "line_charge": "Packaging",
        "exempt_line": ("Vocational training course", "1", "300.00", "E", "0"),
        # what the core and code list variants add (core, code_lists): a tax representative (name, VAT number,
        # address), a deliver-to party (name, location, address), the electronic addresses of seller and buyer, a
        # reduced VAT rate, a supporting document's name and file name, and the wrong values each language's
        # software tends to write: a country's name, a unit, a scheme's name
        "tax_representative": (
            "Fiskalvertretung Beispiel GmbH",
            cii.vat_de("99999998"),  # DE999999987: VIES answers that no company holds it (checked 2026-11-23)
            ("10117", "Beispielallee 5", "Berlin", "DE"),
        ),
        "deliver_to": ("Musterkunde AG, Lager", cii.gln("299999999902"), ("80331", "Musterweg 7", "München", "DE")),
        "endpoints": (("rechnung@musterlieferant.example", "EM"), ("einkauf@musterkunde.example", "EM")),
        "reduced_rate": "7",
        "timesheet": ("Timesheet", "timesheet.csv"),
        "legal_id": "HRB 99999",
        "country_name": "Deutschland",
        "unit": "Stk",
        "scheme_names": {"global": "GLN", "legal": "HRB", "endpoint": "EMAIL"},
        "thanks": "Thank you for your order.",
    },
}
# What the VAT category variants (vat_categories) put on the invoice, per category: its two items (the base's
# quantities and prices), its exemption reason (BT-120) and code (BT-121), the parties it needs; and the reason a
# category that charges VAT should not give (BR-S-10, BR-Z-10).
GERMAN["words"]["categories"] = {
    "S": {"wrong_reason": "Standard rate"},
    # PV modules sold to the operator of the system: 0 % rate, § 12 (3) UStG; next to them, a charging station at the
    # standard rate (the mixed invoice of BR-Z-01)
    "Z": {
        "items": ("Photovoltaic module, 430 Wp", "Module mounting clamp"),
        "standard_line": ("Wallbox charging station", "1", "300.00", "S", "19"),
        "wrong_reason": "Zero rated",
    },
    # transport of goods being exported, invoiced to the exporter: exempt, § 4 No. 3a UStG (Directive art. 146 (1) (e));
    # next to it, storage in Berlin at the standard rate
    "E": {
        "items": ("Road freight Munich - Zurich, export consignment", "Loading of export pallets"),
        "reason": ("Exempt: transport of export goods (§ 4 No. 3a UStG)", "VATEX-EU-146-1E"),
        "standard_line": ("Storage, Berlin warehouse", "1", "300.00", "S", "19"),
    },
    # construction work subcontracted to a general contractor that itself supplies construction work: § 13b UStG
    "AE": {
        "items": ("Electrical installation works (subcontract)", "Cable tray, installed"),
        "reason": ("Reverse charge: the recipient is liable for the VAT (§ 13b UStG)", "VATEX-EU-AE"),
        "buyer": {**GERMAN["buyer"], "vat": cii.vat_de("99999997")},
    },
    # goods shipped to a company in Austria: § 4 No. 1b and § 6a UStG; ATU99999993: VIES answers that no company holds
    # it (checked 2026-11-24)
    "K": {
        "items": ("Industrial pump", "Pump seal kit"),
        "reason": ("Tax-exempt intra-Community supply (§ 4 No. 1b, § 6a UStG)", "VATEX-EU-IC"),
        "buyer": {
            "name": "Beispielkunde GmbH",
            "address": ("1010", "Musterplatz 1", "Wien", "AT"),
            "vat": "ATU99999993",
        },
        "ship_to": ("Beispielkunde GmbH", ("1010", "Musterplatz 1", "Wien", "AT")),
    },
    # goods exported to a company in Switzerland: § 4 No. 1a and § 6 UStG
    "G": {
        "items": ("Packaging machine", "Spare parts kit"),
        "reason": ("Tax-exempt export delivery (§ 4 No. 1a, § 6 UStG)", "VATEX-EU-G"),
        "buyer": {"name": "Beispielkunde AG", "address": ("4051", "Musterstrasse 1", "Basel", "CH")},
    },
    # a service to a company in Switzerland, supplied where the customer is (§ 3a (2) UStG): not taxable in Germany;
    # the seller gives its tax number (Steuernummer, BT-32), not its VAT number, which BR-O-02 forbids. 99/999/99999
    # is no Berlin tax office's number (they start 11 to 37).
    "O": {
        "items": ("Software consulting, October 2026", "Remote support, hours"),
        "reason": ("Not subject to VAT: place of supply outside Germany (§ 3a (2) UStG)", "VATEX-EU-O"),
        "seller": {**GERMAN["seller"], "vat": None, "tax_number": "99/999/99999"},
        "buyer": {"name": "Beispielkunde AG", "address": ("8001", "Musterstrasse 1", "Zürich", "CH")},
    },
}


def variants(base):
    """One invalid variant per EN 16931 rule, built on base: its seller, item names, reasons and standard rate."""
    words, lines, rate = base["words"], base["lines"], base["lines"][0][4]
    return (
        Variant(
            "BR-CO-15",
            "BR-CO-15",
            ("BR-CO-15",),
            "The invoice total with VAT (BT-112) is not the total without VAT (BT-109) plus the VAT total (BT-110).",
            "Le total TTC (BT-112) n'est pas égal au total HT (BT-109) plus le total de TVA (BT-110).",
            edit=edit_all(set_amount("GrandTotalAmount", 1), set_amount("DuePayableAmount", 1)),
        ),
        Variant(
            "BR-CO-03",
            "BR-CO-03",
            ("BR-CO-03",),
            "The VAT breakdown gives both a VAT point date (BT-7) and a VAT point date code (BT-8); only one is allowed.",
            "La ventilation de TVA indique à la fois une date d'exigibilité de la TVA (BT-7) et un code de date d'exigibilité (BT-8) ; un seul est permis.",
            {} if base["due_date_type"] else {"due_date_type": "5"},
            edit=tax_point_with_code("20261015"),
        ),
        Variant(
            "BR-CO-09",
            "BR-CO-09",
            ("BR-CO-09",),
            "The seller's VAT number (BT-31) does not start with a country code (ZZ is not one).",
            "Le numéro de TVA du vendeur (BT-31) ne commence pas par un code pays (ZZ n'en est pas un).",
            {"seller": {**base["seller"], "vat": "ZZ12345678901"}},
        ),
        Variant(
            "BR-CO-10",
            "BR-CO-10",
            ("BR-CO-10",),
            "The sum of the line net amounts (BT-106) is not the total of the lines (BT-131); the other totals follow it.",
            "La somme des montants nets des lignes (BT-106) n'est pas égale au total des lignes (BT-131) ; les autres totaux suivent.",
            edit=shift(1, "LineTotalAmount", "TaxBasisTotalAmount", "GrandTotalAmount", "DuePayableAmount"),
        ),
        Variant(
            "BR-CO-11",
            "BR-CO-11",
            ("BR-CO-11",),
            "The total of document level allowances (BT-107) is not the sum of the allowances (BT-92).",
            "Le total des remises au niveau du document (BT-107) n'est pas égal à la somme des remises (BT-92).",
            {"allowances": [("10.00", "95", words["allowance"], "S", rate)]},
            edit=edit_all(
                set_amount("AllowanceTotalAmount", 1),
                shift(-1, "TaxBasisTotalAmount", "GrandTotalAmount", "DuePayableAmount"),
            ),
        ),
        Variant(
            "BR-CO-12",
            "BR-CO-12",
            ("BR-CO-12",),
            "The total of document level charges (BT-108) is not the sum of the charges (BT-99).",
            "Le total des frais au niveau du document (BT-108) n'est pas égal à la somme des frais (BT-99).",
            {"charges": [("10.00", "FC", words["charge"], "S", rate)]},
            edit=edit_all(
                set_amount("ChargeTotalAmount", 1),
                shift(1, "TaxBasisTotalAmount", "GrandTotalAmount", "DuePayableAmount"),
            ),
        ),
        Variant(
            "BR-CO-13",
            "BR-CO-13",
            ("BR-CO-13",),
            "The total without VAT (BT-109) is not the sum of the lines (BT-106) minus the allowances (BT-107) plus the charges (BT-108).",
            "Le total HT (BT-109) n'est pas égal à la somme des lignes (BT-106) moins les remises (BT-107) plus les frais (BT-108).",
            edit=shift(1, "TaxBasisTotalAmount", "GrandTotalAmount", "DuePayableAmount"),
        ),
        Variant(
            "BR-CO-14",
            "BR-CO-14",
            ("BR-CO-14",),
            "The VAT total (BT-110) is not the sum of the VAT amounts per category (BT-117).",
            "Le total de TVA (BT-110) n'est pas égal à la somme des montants de TVA par catégorie (BT-117).",
            edit=shift(1, "TaxTotalAmount", "GrandTotalAmount", "DuePayableAmount"),
        ),
        Variant(
            "BR-CO-16",
            "BR-CO-16",
            ("BR-CO-16",),
            "The amount due (BT-115) is not the total with VAT (BT-112) minus the paid amount (BT-113) plus the rounding amount (BT-114).",
            "Le net à payer (BT-115) n'est pas égal au total TTC (BT-112) moins le montant déjà payé (BT-113) plus l'arrondi (BT-114).",
            edit=set_amount("DuePayableAmount", 1),
        ),
        Variant(
            "BR-CO-19",
            "BR-CO-19",
            ("BR-CO-19",),
            "The invoicing period (BG-14) has neither a start date (BT-73) nor an end date (BT-74).",
            "La période de facturation (BG-14) n'a ni date de début (BT-73) ni date de fin (BT-74).",
            edit=empty_period("ApplicableHeaderTradeSettlement"),
        ),
        Variant(
            "BR-CO-20",
            "BR-CO-20",
            ("BR-CO-20",),
            "The first line's period (BG-26) has neither a start date (BT-134) nor an end date (BT-135).",
            "La période de la première ligne (BG-26) n'a ni date de début (BT-134) ni date de fin (BT-135).",
            edit=empty_period("SpecifiedLineTradeSettlement"),
        ),
        Variant(
            "BR-CO-04",
            "BR-CO-04",
            ("BR-CO-04", "CII-DT-037", "FX-SCH-A-000620"),
            "The first line's tax is declared with the type GST instead of VAT, so the line has no VAT category (the CII syntax rule CII-DT-037 and a Factur-X profile rule fail too).",
            "La taxe de la première ligne est déclarée avec le type GST au lieu de VAT : la ligne n'a donc pas de catégorie de TVA (la règle de syntaxe CII-DT-037 et une règle du profil Factur-X échouent aussi).",
            edit=line_tax_type("GST"),
        ),
        Variant(
            "BR-CO-17",
            "BR-CO-17",
            ("BR-CO-17", "BR-S-09"),
            f"The VAT amount of the {rate} % rate (BT-117) is not its taxable amount (BT-116) times the rate (BR-S-09, the same check for the standard rate, fails too).",
            f"Le montant de TVA du taux de {rate} % (BT-117) n'est pas sa base (BT-116) multipliée par le taux (BR-S-09, le même contrôle pour le taux normal, échoue aussi).",
            edit=vat_amount(2),
        ),
        Variant(
            "BR-CO-21",
            "BR-CO-21",
            ("BR-33", "BR-CO-21"),
            "A document level allowance gives neither a reason (BT-97) nor a reason code (BT-98) (EN 16931 BR-33 says the same and fails too).",
            "Une remise au niveau du document n'a ni motif (BT-97) ni code de motif (BT-98) (la règle EN 16931 BR-33 dit la même chose et échoue aussi).",
            {"allowances": [("10.00", "95", words["allowance"], "S", rate)]},
            edit=no_reasons("ApplicableHeaderTradeSettlement"),
        ),
        Variant(
            "BR-CO-22",
            "BR-CO-22",
            ("BR-38", "BR-CO-22"),
            "A document level charge gives neither a reason (BT-104) nor a reason code (BT-105) (EN 16931 BR-38 says the same and fails too).",
            "Des frais au niveau du document n'ont ni motif (BT-104) ni code de motif (BT-105) (la règle EN 16931 BR-38 dit la même chose et échoue aussi).",
            {"charges": [("10.00", "FC", words["charge"], "S", rate)]},
            edit=no_reasons("ApplicableHeaderTradeSettlement"),
        ),
        Variant(
            "BR-CO-23",
            "BR-CO-23",
            ("BR-42", "BR-CO-23"),
            "A line allowance gives neither a reason (BT-139) nor a reason code (BT-140) (EN 16931 BR-42 says the same and fails too).",
            "Une remise sur ligne n'a ni motif (BT-139) ni code de motif (BT-140) (la règle EN 16931 BR-42 dit la même chose et échoue aussi).",
            {"lines": [(*lines[0], "50.00"), *lines[1:]]},
            edit=no_reasons("SpecifiedLineTradeSettlement"),
        ),
        Variant(
            "BR-CO-24",
            "BR-CO-24",
            ("BR-44", "BR-CO-24"),
            "A line charge gives neither a reason (BT-144) nor a reason code (BT-145) (EN 16931 BR-44 says the same and fails too).",
            "Des frais sur ligne n'ont ni motif (BT-144) ni code de motif (BT-145) (la règle EN 16931 BR-44 dit la même chose et échoue aussi).",
            edit=line_charge(10.0, None),
            fixed=line_charge(10.0, words["line_charge"]),
        ),
        Variant(
            "BR-CO-26",
            "BR-CO-26",
            ("BR-CO-26", "BR-S-02"),
            "The seller has no identifier at all: no seller identifier (BT-29), no legal registration identifier (BT-30), no VAT number (BT-31) (BR-S-02, which requires the VAT number for standard-rated VAT, fails too).",
            "Le vendeur n'a aucun identifiant : ni identifiant du vendeur (BT-29), ni identifiant d'immatriculation légale (BT-30), ni numéro de TVA (BT-31) (BR-S-02, qui exige le numéro de TVA pour le taux normal, échoue aussi).",
            edit=no_seller_identifiers,
        ),
        # The core and VAT rules seen failing in public write-ups of real invoices. BR-16 (no line), BR-22 (a line
        # without quantity) and BR-26 (a line without net price) have no example: the Factur-X EN 16931 schema requires
        # those elements, and every example here stays schema-valid.
        Variant(
            "BR-23",
            "BR-23",
            ("BR-23",),
            "The first line's invoiced quantity (BT-129) has no unit of measure code (BT-130).",
            "La quantité facturée de la première ligne (BT-129) n'a pas de code d'unité de mesure (BT-130).",
            edit=no_unit_code,
        ),
        Variant(
            "BR-27",
            "BR-27",
            ("BR-27",),
            "A discount is typed as a line with a negative net price (BT-146) instead of a document level allowance.",
            "Une remise est saisie comme une ligne au prix net négatif (BT-146) au lieu d'une remise au niveau du document.",
            {"allowances": [("50.00", "95", words["loyalty_allowance"], "S", rate)]},
            edit=allowance_as_negative_line,
        ),
        Variant(
            "BR-S-02",
            "BR-S-02",
            ("BR-S-02",),
            "The lines are standard-rated (S) but the seller has no VAT number (BT-31).",
            "Les lignes sont au taux normal (S), mais le vendeur n'a pas de numéro de TVA (BT-31).",
            {"seller": {**base["seller"], "vat": None}},
        ),
        Variant(
            "BR-S-08",
            "BR-S-08",
            ("BR-S-08",),
            f"The taxable amount of the {rate} % rate (BT-116) is 1 € more than the net amounts of its lines (BT-131); its VAT amount stays within the tolerance of BR-CO-17.",
            f"La base HT du taux de {rate} % (BT-116) dépasse de 1 € la somme des montants nets de ses lignes (BT-131) ; son montant de TVA reste dans la tolérance de BR-CO-17.",
            edit=vat_basis(1),
        ),
        Variant(
            "BR-E-10",
            "BR-E-10",
            ("BR-E-10",),
            "The VAT breakdown of the exempt line (category E) gives neither an exemption reason (BT-120) nor a reason code (BT-121).",
            "La ventilation de TVA de la ligne exonérée (catégorie E) n'indique ni motif d'exonération (BT-120) ni code de motif (BT-121).",
            {"lines": [*lines, words["exempt_line"]]},
            edit=no_exemption_reason,
        ),
    )


SUMS = "SpecifiedTradeSettlementHeaderMonetarySummation"


def decimals(base):
    """One invalid variant per EN 16931 rule on an amount's decimals (BR-DEC), built on base: the amount keeps its
    value, written with 3 decimals. The two VAT totals are the exception: their rules (BR-DEC-13, BR-DEC-15) read the
    value in CII, not its notation, so their amount is not rounded to the cent. The fr target builds them on its
    invoice under the name of France's rule on the same amounts, BR-FR-DEC-01, which fails next to them there."""
    words, lines, rate = base["words"], base["lines"], base["lines"][0][4]
    first_line = Decimal(lines[0][1]) * Decimal(lines[0][2])
    all_lines = sum(Decimal(q) * Decimal(p) for _, q, p, *_ in lines)
    allowance = {"allowances": [(f"{all_lines / 100:.2f}", "95", words["trade_allowance"], "S", rate)]}  # 1 %
    charge = {"charges": [("15.00", "FC", words["charge"], "S", rate)]}
    charge_percent = {"charges": [(f"{all_lines / 100:.2f}", "FC", words["charge"], "S", rate)]}  # 1 %
    # an invoice in US dollars whose VAT is accounted in euros, at a fictitious exchange rate
    dollars = {"currency": "USD", "tax_currency": ("EUR", "0.9216")}
    discounted = {"lines": [(*lines[0], "50.00"), *lines[1:]]}
    doc_allowance = ("ApplicableHeaderTradeSettlement", "SpecifiedTradeAllowanceCharge")
    line_allowance = ("SpecifiedLineTradeSettlement", "SpecifiedTradeAllowanceCharge")
    vat = ("ApplicableHeaderTradeSettlement", "ApplicableTradeTax")
    return (
        Variant(
            "BR-DEC-01",
            "BR-DEC-01",
            ("BR-DEC-01",),
            "A document level allowance amount (BT-92) has 3 decimals.",
            "Le montant d'une remise au niveau du document (BT-92) a 3 décimales.",
            allowance,
            edit=one_more_decimal(*doc_allowance, "ActualAmount"),
        ),
        Variant(
            "BR-DEC-02",
            "BR-DEC-02",
            ("BR-DEC-02",),
            "A document level allowance base amount (BT-93) has 3 decimals.",
            "L'assiette d'une remise au niveau du document (BT-93) a 3 décimales.",
            allowance,
            edit=edit_all(
                add_element(doc_allowance, "CalculationPercent", "1.00", before="ActualAmount"),
                add_element(doc_allowance, "BasisAmount", f"{all_lines:.3f}", before="ActualAmount"),
            ),
        ),
        Variant(
            "BR-DEC-05",
            "BR-DEC-05",
            ("BR-DEC-05",),
            "A document level charge amount (BT-99) has 3 decimals.",
            "Le montant de frais au niveau du document (BT-99) a 3 décimales.",
            charge,
            edit=one_more_decimal(*doc_allowance, "ActualAmount"),
        ),
        Variant(
            "BR-DEC-06",
            "BR-DEC-06",
            ("BR-DEC-06",),
            "A document level charge base amount (BT-100) has 3 decimals.",
            "L'assiette de frais au niveau du document (BT-100) a 3 décimales.",
            charge_percent,
            edit=edit_all(
                add_element(doc_allowance, "CalculationPercent", "1.00", before="ActualAmount"),
                add_element(doc_allowance, "BasisAmount", f"{all_lines:.3f}", before="ActualAmount"),
            ),
        ),
        Variant(
            "BR-DEC-09",
            "BR-DEC-09",
            ("BR-DEC-09",),
            "The sum of the invoice line net amounts (BT-106) has 3 decimals.",
            "La somme des montants nets des lignes (BT-106) a 3 décimales.",
            edit=one_more_decimal(SUMS, "LineTotalAmount"),
        ),
        Variant(
            "BR-DEC-10",
            "BR-DEC-10",
            ("BR-DEC-10",),
            "The sum of allowances on document level (BT-107) has 3 decimals.",
            "La somme des remises au niveau du document (BT-107) a 3 décimales.",
            allowance,
            edit=one_more_decimal(SUMS, "AllowanceTotalAmount"),
        ),
        Variant(
            "BR-DEC-11",
            "BR-DEC-11",
            ("BR-DEC-11",),
            "The sum of charges on document level (BT-108) has 3 decimals.",
            "La somme des frais au niveau du document (BT-108) a 3 décimales.",
            charge,
            edit=one_more_decimal(SUMS, "ChargeTotalAmount"),
        ),
        Variant(
            "BR-DEC-12",
            "BR-DEC-12",
            ("BR-DEC-12",),
            "The total without VAT (BT-109) has 3 decimals.",
            "Le total HT (BT-109) a 3 décimales.",
            edit=one_more_decimal(SUMS, "TaxBasisTotalAmount"),
        ),
        Variant(
            "BR-DEC-13",
            "BR-DEC-13",
            ("BR-DEC-13", "BR-CO-14"),
            "The VAT total (BT-110) is not rounded to the cent: it has 3 decimals, so it is no longer the sum of the VAT breakdown (EN 16931 BR-CO-14 fails too).",
            "Le total de TVA (BT-110) n'est pas arrondi au centime : il a 3 décimales, et n'est donc plus la somme de la ventilation de TVA (la règle EN 16931 BR-CO-14 échoue aussi).",
            edit=one_more_decimal(SUMS, "TaxTotalAmount", digit="4"),
        ),
        Variant(
            "BR-DEC-14",
            "BR-DEC-14",
            ("BR-DEC-14",),
            "The total with VAT (BT-112) has 3 decimals.",
            "Le total TTC (BT-112) a 3 décimales.",
            edit=one_more_decimal(SUMS, "GrandTotalAmount"),
        ),
        Variant(
            "BR-DEC-15",
            "BR-DEC-15",
            ("BR-DEC-15",),
            "The invoice is in US dollars; its VAT total in euros, the VAT accounting currency (BT-111), is converted but not rounded to the cent: it has 3 decimals.",
            "La facture est en dollars américains ; son total de TVA en euros, la devise de comptabilisation de la TVA (BT-111), est converti mais pas arrondi au centime : il a 3 décimales.",
            dollars,
            edit=accounting_vat_total(dollars["tax_currency"][1]),
        ),
        Variant(
            "BR-DEC-16",
            "BR-DEC-16",
            ("BR-DEC-16",),
            "The paid amount (BT-113) has 3 decimals.",
            "Le montant déjà payé (BT-113) a 3 décimales.",
            edit=paid_amount("200.000"),
        ),
        Variant(
            "BR-DEC-17",
            "BR-DEC-17",
            ("BR-DEC-17",),
            "The rounding amount (BT-114) has 3 decimals.",
            "Le montant d'arrondi (BT-114) a 3 décimales.",
            edit=add_element((SUMS,), "RoundingAmount", "0.000", before="GrandTotalAmount"),
        ),
        Variant(
            "BR-DEC-18",
            "BR-DEC-18",
            ("BR-DEC-18",),
            "The amount due (BT-115) has 3 decimals.",
            "Le net à payer (BT-115) a 3 décimales.",
            edit=one_more_decimal(SUMS, "DuePayableAmount"),
        ),
        Variant(
            "BR-DEC-19",
            "BR-DEC-19",
            ("BR-DEC-19",),
            "A VAT category taxable amount (BT-116) has 3 decimals.",
            "La base d'imposition d'une catégorie de TVA (BT-116) a 3 décimales.",
            edit=one_more_decimal(*vat, "BasisAmount"),
        ),
        Variant(
            "BR-DEC-20",
            "BR-DEC-20",
            ("BR-DEC-20",),
            "A VAT category tax amount (BT-117) has 3 decimals.",
            "Le montant de TVA d'une catégorie (BT-117) a 3 décimales.",
            edit=one_more_decimal(*vat, "CalculatedAmount"),
        ),
        Variant(
            "BR-DEC-23",
            "BR-DEC-23",
            ("BR-DEC-23",),
            "An invoice line net amount (BT-131) has 3 decimals.",
            "Le montant net d'une ligne (BT-131) a 3 décimales.",
            edit=one_more_decimal("SpecifiedTradeSettlementLineMonetarySummation", "LineTotalAmount"),
        ),
        Variant(
            "BR-DEC-24",
            "BR-DEC-24",
            ("BR-DEC-24",),
            "An invoice line allowance amount (BT-136) has 3 decimals.",
            "Le montant d'une remise de ligne (BT-136) a 3 décimales.",
            discounted,
            edit=one_more_decimal(*line_allowance, "ActualAmount"),
        ),
        Variant(
            "BR-DEC-25",
            "BR-DEC-25",
            ("BR-DEC-25",),
            "An invoice line allowance base amount (BT-137) has 3 decimals.",
            "L'assiette d'une remise de ligne (BT-137) a 3 décimales.",
            discounted,
            edit=add_element(line_allowance, "BasisAmount", f"{first_line:.3f}", before="ActualAmount"),
        ),
        Variant(
            "BR-DEC-27",
            "BR-DEC-27",
            ("BR-DEC-27",),
            "An invoice line charge amount (BT-141) has 3 decimals.",
            "Le montant de frais sur une ligne (BT-141) a 3 décimales.",
            edit=edit_all(line_charge(10.0, words["line_charge"]), one_more_decimal(*line_allowance, "ActualAmount")),
            fixed=line_charge(10.0, words["line_charge"]),
        ),
        Variant(
            "BR-DEC-28",
            "BR-DEC-28",
            ("BR-DEC-28",),
            "An invoice line charge base amount (BT-142) has 3 decimals.",
            "L'assiette de frais sur une ligne (BT-142) a 3 décimales.",
            edit=edit_all(
                line_charge(10.0, words["line_charge"]),
                add_element(line_allowance, "BasisAmount", f"{first_line:.3f}", before="ActualAmount"),
            ),
            fixed=line_charge(10.0, words["line_charge"]),
        ),
    )


SETTLEMENT = "//ram:ApplicableHeaderTradeSettlement"
DOC_AC = f"{SETTLEMENT}/ram:SpecifiedTradeAllowanceCharge"
EXEMPT_TAX = f"{SETTLEMENT}/ram:ApplicableTradeTax[ram:CategoryCode='E']"
TAX_REP = "//ram:SellerTaxRepresentativeTradeParty"
GTIN = cii.gln("200000000011")  # GS1's restricted circulation range: no product's number
# A UNSPSC class (scheme TST in UNTDID 7143): "Non scientific vocational training services", in the UNGM UNSPSC
# export (ungm.org/Public/UNSPSC, read 2026-11-23)
CLASS_CODE = "86101700"
TIMESHEET_CSV = base64.b64encode(b"date,hours\n2026-10-14,8\n2026-10-15,8\n").decode("ascii")


def _previous(number):
    """The number of the invoice before this one: its last digits minus one."""
    head = number.rstrip("0123456789")
    digits = number[len(head) :]
    return f"{head}{int(digits) - 1:0{len(digits)}d}"


def core(base):
    """One invalid variant per core EN 16931 rule (BR-01 to BR-65) that a schema-valid Factur-X invoice can fail, built
    on base. BR-12 to BR-15, BR-24, BR-31, BR-36, BR-41, BR-43, BR-47, BR-49 and BR-54 have none: they ask for an
    element the Factur-X EN 16931 schema already requires. BR-33, BR-38, BR-42 and BR-44 fail in the examples of
    BR-CO-21 to BR-CO-24, which say the same; BR-52 has its own (BR_52, below).

    Many of these rules check data that a rule of the Factur-X EN 16931 profile (FX-SCH-A-…) also checks: it fails next
    to them, and the variant names it."""
    w, seller, buyer, lines = base["words"], base["seller"], base["buyer"], base["lines"]
    rate = lines[0][4]
    allowance = {"allowances": [("10.00", "95", w["allowance"], "S", rate)]}
    charge = {"charges": [("10.00", "FC", w["charge"], "S", rate)]}
    exempt = {"lines": [*lines, w["exempt_line"]]}
    rep = add_tax_representative(*w["tax_representative"])
    ship_name, ship_id, ship_address = w["deliver_to"]
    gross = Decimal(lines[0][2]) + 50
    seller_endpoint = {} if seller.get("endpoint") else {"seller": {**seller, "endpoint": w["endpoints"][0]}}
    buyer_endpoint = {} if buyer.get("endpoint") else {"buyer": {**buyer, "endpoint": w["endpoints"][1]}}
    no_country = lambda p: {**p, "address": (*p["address"][:3], "")}  # noqa: E731
    return (
        Variant(
            "BR-01",
            "BR-01",
            ("BR-01",),
            "The specification identifier (BT-24) is empty: the invoice does not say which rules it follows.",
            "L'identifiant de spécification (BT-24) est vide : la facture ne dit pas quelles règles elle suit.",
            {"profile": ""},
        ),
        Variant(
            "BR-02",
            "BR-02",
            ("BR-02",),
            "The invoice number (BT-1) is empty.",
            "Le numéro de facture (BT-1) est vide.",
            {"number": ""},
        ),
        Variant(
            "BR-03",
            "BR-03",
            ("BR-03", "FX-SCH-A-000554"),
            "The issue date (BT-2) is written as a date and time, in format 203, instead of a date in format 102 (the Factur-X profile rule FX-SCH-A-000554, which allows format 102 only, fails too).",
            "La date d'émission (BT-2) est écrite comme une date et une heure, au format 203, et non comme une date au format 102 (la règle du profil Factur-X FX-SCH-A-000554, qui n'admet que le format 102, échoue aussi).",
            {"issue_date": base["issue_date"] + "1430", "issue_date_format": "203"},
        ),
        Variant(
            "BR-04",
            "BR-04",
            ("BR-04", "BR-CL-01"),
            "The invoice type code (BT-3) is empty (BR-CL-01, on the list of type codes, fails too).",
            "Le code type de document (BT-3) est vide (BR-CL-01, sur la liste des codes types, échoue aussi).",
            {"type_code": ""},
        ),
        Variant(
            "BR-05",
            "BR-05",
            ("BR-05", "BR-CL-03", "BR-CL-04"),
            "The invoice currency code (BT-5) is empty, and so is the currency of the VAT total (BR-CL-03 and BR-CL-04, on the list of currency codes, fail too).",
            "Le code de la devise de la facture (BT-5) est vide, comme la devise du total de TVA (BR-CL-03 et BR-CL-04, sur la liste des codes devises, échouent aussi).",
            {"currency": ""},
        ),
        Variant(
            "BR-06",
            "BR-06",
            ("BR-06",),
            "The seller name (BT-27) is empty.",
            "Le nom du vendeur (BT-27) est vide.",
            {"seller": {**seller, "name": ""}},
        ),
        Variant(
            "BR-07",
            "BR-07",
            ("BR-07",),
            "The buyer name (BT-44) is empty.",
            "Le nom de l'acheteur (BT-44) est vide.",
            {"buyer": {**buyer, "name": ""}},
        ),
        Variant(
            "BR-08",
            "BR-08",
            ("BR-08", "BR-09", "FX-SCH-A-000032"),
            "The seller has no postal address (BG-5) (BR-09, which asks for its country code, and the Factur-X profile rule FX-SCH-A-000032 fail too).",
            "Le vendeur n'a pas d'adresse postale (BG-5) (BR-09, qui en exige le code pays, et la règle du profil Factur-X FX-SCH-A-000032 échouent aussi).",
            {"seller": {**seller, "address": None}},
        ),
        Variant(
            "BR-09",
            "BR-09",
            ("BR-09", "BR-CL-14"),
            "The country code of the seller's address (BT-40) is empty (BR-CL-14, on the list of country codes, fails too).",
            "Le code pays de l'adresse du vendeur (BT-40) est vide (BR-CL-14, sur la liste des codes pays, échoue aussi).",
            {"seller": no_country(seller)},
        ),
        Variant(
            "BR-10",
            "BR-10",
            ("BR-10", "BR-11", "FX-SCH-A-000419"),
            "The buyer has no postal address (BG-8) (BR-11, which asks for its country code, and the Factur-X profile rule FX-SCH-A-000419 fail too).",
            "L'acheteur n'a pas d'adresse postale (BG-8) (BR-11, qui en exige le code pays, et la règle du profil Factur-X FX-SCH-A-000419 échouent aussi).",
            {"buyer": {**buyer, "address": None}},
        ),
        Variant(
            "BR-11",
            "BR-11",
            ("BR-11", "BR-CL-14"),
            "The country code of the buyer's address (BT-55) is empty (BR-CL-14, on the list of country codes, fails too).",
            "Le code pays de l'adresse de l'acheteur (BT-55) est vide (BR-CL-14, sur la liste des codes pays, échoue aussi).",
            {"buyer": no_country(buyer)},
        ),
        Variant(
            "BR-17",
            "BR-17",
            ("BR-17",),
            "The seller is named again as payee (BG-10), with its own name (BT-59): a payee is only given when someone else is paid.",
            "Le vendeur est repris comme bénéficiaire du paiement (BG-10), avec son propre nom (BT-59) : un bénéficiaire n'est indiqué que si quelqu'un d'autre est payé.",
            edit=add_payee([], name=seller["name"]),
        ),
        Variant(
            "BR-18",
            "BR-18",
            ("BR-18",),
            "The seller's tax representative (BG-11) has an empty name (BT-62).",
            "Le représentant fiscal du vendeur (BG-11) a un nom vide (BT-62).",
            edit=edit_all(rep, set_value(f"{TAX_REP}/ram:Name", "")),
            fixed=rep,
        ),
        Variant(
            "BR-19",
            "BR-19",
            ("BR-19", "BR-20", "FX-SCH-A-000432"),
            "The seller's tax representative (BG-11) has no postal address (BG-12) (BR-20, which asks for its country code, and the Factur-X profile rule FX-SCH-A-000432 fail too).",
            "Le représentant fiscal du vendeur (BG-11) n'a pas d'adresse postale (BG-12) (BR-20, qui en exige le code pays, et la règle du profil Factur-X FX-SCH-A-000432 échouent aussi).",
            edit=edit_all(rep, remove(f"{TAX_REP}/ram:PostalTradeAddress")),
            fixed=rep,
        ),
        Variant(
            "BR-20",
            "BR-20",
            ("BR-20", "BR-CL-14"),
            "The country code of the tax representative's address (BT-69) is empty (BR-CL-14, on the list of country codes, fails too).",
            "Le code pays de l'adresse du représentant fiscal (BT-69) est vide (BR-CL-14, sur la liste des codes pays, échoue aussi).",
            edit=edit_all(rep, set_value(f"{TAX_REP}/ram:PostalTradeAddress/ram:CountryID", "")),
            fixed=rep,
        ),
        Variant(
            "BR-21",
            "BR-21",
            ("BR-21",),
            "The first line's identifier (BT-126) is empty.",
            "L'identifiant de la première ligne (BT-126) est vide.",
            edit=set_value("//ram:AssociatedDocumentLineDocument/ram:LineID", ""),
        ),
        Variant(
            "BR-25",
            "BR-25",
            ("BR-25",),
            "The first line's item name (BT-153) is empty.",
            "Le nom de l'article de la première ligne (BT-153) est vide.",
            {"lines": [("", *lines[0][1:]), *lines[1:]]},
        ),
        Variant(
            "BR-28",
            "BR-28",
            ("BR-28",),
            "The first line's gross price (BT-148) is written with a minus sign; its price discount (BT-147) and net price (BT-146) are right.",
            "Le prix brut de la première ligne (BT-148) est écrit avec un signe moins ; son rabais (BT-147) et son prix net (BT-146) sont justes.",
            edit=gross_price(f"-{gross:.2f}", "50.00"),
            fixed=gross_price(f"{gross:.2f}", "50.00"),
        ),
        Variant(
            "BR-29",
            "BR-29",
            ("BR-29",),
            "The invoicing period (BG-14) ends before it starts: its start (BT-73) and end (BT-74) dates are swapped.",
            "La période de facturation (BG-14) finit avant de commencer : ses dates de début (BT-73) et de fin (BT-74) sont inversées.",
            edit=billing_period("20261031", "20261001"),
            fixed=billing_period("20261001", "20261031"),
        ),
        Variant(
            "BR-30",
            "BR-30",
            ("BR-30",),
            "The first line's period (BG-26) ends before it starts: its start (BT-134) and end (BT-135) dates are swapped.",
            "La période de la première ligne (BG-26) finit avant de commencer : ses dates de début (BT-134) et de fin (BT-135) sont inversées.",
            edit=billing_period("20261015", "20261014", where="SpecifiedLineTradeSettlement"),
            fixed=billing_period("20261014", "20261015", where="SpecifiedLineTradeSettlement"),
        ),
        Variant(
            "BR-32",
            "BR-32",
            ("BR-32", "BR-S-08", "FX-SCH-A-000185"),
            "A document level allowance has no VAT category (BT-95), so it lowers no VAT breakdown (BR-S-08, on the standard rate's taxable amount, and the Factur-X profile rule FX-SCH-A-000185 fail too).",
            "Une remise au niveau du document n'a pas de catégorie de TVA (BT-95) : elle ne réduit donc aucune ventilation de TVA (BR-S-08, sur la base du taux normal, et la règle du profil Factur-X FX-SCH-A-000185 échouent aussi).",
            allowance,
            edit=remove(f"{DOC_AC}/ram:CategoryTradeTax"),
        ),
        Variant(
            "BR-37",
            "BR-37",
            ("BR-37", "BR-S-08", "FX-SCH-A-000479"),
            "A document level charge has no VAT category (BT-102), so it adds to no VAT breakdown (BR-S-08, on the standard rate's taxable amount, and the Factur-X profile rule FX-SCH-A-000479 fail too).",
            "Des frais au niveau du document n'ont pas de catégorie de TVA (BT-102) : ils ne s'ajoutent donc à aucune ventilation de TVA (BR-S-08, sur la base du taux normal, et la règle du profil Factur-X FX-SCH-A-000479 échouent aussi).",
            charge,
            edit=remove(f"{DOC_AC}/ram:CategoryTradeTax"),
        ),
        Variant(
            "BR-45",
            "BR-45",
            ("BR-45", "BR-E-08", "FX-SCH-A-000177"),
            "The VAT breakdown of the exempt line (category E) has no taxable amount (BT-116) (BR-E-08, on that amount, and the Factur-X profile rule FX-SCH-A-000177 fail too).",
            "La ventilation de TVA de la ligne exonérée (catégorie E) n'a pas de base (BT-116) (BR-E-08, sur ce montant, et la règle du profil Factur-X FX-SCH-A-000177 échouent aussi).",
            exempt,
            edit=remove(f"{EXEMPT_TAX}/ram:BasisAmount"),
        ),
        Variant(
            "BR-46",
            "BR-46",
            ("BR-46", "BR-CO-17", "BR-E-09", "FX-SCH-A-000176"),
            "The VAT breakdown of the exempt line (category E) has no VAT amount (BT-117), although it is 0 (BR-CO-17 and BR-E-09, on that amount, and the Factur-X profile rule FX-SCH-A-000176 fail too).",
            "La ventilation de TVA de la ligne exonérée (catégorie E) n'a pas de montant de TVA (BT-117), bien qu'il soit nul (BR-CO-17 et BR-E-09, sur ce montant, et la règle du profil Factur-X FX-SCH-A-000176 échouent aussi).",
            exempt,
            edit=remove(f"{EXEMPT_TAX}/ram:CalculatedAmount"),
        ),
        Variant(
            "BR-48",
            "BR-48",
            ("BR-48",),
            "The VAT breakdown of the exempt line (category E) has no VAT rate (BT-119): an exempt category still gives its rate, 0.",
            "La ventilation de TVA de la ligne exonérée (catégorie E) n'a pas de taux de TVA (BT-119) : une catégorie exonérée indique quand même son taux, 0.",
            exempt,
            edit=remove(f"{EXEMPT_TAX}/ram:RateApplicablePercent"),
        ),
        Variant(
            "BR-50",
            "BR-50",
            ("BR-50",),
            "The payment account identifier (BT-84), the IBAN of the credit transfer, is empty.",
            "L'identifiant du compte de paiement (BT-84), l'IBAN du virement, est vide.",
            edit=set_value("//ram:PayeePartyCreditorFinancialAccount/ram:IBANID", ""),
        ),
        Variant(
            "BR-51",
            "BR-51",
            ("BR-51",),
            "The invoice gives the payment card's full number (BT-87); the rule allows 10 characters at most, such as the last 4 digits.",
            "La facture indique le numéro complet de la carte de paiement (BT-87) ; la règle n'admet que 10 caractères au plus, par exemple les 4 derniers chiffres.",
            {"payment_code": "54", "iban": None, "bic": None},
            edit=add_card("4111111111111111"),
            fixed=add_card("1111"),
        ),
        Variant(
            "BR-53",
            "BR-53",
            ("BR-53",),
            f"The invoice names a VAT accounting currency (BT-6), {base['currency']}, which is its own currency (BT-5): the rule wants another currency, and the VAT total in it (BT-111).",
            f"La facture indique une devise de comptabilisation de la TVA (BT-6), {base['currency']}, qui est sa propre devise (BT-5) : la règle attend une autre devise, et le total de TVA dans cette devise (BT-111).",
            edit=add_tax_currency(base["currency"]),
        ),
        Variant(
            "BR-55",
            "BR-55",
            ("BR-55",),
            "The invoice refers to a preceding invoice (BG-3) whose reference (BT-25) is empty.",
            "La facture fait référence à une facture antérieure (BG-3) dont la référence (BT-25) est vide.",
            edit=add_invoice_reference(""),
            fixed=add_invoice_reference(_previous(base["number"])),
        ),
        Variant(
            "BR-56",
            "BR-56",
            ("BR-56", "FX-SCH-A-000169"),
            "The seller's tax representative (BG-11) has no VAT identifier (BT-63) (the Factur-X profile rule FX-SCH-A-000169, which asks for it too, fails too).",
            "Le représentant fiscal du vendeur (BG-11) n'a pas de numéro de TVA (BT-63) (la règle du profil Factur-X FX-SCH-A-000169, qui l'exige aussi, échoue aussi).",
            edit=edit_all(rep, remove(f"{TAX_REP}/ram:SpecifiedTaxRegistration")),
            fixed=rep,
        ),
        Variant(
            "BR-57",
            "BR-57",
            ("BR-57", "BR-CL-14"),
            "The country code of the deliver-to address (BT-80) is empty (BR-CL-14, on the list of country codes, fails too).",
            "Le code pays de l'adresse de livraison (BT-80) est vide (BR-CL-14, sur la liste des codes pays, échoue aussi).",
            edit=add_ship_to([(ship_id, "0088")], ship_name, (*ship_address[:3], "")),
            fixed=add_ship_to([(ship_id, "0088")], ship_name, ship_address),
        ),
        Variant(
            "BR-61",
            "BR-61",
            ("BR-50", "BR-61", "CII-SR-470"),
            "The credit transfer's account gives the account name (BT-85) but no IBAN or other account identifier (BT-84) (BR-50 and the CII syntax rule CII-SR-470, on the same identifier, fail too).",
            "Le compte du virement indique le nom du compte (BT-85) mais ni IBAN ni autre identifiant de compte (BT-84) (BR-50 et la règle de syntaxe CII CII-SR-470, sur le même identifiant, échouent aussi).",
            edit=account_name_only(seller["name"]),
        ),
        Variant(
            "BR-62",
            "BR-62",
            ("BR-62", "FX-SCH-A-000446"),
            "The seller's electronic address (BT-34) has no scheme identifier (BT-34-1) (the Factur-X profile rule FX-SCH-A-000446, which asks for it too, fails too).",
            "L'adresse électronique du vendeur (BT-34) n'a pas d'identifiant de schéma (BT-34-1) (la règle du profil Factur-X FX-SCH-A-000446, qui l'exige aussi, échoue aussi).",
            seller_endpoint,
            edit=set_attribute("//ram:SellerTradeParty/ram:URIUniversalCommunication/ram:URIID", "schemeID", None),
        ),
        Variant(
            "BR-63",
            "BR-63",
            ("BR-63", "FX-SCH-A-000428"),
            "The buyer's electronic address (BT-49) has no scheme identifier (BT-49-1) (the Factur-X profile rule FX-SCH-A-000428, which asks for it too, fails too).",
            "L'adresse électronique de l'acheteur (BT-49) n'a pas d'identifiant de schéma (BT-49-1) (la règle du profil Factur-X FX-SCH-A-000428, qui l'exige aussi, échoue aussi).",
            buyer_endpoint,
            edit=set_attribute("//ram:BuyerTradeParty/ram:URIUniversalCommunication/ram:URIID", "schemeID", None),
        ),
        Variant(
            "BR-64",
            "BR-64",
            ("BR-64", "CII-SR-046", "FX-SCH-A-000551"),
            "The first line's item standard identifier (BT-157), a GTIN, has no scheme identifier (BT-157-1) (the CII syntax rule CII-SR-046 and the Factur-X profile rule FX-SCH-A-000551, which ask for it too, fail too).",
            "L'identifiant standard de l'article de la première ligne (BT-157), un GTIN, n'a pas d'identifiant de schéma (BT-157-1) (la règle de syntaxe CII CII-SR-046 et la règle du profil Factur-X FX-SCH-A-000551, qui l'exigent aussi, échouent aussi).",
            edit=add_product_id(GTIN, None),
            fixed=add_product_id(GTIN, "0160"),
        ),
        Variant(
            "BR-65",
            "BR-65",
            ("BR-65", "FX-SCH-A-000296"),
            "The first line's item classification identifier (BT-158) has no scheme identifier (BT-158-1) (the Factur-X profile rule FX-SCH-A-000296, which asks for it too, fails too).",
            "L'identifiant de classification de l'article de la première ligne (BT-158) n'a pas d'identifiant de schéma (BT-158-1) (la règle du profil Factur-X FX-SCH-A-000296, qui l'exige aussi, échoue aussi).",
            edit=add_classification(CLASS_CODE, None),
            fixed=add_classification(CLASS_CODE, "TST"),
        ),
    )


def code_lists(base):
    """One invalid variant per EN 16931 code list rule (BR-CL), built on base: a value that is not in the rule's list,
    often a word or a name where the list has a code. The Factur-X EN 16931 profile checks the same lists: its rule
    (FX-SCH-A-…) fails next to each, and the variant names it. BR-CL-03, on an amount's currency, fails in the examples
    of BR-CL-04 and BR-CL-05."""
    w, seller, buyer, lines = base["words"], base["seller"], base["buyer"], base["lines"]
    rate, names = lines[0][4], w["scheme_names"]
    allowance = {"allowances": [("10.00", "95", w["allowance"], "S", rate)]}
    charge = {"charges": [("10.00", "FC", w["charge"], "S", rate)]}
    dollars = {"currency": "USD", "tax_currency": ("EUR", "0.9216")}
    reduced = w["reduced_rate"]
    second = (*lines[1][:3], "S", reduced)
    ship_name, ship_id, _ = w["deliver_to"]
    global_scheme = seller["global_id"][1]
    legal = {} if seller.get("legal_id") else {"seller": {**seller, "legal_id": (w["legal_id"], None)}}
    endpoint = {} if seller.get("endpoint") else {"seller": {**seller, "endpoint": w["endpoints"][0]}}
    endpoint_scheme = (seller.get("endpoint") or w["endpoints"][0])[1]
    buyer_country = buyer["address"][3]
    due_type = {} if base["due_date_type"] else {"due_date_type": "5"}
    document, filename = w["timesheet"]
    return (
        Variant(
            "BR-CL-01",
            "BR-CL-01",
            ("BR-CL-01", "FX-SCH-A-000555"),
            f"The invoice type code (BT-3) is INV, a word instead of a code from the UNTDID 1001 list such as {base['type_code']} (the Factur-X profile rule FX-SCH-A-000555, on the same list, fails too).",
            f"Le code type de document (BT-3) est INV, un mot au lieu d'un code de la liste UNTDID 1001 comme {base['type_code']} (la règle du profil Factur-X FX-SCH-A-000555, sur la même liste, échoue aussi).",
            {"type_code": "INV"},
        ),
        Variant(
            "BR-CL-04",
            "BR-CL-04",
            ("BR-CL-03", "BR-CL-04", "FX-SCH-A-000595", "FX-SCH-A-000606"),
            f"The invoice currency (BT-5) is written EURO instead of the ISO 4217 code {base['currency']}, and so is the VAT total's currency (BR-CL-03, the same check on an amount's currency, and the Factur-X profile rules FX-SCH-A-000595 and FX-SCH-A-000606 fail too).",
            f"La devise de la facture (BT-5) est écrite EURO au lieu du code ISO 4217 {base['currency']}, comme la devise du total de TVA (BR-CL-03, le même contrôle sur la devise d'un montant, et les règles du profil Factur-X FX-SCH-A-000595 et FX-SCH-A-000606 échouent aussi).",
            {"currency": "EURO"},
        ),
        Variant(
            "BR-CL-05",
            "BR-CL-05",
            ("BR-CL-03", "BR-CL-05", "FX-SCH-A-000607", "FX-SCH-A-000610"),
            "The invoice is in US dollars; its VAT accounting currency (BT-6) is written EURO instead of the ISO 4217 code EUR, and so is the currency of its VAT total in that currency (BR-CL-03, the same check on an amount's currency, and the Factur-X profile rules FX-SCH-A-000607 and FX-SCH-A-000610 fail too).",
            "La facture est en dollars américains ; sa devise de comptabilisation de la TVA (BT-6) est écrite EURO au lieu du code ISO 4217 EUR, comme la devise de son total de TVA dans cette devise (BR-CL-03, le même contrôle sur la devise d'un montant, et les règles du profil Factur-X FX-SCH-A-000607 et FX-SCH-A-000610 échouent aussi).",
            dollars,
            edit=edit_all(
                set_value(f"{SETTLEMENT}/ram:TaxCurrencyCode", "EURO"),
                set_attribute("//ram:TaxTotalAmount[@currencyID='EUR']", "currencyID", "EURO"),
            ),
        ),
        Variant(
            "BR-CL-06",
            "BR-CL-06",
            ("BR-CL-06", "FX-SCH-A-000588"),
            "The VAT point date code (BT-8) is 35, a code of the UBL syntax: CII uses 5, 29 or 72 (the Factur-X profile rule FX-SCH-A-000588, on the same list, fails too).",
            "Le code de date d'exigibilité de la TVA (BT-8) est 35, un code de la syntaxe UBL : CII utilise 5, 29 ou 72 (la règle du profil Factur-X FX-SCH-A-000588, sur la même liste, échoue aussi).",
            due_type,
            edit=set_value(f"{SETTLEMENT}/ram:ApplicableTradeTax/ram:DueDateTypeCode", "35"),
        ),
        Variant(
            "BR-CL-07",
            "BR-CL-07",
            ("BR-CL-07", "FX-SCH-A-000282"),
            "The scheme of the invoiced object identifier (BT-18-1) is ORDER, a word instead of a code from the UNTDID 1153 list (the Factur-X profile rule FX-SCH-A-000282, on the same list, fails too).",
            "Le schéma de l'identifiant de l'objet facturé (BT-18-1) est ORDER, un mot au lieu d'un code de la liste UNTDID 1153 (la règle du profil Factur-X FX-SCH-A-000282, sur la même liste, échoue aussi).",
            edit=add_documents(("FA-2026-07", "130", None, "ORDER")),
            fixed=add_documents(("FA-2026-07", "130", None, "AVV")),  # AVV: a framework agreement number
        ),
        Variant(
            "BR-CL-08",
            "BR-CL-08",
            ("BR-CL-08", "FX-SCH-A-000553"),
            "A note's subject code (BT-21) is INFO, a word instead of a code from the UNCL 4451 list (the Factur-X profile rule FX-SCH-A-000553, on the same list, fails too).",
            "Le code sujet d'une note (BT-21) est INFO, un mot au lieu d'un code de la liste UNCL 4451 (la règle du profil Factur-X FX-SCH-A-000553, sur la même liste, échoue aussi).",
            edit=add_note("INFO", w["thanks"]),
            fixed=add_note("AAI", w["thanks"]),
        ),
        Variant(
            "BR-CL-10",
            "BR-CL-10",
            ("BR-CL-10", "FX-SCH-A-000579"),
            f"The scheme of the seller identifier (BT-29-1) is written {names['global']} instead of its ISO 6523 code, {global_scheme} (the Factur-X profile rule FX-SCH-A-000579, on the same list, fails too).",
            f"Le schéma de l'identifiant du vendeur (BT-29-1) est écrit {names['global']} au lieu de son code ISO 6523, {global_scheme} (la règle du profil Factur-X FX-SCH-A-000579, sur la même liste, échoue aussi).",
            edit=set_attribute("//ram:SellerTradeParty/ram:GlobalID", "schemeID", names["global"]),
        ),
        Variant(
            "BR-CL-11",
            "BR-CL-11",
            ("BR-CL-11", "FX-SCH-A-000581"),
            f"The scheme of the seller's legal registration identifier (BT-30-1) is written {names['legal']}, a name instead of an ISO 6523 code (the Factur-X profile rule FX-SCH-A-000581, on the same list, fails too).",
            f"Le schéma de l'identifiant d'immatriculation légale du vendeur (BT-30-1) est écrit {names['legal']}, un nom au lieu d'un code ISO 6523 (la règle du profil Factur-X FX-SCH-A-000581, sur la même liste, échoue aussi).",
            legal,
            edit=set_attribute(
                "//ram:SellerTradeParty/ram:SpecifiedLegalOrganization/ram:ID", "schemeID", names["legal"]
            ),
        ),
        Variant(
            "BR-CL-13",
            "BR-CL-13",
            ("BR-CL-13", "FX-SCH-A-000297"),
            "The scheme of the first line's item classification (BT-158-1) is written UNSPSC instead of its UNTDID 7143 code, TST (the Factur-X profile rule FX-SCH-A-000297, on the same list, fails too).",
            "Le schéma de la classification de l'article de la première ligne (BT-158-1) est écrit UNSPSC au lieu de son code UNTDID 7143, TST (la règle du profil Factur-X FX-SCH-A-000297, sur la même liste, échoue aussi).",
            edit=add_classification(CLASS_CODE, "UNSPSC"),
            fixed=add_classification(CLASS_CODE, "TST"),
        ),
        Variant(
            "BR-CL-14",
            "BR-CL-14",
            ("BR-CL-14", "FX-SCH-A-000568"),
            f"The buyer's country (BT-55) is written {w['country_name']} instead of the ISO 3166-1 code {buyer_country} (the Factur-X profile rule FX-SCH-A-000568, on the same list, fails too).",
            f"Le pays de l'acheteur (BT-55) est écrit {w['country_name']} au lieu du code ISO 3166-1 {buyer_country} (la règle du profil Factur-X FX-SCH-A-000568, sur la même liste, échoue aussi).",
            {"buyer": {**buyer, "address": (*buyer["address"][:3], w["country_name"])}},
        ),
        Variant(
            "BR-CL-15",
            "BR-CL-15",
            ("BR-CL-15", "FX-SCH-A-000628"),
            f"The first line's item country of origin (BT-159) is written {w['country_name']} instead of the ISO 3166-1 code {buyer_country} (the Factur-X profile rule FX-SCH-A-000628, on the same list, fails too).",
            f"Le pays d'origine de l'article de la première ligne (BT-159) est écrit {w['country_name']} au lieu du code ISO 3166-1 {buyer_country} (la règle du profil Factur-X FX-SCH-A-000628, sur la même liste, échoue aussi).",
            edit=add_origin(w["country_name"]),
            fixed=add_origin(buyer_country),
        ),
        Variant(
            "BR-CL-16",
            "BR-CL-16",
            ("BR-CL-16", "FX-SCH-A-000609"),
            f"The payment means code (BT-81) is SEPA, a word instead of a code from the UNCL 4461 list such as {base['payment_code']} (the Factur-X profile rule FX-SCH-A-000609, on the same list, fails too).",
            f"Le code du moyen de paiement (BT-81) est SEPA, un mot au lieu d'un code de la liste UNCL 4461 comme {base['payment_code']} (la règle du profil Factur-X FX-SCH-A-000609, sur la même liste, échoue aussi).",
            {"payment_code": "SEPA"},
        ),
        Variant(
            "BR-CL-17",
            "BR-CL-17",
            ("BR-CL-17", "BR-S-08", "FX-SCH-A-000599"),
            "A document level allowance's VAT category code (BT-95) is VAT, the tax type, instead of a category such as S, so the allowance lowers no VAT breakdown (BR-S-08, on the standard rate's taxable amount, and the Factur-X profile rule FX-SCH-A-000599 fail too).",
            "Le code de catégorie de TVA d'une remise au niveau du document (BT-95) est VAT, le type de taxe, au lieu d'une catégorie comme S : la remise ne réduit donc aucune ventilation de TVA (BR-S-08, sur la base du taux normal, et la règle du profil Factur-X FX-SCH-A-000599 échouent aussi).",
            allowance,
            edit=set_value(f"{DOC_AC}/ram:CategoryTradeTax/ram:CategoryCode", "VAT"),
        ),
        Variant(
            "BR-CL-18",
            "BR-CL-18",
            ("BR-CL-18", "FX-SCH-A-000587", "FX-SCH-A-000619"),
            f"The second line, at the reduced rate of {reduced} %, has the VAT category code AA, a UNCL 5305 code for a lower rate that EN 16931 does not use; its category S accepts any rate above zero (the Factur-X profile rules FX-SCH-A-000587 and FX-SCH-A-000619, on the same list, fail too).",
            f"La deuxième ligne, au taux réduit de {reduced} %, a le code de catégorie de TVA AA, un code de la liste UNCL 5305 pour un taux réduit qu'EN 16931 n'utilise pas ; sa catégorie S admet tout taux supérieur à zéro (les règles du profil Factur-X FX-SCH-A-000587 et FX-SCH-A-000619, sur la même liste, échouent aussi).",
            {"lines": [lines[0], second]},
            edit=edit_all(
                set_value("(//ram:IncludedSupplyChainTradeLineItem)[2]//ram:CategoryCode", "AA"),
                set_value(
                    f"{SETTLEMENT}/ram:ApplicableTradeTax[ram:RateApplicablePercent='{reduced}']/ram:CategoryCode", "AA"
                ),
            ),
        ),
        Variant(
            "BR-CL-19",
            "BR-CL-19",
            ("BR-CL-19", "FX-SCH-A-000601"),
            f"A document level allowance's reason code (BT-98) is its reason's text, {w['allowance']}, instead of a code from the UNCL 5189 list (the Factur-X profile rule FX-SCH-A-000601, on the same list, fails too).",
            f"Le code motif d'une remise au niveau du document (BT-98) est le texte de son motif, {w['allowance']}, au lieu d'un code de la liste UNCL 5189 (la règle du profil Factur-X FX-SCH-A-000601, sur la même liste, échoue aussi).",
            allowance,
            edit=set_value(f"{DOC_AC}/ram:ReasonCode", w["allowance"]),
        ),
        Variant(
            "BR-CL-20",
            "BR-CL-20",
            ("BR-CL-20", "FX-SCH-A-000604"),
            f"A document level charge's reason code (BT-105) is its reason's text, {w['charge']}, instead of a code from the UNCL 7161 list (the Factur-X profile rule FX-SCH-A-000604, on the same list, fails too).",
            f"Le code motif de frais au niveau du document (BT-105) est le texte de leur motif, {w['charge']}, au lieu d'un code de la liste UNCL 7161 (la règle du profil Factur-X FX-SCH-A-000604, sur la même liste, échoue aussi).",
            charge,
            edit=set_value(f"{DOC_AC}/ram:ReasonCode", w["charge"]),
        ),
        Variant(
            "BR-CL-21",
            "BR-CL-21",
            ("BR-CL-21", "FX-SCH-A-000626"),
            "The scheme of the first line's item standard identifier (BT-157-1), a GTIN, is written EAN instead of its ISO 6523 code, 0160 (the Factur-X profile rule FX-SCH-A-000626, on the same list, fails too).",
            "Le schéma de l'identifiant standard de l'article de la première ligne (BT-157-1), un GTIN, est écrit EAN au lieu de son code ISO 6523, 0160 (la règle du profil Factur-X FX-SCH-A-000626, sur la même liste, échoue aussi).",
            edit=add_product_id(GTIN, "EAN"),
            fixed=add_product_id(GTIN, "0160"),
        ),
        Variant(
            "BR-CL-22",
            "BR-CL-22",
            ("BR-CL-22", "FX-SCH-A-000589"),
            "The exemption reason code of the exempt line's VAT breakdown (BT-121) is VATEX-EU-132-1, cut short: the VATEX list has VATEX-EU-132 and VATEX-EU-132-1A to VATEX-EU-132-1Q (the Factur-X profile rule FX-SCH-A-000589, on the same list, fails too).",
            "Le code motif d'exonération de la ventilation de TVA de la ligne exonérée (BT-121) est VATEX-EU-132-1, tronqué : la liste VATEX a VATEX-EU-132 et VATEX-EU-132-1A à VATEX-EU-132-1Q (la règle du profil Factur-X FX-SCH-A-000589, sur la même liste, échoue aussi).",
            {"lines": [*lines, w["exempt_line"]]},
            edit=lambda root: _exemption_code(root, "VATEX-EU-132-1"),
        ),
        Variant(
            "BR-CL-23",
            "BR-CL-23",
            ("BR-CL-23", "FX-SCH-A-000613"),
            f"The first line's unit of measure code (BT-130) is {w['unit']}, an abbreviation instead of a code from UN/ECE Recommendation 20, such as C62 (the Factur-X profile rule FX-SCH-A-000613, on the same list, fails too).",
            f"Le code d'unité de mesure de la première ligne (BT-130) est {w['unit']}, une abréviation au lieu d'un code de la recommandation 20 de la CEE-ONU, comme C62 (la règle du profil Factur-X FX-SCH-A-000613, sur la même liste, échoue aussi).",
            edit=set_attribute("(//ram:BilledQuantity)[1]", "unitCode", w["unit"]),
        ),
        Variant(
            "BR-CL-24",
            "BR-CL-24",
            ("BR-CL-24", "FX-SCH-A-000287"),
            "A supporting document's attached file (BT-125), a CSV file, has the MIME code text/plain, which the rule does not allow; text/csv is allowed (the Factur-X profile rule FX-SCH-A-000287, on the same list, fails too).",
            "Le fichier joint d'un justificatif (BT-125), un fichier CSV, a le code MIME text/plain, que la règle n'admet pas ; text/csv est admis (la règle du profil Factur-X FX-SCH-A-000287, sur la même liste, échoue aussi).",
            edit=add_attachment("TS-2026-10", document, filename, "text/plain", TIMESHEET_CSV),
            fixed=add_attachment("TS-2026-10", document, filename, "text/csv", TIMESHEET_CSV),
        ),
        Variant(
            "BR-CL-25",
            "BR-CL-25",
            ("BR-CL-25", "FX-SCH-A-000582"),
            f"The scheme of the seller's electronic address (BT-34-1) is written {names['endpoint']} instead of its EAS code, {endpoint_scheme} (the Factur-X profile rule FX-SCH-A-000582, on the same list, fails too).",
            f"Le schéma de l'adresse électronique du vendeur (BT-34-1) est écrit {names['endpoint']} au lieu de son code EAS, {endpoint_scheme} (la règle du profil Factur-X FX-SCH-A-000582, sur la même liste, échoue aussi).",
            endpoint,
            edit=set_attribute(
                "//ram:SellerTradeParty/ram:URIUniversalCommunication/ram:URIID", "schemeID", names["endpoint"]
            ),
        ),
        Variant(
            "BR-CL-26",
            "BR-CL-26",
            ("BR-CL-26", "FX-SCH-A-000585"),
            "The scheme of the deliver-to location identifier (BT-71-1), a GLN, is written GLN instead of its ISO 6523 code, 0088 (the Factur-X profile rule FX-SCH-A-000585, on the same list, fails too).",
            "Le schéma de l'identifiant du lieu de livraison (BT-71-1), un GLN, est écrit GLN au lieu de son code ISO 6523, 0088 (la règle du profil Factur-X FX-SCH-A-000585, sur la même liste, échoue aussi).",
            edit=add_ship_to([(ship_id, "GLN")], ship_name),
            fixed=add_ship_to([(ship_id, "0088")], ship_name),
        ),
    )


# The VAT categories, as the rule pages name them: (code, English, French). K is the code of the BR-IC rules.
CATEGORY = {
    "S": ("standard rate", "taux normal"),
    "Z": ("zero rate", "taux zéro"),
    "E": ("exempt", "exonération"),
    "AE": ("reverse charge", "autoliquidation"),
    "K": ("intra-Community supply", "livraison intracommunautaire"),
    "G": ("export outside the EU", "exportation hors de l'UE"),
    "O": ("outside the scope of VAT", "hors du champ de la TVA"),
    "B": ("split payment, Italy's", "paiement scindé, italien"),
}
RULE_PREFIX = {"S": "BR-S", "Z": "BR-Z", "E": "BR-E", "AE": "BR-AE", "K": "BR-IC", "G": "BR-G", "O": "BR-O"}
SELLER_VAT = "//ram:SellerTradeParty/ram:SpecifiedTaxRegistration"
BUYER_VAT = "//ram:BuyerTradeParty/ram:SpecifiedTaxRegistration"


def _cat(code):
    """How a description names a category: "VAT category Z (zero rate)", « la catégorie de TVA Z (taux zéro) »."""
    en, fr = CATEGORY[code]
    return f"VAT category {code} ({en})", f"la catégorie de TVA {code} ({fr})"


def vat_categories(base):
    """One invalid variant per VAT category rule (BR-S, BR-Z, BR-E, BR-AE, BR-IC, BR-G, BR-O, BR-B) still without one,
    built on base. Each category has its context: the whole invoice in that category, its items, its buyer, its
    exemption reason and code (base["words"]["categories"]); the variant's edit then breaks the rule, so its fixed
    counterpart is the same invoice in that category.

    Some of these rules cannot fail alone in CII: BR-x-03 and BR-x-04 (an allowance, a charge) run the same test as
    BR-x-02 (the lines), so they fail with it; BR-O-11 and BR-O-12 run one test, and so do BR-O-13 and BR-O-14; a
    category's breakdown can only be missing next to another one (the Factur-X schema requires a breakdown), so for
    the categories that make a whole invoice its first rule fails with one breakdown per line. BR-S-02, BR-S-08 and
    BR-E-10 are in variants(); BR-S-09 fails in BR-CO-17's example."""
    w, lines = base["words"], base["lines"]
    std = lines[0][4]
    cats = w["categories"]

    def ctx(code, extra_lines=(), allowance=False, charge=False, **override):
        """The invoice in a category: its two lines (the base's quantities and prices), its exemption reason and code,
        its parties; plus an allowance or a charge in the same category."""
        c = cats[code]
        rate = None if code == "O" else ("0" if code != "B" else std)
        changes = {
            "lines": [(n, q, p, code, rate) for n, (_, q, p, *_) in zip(c["items"], lines, strict=True)]
            + list(extra_lines)
        }
        if c.get("reason"):
            changes["exemptions"] = {code: c["reason"]}
        for key in ("seller", "buyer", "ship_to", "buyer_reference"):
            if key in c:
                changes[key] = c[key]
        if allowance:
            changes["allowances"] = [("10.00", "95", w["allowance"], code, rate)]
        if charge:
            changes["charges"] = [("10.00", "FC", w["charge"], code, rate)]
        changes.update(override)
        return changes

    out = []

    def add(rule, fires, en, fr, changes=None, edit=None, fixed=None, fixed_changes=None):
        out.append(Variant(rule, rule, tuple(fires), en, fr, changes or {}, edit, fixed, fixed_changes))

    # BR-x-01: every category used has exactly one VAT breakdown
    for code in ("Z", "E"):
        en, fr = _cat(code)
        if code not in cats:
            continue
        p = RULE_PREFIX[code]
        mixed = ctx(code, extra_lines=[cats[code]["standard_line"]])
        add(
            f"{p}-01",
            (f"{p}-01",),
            f"The lines are in {en}, next to one at the standard rate, but the invoice has no VAT breakdown for their category.",
            f"Les lignes relèvent de {fr}, à côté d'une ligne au taux normal, mais la facture n'a pas de ventilation de TVA pour leur catégorie.",
            mixed,
            drop_breakdown(code),
        )
    for code in ("AE", "K", "G", "O"):
        if code not in cats:
            continue
        en, fr = _cat(code)
        p = RULE_PREFIX[code]
        add(
            f"{p}-01",
            (f"{p}-01", f"{p}-08"),
            f"The lines are in {en}, and the invoice gives one VAT breakdown per line instead of one for the category ({p}-08, on each breakdown's taxable amount, fails too).",
            f"Les lignes relèvent de {fr}, et la facture donne une ventilation de TVA par ligne au lieu d'une pour la catégorie ({p}-08, sur la base de chaque ventilation, échoue aussi).",
            ctx(code),
            breakdown_per_line(code),
        )
    # BR-S-01: one standard-rated line and no standard-rated breakdown (with two such lines, the CII test passes)
    add(
        "BR-S-01",
        ("BR-S-01", "BR-CO-14"),
        "The invoice has one standard-rated line and one exempt line, but no VAT breakdown for the standard rate; its VAT total still holds the line's VAT (BR-CO-14, on the VAT total against the breakdowns, fails too).",
        "La facture a une ligne au taux normal et une ligne exonérée, mais pas de ventilation de TVA pour le taux normal ; son total de TVA compte toujours la TVA de la ligne (BR-CO-14, sur le total de TVA comparé aux ventilations, échoue aussi).",
        {"lines": [lines[0], w["exempt_line"]]},
        drop_breakdown("S"),
    )

    # BR-x-02 to 04: the VAT numbers each category requires (or, for O, forbids), on a line, an allowance, a charge
    for code in ("S", "Z", "E", "AE", "K", "G", "O"):
        if code not in cats:
            continue
        en, fr = _cat(code)
        p = RULE_PREFIX[code]
        if code == "K":
            who_en, who_fr, edit = (
                "the buyer has no VAT number (BT-48)",
                "l'acheteur n'a pas de numéro de TVA (BT-48)",
                remove(BUYER_VAT),
            )
        elif code == "O":
            who_en, who_fr, edit = (
                "the seller gives a VAT number (BT-31)",
                "le vendeur indique un numéro de TVA (BT-31)",
                None,
            )
        else:
            who_en, who_fr, edit = (
                "the seller has no VAT number (BT-31)",
                "le vendeur n'a pas de numéro de TVA (BT-31)",
                remove(SELLER_VAT),
            )
        # O: the seller keeps its VAT number in the variant; the fixed counterpart removes it
        o_seller = {"seller": {**cats["O"]["seller"], "vat": base["seller"]["vat"]}} if code == "O" else {}
        o_fixed = remove(SELLER_VAT) if code == "O" else None
        if code != "S":
            add(
                f"{p}-02",
                (f"{p}-02",),
                f"The lines are in {en}, but {who_en}.",
                f"Les lignes relèvent de {fr}, mais {who_fr}.",
                {**ctx(code), **o_seller},
                edit,
                o_fixed,
            )
        for n, kind in (("03", "allowance"), ("04", "charge")):
            what_en = "A document level allowance" if kind == "allowance" else "A document level charge"
            what_fr = "Une remise au niveau du document" if kind == "allowance" else "Des frais au niveau du document"
            verb_fr = "relève" if kind == "allowance" else "relèvent"
            if code == "S":
                context = {f"{kind}s": [("10.00", "95" if kind == "allowance" else "FC", w[kind], "S", std)]}
            else:
                context = ctx(code, **{kind: True})
            add(
                f"{p}-{n}",
                (f"{p}-02", f"{p}-{n}"),
                f"{what_en} is in {en}, like the lines, but {who_en} ({p}-02, the same check for the lines, fails too).",
                f"{what_fr} {verb_fr} de {fr}, comme les lignes, mais {who_fr} ({p}-02, le même contrôle pour les lignes, échoue aussi).",
                {**context, **o_seller},
                edit,
                o_fixed,
            )

    # BR-x-05 to 07: the rate of a line, an allowance, a charge (S: above 0; Z, E, AE, K, G: 0; O: none)
    where = (
        ("05", "line", "The first line", "La première ligne", "BT-152", "", "relève"),
        (
            "06",
            "allowance",
            "A document level allowance",
            "Une remise au niveau du document",
            "BT-96",
            "allowance",
            "relève",
        ),
        ("07", "charge", "A document level charge", "Des frais au niveau du document", "BT-103", "charge", "relèvent"),
    )
    for code in ("Z", "E", "AE", "K", "G", "O"):
        if code not in cats:
            continue
        en, fr = _cat(code)
        p = RULE_PREFIX[code]
        for n, place, what_en, what_fr, bt, kind, verb_fr in where:
            context = ctx(code, **({kind: True} if kind else {}))
            if code == "O":
                add(
                    f"{p}-{n}",
                    (f"{p}-{n}",),
                    f"{what_en} is outside the scope of VAT (O), yet gives a VAT rate ({bt}), 0 %; this category has no rate.",
                    f"{what_fr} {verb_fr} de la catégorie hors du champ de la TVA (O), et indique pourtant un taux de TVA ({bt}), 0 % ; cette catégorie n'a pas de taux.",
                    context,
                    set_rate(place, "0"),
                )
            else:
                add(
                    f"{p}-{n}",
                    (f"{p}-{n}",),
                    f"{what_en} is in {en}, but its VAT rate ({bt}) is {std} % instead of 0 %.",
                    f"{what_fr} {verb_fr} de {fr}, mais son taux de TVA ({bt}) est de {std} % au lieu de 0 %.",
                    context,
                    set_rate(place, std),
                )
    # S: a rate of 0 under the standard rate, the invoice's breakdowns computed from it; the fixed counterpart has the
    # standard rate
    s_cases = (
        ("05", {"lines": [(*lines[0][:4], "0"), *lines[1:]]}, {"lines": lines}),
        (
            "06",
            {"allowances": [("10.00", "95", w["allowance"], "S", "0")]},
            {"allowances": [("10.00", "95", w["allowance"], "S", std)]},
        ),
        (
            "07",
            {"charges": [("10.00", "FC", w["charge"], "S", "0")]},
            {"charges": [("10.00", "FC", w["charge"], "S", std)]},
        ),
    )
    for (n, changes, fixed_changes), (_, _, what_en, what_fr, bt, _, verb_fr) in zip(s_cases, where, strict=True):
        add(
            f"BR-S-{n}",
            (f"BR-S-{n}",),
            f"{what_en} is in VAT category S (standard rate), but its VAT rate ({bt}) is 0 %.",
            f"{what_fr} {verb_fr} de la catégorie de TVA S (taux normal), mais son taux de TVA ({bt}) est de 0 %.",
            changes,
            fixed_changes=fixed_changes,
        )

    # BR-x-08 to 10: a category's breakdown: its taxable amount, its VAT amount, its exemption reason
    for code in ("Z", "E", "AE", "K", "G", "O"):
        if code not in cats:
            continue
        en, fr = _cat(code)
        p = RULE_PREFIX[code]
        add(
            f"{p}-08",
            (f"{p}-08",),
            f"The taxable amount of the VAT breakdown in {en} (BT-116) is 1 € more than the net amounts of its lines (BT-131).",
            f"La base de la ventilation de TVA de {fr} (BT-116) dépasse de 1 € la somme des montants nets de ses lignes (BT-131).",
            ctx(code),
            breakdown_basis(code, 1),
        )
        add(
            f"{p}-09",
            (f"{p}-09", "BR-CO-17"),
            f"The VAT breakdown in {en} has a VAT amount (BT-117) of {std} % of its taxable amount instead of 0; the VAT total follows it (BR-CO-17, on the VAT amount against the taxable amount times the rate, fails too).",
            f"La ventilation de TVA de {fr} a un montant de TVA (BT-117) de {std} % de sa base au lieu de 0 ; le total de TVA le suit (BR-CO-17, sur le montant de TVA comparé à la base multipliée par le taux, échoue aussi).",
            ctx(code),
            breakdown_vat(code, std),
        )
        if code not in ("Z", "E"):  # Z: below; E: BR-E-10 is in variants()
            add(
                f"{p}-10",
                (f"{p}-10",),
                f"The VAT breakdown in {en} gives neither an exemption reason (BT-120) nor an exemption reason code (BT-121).",
                f"La ventilation de TVA de {fr} n'indique ni motif d'exonération (BT-120) ni code de motif (BT-121).",
                ctx(code),
                no_exemption(code),
            )
    for code in ("S", "Z"):
        if code not in cats:
            continue
        context = ctx(code) if code != "S" else {}
        en, fr = _cat(code)
        reason = cats[code]["wrong_reason"]
        add(
            f"{RULE_PREFIX[code]}-10",
            (f"{RULE_PREFIX[code]}-10",),
            f"The VAT breakdown in {en} gives an exemption reason (BT-120), « {reason} »; a category that charges VAT, or charges it at 0 %, has none.",
            f"La ventilation de TVA de {fr} indique un motif d'exonération (BT-120), « {reason} » ; une catégorie qui applique la TVA, même à 0 %, n'en a pas.",
            context,
            add_exemption_reason(code, reason),
        )

    # BR-IC-11 and 12: an intra-Community supply says when and where the goods were delivered
    add(
        "BR-IC-11",
        ("BR-IC-11",),
        "The lines are an intra-Community supply (K), but the invoice gives neither an actual delivery date (BT-72) nor an invoicing period (BG-14).",
        "Les lignes sont une livraison intracommunautaire (K), mais la facture n'indique ni date de livraison (BT-72) ni période de facturation (BG-14).",
        ctx("K"),
        remove("//ram:ActualDeliverySupplyChainEvent"),
    )
    add(
        "BR-IC-12",
        ("BR-IC-12",),
        "The lines are an intra-Community supply (K), but the invoice has no deliver-to address, so no deliver-to country (BT-80).",
        "Les lignes sont une livraison intracommunautaire (K), mais la facture n'a pas d'adresse de livraison, donc pas de pays de livraison (BT-80).",
        ctx("K"),
        remove("//ram:ShipToTradeParty"),
    )

    # BR-B: split payment is Italian; the Factur-X profile does not accept category B at all
    b_en, b_fr = _cat("B")
    add(
        "BR-B-01",
        ("BR-B-01", "FX-SCH-A-000587", "FX-SCH-A-000619"),
        f"The lines are in {b_en} (B) on an invoice between two companies outside Italy (the Factur-X profile rules FX-SCH-A-000587 and FX-SCH-A-000619, which do not accept category B, fail too).",
        f"Les lignes relèvent de {b_fr} (B) sur une facture entre deux entreprises hors d'Italie (les règles du profil Factur-X FX-SCH-A-000587 et FX-SCH-A-000619, qui n'acceptent pas la catégorie B, échouent aussi).",
        {"lines": [(*line[:3], "B", line[4]) for line in lines]},
    )
    add(
        "BR-B-02",
        ("BR-B-01", "BR-B-02", "FX-SCH-A-000587", "FX-SCH-A-000619"),
        f"The second line is in {b_en} (B), the first at the standard rate (S) (BR-B-01, as the invoice is not Italian, and the Factur-X profile rules FX-SCH-A-000587 and FX-SCH-A-000619, which do not accept category B, fail too).",
        f"La deuxième ligne relève de {b_fr} (B), la première du taux normal (S) (BR-B-01, la facture n'étant pas italienne, et les règles du profil Factur-X FX-SCH-A-000587 et FX-SCH-A-000619, qui n'acceptent pas la catégorie B, échouent aussi).",
        {"lines": [lines[0], (*lines[1][:3], "B", lines[1][4])]},
    )
    # BR-O-11 to 14: an invoice outside the scope of VAT has no other category (two CII tests for four rules)
    if "O" not in cats:
        return tuple(out)
    add(
        "BR-O-11",
        ("BR-O-11", "BR-O-12"),
        f"The invoice is {CATEGORY['O'][0]} (O), but it also has an empty VAT breakdown at the standard rate, S {std} % (BR-O-12, whose test in CII is the same, fails too).",
        f"La facture est {CATEGORY['O'][1]} (O), mais elle a aussi une ventilation de TVA vide au taux normal, S {std} % (BR-O-12, dont le test en CII est le même, échoue aussi).",
        ctx("O"),
        add_breakdown("S", std),
    )
    o_lines = ctx("O")["lines"]
    add(
        "BR-O-12",
        ("BR-O-11", "BR-O-12"),
        f"The invoice is {CATEGORY['O'][0]} (O), but its second line is at the standard rate, S {std} %, with its own VAT breakdown (BR-O-11, whose test in CII is the same, fails too).",
        f"La facture est {CATEGORY['O'][1]} (O), mais sa deuxième ligne est au taux normal, S {std} %, avec sa propre ventilation de TVA (BR-O-11, dont le test en CII est le même, échoue aussi).",
        {**ctx("O"), "lines": [o_lines[0], (*o_lines[1][:3], "S", std)]},
        fixed_changes={"lines": o_lines},
    )
    for rule, kind, what_en, what_fr, twin in (
        ("BR-O-13", "allowances", "a document level allowance", "une remise au niveau du document", "BR-O-14"),
        ("BR-O-14", "charges", "a document level charge", "des frais au niveau du document", "BR-O-13"),
    ):
        reason_code = "95" if kind == "allowances" else "FC"
        word = w["allowance"] if kind == "allowances" else w["charge"]
        add(
            rule,
            ("BR-O-11", "BR-O-12", "BR-O-13", "BR-O-14"),
            f"The invoice is {CATEGORY['O'][0]} (O), but {what_en} is at the standard rate, S {std} %, with its own VAT breakdown ({twin}, whose test in CII is the same, and BR-O-11 and BR-O-12, on that breakdown, fail too).",
            f"La facture est {CATEGORY['O'][1]} (O), mais {what_fr} est au taux normal, S {std} %, avec sa propre ventilation de TVA ({twin}, dont le test en CII est le même, et BR-O-11 et BR-O-12, sur cette ventilation, échouent aussi).",
            {**ctx("O"), kind: [("10.00", reason_code, word, "S", std)]},
            fixed_changes={kind: [("10.00", reason_code, word, "O", None)]},
        )

    return tuple(out)


def _exemption_code(root, code):
    """Give the exempt category's VAT breakdown an exemption reason code (BT-121), after its category code."""
    for tax in root.xpath(EXEMPT_TAX, namespaces=cii.NS):
        insert(tax, new("ram:ExemptionReasonCode", code), after="CategoryCode")


# The fr target's example of BR-52 is an invoiced object identifier (BT-18) under a French rule's name, BR-FR-29: this
# one is the case any invoice can have, a supporting document. Its fixed counterpart gives the reference.
BR_52 = Variant(
    "BR-52",
    "BR-52",
    ("BR-52",),
    "An additional supporting document (BG-24) has a blank reference (BT-122).",
    "Un justificatif additionnel (BG-24) a une référence vide (BT-122).",
    edit=add_documents((" ", "916", "Timesheet", None)),
    fixed=add_documents(("TS-2026-10", "916", "Timesheet", None)),
)

VARIANTS = (
    *variants(GERMAN),
    BR_52,
    *decimals(GERMAN),
    *core(GERMAN),
    *code_lists(GERMAN),
    *vat_categories(GERMAN),
)


def build(variant=None):
    """The German invoice, or a variant of it, as an lxml root."""
    return edits.build(GERMAN, variant)
