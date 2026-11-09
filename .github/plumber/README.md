# Plumber

The reusable workflow scans GitHub Actions on every PR and main push through `tests.yml`, and weekly on its own schedule. The gate requires grade B or better (`soft-fail: false`). `.plumber.yaml` extends the upstream default policy without disabling controls. Its only change adds `softprops/action-gh-release` to the trusted action sources, because `release.yml` creates the GitHub release with it (pinned to a full commit), the same exception `bunkerity/bunkerweb-mcp` carries.

Every external action is pinned to a full commit. Plumber's binary version is explicit and its SLSA attestation is verified. The job uploads JSON, SARIF, PBOM and CycloneDX evidence as run artifacts. SARIF upload is off on pull requests. Public score publishing is off on pull requests and private repositories.

CodeQL analyzes Python source and uploads pull request findings to code scanning; its database upload stays off on pull requests. Plumber's SARIF and public score publishing stay off on pull requests. Offline Atheris fuzzing runs through `tests.yml` and in longer weekly batches with read-only repository access. OpenSSF Scorecard runs on public main pushes, weekly and branch-protection changes. Dependabot groups weekly updates for GitHub Actions and Python dependencies.

Local scan results cannot prove hosted permissions, branch protection or public score publishing. Before making this repository public, maintainers must configure main-branch protection, required CI checks and security features in GitHub. No repository settings are changed by these files.
