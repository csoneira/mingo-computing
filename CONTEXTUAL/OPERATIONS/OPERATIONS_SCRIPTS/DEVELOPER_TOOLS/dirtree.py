#!/usr/bin/env python3
"""Display files and directories in a tree rooted at the current directory."""

import argparse
from pathlib import Path


def print_tree(
    directory: Path,
    depth: int,
    prefix: str,
    show_hidden: bool,
    directories_only: bool,
) -> None:
    if depth <= 0:
        return

    try:
        children = sorted(
            (
                path for path in directory.iterdir()
                if path.name != ".git"
                and (show_hidden or not path.name.startswith("."))
                and (
                    not directories_only
                    or (path.is_dir() and not path.is_symlink())
                )
            ),
            key=lambda path: (path.name.casefold(), path.name),
        )
    except PermissionError:
        print(f"{prefix}└── [permission denied]")
        return

    for index, child in enumerate(children):
        is_directory = child.is_dir() and not child.is_symlink()
        last = index == len(children) - 1
        branch = "└── " if last else "├── "
        suffix = "/" if is_directory else ("@" if child.is_symlink() else "")
        print(f"{prefix}{branch}{child.name}{suffix}")
        if is_directory:
            print_tree(
                child,
                depth - 1,
                prefix + ("    " if last else "│   "),
                show_hidden,
                directories_only,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print files and directories as a Unicode tree."
    )
    parser.add_argument("depth", nargs="?", type=int, default=4,
                        help="Maximum directory depth below the root (default: 4).")
    parser.add_argument("--all", action="store_true",
                        help="Include hidden files and directories (except .git).")
    parser.add_argument("-d", "--dirs-only", "--directories-only",
                        dest="directories_only", action="store_true",
                        help="Show directories only.")
    args = parser.parse_args()
    if args.depth < 0:
        parser.error("depth must be non-negative")

    root = Path.cwd()
    print(f"{root.name}/" if root.name else "/")
    print_tree(root, args.depth, "", args.all, args.directories_only)


if __name__ == "__main__":
    main()
