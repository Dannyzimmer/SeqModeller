# Build System Documentation

This document explains the automated build system for SeqModeller, including pre-build scripts and deployment configuration.

## Overview

The build system consists of:
- **Pre-build script** (`build_resources.py`): Compiles UI files and resources
- **Deploy script** (`deploy.py`): Packages the application using Nuitka
- **Configuration file** (`deploy-config.json`): Controls the entire build process

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install PyQt6 PyQt6-tools
   ```

2. **Run the build**:
   ```bash
   python deploy.py --verbose
   ```

## Pre-build Script (build_resources.py)

### Features
- ✅ Compiles `.ui` files to `.py` files using `pyuic6`
- ✅ Compiles `.qrc` files to `.py` files using `pyrcc6` or `pyside6-rcc`
- ✅ Checks for required dependencies
- ✅ Creates UI imports module for easier access
- ✅ Supports verbose output for debugging

### Usage
```bash
# Run all build steps (default)
python build_resources.py

# Run specific steps
python build_resources.py --compile-ui --verbose
python build_resources.py --compile-resources
python build_resources.py --check-deps

# Verbose output
python build_resources.py --all --verbose
```

### Generated Files
- `GUI/*_ui.py`: Compiled UI files
- `*_rc.py`: Compiled resource files (if .qrc files exist)
- `GUI/__init__.py`: Auto-generated imports module

## Deploy Script (deploy.py)

### New Features
- ✅ **Pre-build script execution**: Automatically runs preparation scripts
- ✅ **Flexible script support**: Python, Bash, or executable scripts
- ✅ **Error handling**: Stops deployment if pre-build fails
- ✅ **Skip option**: `--skip-pre-build` flag to bypass pre-build
- ✅ **Verbose output**: Shows pre-build script output

### Usage
```bash
# Normal deployment (includes pre-build)
python deploy.py --verbose

# Skip pre-build step
python deploy.py --skip-pre-build

# Dry run (see what would happen)
python deploy.py --dry-run --verbose

# Use custom config
python deploy.py --config my-deploy-config.json
```

## Configuration (deploy-config.json)

### Pre-build Section
```json
{
  "pre_build": {
    "enabled": true,
    "script": "build_resources.py",
    "working_directory": ".",
    "args": ["--all", "--verbose"]
  }
}
```

#### Options:
- **`enabled`**: Whether to run pre-build script
- **`script`**: Path to the script to execute
- **`working_directory`**: Directory to run script from
- **`args`**: Arguments to pass to the script

### Supported Script Types
- **Python scripts** (`.py`): Executed with `python3`
- **Bash scripts** (`.sh`, `.bash`): Executed with `bash`
- **Executables**: Executed directly

## Workflow

1. **Pre-build phase**:
   - Check dependencies
   - Compile `.ui` files to `.py`
   - Compile `.qrc` files to `.py` (if available)
   - Create UI imports module

2. **Build phase**:
   - Validate configuration
   - Run Nuitka compilation inside Singularity
   - Include compiled UI files and resources

3. **Deploy phase**:
   - Copy executable to target directories

## Dependencies

### Required
- `PyQt6`: Core GUI framework
- `python3`: Python interpreter

### Optional (for full functionality)
- `PyQt6-tools`: Provides `pyuic6` for UI compilation
- `PySide6`: Alternative resource compiler (`pyside6-rcc`)

### Installation
```bash
# Minimal (manual UI compilation required)
pip install PyQt6

# Full functionality (recommended)
pip install PyQt6 PyQt6-tools
```

## Troubleshooting

### "pyuic6 not found"
```bash
pip install PyQt6-tools
```

### "pyrcc6 not found"
```bash
# Try one of these:
pip install PyQt6-tools
pip install PySide6
```

### Pre-build script fails
```bash
# Run pre-build manually to debug
python build_resources.py --verbose

# Skip pre-build if needed
python deploy.py --skip-pre-build
```

### UI files not updating
```bash
# Force recompilation
python build_resources.py --compile-ui --verbose
```

## Best Practices

1. **Always run with `--verbose`** during development for debugging
2. **Test pre-build script separately** before running full deployment
3. **Keep UI files in `GUI/` directory** for automatic discovery
4. **Use version control** to track generated files if needed
5. **Include generated files in `.gitignore`** if they're automatically built

## File Structure

```
project/
├── deploy-config.json      # Build configuration
├── deploy.py              # Main deploy script
├── build_resources.py     # Pre-build script
├── main.py               # Application entry point
├── resources.qrc         # Resource definitions (optional)
├── GUI/
│   ├── app.ui           # UI definitions
│   ├── about.ui
│   ├── insert_form.ui
│   ├── app_ui.py        # Generated (compiled UI)
│   ├── about_ui.py      # Generated
│   ├── insert_form_ui.py # Generated
│   └── __init__.py      # Generated (imports)
├── images/
│   └── icon.ico         # Application icon
└── dist/                # Build output
    └── SeqModeller    # Final executable
```

## Examples

### Minimal Configuration
```json
{
  "pre_build": {
    "enabled": false
  },
  "nuitka": {
    "script": "main.py",
    "output_filename": "myapp"
  }
}
```

### Full Configuration
```json
{
  "pre_build": {
    "enabled": true,
    "script": "build_resources.py",
    "working_directory": ".",
    "args": ["--all", "--verbose"]
  },
  "nuitka": {
    "remove_output": true,
    "onefile": true,
    "script": "main.py",
    "output_filename": "myapp",
    "other_flags": [
      "--include-data-dir=GUI=GUI",
      "--include-data-dir=images=images",
      "--enable-plugin=pyqt6"
    ]
  }
}
```