"""The command line: list, generate, one rule, errors; and the generated files themselves."""

import io
import json
from pathlib import Path

from pypdf import PdfReader

from invoice_examples import cii, pdf
from invoice_examples.edits import Variant
from invoice_examples.targets import TARGETS, en16931, fr

ROOT = Path(__file__).parent.parent


def test_list_shows_the_valid_example_and_every_variant(run):
    code, out, _ = run("list", "--target", "fr")
    assert code == 0
    assert "valid" in out
    assert all(v.id in out for v in fr.VARIANTS)


def test_generate_writes_everything_and_a_manifest(run, tmp_path):
    code, _out, _ = run("generate", "--target", "fr", "--out", tmp_path)
    assert code == 0
    folder = tmp_path / "fr"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["licence"] == "CC0-1.0"
    assert manifest["rules"]["BR-FR"].startswith("1.4.0.04")
    assert len(manifest["examples"]) == 1 + len(fr.VARIANTS)
    for e in manifest["examples"]:
        for f in e["files"].values():
            assert (folder / f).exists()
    assert manifest["examples"][0] == {**manifest["examples"][0], "id": "valid", "status": "valid", "fires": []}


def test_generate_one_rule(run, tmp_path):
    code, _, _ = run("generate", "--target", "fr", "--rule", "BR-FR-10", "--format", "xml", "--out", tmp_path)
    assert code == 0
    files = sorted(p.relative_to(tmp_path / "fr").as_posix() for p in (tmp_path / "fr").rglob("*.xml"))
    assert files == ["invalid/BR-FR-10.xml", "valid.xml"]


def test_generate_a_rule_group(run, tmp_path):
    code, _, _ = run("generate", "--target", "fr", "--rule", "BR-FR-05", "--format", "xml", "--out", tmp_path)
    assert code == 0
    assert len(list((tmp_path / "fr" / "invalid").glob("BR-FR-05-*.xml"))) == 3


def test_unknown_rule_is_an_error(run, tmp_path):
    code, _, err = run("generate", "--rule", "BR-XX-99", "--out", tmp_path)
    assert code == 2
    assert "no variant for BR-XX-99" in err


def test_generation_is_deterministic(run, tmp_path):
    run("generate", "--out", tmp_path / "a")
    run("generate", "--out", tmp_path / "b")
    a = sorted((tmp_path / "a").rglob("*.*"))
    b = sorted((tmp_path / "b").rglob("*.*"))
    assert [p.read_bytes() for p in a] == [p.read_bytes() for p in b]


def test_pdf_carries_the_xml_as_factur_x(tmp_path):
    xml = cii.to_bytes(fr.build())
    reader = PdfReader(io.BytesIO(pdf.facturx_pdf(xml)))
    assert reader.attachments["factur-x.xml"] == [xml]


def test_pdf_page_is_readable_and_marked_specimen():
    """The page shows the invoice's own data, and says it is a fictitious specimen."""
    xml = cii.to_bytes(fr.build())
    text = PdfReader(io.BytesIO(pdf.facturx_pdf(xml))).pages[0].extract_text()
    for expected in ("SPÉCIMEN", "F2026-0042", "Atelier Exemple SAS", "lintvoice/invoice-examples"):
        assert expected in text


def test_invalid_pdf_states_the_rule_and_shows_the_wrong_value():
    valid = cii.to_bytes(fr.build())
    variant = next(v for v in fr.VARIANTS if v.id == "BR-CO-15")
    xml = cii.to_bytes(fr.build(variant))
    text = (
        PdfReader(io.BytesIO(pdf.facturx_pdf(xml, reference=valid, rule=variant.rule, description=variant.fr)))
        .pages[0]
        .extract_text()
    )
    assert "Erreur · BR-CO-15" in text
    assert pdf.read(xml)["gross"] != pdf.read(valid)["gross"]  # the value the page draws in the error colour


def test_pdf_amounts_are_in_the_invoices_own_currency():
    """BT-5: the € sign for an invoice in euros, the currency's code for any other, in each language's place."""
    usd = Variant("USD", "BT-5", (), "", "", {"currency": "USD"})
    pages = {
        lang: PdfReader(io.BytesIO(pdf.page_pdf(cii.to_bytes(target.build(usd)), lang=lang))).pages[0].extract_text()
        for lang, target in (("fr", fr), ("en", en16931))
    }
    assert "1 230,00 USD" in pages["fr"] and "€" not in pages["fr"]
    assert "USD 1,219.75" in pages["en"] and "€" not in pages["en"]


def test_annotated_pdf_gives_business_term_numbers(run, tmp_path):
    run("generate", "--out", tmp_path)  # the default target is the European one
    manifest = json.loads((tmp_path / "en16931" / "manifest.json").read_text(encoding="utf-8"))
    text = PdfReader(tmp_path / "en16931" / manifest["annotated"]["pdf"]).pages[0].extract_text()
    assert "BT-1" in text and "BT-112" in text


def test_committed_examples_are_up_to_date(run, tmp_path):
    """examples/ is generated: regenerate every target and compare, so the repository never drifts from the code."""
    for target in TARGETS:
        run("generate", "--target", target, "--out", tmp_path)
    fresh = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    committed = {
        p.relative_to(ROOT / "examples").as_posix(): p.read_bytes()
        for p in (ROOT / "examples").rglob("*")
        if p.is_file() and p.name != "LICENSE"
    }
    assert committed == fresh, "run: uv run invoice-examples generate --target <each target> --out examples"


def test_the_european_target_names_no_french_rule_and_writes_english_pages(run, tmp_path):
    code, _, _ = run("generate", "--target", "en16931", "--out", tmp_path)
    assert code == 0
    folder = tmp_path / "en16931"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["target"] == "en16931"
    assert set(manifest["rules"]) == {"EN 16931", "Factur-X"}
    assert len(manifest["examples"]) == 1 + len(en16931.VARIANTS)
    assert all(e["description"]["en"] and e["description"]["fr"] for e in manifest["examples"])
    valid = PdfReader(folder / "valid.pdf").pages[0].extract_text()
    for expected in ("SPECIMEN", "INVOICE", "Musterlieferant GmbH", "€1,219.75", "2026-10-20"):
        assert expected in valid
    assert "Process" not in valid  # BT-23 is optional outside France: an empty row is left out
    invalid = PdfReader(folder / "invalid" / "BR-CO-15.pdf").pages[0].extract_text()
    assert "Error · BR-CO-15" in invalid and "The invoice total with VAT (BT-112)" in invalid


def test_list_the_european_target(run):
    code, out, _ = run("list", "--target", "en16931")
    assert code == 0
    assert all(v.id in out for v in en16931.VARIANTS)
    assert "BR-FR" not in out
