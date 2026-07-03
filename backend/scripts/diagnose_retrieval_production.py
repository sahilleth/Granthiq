"""
Diagnostic script to investigate retrieval issues in production.
Helps identify why similarity scores are 0.000.
"""
import sys
import asyncio
from pathlib import Path
from uuid import UUID

# Add backend to path
current_file = Path(__file__).resolve()
backend_path = current_file.parents[1]
if str(backend_path) not in sys.path:
    sys.path.append(str(backend_path))

from src.db.vector_store import get_vector_store
from src.config import get_settings
from qdrant_client.models import Filter, FieldCondition, MatchValue


async def diagnose_retrieval(notebook_id: str, user_id: str, query: str):
    """
    Diagnose retrieval issues for a specific notebook and query.

    Args:
        notebook_id: UUID of the notebook
        user_id: UUID of the user
        query: Test query string
    """
    print("=" * 70)
    print("RETRIEVAL DIAGNOSTIC TOOL")
    print("=" * 70)
    print(f"Notebook ID: {notebook_id}")
    print(f"User ID: {user_id}")
    print(f"Query: {query}")
    print("=" * 70)

    # Initialize
    settings = get_settings()
    vs = get_vector_store()

    print("\n[1/5] Configuration Check")
    print("-" * 70)
    print(f"Collection: {vs.collection_name}")
    print(f"Embedding Model: {settings.embedding.model}")
    print(f"Top K: {settings.rag.top_k_results}")
    print(f"Hybrid Alpha: {settings.rag.default_alpha}")
    print(f"Policy Threshold: {settings.policy.min_score_threshold}")
    print(f"Min Chunks: {settings.policy.min_context_chunks}")
    print(f"HyDE Enabled: {settings.rag.use_hyde}")

    # Check indexed chunks
    print("\n[2/5] Checking Indexed Data")
    print("-" * 70)

    try:
        # Count chunks for this notebook
        filter_condition = Filter(
            must=[
                FieldCondition(
                    key="metadata.notebook_id",
                    match=MatchValue(value=notebook_id)
                ),
                FieldCondition(
                    key="metadata.user_id",
                    match=MatchValue(value=user_id)
                )
            ]
        )

        count_result = vs.client.count(
            collection_name=vs.collection_name,
            count_filter=filter_condition
        )

        print(f"Total chunks indexed: {count_result.count}")

        if count_result.count == 0:
            print("ERROR: No chunks found for this notebook!")
            print("Please ensure documents are ingested and indexed.")
            return

    except Exception as e:
        print(f"ERROR checking indexed data: {e}")
        return

    # Generate embedding for query
    print("\n[3/5] Generating Query Embedding")
    print("-" * 70)

    try:
        # Get embedding directly
        from llama_index.core import Settings as LlamaSettings
        embed_model = LlamaSettings.embed_model

        query_embedding = embed_model.get_text_embedding(query)
        print(f"Embedding dimension: {len(query_embedding)}")
        print(f"Embedding sample (first 5 dims): {query_embedding[:5]}")

        # Check if embedding is all zeros (indicates problem)
        if all(x == 0.0 for x in query_embedding):
            print("ERROR: Query embedding is all zeros!")
            print("This indicates an embedding model issue.")
            return

    except Exception as e:
        print(f"ERROR generating embedding: {e}")
        return

    # Test direct Qdrant search
    print("\n[4/5] Testing Direct Qdrant Search")
    print("-" * 70)

    try:
        # Search with filter
        # IMPORTANT: Our collection uses NAMED vectors for hybrid search:
        # - "text-dense"   for dense embeddings
        # - "text-sparse"  for sparse BM42 vectors
        # Qdrant 400 "Not existing vector name" happens if you call `search`
        # without specifying a valid vector_name when the collection has only
        # named vectors. Here we explicitly use the dense vector.
        # Search with filter
        # IMPORTANT: Our collection uses NAMED vectors for hybrid search:
        # - "text-dense"   for dense embeddings
        # - "text-sparse"  for sparse BM42 vectors
        # For qdrant-client >= 1.7.0, passed named vectors as a tuple: (name, vector)
        search_results = vs.client.search(
            collection_name=vs.collection_name,
            query_vector=("text-dense", query_embedding),
            query_filter=filter_condition,
            limit=10,
            with_payload=True
        )

        print(f"Retrieved: {len(search_results)} chunks")

        if len(search_results) == 0:
            print("WARNING: No results returned from Qdrant search!")
            print("This might indicate:")
            print("  - Filter is too restrictive")
            print("  - Embeddings don't match (different model used for indexing)")
            print("  - Data not properly indexed")
        else:
            print("\nTop 5 Results:")
            for i, result in enumerate(search_results[:5], 1):
                score = result.score
                text_preview = result.payload.get("text", "")[:100]
                print(f"\n  [{i}] Score: {score:.6f}")
                print(f"      Text: {text_preview}...")
                print(f"      Metadata: {result.payload.get('metadata', {})}")

            # Analyze score distribution
            scores = [r.score for r in search_results]
            avg_score = sum(scores) / len(scores)
            min_score = min(scores)
            max_score = max(scores)

            print(f"\nScore Statistics:")
            print(f"  Min: {min_score:.6f}")
            print(f"  Max: {max_score:.6f}")
            print(f"  Avg: {avg_score:.6f}")

            # Check for zero scores
            zero_count = sum(1 for s in scores if s == 0.0)
            if zero_count > 0:
                print(f"\n  WARNING: {zero_count}/{len(scores)} results have zero scores!")
                print("  This suggests an embedding mismatch or indexing issue.")

            # Policy check
            threshold = settings.policy.min_score_threshold
            above_threshold = sum(1 for s in scores if s >= threshold)
            print(f"\n  Chunks above policy threshold ({threshold}): {above_threshold}/{len(scores)}")

            if above_threshold == 0:
                print(f"  WARNING: No chunks above threshold!")
                print(f"  Consider lowering threshold to {max_score * 0.5:.3f}")

    except Exception as e:
        print(f"ERROR in Qdrant search: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test with QueryEngine
    print("\n[5/5] Testing QueryEngineService")
    print("-" * 70)

    try:
        from src.services.query.query_engine import QueryEngineService

        query_engine = QueryEngineService(
            streaming=False,
            similarity_top_k=settings.rag.top_k_results,
            use_hyde=False,  # Disable HyDE for diagnostic
        )

        filters = {
            "metadata.notebook_id": notebook_id
        }

        print("Running query through QueryEngineService...")
        response = await query_engine.aquery(query, filters=filters, user_id=user_id)

        print(f"\nResponse generated: {len(response.response)} chars")
        print(f"Source nodes: {len(response.source_nodes)}")

        if response.source_nodes:
            print("\nTop source nodes from QueryEngine:")
            for i, node in enumerate(response.source_nodes[:3], 1):
                score = node.score if hasattr(node, 'score') else 'N/A'
                print(f"  [{i}] Score: {score}")
                print(f"      Text: {node.text[:100]}...")
        else:
            print("WARNING: No source nodes returned!")

        print(f"\nGenerated Response:")
        print(f"{response.response[:300]}...")

    except Exception as e:
        print(f"ERROR in QueryEngineService: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("DIAGNOSIS COMPLETE")
    print("=" * 70)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Diagnose retrieval issues")
    parser.add_argument("--notebook-id", required=True, help="Notebook UUID")
    parser.add_argument("--user-id", required=True, help="User UUID")
    parser.add_argument("--query", default="What is the novelty of this paper?", help="Test query")

    args = parser.parse_args()

    await diagnose_retrieval(args.notebook_id, args.user_id, args.query)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
