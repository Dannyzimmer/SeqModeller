#!/usr/bin/env python3
"""
deploy.py: Build a Python script into a standalone executable using Nuitka inside Singularity,
and copy the resulting binary to one or more target directories, all driven by a JSON config.

Usage:
    ./deploy.py [--config deploy-config.json] [--dry-run] [--verbose] [--skip-pre-build]

Configuration file (JSON) example:
{
  "singularity_image": "/path/to/cli-deployment.sif",
  "deploy_dirs": [
    "/opt/apps/EnvHandler",
    "/home/user/bin"
  ],
  "pre_build": {
    "enabled": true,
    "script": "build_resources.py",
    "working_directory": ".",
    "args": ["--compile-ui", "--compile-resources"]
  },
  "nuitka": {
    "remove_output": true,
    "lto": false,
    "onefile": true,
    "static_libpython": false,
    "output_dir": "dist",
    "output_filename": "myCli",
    "script": "myCli.py",
    "other_flags": [
      "--include-data-files=config_template.json={MAIN_DIRECTORY}/somefile.txt",
      "--include-data-dir=GUI=GUI",
      "--enable-plugin=pyqt6"
    ]
  }
}
"""

import json
import subprocess
import sys
import argparse
from pathlib import Path

def validate_data_dependencies(other_flags):
    """Validate that data files and directories referenced in other_flags exist"""
    warnings = []
    
    for flag in other_flags:
        if flag.startswith("--include-data-files="):
            # Extract file path (before the = in the value part)
            data_spec = flag.split("=", 1)[1]
            source_file = data_spec.split("=")[0]
            
            if not Path(source_file).exists():
                warnings.append(f"Warning: Data file '{source_file}' does not exist")
        
        elif flag.startswith("--include-data-dir="):
            # Extract directory path (before the = in the value part)
            data_spec = flag.split("=", 1)[1]
            source_dir = data_spec.split("=")[0]
            
            if not Path(source_dir).exists():
                warnings.append(f"Warning: Data directory '{source_dir}' does not exist")
    
    return warnings

def run_pre_build_script(pre_build_config, dry_run=False, verbose=False):
    """Execute pre-build script if configured"""
    if not pre_build_config.get("enabled", False):
        return True
    
    script = pre_build_config.get("script")
    if not script:
        print("Warning: pre_build enabled but no script specified")
        return True
    
    script_path = Path(script)
    if not script_path.exists():
        print(f"Error: Pre-build script '{script}' not found", file=sys.stderr)
        return False
    
    working_dir = Path(pre_build_config.get("working_directory", "."))
    args = pre_build_config.get("args", [])
    
    print(f"Running pre-build script: {script}")
    if verbose:
        print(f"Working directory: {working_dir}")
        print(f"Arguments: {args}")
    
    if dry_run:
        print("DRY RUN: Would execute pre-build script")
        return True
    
    # Determine how to execute the script based on extension
    if script_path.suffix == ".py":
        cmd = ["python3", str(script_path)] + args
    elif script_path.suffix in [".sh", ".bash"]:
        cmd = ["bash", str(script_path)] + args
    else:
        # Try to execute directly
        cmd = [str(script_path)] + args
    
    if verbose:
        print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd, 
            cwd=working_dir,
            capture_output=not verbose,
            text=True,
            check=True
        )
        
        if verbose and result.stdout:
            print("Pre-build script output:")
            print(result.stdout)
            
        print("Pre-build script completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error: Pre-build script failed with exit code {e.returncode}", file=sys.stderr)
        if e.stdout:
            print("STDOUT:", e.stdout, file=sys.stderr)
        if e.stderr:
            print("STDERR:", e.stderr, file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error: Failed to execute pre-build script: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Build Python script with Nuitka and deploy to target directories"
    )
    parser.add_argument(
        "--config", 
        default="deploy-config.json",
        help="Configuration file path (default: deploy-config.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose output"
    )
    parser.add_argument(
        "--skip-pre-build",
        action="store_true",
        help="Skip pre-build script execution"
    )
    
    args = parser.parse_args()
    
    config_file = Path(args.config)
    if not config_file.is_file():
        print(f"Error: {config_file} does not exist", file=sys.stderr)
        sys.exit(1)

    try:
        cfg = json.loads(config_file.read_text())
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_file}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Could not read {config_file}: {e}", file=sys.stderr)
        sys.exit(1)

    # Execute pre-build script if configured and not skipped
    if not args.skip_pre_build:
        pre_build_config = cfg.get("pre_build", {})
        if not run_pre_build_script(pre_build_config, args.dry_run, args.verbose):
            print("Pre-build script failed, aborting deployment", file=sys.stderr)
            sys.exit(1)

    # Validate singularity image
    sif = Path(cfg.get("singularity_image", ""))
    if not sif.is_file():
        print(f"Error: Singularity image '{sif}' not found", file=sys.stderr)
        sys.exit(1)

    # Validate deploy directories
    deploy_dirs = cfg.get("deploy_dirs", [])
    if not isinstance(deploy_dirs, list):
        print("Error: 'deploy_dirs' must be an array in the JSON", file=sys.stderr)
        sys.exit(1)

    nuitka_cfg = cfg.get("nuitka", {})
    
    # Validate script exists
    script = nuitka_cfg.get("script")
    if not script:
        print("Error: 'script' must be specified in nuitka configuration", file=sys.stderr)
        sys.exit(1)
    
    if not Path(script).exists():
        print(f"Error: Script '{script}' does not exist", file=sys.stderr)
        sys.exit(1)
    
    # Build Nuitka flags
    flags = []
    if nuitka_cfg.get("remove_output", False):
        flags.append("--remove-output")
    if nuitka_cfg.get("lto", False):
        flags.append("--lto=yes")
    else:
        flags.append("--lto=no")
    if nuitka_cfg.get("onefile", False):
        flags.append("--onefile")
    if nuitka_cfg.get("static_libpython", True) is False:
        flags.append("--static-libpython=no")
    
    out_dir = nuitka_cfg.get("output_dir", "dist")
    out_name = nuitka_cfg.get("output_filename")
    if not out_name:
        print("Error: 'output_filename' must be specified in nuitka configuration", file=sys.stderr)
        sys.exit(1)
    
    flags += [f"--output-dir={out_dir}", f"--output-filename={out_name}"]
    
    # Add other flags
    other_flags = nuitka_cfg.get("other_flags", [])
    if not isinstance(other_flags, list):
        print("Error: 'other_flags' must be an array", file=sys.stderr)
        sys.exit(1)
    
    # Validate data dependencies
    warnings = validate_data_dependencies(other_flags)
    if warnings and args.verbose:
        for warning in warnings:
            print(warning)
    
    for flag in other_flags:
        flags.append(flag)

    # Create output directory
    if not args.dry_run:
        Path(out_dir).mkdir(parents=True, exist_ok=True)

    print(f"Compiling with Nuitka: {script}")
    if args.verbose:
        print(f"Flags: {' '.join(flags)}")
    
    # Build Nuitka command
    cmd = [
        "singularity", "exec", "--cleanenv",
        "--bind", f"{Path.cwd()}:/workspace/",
        str(sif),
        "bash", "-lc",
        f"cd /workspace/ && python3 -m nuitka {' '.join(flags)} {script}"
    ]
    
    if args.verbose:
        print(f"Command: {' '.join(cmd)}")
    
    if args.dry_run:
        print("DRY RUN: Would execute Nuitka compilation")
    else:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print("Error: Nuitka compilation failed", file=sys.stderr)
            sys.exit(result.returncode)

    exec_path = Path(out_dir) / out_name
    if not args.dry_run and not exec_path.exists():
        print(f"Error: executable not found at '{exec_path}'", file=sys.stderr)
        sys.exit(1)

    # Deploy to target directories
    for d in deploy_dirs:
        dest = Path(d)
        print(f"{'Would copy' if args.dry_run else 'Copying'} '{exec_path}' to '{dest}'")
        
        if not args.dry_run:
            try:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / exec_path.name).write_bytes(exec_path.read_bytes())
            except Exception as e:
                print(f"Error copying to {dest}: {e}", file=sys.stderr)
                sys.exit(1)
    
    print("Deployment completed successfully!" if not args.dry_run else "DRY RUN completed!")

if __name__ == "__main__":
    main()