"""Target "fr": a French Factur-X EN 16931 invoice that passes EN 16931, the Factur-X EN 16931 profile rules
and BR-FR, plus one invalid variant per rule.

Each variant changes the baseline as little as possible. Its `fires` lists every rule id the official
rules report on it, so a variant documents its side effects too (for example BR-54 next to BR-FR-27).
"""

import dataclasses


from .. import cii, edits
from ..edits import (
    Variant,
    add_characteristic,
    add_documents,
    add_element,
    add_global_id,
    add_note,
    add_tax_representative,
    add_invoice_reference,
    add_payee,
    add_ship_to,
    billing_period,
    drop_scheme,
    edit_all,
    gross_price,
    no_payment_terms,
    one_more_decimal,
    paid_with_due_date,
    paid_without_due_date,
    set_text,
    tax_point_date,
)
from . import en16931
from ..cii import BUYER_SIREN, BUYER_SIRET, PAYEE_SIREN, PAYEE_SIRET, SELLER_SIREN, gln, luhn_complete

LANG = "fr"
RULES = {
    "EN 16931": "1.3.17 (CII)",
    "Factur-X": "1.09.2, EN 16931 profile",
    "BR-FR": "1.4.0.04 (France_RFE, FNFE-MPE)",
    "EXTENDED-CTC-FR": "1.4.0.04 (France_RFE), with the CII D22B schema, for the examples in that profile",
}
EXTENDED_CTC_FR = "urn:cen.eu:en16931:2017#conformant#urn.cpro.gouv.fr:1p0:extended-ctc-fr"


NOTES = cii.FRENCH["notes"]
BAR_B2B = ("BAR", "B2B")
SELLER, BUYER = cii.FRENCH["seller"], cii.FRENCH["buyer"]
ALLOWANCE = [("10.25", "95", cii.FRENCH["words"]["trade_allowance"], "S", "20")]  # 1 % of 1025.00
SELLER_SIRET_2 = luhn_complete(SELLER_SIREN + "0002")
BUYER_SIRET_2 = luhn_complete(BUYER_SIREN + "0003")  # also the deliver-to establishment
# A seller that belongs to a single VAT taxable person (assujetti unique): the group's 9-digit number as a seller
# identifier with scheme 0231 (BR-FR-32), the note TXD that says so (BR-FR-CO-14) and the group's VAT number as the
# seller's tax representative (BR-FR-CO-15). The number is fictitious, its last digit a Luhn key like a SIREN's.
SINGLE_TAXABLE_PERSON_ID = luhn_complete("05432109")
SINGLE_TAXABLE_PERSON = add_global_id("SellerTradeParty", SINGLE_TAXABLE_PERSON_ID, "0231")
SINGLE_TAXABLE_PERSON_VAT = add_tax_representative(
    "Groupe TVA Exemple", cii.vat_fr(SINGLE_TAXABLE_PERSON_ID), ("75008", "5 avenue de l'Exemple", "Paris", "FR")
)
SINGLE_TAXABLE_PERSON_NOTE = ("TXD", "MEMBRE_ASSUJETTI_UNIQUE")
SPACED_SIRET = f"{BUYER_SIRET_2[:3]} {BUYER_SIRET_2[3:6]} {BUYER_SIRET_2[6:9]} {BUYER_SIRET_2[9:]}"


def _with_french_rules(v):
    """A shared EN 16931 variant on the French invoice, with the French rules that fail next to it."""
    if v.id == "BR-CO-26":
        return dataclasses.replace(
            v,
            fires=("BR-CO-26", "BR-FR-10_BT-30", "BR-S-02"),
            en="The seller has no identifier at all: no SIRET (BT-29), no SIREN (BT-30), no VAT number (BT-31) (BR-FR-10, which requires the SIREN, and BR-S-02, which requires the VAT number for standard-rated VAT, fail too).",
            fr="Le vendeur n'a aucun identifiant : ni SIRET (BT-29), ni SIREN (BT-30), ni numéro de TVA (BT-31) (BR-FR-10, qui exige le SIREN, et BR-S-02, qui exige le numéro de TVA pour le taux normal, échouent aussi).",
        )
    if v.id == "BR-27":
        return dataclasses.replace(
            v,
            fires=("BR-27", "BR-FR-DEC-03_BT-146"),
            en="A discount is typed as a line with a negative net price (BT-146) instead of a document level allowance (BR-FR-DEC-03, which wants a positive price outside the billing frames S9, M9 and B9, fails too).",
            fr="Une remise est saisie comme une ligne au prix net négatif (BT-146) au lieu d'une remise au niveau du document (BR-FR-DEC-03, qui exige un prix positif hors des cadres de facturation S9, M9 et B9, échoue aussi).",
        )
    if v.id in FRENCH_ALSO:
        fires, en, fr = FRENCH_ALSO[v.id]
        return dataclasses.replace(v, fires=(*v.fires, *fires), en=en, fr=fr)
    return v


# The core and code list variants (en16931.core, en16931.code_lists) where a French rule fails next to the EN 16931
# one, on the same data: the French rules it adds, and the description that names them.
FR_02 = (
    "France's BR-FR-02, on the characters of a number",
    "la règle française BR-FR-02, sur les caractères d'un numéro",
)
FR_04 = (
    "France's BR-FR-04, on its own list of type codes",
    "la règle française BR-FR-04, sur sa propre liste de codes types",
)
FR_CO_12 = (
    "France's BR-FR-CO-12, which asks an invoice in another currency than EUR for its VAT in euros",
    "la règle française BR-FR-CO-12, qui demande à une facture dans une autre devise que EUR sa TVA en euros",
)
FRENCH_ALSO = {
    "BR-02": (
        ("BR-FR-02_BT-1",),
        f"The invoice number (BT-1) is empty ({FR_02[0]}, fails too).",
        f"Le numéro de facture (BT-1) est vide ({FR_02[1]}, échoue aussi).",
    ),
    "BR-04": (
        ("BR-FR-04_BT-3",),
        f"The invoice type code (BT-3) is empty (BR-CL-01, on the list of type codes, and {FR_04[0]}, fail too).",
        f"Le code type de document (BT-3) est vide (BR-CL-01, sur la liste des codes types, et {FR_04[1]}, échouent aussi).",
    ),
    "BR-05": (
        ("BR-FR-CO-12_BT-5",),
        f"The invoice currency code (BT-5) is empty, and so is the currency of the VAT total (BR-CL-03 and BR-CL-04, on the list of currency codes, and {FR_CO_12[0]}, fail too).",
        f"Le code de la devise de la facture (BT-5) est vide, comme la devise du total de TVA (BR-CL-03 et BR-CL-04, sur la liste des codes devises, et {FR_CO_12[1]}, échouent aussi).",
    ),
    "BR-28": (
        ("BR-FR-DEC-03_BT-148",),
        "The first line's gross price (BT-148) is written with a minus sign; its price discount (BT-147) and net price (BT-146) are right (France's BR-FR-DEC-03, which wants a positive price outside the billing frames S9, M9 and B9, fails too).",
        "Le prix brut de la première ligne (BT-148) est écrit avec un signe moins ; son rabais (BT-147) et son prix net (BT-146) sont justes (la règle française BR-FR-DEC-03, qui exige un prix positif hors des cadres de facturation S9, M9 et B9, échoue aussi).",
    ),
    "BR-55": (
        ("BR-FR-02_BT-25",),
        f"The invoice refers to a preceding invoice (BG-3) whose reference (BT-25) is empty ({FR_02[0]}, fails too).",
        f"La facture fait référence à une facture antérieure (BG-3) dont la référence (BT-25) est vide ({FR_02[1]}, échoue aussi).",
    ),
    "BR-CL-01": (
        ("BR-FR-04_BT-3",),
        f"The invoice type code (BT-3) is INV, a word instead of a code from the UNTDID 1001 list such as 380 (the Factur-X profile rule FX-SCH-A-000555, on the same list, and {FR_04[0]}, fail too).",
        f"Le code type de document (BT-3) est INV, un mot au lieu d'un code de la liste UNTDID 1001 comme 380 (la règle du profil Factur-X FX-SCH-A-000555, sur la même liste, et {FR_04[1]}, échouent aussi).",
    ),
    "BR-CL-04": (
        ("BR-FR-CO-12_BT-5",),
        f"The invoice currency (BT-5) is written EURO instead of the ISO 4217 code EUR, and so is the VAT total's currency (BR-CL-03, the same check on an amount's currency, the Factur-X profile rules FX-SCH-A-000595 and FX-SCH-A-000606, and {FR_CO_12[0]}, fail too).",
        f"La devise de la facture (BT-5) est écrite EURO au lieu du code ISO 4217 EUR, comme la devise du total de TVA (BR-CL-03, le même contrôle sur la devise d'un montant, les règles du profil Factur-X FX-SCH-A-000595 et FX-SCH-A-000606, et {FR_CO_12[1]}, échouent aussi).",
    ),
    "BR-CL-05": (
        ("BR-FR-CO-12_BT-5",),
        f"The invoice is in US dollars; its VAT accounting currency (BT-6) is written EURO instead of the ISO 4217 code EUR, and so is the currency of its VAT total in that currency (BR-CL-03, the same check on an amount's currency, the Factur-X profile rules FX-SCH-A-000607 and FX-SCH-A-000610, and {FR_CO_12[0]}, fail too).",
        f"La facture est en dollars américains ; sa devise de comptabilisation de la TVA (BT-6) est écrite EURO au lieu du code ISO 4217 EUR, comme la devise de son total de TVA dans cette devise (BR-CL-03, le même contrôle sur la devise d'un montant, les règles du profil Factur-X FX-SCH-A-000607 et FX-SCH-A-000610, et {FR_CO_12[1]}, échouent aussi).",
    ),
    "BR-CL-11": (
        ("BR-FR-09_BT-29", "BR-FR-10_BT-30"),
        "The scheme of the seller's SIREN, its legal registration identifier (BT-30-1), is written SIREN, a name instead of the ISO 6523 code 0002 (the Factur-X profile rule FX-SCH-A-000581, on the same list, and France's BR-FR-10 and BR-FR-09, which read the SIREN under the code 0002 only, fail too).",
        "Le schéma du SIREN du vendeur, son identifiant d'immatriculation légale (BT-30-1), est écrit SIREN, un nom au lieu du code ISO 6523 0002 (la règle du profil Factur-X FX-SCH-A-000581, sur la même liste, et les règles françaises BR-FR-10 et BR-FR-09, qui ne lisent le SIREN que sous le code 0002, échouent aussi).",
    ),
    "BR-CL-17": (
        ("BR-FR-15_BT-95_BT-102",),
        "A document level allowance's VAT category code (BT-95) is VAT, the tax type, instead of a category such as S, so the allowance lowers no VAT breakdown (BR-S-08, on the standard rate's taxable amount, the Factur-X profile rule FX-SCH-A-000599, on the same list, and France's BR-FR-15, on the categories allowed in France, fail too).",
        "Le code de catégorie de TVA d'une remise au niveau du document (BT-95) est VAT, le type de taxe, au lieu d'une catégorie comme S : la remise ne réduit donc aucune ventilation de TVA (BR-S-08, sur la base du taux normal, la règle du profil Factur-X FX-SCH-A-000599, sur la même liste, et la règle française BR-FR-15, sur les catégories admises en France, échouent aussi).",
    ),
    "BR-CL-18": (
        ("BR-FR-15_BT-95_BT-118", "BR-FR-15_BT-95_BT-151"),
        "The second line, at the reduced rate of 5.5 %, has the VAT category code AA, a UNCL 5305 code for a lower rate that EN 16931 does not use; its category S accepts any rate above zero (the Factur-X profile rules FX-SCH-A-000587 and FX-SCH-A-000619, on the same list, and France's BR-FR-15, on the categories allowed in France, fail too).",
        "La deuxième ligne, au taux réduit de 5,5 %, a le code de catégorie de TVA AA, un code de la liste UNCL 5305 pour un taux réduit qu'EN 16931 n'utilise pas ; sa catégorie S admet tout taux supérieur à zéro (les règles du profil Factur-X FX-SCH-A-000587 et FX-SCH-A-000619, sur la même liste, et la règle française BR-FR-15, sur les catégories admises en France, échouent aussi).",
    ),
}


# The EN 16931 variants, written once in the en16931 target and built here on the French invoice. BR-CO-25 is French
# only (its example is an EXTENDED-CTC-FR invoice) and keeps its place, before BR-CO-26.
EN16931 = tuple(_with_french_rules(v) for v in en16931.variants(cii.FRENCH))
_CO_26 = [v.id for v in EN16931].index("BR-CO-26")

# The EN 16931 decimals rules (BR-DEC) on the French invoice: each with the business term of its amount, which names
# the file, and the terms of the BR-FR-DEC-01 assertion that fails next to it. BR-DEC-14 and BR-DEC-18 (the totals
# BT-112 and BT-115) share one example, BR-FR-DEC-01; BR-DEC-13 keeps its own name (below).
FR_DEC_01 = {
    "BR-DEC-01": ("BT-92", "BT-92_BT-99"),
    "BR-DEC-02": ("BT-93", "BT-93_BT-100"),
    "BR-DEC-05": ("BT-99", "BT-92_BT-99"),
    "BR-DEC-06": ("BT-100", "BT-93_BT-100"),
    "BR-DEC-09": ("BT-106", "BT-106"),
    "BR-DEC-10": ("BT-107", "BT-107"),
    "BR-DEC-11": ("BT-108", "BT-108"),
    "BR-DEC-12": ("BT-109", "BT-109"),
    # France_RFE's CII file checks BT-110 and BT-111 in two rules with the same context, every VAT total: the first,
    # BT-110's, takes both, so a VAT total in the accounting currency fails under BT-110's assertion id.
    "BR-DEC-15": ("BT-111", "BT-110"),
    "BR-DEC-16": ("BT-113", "BT-113"),
    "BR-DEC-17": ("BT-114", "BT-114"),
    "BR-DEC-19": ("BT-116", "BT-116"),
    "BR-DEC-20": ("BT-117", "BT-117"),
    "BR-DEC-23": ("BT-131", "BT-131"),
    "BR-DEC-24": ("BT-136", "BT-136_BT-141"),
    "BR-DEC-25": ("BT-137", "BT-137_BT-142"),
    "BR-DEC-27": ("BT-141", "BT-136_BT-141"),
    "BR-DEC-28": ("BT-142", "BT-137_BT-142"),
}


def _under_br_fr_dec_01(v):
    """A shared EN 16931 decimals variant on the French invoice, named for BR-FR-DEC-01, which fails next to it."""
    term, terms = FR_DEC_01[v.rule]
    return dataclasses.replace(
        v,
        id=f"BR-FR-DEC-01-{term}",
        rule="BR-FR-DEC-01",
        fires=(f"BR-FR-DEC-01_{terms}", v.rule),
        en=f"{v.en[:-1]} (EN 16931 {v.rule} fires too).",
        fr=f"{v.fr[:-1]} (la règle EN 16931 {v.rule} se déclenche aussi).",
    )


# The core EN 16931 rules (BR-01 to BR-65) and the code list rules (BR-CL) on the French invoice, with the French rules
# that fail next to them.
CORE = tuple(_with_french_rules(v) for v in (*en16931.core(cii.FRENCH), *en16931.code_lists(cii.FRENCH)))

_FRENCH_DECIMALS = en16931.decimals(cii.FRENCH)
DECIMALS = tuple(_under_br_fr_dec_01(v) for v in _FRENCH_DECIMALS if v.rule in FR_DEC_01)
# BR-FR-DEC-01's own example for the VAT total (BT-110), where no EN 16931 rule fails, and BR-DEC-13's, where the VAT
# total is not rounded to the cent, take their place before BT-111.
_BT_111 = [v.id for v in DECIMALS].index("BR-FR-DEC-01-BT-111")
BR_DEC_13 = dataclasses.replace(
    next(v for v in _FRENCH_DECIMALS if v.rule == "BR-DEC-13"),
    fires=("BR-DEC-13", "BR-CO-14", "BR-FR-DEC-01_BT-110"),
    en="The VAT total (BT-110) is not rounded to the cent: it has 3 decimals, so it is no longer the sum of the VAT breakdown (EN 16931 BR-CO-14 and France's BR-FR-DEC-01 fail too).",
    fr="Le total de TVA (BT-110) n'est pas arrondi au centime : il a 3 décimales, et n'est donc plus la somme de la ventilation de TVA (la règle EN 16931 BR-CO-14 et la règle française BR-FR-DEC-01 échouent aussi).",
)

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
        edit=add_documents(("PJ-1", "916", "CONTRAT", None)),
    ),
    Variant(
        "BR-FR-18",
        "BR-FR-18",
        ("BR-FR-18_BT-123",),
        "Two attachments are described as LISIBLE (BT-123): only one readable copy is allowed.",
        "Deux pièces jointes sont décrites LISIBLE (BT-123) : une seule version lisible est permise.",
        edit=add_documents(("PJ-1", "916", "LISIBLE", None), ("PJ-2", "916", "LISIBLE", None)),
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
        edit=add_characteristic(" ", "Bleu"),
    ),
    Variant(
        "BR-FR-28",
        "BR-FR-28",
        ("BR-FR-28-Value", "BR-FREXT-54-2"),
        "An EXTENDED-CTC-FR invoice: an item attribute (BG-32) gives its value both as text (BT-161) and as a measure with its unit; only one is allowed (the EXTENDED-CTC-FR profile rule BR-FREXT-54-2 says the same and fails too).",
        "Une facture au profil EXTENDED-CTC-FR : un attribut d'article (BG-32) donne sa valeur à la fois en texte (BT-161) et en mesure avec son unité ; une seule est permise (la règle du profil EXTENDED-CTC-FR BR-FREXT-54-2 dit la même chose et échoue aussi).",
        {"profile": EXTENDED_CTC_FR},
        edit=add_characteristic("Durée", "2 jours", measure=("2", "DAY")),
        fixed=add_characteristic("Durée", "2 jours"),
    ),
    Variant(
        "BR-FR-29",
        "BR-FR-29",
        ("BR-FR-29_BT-18",),
        "Two invoiced object identifiers (BT-18) use the reference type AFL.",
        "Deux identifiants d'objet facturé (BT-18) utilisent le type de référence AFL.",
        edit=add_documents(("OBJ-1", "130", None, "AFL"), ("OBJ-2", "130", None, "AFL")),
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
        "BR-FR-CO-14",
        "BR-FR-CO-14",
        ("BR-FR-CO-14_BT-29-1",),
        "The seller is a member of a single VAT taxable person (an identifier with scheme 0231, BT-29-1) but the invoice has no note TXD saying MEMBRE_ASSUJETTI_UNIQUE.",
        "Le vendeur est membre d'un assujetti unique (un identifiant au schéma 0231, BT-29-1) mais la facture n'a pas de mention TXD « MEMBRE_ASSUJETTI_UNIQUE ».",
        edit=edit_all(SINGLE_TAXABLE_PERSON, SINGLE_TAXABLE_PERSON_VAT),
        fixed=edit_all(SINGLE_TAXABLE_PERSON, SINGLE_TAXABLE_PERSON_VAT, add_note(*SINGLE_TAXABLE_PERSON_NOTE)),
    ),
    Variant(
        "BR-FR-CO-15",
        "BR-FR-CO-15",
        ("BR-FR-CO-15_BT-29-1",),
        "The seller is a member of a single VAT taxable person (an identifier with scheme 0231, BT-29-1) but the invoice gives no tax representative (BG-11) with the single taxable person's VAT number (BT-63).",
        "Le vendeur est membre d'un assujetti unique (un identifiant au schéma 0231, BT-29-1) mais la facture n'indique pas de représentant fiscal (BG-11) avec le numéro de TVA de l'assujetti unique (BT-63).",
        {"notes": [*NOTES, SINGLE_TAXABLE_PERSON_NOTE]},
        edit=SINGLE_TAXABLE_PERSON,
        fixed=edit_all(SINGLE_TAXABLE_PERSON, SINGLE_TAXABLE_PERSON_VAT),
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
        edit=add_invoice_reference("F2026-" + "0" * 30),
    ),
    Variant(
        "BR-FR-02-BT-25",
        "BR-FR-02",
        ("BR-FR-02_BT-25",),
        "The preceding invoice reference (BT-25) contains a character outside letters, digits and + - _ /.",
        "La référence de la facture antérieure (BT-25) contient un caractère autre que lettres, chiffres et + - _ /.",
        edit=add_invoice_reference("F2026.0001"),
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
        edit=add_invoice_reference("F2026-0001", "19990915"),
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
        edit=add_documents((" ", "130", None, "AFL")),
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
        edit=drop_scheme("SellerTradeParty"),
    ),
    Variant(
        "BR-FR-DEC-01",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-112", "BR-FR-DEC-01_BT-115", "BR-DEC-14", "BR-DEC-18"),
        "The total with VAT (BT-112) and the amount due (BT-115) are written with 3 decimals (EN 16931 BR-DEC-14 and BR-DEC-18 fire too).",
        "Le total TTC (BT-112) et le net à payer (BT-115) sont écrits avec 3 décimales (les règles EN 16931 BR-DEC-14 et BR-DEC-18 se déclenchent aussi).",
        edit=edit_all(
            one_more_decimal(en16931.SUMS, "GrandTotalAmount"), one_more_decimal(en16931.SUMS, "DuePayableAmount")
        ),
    ),
    *EN16931[:_CO_26],
    Variant(
        "BR-CO-25",
        "BR-CO-25",
        ("BR-CO-25",),
        "An EXTENDED-CTC-FR invoice with an amount due (BT-115) gives neither a payment due date (BT-9) nor payment terms (BT-20).",
        "Une facture au profil EXTENDED-CTC-FR, avec un net à payer (BT-115), n'indique ni date d'échéance (BT-9) ni conditions de paiement (BT-20).",
        {"profile": EXTENDED_CTC_FR},
        edit=no_payment_terms,
    ),
    *EN16931[_CO_26:],
    Variant(
        "BR-FR-03-BT-7",
        "BR-FR-03",
        ("BR-FR-03_BT-7",),
        "The VAT point date (BT-7) has a year outside 2000-2099.",
        "La date d'exigibilité de la TVA (BT-7) a une année hors de 2000-2099.",
        {"due_date_type": None},
        edit=tax_point_date("19991020"),
    ),
    Variant(
        "BR-FR-03-BT-73",
        "BR-FR-03",
        ("BR-FR-03_BT-73",),
        "The invoicing period start date (BT-73) has a year outside 2000-2099.",
        "La date de début de la période de facturation (BT-73) a une année hors de 2000-2099.",
        edit=billing_period("19991001", "20261031"),
    ),
    Variant(
        "BR-FR-03-BT-74",
        "BR-FR-03",
        ("BR-FR-03_BT-74",),
        "The invoicing period end date (BT-74) has a year outside 2000-2099.",
        "La date de fin de la période de facturation (BT-74) a une année hors de 2000-2099.",
        edit=billing_period("20261001", "21001031"),
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
        edit=add_payee([(SELLER["global_id"][0], "0009")], PAYEE_SIREN),
    ),
    Variant(
        "BR-FR-09-ship-to",
        "BR-FR-09",
        ("BR-FR-09_BT-71",),
        "The deliver-to location identifier with scheme 0009 (SIRET, BT-71) is not 14 digits: it has spaces.",
        "L'identifiant du lieu de livraison au schéma 0009 (SIRET, BT-71) n'a pas 14 chiffres : il contient des espaces.",
        edit=add_ship_to([(SPACED_SIRET, "0009")]),
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
        edit=set_text("SpecifiedTradeAllowanceCharge", "CategoryTradeTax", "RateApplicablePercent", text="20.000"),
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
        edit=add_documents((" ", "130", None, "AVV")),
    ),
    Variant(
        "BR-FR-CO-09-BT-9",
        "BR-FR-CO-09",
        ("BR-FR-CO-09_BT-23-3",),
        "An already paid invoice (billing frame S2) has no payment due date (BT-9).",
        "Une facture déjà payée (cadre de facturation S2) n'a pas de date d'échéance (BT-9).",
        {"billing_frame": "S2"},
        edit=paid_without_due_date,
        fixed=paid_with_due_date,
    ),
    Variant(
        "BR-FR-CO-10-BT-29-2",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-29-2",),
        "The seller has two identifiers (BT-29) with the same scheme 0009.",
        "Le vendeur a deux identifiants (BT-29) au même schéma 0009.",
        edit=add_global_id("SellerTradeParty", SELLER_SIRET_2, "0009"),
    ),
    Variant(
        "BR-FR-CO-10-BT-46-1",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-46-1", "FX-SCH-A-000420"),
        "The buyer's identifier (BT-46) has no scheme identifier; the Factur-X profile rules reject it too.",
        "L'identifiant de l'acheteur (BT-46) n'a pas d'identifiant de schéma ; les règles du profil Factur-X le refusent aussi.",
        edit=drop_scheme("BuyerTradeParty"),
    ),
    Variant(
        "BR-FR-CO-10-BT-46-2",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-46-2", "FX-SCH-A-000164"),
        "The buyer has two identifiers (BT-46) with the same scheme 0009; the Factur-X profile rules reject it too.",
        "L'acheteur a deux identifiants (BT-46) au même schéma 0009 ; les règles du profil Factur-X le refusent aussi.",
        edit=add_global_id("BuyerTradeParty", BUYER_SIRET_2, "0009"),
    ),
    Variant(
        "BR-FR-CO-10-BT-60-1",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-60-1", "FX-SCH-A-000470"),
        "The payee's identifier (BT-60) has no scheme identifier; the Factur-X profile rules reject it too.",
        "L'identifiant du bénéficiaire (BT-60) n'a pas d'identifiant de schéma ; les règles du profil Factur-X le refusent aussi.",
        edit=add_payee([(PAYEE_SIRET, None)], PAYEE_SIREN),
    ),
    Variant(
        "BR-FR-CO-10-BT-60-2",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-60-2", "FX-SCH-A-000468"),
        "The payee has two identifiers (BT-60) with the same scheme 0009; the Factur-X profile rules reject it too.",
        "Le bénéficiaire a deux identifiants (BT-60) au même schéma 0009 ; les règles du profil Factur-X le refusent aussi.",
        edit=add_payee([(PAYEE_SIRET, "0009"), (luhn_complete(PAYEE_SIREN + "0002"), "0009")], PAYEE_SIREN),
    ),
    Variant(
        "BR-FR-CO-10-BT-71-1",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-71-1", "FX-SCH-A-000453"),
        "The deliver-to location identifier (BT-71) has no scheme identifier; the Factur-X profile rules reject it too.",
        "L'identifiant du lieu de livraison (BT-71) n'a pas d'identifiant de schéma ; les règles du profil Factur-X le refusent aussi.",
        edit=add_ship_to([(BUYER_SIRET_2, None)]),
    ),
    # Two SIRETs (0009) here would stop France_RFE 1.4.0.04's BR-FR-09 rule with an error (its $siren variable calls
    # substring() on both): two GLNs instead.
    Variant(
        "BR-FR-CO-10-BT-71-2",
        "BR-FR-CO-10",
        ("BR-FR-CO-10_BT-71-2", "FX-SCH-A-000452"),
        "The deliver-to party has two location identifiers (BT-71) with the same scheme 0088 (GLN); the Factur-X profile rules reject it too.",
        "Le lieu de livraison a deux identifiants (BT-71) au même schéma 0088 (GLN) ; les règles du profil Factur-X le refusent aussi.",
        edit=add_ship_to([(gln("200000000001"), "0088"), (gln("200000000002"), "0088")]),
    ),
    # Amounts with 3 decimals (BR-FR-DEC-01): the value is unchanged, only its notation, but for BR-DEC-13 and BT-111.
    *DECIMALS[:_BT_111],
    Variant(
        "BR-FR-DEC-01-BT-110",
        "BR-FR-DEC-01",
        ("BR-FR-DEC-01_BT-110",),
        "The VAT total (BT-110) has 3 decimals.",
        "Le total de TVA (BT-110) a 3 décimales.",
        edit=one_more_decimal(en16931.SUMS, "TaxTotalAmount"),
    ),
    BR_DEC_13,
    *DECIMALS[_BT_111:],
    Variant(
        "BR-FR-DEC-02-BT-149",
        "BR-FR-DEC-02",
        ("BR-FR-DEC-02_BT-149",),
        "An item price base quantity (BT-149) has 5 decimals.",
        "La quantité de base du prix d'un article (BT-149) a 5 décimales.",
        edit=add_element(
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
        edit=gross_price("500.00", "50.0000000"),
    ),
    Variant(
        "BR-FR-DEC-03-BT-148",
        "BR-FR-DEC-03",
        ("BR-FR-DEC-03_BT-148",),
        "An item gross price (BT-148) has 7 decimals.",
        "Le prix brut d'un article (BT-148) a 7 décimales.",
        edit=gross_price("500.0000000", "50.00"),
    ),
    # the core EN 16931 rules and the code list rules (BR-CL), written once in the en16931 target
    *CORE,
)


def build(variant=None):
    """The French invoice, or a variant of it, as an lxml root."""
    return edits.build(cii.FRENCH, variant)
