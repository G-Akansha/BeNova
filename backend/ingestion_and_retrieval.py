"""
Document Ingestion and Hybrid Retrieval (FR-01, FR-02, FR-03)

- Multi-format parsers (MD, HTML, TXT, PDF) that keep headings, list items and table cells.
- Sentence/line-aware chunking (passages keep their line structure so answers can quote exact lines).
- Hybrid lexical retrieval: TF-IDF (1,2-gram) + BM25Okapi fused with Reciprocal Rank Fusion.
  * Filters are applied BEFORE ranking.
  * Candidates with zero lexical evidence are dropped (RRF never invents relevance).
- Index rebuilds build a complete new snapshot and swap it in one assignment, so a request
  never sees a half-built index. Uploads are transactional (parse first, commit after).
"""

import io
import os
import re
import json
import uuid
import threading
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from rank_bm25 import BM25Okapi
import pypdf

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
EXT_TO_FORMAT = {".md": "MD", ".markdown": "MD", ".html": "HTML", ".htm": "HTML", ".txt": "TXT", ".pdf": "PDF"}

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class Passage(BaseModel):
    passage_id: str
    doc_id: str
    doc_title: str
    source_filename: str
    doc_format: str
    section_heading: str
    page_number: Optional[int] = None
    version: str
    effective_date: str
    environment: str
    text: str
    word_count: int = 0


class ScoredPassage(Passage):
    rank: int
    tfidf_similarity: float
    bm25_score: float
    rrf_score: float
    matched_terms: List[str]


# ---------------------------------------------------------------------------
# Text normalisation shared by retrieval and evidence extraction
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "the", "what", "is", "are", "and", "or", "to", "for", "in", "on", "at", "by", "of", "how",
    "do", "does", "did", "if", "can", "an", "a", "my", "me", "i", "we", "our", "you", "your",
    "they", "their", "this", "that", "with", "from", "as", "be", "was", "were", "been", "has",
    "have", "had", "will", "would", "should", "could", "any", "all", "so", "it", "its", "there",
    "which", "who", "whom", "when", "where", "why", "than", "then", "into", "about", "per",
    "not", "no", "cannot", "get", "got", "tell", "please", "many", "much", "often", "long",
    "us", "there", "these", "those", "some", "also", "via", "after", "before", "under", "over",
}

# Words that appear in almost every question about this corpus and say nothing about WHAT is asked.
GENERIC_TERMS = {
    "policy", "policies", "company", "corporate", "enterprise", "rule", "rules", "guidance",
    "document", "documentation", "work", "happen", "need", "use", "used", "using", "current",
    "standard", "general", "detail", "details", "information", "info", "explain", "describe",
    "occur", "happen", "happens", "apply", "count", "exist", "available", "currently", "allowed",
    "require", "required", "requirement", "version", "go", "goes", "going", "stay", "keep", "kept", "move", "make", "take", "out", "give", "know", "want",
}


def stem(token: str) -> str:
    """Very light suffix stripping so 'retries'~'retry', 'minutes'~'minute', 'tunneling'~'tunnel'."""
    t = token
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 5 and t.endswith("ing"):
        return t[:-3]
    if len(t) > 4 and t.endswith("ed") and not t.endswith("eed"):
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss") and not t.endswith("us"):
        return t[:-1]
    return t


def raw_tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def index_tokens(text: str) -> List[str]:
    """Tokens used by TF-IDF/BM25: lowercase, stop words removed, lightly stemmed."""
    return [stem(t) for t in raw_tokens(text) if t not in STOP_WORDS]


def _tfidf_analyzer(text: str) -> List[str]:
    toks = index_tokens(text)
    return toks + [f"{a} {b}" for a, b in zip(toks, toks[1:])]


# ---------------------------------------------------------------------------
# Synonym expansion (vocabulary only - never answer values)
# ---------------------------------------------------------------------------

EXPANSION_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(log ?in|sign[- ]?in|signing in|log on)\b", re.I), "authentication sso"),
    (re.compile(r"\b(two[- ]factor|2fa|second factor)\b", re.I), "mfa"),
    (re.compile(r"\b(security key|hardware key|security token)\b", re.I), "hardware token yubikey"),
    (re.compile(r"\b(throttling|throttle|quota|rate[- ]limit|api limit)\b", re.I), "rate limit requests minute"),
    (re.compile(r"\b(reimbursement|money back|refund)\b", re.I), "refund credit"),
    (re.compile(r"\b(upload cap|max upload|upload size|file size)\b", re.I), "upload size object"),
    (re.compile(r"\b(access denied|403|permission denied)\b", re.I), "accessdenied permission"),
    (re.compile(r"\b(retry|retries|redeliver)\b", re.I), "retry attempt"),
    (re.compile(r"\b(payment terms|invoice terms|due date|pay an invoice)\b", re.I), "payment terms invoice"),
    (re.compile(r"\b(locked out|lock out|lockout)\b", re.I), "lockout"),
    (re.compile(r"\b(timeout|time out|expire|expiry)\b", re.I), "timeout session"),
    (re.compile(r"\b(extra|additional)\b", re.I), "additional extra"),
    (re.compile(r"\b(failed|incorrect|wrong|invalid|bad)\b", re.I), "incorrect failed invalid"),
    (re.compile(r"\b(attempts?|tries|times)\b", re.I), "attempt times"),
]


def expand_query(query: str) -> Tuple[str, Dict[str, Set[str]]]:
    """Returns (expanded_query_text, alt_map). alt_map maps an original stemmed token to the
    stemmed synonyms that also satisfy it (used for evidence coverage checks)."""
    extra: List[str] = []
    alt_map: Dict[str, Set[str]] = {}
    for pattern, expansion in EXPANSION_RULES:
        matches = list(pattern.finditer(query))
        if not matches:
            continue
        extra.append(expansion)
        alts = set(index_tokens(expansion))
        for m in matches:
            for tok in index_tokens(m.group(0)):
                alt_map.setdefault(tok, set()).update(alts - {tok})
    return (f"{query} {' '.join(extra)}" if extra else query), alt_map


# ---------------------------------------------------------------------------
# Parsers -> List[(section_heading, text_with_lines, page_number)]
# ---------------------------------------------------------------------------

LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)]|\([a-z0-9]\))\s+")


def reflow(lines: List[str]) -> List[str]:
    """Joins hard-wrapped lines back into logical lines while keeping list items and
    paragraph breaks. Output lines are whitespace-normalised."""
    out: List[str] = []
    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            out.append("")
            continue
        starts_new = (
            not out or out[-1] == "" or LIST_MARKER.match(line)
            or out[-1].endswith((".", ":", "!", "?", "|")) or "|" in line
        )
        if starts_new:
            out.append(line)
        else:
            out[-1] = f"{out[-1]} {line}"
    return [l for l in out if l]


def _clean_md_inline(line: str) -> str:
    line = re.sub(r"^\s*>\s?", "", line)          # blockquote marker
    line = line.replace("**", "").replace("__", "")
    return line


def parse_markdown(content: str) -> List[Tuple[str, str, Optional[int]]]:
    sections: List[Tuple[str, str, Optional[int]]] = []
    stack: List[Tuple[int, str]] = []
    buf: List[str] = []
    in_fence = False
    title = None

    def heading_path() -> str:
        names = [h for lvl, h in stack if not (lvl == 1 and len(stack) > 1)]
        return " > ".join(names) if names else (title or "Overview")

    def flush():
        text = "\n".join(reflow(buf))
        if text.strip():
            sections.append((heading_path(), text, None))
        buf.clear()

    for line in content.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            buf.append(line)
            continue
        m = None if in_fence else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line.strip())
        if m:
            flush()
            level, name = len(m.group(1)), _clean_md_inline(m.group(2)).strip()
            if level == 1 and title is None:
                title = name
            stack = [(l, h) for l, h in stack if l < level] + [(level, name)]
            continue
        if not in_fence and re.match(r"^\s*([-*_])\1{2,}\s*$", line):   # horizontal rule
            buf.append("")
            continue
        buf.append(line if in_fence else _clean_md_inline(line))
    flush()
    return sections


class _HTMLSectionParser(HTMLParser):
    BLOCK = {"p", "div", "li", "tr", "br", "ul", "ol", "table", "section", "article", "blockquote", "pre"}
    CELL = {"td", "th"}
    HEAD = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections: List[Tuple[str, str, Optional[int]]] = []
        self.heading = "Overview"
        self.lines: List[str] = [""]
        self.skip = 0
        self.in_head = False
        self.head_buf: List[str] = []
        self.cell_index = 0

    def _newline(self):
        if self.lines[-1].strip():
            self.lines.append("")

    def _flush(self):
        text = "\n".join(reflow(self.lines))
        if text.strip():
            self.sections.append((self.heading, text, None))
        self.lines = [""]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style", "head", "title"):
            self.skip += 1
        elif tag in self.HEAD:
            self.in_head, self.head_buf = True, []
        elif tag in self.CELL:
            if self.cell_index > 0:
                self.lines[-1] += " | "
            self.cell_index += 1
        elif tag in self.BLOCK:
            if tag == "tr":
                self.cell_index = 0
            if tag == "li":
                self._newline()
                self.lines[-1] = "- "
            else:
                self._newline()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style", "head", "title"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.HEAD:
            self.in_head = False
            name = " ".join("".join(self.head_buf).split())
            if name:
                self._flush()
                self.heading = name
        elif tag in self.BLOCK:
            self._newline()

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_head:
            self.head_buf.append(data)
        else:
            self.lines[-1] += data.replace("\n", " ")

    def close(self):
        super().close()
        self._flush()


def parse_html(content: str) -> List[Tuple[str, str, Optional[int]]]:
    p = _HTMLSectionParser()
    p.feed(content)
    p.close()
    return p.sections


NUMBERED_HEADING = re.compile(r"^(\d+\.\s+[A-Z][A-Za-z0-9 &\-_()/',]{2,90})$")


def _looks_like_heading(line: str) -> bool:
    s = line.strip()
    return bool(NUMBERED_HEADING.match(s)) and not s.endswith(".") and len(s.split()) <= 12


def _parse_lines_with_numbered_headings(lines: List[str], default_heading: str, page: Optional[int]):
    sections, buf, heading = [], [], default_heading
    for line in lines:
        s = line.strip()
        if re.match(r"^[=\-_]{3,}$", s):
            buf.append("")
            continue
        if _looks_like_heading(s):
            text = "\n".join(reflow(buf))
            if text.strip():
                sections.append((heading, text, page))
            buf, heading = [], s
            continue
        buf.append(line)
    text = "\n".join(reflow(buf))
    if text.strip():
        sections.append((heading, text, page))
    return sections


def parse_txt(content: str) -> List[Tuple[str, str, Optional[int]]]:
    return _parse_lines_with_numbered_headings(content.splitlines(), "General", None)


def parse_pdf_bytes(data: bytes) -> List[Tuple[str, str, Optional[int]]]:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
    except Exception as e:
        raise ValueError(f"Could not read PDF (corrupted or not a PDF): {e}")
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise ValueError("PDF is password-protected and cannot be parsed.")
    results: List[Tuple[str, str, Optional[int]]] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            results.extend(_parse_lines_with_numbered_headings(text.splitlines(), f"Page {page_no}", page_no))
    if not results:
        raise ValueError("PDF has no extractable text (scanned/image-only PDFs are not supported; OCR is out of scope).")
    return results


def decode_text(data: bytes, filename: str) -> str:
    for enc in ("utf-8-sig",):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    raise ValueError(f"'{filename}' is not valid UTF-8 text. Re-save it as UTF-8 and upload again.")


def parse_document(data: bytes, doc_format: str, filename: str) -> List[Tuple[str, str, Optional[int]]]:
    if doc_format == "PDF":
        return parse_pdf_bytes(data)
    text = decode_text(data, filename)
    if doc_format == "MD":
        return parse_markdown(text)
    if doc_format == "HTML":
        return parse_html(text)
    return parse_txt(text)


# ---------------------------------------------------------------------------
# Chunking: whole logical lines, ~220 words, one line of overlap
# ---------------------------------------------------------------------------

def chunk_text(text: str, target_words: int = 220) -> List[str]:
    lines = [l for l in text.split("\n") if l.strip()]
    if sum(len(l.split()) for l in lines) <= target_words:
        return ["\n".join(lines)]
    chunks, cur, count = [], [], 0
    for line in lines:
        n = len(line.split())
        if cur and count + n > target_words:
            chunks.append("\n".join(cur))
            cur, count = [cur[-1]], len(cur[-1].split())   # one-line overlap keeps context
        cur.append(line)
        count += n
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def build_passages(doc: Dict[str, Any], sections) -> List[Passage]:
    out: List[Passage] = []
    for s_idx, (heading, body, page) in enumerate(sections, start=1):
        for c_idx, chunk in enumerate(chunk_text(body), start=1):
            prefix = f"P{page:02d}-" if page else ""
            out.append(Passage(
                passage_id=f"{doc['doc_id']}-{prefix}S{s_idx:02d}-C{c_idx:02d}",
                doc_id=doc["doc_id"],
                doc_title=doc.get("title", doc["filename"]),
                source_filename=doc["filename"],
                doc_format=doc.get("format", "TXT").upper(),
                section_heading=heading,
                page_number=page,
                version=doc.get("version") or "Unknown",
                effective_date=doc.get("effective_date") or "Unknown",
                environment=doc.get("environment") or "Unknown",
                text=chunk,
                word_count=len(chunk.split()),
            ))
    return out


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def scope_values(field_value: str) -> List[str]:
    return [v.strip().lower() for v in (field_value or "").split(",") if v.strip()]


def passes_filters(p: Passage, filters: Optional[Dict[str, Any]]) -> bool:
    if not filters:
        return True
    fmt = filters.get("format") or filters.get("format_filter")
    if fmt and fmt.upper() != "ALL" and p.doc_format.upper() != fmt.upper():
        return False
    env = (filters.get("environment") or "").strip().lower()
    if env and env != "all":
        envs = scope_values(p.environment)
        if env not in envs and "all" not in envs:
            return False
    ver = (filters.get("version") or "").strip().lower()
    if ver and ver != "all" and p.version.strip().lower() != ver:
        return False
    if filters.get("doc_id") and p.doc_id != filters["doc_id"]:
        return False
    return True


@dataclass(frozen=True)
class IndexSnapshot:
    passages: List[Passage] = field(default_factory=list)
    vectorizer: Optional[TfidfVectorizer] = None
    matrix: Any = None
    bm25: Optional[BM25Okapi] = None
    token_sets: List[Set[str]] = field(default_factory=list)
    generation: int = 0


def build_snapshot(passages: List[Passage], generation: int) -> IndexSnapshot:
    if not passages:
        return IndexSnapshot(generation=generation)
    texts = [f"{p.doc_title} {p.section_heading} {p.text}" for p in passages]
    vec = TfidfVectorizer(analyzer=_tfidf_analyzer, sublinear_tf=True)
    matrix = vec.fit_transform(texts)
    tokenized = [index_tokens(t) for t in texts]
    return IndexSnapshot(passages, vec, matrix, BM25Okapi(tokenized), [set(t) for t in tokenized], generation)


class KnowledgeBaseIndex:
    def __init__(self, backend_dir: Optional[Path] = None):
        self.backend_dir = Path(backend_dir or Path(__file__).resolve().parent)
        self.docs_corpus_dir = self.backend_dir / "docs_corpus"
        self.data_dir = self.backend_dir / "data"
        self.manifest_path = self.data_dir / "document_manifest.json"
        self._snapshot = IndexSnapshot()
        self._write_lock = threading.Lock()
        self.load_warnings: List[str] = []

    # Read-only views of the current snapshot ---------------------------------
    @property
    def snapshot(self) -> IndexSnapshot:
        return self._snapshot

    @property
    def passages(self) -> List[Passage]:
        return self._snapshot.passages

    @property
    def generation(self) -> int:
        return self._snapshot.generation

    # Manifest ----------------------------------------------------------------
    def read_manifest(self) -> List[Dict[str, Any]]:
        if not self.manifest_path.exists():
            return []
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write_manifest(self, manifest: List[Dict[str, Any]]):
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(tmp, self.manifest_path)          # atomic on the same filesystem

    # Build -------------------------------------------------------------------
    def _passages_for_manifest(self, manifest) -> Tuple[List[Passage], List[str]]:
        passages, warnings = [], []
        for doc in manifest:
            path = self.docs_corpus_dir / doc["filename"]
            if not path.exists():
                warnings.append(f"Missing file for {doc.get('doc_id')}: {doc['filename']}")
                continue
            try:
                sections = parse_document(path.read_bytes(), doc.get("format", "TXT").upper(), doc["filename"])
                passages.extend(build_passages(doc, sections))
            except Exception as e:   # one bad file must never take the whole index down
                warnings.append(f"Skipped {doc['filename']}: {e}")
        return passages, warnings

    def build_index(self):
        self.docs_corpus_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        passages, warnings = self._passages_for_manifest(self.read_manifest())
        for w in warnings:
            print(f"Warning: {w}")
        self.load_warnings = warnings
        self._snapshot = build_snapshot(passages, self._snapshot.generation + 1)

    # Retrieval ---------------------------------------------------------------
    def find_relevant_passages(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None,
                               rrf_k: int = 60) -> List[ScoredPassage]:
        snap = self._snapshot                     # take one consistent snapshot for this request
        if not snap.passages or snap.vectorizer is None:
            return []
        expanded, _ = expand_query(query)
        q_tokens = index_tokens(expanded)
        if not q_tokens:
            return []

        tfidf = (snap.matrix @ snap.vectorizer.transform([expanded]).T).toarray().ravel()
        bm25 = snap.bm25.get_scores(q_tokens)

        eligible = [i for i, p in enumerate(snap.passages)
                    if passes_filters(p, filters) and (tfidf[i] > 0 or bm25[i] > 0)]
        if not eligible:
            return []
        tf_rank = {i: r for r, i in enumerate(sorted(eligible, key=lambda i: -tfidf[i]), start=1)}
        bm_rank = {i: r for r, i in enumerate(sorted(eligible, key=lambda i: -bm25[i]), start=1)}
        rrf = {i: 1.0 / (rrf_k + tf_rank[i]) + 1.0 / (rrf_k + bm_rank[i]) for i in eligible}

        q_set = set(q_tokens)
        results = []
        for rank, i in enumerate(sorted(eligible, key=lambda i: -rrf[i])[:top_k], start=1):
            p = snap.passages[i]
            results.append(ScoredPassage(
                **p.model_dump(), rank=rank, tfidf_similarity=float(tfidf[i]), bm25_score=float(bm25[i]),
                rrf_score=float(rrf[i]), matched_terms=sorted(q_set & snap.token_sets[i]),
            ))
        return results

    def get_passage(self, passage_id: str) -> Optional[Passage]:
        return next((p for p in self._snapshot.passages if p.passage_id == passage_id), None)

    # Upload (transactional) --------------------------------------------------
    def ingest_uploaded_file(self, filename: str, content_bytes: bytes, version: Optional[str] = None,
                             environment: Optional[str] = None, effective_date: Optional[str] = None,
                             document_title: Optional[str] = None) -> Dict[str, Any]:
        if not content_bytes:
            raise ValueError("Uploaded file is empty.")
        if len(content_bytes) > MAX_UPLOAD_BYTES:
            raise ValueError("File exceeds the 10 MB upload limit.")

        clean = re.sub(r"[^A-Za-z0-9_.\-]", "_", Path(filename or "upload.txt").name) or "upload.txt"
        ext = os.path.splitext(clean)[1].lower()
        if ext not in EXT_TO_FORMAT:
            raise ValueError(f"Unsupported format '{ext}'. Allowed: .md, .html, .htm, .txt, .pdf")
        doc_format = EXT_TO_FORMAT[ext]

        doc = {
            "doc_id": f"DOC-UP-{uuid.uuid4().hex[:8].upper()}",
            "title": (document_title or "").strip() or Path(clean).stem.replace("_", " "),
            "filename": clean,
            "format": doc_format,
            "version": (version or "").strip() or "Unknown",
            "effective_date": (effective_date or "").strip() or "Unknown",
            "environment": (environment or "").strip() or "Unknown",
            "uploaded_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }

        # 1) Parse in memory BEFORE touching disk -> bad files never enter the corpus.
        sections = parse_document(content_bytes, doc_format, clean)
        new_passages = build_passages(doc, sections)
        if not new_passages:
            raise ValueError("No extractable text passages were found in this document.")

        with self._write_lock:
            target = self.docs_corpus_dir / clean
            if target.exists():
                clean = f"{uuid.uuid4().hex[:6]}_{clean}"
                doc["filename"] = clean
                target = self.docs_corpus_dir / clean
                new_passages = build_passages(doc, sections)

            # 2) Build the candidate index off to the side.
            manifest = self.read_manifest()
            candidate = build_snapshot(list(self._snapshot.passages) + new_passages, self._snapshot.generation + 1)

            # 3) Commit file + manifest, roll back on any failure, then swap the index.
            try:
                target.write_bytes(content_bytes)
                self._write_manifest(manifest + [doc])
            except Exception:
                if target.exists():
                    target.unlink()
                raise
            self._snapshot = candidate

        return {**doc, "passage_count": len(new_passages), "status": "INGESTED_SUCCESSFULLY"}


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

_kb_index: Optional[KnowledgeBaseIndex] = None
_kb_lock = threading.Lock()


def get_knowledge_base() -> KnowledgeBaseIndex:
    global _kb_index
    if _kb_index is None:
        with _kb_lock:
            if _kb_index is None:
                kb = KnowledgeBaseIndex()
                kb.build_index()
                _kb_index = kb
    return _kb_index


def find_relevant_passages(query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[ScoredPassage]:
    return get_knowledge_base().find_relevant_passages(query, top_k=top_k, filters=filters)


def ingest_uploaded_file(filename: str, content_bytes: bytes, **kwargs) -> Dict[str, Any]:
    return get_knowledge_base().ingest_uploaded_file(filename, content_bytes, **kwargs)
