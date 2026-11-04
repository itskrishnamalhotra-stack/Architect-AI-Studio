# GitHub publication status — Architect AI Studio V4.1

**Published repository:** https://github.com/itskrishnamalhotra-stack/Architect-AI-Studio  
**Default branch:** main  
**Visibility:** public

The V4.1 application, user guides, interface screenshots, 35 generated example cases, 92-page catalog PDF, source files, and tests were published on 4 November 2026. You do **not** need to upload an extracted ZIP or repeat the initial publishing procedure.

## Verify the current release

1. Open the repository and browse `architect/`, `static/`, `docs/`, `tests/`, `examples/` and `showcase/catalog/`.
2. Open the **Actions → Tests** workflow. A green check means Python regression tests and repository-file integrity checks completed successfully for that commit. Failed checks are linked to diagnostic logs.
3. Read the installation and usage steps in `README.md` and `docs/USER_GUIDE.md`.
4. Use the PNG gallery in `docs/SCREENSHOTS.md` and the example index in `docs/EXAMPLE_CATALOG.md`.

## Future source updates

Work in a clone of the published repository, commit changes, and push through an authenticated GitHub connection. The former `scripts/publish_github.py` is retained as a legacy initial-upload utility, **not** something to run against an already populated repository without reviewing its effects. Do not force-push over existing commits.

The repository is public, but no open-source `LICENSE` was added. Redistribution and reuse permissions require a deliberate license choice. Keep API keys, private plans, access tokens and third-party proprietary CAD files out of Git.
