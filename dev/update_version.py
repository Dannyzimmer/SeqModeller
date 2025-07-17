#!/usr/bin/env python3
"""
Version Update Script for SeqModeller

This script reads the version information from version.json (SSOT - Single Source of Truth)
and automatically updates all files that contain version information:
- ./GUI/about.ui
- ./GUI/app.ui  
- ./README.md

Usage:
    python update_version.py

"""

import json
import re
from pathlib import Path

def load_version_info():
    """Load version information from version.json"""
    try:
        with open('version.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: version.json not found. Please ensure it exists in the project root.")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in version.json: {e}")
        return None

def update_about_ui(version_info):
    """Update version in GUI/about.ui"""
    file_path = Path("GUI/about.ui")
    if not file_path.exists():
        print(f"Warning: {file_path} not found, skipping...")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Pattern to match the version string in about.ui
        pattern = r'(\[SeqModeller\]\(https://github\.com/Dannyzimmer/SeqModeller\.git\) \*v)[0-9]+\.[0-9]+\.[0-9]+(\*)'
        replacement = fr'\g<1>{version_info["version"]}\g<2>'
        
        new_content = re.sub(pattern, replacement, content)
        
        if new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"✓ Updated {file_path}: v{version_info['version']}")
            return True
        else:
            print(f"- No changes needed in {file_path}")
            return False
            
    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False

def update_app_ui(version_info):
    """Update version in GUI/app.ui"""
    file_path = Path("GUI/app.ui")
    if not file_path.exists():
        print(f"Warning: {file_path} not found, skipping...")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Pattern to match the window title version
        pattern = r'(<string>SeqModeller - v)[0-9]+\.[0-9]+\.[0-9]+(</string>)'
        replacement = fr'\g<1>{version_info["version"]}\g<2>'
        
        new_content = re.sub(pattern, replacement, content)
        
        if new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"✓ Updated {file_path}: v{version_info['version']}")
            return True
        else:
            print(f"- No changes needed in {file_path}")
            return False
            
    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False

def update_readme(version_info):
    """Update version in README.md"""
    file_path = Path("README.md")
    if not file_path.exists():
        print(f"Warning: {file_path} not found, skipping...")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        updated = False
        
        # Pattern 1: Download URL
        pattern1 = r'(wget https://github\.com/Dannyzimmer/SeqModeller/releases/download/v)[0-9]+\.[0-9]+\.[0-9]+(/SeqModeller-v)[0-9]+\.[0-9]+\.[0-9]+(_Linux_x86-64\.zip)'
        replacement1 = fr'\g<1>{version_info["version"]}\g<2>{version_info["version"]}\g<3>'
        new_content = re.sub(pattern1, replacement1, content)
        if new_content != content:
            content = new_content
            updated = True
        
        # Pattern 2: Unzip command
        pattern2 = r'(unzip SeqModeller-v)[0-9]+\.[0-9]+\.[0-9]+(_Linux_x86-64\.zip)'
        replacement2 = fr'\g<1>{version_info["version"]}\g<2>'
        new_content = re.sub(pattern2, replacement2, content)
        if new_content != content:
            content = new_content
            updated = True
        
        # Pattern 3: Directory change command
        pattern3 = r'(cd SeqModeller-v)[0-9]+\.[0-9]+\.[0-9]+(_Linux_x86-64)'
        replacement3 = fr'\g<1>{version_info["version"]}\g<2>'
        new_content = re.sub(pattern3, replacement3, content)
        if new_content != content:
            content = new_content
            updated = True
        
        if updated:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Updated {file_path}: v{version_info['version']}")
            return True
        else:
            print(f"- No changes needed in {file_path}")
            return False
            
    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False

def main():
    """Main function to update all version references"""
    print("SeqModeller Version Update Script")
    print("=" * 40)
    
    # Load version information
    version_info = load_version_info()
    if not version_info:
        return 1
    
    print(f"Current version: {version_info['version']}")
    print(f"Build: {version_info['build']}")
    print()
    
    # Track changes
    files_updated = 0
    
    # Update each file
    if update_about_ui(version_info):
        files_updated += 1
    
    if update_app_ui(version_info):
        files_updated += 1
    
    if update_readme(version_info):
        files_updated += 1
    
    print()
    print(f"Update complete! {files_updated} file(s) updated.")
    
    if files_updated > 0:
        print("\nFiles updated successfully:")
        print("- GUI/about.ui")
        print("- GUI/app.ui") 
        print("- README.md")
        print("\nDon't forget to commit these changes to your repository!")
    
    return 0

if __name__ == "__main__":
    exit(main())