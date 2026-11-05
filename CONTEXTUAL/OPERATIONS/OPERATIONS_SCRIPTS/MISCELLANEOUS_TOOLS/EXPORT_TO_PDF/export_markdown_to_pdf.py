#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent
VENV_DIR = SCRIPT_DIR / ".venv"
EXPORT_DIR = SCRIPT_DIR / "EXPORTS"

REQUIRED_PACKAGES = [
    ("PIL", "pillow"),
    ("fpdf", "fpdf2"),
]


def inside_own_venv() -> bool:
    return Path(sys.prefix).resolve() == VENV_DIR.resolve()


def venv_python() -> Path:
    return VENV_DIR / "bin" / "python"


def module_available(module_name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(module_name) is not None


def ensure_local_venv_and_reexec() -> None:
    """
    Ensure the script runs inside its own local virtual environment.

    This avoids installing packages into the system Python, which fails on
    externally managed Python installations such as Ubuntu/Debian Python 3.12.
    """
    if inside_own_venv():
        return

    py = venv_python()

    if not py.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])

    missing = []
    for import_name, pip_name in REQUIRED_PACKAGES:
        check_cmd = [
            str(py),
            "-c",
            f"import importlib.util; raise SystemExit(0 if importlib.util.find_spec({import_name!r}) else 1)",
        ]
        if subprocess.call(check_cmd) != 0:
            missing.append(pip_name)

    if missing:
        subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([str(py), "-m", "pip", "install", *missing])

    os.execv(str(py), [str(py), str(SCRIPT_PATH), *sys.argv[1:]])


ensure_local_venv_and_reexec()

from PIL import Image
from fpdf import FPDF


def sanitize_for_pdf(text: str) -> str:
    replacements = {
        "–": "-",
        "—": "-",
        "−": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
        "≤": "<=",
        "≥": ">=",
        "≈": "~",
        "≠": "!=",
        "→": "->",
        "←": "<-",
        "↔": "<->",
        "×": "x",
        "·": ".",
        "°": " deg",
        "μ": "u",
        "α": "alpha",
        "β": "beta",
        "γ": "gamma",
        "δ": "delta",
        "ε": "epsilon",
        "θ": "theta",
        "λ": "lambda",
        "π": "pi",
        "ρ": "rho",
        "σ": "sigma",
        "φ": "phi",
        "Ω": "Ohm",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text.encode("latin-1", errors="replace").decode("latin-1")


def clean_inline_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return sanitize_for_pdf(text)


class MarkdownPDF(FPDF):
    def __init__(self, title: str):
        super().__init__()
        self.document_title = title

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, sanitize_for_pdf(self.document_title), border=0, ln=1, align="C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def write_paragraph(pdf: FPDF, text: str, size: int = 10, style: str = "") -> None:
    text = clean_inline_markdown(text).strip()
    if not text:
        return

    pdf.set_font("Helvetica", style, size)
    pdf.multi_cell(0, 5.5, text)
    pdf.ln(1)


def add_image(pdf: FPDF, image_path: Path, page_width: float) -> None:
    if not image_path.exists():
        write_paragraph(pdf, f"[Missing image: {image_path}]", size=9, style="I")
        return

    try:
        with Image.open(image_path) as image:
            width_px, height_px = image.size
    except Exception as exc:
        write_paragraph(
            pdf,
            f"[Could not read image: {image_path} ({exc})]",
            size=9,
            style="I",
        )
        return

    display_width = page_width
    display_height = display_width * height_px / width_px

    max_height = pdf.h - 40
    if display_height > max_height:
        display_height = max_height
        display_width = display_height * width_px / height_px

    if pdf.get_y() + display_height > pdf.page_break_trigger:
        pdf.add_page()

    x = pdf.l_margin + (page_width - display_width) / 2
    pdf.image(str(image_path), x=x, y=pdf.get_y(), w=display_width)
    pdf.ln(display_height + 4)


def flush_code_block(pdf: FPDF, code_buffer: list[str]) -> None:
    if not code_buffer:
        return

    pdf.set_font("Courier", "", 8)
    pdf.set_fill_color(245, 245, 245)

    for code_line in code_buffer:
        pdf.multi_cell(0, 4.5, sanitize_for_pdf(code_line), fill=True)

    pdf.ln(2)


def convert_markdown_to_pdf(input_md: Path, output_pdf: Path) -> None:
    input_md = input_md.resolve()
    output_pdf = output_pdf.resolve()
    base_dir = input_md.parent

    text = input_md.read_text(encoding="utf-8", errors="replace")

    pdf = MarkdownPDF(title=input_md.name)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    pdf.add_page()

    page_width = pdf.w - pdf.l_margin - pdf.r_margin

    in_code_block = False
    code_buffer: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_buffer = []
            else:
                in_code_block = False
                flush_code_block(pdf, code_buffer)
                code_buffer = []
            continue

        if in_code_block:
            code_buffer.append(line)
            continue

        image_match = re.match(r"!\[[^\]]*\]\(([^)]+)\)", line.strip())
        if image_match:
            image_ref = image_match.group(1).strip().strip('"').strip("'")
            image_path = Path(image_ref)

            if not image_path.is_absolute():
                image_path = base_dir / image_path

            add_image(pdf, image_path, page_width)
            continue

        if not line.strip():
            pdf.ln(2)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            heading = clean_inline_markdown(heading_match.group(2))
            size = max(10, 18 - 2 * (level - 1))

            pdf.set_font("Helvetica", "B", size)
            pdf.multi_cell(0, 7, heading)
            pdf.ln(2)
            continue

        bullet_match = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if bullet_match:
            write_paragraph(pdf, "- " + bullet_match.group(1), size=10)
            continue

        numbered_match = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if numbered_match:
            write_paragraph(
                pdf,
                f"{numbered_match.group(1)}. {numbered_match.group(2)}",
                size=10,
            )
            continue

        if line.strip().startswith(">"):
            write_paragraph(
                pdf,
                line.strip().lstrip(">").strip(),
                size=9,
                style="I",
            )
            continue

        write_paragraph(pdf, line, size=10)

    if in_code_block:
        flush_code_block(pdf, code_buffer)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_pdf))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a Markdown file to PDF and save it in DOCS/EXPORT_TO_PDF/EXPORTS."
    )
    parser.add_argument("markdown_file", help="Path to the input Markdown file")
    args = parser.parse_args()

    input_md = Path(args.markdown_file)

    if not input_md.exists():
        raise SystemExit(f"Error: input file does not exist: {input_md}")

    if not input_md.is_file():
        raise SystemExit(f"Error: input path is not a file: {input_md}")

    if input_md.suffix.lower() not in {".md", ".markdown"}:
        raise SystemExit(f"Error: input file must be Markdown: {input_md}")

    output_pdf = EXPORT_DIR / f"{input_md.stem}.pdf"

    convert_markdown_to_pdf(input_md, output_pdf)

    print("Created PDF:")
    print(output_pdf)


if __name__ == "__main__":
    main()