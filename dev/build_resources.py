#!/usr/bin/env python3
"""
Pre-build script for SeqModeller.
Compiles UI files and resources before packaging.

Usage:
    python build_resources.py [--compile-ui] [--compile-resources] [--verbose]
"""

import argparse
import subprocess
import sys
from pathlib import Path
import shutil

def check_command_available(command):
    """Check if a command is available in the system"""
    return shutil.which(command) is not None

def compile_ui_files(verbose=False):
    """Compile all .ui files to .py files"""
    print("Compiling UI files...")
    
    # Check if pyuic6 is available
    if not check_command_available("pyuic6"):
        print("Warning: pyuic6 not found. UI files will not be compiled.")
        print("Install with: pip install PyQt6-tools")
        return False
    
    gui_dir = Path("GUI")
    if not gui_dir.exists():
        print("Warning: GUI directory not found")
        return True
    
    ui_files = list(gui_dir.glob("*.ui"))
    if not ui_files:
        print("No .ui files found in GUI directory")
        return True
    
    success = True
    for ui_file in ui_files:
        # Create output filename: app.ui -> app_ui.py
        py_file = gui_dir / f"{ui_file.stem}_ui.py"
        
        cmd = ["pyuic6", "-o", str(py_file), str(ui_file)]
        
        if verbose:
            print(f"Compiling {ui_file} -> {py_file}")
            print(f"Command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=not verbose,
                text=True,
                check=True
            )
            
            if verbose and result.stdout:
                print(result.stdout)
                
            print(f"✓ Compiled {ui_file.name}")
            
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to compile {ui_file.name}: {e}")
            if e.stderr:
                print(f"Error: {e.stderr}")
            success = False
        except Exception as e:
            print(f"✗ Unexpected error compiling {ui_file.name}: {e}")
            success = False
    
    return success

def compile_resources(verbose=False):
    """Compile .qrc files to .py files"""
    print("Compiling resource files...")
    
    # Check for available resource compilers
    compilers = ["pyrcc6", "pyside6-rcc"]
    compiler = None
    
    for cmd in compilers:
        if check_command_available(cmd):
            compiler = cmd
            break
    
    if not compiler:
        print("Warning: No resource compiler found (pyrcc6 or pyside6-rcc)")
        print("Install with: pip install PyQt6-tools or pip install PySide6")
        return False
    
    # Look for .qrc files
    qrc_files = list(Path(".").glob("*.qrc"))
    if not qrc_files:
        print("No .qrc files found")
        return True
    
    success = True
    for qrc_file in qrc_files:
        # Create output filename: resources.qrc -> resources_rc.py
        py_file = qrc_file.parent / f"{qrc_file.stem}_rc.py"
        
        cmd = [compiler, str(qrc_file), "-o", str(py_file)]
        
        if verbose:
            print(f"Compiling {qrc_file} -> {py_file}")
            print(f"Command: {' '.join(cmd)}")
        
        try:
            qrc_src = str(qrc_file)
            qrc_py  = Path(str(py_file))

            # 1) Ejecutar pyside6-rcc y capturar su salida
            result = subprocess.run(
                ["pyside6-rcc", qrc_src],
                capture_output=True,
                text=True,
                check=True
            )

            # 2) Reemplazar el import en el string
            fixed = result.stdout.replace(
                "from PySide6 import ",
                "from PyQt6 import "
            )

            # 3) Escribir el fichero corregido
            qrc_py.write_text(fixed, encoding="utf-8")
            # result = subprocess.run(
            #     cmd,
            #     capture_output=not verbose,
            #     text=True,
            #     check=True
            # )
            
            # if verbose and result.stdout:
            #     print(result.stdout)

            # qrc_py = str(py_file)
            # with open(qrc_py, "w") as out:
            #     subprocess.run(
            #         [
            #             "sed",
            #             "s/^from PySide6 import /from PyQt6 import /",
            #             qrc_py
            #         ],
            #         stdout=out,
            #         check=True
            #     )
            # print(f"✓ Compiled {qrc_file.name}")
            
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to compile {qrc_file.name}: {e}")
            if e.stderr:
                print(f"Error: {e.stderr}")
            success = False
        except Exception as e:
            print(f"✗ Unexpected error compiling {qrc_file.name}: {e}")
            success = False
    
    return success

def check_dependencies(verbose=False):
    """Check if required dependencies are available"""
    print("Checking dependencies...")
    
    # required_packages = ["PyQt6"]
    # optional_packages = ["PyQt6-tools"]
    
    # missing_required = []
    # missing_optional = []
    
    # for package in required_packages:
    #     try:
    #         __import__(package.replace("-", "_").lower())
    #         if verbose:
    #             print(f"✓ {package} is available")
    #     except ImportError:
    #         missing_required.append(package)
    #         print(f"✗ {package} is missing (required)")
    
    # for package in optional_packages:
    #     # For tools packages, check if commands are available
    #     if package == "PyQt6-tools":
    #         if check_command_available("pyuic6"):
    #             if verbose:
    #                 print(f"✓ {package} tools are available")
    #         else:
    #             missing_optional.append(package)
    #             print(f"⚠ {package} is missing (optional, but recommended)")
    
    # if missing_required:
    #     print(f"Error: Missing required packages: {', '.join(missing_required)}")
    #     print("Install with: pip install " + " ".join(missing_required))
    #     return False
    
    # if missing_optional and verbose:
    #     print(f"Optional packages missing: {', '.join(missing_optional)}")
    #     print("Install with: pip install " + " ".join(missing_optional))
    
    return True

def create_compiled_ui_imports(verbose=False):
    """Create a module to import all compiled UI files"""
    print("Creating UI imports module...")
    
    gui_dir = Path("GUI")
    ui_py_files = list(gui_dir.glob("*_ui.py"))
    
    if not ui_py_files:
        if verbose:
            print("No compiled UI files found, skipping imports module")
        return True
    
    imports_content = [
        '"""',
        'Auto-generated UI imports module.',
        'This file imports all compiled UI files for easier access.',
        '"""',
        '',
    ]
    
    for ui_file in ui_py_files:
        module_name = ui_file.stem
        imports_content.append(f'from GUI.{module_name} import *')
    
    imports_file = gui_dir / "__init__.py"
    
    try:
        with open(imports_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(imports_content))
        
        if verbose:
            print(f"✓ Created {imports_file}")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to create imports module: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Pre-build script for SeqModeller"
    )
    parser.add_argument(
        "--compile-ui",
        action="store_true",
        help="Compile .ui files to .py files"
    )
    parser.add_argument(
        "--compile-resources",
        action="store_true",
        help="Compile .qrc files to .py files"
    )
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Check for required dependencies"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all build steps"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose output"
    )
    
    args = parser.parse_args()
    
    # If no specific flags are given, run all by default
    if not any([args.compile_ui, args.compile_resources, args.check_deps]):
        args.all = True
    
    success = True
    
    # Check dependencies first
    if args.check_deps or args.all:
        if not check_dependencies(args.verbose):
            success = False
    
    # Compile UI files
    if args.compile_ui or args.all:
        if not compile_ui_files(args.verbose):
            print("Warning: UI compilation had issues")
        
        # Create imports module for compiled UI files
        if not create_compiled_ui_imports(args.verbose):
            print("Warning: Failed to create UI imports module")
    
    # Compile resources
    if args.compile_resources or args.all:
        if not compile_resources(args.verbose):
            print("Warning: Resource compilation had issues")
    
    if success:
        print("Pre-build completed successfully!")
        sys.exit(0)
    else:
        print("Pre-build completed with errors!")
        sys.exit(1)

if __name__ == "__main__":
    main()