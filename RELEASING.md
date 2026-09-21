# Releasing dot.Flip

Releases are tags on `main`, published as GitHub Releases with the installer attached.
Versions follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

## Steps

1. **Merge** everything for the release into `main`, then update your checkout:
   ```
   git checkout main
   git pull
   ```
2. **Set the version** in `pyproject.toml` (`version = "X.Y.Z"`), commit it, and merge it via a PR.
3. **Run the tests:**
   ```
   .venv\Scripts\python -m pytest
   ```
4. **Build the installer** (see [Build from source](README.md#build-from-source) for prerequisites):
   ```
   powershell -ExecutionPolicy Bypass -File tools\build_release.ps1 -Version X.Y.Z
   ```
   The output is `dist\DotFlip-Setup-X.Y.Z.exe`.
5. **Test the installer** on a clean Windows 11 machine or VM: install, check the right-click menu
   (one "Convert to" entry, all formats, scale options), convert a few files, then uninstall and
   reinstall to confirm the menu is not duplicated.
6. **Tag and push:**
   ```
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
7. **Publish the release** on GitHub: *Releases* > *Draft a new release*, choose the `vX.Y.Z` tag, click
   *Generate release notes*, attach `DotFlip-Setup-X.Y.Z.exe`, and publish.

## Release notes

GitHub generates the notes from the pull requests merged since the previous release. They are grouped
by label as configured in [`.github/release.yml`](.github/release.yml):

| Label | Section |
| --- | --- |
| `enhancement` | New features |
| `bug` | Fixes |
| anything else | Other changes |

Add `ignore-for-release` to a PR to leave it out of the notes.

## Patching an older version

Normally fixes ship from `main` as the next release. If `main` has moved on and an older version needs
a fix, branch from its tag (`git checkout -b release-1.0 v1.0.0`), apply the fix, and tag a patch release
from that branch.
