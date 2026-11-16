"""Command line: invoice-examples list | generate.

invoice-examples list --target fr
invoice-examples generate --target fr --out examples/        # the valid invoice and every invalid variant
invoice-examples generate --target fr --rule BR-FR-10 --out . # one variant, plus the valid invoice
"""

import dataclasses
import argparse
import json
import sys
from pathlib import Path

from . import __version__, cii, pdf
from .targets import TARGETS

FORMATS = ("xml", "pdf")


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _files(out, stem, xml, formats, **page):
    """Write the XML and its PDF. `page` goes to the PDF page: the valid invoice as reference, the rule and
    what is wrong, so an invalid variant's page shows where the mistake is."""
    written = {}
    if "xml" in formats:
        written["xml"] = _write(out / f"{stem}.xml", xml).relative_to(out).as_posix()
    if "pdf" in formats:
        written["pdf"] = _write(out / f"{stem}.pdf", pdf.facturx_pdf(xml, **page)).relative_to(out).as_posix()
    return written


def cmd_list(args, out):
    target = TARGETS[args.target]
    print(f"Target {args.target}: rules {', '.join(f'{k} {v}' for k, v in target.RULES.items())}", file=out)
    print(f"  {'valid':<14} the baseline invoice, which passes every rule", file=out)
    for v in target.VARIANTS:
        print(f"  {v.id:<14} fails {', '.join(v.fires)}: {v.en}", file=out)
    return 0


def cmd_generate(args, out):
    target = TARGETS[args.target]
    variants = target.VARIANTS
    if args.rule:
        wanted = {r.strip() for r in args.rule.split(",")}
        variants = [v for v in variants if v.id in wanted or v.rule in wanted]
        unknown = wanted - {v.id for v in variants} - {v.rule for v in variants}
        if unknown:
            print(
                f"invoice-examples: no variant for {', '.join(sorted(unknown))} in target {args.target} "
                f"(see: invoice-examples list --target {args.target})",
                file=sys.stderr,
            )
            return 2
    formats = [f.strip() for f in args.format.split(",")]
    root = Path(args.out) / args.target
    valid = cii.to_bytes(target.build())
    entries = [
        {
            "id": "valid",
            "status": "valid",
            "fires": [],
            "files": _files(root, "valid", valid, formats),
            "description": {"en": "Passes every rule listed.", "fr": "Passe toutes les règles listées."},
        }
    ]
    for v in variants:
        # A variant that first sets a context (an allowance, a charge, lines…) and then breaks a rule also gets the
        # same invoice before the break, which passes every rule: its page compares with it, and so can the reader.
        fixed = cii.to_bytes(target.build(dataclasses.replace(v, edit=v.fixed))) if v.changes and v.edit else None
        entry = {
            "id": v.id,
            "status": "invalid",
            "rule": v.rule,
            "fires": list(v.fires),
            "files": _files(
                root,
                f"invalid/{v.id}",
                cii.to_bytes(target.build(v)),
                formats,
                reference=fixed or valid,
                rule=v.rule,
                description=v.fr,
            ),
            "description": {"en": v.en, "fr": v.fr},
        }
        if fixed:
            entry["fixed"] = _files(root, f"fixed/{v.id}", fixed, formats)
        entries.append(entry)
    annotated = {}
    if "pdf" in formats:
        # the valid invoice again, each value with its EN 16931 business term number: for reading, not for tests
        annotated = {
            "pdf": _write(root / "annotated.pdf", pdf.facturx_pdf(valid, annotate=True)).relative_to(root).as_posix()
        }
    manifest = {
        "generator": f"invoice-examples {__version__}",
        "target": args.target,
        "syntax": "CII",
        "profile": "Factur-X EN 16931",
        "rules": target.RULES,
        "licence": "CC0-1.0",
        "examples": entries,
        "annotated": annotated,
    }
    _write(root / "manifest.json", (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"wrote {len(entries)} examples ({', '.join(formats)}) and manifest.json in {root}", file=out)
    return 0


def parser():
    p = argparse.ArgumentParser(
        prog="invoice-examples", description="Valid and invalid e-invoice examples, one per rule."
    )
    p.add_argument("--version", action="version", version=f"invoice-examples {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("list", help="list the examples of a target")
    ls.add_argument("--target", choices=sorted(TARGETS), default="fr")
    ls.set_defaults(func=cmd_list)
    gen = sub.add_parser("generate", help="write the valid example and the invalid variants")
    gen.add_argument("--target", choices=sorted(TARGETS), default="fr")
    gen.add_argument(
        "--rule", help="only these variants (ids or rules, comma-separated); the valid example is always written"
    )
    gen.add_argument("--format", default="xml,pdf", help="xml, pdf or both (default: xml,pdf)")
    gen.add_argument("--out", default="examples", help="output folder (default: examples); files go in <out>/<target>/")
    gen.set_defaults(func=cmd_generate)
    return p


def main(argv=None, out=None):
    args = parser().parse_args(argv)
    return args.func(args, out or sys.stdout)
