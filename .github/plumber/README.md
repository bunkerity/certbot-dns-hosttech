# Plumber

The reusable workflow scans GitHub Actions on every PR and main push through `tests.yml`, and weekly on its own schedule. The gate requires grade B or better (`soft-fail: false`). `.plumber.yaml` extends the upstream default policy without disabling controls or broadening trust lists.

Every external action is pinned to a full commit. Plumber's binary version is explicit and its SLSA attestation is verified. The job uploads JSON, SARIF, PBOM and CycloneDX evidence as run artifacts. SARIF upload is off on pull requests. Public score publishing is off on pull requests and private repositories.

CodeQL analyzes Python source. OpenSSF Scorecard runs on public main pushes, weekly and branch-protection changes. Dependabot groups weekly updates for GitHub Actions and Python dependencies.

Local scan results cannot prove hosted permissions, branch protection or public score publishing. Before making this repository public, maintainers must configure main-branch protection, required CI checks and security features in GitHub. No repository settings are changed by these files.
