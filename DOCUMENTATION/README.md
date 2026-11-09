# miniTRASGO Documentation

This MkDocs documentation is part of the `mingo-computing` repository and lives in `DOCUMENTATION/`.

## Location in this repository

```text
mingo-computing/
├── DOCUMENTATION/
│   ├── REFERENCE/
│   ├── mkdocs.yml
│   └── docs/
├── CONTEXTUAL/CONFIG/CONTENTS/packages/
│   └── docs-requirements.txt
└── .github/workflows/deploy-documentation.yml
```

## Contributing

Contributions are made through pull requests against the main repository.

1. Fork the main repository.
2. Edit Markdown pages under `DOCUMENTATION/docs/` and, when needed, update navigation in `DOCUMENTATION/mkdocs.yml`.
3. Open a pull request targeting the default branch.

You can also use GitHub's web editor for quick text fixes in `DOCUMENTATION/docs/`.

Repository guides and component-specific manuals that are not part of the published site are collected in [REFERENCE](REFERENCE/README.md), organized by their original repository component.

## Build and serve locally

```bash
cd DOCUMENTATION
python -m venv .venv
source .venv/bin/activate
pip install -r ../CONTEXTUAL/CONFIG/CONTENTS/packages/docs-requirements.txt
mkdocs serve
```

To build the static site locally:

```bash
cd DOCUMENTATION
source .venv/bin/activate
mkdocs build
```

The generated site is written to `DOCUMENTATION/site/`.

## Deployment Process

The documentation site is deployed from this repository via GitHub Actions and GitHub Pages.

- Workflow: `.github/workflows/deploy-documentation.yml`
- Trigger: push to `main` and manual `workflow_dispatch`
- Build source: `DOCUMENTATION/`
- Published artifact: `DOCUMENTATION/site/`
- Hosted URL: <https://csoneira.github.io/mingo-computing/>

## Troubleshooting

- Ensure new pages are included in `DOCUMENTATION/mkdocs.yml` navigation.
- If deployment fails, inspect the latest GitHub Actions run for the workflow above.
