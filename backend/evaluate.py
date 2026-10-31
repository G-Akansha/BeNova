"""
Evaluation (FR-08)

  python backend/evaluate.py            # offline, extractive (default)
  python backend/evaluate.py --with-llm # same suite, LLM rephrasing enabled (needs GROQ_API_KEY)

A case PASSES only if ALL hold:
  - status matches the label (GROUNDED / CONFLICT / CLARIFICATION / NOT_FOUND)
  - every expected fact appears in the answer (word-boundary match)
  - no number in the answer is missing from the cited passages (unsupported-number check)
  - for answerable cases, at least one citation comes from an expected source document

Also reports retrieval Hit@1/Hit@3/MRR against labelled relevant sections, and runs
robustness checks on a temporary copy of the corpus (changed values, removed document,
empty corpus, new uploads, bad upload, dishonest LLM output).

Writes EVALUATION_REPORT.md (project root) and backend/data/eval_results.json (shown in the UI).
"""

import argparse
import json
import re
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import llm_generator  # noqa: E402
from ingestion_and_retrieval import KnowledgeBaseIndex  # noqa: E402
from conflict_and_fallback import analyze_evidence_state  # noqa: E402
from llm_generator import generate_grounded_answer, GROQ_MODEL  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DATA_DIR = BACKEND_DIR / "data"
NUMBER = re.compile(r"(?<![\w.$/])\d[\d,]*(?:\.\d+)?%?(?![\w])")


def nums(text: str) -> set:
    return {n.replace(",", "") for n in NUMBER.findall(text)}


def fact_present(fact: str, text: str) -> bool:
    pat = re.escape(fact.lower())
    pat = (r"(?<![\w])" if fact[:1].isalnum() else "") + pat + (r"(?![\w])" if fact[-1:].isalnum() else "")
    return re.search(pat, text.lower()) is not None


def run_pipeline(kb: KnowledgeBaseIndex, question: str, filters: Optional[Dict[str, Any]], with_llm: bool):
    t0 = time.time()
    retrieved = kb.find_relevant_passages(question, top_k=8, filters=filters or None)
    ret_ms = (time.time() - t0) * 1000
    analysis = analyze_evidence_state(question, retrieved, kb.passages,
                                      (filters or {}).get("environment"), (filters or {}).get("version"))
    gen = generate_grounded_answer(question, analysis, kb.passages, allow_llm=with_llm)
    return retrieved, analysis, gen, ret_ms, (time.time() - t0) * 1000


def unsupported_numbers(gen, kb: KnowledgeBaseIndex, question: str) -> List[str]:
    """Numbers in fact sentences that do not occur in the cited passages (or their citation metadata)."""
    lookup = {p.passage_id: p for p in kb.passages}
    bad = []
    for seg in gen.segments:
        if seg.kind not in ("fact", "conflict"):
            continue
        support = " ".join(f"{lookup[i].text} {lookup[i].doc_title} {lookup[i].section_heading} "
                           f"{lookup[i].version} {lookup[i].environment}" for i in seg.citation_ids if i in lookup)
        bad += sorted(nums(seg.text) - nums(support) - nums(question))
    return bad


# ---------------------------------------------------------------------------
# Labelled suite
# ---------------------------------------------------------------------------

def evaluate_suite(kb: KnowledgeBaseIndex, cases: List[Dict[str, Any]], with_llm: bool) -> Dict[str, Any]:
    rows = []
    for case in cases:
        retrieved, analysis, gen, ret_ms, total_ms = run_pipeline(kb, case["question"], case.get("filters"), with_llm)
        exp_status = case["expected_status"]
        sources = case.get("expected_sources", [])
        sections = [s.lower() for s in case.get("relevant_sections", [])]

        def relevant(p):
            return p.source_filename in sources and (not sections or any(s in p.section_heading.lower() for s in sections))

        first_rel = next((i for i, p in enumerate(retrieved[:5], start=1) if relevant(p)), None)
        found_docs = {p.source_filename for p in retrieved[:5]}
        facts = case.get("expected_facts", [])
        hits = [f for f in facts if fact_present(f, gen.answer)]
        cited_docs = [c.source_filename for c in gen.citations]
        unsupported = unsupported_numbers(gen, kb, case["question"])

        checks = {
            "status": analysis.status == exp_status,
            "facts": len(hits) == len(facts),
            "no_unsupported_numbers": not unsupported,
            "cites_expected_source": (not sources) or exp_status not in ("GROUNDED_ANSWER", "CONFLICT_DETECTED")
                                     or any(d in sources for d in cited_docs),
        }
        if exp_status == "CONFLICT_DETECTED" and case.get("expected_conflict_type"):
            checks["conflict_type"] = any(c.conflict_type == case["expected_conflict_type"] for c in analysis.conflict_details)
        failed = [k for k, v in checks.items() if not v]
        rows.append({
            "id": case["id"], "name": case["name"], "question": case["question"], "filters": case.get("filters"),
            "expected_status": exp_status, "actual_status": analysis.status, "passed": not failed, "failed_checks": failed,
            "evidence_strength": analysis.confidence_score,
            "first_relevant_rank": first_rel if sources else None,
            "source_recall_at5": round(len(found_docs & set(sources)) / len(sources), 3) if sources else None,
            "fact_coverage": f"{len(hits)}/{len(facts)}", "missing_facts": [f for f in facts if f not in hits],
            "citation_precision": round(sum(d in sources for d in cited_docs) / len(cited_docs), 3) if (sources and cited_docs) else None,
            "unsupported_numbers": unsupported, "model_used": gen.model_used, "fallback_used": gen.fallback_used,
            "retrieval_ms": round(ret_ms, 2), "total_ms": round(total_ms, 2),
            "answer": gen.answer,
        })
        mark = "PASS" if not failed else f"FAIL ({', '.join(failed)})"
        print(f"[{case['id']}] {mark:<34} {analysis.status:<21} strength={analysis.confidence_score:<5} {case['name']}")
    return {"rows": rows, "metrics": aggregate(rows)}


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    ranked = [r for r in rows if r["first_relevant_rank"] is not None or (r["source_recall_at5"] is not None)]
    rr = [1.0 / r["first_relevant_rank"] if r["first_relevant_rank"] else 0.0 for r in ranked]

    def pr(label):
        tp = sum(r["expected_status"] == label and r["actual_status"] == label for r in rows)
        fp = sum(r["expected_status"] != label and r["actual_status"] == label for r in rows)
        fn = sum(r["expected_status"] == label and r["actual_status"] != label for r in rows)
        return {"precision": round(tp / (tp + fp), 3) if tp + fp else None,
                "recall": round(tp / (tp + fn), 3) if tp + fn else None, "support": tp + fn}

    cps = [r["citation_precision"] for r in rows if r["citation_precision"] is not None]
    lat = [r["total_ms"] for r in rows]
    return {
        "cases": len(rows), "passed": sum(r["passed"] for r in rows),
        "status_accuracy": round(sum(r["expected_status"] == r["actual_status"] for r in rows) / len(rows), 3),
        "hit_at_1": round(sum(r["first_relevant_rank"] == 1 for r in ranked) / len(ranked), 3) if ranked else None,
        "hit_at_3": round(sum((r["first_relevant_rank"] or 99) <= 3 for r in ranked) / len(ranked), 3) if ranked else None,
        "mrr": round(sum(rr) / len(rr), 3) if rr else None,
        "source_recall_at5": round(statistics.mean(r["source_recall_at5"] for r in ranked), 3) if ranked else None,
        "fact_coverage_cases_complete": f"{sum(not r['missing_facts'] for r in rows)}/{len(rows)}",
        "citation_precision": round(statistics.mean(cps), 3) if cps else None,
        "answers_with_unsupported_numbers": sum(bool(r["unsupported_numbers"]) for r in rows),
        "by_status": {s: pr(s) for s in ("GROUNDED_ANSWER", "CONFLICT_DETECTED", "CLARIFICATION_NEEDED", "NOT_FOUND")},
        "latency_ms": {"mean": round(statistics.mean(lat), 2), "p50": round(statistics.median(lat), 2),
                       "p95": round(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], 2)},
    }


# ---------------------------------------------------------------------------
# Robustness checks: answers must follow the documents when the documents change
# ---------------------------------------------------------------------------

def _temp_backend() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="docqa_eval_"))
    shutil.copytree(BACKEND_DIR / "docs_corpus", tmp / "docs_corpus")
    (tmp / "data").mkdir()
    shutil.copy(DATA_DIR / "document_manifest.json", tmp / "data" / "document_manifest.json")
    return tmp


def robustness_checks() -> List[Dict[str, Any]]:
    results = []

    def record(name, ok, detail):
        results.append({"check": name, "passed": bool(ok), "detail": detail})
        print(f"[ROBUST] {'PASS' if ok else 'FAIL'}  {name}  -- {detail}")

    q_terms = "What are the enterprise invoice payment terms?"

    # 1. Change a value in a seeded document -> answer must change with it.
    tmp = _temp_backend()
    html = tmp / "docs_corpus" / "02_Billing_And_Refund_Policy.html"
    html.write_text(html.read_text(encoding="utf-8").replace("net-45", "net-30").replace("45 calendar days", "30 calendar days"), encoding="utf-8")
    kb = KnowledgeBaseIndex(tmp); kb.build_index()
    _, a, g, *_ = run_pipeline(kb, q_terms, None, False)
    record("Edited document value (net-45 -> net-30) is reflected", "net-30" in g.answer and "net-45" not in g.answer,
           f"{a.status}; answer mentions net-30={'net-30' in g.answer}, net-45={'net-45' in g.answer}")
    shutil.rmtree(tmp, ignore_errors=True)

    # 2. Remove the legacy document -> the rate-limit conflict must disappear.
    tmp = _temp_backend()
    man = json.loads((tmp / "data" / "document_manifest.json").read_text())
    (tmp / "data" / "document_manifest.json").write_text(json.dumps([d for d in man if d["doc_id"] != "DOC-GW-LEGACY"]))
    kb = KnowledgeBaseIndex(tmp); kb.build_index()
    _, a, g, *_ = run_pipeline(kb, "What is the maximum API rate limit per minute?", None, False)
    record("Removing the legacy document removes the conflict", a.status == "GROUNDED_ANSWER" and "500" in g.answer and "100 requests" not in g.answer,
           f"status={a.status}")
    shutil.rmtree(tmp, ignore_errors=True)

    # 3. Empty corpus -> nothing can be answered or 'conflict'.
    tmp = Path(tempfile.mkdtemp(prefix="docqa_empty_")); (tmp / "data").mkdir(); (tmp / "docs_corpus").mkdir()
    (tmp / "data" / "document_manifest.json").write_text("[]")
    kb = KnowledgeBaseIndex(tmp); kb.build_index()
    _, a, g, *_ = run_pipeline(kb, "What is the API rate limit?", None, False)
    record("Empty corpus returns NOT_FOUND (no fabricated conflict)", a.status == "NOT_FOUND" and not g.citations, f"status={a.status}")
    shutil.rmtree(tmp, ignore_errors=True)

    # 4. Upload a document on a new topic -> previously unanswerable question becomes answerable.
    tmp = _temp_backend(); kb = KnowledgeBaseIndex(tmp); kb.build_index()
    q_pet = "What is the pet policy in the corporate office?"
    before = run_pipeline(kb, q_pet, None, False)[1].status
    kb.ingest_uploaded_file("Office_Pet_Policy.md", b"# Office Pet Policy\n\n## Dogs in the office\nWell-behaved dogs are permitted in the corporate office on Fridays.\n")
    _, a, g, *_ = run_pipeline(kb, q_pet, None, False)
    record("Uploaded pet policy makes the pet question answerable", before == "NOT_FOUND" and a.status == "GROUNDED_ANSWER" and "dogs" in g.answer.lower(),
           f"before={before}, after={a.status}")

    # 5. Upload a contradicting document with the same scope -> unresolved contradiction shown.
    kb.ingest_uploaded_file("Billing_Update.txt", b"Billing Update\n\n1. Payment Terms\nStandard payment terms for enterprise accounts are net-30 payment terms.\n",
                            version="v3.0", environment="Production", effective_date="2026-10-15")
    _, a, g, *_ = run_pipeline(kb, q_terms, None, False)
    types = [c.conflict_type for c in a.conflict_details]
    record("Same-scope contradicting upload is flagged, not silently resolved",
           a.status == "CONFLICT_DETECTED" and "UNRESOLVED_CONTRADICTION" in types and "net-30" in g.answer and "net-45" in g.answer, f"status={a.status}, types={types}")

    # 6. Invalid upload is rejected and leaves the corpus usable.
    n_before = len(kb.passages)
    try:
        kb.ingest_uploaded_file("broken.txt", b"\xff\xfe\x80 not utf8")
        rejected = False
    except ValueError:
        rejected = True
    kb.build_index()
    record("Invalid UTF-8 upload is rejected and the index still rebuilds", rejected and len(kb.passages) == n_before,
           f"rejected={rejected}, passages {n_before}->{len(kb.passages)}, file left behind={(tmp / 'docs_corpus' / 'broken.txt').exists()}")
    shutil.rmtree(tmp, ignore_errors=True)

    # 7. Dishonest LLM output is not accepted.
    kb = KnowledgeBaseIndex(); kb.build_index()
    original_call, original_key = llm_generator.call_groq_api, llm_generator.GROQ_API_KEY
    try:
        llm_generator.GROQ_API_KEY = "test"
        llm_generator.call_groq_api = lambda *a, **k: ('{"answer":[{"text":"Invoice payment is free forever.","source_ids":["NONEXISTENT"]}]}', None)
        _, a, g, *_ = run_pipeline(kb, q_terms, None, True)
        ok1 = g.fallback_used and "free forever" not in g.answer
        llm_generator.call_groq_api = lambda *a, **k: ('{"answer":[{"text":"Payment terms are net-90.","source_ids":["DOC-BILL-S02-C01"]}]}', None)
        _, a, g2, *_ = run_pipeline(kb, q_terms, None, True)
        ok2 = g2.fallback_used and "net-90" not in g2.answer
    finally:
        llm_generator.call_groq_api, llm_generator.GROQ_API_KEY = original_call, original_key
    record("LLM sentence with unknown source id is rejected", ok1, f"fallback_used={g.fallback_used}")
    record("LLM sentence with a number not in the cited passage is rejected", ok2, f"fallback_used={g2.fallback_used}")
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def write_report(res: Dict[str, Any], path: Path):
    m, rows, rob = res["metrics"], res["rows"], res["robustness"]
    L = [
        "# Evaluation Report - Enterprise Documentation Q&A Assistant", "",
        f"Generated: {res['generated_at']}  ",
        f"Answer mode: {res['mode']}  ",
        f"Corpus: {res['corpus']['documents']} documents, {res['corpus']['passages']} passages  ",
        f"Result: **{m['passed']}/{m['cases']} labelled cases pass all checks**, "
        f"{sum(r['passed'] for r in rob)}/{len(rob)} robustness checks pass.", "",
        "> All documents are synthetic, written for this hackathon. Test questions and relevance labels were written by the team "
        "(see `_labelling_notes` in `backend/data/test_questions.json`).", "",
        "## 1. Method", "",
        "A case passes only if **all** of these hold: correct status; every expected fact is in the answer; "
        "no number in the answer is missing from its cited passage; at least one citation is from an expected source. "
        "Retrieval is scored against labelled relevant *sections*, not just files.", "",
        "## 2. Aggregate metrics", "",
        "| Metric | Value |", "| :-- | :-- |",
        f"| Cases passing all checks | {m['passed']}/{m['cases']} |",
        f"| Status accuracy | {pct(m['status_accuracy'])} |",
        f"| Retrieval Hit@1 / Hit@3 (relevant section) | {pct(m['hit_at_1'])} / {pct(m['hit_at_3'])} |",
        f"| MRR | {m['mrr']} |",
        f"| Source-document recall@5 | {pct(m['source_recall_at5'])} |",
        f"| Cases with all expected facts | {m['fact_coverage_cases_complete']} |",
        f"| Citation precision (cited docs that are expected docs) | {pct(m['citation_precision'])} |",
        f"| Answers containing an unsupported number | {m['answers_with_unsupported_numbers']} |",
        f"| Latency mean / p50 / p95 | {m['latency_ms']['mean']} / {m['latency_ms']['p50']} / {m['latency_ms']['p95']} ms |", "",
        "| Status | Precision | Recall | Cases |", "| :-- | :-- | :-- | :-- |",
    ]
    for s, v in m["by_status"].items():
        L.append(f"| {s} | {pct(v['precision'])} | {pct(v['recall'])} | {v['support']} |")
    L += ["", "## 3. Per-case results", "",
          "| ID | Scenario | Expected | Actual | Facts | 1st relevant rank | Result |", "| :-- | :-- | :-- | :-- | :-- | :-- | :-- |"]
    for r in rows:
        L.append(f"| {r['id']} | {r['name']} | {r['expected_status']} | {r['actual_status']} | {r['fact_coverage']} | "
                 f"{r['first_relevant_rank'] or '-'} | {'PASS' if r['passed'] else 'FAIL: ' + ', '.join(r['failed_checks'])} |")
    L += ["", "## 4. Robustness checks (corpus changed at test time)", "", "| Check | Result | Detail |", "| :-- | :-- | :-- |"]
    for r in rob:
        L.append(f"| {r['check']} | {'PASS' if r['passed'] else 'FAIL'} | {r['detail']} |")
    fails = [r for r in rows if not r["passed"]]
    L += ["", "## 5. Failure cases", ""]
    if not fails:
        L.append("None in this run.")
    for r in fails:
        L += [f"### {r['id']} - {r['name']}", f"- Question: *{r['question']}*",
              f"- Expected {r['expected_status']}, got {r['actual_status']}; failed checks: {', '.join(r['failed_checks'])}",
              f"- Missing facts: {r['missing_facts'] or 'none'}; unsupported numbers: {r['unsupported_numbers'] or 'none'}",
              "- Answer given:", "", "```", r["answer"][:700], "```", ""]
    L += ["## 6. Demo examples (actual output)", ""]
    for r in rows:
        if r["id"] in ("DEMO-Q01", "DEMO-Q02", "DEMO-Q03", "DEMO-Q06"):
            L += [f"**{r['id']} - {r['name']}** ({r['actual_status']})", "", "```", r["answer"][:900], "```", ""]
    L += ["## 7. Limitations", "",
          "1. Retrieval and evidence selection are lexical (TF-IDF + BM25 + a small synonym list). Paraphrases with no shared "
          "vocabulary (e.g. 'out of sync' vs 'drifts more than 180 seconds') can be missed; the system then says NOT_FOUND rather than guessing.",
          "2. Conflict detection compares numbers in the best line from each document. Contradictions without numbers "
          "(e.g. 'refunds are issued' vs 'not issued') are not detected.",
          "3. The extractive answer quotes lines verbatim; it can include an extra neighbouring line. The optional LLM mode rephrases, "
          "but every sentence is validated against the cited passage (ids and numbers).",
          "4. Evidence strength is key-term coverage, not a calibrated probability.",
          "5. Scanned PDFs (no text layer) are rejected; OCR is out of scope. Single process / single worker only.",
          "", "## 8. Reproduce", "", "```bash", "python backend/seed_docs.py", "python backend/evaluate.py", "```"]
    path.write_text("\n".join(L), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-llm", action="store_true")
    ap.add_argument("--offline", action="store_true", help="(default) extractive mode, no network")
    args = ap.parse_args()
    with_llm = args.with_llm and not args.offline

    suite = json.loads((DATA_DIR / "test_questions.json").read_text(encoding="utf-8"))
    cases = suite.get("demo_scenarios", []) + suite.get("additional_evaluation_queries", [])
    kb = KnowledgeBaseIndex(); kb.build_index()
    print(f"Evaluating {len(cases)} cases on {len(kb.passages)} passages ({'LLM' if with_llm else 'extractive'})\n")
    res = evaluate_suite(kb, cases, with_llm)
    print()
    res["robustness"] = robustness_checks()
    res["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    res["mode"] = f"LLM rephrasing ({GROQ_MODEL}) + validation" if with_llm else "Extractive (offline, no LLM)"
    res["corpus"] = {"documents": len(kb.read_manifest()), "passages": len(kb.passages)}

    (DATA_DIR / "eval_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    write_report(res, BACKEND_DIR.parent / "EVALUATION_REPORT.md")
    m = res["metrics"]
    print(f"\n{m['passed']}/{m['cases']} cases pass | Hit@1 {pct(m['hit_at_1'])} | MRR {m['mrr']} | "
          f"robustness {sum(r['passed'] for r in res['robustness'])}/{len(res['robustness'])}")
    print("Wrote EVALUATION_REPORT.md and backend/data/eval_results.json")


if __name__ == "__main__":
    main()
