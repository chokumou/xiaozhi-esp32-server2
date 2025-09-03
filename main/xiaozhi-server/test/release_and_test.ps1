Param()

Write-Host "This script will: commit any changes, push to master, trigger redeploy by empty commit, and run local tests."

$root = Split-Path -Parent $MyInvocation.MyCommand.Definition | Split-Path -Parent
Write-Host "Repo root: $root"

Push-Location $root

Write-Host "Staging changes..."
git add -A

if ((git status --porcelain) -eq "") {
    Write-Host "No local changes to commit. Creating empty commit to trigger deploy."
    git commit --allow-empty -m "ci: trigger redeploy"
} else {
    git commit -m "chore: automated commit for release_and_test"
}

Write-Host "Pushing to origin master..."
git push origin HEAD:master

Write-Host "Triggering redeploy by creating empty commit and pushing"
git commit --allow-empty -m "ci: trigger redeploy"
git push origin HEAD:master

Write-Host "Waiting 5 seconds for remote to pick up..."
Start-Sleep -Seconds 5

Write-Host "Now running local test runner..."
Push-Location -Path (Join-Path $root "main\xiaozhi-server\test")
.\run_full_test.ps1
Pop-Location

Pop-Location

Write-Host "Done. Check test_logs for details."


