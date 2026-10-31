"""
dump_snapshot.py - write the project's text files into ONE .txt for sharing with a reviewer / AI.

Format (same as before, round-trips with apply_snapshot.py):
    === PROJECT FILE TREE ===
    - backend/main.py   (12.3 KB)
    ...
    ========================================
    === FILE: backend/main.py ===
    <file content>

Usage (from the repo root):
    python dump_snapshot.py                         -> project_snapshot.txt
    python dump_snapshot.py -o review.txt
    python dump_snapshot.py --only backend          -> just one folder (repeatable)
    python dump_snapshot.py --include-generated     -> also EVALUATION_REPORT.md / eval_results.json
    python dump_snapshot.py --changed               -> only files changed vs. last commit (+ untracked)

File list = `git ls-files` + untracked-but-not-ignored files, so .gitignore is respected
(.venv, node_modules, .env never get in). Falls back to a folder walk if git is missing.
Binary files (PDF, images), lockfiles and big files are listed in the tree but not dumped.
"""

import argparse
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache", ".idea", ".vscode"}
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", ".env", "audit_log.jsonl",
              "project_snapshot.txt", "corrected_project_snapshot.txt", "dump_snapshot.py", "apply_snapshot.py"}
BINARY_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".docx", ".xlsx", ".pptx", ".zip",
              ".pyc", ".woff", ".woff2", ".ttf", ".exe", ".dll"}
GENERATED = {"EVALUATION_REPORT.md", "backend/data/eval_results.json"}
MAX_KB_DEFAULT = 200


def git_files(root: Path, changed_only: bool):
    def run(*args):
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout
        return [l.strip() for l in out.splitlines() if l.strip()]
    try:
        untracked = run("ls-files", "--others", "--exclude-standard")
        if changed_only:
            return sorted(set(run("diff", "--name-only", "HEAD") + untracked))
        return sorted(set(run("ls-files") + untracked))
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def walk_files(root: Path):
    out = []
    for p in root.rglob("*"):
        if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            out.append(p.relative_to(root).as_posix())
    return sorted(out)


def is_text(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096]
        chunk.decode("utf-8")
        return b"\x00" not in chunk
    except (UnicodeDecodeError, OSError):
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default="project_snapshot.txt")
    ap.add_argument("--only", action="append", default=[], help="folder/file prefix to include (repeatable)")
    ap.add_argument("--include-generated", action="store_true")
    ap.add_argument("--changed", action="store_true", help="only files changed since the last commit")
    ap.add_argument("--max-kb", type=int, default=MAX_KB_DEFAULT)
    args = ap.parse_args()

    root = Path.cwd()
    out_path = (root / args.out).resolve()
    files = git_files(root, args.changed)
    if files is None:
        if args.changed:
            sys.exit("--changed needs git.")
        files = walk_files(root)

    tree, dumped = [], []
    for rel in files:
        p = root / rel
        parts = Path(rel).parts
        if not p.is_file() or p.resolve() == out_path:
            continue
        if any(x in SKIP_DIRS for x in parts) or Path(rel).name in SKIP_NAMES:
            continue
        if args.only and not any(rel == o.strip("/\\").replace("\\", "/") or rel.startswith(o.strip("/\\").replace("\\", "/") + "/")
                                 for o in args.only):
            continue
        size_kb = p.stat().st_size / 1024
        note = ""
        if rel in GENERATED and not args.include_generated:
            note = "generated - not dumped (run backend/evaluate.py)"
        elif p.suffix.lower() in BINARY_EXT or not is_text(p):
            note = "binary - not dumped"
        elif p.read_text(encoding="utf-8", errors="ignore").lstrip().startswith("=== PROJECT FILE TREE ==="):
            continue                                   # another snapshot dump - never nest them
        elif size_kb > args.max_kb:
            note = f"over {args.max_kb} KB - not dumped"
        tree.append(f"- {rel}   ({size_kb:.1f} KB){'   [' + note + ']' if note else ''}")
        if not note:
            dumped.append(rel)

    lines = ["=== PROJECT FILE TREE ===", *tree, "", "=" * 40, ""]
    for rel in dumped:
        text = (root / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        lines += [f"=== FILE: {rel} ===", text.rstrip("\n"), ""]
    out_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    total_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path.name}: {len(dumped)} files dumped, {len(tree) - len(dumped)} listed only, {total_kb:.0f} KB")


if __name__ == "__main__":
    main()
