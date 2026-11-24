"""What every target builds its variants with: the Variant record, and the edits that break one rule in a CII invoice.

An edit is a function(root) that changes the XML tree after the invoice is built from its base; the helpers here
return such functions, or are one.
"""

import copy
from dataclasses import dataclass, field
from decimal import Decimal

from lxml import etree

from . import cii
from .cii import NS, el


@dataclass(frozen=True)
class Variant:
    id: str  # file stem, e.g. "BR-FR-10"
    rule: str  # the rule this variant is about
    fires: tuple  # every rule id the official rules report on it
    en: str  # what is wrong, in English
    fr: str  # the same, in French
    changes: dict = field(default_factory=dict)  # baseline keys to replace
    edit: object = None  # optional function(root) applied to the XML tree
    # the edit that gives the same invoice without the mistake, when that is not simply the variant without its
    # edit (the variant's edit both sets a context and breaks the rule)
    fixed: object = None
    # the baseline keys that give the same invoice without the mistake, when the mistake is in the changes (a line in
    # the wrong VAT category, whose totals the invoice computes from it): they replace the variant's own
    fixed_changes: dict = None


def ram(tag):
    return f"{{{NS['ram']}}}{tag}"


def agreement(root):
    return root.find(f".//{ram('ApplicableHeaderTradeAgreement')}")


def add_documents(*docs):
    """Add AdditionalReferencedDocument elements (BG-24, BT-18): (issuer id, type code, name or None, reference type or None)."""

    def edit(root):
        parent = agreement(root)
        for issuer_id, type_code, name, reference_type in docs:
            d = el(parent, "ram:AdditionalReferencedDocument")
            el(d, "ram:IssuerAssignedID", issuer_id)
            el(d, "ram:TypeCode", type_code)
            if name:
                el(d, "ram:Name", name)
            if reference_type:
                el(d, "ram:ReferenceTypeCode", reference_type)

    return edit


def add_characteristic(description, value, measure=None):
    """Add an item attribute (BG-32) to the first line; measure, a (quantity, unit code) pair, adds its value as a
    measure (ram:ValueMeasure, in the EXTENDED profiles only)."""

    def edit(root):
        product = root.find(f".//{ram('SpecifiedTradeProduct')}")
        ch = el(product, "ram:ApplicableProductCharacteristic")
        if description is not None:
            el(ch, "ram:Description", description)
        if measure is not None:
            el(ch, "ram:ValueMeasure", measure[0], unitCode=measure[1])
        if value is not None:
            el(ch, "ram:Value", value)

    return edit


def add_note(subject, content):
    """Add a note (BG-1) to the document, after the others."""

    def edit(root):
        note = new("ram:IncludedNote")
        sub(note, "ram:Content", content)
        sub(note, "ram:SubjectCode", subject)
        document = root.find(f"{{{NS['rsm']}}}ExchangedDocument")
        insert(document, note, before="EffectiveSpecifiedPeriod", after="IncludedNote")

    return edit


def add_tax_representative(name, vat, address):
    """Add a seller tax representative (BG-11): its name, postal address (postcode, street, city, country) and VAT
    identifier (BT-63), after the buyer."""

    def edit(root):
        node = new("ram:SellerTaxRepresentativeTradeParty")
        sub(node, "ram:Name", name)
        postal = sub(node, "ram:PostalTradeAddress")
        for tag, value in zip(("PostcodeCode", "LineOne", "CityName", "CountryID"), address, strict=True):
            sub(postal, f"ram:{tag}", value)
        sub(sub(node, "ram:SpecifiedTaxRegistration"), "ram:ID", vat, schemeID="VA")
        insert(first(root, "ApplicableHeaderTradeAgreement"), node, after="BuyerTradeParty")

    return edit


def add_invoice_reference(issuer_id, date="20260915"):
    """Reference a preceding invoice (BG-3: BT-25, BT-26), at the end of the header settlement."""

    def edit(root):
        settlement = root.find(f".//{ram('ApplicableHeaderTradeSettlement')}")
        ref = el(settlement, "ram:InvoiceReferencedDocument")
        el(ref, "ram:IssuerAssignedID", issuer_id)
        el(el(ref, "ram:FormattedIssueDateTime"), "qdt:DateTimeString", date, format="102")

    return edit


def drop_scheme(party_tag):
    """Remove the schemeID of a party's GlobalID."""

    def edit(root):
        for gid in root.iter(ram("GlobalID")):
            if gid.getparent().tag == ram(party_tag):
                gid.attrib.pop("schemeID", None)

    return edit


def one_more_decimal(*path, digit="0"):
    """Write the first element at the end of a ram: path with one more decimal (2 decimals become 3). The default
    digit, a trailing 0, keeps the value and changes only its notation; another digit changes the value."""

    def edit(root):
        first(root, *path).text += digit

    return edit


def accounting_vat_total(factor):
    """Write the VAT total in the VAT accounting currency (BT-111) as the VAT total (BT-110) times factor, kept with
    3 decimals instead of rounded to the cent."""

    def edit(root):
        invoice, accounting = first(root, "SpecifiedTradeSettlementHeaderMonetarySummation").findall(
            ram("TaxTotalAmount")
        )
        accounting.text = f"{(Decimal(invoice.text) * Decimal(factor)).quantize(Decimal('0.001'))}"

    return edit


def set_amount(tag, delta):
    """Add delta to a header monetary total (e.g. GrandTotalAmount)."""

    def edit(root):
        for node in root.iter(ram(tag)):
            if node.getparent().tag == ram("SpecifiedTradeSettlementHeaderMonetarySummation"):
                node.text = f"{float(node.text) + delta:.2f}"

    return edit


def edit_all(*edits):
    def edit(root):
        for e in edits:
            e(root)

    return edit


def new(tag, text=None, **attrs):
    prefix, name = tag.split(":")
    node = etree.Element(f"{{{NS[prefix]}}}{name}", attrs)
    if text is not None:
        node.text = text
    return node


def sub(parent, tag, text=None, **attrs):
    node = new(tag, text, **attrs)
    parent.append(node)
    return node


def first(root, *path):
    """The first element at the end of a chain of ram: tags."""
    return root.find(".//" + "/".join(ram(t) for t in path))


def insert(parent, node, before=None, after=None):
    """Insert node before the first child named `before`, or after the last child named `after`, else at the end."""
    if before is not None and parent.find(ram(before)) is not None:
        parent.find(ram(before)).addprevious(node)
    elif after is not None and parent.findall(ram(after)):
        parent.findall(ram(after))[-1].addnext(node)
    else:
        parent.append(node)


def party(tag, name, global_ids, legal_id=None):
    node = new(f"ram:{tag}")
    for value, scheme in global_ids:
        sub(node, "ram:GlobalID", value, **({"schemeID": scheme} if scheme else {}))
    sub(node, "ram:Name", name)
    if legal_id:
        sub(sub(node, "ram:SpecifiedLegalOrganization"), "ram:ID", legal_id, schemeID="0002")
    return node


def add_payee(global_ids, legal_id=None, name="Affacturage Exemple"):
    """Add a payee (BG-10), by default a factoring company, before the payment means."""

    def edit(root):
        insert(
            first(root, "ApplicableHeaderTradeSettlement"),
            party("PayeeTradeParty", name, global_ids, legal_id),
            before="SpecifiedTradeSettlementPaymentMeans",
        )

    return edit


def add_ship_to(global_ids, name="Médiathèque d'Exemple", address=None):
    """Add a deliver-to party (BG-13) with location identifiers (BT-71), and its address (BG-15: postcode, street,
    city, country) when given."""

    def edit(root):
        node = party("ShipToTradeParty", name, global_ids)
        if address is not None:
            postal = sub(node, "ram:PostalTradeAddress")
            for tag, value in zip(("PostcodeCode", "LineOne", "CityName", "CountryID"), address, strict=True):
                sub(postal, f"ram:{tag}", value)
        first(root, "ApplicableHeaderTradeDelivery").insert(0, node)

    return edit


def add_global_id(party_tag, value, scheme):
    """Add a second GlobalID to a party, after the first one."""

    def edit(root):
        insert(first(root, party_tag), new("ram:GlobalID", value, schemeID=scheme), after="GlobalID")

    return edit


def billing_period(start, end, where="ApplicableHeaderTradeSettlement"):
    """Add the invoicing period (BG-14: BT-73, BT-74) after the VAT breakdown, or with where
    "SpecifiedLineTradeSettlement", the first line's period (BG-26: BT-134, BT-135) after its VAT."""

    def edit(root):
        period = new("ram:BillingSpecifiedPeriod")
        sub(sub(period, "ram:StartDateTime"), "udt:DateTimeString", start, format="102")
        sub(sub(period, "ram:EndDateTime"), "udt:DateTimeString", end, format="102")
        insert(first(root, where), period, after="ApplicableTradeTax")

    return edit


def tax_point_date(value):
    """Give each VAT breakdown a VAT point date (BT-7); use with due_date_type None (BT-7 and BT-8 exclude each other)."""

    def edit(root):
        for tax in first(root, "ApplicableHeaderTradeSettlement").iterfind(ram("ApplicableTradeTax")):
            point = new("ram:TaxPointDate")
            sub(point, "udt:DateString", value, format="102")
            insert(tax, point, before="RateApplicablePercent")

    return edit


def set_text(*path, text):
    """Rewrite the text of the first element at the end of a ram: path."""

    def edit(root):
        first(root, *path).text = text

    return edit


def add_element(path, tag, text, before=None, after=None, **attrs):
    """Add a ram: element inside the first element at the end of path."""

    def edit(root):
        insert(first(root, *path), new(f"ram:{tag}", text, **attrs), before=before, after=after)

    return edit


def prepaid(amount, due):
    """Add a paid amount (BT-113) and set the amount due (BT-115)."""

    def edit(root):
        sums = first(root, "SpecifiedTradeSettlementHeaderMonetarySummation")
        insert(sums, new("ram:TotalPrepaidAmount", amount), before="DuePayableAmount")
        sums.find(ram("DuePayableAmount")).text = due

    return edit


def paid_amount(text):
    """Add a paid amount (BT-113) written as text, and set the amount due (BT-115) to the total with VAT minus it."""

    def edit(root):
        grand = first(root, "SpecifiedTradeSettlementHeaderMonetarySummation", "GrandTotalAmount").text
        prepaid(text, f"{float(grand) - float(text):.2f}")(root)

    return edit


def paid_without_due_date(root):
    """Already paid: paid amount = total with VAT, nothing due, and no payment due date (BT-9)."""
    sums = first(root, "SpecifiedTradeSettlementHeaderMonetarySummation")
    prepaid(sums.find(ram("GrandTotalAmount")).text, "0.00")(root)
    terms = first(root, "SpecifiedTradePaymentTerms")
    terms.remove(terms.find(ram("DueDateDateTime")))


def paid_with_due_date(root):
    """Already paid, as in paid_without_due_date, but the payment due date (BT-9) stays."""
    sums = first(root, "SpecifiedTradeSettlementHeaderMonetarySummation")
    prepaid(sums.find(ram("GrandTotalAmount")).text, "0.00")(root)


def gross_price(gross, discount):
    """Give the first line a gross price (BT-148) and a price discount (BT-147); the net price stays."""

    def edit(root):
        price = new("ram:GrossPriceProductTradePrice")
        sub(price, "ram:ChargeAmount", gross)
        ac = sub(price, "ram:AppliedTradeAllowanceCharge")
        sub(sub(ac, "ram:ChargeIndicator"), "udt:Indicator", "false")
        sub(ac, "ram:ActualAmount", discount)
        insert(first(root, "SpecifiedLineTradeAgreement"), price, before="NetPriceProductTradePrice")

    return edit


def shift(delta, *tags):
    """Add delta to several header monetary totals, so that only the rule under test sees a difference."""
    return edit_all(*(set_amount(tag, delta) for tag in tags))


def tax_point_with_code(value):
    """Give each VAT breakdown a VAT point date (BT-7) next to its VAT point date code (BT-8), which BR-CO-03 forbids."""

    def edit(root):
        for tax in first(root, "ApplicableHeaderTradeSettlement").iterfind(ram("ApplicableTradeTax")):
            point = new("ram:TaxPointDate")
            sub(point, "udt:DateString", value, format="102")
            insert(tax, point, before="DueDateTypeCode")

    return edit


def empty_period(where):
    """Add an invoicing period with no dates: at document level (BG-14) or on the first line (BG-26)."""

    def edit(root):
        insert(first(root, where), new("ram:BillingSpecifiedPeriod"), after="ApplicableTradeTax")

    return edit


def vat_amount(delta):
    """Add delta to the first VAT breakdown's tax amount (BT-117), and to the totals that follow from it."""

    def edit(root):
        node = first(root, "ApplicableHeaderTradeSettlement", "ApplicableTradeTax", "CalculatedAmount")
        node.text = f"{float(node.text) + delta:.2f}"
        shift(delta, "TaxTotalAmount", "GrandTotalAmount", "DuePayableAmount")(root)

    return edit


def no_reasons(where):
    """Remove the reason (BT-97, BT-104, BT-139, BT-144) and the reason code of every allowance or charge in where:
    the document level (ApplicableHeaderTradeSettlement) or the first line (SpecifiedLineTradeSettlement)."""

    def edit(root):
        for ac in first(root, where).iterfind(ram("SpecifiedTradeAllowanceCharge")):
            for tag in ("ReasonCode", "Reason"):
                for node in ac.findall(ram(tag)):
                    ac.remove(node)

    return edit


def line_charge(amount, reason):
    """Add a charge (BG-28) to the first line, with its reason (a text) or without (None), and carry it into the line
    net amount, the VAT breakdown at the line's rate and every total."""

    def edit(root):
        settle = first(root, "SpecifiedLineTradeSettlement")
        rate = float(settle.find(f"{ram('ApplicableTradeTax')}/{ram('RateApplicablePercent')}").text) / 100
        ac = new("ram:SpecifiedTradeAllowanceCharge")
        sub(sub(ac, "ram:ChargeIndicator"), "udt:Indicator", "true")
        sub(ac, "ram:ActualAmount", f"{amount:.2f}")
        if reason:
            sub(ac, "ram:ReasonCode", "ABL")
            sub(ac, "ram:Reason", reason)
        insert(settle, ac, before="SpecifiedTradeSettlementLineMonetarySummation")
        net = settle.find(f"{ram('SpecifiedTradeSettlementLineMonetarySummation')}/{ram('LineTotalAmount')}")
        net.text = f"{float(net.text) + amount:.2f}"
        tax = first(root, "ApplicableHeaderTradeSettlement", "ApplicableTradeTax")
        for tag, delta in (("BasisAmount", amount), ("CalculatedAmount", amount * rate)):
            node = tax.find(ram(tag))
            node.text = f"{float(node.text) + delta:.2f}"
        shift(amount, "LineTotalAmount", "TaxBasisTotalAmount")(root)
        shift(amount * rate, "TaxTotalAmount")(root)
        shift(amount * (1 + rate), "GrandTotalAmount", "DuePayableAmount")(root)

    return edit


def no_payment_terms(root):
    """Remove the payment terms block: the payment due date (BT-9) and the payment terms text (BT-20)."""
    settle = first(root, "ApplicableHeaderTradeSettlement")
    settle.remove(settle.find(ram("SpecifiedTradePaymentTerms")))


def line_tax_type(code):
    """Declare the first line's tax with another type code than VAT."""

    def edit(root):
        first(root, "SpecifiedLineTradeSettlement", "ApplicableTradeTax", "TypeCode").text = code

    return edit


def no_seller_identifiers(root):
    """Remove every identifier of the seller: its identifier (BT-29), legal registration identifier (BT-30) and VAT
    number (BT-31)."""
    seller = first(root, "SellerTradeParty")
    for tag in ("GlobalID", "SpecifiedLegalOrganization", "SpecifiedTaxRegistration"):
        for node in seller.findall(ram(tag)):
            seller.remove(node)


def no_unit_code(root):
    """Remove the unit of measure code (BT-130) of the first line's invoiced quantity."""
    del first(root, "SpecifiedLineTradeDelivery", "BilledQuantity").attrib["unitCode"]


def allowance_as_negative_line(root):
    """Write the document level allowance as a last line of quantity 1 at a negative net price (BT-146): the same
    amounts and totals, the discount typed as a line."""
    settle = first(root, "ApplicableHeaderTradeSettlement")
    allowance = settle.find(ram("SpecifiedTradeAllowanceCharge"))
    amount, reason = allowance.find(ram("ActualAmount")).text, allowance.find(ram("Reason")).text
    settle.remove(allowance)
    lines = root.findall(f".//{ram('IncludedSupplyChainTradeLineItem')}")
    line = copy.deepcopy(lines[-1])
    for path, text in (
        (("LineID",), str(len(lines) + 1)),
        (("SpecifiedTradeProduct", "Name"), reason),
        (("NetPriceProductTradePrice", "ChargeAmount"), f"-{amount}"),
        (("BilledQuantity",), "1"),
        (("SpecifiedTradeSettlementLineMonetarySummation", "LineTotalAmount"), f"-{amount}"),
    ):
        first(line, *path).text = text
    lines[-1].addnext(line)
    sums = first(root, "SpecifiedTradeSettlementHeaderMonetarySummation")
    sums.remove(sums.find(ram("AllowanceTotalAmount")))
    set_amount("LineTotalAmount", -float(amount))(root)


def vat_basis(delta):
    """Add delta to the first VAT breakdown's taxable amount (BT-116) only."""

    def edit(root):
        node = first(root, "ApplicableHeaderTradeSettlement", "ApplicableTradeTax", "BasisAmount")
        node.text = f"{float(node.text) + delta:.2f}"

    return edit


def no_exemption_reason(root):
    """Remove the exemption reason (BT-120) of every VAT breakdown."""
    for tax in first(root, "ApplicableHeaderTradeSettlement").iterfind(ram("ApplicableTradeTax")):
        for node in tax.findall(ram("ExemptionReason")):
            tax.remove(node)


# Edits at an XPath, its prefixes those of cii.NS (rsm:, ram:, udt:, qdt:).


def set_value(path, text):
    """Rewrite the text of the first element at an XPath."""

    def edit(root):
        root.xpath(path, namespaces=NS)[0].text = text

    return edit


def set_attribute(path, name, value):
    """Set an attribute of every element at an XPath; None removes it."""

    def edit(root):
        for node in root.xpath(path, namespaces=NS):
            if value is None:
                node.attrib.pop(name, None)
            else:
                node.set(name, value)

    return edit


def remove(path):
    """Remove the first element at an XPath."""

    def edit(root):
        node = root.xpath(path, namespaces=NS)[0]
        node.getparent().remove(node)

    return edit


def add_tax_currency(code):
    """Name a VAT accounting currency (BT-6) without its VAT total (BT-111)."""

    def edit(root):
        insert(
            first(root, "ApplicableHeaderTradeSettlement"),
            new("ram:TaxCurrencyCode", code),
            before="InvoiceCurrencyCode",
        )

    return edit


def add_product_id(value, scheme):
    """Give the first line's item a standard identifier (BT-157), with its scheme (BT-157-1) or none."""

    def edit(root):
        node = new("ram:GlobalID", value, **({"schemeID": scheme} if scheme is not None else {}))
        first(root, "SpecifiedTradeProduct").insert(0, node)

    return edit


def add_classification(code, list_id):
    """Give the first line's item a classification identifier (BT-158), with its scheme (BT-158-1) or none."""

    def edit(root):
        classification = new("ram:DesignatedProductClassification")
        sub(classification, "ram:ClassCode", code, **({"listID": list_id} if list_id is not None else {}))
        insert(first(root, "SpecifiedTradeProduct"), classification, before="OriginTradeCountry")

    return edit


def add_origin(country):
    """Give the first line's item a country of origin (BT-159)."""

    def edit(root):
        sub(sub(first(root, "SpecifiedTradeProduct"), "ram:OriginTradeCountry"), "ram:ID", country)

    return edit


def add_card(number):
    """Give the payment means a payment card (BG-18) whose primary account number is number (BT-87)."""

    def edit(root):
        card = new("ram:ApplicableTradeSettlementFinancialCard")
        sub(card, "ram:ID", number)
        insert(first(root, "SpecifiedTradeSettlementPaymentMeans"), card, after="TypeCode")

    return edit


def account_name_only(name):
    """Replace the payment account's identifier (BT-84) by its name (BT-85): an account with no IBAN."""

    def edit(root):
        account = first(root, "PayeePartyCreditorFinancialAccount")
        for node in list(account):
            account.remove(node)
        sub(account, "ram:AccountName", name)

    return edit


def add_attachment(issuer_id, name, filename, mime, content):
    """Add a supporting document (BG-24) with an attached file (BT-125): its MIME code and file name."""

    def edit(root):
        document = sub(agreement(root), "ram:AdditionalReferencedDocument")
        sub(document, "ram:IssuerAssignedID", issuer_id)
        sub(document, "ram:TypeCode", "916")
        sub(document, "ram:Name", name)
        sub(document, "ram:AttachmentBinaryObject", content, mimeCode=mime, filename=filename)

    return edit


def build(base, variant=None):
    """The base invoice, or a variant of it (its changes to the base, then its edit of the XML), as an lxml root."""
    conf = copy.deepcopy(base)
    if variant:
        conf.update(copy.deepcopy(variant.changes))
    root = cii.build(conf)
    if variant and variant.edit:
        variant.edit(root)
    return root


# Edits on a VAT category's breakdown (BG-23) and rates, for the VAT category rules (BR-S, BR-Z, BR-E, BR-AE, BR-IC,
# BR-G, BR-O).


def _breakdowns(root, category):
    settlement = first(root, "ApplicableHeaderTradeSettlement")
    return [t for t in settlement.iterfind(ram("ApplicableTradeTax")) if t.findtext(ram("CategoryCode")) == category]


def _line_nets(root, category):
    return [
        item.findtext(f".//{ram('LineTotalAmount')}")
        for item in root.iter(ram("IncludedSupplyChainTradeLineItem"))
        if item.findtext(f".//{ram('ApplicableTradeTax')}/{ram('CategoryCode')}") == category
    ]


def breakdown_per_line(category):
    """Replace a category's VAT breakdown with one per line of that category, each with its line's net amount as
    taxable amount (BT-116): one breakdown per line instead of one per category and rate."""

    def edit(root):
        tax = _breakdowns(root, category)[0]
        for net in reversed(_line_nets(root, category)):
            copy_ = copy.deepcopy(tax)
            copy_.find(ram("BasisAmount")).text = net
            tax.addnext(copy_)
        tax.getparent().remove(tax)

    return edit


def drop_breakdown(category):
    """Remove a category's VAT breakdown, and nothing else: the totals stay as computed with it."""

    def edit(root):
        tax = _breakdowns(root, category)[0]
        tax.getparent().remove(tax)

    return edit


def breakdown_basis(category, delta):
    """Add delta to a category's taxable amount (BT-116) only."""

    def edit(root):
        node = _breakdowns(root, category)[0].find(ram("BasisAmount"))
        node.text = f"{Decimal(node.text) + Decimal(delta):.2f}"

    return edit


def breakdown_vat(category, rate):
    """Give a category's VAT breakdown a VAT amount (BT-117) of rate % of its taxable amount, its rate (BT-119)
    unchanged; the VAT total and the totals after it follow."""

    def edit(root):
        tax = _breakdowns(root, category)[0]
        vat = (Decimal(tax.findtext(ram("BasisAmount"))) * Decimal(rate) / 100).quantize(Decimal("0.01"))
        delta = vat - Decimal(tax.findtext(ram("CalculatedAmount")))
        tax.find(ram("CalculatedAmount")).text = f"{vat:.2f}"
        shift(float(delta), "TaxTotalAmount", "GrandTotalAmount", "DuePayableAmount")(root)

    return edit


def no_exemption(category):
    """Remove the exemption reason (BT-120) and its code (BT-121) of a category's VAT breakdown."""

    def edit(root):
        for tax in _breakdowns(root, category):
            for tag in ("ExemptionReason", "ExemptionReasonCode"):
                for node in tax.findall(ram(tag)):
                    tax.remove(node)

    return edit


def add_exemption_reason(category, text):
    """Give a category's VAT breakdown an exemption reason (BT-120)."""

    def edit(root):
        insert(_breakdowns(root, category)[0], new("ram:ExemptionReason", text), before="BasisAmount")

    return edit


def add_breakdown(category, rate):
    """Add an empty VAT breakdown (taxable amount and VAT 0.00) of a category and rate, after the others."""

    def edit(root):
        tax = new("ram:ApplicableTradeTax")
        sub(tax, "ram:CalculatedAmount", "0.00")
        sub(tax, "ram:TypeCode", "VAT")
        sub(tax, "ram:BasisAmount", "0.00")
        sub(tax, "ram:CategoryCode", category)
        sub(tax, "ram:RateApplicablePercent", rate)
        settlement = first(root, "ApplicableHeaderTradeSettlement")
        settlement.findall(ram("ApplicableTradeTax"))[-1].addnext(tax)

    return edit


def set_rate(where, rate):
    """Write a VAT rate on the first line (where="line", BT-152), the document level allowance ("allowance", BT-96)
    or charge ("charge", BT-103), whatever its category: a rate where the category wants another, or none."""

    def edit(root):
        if where == "line":
            tax = first(root, "SpecifiedLineTradeSettlement", "ApplicableTradeTax")
        else:
            indicator = "true" if where == "charge" else "false"
            tax = next(
                ac.find(ram("CategoryTradeTax"))
                for ac in first(root, "ApplicableHeaderTradeSettlement").iterfind(ram("SpecifiedTradeAllowanceCharge"))
                if ac.findtext(f"{ram('ChargeIndicator')}/{{{NS['udt']}}}Indicator") == indicator
            )
        node = tax.find(ram("RateApplicablePercent"))
        if node is None:
            node = sub(tax, "ram:RateApplicablePercent")
        node.text = rate

    return edit
