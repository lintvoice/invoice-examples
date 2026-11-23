<a href="https://lintvoice.com"><picture><source media="(prefers-color-scheme: dark)" srcset="https://lintvoice.com/static/logo/lintvoice-wordmark-dark.svg"><img src="https://lintvoice.com/static/logo/lintvoice-wordmark-light.svg" alt="lintvoice" width="160"></picture></a>

# Test your e-invoice generator, rule by rule

Example invoices checked against the official rules: each invalid one fails the rules its manifest names, and nothing else, so your tests know exactly what must be caught. Free to use for anything: the examples are in the public domain ([CC0](examples/LICENSE)).

## Targets

A target is the set of rules the examples follow. Pick the one your invoices must pass.

| Target | Rules | For |
| --- | --- | --- |
| `en16931` | The European standard EN 16931, and the Factur-X / ZUGFeRD profile rules | An e-invoice that follows the European standard, in any country: the French, German (XRechnung) and Peppol rules all build on it |
| `fr` | The same, plus the French e-invoicing reform's rules (BR-FR) | An invoice from a seller in France |

Next: Germany (XRechnung), then Peppol, and UBL alongside CII.

## Download the examples

Each target has its folder, `examples/en16931/` and `examples/fr/`, which holds, as XML (CII) and as a Factur-X PDF
(in Germany, ZUGFeRD):

- `valid.xml`, `valid.pdf`: an invoice that passes every rule of its target. In `en16931`, a domestic invoice between
  two companies in Germany, with no national field; in `fr`, a French invoice;
- `invalid/<rule>.xml`, `invalid/<rule>.pdf`: the same invoice with one thing wrong, for example
  `invalid/BR-CO-15.xml` (the total with VAT is not the total without VAT plus the VAT) or, in `fr`,
  `invalid/BR-FR-10.xml` (the seller's SIREN is missing);
- `fixed/<rule>.xml`, `fixed/<rule>.pdf`: for an invalid example that first adds something to the invoice (an
  allowance, a charge, lines), the same invoice without the mistake, which passes every rule;
- `manifest.json`: for each example, the rules it fails, in English and French, and the rule versions.

| Rules checked | Version | Targets |
| --- | --- | --- |
| EN 16931 (CII) | [1.3.17](https://github.com/ConnectingEurope/eInvoicing-EN16931/releases/tag/validation-1.3.17) | `en16931`, `fr` |
| Factur-X, EN 16931 profile | 1.09.2 | `en16931`, `fr` |
| BR-FR (French e-invoicing reform), [FNFE-MPE France_RFE](https://github.com/fnfempe/France_RFE/tree/97ba0f3d4ef2abed5780e9490d5c3a2be832ab1d) | 1.4.0.04 | `fr` |
| EXTENDED-CTC-FR (France_RFE), with the CII D22B schema: only for the examples in that profile (`BR-CO-25`) | 1.4.0.04 | `fr` |

Most examples use the Factur-X EN 16931 profile. An example whose rule exists only in a richer profile uses it and says so: `BR-CO-25` is an EXTENDED-CTC-FR invoice, one of the profiles the French reform admits, since the EN 16931 validation files no longer carry that rule ([release notes of 1.3.16](https://github.com/ConnectingEurope/eInvoicing-EN16931/releases/tag/validation-1.3.16)).

**Valid** means:
- no fatal error from the rule sets of its target;
- valid against the Factur-X 1.09.2 EN 16931 schema.

No BR-FR rule fires on an `en16931` example: those rules apply to a seller in France.

**Invalid** means the example fails exactly the rules its manifest entry lists, and nothing else.
- Most fail one rule.
- A few fail two or more, because the official rules overlap (for example EN 16931 `BR-CO-21` and `BR-33`, which both want a reason for a document level allowance).
- Every invalid example stays schema-valid: only a business rule is broken.

**Coverage:** [COVERAGE.md](COVERAGE.md) lists, for each target, every rule with its invalid example and what is wrong in it, and says why a rule has none.

**About the PDFs:** each one has a readable page drawn from its own XML, marked SPECIMEN, and carries that XML as `factur-x.xml`. The pages are in English in `en16931`, in French in `fr`. On an invalid example, the page names the rule it fails and what is wrong, and shows the mistake in red: the values it draws that differ from the invoice it is compared with (`valid.pdf`, or `fixed/<rule>.pdf` when there is one); when the mistake sits in data the page does not draw (a supporting document, a period, the payee), a box under the totals names that file and lists what differs, each element with its business term (BT-…) and its value. `annotated.pdf` is the valid invoice with each value's EN 16931 business term number (BT-…), for learning to read an e-invoice. The PDFs are not PDF/A-3: they are for testing XML extraction and the XML rules, not PDF/A-3 validation.

## Use them in a test suite

The same examples also ship as a Python package, so a test suite can pin a version instead of copying files:

```sh
uvx invoice-examples generate --target en16931 --out examples/   # writes exactly the files of examples/en16931/
uvx invoice-examples generate --target fr --out examples/        # and those of examples/fr/
```

The same version always writes the same bytes. Each release also ships its wheel and sdist on [GitHub Releases](https://github.com/lintvoice/invoice-examples/releases).

## How the examples are checked

The test suite builds every example and runs the official artefacts on it, pinned and downloaded once:
- the EN 16931 Schematron;
- the Factur-X profile rules;
- the BR-FR Schematron, for target `fr` (run with Saxon);
- the Factur-X schema.

It fails if:
- a valid example fails any rule of its target;
- an invalid example fails a rule it does not declare, or misses one it does;
- the committed `examples/` folder differs from what the code generates.

The checks use the official files only, not a validator of ours, so the examples are an independent reference.
France_RFE's AFNOR documents are never downloaded.

```sh
uv sync && uv run pytest
uv run python scripts/coverage.py   # rewrites COVERAGE.md
```

## Licences

- The examples (`examples/`): [CC0-1.0](examples/LICENSE).
- The code: [MIT](LICENSE).
- The fonts drawn in the PDFs (`src/invoice_examples/fonts/`): IBM Plex, [SIL Open Font License 1.1](src/invoice_examples/fonts/OFL.txt).
- The official rules used by the tests keep their own licences (EUPL-1.2 for EN 16931; Apache-2.0 for the France_RFE repository, whose Schematron file headers say EUPL)
  and are not part of this repository.
