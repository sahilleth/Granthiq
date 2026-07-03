#!/usr/bin/env python3
"""
Validate that requirements-docker.txt includes all necessary packages from pyproject.toml
"""
import re
import sys
from pathlib import Path

# Packages to exclude (development, platform-specific, or not needed in Docker)
EXCLUDED_PACKAGES = {
    # Development only
    "streamlit",
    "deepeval", 
    "aiosqlite",  # Using Postgres only
    
    # Platform-specific
    "python-magic-bin",  # Windows-specific
    "pywin32",  # Windows-specific
    
    # Alternative/unused providers
    "fastembed",
    "langchain-google-genai",
    "langchain-groq",
    "langchain-huggingface",
    "langchain-litellm",
    "litellm",
    "llama-index-embeddings-huggingface",
    "llama-index-llms-groq",
    "llama-index-llms-litellm",
    "llama-index-postprocessor-cohere-rerank",
    "llama-index-retrievers-bm25",
    
    # Meta-packages (using individual packages instead)
    "llama-index",  # Meta-package
    "llama-index-cli",  # Not needed in Docker
    "llama-index-indices-managed-llama-cloud",
    "llama-index-legacy",
}

def parse_pyproject_dependencies():
    """Extract package names from pyproject.toml"""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    
    if not pyproject_path.exists():
        print(f"❌ {pyproject_path} not found")
        return set()
    
    content = pyproject_path.read_text()
    
    # Extract dependencies list
    deps_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if not deps_match:
        print("❌ Could not find dependencies in pyproject.toml")
        return set()
    
    deps_str = deps_match.group(1)
    
    # Parse package names (ignore version specs)
    packages = set()
    for line in deps_str.split('\n'):
        line = line.strip().strip('"').strip(',')
        if not line or line.startswith('#'):
            continue
        
        # Extract package name (before any version spec)
        match = re.match(r'([a-zA-Z0-9._-]+(?:\[[^\]]+\])?)', line)
        if match:
            pkg_name = match.group(1)
            # Remove brackets for comparison (e.g., "procrastinate[postgresql]" -> "procrastinate")
            base_name = pkg_name.split('[')[0]
            packages.add(base_name)
    
    return packages

def parse_requirements_docker():
    """Extract package names from requirements-docker.txt"""
    req_path = Path(__file__).parent.parent / "requirements-docker.txt"
    
    if not req_path.exists():
        print(f"[!] {req_path} not found")
        return set()
    
    content = req_path.read_text(encoding='utf-8')
    
    packages = set()
    for line in content.split('\n'):
        line = line.strip()
        
        # Skip comments, empty lines, and special directives
        if not line or line.startswith('#') or line.startswith('--'):
            continue
        
        # Extract package name (before any version spec)
        match = re.match(r'([a-zA-Z0-9._-]+(?:\[[^\]]+\])?)', line)
        if match:
            pkg_name = match.group(1)
            # Remove brackets for comparison
            base_name = pkg_name.split('[')[0]
            packages.add(base_name)
    
    return packages

def main():
    # Fix Unicode encoding for Windows
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("Validating requirements-docker.txt against pyproject.toml...\n")
    
    # Parse both files
    pyproject_pkgs = parse_pyproject_dependencies()
    docker_pkgs = parse_requirements_docker()
    
    if not pyproject_pkgs or not docker_pkgs:
        print("Failed to parse files")
        return 1
    
    # Find missing packages (in pyproject but not in docker, excluding known exclusions)
    missing = (pyproject_pkgs - docker_pkgs) - EXCLUDED_PACKAGES
    
    # Find extra packages (in docker but not in pyproject - usually fine)
    extra = docker_pkgs - pyproject_pkgs
    
    print(f"Statistics:")
    print(f"  pyproject.toml: {len(pyproject_pkgs)} packages")
    print(f"  requirements-docker.txt: {len(docker_pkgs)} packages")
    print(f"  Excluded (dev/platform): {len(EXCLUDED_PACKAGES)} packages")
    print()
    
    # Report results
    if missing:
        print(f"❌ MISSING {len(missing)} packages in requirements-docker.txt:")
        for pkg in sorted(missing):
            print(f"  ✗ {pkg}")
        print()
        print("💡 Add these to requirements-docker.txt or EXCLUDED_PACKAGES if intentional")
        return 1
    else:
        print("✅ All necessary packages included!")
    
    if extra:
        print(f"\nℹ️  Extra {len(extra)} packages in requirements-docker.txt:")
        extra_list = sorted(extra)[:10]  # Show first 10
        for pkg in extra_list:
            print(f"  + {pkg}")
        if len(extra) > 10:
            print(f"  ... and {len(extra) - 10} more")
        print("\n💡 This is usually fine (pinned versions, dependencies, etc.)")
    
    print("\n" + "="*60)
    print("✅ VALIDATION PASSED - requirements-docker.txt is complete!")
    print("="*60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
