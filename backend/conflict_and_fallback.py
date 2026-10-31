"""
Evidence Analysis, Conflict Handling and Fallback (FR-04 support, FR-06, FR-07)

Everything here is derived from the passages that are actually indexed - there are no
topic templates, hard-coded values or hard-coded document names.

Pipeline for one question:
  1. Split multi-part questions ("... and how many ...") into parts.
  2. For each part, pick the exact lines/sentences from retrieved passages that cover the
     part's key terms (IDF-weighted, synonyms allowed). Coverage < threshold => part not found.
  3. No part covered                          -> NOT_FOUND (lists the key terms that are missing)
     Under-specified question in >=2 documents -> CLARIFICATION_NEEDED (options = real sections)
     Two documents answer the same part with different numbers -> CONFLICT_DETECTED
     Otherwise                                -> GROUNDED_ANSWER (uncovered parts flagged as partial)
"""

import math
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ingestion_and_retrieval import (  # noqa: E402
    Passage, ScoredPassage, STOP_WORDS, GENERIC_TERMS, raw_tokens, stem, index_tokens,
    expand_query, scope_values, LIST_MARKER,
)

COVERAGE_THRESHOLD = 0.6     # share of (IDF-weighted) key terms a passage line must cover
MAX_UNITS_PER_PART = 6

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EvidenceUnit(BaseModel):
    text: str
    passage_id: str


class AnswerPart(BaseModel):
    question_part: str
    covered: bool
    coverage: float
    missing_terms: List[str]
    units: List[EvidenceUnit]
    primary: Optional[EvidenceUnit] = None      # the single best line (used for conflict comparison)


class ConflictDetail(BaseModel):
    conflict_type: str           # VERSION_ENVIRONMENT_VARIANCE | UNRESOLVED_CONTRADICTION
    topic: str                   # the question part the documents disagree on
    description: str
    competing_passages: List[Dict[str, Any]]


class ScopeOption(BaseModel):
    label: str
    environment: Optional[str] = None
    version: Optional[str] = None
    doc_id: Optional[str] = None


class ClarificationChoice(BaseModel):
    label: str
    question: str          # refined question to send when the user picks this option
    doc_id: str            # restrict the follow-up to this document


class EvidenceAnalysisResult(BaseModel):
    status: str                  # GROUNDED_ANSWER | CONFLICT_DETECTED | CLARIFICATION_NEEDED | NOT_FOUND
    confidence_score: float      # "evidence strength": weighted key-term coverage, NOT a probability
    confidence_band: str         # HIGH | MEDIUM | LOW
    detected_topics: List[str]   # key terms of the question (kept under the old field name)
    conflict_details: List[ConflictDetail]
    clarification_options: List[str]
    explanation: str
    supporting_passage_ids: List[str]
    answer_parts: List[AnswerPart] = []
    scope_options: List[ScopeOption] = []
    clarification_choices: List[ClarificationChoice] = []
    applied_scope_terms: List[str] = []


# ---------------------------------------------------------------------------
# Question handling
# ---------------------------------------------------------------------------

QWORDS = r"(?:how|what|when|where|which|who|why|is|are|do|does|can|should)"


def split_question(q: str) -> List[str]:
    """Split on ' and <question word>' / '?' / ';' so each part can be checked independently."""
    q = q.strip()
    pieces = re.split(rf"\?\s+|;\s+|,?\s+and\s+(?={QWORDS}\b)|,?\s+also\s+(?={QWORDS}\b)", q, flags=re.I)
    parts: List[str] = []
    for piece in pieces:
        piece = (piece or "").strip(" ?.")
        m = re.match(r"^(.*\S)\s+and\s+(\S.*)$", piece, flags=re.I)
        if (m and not m.group(2)[0].isupper() and len(key_terms(m.group(1))) >= 2
                and len(key_terms(m.group(2))) >= 1 and len(raw_tokens(m.group(2))) >= 2):
            parts += [m.group(1), m.group(2)]
        elif len(raw_tokens(piece)) >= 2:
            parts.append(piece)
    return parts or [q.strip(" ?.")]


def is_explanatory(part: str) -> bool:
    """'How do I reset..', 'How is X configured', 'steps to..' -> answer with the whole best section."""
    p = part.lower().strip()
    if re.match(r"^how\s+(many|much|long|often|old|far|large|big|soon)\b", p):
        return False
    return bool(re.match(r"^how\b", p) or re.search(r"\b(steps?|procedure|process|explain|describe|configure[ds]?|troubleshoot|fix|resolve|reset)\b", p))


QUANTITY_HINT = re.compile(r"\b(limit|size|maximum|minimum|max|min|how many|how much|how often|how long|rate|"
                           r"timeout|duration|when|threshold|terms|number|count|version|date|days?|hours?|minutes?|"
                           r"percent|price|cost|fee|quota|retention|interval)\b", re.I)


def context_clause_terms(part: str) -> Set[str]:
    """Terms in a trailing 'if/because/so that ...' clause describe the situation, not the ask."""
    m = re.search(r"\s(if|because|since|so that|while|in case)\s(.+)$", part, flags=re.I)
    if not m:
        return set()
    main_terms = set(key_terms(part[: m.start()]))
    return {t for t in key_terms(m.group(2)) if t not in main_terms}


def key_terms(text: str) -> List[str]:
    seen, out = set(), []
    for t in raw_tokens(text):
        if t in STOP_WORDS or t in GENERIC_TERMS or len(t) < 2:
            continue
        s = stem(t)
        if s in GENERIC_TERMS or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# Units (lines / sentences) and scoring
# ---------------------------------------------------------------------------

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'`])")


def passage_units(p: Passage) -> List[Dict[str, Any]]:
    units = []
    for line in p.text.split("\n"):
        line = line.strip()
        if not line:
            continue
        is_item = bool(LIST_MARKER.match(line))
        sentences = [line] if is_item else SENTENCE_SPLIT.split(line)
        for s in sentences:
            s = s.strip()
            if len(s) < 3 or s.lower() == p.doc_title.lower() or re.search(r"\bdocument id\s*:", s, re.I):
                continue      # titles / metadata banners are not evidence
            display = re.sub(r"^\s*[-*•]\s+", "", s)
            units.append({"text": display, "tokens": set(index_tokens(display)), "is_item": is_item,
                          "passage": p})
    return units


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


class TermScorer:
    def __init__(self, terms: List[str], alt_map: Dict[str, Set[str]], idf: Dict[str, float], max_idf: float,
                 context_terms: Optional[Set[str]] = None):
        self.terms = terms
        # a synonym may not be another word of the same question ("minute" must not satisfy "rate")
        self.alts = {t: alt_map.get(t, set()) - set(terms) for t in terms}
        ctx = context_terms or set()
        # unseen term => rarest => weighs most; terms from an "if/when ..." clause are context, half weight
        self.w = {t: idf.get(t, max_idf) * (0.5 if t in ctx else 1.0) for t in terms}
        self.total = sum(self.w.values()) or 1.0

    @staticmethod
    def _has(t: str, tokens: Set[str]) -> bool:
        if t in tokens:
            return True
        # tolerate inflection: rotate~rotation, configured~configuration (shared prefix >= 5 chars)
        return len(t) >= 5 and any(len(x) >= 5 and _common_prefix(t, x) >= max(5, int(0.75 * min(len(t), len(x))))
                                   for x in tokens)

    def presence(self, t: str, tokens: Set[str], heading: Set[str]) -> float:
        if self._has(t, tokens):
            return 1.0
        if any(self._has(a, tokens) for a in self.alts[t]):
            return 0.8
        if self._has(t, heading) or any(self._has(a, heading) for a in self.alts[t]):
            return 0.5        # the section is about it, the line itself does not say it
        return 0.0

    def unit_vector(self, unit, heading_tokens: Set[str]) -> Dict[str, float]:
        return {t: self.presence(t, unit["tokens"], heading_tokens) for t in self.terms}

    def coverage(self, vec: Dict[str, float]) -> float:
        return sum(self.w[t] * v for t, v in vec.items()) / self.total

    def missing(self, vec: Dict[str, float]) -> List[str]:
        return [t for t in self.terms if vec.get(t, 0) < 0.5]

    def is_covered(self, vec: Dict[str, float]) -> bool:
        """Weighted coverage AND at least half of the key terms actually present (stops one rare
        incidental word, e.g. 'minute', from making an unrelated line look like an answer)."""
        present = sum(1 for t in self.terms if vec.get(t, 0) >= 0.5)
        return self.coverage(vec) >= COVERAGE_THRESHOLD and present * 2 >= len(self.terms)


def corpus_idf(all_passages: List[Passage]) -> Tuple[Dict[str, float], float]:
    n = len(all_passages)
    df: Dict[str, int] = {}
    for p in all_passages:
        for t in set(index_tokens(f"{p.section_heading} {p.text}")):
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
    return idf, math.log(n + 1) + 1


# ---------------------------------------------------------------------------
# Scope words mentioned in the question ("legacy", "staging", "v2.4" ...)
# ---------------------------------------------------------------------------

def _scope_tokens(p: Passage) -> Set[str]:
    out = set()
    for value in scope_values(p.environment) + scope_values(p.version):
        if value in ("all", "unknown"):
            continue
        out.add(value)
        out.update(x for x in re.split(r"[-\s]+", value) if len(x) >= 2 and x not in ("all", "unknown"))
    return out


def mentioned_scope_terms(question: str, passages: List[Passage]) -> Set[str]:
    vocab = set().union(*(_scope_tokens(p) for p in passages)) if passages else set()
    q = question.lower()
    return {v for v in vocab if re.search(rf"(?<![\w.]){re.escape(v)}(?![\w])", q)}


def in_scope(p: Passage, mentioned: Set[str]) -> bool:
    if not mentioned:
        return True
    envs = scope_values(p.environment)
    return "all" in envs or bool(_scope_tokens(p) & mentioned)


# ---------------------------------------------------------------------------
# Evidence selection for one question part
# ---------------------------------------------------------------------------

def _label_tokens(text: str) -> Set[str]:
    label = re.sub(r"^\s*\d+[.)]\s*", "", text).split(":", 1)
    if len(label) < 2 or len(label[0].split()) > 6:
        return set()
    return {t for t in index_tokens(re.sub(r"[\d%$.,]+", " ", label[0])) if len(t) > 2}


def _mentions_other_scope(text: str, vocab: Set[str], mentioned: Set[str]) -> bool:
    """Line explicitly names a different environment/version than the one the user asked about."""
    if not mentioned:
        return False
    low = text.lower()
    named = {v for v in vocab if re.search(rf"(?<![\w.]){re.escape(v)}(?![\w])", low)}
    return bool(named) and not (named & mentioned)


def select_evidence(part: str, passages: List[ScoredPassage], idf, max_idf,
                    scope_vocab: Optional[Set[str]] = None, mentioned: Optional[Set[str]] = None) -> AnswerPart:
    terms = key_terms(part)
    if not terms or not passages:
        return AnswerPart(question_part=part, covered=False, coverage=0.0, missing_terms=terms, units=[])
    _, alt_map = expand_query(part)
    sc = TermScorer(terms, alt_map, idf, max_idf, context_clause_terms(part))
    wants_value = bool(QUANTITY_HINT.search(part)) and not is_explanatory(part)
    vocab, mentioned = scope_vocab or set(), mentioned or set()

    scored = []   # (unit, vector, standalone coverage, heading agreement)
    for p in passages:
        heading = set(index_tokens(f"{p.doc_title} {p.section_heading}"))
        for u in passage_units(p):
            if _mentions_other_scope(u["text"], vocab, mentioned):
                continue
            vec = sc.unit_vector(u, heading)
            in_head = sum(1 for t in terms if vec[t] == 1.0 and sc._has(t, heading))
            scored.append((u, vec, sc.coverage(vec), in_head))

    chosen: List[Tuple[dict, dict, float]] = []
    primary_row = None
    if is_explanatory(part):
        # Best whole section: coverage of all its lines together.
        best_pid, best_cov = None, -1.0
        for p in passages:
            rows = [r for r in scored if r[0]["passage"].passage_id == p.passage_id]
            vec = {t: max((r[1][t] for r in rows), default=0.0) for t in terms}
            cov = sc.coverage(vec)
            if cov > best_cov + 1e-9:
                best_pid, best_cov = p.passage_id, cov
        rows = [r for r in scored if r[0]["passage"].passage_id == best_pid]
        if len(rows) > MAX_UNITS_PER_PART:     # keep the most relevant lines, in document order
            keep = sorted(rows, key=lambda r: -r[2])[:MAX_UNITS_PER_PART]
            rows = [r for r in rows if r in keep]
        chosen = rows
    else:
        # Greedy set cover: each extra line must add a key term the answer does not have yet,
        # and must itself be reasonably on-topic (no lines that match one stray word).
        current = {t: 0.0 for t in terms}
        for _ in range(3):
            best, gain = None, 0.0
            for row in scored:
                if row in chosen:
                    continue
                if chosen:
                    same_doc = row[0]["passage"].doc_id == chosen[0][0]["passage"].doc_id
                    # a 2nd document is only cited if it answers well on its own
                    if row[2] < (0.6 * chosen[0][2] if same_doc else COVERAGE_THRESHOLD):
                        continue
                g = sum(sc.w[t] * max(0.0, row[1][t] - current[t]) for t in terms) / sc.total
                if wants_value and not chosen and numbers_in(row[0]["text"]):
                    g += 0.25                                  # "what is the limit" -> prefer the line with the value
                g += 0.01 * row[2] + 0.005 * row[3]          # tie-breaks: relevance, heading agreement
                if g > gain + 1e-9:
                    best, gain = row, g
            if best is None or (chosen and gain < 0.15):
                break
            chosen.append(best)
            current = {t: max(current[t], best[1][t]) for t in terms}
        primary_row = chosen[0] if chosen else None
        if chosen:
            top = chosen[0]
            pid = top[0]["passage"].passage_id
            same = [r for r in scored if r[0]["passage"].passage_id == pid and r not in chosen]
            # near-ties in the same passage (two sentences saying the relevant thing)
            extra = [r for r in same if r[2] >= 0.85 * top[2]]
            # parallel list items with the same kind of label (80%/90%/100% Threshold ...)
            if top[0]["is_item"]:
                lab = _label_tokens(top[0]["text"])
                extra += [r for r in same if r[0]["is_item"] and r not in extra and lab & _label_tokens(r[0]["text"])]
            chosen.extend(extra[: MAX_UNITS_PER_PART - len(chosen)])
            order = {id(r[0]): i for i, r in enumerate(scored)}
            chosen.sort(key=lambda r: order[id(r[0])])            # read in document order

    vec = {t: max((r[1][t] for r in chosen), default=0.0) for t in terms}
    cov = round(sc.coverage(vec), 3)
    covered = sc.is_covered(vec)
    units = [EvidenceUnit(text=r[0]["text"], passage_id=r[0]["passage"].passage_id) for r in chosen] if covered else []
    primary = None
    if covered and chosen:
        top = primary_row if primary_row is not None else chosen[0]
        primary = EvidenceUnit(text=top[0]["text"], passage_id=top[0]["passage"].passage_id)
    return AnswerPart(question_part=part, covered=covered, coverage=cov, missing_terms=sc.missing(vec),
                      units=units, primary=primary)


# ---------------------------------------------------------------------------
# Conflict detection (FR-06)
# ---------------------------------------------------------------------------

NUMBER = re.compile(r"(?<![\w.$/])\d[\d,]*(?:\.\d+)?%?(?![\w])")


def numbers_in(text: str) -> Set[str]:
    return {n.replace(",", "") for n in NUMBER.findall(text)}


def _known(v: str) -> bool:
    return bool(v) and v.strip().lower() not in ("unknown", "")


def _scope_label(p: Passage) -> str:
    bits = [f"Version {p.version}" if _known(p.version) else "version unknown",
            f"Scope {p.environment}" if _known(p.environment) else "scope unknown"]
    return " | ".join(bits)


def detect_conflicts(part: str, passages: List[ScoredPassage], idf, max_idf,
                     vocab: Optional[Set[str]] = None, mentioned: Optional[Set[str]] = None) -> Optional[ConflictDetail]:
    """Answer the part separately from each document. If two or more documents answer it and
    their best lines carry different numbers, the conflict is reported (never silently resolved)."""
    by_doc: Dict[str, List[ScoredPassage]] = {}
    for p in passages:
        by_doc.setdefault(p.doc_id, []).append(p)
    if len(by_doc) < 2:
        return None

    answers = []   # (passage meta, AnswerPart)
    for doc_id, doc_passages in by_doc.items():
        ap = select_evidence(part, doc_passages, idf, max_idf, vocab, mentioned)
        if ap.covered and ap.primary and numbers_in(ap.primary.text):
            meta = next(p for p in doc_passages if p.passage_id == ap.primary.passage_id)
            answers.append((meta, ap))
    if len(answers) < 2 or len({frozenset(numbers_in(ap.primary.text)) for _, ap in answers}) < 2:
        return None                                   # one answer, or all documents agree

    answers.sort(key=lambda x: -x[1].coverage)
    competing = []
    for meta, ap in answers:
        lines = [ap.primary] + [u for u in ap.units if u != ap.primary and numbers_in(u.text)][:1]
        competing.append({
            "passage_id": ap.primary.passage_id,
            "passage_ids": list(dict.fromkeys(u.passage_id for u in lines)),
            "doc_id": meta.doc_id,
            "doc_title": meta.doc_title,
            "source_filename": meta.source_filename,
            "section_heading": meta.section_heading,
            "version": meta.version,
            "environment": meta.environment,
            "effective_date": meta.effective_date,
            "value": " ".join(u.text for u in lines),
            "lines": [{"text": u.text, "passage_id": u.passage_id} for u in lines],
            "scope_type": _scope_label(meta),
        })
    metas = [m for m, _ in answers]

    def scope_key(p):
        return (p.version.strip().lower(), p.environment.strip().lower())

    all_known = all(_known(p.version) or _known(p.environment) for p in metas)
    distinct_scopes = len({scope_key(p) for p in metas}) == len(metas)
    if all_known and distinct_scopes:
        ctype = "VERSION_ENVIRONMENT_VARIANCE"
        desc = ("The documents give different values for this, and each applies to a different "
                "version/environment. All are shown; choose the scope that applies to you.")
    else:
        ctype = "UNRESOLVED_CONTRADICTION"
        dated = [p for p in metas if _known(p.effective_date)]
        newest = max(dated, key=lambda p: p.effective_date) if len(dated) == len(metas) else None
        desc = ("Potential contradiction: documents with the same or unknown scope give different values. "
                "The assistant does not pick one.")
        if newest:
            desc += f" Most recent effective date: {newest.effective_date} ({newest.doc_title}) - confirm with the document owner."
    return ConflictDetail(conflict_type=ctype, topic=part, description=desc, competing_passages=competing)


def scope_options_for(conflicts: List[ConflictDetail], all_passages: List[Passage]) -> List[ScopeOption]:
    opts, seen = [], set()
    for c in conflicts:
        for comp in c.competing_passages:
            envs = [e for e in (comp["environment"] or "").split(",") if _known(e) and e.strip().lower() != "all"]
            if c.conflict_type != "VERSION_ENVIRONMENT_VARIANCE":
                envs = []                    # same scope: the only meaningful choice is the document itself
                if comp["doc_id"] not in seen:
                    seen.add(comp["doc_id"])
                    opts.append(ScopeOption(label=f"Only '{comp['doc_title']}'", doc_id=comp["doc_id"]))
                continue
            if envs:
                for e in envs:
                    e = e.strip()
                    if e.lower() not in seen:
                        seen.add(e.lower())
                        opts.append(ScopeOption(label=f"Only {e}", environment=e))
            elif _known(comp["version"]):
                if comp["version"].lower() not in seen:
                    seen.add(comp["version"].lower())
                    opts.append(ScopeOption(label=f"Only version {comp['version']}", version=comp["version"]))
            elif comp["doc_id"] not in seen:
                seen.add(comp["doc_id"])
                opts.append(ScopeOption(label=f"Only '{comp['doc_title']}'", doc_id=comp["doc_id"]))
    return opts


# ---------------------------------------------------------------------------
# Clarification (FR-07)
# ---------------------------------------------------------------------------

def clean_heading(h: str) -> str:
    last = h.split(" > ")[-1]
    return re.sub(r"^\d+[.)]\s*", "", last).strip()


def clarification_for(question: str, passages: List[ScoredPassage]) -> Optional[List["ClarificationChoice"]]:
    """Question with at most one key term that matches sections in two or more documents.
    Options are the real matching sections (heading matches first, max 2 per document)."""
    terms = key_terms(question)
    if len(terms) != 1:
        return None
    term = terms[0]
    _, alt_map = expand_query(question)
    accept = {term} | alt_map.get(term, set())
    head_hits, text_hits = [], []
    for p in passages:
        if accept & set(index_tokens(p.section_heading)):
            head_hits.append(p)
        elif accept & set(index_tokens(p.text)):
            text_hits.append(p)
    picked, per_doc, seen = [], {}, set()
    for p in head_hits + text_hits:
        key = (p.doc_id, clean_heading(p.section_heading))
        if key in seen or per_doc.get(p.doc_id, 0) >= 2:
            continue
        seen.add(key)
        per_doc[p.doc_id] = per_doc.get(p.doc_id, 0) + 1
        picked.append(p)
    if len(per_doc) < 2:
        return None
    base = question.strip().rstrip("?")
    return [ClarificationChoice(
        label=f"{clean_heading(p.section_heading)} ({p.doc_title})",
        question=f"{base} for {clean_heading(p.section_heading)}?",
        doc_id=p.doc_id,
    ) for p in picked[:4]]


# ---------------------------------------------------------------------------
# Master entrypoint
# ---------------------------------------------------------------------------

def _band(score: float) -> str:
    return "HIGH" if score >= 0.8 else "MEDIUM" if score >= 0.6 else "LOW"


def _result(status, score, terms, explanation, **kw) -> EvidenceAnalysisResult:
    return EvidenceAnalysisResult(
        status=status, confidence_score=round(score, 3), confidence_band=_band(score),
        detected_topics=terms, conflict_details=kw.get("conflicts", []),
        clarification_options=kw.get("options", []), explanation=explanation,
        supporting_passage_ids=kw.get("support", []), answer_parts=kw.get("parts", []),
        scope_options=kw.get("scope_options", []), applied_scope_terms=kw.get("scope_terms", []),
        clarification_choices=kw.get("choices", []),
    )


def analyze_evidence_state(query: str, ranked_passages: List[ScoredPassage], all_passages: List[Passage],
                           environment: Optional[str] = None, version: Optional[str] = None) -> EvidenceAnalysisResult:
    q = (query or "").strip()
    terms = key_terms(q)
    if not q:
        return _result("NOT_FOUND", 0.0, [], "The question was empty.")
    if not ranked_passages:
        return _result("NOT_FOUND", 0.0, terms,
                       "No passage in the selected documents matches this question. "
                       "Try different wording or remove filters.")

    # Ambiguity first: a one-word question that matches several documents.
    choices = clarification_for(q, ranked_passages)
    if choices:
        return _result("CLARIFICATION_NEEDED", 0.3, terms,
                       f"'{q}' matches several unrelated sections. Which one do you mean?",
                       options=[c.label for c in choices], choices=choices)

    # Scope words in the question ("legacy", "staging") narrow the evidence, if anything remains.
    scope_terms = mentioned_scope_terms(q, all_passages)
    scoped = [p for p in ranked_passages if in_scope(p, scope_terms)] or ranked_passages

    idf, max_idf = corpus_idf(all_passages)
    vocab = set().union(*(_scope_tokens(p) for p in all_passages)) if all_passages else set()
    parts = [select_evidence(part, scoped, idf, max_idf, vocab, scope_terms) for part in split_question(q)]
    covered = [p for p in parts if p.covered]
    strength = sum(p.coverage for p in parts) / len(parts)

    if not covered:
        missing = sorted({t for p in parts for t in p.missing_terms})
        return _result("NOT_FOUND", min(strength, 0.3), terms,
                       "The documents do not contain an answer to this question"
                       + (f" (the closest passages do not mention: {', '.join(missing[:6])})." if missing else "."),
                       parts=parts, scope_terms=sorted(scope_terms))

    # Conflict check runs on the filtered/scoped evidence, so a pinned scope naturally removes variance.
    conflicts: List[ConflictDetail] = []
    for part in covered:
        c = detect_conflicts(part.question_part, scoped, idf, max_idf, vocab, scope_terms)
        if c:
            conflicts.append(c)

    support = []
    for p in covered:
        support += [u.passage_id for u in p.units]
    for c in conflicts:
        for comp in c.competing_passages:
            support += comp["passage_ids"]
    support = list(dict.fromkeys(support))

    if conflicts:
        return _result("CONFLICT_DETECTED", strength, terms,
                       "Documents disagree on part of this question; all versions are shown.",
                       conflicts=conflicts, parts=parts, support=support,
                       scope_options=scope_options_for(conflicts, all_passages), scope_terms=sorted(scope_terms))

    note = "Answered from the cited passages."
    if len(covered) < len(parts):
        note = "Partially answered: some parts of the question are not covered by the documents."
    elif strength < 0.7:
        note = "Weak evidence: the cited lines only partly match the question. Check the sources."
    return _result("GROUNDED_ANSWER", strength, terms, note, parts=parts, support=support,
                   scope_terms=sorted(scope_terms))
