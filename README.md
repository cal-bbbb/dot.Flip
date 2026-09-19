# dot.Flip

An open-source image file-type converter for Windows.

Right-click any image in Explorer → **Convert to ▸ PNG / JPEG / TIFF / GIF / WebP / BMP / ICO / AVIF**,
or open the desktop app to batch-convert with full control over quality, resizing, naming and output.

- **Reads:** PNG, JPEG, TIFF, GIF, WebP, BMP, ICO, AVIF, HEIC/HEIF, SVG
- **Writes:** PNG, JPEG, TIFF, GIF, WebP, BMP, ICO, AVIF
- Works in the Windows 11 right-click menu *and* the classic menu
- Transparency is flattened onto a colour you choose when the target has no alpha; animated GIF/WebP stay animated
- Originals are never deleted unless you ask; existing files are never overwritten unless you ask

## Install
Download **DotFlip-Setup-x.y.z.exe** from the [latest release](https://github.com/cal-bbbb/dot.Flip/releases/latest)
and run it. Windows may show a SmartScreen warning because the installer is not yet signed by a commercial
certificate: choose **More info → Run anyway**. Setup asks for administrator rights only to trust the package that
adds dot.Flip to the Windows 11 menu.

## Use
- **Right-click** one or more images → **Convert to** → pick a format. (On Windows 10, or under *Show more options*
  on Windows 11, the same submenu is in the classic menu.) **Options ▸ Scale: 100% / 50%** sets the size of right-click conversions (the choice is remembered).
  **More options…** opens the app with the files loaded.
- **App:** drag in files or folders, choose a format, tune options, press Convert.
- **Command line:** `DotFlip.exe --to webp --quality 80 photo.png` (see `--help`).

## Build from source
Requirements: Python 3.10+, Visual Studio Build Tools (C++ workload) + Windows SDK, Inno Setup 6
(`winget install JRSoftware.InnoSetup`).
```
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m pytest
.venv\Scripts\python -m dotflip.cli            # run the GUI from source
powershell -ExecutionPolicy Bypass -File tools\build_release.ps1 -Version 1.0.0
```
Output: `dist\DotFlip-Setup-1.0.0.exe`. The script builds the PyInstaller bundle, the C++ shell extension
(`shellext/`), a signed sparse MSIX package, and the installer (`installer/DotFlip.iss`).

## How the right-click menus work
- **Windows 11 top-level menu:** `shellext/DotFlipMenu.cpp` is a small native `IExplorerCommand` COM handler,
  registered through a *sparse MSIX package* (`shellext/AppxManifest.xml.in`). Windows only loads such handlers
  for packages with identity, and packages must be signed.
- **Classic menu:** per-user registry verbs, see `src/dotflip/shell/register.py`.

## Code signing
By default `build_release.ps1` creates a self-signed certificate (`CN=DotFlip`) in the *builder's* certificate store
and the installer trusts it on the user's machine. The private key stays on the builder's machine and must never be
committed. For wider distribution use a real code-signing certificate (`-CertThumbprint`, with a matching
`-Publisher`) or an OSS signing service such as SignPath.

## License
MIT, see [LICENSE](LICENSE). Bundled libraries (Pillow, pillow-heif, resvg-py, PySide6 under LGPL) keep their own licenses.
