"""The command line: list, generate, one rule, errors; and the generated files themselves."""

import io
import json
from pathlib import Path

from pypdf import PdfReader

from invoice_examples import cii, pdf
from invoice_examples.targets import fr

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
    code, _, _ = run("generate", "--rule", "BR-FR-10", "--format", "xml", "--out", tmp_path)
    assert code == 0
    files = sorted(p.relative_to(tmp_path / "fr").as_posix() for p in (tmp_path / "fr").rglob("*.xml"))
    assert files == ["invalid/BR-FR-10.xml", "valid.xml"]


def test_generate_a_rule_group(run, tmp_path):
    code, _, _ = run("generate", "--rule", "BR-FR-05", "--format", "xml", "--out", tmp_path)
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


def test_committed_examples_are_up_to_date(run, tmp_path):
    """examples/ is generated: regenerate it and compare, so the repository never drifts from the code."""
    run("generate", "--out", tmp_path)
    fresh = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    committed = {
        p.relative_to(ROOT / "examples").as_posix(): p.read_bytes()
        for p in (ROOT / "examples").rglob("*")
        if p.is_file() and p.name != "LICENSE"
    }
    assert committed == fresh, "run: uv run invoice-examples generate --out examples"
