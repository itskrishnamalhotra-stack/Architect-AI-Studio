# Publishes this project to the owner's EXISTING public GitHub repository.
# Run from the extracted project root. Requires Git for Windows + GitHub sign-in.
$ErrorActionPreference = 'Stop'
$repo = 'itskrishnamalhotra-stack/Architect-AI-Studio'
$target = "https://github.com/$repo.git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows: https://git-scm.com/downloads/win' }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot
if (-not (Test-Path .git)) {
    git init -b main
    if ($LASTEXITCODE -ne 0) { throw 'Git initialization failed.' }
}
$existingOrigin = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
    if ($existingOrigin.Trim() -ne $target) { throw "Existing origin is $existingOrigin, not $target. Refusing to push to an unexpected repository." }
} else {
    git remote add origin $target
    if ($LASTEXITCODE -ne 0) { throw 'Could not set GitHub remote.' }
}
git add -A
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m 'Initial release: Architect AI Studio V4.1 with examples and docs'
    if ($LASTEXITCODE -ne 0) { throw 'Git commit failed. Configure git user.name and user.email and retry.' }
}
git branch -M main
if ($LASTEXITCODE -ne 0) { throw 'Cannot switch branch to main.' }
git push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'Push failed. Complete browser sign-in in Git Credential Manager, then rerun.' }
Write-Host "Published: https://github.com/$repo"
