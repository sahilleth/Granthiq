#!/usr/bin/env python3
"""
Environment Variable Validation Script
Checks if your .env file has all required variables
"""

import os
from pathlib import Path
from typing import List, Tuple

# Required environment variables (grouped by category)
REQUIRED_VARS = {
    "Critical (App will not start)": [
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "QDRANT_HOST",
        "QDRANT_COLLECTION_NAME",
    ],
    "Important (Core features won't work)": [
        "GEMINI_API_KEY",  # or OPENAI_API_KEY or GROQ_API_KEY
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ],
    "Optional (Enhanced features)": [
        "FIRECRAWL_API_KEY",
        "ASSEMBLYAI_API_KEY",
        "COHERE_API_KEY",
    ]
}

def load_env_file(path: str = ".env") -> dict:
    """Load environment variables from .env file"""
    env_vars = {}
    env_path = Path(path)
    
    if not env_path.exists():
        print(f"❌ Error: {path} file not found!")
        return env_vars
    
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if value:  # Only add if value is not empty
                    env_vars[key] = value
    
    return env_vars

def check_env_vars(env_vars: dict) -> Tuple[List[str], List[str], List[str]]:
    """Check which required variables are missing"""
    missing = {"Critical (App will not start)": [], "Important (Core features won't work)": [], "Optional (Enhanced features)": []}
    found = {"Critical (App will not start)": [], "Important (Core features won't work)": [], "Optional (Enhanced features)": []}
    
    for category, vars_list in REQUIRED_VARS.items():
        for var in vars_list:
            if var not in env_vars:
                missing[category].append(var)
            else:
                found[category].append(var)
    
    # Special check: At least one LLM API key
    llm_keys = ["GEMINI_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"]
    has_llm = any(key in env_vars for key in llm_keys)
    
    return missing, found, has_llm

def print_results(missing: dict, found: dict, has_llm: bool):
    """Print validation results"""
    print("\n" + "="*70)
    print("📋 ENVIRONMENT VARIABLE VALIDATION REPORT")
    print("="*70 + "\n")
    
    # Summary
    total_critical = len(REQUIRED_VARS["Critical (App will not start)"])
    total_important = len(REQUIRED_VARS["Important (Core features won't work)"])
    total_optional = len(REQUIRED_VARS["Optional (Enhanced features)"])
    
    found_critical = len(found["Critical (App will not start)"])
    found_important = len(found["Important (Core features won't work)"])
    found_optional = len(found["Optional (Enhanced features)"])
    
    print(f"✅ Critical Variables: {found_critical}/{total_critical}")
    print(f"⚠️  Important Variables: {found_important}/{total_important}")
    print(f"ℹ️  Optional Variables: {found_optional}/{total_optional}")
    print(f"🤖 LLM Provider: {'✅ Configured' if has_llm else '❌ Missing'}\n")
    
    # Detailed breakdown
    for category, vars_list in missing.items():
        if vars_list:
            print(f"\n{'❌' if 'Critical' in category else '⚠️'} {category}:")
            for var in vars_list:
                print(f"   - {var}")
    
    # What's configured
    if any(found.values()):
        print(f"\n✅ Configured Variables:")
        for category, vars_list in found.items():
            if vars_list:
                print(f"\n   {category}:")
                for var in vars_list:
                    print(f"   ✓ {var}")
    
    print("\n" + "="*70)
    
    # Final verdict
    can_start = not missing["Critical (App will not start)"] and has_llm
    
    if can_start:
        print("✅ READY TO START - All critical variables are set!")
        if missing["Important (Core features won't work)"]:
            print("⚠️  Some important features will be unavailable")
    else:
        print("❌ CANNOT START - Missing critical variables!")
        print("\n💡 Quick fix:")
        if missing["Critical (App will not start)"]:
            print("   1. Add these to your .env file:")
            for var in missing["Critical (App will not start)"]:
                print(f"      {var}=your_value_here")
        if not has_llm:
            print("   2. Add at least one LLM API key:")
            print("      GEMINI_API_KEY=your_gemini_key")
            print("      (or OPENAI_API_KEY or GROQ_API_KEY)")
    
    print("="*70 + "\n")

def main():
    """Main validation function"""
    print("🔍 Checking .env file...\n")
    
    # Load environment variables
    env_vars = load_env_file(".env")
    
    if not env_vars:
        print("❌ No environment variables found! Copy .env.example to .env and fill in values.\n")
        return
    
    print(f"✓ Found {len(env_vars)} environment variables")
    
    # Check required variables
    missing, found, has_llm = check_env_vars(env_vars)
    
    # Print results
    print_results(missing, found, has_llm)

if __name__ == "__main__":
    main()
