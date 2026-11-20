"""Target "en16931": a domestic invoice between two companies in Germany, in the Factur-X EN 16931 profile (in Germany,
ZUGFeRD), that passes EN 16931 and the Factur-X EN 16931 profile rules, with no national field; plus one invalid
variant per EN 16931 rule.

The variants are written once, here, as a function of a base: this target builds them on its German invoice, and the
"fr" target on its French one, where the French rules sometimes fail next to them.
"""

from .. import cii, edits
from ..edits import (
    Variant,
    allowance_as_negative_line,
    edit_all,
    empty_period,
    line_charge,
    line_tax_type,
    no_exemption_reason,
    no_reasons,
    no_seller_identifiers,
    no_unit_code,
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

# Fictitious companies. The seller's GLN is in GS1's restricted circulation range (no company's number), its VAT
# number passes its check digit, the IBAN is the Bundesbank's bank code (10000000) with an all-zero account.
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
        "charge": "Shipping",
        "loyalty_allowance": "Loyalty discount",
        "line_charge": "Packaging",
        "exempt_line": ("Vocational training course", "1", "300.00", "E", "0"),
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


VARIANTS = variants(GERMAN)


def build(variant=None):
    """The German invoice, or a variant of it, as an lxml root."""
    return edits.build(GERMAN, variant)
