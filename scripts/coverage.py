"""Write COVERAGE.md: for each target, which rules have an invalid example, and what is wrong in it.

The rules: the EN 16931 business rules (EN 16931 1.3.17, CII) for every target; the BR-FR rules (France_RFE 1.4.0.04,
CII) for target fr. Run after the tests have installed the rules: uv run python scripts/coverage.py
"""

import re
from pathlib import Path

from invoice_examples.targets import TARGETS

ROOT = Path(__file__).parent.parent
EN16931 = ROOT / ".rules-cache/en16931-1.3.17/schematron/preprocessed/EN16931-CII-validation-preprocessed.sch"
SCH = ROOT / ".rules-cache/france-rfe-1.4.0.04/schematron/BR-FR-Flux2-Schematron-CII.sch"
# EN 16931 rules that no schema-valid Factur-X EN 16931 invoice can fail: every example here stays schema-valid.
NO_EXAMPLE = {
    "BR-16": "no example: the Factur-X EN 16931 schema requires at least one line",
    "BR-22": "no example: the Factur-X EN 16931 schema requires each line's invoiced quantity",
    "BR-26": "no example: the Factur-X EN 16931 schema requires each line's net price",
    "BR-CO-18": "no example: the Factur-X EN 16931 schema requires at least one VAT breakdown",
    "BR-12": "no example: the Factur-X EN 16931 schema requires the sum of the line net amounts (BT-106)",
    "BR-13": "no example: the Factur-X EN 16931 schema requires the total without VAT (BT-109)",
    "BR-14": "no example: the Factur-X EN 16931 schema requires the total with VAT (BT-112)",
    "BR-15": "no example: the Factur-X EN 16931 schema requires the amount due (BT-115)",
    "BR-24": "no example: the Factur-X EN 16931 schema requires each line's net amount (BT-131)",
    "BR-31": "no example: the Factur-X EN 16931 schema requires each document level allowance's amount (BT-92)",
    "BR-36": "no example: the Factur-X EN 16931 schema requires each document level charge's amount (BT-99)",
    "BR-41": "no example: the Factur-X EN 16931 schema requires each line allowance's amount (BT-136)",
    "BR-43": "no example: the Factur-X EN 16931 schema requires each line charge's amount (BT-141)",
    "BR-47": "no example: the Factur-X EN 16931 schema requires each VAT breakdown's category code (BT-118)",
    "BR-49": "no example: the Factur-X EN 16931 schema requires the payment means type code (BT-81)",
    "BR-54": "no example: the Factur-X EN 16931 schema requires both the name (BT-160) and the value (BT-161) of an "
    "item attribute",
}
# Rules that an EN 16931 invoice cannot reach, or only through cases we do not generate yet.
NOT_APPLICABLE = (
    ("EXT-FR-FE", "Factur-X EXTENDED elements; the fr target is the EN 16931 profile"),
    ("BR-FR-MV-", "multi-vendor invoices (special contract)"),
    ("BR-FR-BD-", "special contract BD"),
    (
        "BR-FR-30",
        "unreachable: the rule looks for IncludedSupplyChainTradeLineItem/AdditionalReferencedDocument, "
        "but no CII schema has that element (Factur-X 1.09.2 EN 16931 and EXTENDED, CII D22B): they put BT-128 under "
        "SpecifiedLineTradeSettlement (possible France_RFE issue; the UBL rule works)",
    ),
    (
        "BR-FR-27_BG-32",
        "unreachable in the EN 16931 profile: the Factur-X schema requires ram:Description in every item attribute",
    ),
    (
        "BR-FR-DEC-01_BT-111",
        "unreachable: its rule has the same context as BR-FR-DEC-01_BT-110 in the same pattern, so the BT-110 rule "
        "always takes the node (possible France_RFE issue)",
    ),
)


def _examples(target):
    """Each rule id's example: the one that fails the fewest rules (the first, among equals), so that an example made
    for another rule, which fails this one on the side, does not take its place."""
    covered = {}
    for v in target.VARIANTS:
        for f in v.fires:
            if f not in covered or len(v.fires) < len(covered[f].fires):
                covered[f] = v
    return covered


def _row(rule, covered, why):
    if rule in covered:
        v = covered[rule]
        return f"| {rule} | `invalid/{v.id}` | {v.en} |"
    return f"| {rule} | {why or 'not yet'} | |"


def _en16931(name, target):
    text = EN16931.read_text(encoding="utf-8")
    rules = list(dict.fromkeys(re.findall(r'<assert\b[^>]*\bid="(BR-[^"]+)"', text)))
    covered = _examples(target)
    n_cov = sum(r in covered for r in rules)
    # an example of an EN 16931 rule these files no longer hold (BR-CO-25, in an EXTENDED-CTC-FR invoice)
    others = sorted({v.id for r, v in covered.items() if re.match(r"BR-(?!FR)", r) and r not in rules})
    also = [
        f"Also {', '.join(f'`invalid/{o}`' for o in others)}: a rule these files no longer hold, in a profile that keeps it.",
        "",
    ]
    return (
        [
            f"## Target `{name}`: EN 16931 business rules",
            "",
            f"EN 16931 1.3.17, CII Schematron: {len(rules)} business rule ids. **{n_cov} have an invalid example**; "
            f"{len(NO_EXAMPLE)} cannot have one, the others not yet.",
            "",
            "| Rule id | Example | What is wrong |",
            "| --- | --- | --- |",
            *(_row(r, covered, NO_EXAMPLE.get(r)) for r in rules),
            "",
            *(also if others else []),
        ],
        n_cov,
        len(rules),
    )


def _br_fr(target):
    text = SCH.read_text(encoding="utf-8")
    ids = list(dict.fromkeys(re.findall(r'id="(BR-FR-[^"]+)"', text)))
    asserted = [i for i in ids if re.search(rf'<(assert|report)[^>]*id="{re.escape(i)}"', text)]
    covered = _examples(target)
    rows, n_cov, n_app = [], 0, 0
    for rule in asserted:
        why = next((w for prefix, w in NOT_APPLICABLE if prefix in rule), None)
        if rule in covered:
            n_cov, n_app = n_cov + 1, n_app + 1
        elif why:
            why = f"not applicable: {why}"
        else:
            why, n_app = "**to do**", n_app + 1
        rows.append(_row(rule, covered, why))
    return (
        [
            "## Target `fr`: BR-FR rules",
            "",
            f"France_RFE 1.4.0.04, CII Schematron: {len(asserted)} rule ids. "
            f"**{n_cov} of the {n_app} that apply to a Factur-X EN 16931 invoice have an invalid example.**",
            "",
            "| Rule id | Example | What is wrong |",
            "| --- | --- | --- |",
            *rows,
            "",
        ],
        n_cov,
        n_app,
    )


def main():
    out = [
        "# Coverage: the rules with an invalid example, by target",
        "",
        "Generated by `scripts/coverage.py` from the official rule files and each target's examples. A rule's example is "
        "the one that fails the fewest rules; what is wrong is its description in `manifest.json`.",
        "",
    ]
    for name in ("en16931", "fr"):
        section, n_cov, n_all = _en16931(name, TARGETS[name])
        out += section
        print(f"{name}: {n_cov}/{n_all} EN 16931 business rule ids have an example")
    section, n_cov, n_app = _br_fr(TARGETS["fr"])
    out += section
    print(f"fr: {n_cov}/{n_app} applicable BR-FR rule ids have an example")
    (ROOT / "COVERAGE.md").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
