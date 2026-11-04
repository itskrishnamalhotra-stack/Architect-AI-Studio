#!/usr/bin/env python3
"""Publish the complete Architect AI Studio V4.1 project to its GitHub repository.

Run from anywhere:
    py scripts/publish_github.py

Requires Git installed (https://git-scm.com/downloads). Git Credential Manager
may open a browser to sign in the first time. Does not require a GitHub PAT,
install third-party Python packages, or manually select individual files.

Optional dry-run:
    py scripts/publish_github.py --dry-run

This script only ever targets its named repository, and refuses an unexpected
existing 'origin' remote. Never include credentials in the repository itself.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

OWNER_REPO = 'itskrishnamalhotra-stack/Architect-AI-Studio'
URL = f'https://github.com/{OWNER_REPO}.git'
ROOT = Path(__file__).resolve().parent.parent


def git(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ['git', *args], cwd=ROOT, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if check and proc.returncode:
        if capture and proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        raise RuntimeError(f'Git command failed: git {" ".join(args)}')
    return proc


def main() -> int:
    parser = argparse.ArgumentParser(description='Publish Architect AI Studio V4.1 to GitHub.')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be published without committing or pushing')
    args = parser.parse_args()

    if not shutil.which('git'):
        print('Git is not installed. Install Git for Windows: https://git-scm.com/downloads/win', file=sys.stderr)
        return 2
    if not (ROOT / 'app.py').is_file() or not (ROOT / 'README.md').is_file():
        print('Not in the complete project folder. Extract the full ZIP before running this script.', file=sys.stderr)
        return 2
    print(f'Project: {ROOT}\nDestination: https://github.com/{OWNER_REPO}')

    if (ROOT / '.git').exists():
        repo_root = git('rev-parse', '--show-toplevel', capture=True)
        if repo_root.returncode or Path(repo_root.stdout.strip()).resolve() != ROOT.resolve():
            print('Refusing: the existing .git directory points to a different project.', file=sys.stderr)
            return 2
        origin = git('remote', 'get-url', 'origin', check=False, capture=True)
        if origin.returncode == 0 and origin.stdout.strip() != URL:
            print(f'Refusing: existing origin is {origin.stdout.strip()!r} (expected {URL!r}).', file=sys.stderr)
            return 2
    elif not args.dry_run:
        git('init', '-b', 'main')

    if args.dry_run and not (ROOT / '.git').exists():
        files = [p for p in ROOT.rglob('*') if p.is_file()
                 and not any(part in {'.git', '__pycache__', '.pytest_cache', '.venv'} for part in p.relative_to(ROOT).parts)]
        print(f'Preview only: approximately {len(files)} source and example files (see .gitignore for exclusions).')
        return 0

    git('add', '-A')
    tracked = git('ls-files', '-z', capture=True).stdout.split('\0')
    tracked = [s for s in tracked if s]
    unsafe = [s for s in tracked if Path(s).name in {'.env', 'id_rsa', 'id_ed25519'}
              or (Path(s).name.startswith('.env.') and s != '.env.example')]
    if unsafe:
        print('Refusing: possible secrets staged: ' + ', '.join(unsafe), file=sys.stderr)
        return 2
    print(f'Files staged/tracked: {len(tracked)}')
    if args.dry_run:
        print('Preview only—no commit or push.')
        return 0
    origin = git('remote', 'get-url', 'origin', check=False, capture=True)
    if origin.returncode != 0:
        git('remote', 'add', 'origin', URL)

    changes = git('diff', '--cached', '--quiet', check=False)
    if changes.returncode == 1:
        commit = git('commit', '-m', 'Publish Architect AI Studio V4.1, user guide, screenshots, examples and tests', check=False)
        if commit.returncode:
            print('Cannot commit. Set your Git identity, then rerun:\n'
                  'git config --global user.name "Your Name"\n'
                  'git config --global user.email "your-github-email@example.com"', file=sys.stderr)
            return 2
    elif changes.returncode != 0:
        print('Unable to inspect staged changes.', file=sys.stderr)
        return 2
    git('branch', '-M', 'main')
    print('Uploading to GitHub. If prompted, complete the GitHub sign-in in your browser...')
    pushed = git('push', '-u', 'origin', 'main', check=False)
    if pushed.returncode:
        print('GitHub push did not succeed. Check your internet connection and sign in via Git Credential Manager, then rerun.', file=sys.stderr)
        return 3
    print(f'Published successfully: https://github.com/{OWNER_REPO}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f'Publishing failed: {exc}', file=sys.stderr)
        raise SystemExit(2)
