"""Build a Factur-X EN 16931 (CII) invoice from a dict of settings.

Totals and VAT breakdowns are computed from the lines and allowances, so a
mutation that changes a price or a rate stays arithmetically consistent.
All identifiers are fictitious but pass their check digits (Luhn, IBAN, VAT key). The SIRENs start
with 0, a range with no company in the SIRENE directory (recherche-entreprises.api.gouv.fr, checked
2026-11-05). The IBAN has a real bank code (30004) and an all-zero branch and account.
"""

from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal

from lxml import etree

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}
CENT = Decimal("0.01")


def luhn_ok(digits):
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def luhn_complete(prefix):
    """Append the digit that makes prefix pass the Luhn check."""
    return next(prefix + str(d) for d in range(10) if luhn_ok(prefix + str(d)))


def vat_fr(siren):
    return f"FR{(12 + 3 * (int(siren) % 97)) % 97:02d}{siren}"


def iban_fr(bank, branch, account):
    rib_key = 97 - (89 * int(bank) + 15 * int(branch) + 3 * int(account)) % 97
    bban = f"{bank}{branch}{account}{rib_key:02d}"
    check = 98 - int(bban + "152700") % 97  # "FR00" moved to the end, F=15 R=27
    return f"FR{check:02d}{bban}", bban


def vat_de(serial):
    """A German VAT number (USt-IdNr.): DE, 8 digits and their check digit (ISO 7064, MOD 11,10)."""
    product = 10
    for d in serial:
        total = (int(d) + product) % 10 or 10
        product = 2 * total % 11
    check = 11 - product
    return f"DE{serial}{0 if check == 10 else check}"


def iban_de(bank, account):
    bban = f"{bank}{account}"
    return f"DE{98 - int(bban + '131400') % 97:02d}{bban}"  # "DE00" moved to the end, D=13 E=14


SELLER_SIREN = luhn_complete("01234567")
SELLER_SIRET = luhn_complete(SELLER_SIREN + "0001")
BUYER_SIREN = luhn_complete("07654321")
BUYER_SIRET = luhn_complete(BUYER_SIREN + "0002")
IBAN, RIB = iban_fr("30004", "00000", "00000000000")
PAYEE_SIREN = luhn_complete("03456789")  # a factoring company, for the payee (BG-10) variants
PAYEE_SIRET = luhn_complete(PAYEE_SIREN + "0001")


def gln(prefix12):
    """A GLN (scheme 0088) with its check digit. Prefix 2 is GS1's restricted circulation range: no company's number."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(prefix12))
    return prefix12 + str((10 - total % 10) % 10)


# The French baseline: passes EN 16931, the Factur-X EN 16931 profile and BR-FR (target "fr").
FRENCH = {
    "profile": "urn:cen.eu:en16931:2017",
    "billing_frame": "S1",  # BT-23, BR-FR-08 list
    "number": "F2026-0042",  # BT-1
    "type_code": "380",  # BT-3
    "issue_date": "20261020",  # BT-2
    "issue_date_format": "102",
    "notes": [
        ("PMT", "Indemnité forfaitaire pour frais de recouvrement : 40 EUR."),
        ("PMD", "Pénalités de retard : trois fois le taux d'intérêt légal."),
        ("AAB", "Pas d'escompte pour paiement anticipé."),
    ],
    "buyer_reference": "FACTURES_PUBLIQUES",  # BT-10, Chorus Pro code service
    "seller": {
        "name": "Atelier Exemple SAS",
        "global_id": (SELLER_SIRET, "0009"),  # BT-29
        "legal_id": (SELLER_SIREN, "0002"),  # BT-30
        "address": ("75011", "10 rue de l'Exemple", "Paris", "FR"),
        "endpoint": (SELLER_SIREN, "0225"),  # BT-34
        "vat": vat_fr(SELLER_SIREN),  # BT-31
    },
    "buyer": {
        "name": "Commune d'Exemple",
        "global_id": (BUYER_SIRET, "0009"),  # BT-46
        "legal_id": (BUYER_SIREN, "0002"),  # BT-47
        "address": ("69001", "1 place de la Mairie", "Lyon", "FR"),
        "endpoint": (BUYER_SIREN, "0225"),  # BT-49
        "department": None,  # Chorus Pro "nom du service" (OCA puts it here)
    },
    "invoicee": None,  # Chorus Pro "valideur" (InvoiceeTradeParty)
    "order_reference": "1234567890",  # BT-13, Chorus Pro numéro d'engagement
    "delivery_date": "20261015",
    "currency": "EUR",  # BT-5
    "tax_currency": None,  # BT-6
    "payment_code": "30",  # BT-81
    "iban": IBAN,  # BT-84
    "proprietary_account": None,  # BT-84 when not an IBAN
    "bic": "BNPAFRPPXXX",  # BT-86
    "due_date": "20261119",
    "due_date_type": "5",  # BT-8
    "tax_type": "VAT",
    "lines": [
        # name, quantity, unit price, VAT category, VAT rate[, line allowance amount (BT-136)]
        ("Atelier de formation", "2", "450.00", "S", "20"),
        ("Support de cours", "10", "12.50", "S", "20"),
    ],
    "allowances": [],  # (amount, reason code, reason, category, rate)
    "charges": [],  # same shape, document level charges (BG-21)
    "payment_terms": "Paiement à 30 jours par virement.",  # BT-20
    "exemption_reason": "Exonération de TVA",  # BT-120, for the categories that need one
    "line_allowance_reason": "Remise",  # BT-139, for a line with a discount
    # the texts the EN 16931 variants add to the invoice (targets/en16931.py, variants)
    "words": {
        "allowance": "Remise",
        "trade_allowance": "Remise commerciale",
        "charge": "Frais de port",
        "loyalty_allowance": "Remise fidélité",
        "line_charge": "Emballage",
        "exempt_line": ("Formation professionnelle continue", "1", "300.00", "E", "0"),
        "tax_representative": (
            "Représentation Fiscale Exemple",
            vat_fr(luhn_complete("06543210")),
            ("75008", "8 rue de l'Exemple", "Paris", "FR"),
        ),
        "deliver_to": (
            "Commune d'Exemple, entrepôt",
            gln("200000000003"),
            ("69002", "2 rue de l'Exemple", "Lyon", "FR"),
        ),
        "endpoints": ((SELLER_SIREN, "0225"), (BUYER_SIREN, "0225")),
        "reduced_rate": "5.5",
        "timesheet": ("DOCUMENT_ANNEXE", "feuille-de-temps.csv"),  # BT-123: a code from the French list (BR-FR-17)
        "legal_id": SELLER_SIREN,
        "country_name": "France",
        "unit": "U",
        "scheme_names": {"global": "SIRET", "legal": "SIREN", "endpoint": "SIREN"},
        "thanks": "Merci pour votre commande.",
    },
}
# A French company buying from the seller (the categories where the town hall of the baseline would not be realistic):
# an exporter, a general contractor. Their SIRENs are fictitious, their last digit a Luhn key; the API Recherche
# d'entreprises (recherche-entreprises.api.gouv.fr) finds no company under either (checked 2026-11-24).
EXPORTER_SIREN = luhn_complete("05678901")
CONTRACTOR_SIREN = luhn_complete("06789012")


def _company(name, siren, address):
    siret = luhn_complete(siren + "0001")
    return {
        "name": name,
        "global_id": (siret, "0009"),
        "legal_id": (siren, "0002"),
        "address": address,
        "endpoint": (siren, "0225"),
        "department": None,
        "vat": vat_fr(siren),
    }


# What the VAT category variants put on the invoice, per category (targets/en16931.py, vat_categories). No Z and no O:
# France has no domestic zero rate, and a French company registered for VAT gives its VAT number on every invoice
# (CGI annex II, art. 242 nonies A), which category O forbids (BR-O-02); those examples are on the European invoice.
FRENCH["words"]["categories"] = {
    "S": {"wrong_reason": "Taux normal"},
    # transport of goods being exported, invoiced to the exporter: CGI art. 262 I 1° (Directive art. 146 (1) (e))
    "E": {
        "items": ("Transport routier Lyon - Genève, marchandises exportées", "Chargement des palettes exportées"),
        "reason": ("Exonération de TVA, article 262 I 1° du CGI", "VATEX-EU-146-1E"),
        "standard_line": ("Stockage en entrepôt à Lyon", "1", "300.00", "S", "20"),
        "buyer": _company("Exportateur Exemple SAS", EXPORTER_SIREN, ("69007", "3 quai de l'Exemple", "Lyon", "FR")),
        "buyer_reference": None,
    },
    # construction work subcontracted to a general contractor: CGI art. 283-2 nonies, the mention « Autoliquidation »
    "AE": {
        "items": ("Travaux d'électricité en sous-traitance", "Chemin de câbles posé"),
        "reason": ("Autoliquidation", "VATEX-EU-AE"),
        "buyer": _company(
            "Entreprise Générale Exemple SAS", CONTRACTOR_SIREN, ("75015", "8 rue de l'Exemple", "Paris", "FR")
        ),
        "buyer_reference": None,
    },
    # goods shipped to a company in Belgium: CGI art. 262 ter I; BE0999999922: VIES answers that no company holds it
    # (checked 2026-11-24)
    "K": {
        "items": ("Pompe industrielle", "Kit de joints de pompe"),
        "reason": ("Exonération de TVA, article 262 ter I du CGI", "VATEX-EU-IC"),
        "buyer": {
            "name": "Client Exemple SRL",
            "address": ("1000", "Rue de l'Exemple 1", "Bruxelles", "BE"),
            "endpoint": ("achats@client-exemple.example", "EM"),  # BT-49, which BR-FR-12 requires
            "vat": "BE0999999922",
        },
        "ship_to": ("Client Exemple SRL", ("1000", "Rue de l'Exemple 1", "Bruxelles", "BE")),
        "buyer_reference": None,
    },
    # goods exported to a company in Switzerland: CGI art. 262 I 1°
    "G": {
        "items": ("Machine d'emballage", "Kit de pièces de rechange"),
        "reason": ("Exonération de TVA, article 262 I 1° du CGI", "VATEX-EU-G"),
        "buyer": {
            "name": "Client Exemple SA",
            "address": ("1201", "Rue de l'Exemple 1", "Genève", "CH"),
            "endpoint": ("achats@client-exemple.example", "EM"),
        },
        "buyer_reference": None,
    },
}


def amt(value):
    return f"{Decimal(value).quantize(CENT, ROUND_HALF_UP)}"


def el(parent, tag, text=None, **attrs):
    prefix, name = tag.split(":")
    node = etree.SubElement(parent, f"{{{NS[prefix]}}}{name}", {k.replace("_", ""): v for k, v in attrs.items()})
    if text is not None:
        node.text = str(text)
    return node


def date(parent, tag, value, fmt="102", ns="udt"):
    el(el(parent, tag), f"{ns}:DateTimeString", value, format=fmt)


def _scheme(scheme):
    """The schemeID attribute, or none when the scheme is None (an identifier written without its scheme)."""
    return {"schemeID": scheme} if scheme is not None else {}


def party(parent, tag, p):
    node = el(parent, tag)
    if p.get("global_id"):
        el(node, "ram:GlobalID", p["global_id"][0], **_scheme(p["global_id"][1]))
    el(node, "ram:Name", p["name"])
    if p.get("legal_id"):
        el(el(node, "ram:SpecifiedLegalOrganization"), "ram:ID", p["legal_id"][0], **_scheme(p["legal_id"][1]))
    if p.get("department"):
        el(el(node, "ram:DefinedTradeContact"), "ram:DepartmentName", p["department"])
    if p.get("address"):
        addr = el(node, "ram:PostalTradeAddress")
        postcode, line, city, country = p["address"]
        el(addr, "ram:PostcodeCode", postcode)
        el(addr, "ram:LineOne", line)
        el(addr, "ram:CityName", city)
        el(addr, "ram:CountryID", country)
    if p.get("endpoint"):
        el(el(node, "ram:URIUniversalCommunication"), "ram:URIID", p["endpoint"][0], **_scheme(p["endpoint"][1]))
    if p.get("vat"):
        el(el(node, "ram:SpecifiedTaxRegistration"), "ram:ID", p["vat"], schemeID="VA")
    if p.get("tax_number"):  # BT-32, the seller's tax registration identifier (a German Steuernummer)
        el(el(node, "ram:SpecifiedTaxRegistration"), "ram:ID", p["tax_number"], schemeID="FC")
    return node


def build(c):
    """Return the invoice as an lxml element tree root."""
    root = etree.Element(f"{{{NS['rsm']}}}CrossIndustryInvoice", nsmap=NS)
    ctx = el(root, "rsm:ExchangedDocumentContext")
    if c["billing_frame"] is not None:
        el(el(ctx, "ram:BusinessProcessSpecifiedDocumentContextParameter"), "ram:ID", c["billing_frame"])
    el(el(ctx, "ram:GuidelineSpecifiedDocumentContextParameter"), "ram:ID", c["profile"])

    doc = el(root, "rsm:ExchangedDocument")
    el(doc, "ram:ID", c["number"])
    el(doc, "ram:TypeCode", c["type_code"])
    date(doc, "ram:IssueDateTime", c["issue_date"], c["issue_date_format"])
    for subject, content in c["notes"]:
        note = el(doc, "ram:IncludedNote")
        el(note, "ram:Content", content)
        el(note, "ram:SubjectCode", subject)

    tx = el(root, "rsm:SupplyChainTradeTransaction")
    groups = OrderedDict()  # (category, rate) -> basis
    line_total = Decimal(0)
    for i, (name, qty, price, cat, rate, *discount) in enumerate(c["lines"], 1):
        net = (Decimal(qty) * Decimal(price)).quantize(CENT, ROUND_HALF_UP) - sum(Decimal(d) for d in discount)
        line_total += net
        groups[(cat, rate)] = groups.get((cat, rate), Decimal(0)) + net
        item = el(tx, "ram:IncludedSupplyChainTradeLineItem")
        el(el(item, "ram:AssociatedDocumentLineDocument"), "ram:LineID", i)
        el(el(item, "ram:SpecifiedTradeProduct"), "ram:Name", name)
        el(el(el(item, "ram:SpecifiedLineTradeAgreement"), "ram:NetPriceProductTradePrice"), "ram:ChargeAmount", price)
        el(el(item, "ram:SpecifiedLineTradeDelivery"), "ram:BilledQuantity", qty, unitCode="C62")
        settle = el(item, "ram:SpecifiedLineTradeSettlement")
        tax = el(settle, "ram:ApplicableTradeTax")
        el(tax, "ram:TypeCode", c["tax_type"])
        el(tax, "ram:CategoryCode", cat)
        if rate is not None:  # None: no rate at all, as category O (not subject to VAT) requires
            el(tax, "ram:RateApplicablePercent", rate)
        for d in discount:
            ac = el(settle, "ram:SpecifiedTradeAllowanceCharge")
            el(el(ac, "ram:ChargeIndicator"), "udt:Indicator", "false")
            el(ac, "ram:ActualAmount", amt(d))
            el(ac, "ram:ReasonCode", "95")
            el(ac, "ram:Reason", c["line_allowance_reason"])
        el(el(settle, "ram:SpecifiedTradeSettlementLineMonetarySummation"), "ram:LineTotalAmount", amt(net))

    agree = el(tx, "ram:ApplicableHeaderTradeAgreement")
    if c["buyer_reference"] is not None:
        el(agree, "ram:BuyerReference", c["buyer_reference"])
    party(agree, "ram:SellerTradeParty", c["seller"])
    party(agree, "ram:BuyerTradeParty", c["buyer"])
    if c["order_reference"] is not None:
        el(el(agree, "ram:BuyerOrderReferencedDocument"), "ram:IssuerAssignedID", c["order_reference"])

    delivery = el(tx, "ram:ApplicableHeaderTradeDelivery")
    if c.get("ship_to"):  # BG-13: (name, (postcode, street, city, country))
        ship_to = el(delivery, "ram:ShipToTradeParty")
        el(ship_to, "ram:Name", c["ship_to"][0])
        addr = el(ship_to, "ram:PostalTradeAddress")
        for tag, value in zip(("PostcodeCode", "LineOne", "CityName", "CountryID"), c["ship_to"][1], strict=True):
            el(addr, f"ram:{tag}", value)
    if c["delivery_date"]:
        event = el(delivery, "ram:ActualDeliverySupplyChainEvent")
        date(event, "ram:OccurrenceDateTime", c["delivery_date"])

    settle = el(tx, "ram:ApplicableHeaderTradeSettlement")
    if c["tax_currency"]:
        el(settle, "ram:TaxCurrencyCode", c["tax_currency"][0])
    el(settle, "ram:InvoiceCurrencyCode", c["currency"])
    if c["invoicee"]:
        party(settle, "ram:InvoiceeTradeParty", c["invoicee"])
    means = el(settle, "ram:SpecifiedTradeSettlementPaymentMeans")
    el(means, "ram:TypeCode", c["payment_code"])
    if c["iban"] or c["proprietary_account"]:
        account = el(means, "ram:PayeePartyCreditorFinancialAccount")
        if c["iban"]:
            el(account, "ram:IBANID", c["iban"])
        if c["proprietary_account"]:
            el(account, "ram:ProprietaryID", c["proprietary_account"])
    if c["bic"]:
        el(el(means, "ram:PayeeSpecifiedCreditorFinancialInstitution"), "ram:BICID", c["bic"])

    allowance_total = sum((Decimal(a[0]) for a in c["allowances"]), Decimal(0))
    charge_total = sum((Decimal(a[0]) for a in c["charges"]), Decimal(0))
    for sign, items in ((-1, c["allowances"]), (1, c["charges"])):
        for amount, _code, _reason, cat, rate in items:
            groups[(cat, rate)] = groups.get((cat, rate), Decimal(0)) + sign * Decimal(amount)
    tax_total = Decimal(0)
    # the exemption reason (BT-120) and its code (BT-121) of a category, when the invoice names them; else the
    # invoice's one reason, for the categories that need one
    exemptions = c.get("exemptions", {})
    for (cat, rate), basis in groups.items():
        vat = (basis * Decimal(rate or 0) / 100).quantize(CENT, ROUND_HALF_UP)
        tax_total += vat
        tax = el(settle, "ram:ApplicableTradeTax")
        el(tax, "ram:CalculatedAmount", amt(vat))
        el(tax, "ram:TypeCode", c["tax_type"])
        reason, code = exemptions.get(
            cat, (c["exemption_reason"], None) if cat in ("E", "AE", "K", "G", "O") else (None, None)
        )
        if reason:
            el(tax, "ram:ExemptionReason", reason)
        el(tax, "ram:BasisAmount", amt(basis))
        el(tax, "ram:CategoryCode", cat)
        if code:
            el(tax, "ram:ExemptionReasonCode", code)
        if c["due_date_type"]:
            el(tax, "ram:DueDateTypeCode", c["due_date_type"])
        if rate is not None:
            el(tax, "ram:RateApplicablePercent", rate)
    for indicator, amount, code, reason, cat, rate in [("false", *a) for a in c["allowances"]] + [
        ("true", *a) for a in c["charges"]
    ]:
        ac = el(settle, "ram:SpecifiedTradeAllowanceCharge")
        el(el(ac, "ram:ChargeIndicator"), "udt:Indicator", indicator)
        el(ac, "ram:ActualAmount", amt(amount))
        el(ac, "ram:ReasonCode", code)
        el(ac, "ram:Reason", reason)
        tax = el(ac, "ram:CategoryTradeTax")
        el(tax, "ram:TypeCode", c["tax_type"])
        el(tax, "ram:CategoryCode", cat)
        if rate is not None:
            el(tax, "ram:RateApplicablePercent", rate)
    terms = el(settle, "ram:SpecifiedTradePaymentTerms")
    el(terms, "ram:Description", c["payment_terms"])
    date(terms, "ram:DueDateDateTime", c["due_date"])

    basis_total = line_total + charge_total - allowance_total
    grand = basis_total + tax_total
    sums = el(settle, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    el(sums, "ram:LineTotalAmount", amt(line_total))
    if c["charges"]:
        el(sums, "ram:ChargeTotalAmount", amt(charge_total))
    if c["allowances"]:
        el(sums, "ram:AllowanceTotalAmount", amt(allowance_total))
    el(sums, "ram:TaxBasisTotalAmount", amt(basis_total))
    el(sums, "ram:TaxTotalAmount", amt(tax_total), currencyID=c["currency"])
    if c["tax_currency"]:
        code, factor = c["tax_currency"]
        el(sums, "ram:TaxTotalAmount", amt(tax_total * Decimal(factor)), currencyID=code)
    el(sums, "ram:GrandTotalAmount", amt(grand))
    el(sums, "ram:DuePayableAmount", amt(grand))
    return root


def to_bytes(root):
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
