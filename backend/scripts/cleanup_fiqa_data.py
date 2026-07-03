"""
Cleanup script to delete only FiQA evaluation data from Qdrant.
This preserves other data in the collection.
"""
import sys
from pathlib import Path

# Add backend directory to path
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from src.db.vector_store import get_vector_store
from qdrant_client.models import Filter, FieldCondition, MatchValue
from loguru import logger

FIQA_USER_ID = "fiqa-eval-user-2024"

def delete_fiqa_data():
    """Delete all FiQA evaluation data from Qdrant."""
    print("=" * 80)
    print("FiQA Data Cleanup")
    print("=" * 80)
    
    vs = get_vector_store()
    
    # 1. Count FiQA data before deletion
    print(f"\n1. Checking FiQA data (user_id='{FIQA_USER_ID}')...")
    try:
        fiqa_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.user_id",
                    match=MatchValue(value=FIQA_USER_ID)
                )
            ]
        )
        count_before = vs.client.count(
            collection_name=vs.collection_name,
            count_filter=fiqa_filter
        )
        print(f"   Found {count_before.count} FiQA chunks to delete")
        
        if count_before.count == 0:
            print("   ✅ No FiQA data found. Nothing to delete.")
            return
        
    except Exception as e:
        print(f"   ❌ Error checking FiQA data: {e}")
        return
    
    # 2. Confirm deletion
    print(f"\n2. ⚠️  WARNING: This will delete {count_before.count} FiQA chunks!")
    response = input("   Continue? (yes/no): ").strip().lower()
    
    if response != "yes":
        print("   ❌ Deletion cancelled.")
        return
    
    # 3. Delete FiQA data
    print(f"\n3. Deleting FiQA data...")
    try:
        # Ensure index exists
        try:
            vs.client.create_payload_index(
                collection_name=vs.collection_name,
                field_name="metadata.user_id",
                field_schema="keyword",
            )
        except Exception:
            pass  # Index might already exist
        
        # Find all points with FiQA user_id
        points_to_delete = []
        offset = None
        
        while True:
            result, offset = vs.client.scroll(
                collection_name=vs.collection_name,
                scroll_filter=fiqa_filter,
                limit=100,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            
            if not result:
                break
            
            points_to_delete.extend([point.id for point in result])
            
            if offset is None:
                break
        
        # Delete in batches
        if points_to_delete:
            batch_size = 100
            deleted_total = 0
            
            for i in range(0, len(points_to_delete), batch_size):
                batch = points_to_delete[i:i + batch_size]
                vs.client.delete(
                    collection_name=vs.collection_name,
                    points_selector=batch,
                )
                deleted_total += len(batch)
                print(f"   Deleted batch {i//batch_size + 1}: {len(batch)} chunks (total: {deleted_total}/{len(points_to_delete)})")
            
            print(f"\n   ✅ Successfully deleted {deleted_total} FiQA chunks")
            
            # Verify deletion
            count_after = vs.client.count(
                collection_name=vs.collection_name,
                count_filter=fiqa_filter
            )
            print(f"   Verification: {count_after.count} FiQA chunks remaining (should be 0)")
            
            if count_after.count == 0:
                print("\n   ✅ Cleanup complete! You can now re-index FiQA data.")
            else:
                print(f"\n   ⚠️  Warning: {count_after.count} chunks still remain. May need manual cleanup.")
        else:
            print("   ⚠️  No points found to delete")
            
    except Exception as e:
        print(f"   ❌ Error deleting FiQA data: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 80)
    print("Next Steps:")
    print("  1. Re-index FiQA dataset:")
    print("     python -m src.evaluation.run_fiqa_evaluation --limit 20")
    print("     (without --skip-ingestion flag)")
    print("  2. Run evaluation again:")
    print("     python -m src.evaluation.run_fiqa_evaluation --limit 20 --skip-ingestion")
    print("=" * 80)


if __name__ == "__main__":
    delete_fiqa_data()
