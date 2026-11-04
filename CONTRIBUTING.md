# Contributing / development workflow

This project is currently distributed without an open-source license. Do not infer permission to redistribute or commercially reuse its code. If the repository owner later selects a license, this file can be updated with external contribution terms.

## Development

1. Make a branch from `main`.
2. Install dependencies: `python -m pip install -r requirements.txt`.
3. Run `python -m pytest tests/test_v4.py tests/test_v3.py -v` before submitting changes.
4. Document new UI controls in `docs/USER_GUIDE.md`, and add real browser screenshots if the interface changes.
5. Add a model-based or geometry regression test for every new layout rule.
6. Keep the source-of-truth `PropertyProject` JSON contract compatible or version it explicitly.
7. Do not commit API keys, tokens, architectural client data, personal project exports or `.env` files.

## Design quality

Tests must distinguish **known geometry invariants**, **architectural warnings**, and **design preferences**. Avoid changing a warning to a pass merely because a drawing looks nicer. No generated project should be advertised as certified or buildable without the relevant licensed professional review.
