# Image to LEGO Converter

Convert any image into a 3D-printable LEGO-style STL model. Available as a desktop app for macOS and Windows.

## Download

Grab the latest release from the [Actions tab](https://github.com/aakashmehra/Image-to-LEGO/actions) — download the artifact for your platform after a successful build.

## Installation

### macOS

1. Open the `.dmg` and drag the app to your Applications folder.
2. **First launch only:** macOS will block the app because it isn't from a paid Apple developer account.
   - Right-click (or Control-click) the app → **Open**
   - Click **Open** in the dialog that appears
3. From then on, just double-click to open normally.

### Windows

1. Run the `.exe` installer.
2. **First launch only:** Windows SmartScreen may show a warning.
   - Click **More info** → **Run anyway**
3. The installed app will open normally from that point on.

> These one-time prompts appear because the app is not commercially code-signed. The app itself is safe — you can inspect the full source code in this repo.

## Development

### Prerequisites

- [Node.js](https://nodejs.org/) 20+
- [Rust](https://www.rust-lang.org/tools/install)
- Python 3 with `pip install pillow trimesh numpy`

### Run locally

```bash
npm install
npm run tauri dev
```

`cli_convert.py` must be present in the parent `APStudios/` directory (it's automatically found at dev time).

### Build a release locally

```bash
# 1. Build the Python sidecar
pip install pyinstaller
pyinstaller ../cli_convert.spec

# 2. Copy binary with the correct target-triple name (macOS arm64 example)
cp dist/cli_convert src-tauri/binaries/cli_convert-aarch64-apple-darwin

# 3. Build the Tauri app
npm run tauri build
```

Output is in `src-tauri/target/release/bundle/`.
