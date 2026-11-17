"""The official rules, pinned, run in-process: the independent judge of every example.

Deliberately not lintvoice: the examples must be checked by the official artefacts alone.
"""

import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

from lxml import etree

CACHE = Path(__file__).parent.parent / ".rules-cache"
EN16931 = (
    "https://github.com/ConnectingEurope/eInvoicing-EN16931/releases/download/validation-1.3.17/en16931-cii-1.3.17.zip",
    "e5f3235824b6b38454b1d54cf3f14e01efb5b33971fbefc4e64997d0ef619e89",
)
FRANCE_RFE = "https://github.com/fnfempe/France_RFE/archive/97ba0f3d4ef2abed5780e9490d5c3a2be832ab1d.zip"
FX = "FNFE_RFE_INVOICE/Factur-X/EN16931/"  # Factur-X 1.09.2 EN 16931 profile: XSD, profile rules, BR-FR rules
CTC = "FNFE_RFE_INVOICE/CII/"  # CII D22B schema, BR-FR and EXTENDED-CTC-FR rules, for EXTENDED-CTC-FR invoices
EXTENDED_CTC_FR = "urn:cen.eu:en16931:2017#conformant#urn.cpro.gouv.fr:1p0:extended-ctc-fr"
SVRL = {"svrl": "http://purl.oclc.org/dsdl/svrl"}


def _get(url):
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "invoice-examples-tests"}), timeout=300
    ) as r:
        return r.read()


def install():
    en = CACHE / "en16931-1.3.17"
    if not en.exists():
        data = _get(EN16931[0])
        assert hashlib.sha256(data).hexdigest() == EN16931[1], "EN 16931 download is not the pinned release"
        zipfile.ZipFile(io.BytesIO(data)).extractall(en)
    folders = {FX: CACHE / "france-rfe-1.4.0.04", CTC: CACHE / "france-rfe-1.4.0.04-cii"}
    missing = {prefix: folder for prefix, folder in folders.items() if not folder.exists()}
    if missing:
        archive = zipfile.ZipFile(io.BytesIO(_get(FRANCE_RFE)))
        for name in archive.namelist():
            rel = name.split("/", 1)[1] if "/" in name else ""
            for prefix, folder in missing.items():
                if rel.startswith(prefix) and not name.endswith("/"):  # never the Z.* folders (AFNOR documents)
                    out = folder / rel[len(prefix) :]
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(archive.read(name))


class Judge:
    def __init__(self):
        from saxonche import PySaxonProcessor

        install()
        fr, cii = CACHE / "france-rfe-1.4.0.04", CACHE / "france-rfe-1.4.0.04-cii"
        self.proc = PySaxonProcessor(license=False)
        compile_ = lambda path: self.proc.new_xslt30_processor().compile_stylesheet(stylesheet_file=str(path))  # noqa: E731
        en16931 = compile_(CACHE / "en16931-1.3.17/xslt/EN16931-CII-validation.xslt")
        # The schema and rule sets lintvoice applies to each profile: Factur-X EN 16931 by default; the CII schema,
        # BR-FR and the EXTENDED-CTC-FR rules for an EXTENDED-CTC-FR invoice.
        self.profiles = {
            "en16931": (
                etree.XMLSchema(etree.parse(str(fr / "1xsd/Factur-X_EN16931.xsd"))),
                [
                    en16931,
                    compile_(fr / "2xslt/FACTUR-X_EN16931.xslt"),
                    compile_(fr / "2xslt/BR-FR-Flux2-Schematron-CII.xslt"),
                ],
            ),
            "extended-ctc-fr": (
                etree.XMLSchema(etree.parse(str(cii / "1xsd-CII_D22B_uncoupled/CrossIndustryInvoice_100pD22B.xsd"))),
                [
                    en16931,
                    compile_(cii / "EN16931/2xslt/BR-FR-Flux2-Schematron-CII.xslt"),
                    compile_(cii / "EXTENDED-CTC-FR/2xslt/EXTENDED-CTC-FR-CII.xslt"),
                ],
            ),
        }

    def _profile(self, xml):
        ids = etree.fromstring(xml).xpath(
            "//*[local-name()='GuidelineSpecifiedDocumentContextParameter']/*[local-name()='ID']/text()"
        )
        return self.profiles["extended-ctc-fr" if ids and ids[0].strip() == EXTENDED_CTC_FR else "en16931"]

    def schema_errors(self, xml):
        xsd = self._profile(xml)[0]
        return [] if xsd.validate(etree.fromstring(xml)) else [e.message for e in xsd.error_log]

    def fired(self, xml):
        """Rule ids that fail (fatal or error), across the profile's Schematron sets."""
        node = self.proc.parse_xml(xml_text=xml.decode("utf-8"))
        ids = set()
        for exe in self._profile(xml)[1]:
            svrl = etree.fromstring(exe.transform_to_string(xdm_node=node).encode("utf-8"))
            ids |= {
                f.get("id")
                for f in svrl.xpath("//svrl:failed-assert | //svrl:successful-report", namespaces=SVRL)
                if (f.get("flag") or "fatal") in ("fatal", "error")
            }
        return ids
