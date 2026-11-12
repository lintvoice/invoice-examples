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
    fr = CACHE / "france-rfe-1.4.0.04"
    if not fr.exists():
        archive = zipfile.ZipFile(io.BytesIO(_get(FRANCE_RFE)))
        for name in archive.namelist():
            rel = name.split("/", 1)[1] if "/" in name else ""
            if rel.startswith(FX) and not name.endswith("/"):  # never the Z.* folders (AFNOR documents)
                out = fr / rel[len(FX) :]
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(archive.read(name))


class Judge:
    def __init__(self):
        from saxonche import PySaxonProcessor

        install()
        fr = CACHE / "france-rfe-1.4.0.04"
        self.proc = PySaxonProcessor(license=False)
        self.xsd = etree.XMLSchema(etree.parse(str(fr / "1xsd/Factur-X_EN16931.xsd")))
        self.sets = {
            name: self.proc.new_xslt30_processor().compile_stylesheet(stylesheet_file=str(path))
            for name, path in {
                "EN 16931": CACHE / "en16931-1.3.17/xslt/EN16931-CII-validation.xslt",
                "Factur-X": fr / "2xslt/FACTUR-X_EN16931.xslt",
                "BR-FR": fr / "2xslt/BR-FR-Flux2-Schematron-CII.xslt",
            }.items()
        }

    def schema_errors(self, xml):
        return [] if self.xsd.validate(etree.fromstring(xml)) else [e.message for e in self.xsd.error_log]

    def fired(self, xml):
        """Rule ids that fail (fatal or error), across the three Schematron sets."""
        node = self.proc.parse_xml(xml_text=xml.decode("utf-8"))
        ids = set()
        for exe in self.sets.values():
            svrl = etree.fromstring(exe.transform_to_string(xdm_node=node).encode("utf-8"))
            ids |= {
                f.get("id")
                for f in svrl.xpath("//svrl:failed-assert | //svrl:successful-report", namespaces=SVRL)
                if (f.get("flag") or "fatal") in ("fatal", "error")
            }
        return ids
