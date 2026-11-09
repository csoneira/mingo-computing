#!/usr/bin/env python3
"""Display a directory-only tree rooted at the current working directory."""

import argparse
from pathlib import Path


def print_tree(directory: Path, depth: int, prefix: str, show_hidden: bool) -> None:
    if depth == 0:
        return

    try:
        children = sorted(
            (
                path for path in directory.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and path.name != ".git"
                and (show_hidden or not path.name.startswith("."))
            ),
            key=lambda path: (path.name.casefold(), path.name),
        )
    except PermissionError:
        print(f"{prefix}└── [permission denied]")
        return

    for index, child in enumerate(children):
        last = index == len(children) - 1
        print(f"{prefix}{'└── ' if last else '├── '}{child.name}/")
        print_tree(child, depth - 1, prefix + ("    " if last else "│   "), show_hidden)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print directories as a Unicode tree.")
    parser.add_argument("depth", nargs="?", type=int, default=4,
                        help="Maximum subdirectory depth (default: 4).")
    parser.add_argument("--all", action="store_true",
                        help="Include hidden directories (except .git).")
    args = parser.parse_args()
    if args.depth < 0:
        parser.error("depth must be non-negative")

    root = Path.cwd()
    print(f"{root.name}/" if root.name else "/")
    print_tree(root, args.depth, "", args.all)


if __name__ == "__main__":
    main()
