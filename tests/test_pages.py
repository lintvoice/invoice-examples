"""The PDF page of every invalid example shows its mistake in the error colour: in place when the page draws the
value, else in a box under the totals that says the mistake is in the electronic data only, names the file it compares
with and lists what differs."""

from pathlib import Path

import pytest
from pypdf import PdfReader

from invoice_examples import cii, cli, pdf
from invoice_examples.differences import differences
from invoice_examples.targets import TARGETS, en16931

EXAMPLES = Path(__file__).parent.parent / "examples"
VARIANTS = [(name, v) for name, t in TARGETS.items() for v in t.VARIANTS]


@pytest.fixture
def marks(monkeypatch):
    """The texts the page draws in the error colour, the error banner's title line aside."""
    found = []
    text = pdf._Page.text

    def spy(self, x, y, s, font="Plex", size=8.5, color=pdf.INK, align="l"):
        if color == pdf.ERROR and not s.startswith("× "):
            found.append(s)
        return text(self, x, y, s, font, size, color, align)

    monkeypatch.setattr(pdf._Page, "text", spy)
    return found


@pytest.mark.parametrize("case", VARIANTS, ids=lambda c: f"{c[0]}-{c[1].id}")
def test_every_invalid_page_shows_its_mistake_in_red(marks, case):
    target, variant = TARGETS[case[0]], case[1]
    reference = cli.fixed_counterpart(target, variant) or cii.to_bytes(target.build())
    pdf.page_pdf(cii.to_bytes(target.build(variant)), reference, variant.rule, variant.en, lang=target.LANG)
    assert marks, "the page shows no value in the error colour: name the element in differences.TERMS"


def _page(target, stem):
    """The committed page's text, its whitespace folded: the extraction breaks a line where the font changes."""
    return " ".join(PdfReader(EXAMPLES / target / "invalid" / f"{stem}.pdf").pages[0].extract_text().split())


def test_the_box_says_the_mistake_is_in_the_electronic_data_and_names_the_file_it_compares_with():
    page = _page("en16931", "BR-52")
    assert "Mistake in the electronic data only: this page does not show it" in page
    assert (
        "The electronic data is the XML file attached to this PDF as factur-x.xml (see the PDF's attachments)" in page
    )
    assert "Compared with fixed/BR-52.pdf" in page
    assert "Compared with valid.pdf" in _page("en16931", "BR-CO-19")
    page = _page("fr", "BR-FR-17")
    assert "Erreur dans les données électroniques seulement : cette page ne la montre pas" in page
    assert "Par rapport à valid.pdf" in page


def test_the_box_lists_each_element_with_its_business_term_and_value():
    page = _page("en16931", "BR-52")
    assert "BT-122" in page and "Supporting document reference" in page and "blank" in page
    assert "AdditionalReferencedDocument/IssuerAssignedID · in fixed/BR-52.pdf: TS-2026-10" in page
    assert "AdditionalReferencedDocument/IssuerAssignedID · absent de valid.pdf" in _page("fr", "BR-FR-17")
    assert "BG-14" in _page("en16931", "BR-CO-19") and "no dates" in _page("en16931", "BR-CO-19")
    usd = _page("fr", "BR-FR-CO-12")
    assert "Devise de la facture" in usd and "205,00 USD" in usd
    payee = _page("fr", "BR-FR-CO-10-BT-60-1")
    assert "03456789100014 · sans schéma" in payee and "034567891 · schéma 0002" in payee


def test_a_page_that_draws_its_mistake_has_no_box():
    assert "electronic data only" not in _page("en16931", "BR-CO-15")
    assert "données électroniques seulement" not in _page("fr", "BR-FR-05-PMT")


def test_the_document_type_title_shows_the_changed_type():
    """BT-3 has no value drawn as such: its title stands for it, in the error colour when it differs."""
    assert "FACTURE PARTIELLE" in _page("fr", "BR-FR-04")
    assert "données électroniques seulement" not in _page("fr", "BR-FR-04")


def test_an_element_without_a_business_term_stops_the_page():
    """A new example whose mistake sits in an element the table does not name cannot silently show nothing."""
    variant = next(v for v in en16931.VARIANTS if v.id == "BR-27")  # adds a line: its line identifier has no entry
    with pytest.raises(ValueError, match="AssociatedDocumentLineDocument/LineID"):
        differences(cii.to_bytes(en16931.build(variant)), cii.to_bytes(en16931.build()))
