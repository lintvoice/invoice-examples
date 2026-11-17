"""Target fr: the baseline passes every official rule; each variant fails exactly the rules it declares."""

import dataclasses

import pytest

from invoice_examples import cii
from invoice_examples.targets import fr


def test_valid_example_passes_every_rule(judge):
    xml = cii.to_bytes(fr.build())
    assert judge.schema_errors(xml) == []
    assert judge.fired(xml) == set()


@pytest.mark.parametrize("variant", fr.VARIANTS, ids=lambda v: v.id)
def test_variant_fails_exactly_the_declared_rules(judge, variant):
    xml = cii.to_bytes(fr.build(variant))
    assert judge.schema_errors(xml) == [], "an invalid example must stay schema-valid: only a business rule is broken"
    assert judge.fired(xml) == set(variant.fires)


@pytest.mark.parametrize("variant", [v for v in fr.VARIANTS if (v.changes and v.edit) or v.fixed], ids=lambda v: v.id)
def test_fixed_counterpart_passes_every_rule(judge, variant):
    """The same invoice before the edit that breaks the rule: what the reader compares with."""
    xml = cii.to_bytes(fr.build(dataclasses.replace(variant, edit=variant.fixed)))
    assert judge.schema_errors(xml) == []
    assert judge.fired(xml) == set()


@pytest.mark.parametrize("variant", fr.VARIANTS, ids=lambda v: v.id)
def test_variant_is_about_a_rule_it_fails(variant):
    assert any(
        f == variant.rule or f.startswith(variant.rule + "_") or f.startswith(variant.rule + "-") for f in variant.fires
    )


def test_variant_ids_are_unique():
    ids = [v.id for v in fr.VARIANTS]
    assert len(ids) == len(set(ids))
