#!/usr/bin/env python3
"""
Find unused packages in requirements-docker.txt
"""
import re
from pathlib import Path
from collections import defaultdict

# Package name mapping for imports
PACKAGE_MAP = {
    # Import name → Package name
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "sqlmodel": "sqlmodel",
    "asyncpg": "asyncpg",
    "alembic": "alembic",
    "supabase": "supabase",
    "websockets": "websockets",
    "llama_index": "llama-index-core",
    "openai": "openai",
    "tiktoken": "tiktoken",
    "qdrant_client": "qdrant-client",
    "langchain": "langchain",
    "langchain_openai": "langchain-openai",
    "langchain_community": "langchain-community",
    "langsmith": "langsmith",
    "packaging": "packaging",
    "tenacity": "tenacity",
    "pypdf": "pypdf",
    "bs4": "beautifulsoup4",
    "beautifulsoup4": "beautifulsoup4",
    "assemblyai": "assemblyai",
    "pydub": "pydub",
    "soundfile": "soundfile",
    "huggingface_hub": "huggingface-hub",
    "transformers": "transformers",
    "sentence_transformers": "sentence-transformers",
    "requests": "requests",
    "httpx": "httpx",
    "aiohttp": "aiohttp",
    "aiofiles": "aiofiles",
    "loguru": "loguru",
    "tqdm": "tqdm",
    "pytest": "pytest",
    "pytest_asyncio": "pytest-asyncio",
}

# Required packages in requirements-docker.txt
REQUIRED_PACKAGES = [
    "fastapi",
    "uvicorn",
    "python-multipart",
    "python-dotenv",
    "pydantic",
    "pydantic-settings",
    "sqlmodel",
    "asyncpg",
    "alembic",
    "supabase",
    "websockets",
    "llama-index-core",
    "llama-index-vector-stores-qdrant",
    "openai",
    "tiktoken",
    "qdrant-client",
    "langchain",
    "langchain-openai",
    "langchain-community",
    "langsmith",
    "packaging",
    "tenacity",
    "pypdf",
    "beautifulsoup4",
    "assemblyai",
    "pydub",
    "soundfile",
    "huggingface-hub",
    "transformers",
    "sentence-transformers",
    "requests",
    "httpx",
    "aiohttp",
    "aiofiles",
    "loguru",
    "tqdm",
    "pytest",
    "pytest-asyncio",
]

def find_imports(directory: Path):
    """Find all imports in Python files"""
    imports = defaultdict(set)
    
    for py_file in directory.rglob("*.py"):
        # Skip test files, migrations, __pycache__
        if any(skip in str(py_file) for skip in ["test_", "__pycache__", "migrations", ".venv", "build"]):
            continue
            
        try:
            content = py_file.read_text(encoding="utf-8")
            
            # Find all import statements
            for line in content.split("\n"):
                # from X import Y
                match = re.match(r"from\s+(\w+)", line.strip())
                if match:
                    package = match.group(1)
                    imports[package].add(str(py_file.relative_to(directory)))
                
                # import X
                match = re.match(r"import\s+(\w+)", line.strip())
                if match:
                    package = match.group(1)
                    imports[package].add(str(py_file.relative_to(directory)))
        except Exception as e:
            print(f"Error reading {py_file}: {e}")
    
    return imports

def main():
    backend_dir = Path(__file__).parent.parent
    src_dir = backend_dir / "src"
    
    print("🔍 Analyzing package usage...\n")
    
    # Find all imports
    imports = find_imports(src_dir)
    
    # Map imports to packages
    used_packages = set()
    for import_name in imports.keys():
        if import_name in PACKAGE_MAP:
            used_packages.add(PACKAGE_MAP[import_name])
    
    # Check which required packages are NOT used
    unused = []
    used = []
    
    for package in REQUIRED_PACKAGES:
        if package in used_packages:
            used.append(package)
        else:
            # Some packages might be indirect dependencies or always needed
            if package in ["python-multipart", "python-dotenv", "pytest", "pytest-asyncio"]:
                used.append(f"{package} (build/runtime)")
            else:
                unused.append(package)
    
    print(f"✅ USED Packages ({len(used)}):")
    for pkg in sorted(used):
        print(f"  ✓ {pkg}")
    
    if unused:
        print(f"\n⚠️  POTENTIALLY UNUSED Packages ({len(unused)}):")
        for pkg in sorted(unused):
            print(f"  ✗ {pkg}")
        print("\n💡 These packages might be:")
        print("   - Transitive dependencies (needed by other packages)")
        print("   - Used in scripts/ or tests/")
        print("   - Runtime requirements not directly imported")
    else:
        print("\n✅ All packages are used!")
    
    # Show most imported packages
    print("\n📊 Most Used Packages:")
    package_usage = defaultdict(int)
    for import_name, files in imports.items():
        if import_name in PACKAGE_MAP:
            package_usage[PACKAGE_MAP[import_name]] += len(files)
    
    for pkg, count in sorted(package_usage.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {pkg}: {count} files")

if __name__ == "__main__":
    main()
