import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
print("Importing firecrawl...")
try:
    from firecrawl import Firecrawl
    print("Success Firecrawl")
except Exception as e:
    import traceback
    traceback.print_exc()

print("Importing create_app...")
try:
    from src.app import create_app
    print("Success App")
except Exception as e:
    import traceback
    traceback.print_exc()
