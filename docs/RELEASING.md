# Releasing

One version covers every supported laptop: new hardware arrives as a minor
release of the same package, never as a separate per-model build.

## Version numbers

- **Patch** (`0.1.1`): fixes with no new hardware or features.
- **Minor** (`0.2.0`): a newly validated laptop model, a newly allow-listed
  effect, or a new feature.
- **Major** (`1.0.0`): reserved for the first release considered stable.
- **Beta** (`0.1.0b1`, `0.1.0b2`): a `bN` suffix marks a pre-release. Python
  and pacman both sort it before the plain `0.1.0`.

## Cutting a release

1. Set the new version in `pyproject.toml` and `src/aero_keyboard/__init__.py`.
2. Run the tests: `.venv/bin/pytest`.
   If the interface changed, refresh the README screenshots:
   `QT_SCALE_FACTOR=2 .venv/bin/python scripts/make-screenshots.py`.
3. Commit, then tag and push:

   ```bash
   git tag v0.1.0b1
   git push origin main v0.1.0b1
   ```

   The `Release` workflow checks that the tag matches the package version,
   runs the tests, and publishes a GitHub release with the wheel attached.

## Updating the Arch package

`packaging/arch/PKGBUILD` builds the tagged release.

1. Set `pkgver` in `packaging/arch/PKGBUILD` to the new version and reset
   `pkgrel` to `1`.
2. Fill in the tarball checksum and test the build:

   ```bash
   cd packaging/arch
   updpkgsums            # from the pacman-contrib package
   makepkg -si
   ```

3. Commit and push the updated `PKGBUILD`.

`packaging/arch-git/PKGBUILD` follows `main`, so it only needs changing when
its dependencies or install steps change.

## One-line installer

`scripts/install.sh` installs the newest GitHub release, or `main` when no
release exists yet. It needs no change per release.
