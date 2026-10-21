"""Week 7 — run the measurement campaign over the corpus, and store it.

    cd backend
    python evaluate_corpus.py                          # uses ../data/corpus
    python evaluate_corpus.py "D:/my corpus"           # another folder
    python evaluate_corpus.py --note "after the XB check"
    python evaluate_corpus.py --json                   # also write a JSON file

One folder per package (RP001, RP002...), each holding the document(s) and
ONE annotation workbook (its name contains "annotation").

The campaign is stored in the database (exercise 20): tables
evaluation_campaign (one row per run, with the headline figures) and
evaluation_package (one row per package). The fingerprint (SHA-256) of
every input file is stored with it, so a figure quoted in the thesis can be
traced back to the exact files that produced it. It needs STORAGE=sql in
.env — the database the application uses. With STORAGE=memory nothing
could be kept, so the campaign is written to a JSON file instead.

No server and no model call: the rule-based extractor and the domain layer.
Run it as often as you like — each run is a new campaign, none is replaced.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from app.config import Config
from app.services.corpus_campaign import (
    DEFAULT_CORPUS,
    JUDGED_CODES,
    run_campaign,
    to_entity,
)


def pct(value: Decimal | None) -> str:
    return "-" if value is None else f"{(value * 100).quantize(Decimal('0.1'))} %"


def open_repository():
    """The application's own database, or None when STORAGE is not sql."""
    config = Config()
    if config.storage != "sql":
        return None
    from app.infra.db.repositories import SqlEvaluationRepository  # noqa: PLC0415
    from app.infra.db.session import create_schema, make_engine, make_session_factory  # noqa: PLC0415

    engine = make_engine(config.database_url)
    create_schema(engine)  # creates the two new tables the first time
    return SqlEvaluationRepository(make_session_factory(engine)())


def main(argv: list[str]) -> int:
    # A Windows console may not know a character such as "≠" (CHK003 message):
    # print a "?" instead of crashing the whole campaign.
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description="Week 7 measurement campaign")
    parser.add_argument("corpus", nargs="?", help="corpus folder (default: data/corpus)")
    parser.add_argument("--note", help="a short note stored with the campaign")
    parser.add_argument("--author", help="who ran it (default: your Windows user name)")
    parser.add_argument("--json", action="store_true", help="also write a JSON file")
    args = parser.parse_args(argv[1:])

    corpus = Path(args.corpus or os.environ.get("CORPUS_DIR") or DEFAULT_CORPUS)
    print(f"Corpus: {corpus}")
    print(f"Items judged: {', '.join(JUDGED_CODES)}\n")
    campaign = run_campaign(corpus)

    for p in campaign.packages:
        print(f"=== {p.package}  ({', '.join(p.documents) or 'no document'})")
        for problem in p.annotation_problems:
            print(f"    annotation: {problem}")
        if p.status != "EVALUATED":
            print(f"    {p.status}: {p.reason}\n")
            continue
        print(f"    field accuracy   {p.judged_fields - len(p.wrong_fields)}/{p.judged_fields}"
              f" = {pct(p.field_accuracy)}")
        for w in p.wrong_fields:
            print(f"        {w['code']}: read {w['extracted'] or 'nothing'}, truth {w['truth']}")
        print(f"    ratio accuracy   {p.ratios - len(p.wrong_ratios)}/{p.ratios}"
              f" = {pct(p.ratio_accuracy)}")
        for w in p.wrong_ratios:
            print(f"        {w['code']}: got {w['extracted']['value'] or w['extracted']['status']},"
                  f" truth {w['truth']['value'] or w['truth']['status']}")
        print(f"    amplification    {p.amplification if p.amplification is not None else 'none (no wrong field)'}")
        print(f"    silent false +   {', '.join(p.silent_false_positives) or 'none'}")
        print(f"    checks failed    {', '.join(p.checks_failed_on_extraction) or 'none'}")
        other = p.other_lines
        if other.get("annotated"):
            print(f"    other lines      {other['identical']}/{other['annotated']} identical"
                  + (f" - different: {', '.join(d['code'] for d in other['different'])}"
                     if other["different"] else ""))
        print()

    s = campaign.summary()
    print("=== CORPUS")
    print(f"    packages         {s['packages']} found, {s['evaluated']} evaluated")
    for key, label in (("reference_rejected", "reference rejected"),
                       ("extraction_failed", "extraction failed"),
                       ("unreadable", "unreadable")):
        if s[key]:
            print(f"    {label}: {', '.join(s[key])}")
    print(f"    field accuracy   {s['fields_judged'] - s['fields_wrong']}/{s['fields_judged']}"
          f" = {pct(s['field_accuracy'])}")
    print(f"    ratio accuracy   {s['ratios_judged'] - s['ratios_wrong']}/{s['ratios_judged']}"
          f" = {pct(s['ratio_accuracy'])}")
    print(f"    amplification    {s['amplification'] if s['amplification'] is not None else 'none (no wrong field)'}")
    silent = s["silent_false_positives"]
    print(f"    silent false +   {len(silent)}"
          + (f" ({', '.join(x['package'] + ':' + x['code'] for x in silent)})" if silent else ""))
    print(f"    interception     {pct(s['interception_rate'])} of injected errors caught by the checks")
    print("    criticality      " + ", ".join(
        f"{code} {value.quantize(Decimal('0.0001'))}"
        for code, value in s["criticality"].items() if value > 0))

    entity = to_entity(campaign, author=args.author or getpass.getuser(), note=args.note)
    repository = open_repository()
    if repository is not None:
        repository.add(entity)
        print(f"\nStored in the database: evaluation_campaign {entity.id}")
    else:
        print("\nSTORAGE is not 'sql' in .env: nothing stored in the database,"
              " the campaign goes to a JSON file instead.")

    if args.json or repository is None:
        out_dir = corpus / "_results"
        out_dir.mkdir(exist_ok=True)
        out = out_dir / f"campaign_{entity.run_at.astimezone():%Y%m%d_%H%M%S}.json"
        out.write_text(json.dumps({
            "id": entity.id,
            "run_at": entity.run_at.isoformat(timespec="seconds"),
            "author": entity.author,
            "note": entity.note,
            "engine": entity.engine,
            "judged_codes": list(JUDGED_CODES),
            "inputs_sha256": entity.inputs,
            "summary": entity.summary,
            "packages": entity.packages,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))