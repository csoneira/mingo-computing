#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DEVELOPER_TOOLS/standardize_script_headers.py
Purpose: Apply standardized non-functional headers to tracked .py/.sh/.m/.html scripts.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DEVELOPER_TOOLS/standardize_script_headers.py [--apply]
Inputs: Tracked script files from git index.
Outputs: Updated script headers (when --apply is used) and summary report.
Notes: This tool modifies header/docstring comments only; no runtime logic changes.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import re
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

HEADER_MARKER = "DATAFLOW_v3 Script Header v1"
ENCODING_RE = re.compile(r"^#.*coding[:=]\s*[-\w.]+")
SH_HEADER_RE = re.compile(
    r"^# =============================================================================\n"
    r"# DATAFLOW_v3 Script Header v1\n"
    r"(?:# .*\n)*"
    r"# =============================================================================\n\n?",
    flags=re.MULTILINE,
)
M_HEADER_RE = re.compile(
    r"^% =============================================================================\n"
    r"% DATAFLOW_v3 Script Header v1\n"
    r"(?:% .*\n)*"
    r"% =============================================================================\n\n?",
    flags=re.MULTILINE,
)
HTML_HEADER_RE = re.compile(
    r"^<!--\n"
    r"=============================================================================\n"
    r"DATAFLOW_v3 Script Header v1\n"
    r"(?:.*\n)*?"
    r"=============================================================================\n"
    r"-->\n\n?",
    flags=re.MULTILINE,
)

GENERIC_PURPOSES = {
    "run with.",
    "usage.",
    "configuration.",
    "join.",
    "script.",
}


def run_git(args: List[str]) -> str:
    proc = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def get_signature() -> str:
    try:
        name = run_git(["config", "user.name"])
    except subprocess.CalledProcessError:
        name = "DATAFLOW_v3 maintainer"
    try:
        email = run_git(["config", "user.email"])
    except subprocess.CalledProcessError:
        email = "unknown@example.com"
    return f"{name} <{email}>"


def tracked_script_paths() -> List[Path]:
    raw = run_git(["ls-files", "*.py", "*.sh", "*.m", "*.html"])
    paths = [Path(line) for line in raw.splitlines() if line.strip()]
    return [p for p in paths if p.is_file()]


def infer_default_purpose(path: Path) -> str:
    words = path.stem.replace("_", " ").replace("-", " ").strip()
    if not words:
        return "Provide script functionality."
    parent = path.parent.name.replace("_", " ").replace("-", " ").strip()
    stem = words[0].upper() + words[1:]
    if parent and parent.lower() not in {"", "bin", "scripts", "software", "ana"}:
        return f"{stem} workflow for {parent}."
    return f"{stem} workflow utility."


def first_sentence(text: str) -> str:
    line = text.strip().splitlines()[0].strip()
    if not line:
        return ""
    if not line.endswith("."):
        line += "."
    return line


def is_generic_purpose(purpose: str) -> bool:
    p = purpose.strip().lower()
    if not p:
        return True
    if p in GENERIC_PURPOSES:
        return True
    if len(p.replace(".", "").split()) <= 1:
        return True
    if p.startswith("run ") or p.startswith("use ") or p.startswith("this script"):
        return True
    return False


def extract_purpose_py(text: str, path: Path) -> str:
    try:
        module = ast.parse(text)
    except SyntaxError:
        return infer_default_purpose(path)
    doc = ast.get_docstring(module, clean=True)
    if doc:
        sent = first_sentence(doc)
        if sent and HEADER_MARKER not in sent and not is_generic_purpose(sent):
            return sent
    # fallback: first comment line
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            body = s.lstrip("#").strip()
            if body and HEADER_MARKER not in body:
                sent = first_sentence(body)
                if not is_generic_purpose(sent):
                    return sent
        elif s:
            break
    return infer_default_purpose(path)


def extract_purpose_sh(text: str, path: Path) -> str:
    lines = text.splitlines()
    start = 1 if lines and lines[0].startswith("#!") else 0
    for line in lines[start:start + 30]:
        s = line.strip()
        if s.startswith("#"):
            body = s.lstrip("#").strip(" -")
            if body and HEADER_MARKER not in body:
                sent = first_sentence(body)
                if not is_generic_purpose(sent):
                    return sent
        elif s:
            break
    return infer_default_purpose(path)


def extract_purpose_m(text: str, path: Path) -> str:
    for line in text.splitlines()[:40]:
        s = line.strip()
        if s.startswith("%"):
            body = s.lstrip("%").strip(" -")
            if body and HEADER_MARKER not in body:
                sent = first_sentence(body)
                if not is_generic_purpose(sent):
                    return sent
        elif s.lower().startswith("function"):
            m = re.search(r"function\s+.*?=\s*([A-Za-z0-9_]+)\s*\(|function\s+([A-Za-z0-9_]+)\s*\(", s)
            if m:
                fn = m.group(1) or m.group(2)
                return first_sentence(f"{fn} function implementation")
        elif s:
            break
    return infer_default_purpose(path)


def extract_purpose_html(text: str, path: Path) -> str:
    title_match = re.search(r"<title>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        title = " ".join(title_match.group(1).split())
        if title:
            sent = first_sentence(title)
            if not is_generic_purpose(sent):
                return sent
    comment_match = re.search(r"<!--(.*?)-->", text, flags=re.DOTALL)
    if comment_match:
        body = " ".join(comment_match.group(1).split())
        if body and HEADER_MARKER not in body:
            sent = first_sentence(body)
            if not is_generic_purpose(sent):
                return sent
    return infer_default_purpose(path)


def remove_initial_module_docstring(text: str) -> Tuple[str, Optional[str]]:
    """Remove initial Python module docstring if present; return (text, doc)."""
    try:
        module = ast.parse(text)
    except SyntaxError:
        return text, None
    if not module.body:
        return text, None
    first = module.body[0]
    if not (isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str)):
        return text, None

    doc = first.value.value
    lines = text.splitlines()
    start = first.lineno - 1
    end = first.end_lineno
    new_lines = lines[:start] + lines[end:]
    # collapse leading extra blank lines after shebang/encoding region later
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), doc


def py_header(path: Path, purpose: str, signoff: str, today: str) -> str:
    return (
        '"""\n'
        f"{HEADER_MARKER}\n"
        f"Script: {path.as_posix()}\n"
        f"Purpose: {purpose}\n"
        "Owner: DATAFLOW_v3 contributors\n"
        f"Sign-off: {signoff}\n"
        f"Last Updated: {today}\n"
        "Runtime: python3\n"
        f"Usage: python3 {path.as_posix()} [options]\n"
        "Inputs: CLI args, config files, environment variables, and/or upstream files.\n"
        "Outputs: Files, logs, plots, or stdout/stderr side effects.\n"
        "Notes: Keep behavior configuration-driven and reproducible.\n"
        '"""\n\n'
    )


def sh_header(path: Path, purpose: str, signoff: str, today: str) -> str:
    return (
        "# =============================================================================\n"
        f"# {HEADER_MARKER}\n"
        f"# Script: {path.as_posix()}\n"
        f"# Purpose: {purpose}\n"
        "# Owner: DATAFLOW_v3 contributors\n"
        f"# Sign-off: {signoff}\n"
        f"# Last Updated: {today}\n"
        "# Runtime: bash\n"
        f"# Usage: bash {path.as_posix()} [options]\n"
        "# Inputs: CLI args, config files, environment variables, and/or upstream files.\n"
        "# Outputs: Files, logs, or process-level side effects.\n"
        "# Notes: Keep behavior configuration-driven and reproducible.\n"
        "# =============================================================================\n\n"
    )


def m_header(path: Path, purpose: str, signoff: str, today: str) -> str:
    return (
        "% =============================================================================\n"
        f"% {HEADER_MARKER}\n"
        f"% Script: {path.as_posix()}\n"
        f"% Purpose: {purpose}\n"
        "% Owner: DATAFLOW_v3 contributors\n"
        f"% Sign-off: {signoff}\n"
        f"% Last Updated: {today}\n"
        "% Runtime: octave/matlab\n"
        "% Usage: Run from MATLAB/Octave entrypoint with expected args/context.\n"
        "% Inputs: Variables, config files, environment, and/or upstream files.\n"
        "% Outputs: Variables, files, plots, or logs.\n"
        "% Notes: Keep behavior configuration-driven and reproducible.\n"
        "% =============================================================================\n\n"
    )


def html_header(path: Path, purpose: str, signoff: str, today: str) -> str:
    return (
        "<!--\n"
        "=============================================================================\n"
        f"{HEADER_MARKER}\n"
        f"Script: {path.as_posix()}\n"
        f"Purpose: {purpose}\n"
        "Owner: DATAFLOW_v3 contributors\n"
        f"Sign-off: {signoff}\n"
        f"Last Updated: {today}\n"
        "Runtime: html\n"
        "Usage: Open/render in browser or embed in docs/UI workflow.\n"
        "Inputs: Static assets, linked resources, template variables (if any).\n"
        "Outputs: Rendered page/view.\n"
        "Notes: Keep references stable and document external dependencies.\n"
        "=============================================================================\n"
        "-->\n\n"
    )


def apply_header(path: Path, signoff: str, today: str, refresh: bool = False) -> bool:
    text = path.read_text(encoding="utf-8")
    if HEADER_MARKER in text and not refresh:
        return False

    ext = path.suffix.lower()

    if ext == ".py":
        cleaned, removed_doc = remove_initial_module_docstring(text)
        purpose = extract_purpose_py(cleaned, path)
        if removed_doc and purpose == infer_default_purpose(path):
            from_doc = first_sentence(removed_doc)
            if from_doc and HEADER_MARKER not in from_doc:
                purpose = from_doc
        lines = cleaned.splitlines(keepends=True)
        idx = 0
        if lines and lines[0].startswith("#!"):
            idx = 1
        if idx < len(lines) and ENCODING_RE.match(lines[idx].rstrip("\n")):
            idx += 1
        prefix = "".join(lines[:idx])
        rest = "".join(lines[idx:])
        # normalize extra leading blank lines in remainder
        rest = rest.lstrip("\n")
        new_text = prefix + py_header(path, purpose, signoff, today) + rest

    elif ext == ".sh":
        lines = text.splitlines(keepends=True)
        if lines and lines[0].startswith("#!"):
            prefix = lines[0]
            rest = "".join(lines[1:]).lstrip("\n")
            if refresh:
                rest = SH_HEADER_RE.sub("", rest, count=1)
            purpose = extract_purpose_sh(prefix + rest, path)
            new_text = prefix + sh_header(path, purpose, signoff, today) + rest
        else:
            body = text.lstrip("\n")
            if refresh:
                body = SH_HEADER_RE.sub("", body, count=1)
            purpose = extract_purpose_sh(body, path)
            new_text = sh_header(path, purpose, signoff, today) + body

    elif ext == ".m":
        body = text.lstrip("\n")
        if refresh:
            body = M_HEADER_RE.sub("", body, count=1)
        purpose = extract_purpose_m(body, path)
        new_text = m_header(path, purpose, signoff, today) + body

    elif ext == ".html":
        stripped = text.lstrip("\n")
        lower = stripped.lower()
        if lower.startswith("<!doctype"):
            first_line, sep, tail = stripped.partition("\n")
            if refresh:
                tail = HTML_HEADER_RE.sub("", tail, count=1)
            purpose = extract_purpose_html(first_line + "\n" + tail, path)
            new_text = first_line + ("\n" if sep else "") + html_header(path, purpose, signoff, today) + tail
        else:
            body = stripped
            if refresh:
                body = HTML_HEADER_RE.sub("", body, count=1)
            purpose = extract_purpose_html(body, path)
            new_text = html_header(path, purpose, signoff, today) + body

    else:
        return False

    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Standardize headers for tracked script files.")
    parser.add_argument("--apply", action="store_true", help="Write updates to files.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh existing standard headers (for improved inferred purpose/signature/date fields).",
    )
    args = parser.parse_args()

    signoff = get_signature()
    today = dt.date.today().isoformat()
    paths = tracked_script_paths()

    changed: List[Path] = []
    for path in paths:
        if not args.apply:
            text = path.read_text(encoding="utf-8")
            if HEADER_MARKER not in text:
                changed.append(path)
            continue
            if apply_header(path, signoff, today, refresh=args.refresh):
                changed.append(path)

    mode = "updated" if args.apply else "would update"
    print(f"{mode}: {len(changed)} files")
    for p in changed[:40]:
        print(f" - {p.as_posix()}")
    if len(changed) > 40:
        print(f" ... and {len(changed)-40} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
