# Publish Architect AI Studio to GitHub (public repository)

The public GitHub repository already exists: [itskrishnamalhotra-stack/Architect-AI-Studio](https://github.com/itskrishnamalhotra-stack/Architect-AI-Studio). This ZIP is the tested V4.1 project source. Upload the **extracted folder contents**, not the ZIP itself, to make code, screenshots, tests, and examples navigable online.

## Simplest Windows method (existing empty repository)

1. Download and extract the [repository-ready project ZIP](../README.md) to your Windows computer.
2. Install [Git for Windows](https://git-scm.com/downloads/win) if you have not already.
3. Open PowerShell inside the extracted `Architect_AI_Studio_V4_1` folder.
4. Run the **Python uploader**:

```powershell
py scripts/publish_github.py
```

To preview the process without publishing, use `py scripts/publish_github.py --dry-run`. If you prefer the PowerShell version, use `powershell -ExecutionPolicy Bypass -File .\scripts\publish_github.ps1`.

Git Credential Manager should offer a browser-based GitHub sign-in if required. The Python script creates a local commit, verifies the exact target repository URL, and pushes all tracked project files to `main`. It was tested against a local bare Git repository with both text and binary files. It never stores or asks you to paste an API token into the project.

## macOS / Linux

```bash
bash scripts/publish_github.sh
```

## Manual commands (if you prefer)

```bash
git init -b main
git add -A
git commit -m "Initial release: Architect AI Studio V4.1"
git remote add origin https://github.com/itskrishnamalhotra-stack/Architect-AI-Studio.git
git push -u origin main
```

If the repository is no longer empty, do **not** force-push over its content; reconcile the existing changes before proceeding.

## After uploading

- Open [the repository](https://github.com/itskrishnamalhotra-stack/Architect-AI-Studio) and check README screenshot previews.
- Confirm `architect/`, `static/`, `tests/`, `docs/screenshots/` and `showcase/catalog/` are present.
- Open **Actions → Tests**; the CI run's status, not the historical local results, indicates whether GitHub's environment passes.
- No `LICENSE` was added intentionally. A public repository is visible, but it is **not automatically open-source licensed**; select a license after reviewing intended commercial rights and any third-party material.
- Never publish API keys, client floor plans, private access tokens, or proprietary third-party CAD files.

## If Git reports an author error

```bash
git config --global user.name "Your GitHub display name"
git config --global user.email "Your GitHub commit email"
```

Then rerun the script. To keep your personal email private, GitHub offers a no-reply commit address in its email settings.
