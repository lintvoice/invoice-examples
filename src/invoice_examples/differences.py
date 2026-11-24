"""What differs between an invalid example's XML and the invoice it is compared with, element by element.

The PDF page draws the main values of an invoice: parties, lines, totals, VAT breakdown, notes. Some mistakes sit in
data it does not draw (a supporting document, a period, the payee, a price's base quantity…): in the electronic data
only. For those, the page says so and lists the elements that differ, each with its EN 16931 business term, its place
in the XML and its value in both files, so the mistake still shows.

TERMS names those elements: the end of their path in the CII syntax, their business term, their label in each language
and how their value reads. A difference in an element TERMS does not name stops the page, so that a new example cannot
silently show nothing.
"""

import re
from collections import Counter
from dataclasses import dataclass

from lxml import etree

# (business term, English label, French label, kind of value). The kind tells how the page writes the value: "date",
# "amount", "percent", "quantity" (with its unit code), "id" (with its scheme: a schemeID, or a classification's
# listID), "file" (an attached file: its name and MIME code), "period" (a container, empty or not), "text"; "syntax" marks an element that only says which business term its siblings are, and is never listed.
# A supporting document, a tender and an invoiced object are the same CII element, told apart by their type code
# (916, 50, 130); an allowance and a charge, by their indicator.
TERMS = {
    "ExchangedDocument/TypeCode": ("BT-3", "Invoice type code", "Type de document", "text"),
    "ApplicableHeaderTradeSettlement/InvoiceCurrencyCode": ("BT-5", "Invoice currency", "Devise de la facture", "text"),
    "ApplicableHeaderTradeSettlement/ApplicableTradeTax/TaxPointDate/DateString": (
        "BT-7",
        "VAT point date",
        "Date d'exigibilité de la TVA",
        "date",
    ),
    "AdditionalReferencedDocument:130/IssuerAssignedID": (
        "BT-18",
        "Invoiced object identifier",
        "Identifiant de l'objet facturé",
        "text",
    ),
    "AdditionalReferencedDocument:130/ReferenceTypeCode": (
        "BT-18-1",
        "Invoiced object identifier's scheme",
        "Schéma de l'identifiant de l'objet facturé",
        "text",
    ),
    "AdditionalReferencedDocument/TypeCode": (None, "", "", "syntax"),
    "InvoiceReferencedDocument/IssuerAssignedID": (
        "BT-25",
        "Preceding invoice reference",
        "Référence de la facture antérieure",
        "text",
    ),
    "InvoiceReferencedDocument/FormattedIssueDateTime/DateTimeString": (
        "BT-26",
        "Preceding invoice issue date",
        "Date de la facture antérieure",
        "date",
    ),
    "SellerTradeParty/GlobalID": ("BT-29", "Seller identifier", "Identifiant du vendeur", "id"),
    "BuyerTradeParty/GlobalID": ("BT-46", "Buyer identifier", "Identifiant de l'acheteur", "id"),
    "PayeeTradeParty/Name": ("BT-59", "Payee name", "Nom du bénéficiaire", "text"),
    "SellerTaxRepresentativeTradeParty/Name": (
        "BT-62",
        "Seller tax representative name",
        "Nom du représentant fiscal du vendeur",
        "text",
    ),
    "SellerTaxRepresentativeTradeParty/PostalTradeAddress/LineOne": (
        "BT-64",
        "Tax representative address line",
        "Adresse du représentant fiscal",
        "text",
    ),
    "SellerTaxRepresentativeTradeParty/PostalTradeAddress/CityName": (
        "BT-66",
        "Tax representative city",
        "Ville du représentant fiscal",
        "text",
    ),
    "SellerTaxRepresentativeTradeParty/PostalTradeAddress/PostcodeCode": (
        "BT-67",
        "Tax representative post code",
        "Code postal du représentant fiscal",
        "text",
    ),
    "SellerTaxRepresentativeTradeParty/PostalTradeAddress/CountryID": (
        "BT-69",
        "Tax representative country code",
        "Code pays du représentant fiscal",
        "text",
    ),
    "SellerTaxRepresentativeTradeParty/SpecifiedTaxRegistration/ID": (
        "BT-63",
        "Seller tax representative VAT identifier",
        "Numéro de TVA du représentant fiscal du vendeur",
        "id",
    ),
    # an EXTENDED-CTC-FR term: an item attribute's value as a measure, with its unit
    "ApplicableProductCharacteristic/ValueMeasure": (
        "EXT-FR-FE-160",
        "Item attribute value as a measure",
        "Valeur de l'attribut d'article en mesure",
        "quantity",
    ),
    "PayeeTradeParty/GlobalID": ("BT-60", "Payee identifier", "Identifiant du bénéficiaire", "id"),
    "PayeeTradeParty/SpecifiedLegalOrganization/ID": (
        "BT-61",
        "Payee legal registration identifier",
        "Identifiant légal du bénéficiaire",
        "id",
    ),
    "ShipToTradeParty/Name": ("BT-70", "Deliver to party name", "Nom du destinataire de la livraison", "text"),
    "ShipToTradeParty/GlobalID": ("BT-71", "Deliver to location identifier", "Identifiant du lieu de livraison", "id"),
    "ActualDeliverySupplyChainEvent/OccurrenceDateTime/DateTimeString": (
        "BT-72",
        "Actual delivery date",
        "Date de livraison",
        "date",
    ),
    "ApplicableHeaderTradeSettlement/BillingSpecifiedPeriod": (
        "BG-14",
        "Invoicing period",
        "Période de facturation",
        "period",
    ),
    "ApplicableHeaderTradeSettlement/BillingSpecifiedPeriod/StartDateTime/DateTimeString": (
        "BT-73",
        "Invoicing period start date",
        "Début de la période de facturation",
        "date",
    ),
    "ApplicableHeaderTradeSettlement/BillingSpecifiedPeriod/EndDateTime/DateTimeString": (
        "BT-74",
        "Invoicing period end date",
        "Fin de la période de facturation",
        "date",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:allowance/BasisAmount": (
        "BT-93",
        "Document level allowance base amount",
        "Assiette de la remise",
        "amount",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:allowance/CalculationPercent": (
        "BT-94",
        "Document level allowance percentage",
        "Pourcentage de la remise",
        "percent",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:allowance/CategoryTradeTax/RateApplicablePercent": (
        "BT-96",
        "Document level allowance VAT rate",
        "Taux de TVA de la remise",
        "percent",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:charge/BasisAmount": (
        "BT-100",
        "Document level charge base amount",
        "Assiette des frais",
        "amount",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:charge/CalculationPercent": (
        "BT-101",
        "Document level charge percentage",
        "Pourcentage des frais",
        "percent",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:charge/CategoryTradeTax/RateApplicablePercent": (
        "BT-103",
        "Document level charge VAT rate",
        "Taux de TVA des frais",
        "percent",
    ),
    "SpecifiedTradeSettlementHeaderMonetarySummation/TaxTotalAmount": (
        "BT-110",
        "Invoice total VAT amount",
        "Montant total de TVA",
        "amount",
    ),
    "SpecifiedTradeSettlementHeaderMonetarySummation/TaxTotalAmount:accounting": (
        "BT-111",
        "Invoice total VAT amount in accounting currency",
        "Montant total de TVA en devise de comptabilisation",
        "amount",
    ),
    "AdditionalReferencedDocument:916/IssuerAssignedID": (
        "BT-122",
        "Supporting document reference",
        "Référence du document justificatif",
        "text",
    ),
    "AdditionalReferencedDocument:916/Name": (
        "BT-123",
        "Supporting document description",
        "Description du document justificatif",
        "text",
    ),
    "SpecifiedLineTradeSettlement/BillingSpecifiedPeriod": (
        "BG-26",
        "Invoice line period",
        "Période de la ligne",
        "period",
    ),
    "SpecifiedLineTradeSettlement/SpecifiedTradeAllowanceCharge:allowance/BasisAmount": (
        "BT-137",
        "Invoice line allowance base amount",
        "Assiette de la remise sur la ligne",
        "amount",
    ),
    "SpecifiedLineTradeSettlement/SpecifiedTradeAllowanceCharge:charge/BasisAmount": (
        "BT-142",
        "Invoice line charge base amount",
        "Assiette des frais sur la ligne",
        "amount",
    ),
    "GrossPriceProductTradePrice/AppliedTradeAllowanceCharge:allowance/ActualAmount": (
        "BT-147",
        "Item price discount",
        "Rabais sur le prix",
        "amount",
    ),
    "AppliedTradeAllowanceCharge/ChargeIndicator/Indicator": (None, "", "", "syntax"),
    "GrossPriceProductTradePrice/ChargeAmount": ("BT-148", "Item gross price", "Prix brut", "amount"),
    "NetPriceProductTradePrice/BasisQuantity": (
        "BT-149",
        "Item price base quantity",
        "Quantité de base du prix",
        "quantity",
    ),
    # In CII, a line's VAT information also carries a tax type, always VAT in EN 16931: it has no business term of
    # its own, so the group's.
    "SpecifiedLineTradeSettlement/ApplicableTradeTax/TypeCode": (
        "BG-30",
        "Line VAT information: tax type",
        "TVA de la ligne : type de taxe",
        "text",
    ),
    "ApplicableProductCharacteristic/Description": ("BT-160", "Item attribute name", "Nom de l'attribut", "text"),
    "ApplicableProductCharacteristic/Value": ("BT-161", "Item attribute value", "Valeur de l'attribut", "text"),
    # the core EN 16931 rules and the code list rules (BR-CL)
    "GuidelineSpecifiedDocumentContextParameter/ID": (
        "BT-24",
        "Specification identifier",
        "Identifiant de spécification",
        "text",
    ),
    "ApplicableHeaderTradeSettlement/TaxCurrencyCode": (
        "BT-6",
        "VAT accounting currency code",
        "Code de devise de comptabilisation de la TVA",
        "text",
    ),
    "ApplicableHeaderTradeSettlement/ApplicableTradeTax/DueDateTypeCode": (
        "BT-8",
        "VAT point date code",
        "Code de date d'exigibilité de la TVA",
        "text",
    ),
    "ExchangedDocument/IncludedNote/SubjectCode": (
        "BT-21",
        "Invoice note subject code",
        "Code du sujet de la note",
        "text",
    ),
    "SellerTradeParty/SpecifiedLegalOrganization/ID": (
        "BT-30",
        "Seller legal registration identifier",
        "Identifiant d'immatriculation légale du vendeur",
        "id",
    ),
    "SellerTradeParty/URIUniversalCommunication/URIID": (
        "BT-34",
        "Seller electronic address",
        "Adresse électronique du vendeur",
        "id",
    ),
    "SellerTradeParty/PostalTradeAddress/CountryID": ("BT-40", "Seller country code", "Code pays du vendeur", "text"),
    "BuyerTradeParty/URIUniversalCommunication/URIID": (
        "BT-49",
        "Buyer electronic address",
        "Adresse électronique de l'acheteur",
        "id",
    ),
    "BuyerTradeParty/PostalTradeAddress/CountryID": ("BT-55", "Buyer country code", "Code pays de l'acheteur", "text"),
    "ShipToTradeParty/PostalTradeAddress/LineOne": (
        "BT-75",
        "Deliver to address line 1",
        "Adresse de livraison",
        "text",
    ),
    "ShipToTradeParty/PostalTradeAddress/CityName": ("BT-77", "Deliver to city", "Ville de livraison", "text"),
    "ShipToTradeParty/PostalTradeAddress/PostcodeCode": (
        "BT-78",
        "Deliver to post code",
        "Code postal de livraison",
        "text",
    ),
    "ShipToTradeParty/PostalTradeAddress/CountryID": (
        "BT-80",
        "Deliver to country code",
        "Code pays de livraison",
        "text",
    ),
    "SpecifiedTradeSettlementPaymentMeans/TypeCode": (
        "BT-81",
        "Payment means type code",
        "Code du moyen de paiement",
        "text",
    ),
    "ApplicableTradeSettlementFinancialCard/ID": (
        "BT-87",
        "Payment card primary account number",
        "Numéro de la carte de paiement",
        "text",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:allowance/CategoryTradeTax/CategoryCode": (
        "BT-95",
        "Document level allowance VAT category code",
        "Catégorie de TVA de la remise",
        "text",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:allowance/ReasonCode": (
        "BT-98",
        "Document level allowance reason code",
        "Code motif de la remise",
        "text",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:charge/CategoryTradeTax/CategoryCode": (
        "BT-102",
        "Document level charge VAT category code",
        "Catégorie de TVA des frais",
        "text",
    ),
    "ApplicableHeaderTradeSettlement/SpecifiedTradeAllowanceCharge:charge/ReasonCode": (
        "BT-105",
        "Document level charge reason code",
        "Code motif des frais",
        "text",
    ),
    # in CII, an allowance's or charge's VAT category also carries a tax type, always VAT: no business term of its own
    "SpecifiedTradeAllowanceCharge/CategoryTradeTax/TypeCode": (None, "", "", "syntax"),
    # a VAT breakdown (BG-23) as a whole, when one is missing or one too many (the VAT category rules)
    "ApplicableHeaderTradeSettlement/ApplicableTradeTax/CalculatedAmount": (
        "BT-117",
        "VAT category tax amount",
        "Montant de TVA de la catégorie",
        "amount",
    ),
    "ApplicableHeaderTradeSettlement/ApplicableTradeTax/BasisAmount": (
        "BT-116",
        "VAT category taxable amount",
        "Base de la catégorie de TVA",
        "amount",
    ),
    "ApplicableHeaderTradeSettlement/ApplicableTradeTax/RateApplicablePercent": (
        "BT-119",
        "VAT category rate",
        "Taux de la catégorie de TVA",
        "percent",
    ),
    "ApplicableHeaderTradeSettlement/ApplicableTradeTax/ExemptionReason": (
        "BT-120",
        "VAT exemption reason text",
        "Motif d'exonération de TVA",
        "text",
    ),
    # in CII, a VAT breakdown also carries a tax type, always VAT: no business term of its own
    "ApplicableHeaderTradeSettlement/ApplicableTradeTax/TypeCode": (None, "", "", "syntax"),
    "ApplicableHeaderTradeSettlement/ApplicableTradeTax/CategoryCode": (
        "BT-118",
        "VAT category code",
        "Code de catégorie de TVA",
        "text",
    ),
    "ApplicableHeaderTradeSettlement/ApplicableTradeTax/ExemptionReasonCode": (
        "BT-121",
        "VAT exemption reason code",
        "Code motif d'exonération de TVA",
        "text",
    ),
    "AdditionalReferencedDocument:916/AttachmentBinaryObject": (
        "BT-125",
        "Attached document",
        "Document joint",
        "file",
    ),
    "AssociatedDocumentLineDocument/LineID": ("BT-126", "Invoice line identifier", "Identifiant de la ligne", "text"),
    "SpecifiedLineTradeSettlement/BillingSpecifiedPeriod/StartDateTime/DateTimeString": (
        "BT-134",
        "Invoice line period start date",
        "Début de la période de la ligne",
        "date",
    ),
    "SpecifiedLineTradeSettlement/BillingSpecifiedPeriod/EndDateTime/DateTimeString": (
        "BT-135",
        "Invoice line period end date",
        "Fin de la période de la ligne",
        "date",
    ),
    "SpecifiedLineTradeSettlement/ApplicableTradeTax/CategoryCode": (
        "BT-151",
        "Invoiced item VAT category code",
        "Catégorie de TVA de la ligne",
        "text",
    ),
    "SpecifiedTradeProduct/GlobalID": ("BT-157", "Item standard identifier", "Identifiant standard de l'article", "id"),
    "DesignatedProductClassification/ClassCode": (
        "BT-158",
        "Item classification identifier",
        "Identifiant de classification de l'article",
        "id",
    ),
    "OriginTradeCountry/ID": ("BT-159", "Item country of origin", "Pays d'origine de l'article", "text"),
}
IGNORED = {"format"}  # a date's format attribute, always 102 here: the date itself is what the page shows


@dataclass(frozen=True)
class Difference:
    term: str  # the business term, e.g. "BT-122"; None for an element that has none of its own
    en: str
    fr: str
    kind: str
    path: str  # where it sits in the XML: its name and its parents', as many as tell it apart in the file
    value: str | None  # the element's text in the invalid example; None when it is not there
    attributes: dict  # its attributes, the date format aside (a currency, a scheme, a unit)
    reference_value: str | None  # the same in the invoice it is compared with
    reference_attributes: dict


def _name(e):
    """The element's local name; a reference document with its type code, an allowance or charge with its kind, a VAT
    total in another currency than the invoice's (BT-111, in the VAT accounting currency) apart from the VAT total
    (BT-110), as they stand for different business terms."""
    name = etree.QName(e).localname
    if name == "TaxTotalAmount":
        invoice = e.getroottree().find(".//{*}InvoiceCurrencyCode")
        currency = e.get("currencyID")
        accounting = invoice is not None and currency is not None and currency != (invoice.text or "").strip()
        return f"{name}:accounting" if accounting else name
    if name == "AdditionalReferencedDocument":
        code = e.find("{*}TypeCode")
        return f"{name}:{(code.text or '').strip() if code is not None else ''}"
    if name in ("SpecifiedTradeAllowanceCharge", "AppliedTradeAllowanceCharge"):
        indicator = e.find("{*}ChargeIndicator/{*}Indicator")
        charge = indicator is not None and (indicator.text or "").strip() == "true"
        return f"{name}:{'charge' if charge else 'allowance'}"
    return name


def _leaves(xml_bytes):
    """Each element without child elements, by its path with sibling positions: (path without positions, text,
    attributes)."""
    found = {}

    def walk(e, path, plain):
        children = [c for c in e if isinstance(c.tag, str)]
        if not children:
            attributes = {etree.QName(k).localname: v for k, v in e.attrib.items()}
            found[path] = (plain, (e.text or "").strip(), {k: v for k, v in attributes.items() if k not in IGNORED})
        seen = Counter()
        for c in children:
            name = _name(c)
            seen[name] += 1
            walk(c, f"{path}/{name}[{seen[name]}]", f"{plain}/{name}")

    walk(etree.fromstring(xml_bytes), "", "")
    return found


def _bare(plain):
    """The path as the XML writes it, without the type codes and kinds _name adds."""
    return re.sub(r":[\w-]*", "", plain).strip("/")


def _place(plain, others):
    """The element's name and its parent's, and more parents while another element of the files ends the same way:
    enough to find it in the XML by a search."""
    parts = _bare(plain).split("/")
    for k in range(2, len(parts)):
        suffix = "/".join(parts[-k:])
        if not any(("/" + o).endswith("/" + suffix) for o in others if o != "/".join(parts)):
            return suffix
    return "/".join(parts)


def _term(plain):
    """The TERMS entry whose path ends this one, the longest if several do; else the one that ends it once the type
    codes and kinds are left out (an element that means the same whatever they are)."""
    for path in (plain, re.sub(r":[\w-]*", "", plain)):
        keys = [k for k in TERMS if path.endswith("/" + k)]
        if keys:
            return TERMS[max(keys, key=len)]
    return None


def differences(xml_bytes, reference_bytes):
    """The elements whose text or attributes differ from the reference, in the order of the invalid example's XML
    (an element only in the reference comes after, with no value)."""
    mine, theirs = _leaves(xml_bytes), _leaves(reference_bytes)
    others = {_bare(leaf[0]) for leaf in (*mine.values(), *theirs.values())}
    found = []
    for path in [*mine, *(p for p in theirs if p not in mine)]:
        a, b = mine.get(path), theirs.get(path)
        if a and b and a[1:] == b[1:]:
            continue
        plain = (a or b)[0]
        term = _term(plain)
        if term is None:
            raise ValueError(f"no business term for {plain}: name it in differences.TERMS")
        if term[3] != "syntax":
            mine_value, mine_attributes = a[1:] if a else (None, {})
            their_value, their_attributes = b[1:] if b else (None, {})
            place = _place(plain, others)
            found.append(Difference(*term, place, mine_value, mine_attributes, their_value, their_attributes))
    return found
