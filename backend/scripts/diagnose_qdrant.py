"""
Diagnostic script to check Qdrant collection contents and metadata.
"""
import sys
from pathlib import Path

# Add backend directory to path
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from src.db.vector_store import get_vector_store
from qdrant_client.models import Filter, FieldCondition, MatchValue
import json

# Test notebook/user IDs from test_chat.py
TEST_NOTEBOOK_ID = "1504830e-2f2a-426b-a934-0625a3cb9812"
TEST_USER_ID = "eaa585c2-9a2c-445e-9b8c-eaf5bb6bf4fa"
FIQA_USER_ID = "fiqa-eval-user-2024"

def main():
    print("=== Qdrant Diagnostic ===\n")
    
    vs = get_vector_store()
    
    # 1. Check total collection count
    try:
        total_count = vs.client.count(collection_name=vs.collection_name)
        print(f"Total points in collection '{vs.collection_name}': {total_count.count}")
    except Exception as e:
        print(f"Error counting collection: {e}")
        return
    
    # 2. Sample some points to see metadata structure
    print("\n--- Sample Points (first 5) ---")
    try:
        points, _ = vs.client.scroll(
            collection_name=vs.collection_name,
            limit=5,
            with_payload=True,
            with_vectors=False
        )
        
        for i, point in enumerate(points):
            print(f"\n[Point {i+1}] ID: {point.id}")
            payload = point.payload or {}
            metadata = payload.get("metadata", payload)  # Some may store directly
            
            print(f"  document_id: {metadata.get('document_id', 'MISSING')}")
            print(f"  notebook_id: {metadata.get('notebook_id', 'MISSING')}")
            print(f"  user_id: {metadata.get('user_id', 'MISSING')}")
            print(f"  filename: {metadata.get('filename', 'MISSING')}")
            
            # Show text snippet
            text = payload.get("text", payload.get("_node_content", ""))
            if isinstance(text, str):
                print(f"  text_snippet: {text[:100]}...")
            
    except Exception as e:
        print(f"Error scrolling points: {e}")
    
    # 3. Check for points with TEST_NOTEBOOK_ID
    print(f"\n--- Points with notebook_id = {TEST_NOTEBOOK_ID} ---")
    try:
        notebook_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.notebook_id",
                    match=MatchValue(value=TEST_NOTEBOOK_ID)
                )
            ]
        )
        count_result = vs.client.count(
            collection_name=vs.collection_name,
            count_filter=notebook_filter
        )
        print(f"Count: {count_result.count}")
        
        if count_result.count > 0:
            points, _ = vs.client.scroll(
                collection_name=vs.collection_name,
                scroll_filter=notebook_filter,
                limit=3,
                with_payload=True,
                with_vectors=False
            )
            for point in points:
                metadata = point.payload.get("metadata", point.payload)
                print(f"  - doc_id: {metadata.get('document_id')}, filename: {metadata.get('filename')}")
    except Exception as e:
        print(f"Error: {e}")
    
    # 4. Check for points with TEST_USER_ID
    print(f"\n--- Points with user_id = {TEST_USER_ID} ---")
    try:
        user_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.user_id",
                    match=MatchValue(value=TEST_USER_ID)
                )
            ]
        )
        count_result = vs.client.count(
            collection_name=vs.collection_name,
            count_filter=user_filter
        )
        print(f"Count: {count_result.count}")
        
        if count_result.count > 0:
            points, _ = vs.client.scroll(
                collection_name=vs.collection_name,
                scroll_filter=user_filter,
                limit=3,
                with_payload=True,
                with_vectors=False
            )
            for point in points:
                metadata = point.payload.get("metadata", point.payload)
                print(f"  - doc_id: {metadata.get('document_id')}, notebook_id: {metadata.get('notebook_id', 'MISSING')}")
    except Exception as e:
        print(f"Error: {e}")
    
    # 5. Check if any points are missing notebook_id
    print("\n--- Points MISSING notebook_id (potential issue) ---")
    try:
        # This is tricky - we need to find points where notebook_id doesn't exist
        # Sample all points and filter locally
        all_points, _ = vs.client.scroll(
            collection_name=vs.collection_name,
            limit=100,
            with_payload=True,
            with_vectors=False
        )
        
        missing_notebook_id = []
        for point in all_points:
            metadata = point.payload.get("metadata", point.payload)
            if not metadata.get("notebook_id"):
                missing_notebook_id.append({
                    "id": point.id,
                    "doc_id": metadata.get("document_id"),
                    "user_id": metadata.get("user_id"),
                    "filename": metadata.get("filename")
                })
        
        print(f"Found {len(missing_notebook_id)} points without notebook_id (out of {len(all_points)} sampled)")
        for item in missing_notebook_id[:5]:
            print(f"  - {item}")
            
    except Exception as e:
        print(f"Error: {e}")
    
    # 6. Check FiQA data specifically
    print(f"\n--- FiQA Evaluation Data (user_id='{FIQA_USER_ID}') ---")
    try:
        fiqa_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.user_id",
                    match=MatchValue(value=FIQA_USER_ID)
                )
            ]
        )
        fiqa_count = vs.client.count(
            collection_name=vs.collection_name,
            count_filter=fiqa_filter
        )
        print(f"Count: {fiqa_count.count}")
        
        if fiqa_count.count > 0:
            points, _ = vs.client.scroll(
                collection_name=vs.collection_name,
                scroll_filter=fiqa_filter,
                limit=3,
                with_payload=True,
                with_vectors=False
            )
            print("\nSample FiQA points:")
            for i, point in enumerate(points):
                metadata = point.payload.get("metadata", point.payload)
                print(f"  [{i+1}] doc_id: {metadata.get('document_id')}, "
                      f"source_type: {metadata.get('source_type', 'MISSING')}")
                text = point.payload.get("text", "")
                if text:
                    print(f"      text: {text[:100]}...")
        else:
            print("  ⚠️  WARNING: No FiQA data found!")
            print("     This might explain low similarity scores.")
            print("     Recommendation: Re-index FiQA dataset")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n=== Diagnostic Complete ===")
    print("\n💡 Recommendations:")
    print("   - If FiQA count is 0 or very low: Re-index the dataset")
    print("   - If similarity scores are low: Check embedding model consistency")
    print("   - If data exists but scores are low: May need to delete and re-index")

if __name__ == "__main__":
    main()
