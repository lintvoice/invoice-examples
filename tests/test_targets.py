"""Every target: its valid invoice passes every official rule it names; each variant fails exactly the rules it
declares, and stays schema-valid."""

import pytest

from invoice_examples import cii, cli
from invoice_examples.targets import TARGETS, en16931, fr

VARIANTS = [(name, v) for name, t in TARGETS.items() for v in t.VARIANTS]


def _id(case):
    return f"{case[0]}-{case[1].id}" if isinstance(case, tuple) else case


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_valid_example_passes_every_rule(judge, name):
    target = TARGETS[name]
    xml = cii.to_bytes(target.build())
    assert judge.schema_errors(xml) == []
    assert judge.fired(xml, target.RULES) == set()


@pytest.mark.parametrize("case", VARIANTS, ids=_id)
def test_variant_fails_exactly_the_declared_rules(judge, case):
    target, variant = TARGETS[case[0]], case[1]
    xml = cii.to_bytes(target.build(variant))
    assert judge.schema_errors(xml) == [], "an invalid example must stay schema-valid: only a business rule is broken"
    assert judge.fired(xml, target.RULES) == set(variant.fires)


@pytest.mark.parametrize("case", [c for c in VARIANTS if cli.fixed_counterpart(TARGETS[c[0]], c[1])], ids=_id)
def test_fixed_counterpart_passes_every_rule(judge, case):
    """The same invoice before the edit that breaks the rule: what the reader compares with."""
    target = TARGETS[case[0]]
    xml = cli.fixed_counterpart(target, case[1])
    assert judge.schema_errors(xml) == []
    assert judge.fired(xml, target.RULES) == set()


@pytest.mark.parametrize("case", VARIANTS, ids=_id)
def test_variant_is_about_a_rule_it_fails(case):
    variant = case[1]
    assert any(
        f == variant.rule or f.startswith(variant.rule + "_") or f.startswith(variant.rule + "-") for f in variant.fires
    )


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_variant_ids_are_unique(name):
    ids = [v.id for v in TARGETS[name].VARIANTS]
    assert len(ids) == len(set(ids))


def test_no_french_rule_in_the_european_target():
    assert not [f for v in en16931.VARIANTS for f in v.fires if f.startswith(("BR-FR", "EXT-FR"))]
    assert "BR-FR" not in en16931.RULES


def test_every_european_rule_also_has_an_example_on_the_french_invoice():
    """Under the same id, or under the name of a French rule that fails next to it (BR-DEC under BR-FR-DEC-01, BR-52
    under BR-FR-29). Except the zero rate (BR-Z) and the operations outside the scope of VAT (BR-O), which a French
    invoice cannot show (cii.FRENCH, the VAT categories)."""
    european = {v.rule for v in en16931.VARIANTS if not v.rule.startswith(("BR-Z-", "BR-O-"))}
    assert european <= {f for v in fr.VARIANTS for f in v.fires}
    assert not [v for v in fr.VARIANTS if v.rule.startswith(("BR-Z-", "BR-O-"))]
