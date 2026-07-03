"""
Deep diagnostic for FiQA evaluation failures.

This script investigates why queries #4, #5, #8 return zero context_recall/precision.
It shows:
1. The actual query text
2. Expected ground-truth contexts (from RAGAS)
3. What's indexed in Qdrant
4. What retrieval returns
5. Why there's a mismatch
"""
import sys
import asyncio
from pathlib import Path
import json

# Add backend to path
current_file = Path(__file__).resolve()
backend_path = current_file.parents[1]
if str(backend_path) not in sys.path:
    sys.path.append(str(backend_path))

from src.evaluation.test_dataset import EvaluationDataset
from src.db.vector_store import get_vector_store
from src.services.embeddings.embedding_config import configure_llamaindex_embed_model
from llama_index.core import Settings
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

FIQA_USER_ID = "fiqa-eval-user-2024"
DATASET_NAME = "vibrantlabsai/fiqa"
DATASET_SPLIT = "baseline"
DATASET_CONFIG = "ragas_eval_v3"


async def investigate_query(dataset, query_idx: int):
    """Deep investigation of a single query."""

    print("\n" + "="*80)
    print(f"INVESTIGATING QUERY #{query_idx + 1}")
    print("="*80)

    # Get query data
    example = dataset[query_idx]
    question = example.get("question", "")
    ground_truth_answer = example.get("ground_truth", "")
    expected_contexts = example.get("contexts", [])

    print(f"\n[QUERY]:")
    print(f"   {question}")
    print(f"\n[GROUND TRUTH ANSWER]:")
    print(f"   {ground_truth_answer[:200]}...")
    print(f"\n[EXPECTED CONTEXTS] (what RAGAS wants to find):")
    for i, ctx in enumerate(expected_contexts):
        print(f"\n   Context {i+1} ({len(ctx)} chars):")
        print(f"   {ctx[:200]}...")
        if len(ctx) > 200:
            print(f"   ... (truncated, full length: {len(ctx)} chars)")

    # Configure embedding model
    configure_llamaindex_embed_model()

    # Check what's actually in Qdrant
    from src.config import get_settings
    settings = get_settings()

    qdrant_client = QdrantClient(
        url=settings.qdrant.host,
        api_key=settings.qdrant.api_key,
    )

    collection_name = settings.qdrant.collection_name

    print(f"\n[CHECKING QDRANT COLLECTION]: {collection_name}")

    # Search for points with user_id filter
    filter_condition = Filter(
        must=[
            FieldCondition(
                key="metadata.user_id",
                match=MatchValue(value=FIQA_USER_ID),
            )
        ]
    )

    # Count total points with this user_id
    count_result = qdrant_client.count(
        collection_name=collection_name,
        count_filter=filter_condition,
    )

    print(f"   Total chunks indexed with user_id={FIQA_USER_ID}: {count_result.count}")

    # Now do a semantic search
    print(f"\n[SEMANTIC SEARCH RESULTS] (top 10):")

    # Get query embedding
    embed_model = Settings.embed_model
    query_embedding = embed_model.get_query_embedding(question)

    search_results = qdrant_client.search(
        collection_name=collection_name,
        query_vector=query_embedding,
        query_filter=filter_condition,
        limit=10,
        with_payload=True,
    )

    if not search_results:
        print("   ❌ NO RESULTS FOUND!")
        print("   This means retrieval is completely failing for this query.")
        print("   Possible causes:")
        print("   - Ground truth contexts weren't indexed")
        print("   - User_id mismatch")
        print("   - Embedding mismatch")
        return

    print(f"   Found {len(search_results)} results")

    for i, hit in enumerate(search_results):
        score = hit.score
        text = hit.payload.get("text", "")
        metadata = hit.payload.get("metadata", {})
        doc_id = metadata.get("document_id", "unknown")
        chunk_idx = metadata.get("chunk_index", "unknown")

        print(f"\n   Result {i+1}:")
        print(f"      Score: {score:.6f}")
        print(f"      Document ID: {doc_id}")
        print(f"      Chunk Index: {chunk_idx}")
        print(f"      Text ({len(text)} chars): {text[:150]}...")

        # Check if this matches any expected context
        matched = False
        for ctx_idx, expected_ctx in enumerate(expected_contexts):
            # Check if retrieved text is a substring of expected context
            # OR if expected context is a substring of retrieved text
            # OR if they have significant overlap
            if text in expected_ctx or expected_ctx in text:
                print(f"      ✓ PARTIAL MATCH with Expected Context {ctx_idx+1}")
                matched = True
            elif len(text) > 50 and len(expected_ctx) > 50:
                # Check for substring overlap
                text_clean = text.strip().lower()
                ctx_clean = expected_ctx.strip().lower()
                # Simple overlap check
                overlap_words = set(text_clean.split()) & set(ctx_clean.split())
                if len(overlap_words) > 10:  # At least 10 common words
                    print(f"      ~ SEMANTIC OVERLAP with Expected Context {ctx_idx+1} ({len(overlap_words)} common words)")
                    matched = True

        if not matched:
            print(f"      ✗ NO MATCH with any expected context")

    # Analyze the mismatch
    print(f"\n[MISMATCH ANALYSIS]:")

    # Check if expected contexts exist in indexed data
    print(f"\n   Checking if expected contexts were indexed...")

    for ctx_idx, expected_ctx in enumerate(expected_contexts):
        # Search for the expected context directly
        # We'll search for a unique substring from the expected context
        unique_phrase = expected_ctx[:100].strip()  # First 100 chars

        # Get embedding for the expected context
        ctx_embedding = embed_model.get_text_embedding(expected_ctx)

        ctx_search = qdrant_client.search(
            collection_name=collection_name,
            query_vector=ctx_embedding,
            query_filter=filter_condition,
            limit=3,
            with_payload=True,
        )

        print(f"\n   Expected Context {ctx_idx+1}:")
        if ctx_search and ctx_search[0].score > 0.9:
            print(f"      ✓ FOUND in index (score: {ctx_search[0].score:.6f})")
            print(f"      Indexed text: {ctx_search[0].payload.get('text', '')[:100]}...")
        elif ctx_search and ctx_search[0].score > 0.7:
            print(f"      ~ SIMILAR chunk found (score: {ctx_search[0].score:.6f})")
            print(f"      This might be a chunked version of the expected context")
            print(f"      Indexed text: {ctx_search[0].payload.get('text', '')[:100]}...")
        else:
            print(f"      ✗ NOT FOUND in index (best score: {ctx_search[0].score if ctx_search else 0:.6f})")
            print(f"      This context was likely NOT indexed, or heavily chunked")

    # Summary
    print(f"\n[DIAGNOSIS]:")
    print(f"   1. Are contexts indexed? Check above")
    print(f"   2. Chunking issue? If contexts are split, RAGAS won't match them")
    print(f"   3. Semantic mismatch? Query doesn't match indexed content semantically")


async def main():
    """Run deep diagnostic on problematic queries."""

    print("="*80)
    print("FiQA Deep Diagnostic - Zero Context Queries")
    print("="*80)

    # Load dataset
    print("\nLoading FiQA dataset...")
    dataset = EvaluationDataset.load_from_huggingface(
        dataset_name=DATASET_NAME,
        split=DATASET_SPLIT,
        config_name=DATASET_CONFIG,
        limit=10
    )
    print(f"Loaded {len(dataset)} examples")

    # Problematic query indices (0-indexed)
    problematic_indices = [3, 4, 7]  # Queries #4, #5, #8

    for idx in problematic_indices:
        await investigate_query(dataset, idx)

    print("\n" + "="*80)
    print("DIAGNOSTIC COMPLETE")
    print("="*80)

    print("\n[NEXT STEPS]:")
    print("1. If contexts are NOT FOUND: Re-index with different strategy")
    print("2. If contexts are CHUNKED: Disable chunking for evaluation data")
    print("3. If SEMANTIC MISMATCH: Improve embedding model or query expansion")
    print("\nSee detailed recommendations in docs/EVALUATION_RESULTS_ANALYSIS_JAN_14.md")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
