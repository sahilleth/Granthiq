"""
Diagnostic script to investigate FiQA retrieval issues.

This script helps identify why context_recall and context_precision dropped significantly.
It examines:
1. Actual similarity scores from Qdrant
2. Policy filtering behavior
3. Number of chunks retrieved at each stage
4. User_id filter verification
"""
import sys
import asyncio
import logging
from pathlib import Path
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# Add backend to path
current_file = Path(__file__).resolve()
backend_path = current_file.parents[1]
if str(backend_path) not in sys.path:
    sys.path.append(str(backend_path))

from src.evaluation.test_dataset import EvaluationDataset
from src.services.query.query_engine import QueryEngineService
from src.db.vector_store import get_vector_store
from src.config import get_settings

FIQA_USER_ID = "fiqa-eval-user-2024"
DATASET_NAME = "vibrantlabsai/fiqa"
DATASET_SPLIT = "baseline"
DATASET_CONFIG = "ragas_eval_v3"


async def diagnose_single_query(query_engine, question: str, user_id: str, query_idx: int):
    """
    Diagnose retrieval for a single query by examining scores at each stage.
    """
    print(f"\n{'='*80}")
    print(f"Query #{query_idx + 1}: {question[:100]}...")
    print(f"{'='*80}")

    # Get raw retrieval from vector store
    from src.services.retriever.retriever import get_retriever
    from llama_index.core import Settings

    settings = get_settings()

    # Create retriever with high top_k to see what's available
    retriever = get_retriever(
        similarity_top_k=50,  # Get many candidates
        enable_query_fusion=False,  # Disable for clearer diagnostics
        llm=Settings.llm,
        alpha=0.70,  # Favor semantic
    )

    # Retrieve with user_id filter
    from llama_index.core.schema import QueryBundle
    from src.utils.filter import build_qdrant_filters

    query_bundle = QueryBundle(query_str=question)

    # Build filters
    filters = build_qdrant_filters(user_id=user_id)

    print(f"\n1. RAW RETRIEVAL (similarity_top_k=50, user_id={user_id}):")
    print(f"   Filters: {filters}")

    try:
        # Retrieve nodes
        retrieved_nodes = await retriever.aretrieve(query_bundle)

        print(f"   Retrieved: {len(retrieved_nodes)} nodes")

        if len(retrieved_nodes) == 0:
            print("   ❌ CRITICAL: No nodes retrieved! Check:")
            print("      - Is data indexed with correct user_id?")
            print("      - Is Qdrant running and accessible?")
            print("      - Are filters too restrictive?")
            return

        # Show score distribution
        scores = [node.score for node in retrieved_nodes if node.score is not None]
        if scores:
            print(f"   Score range: {min(scores):.4f} - {max(scores):.4f}")
            print(f"   Average score: {sum(scores)/len(scores):.4f}")
            print(f"   Median score: {sorted(scores)[len(scores)//2]:.4f}")

            # Show top 10 scores
            print(f"\n   Top 10 scores:")
            for i, node in enumerate(retrieved_nodes[:10]):
                score = node.score if node.score else 0.0
                text_preview = node.text[:80].replace('\n', ' ') if node.text else "No text"
                print(f"      {i+1}. Score: {score:.4f} | {text_preview}...")

        # Simulate policy filtering at different thresholds
        print(f"\n2. POLICY FILTERING SIMULATION:")
        for threshold in [0.60, 0.40, 0.30, 0.20, 0.15, 0.10, 0.05]:
            filtered = [n for n in retrieved_nodes if (n.score or 0.0) >= threshold]
            print(f"   Threshold {threshold:.2f}: {len(filtered)} nodes pass")
            if len(filtered) < 3:
                print(f"      ⚠️  Less than 3 nodes - would trigger refusal with min_chunks=3")

        # Check adaptive threshold logic
        if scores:
            max_score = max(scores)
            for min_threshold in [0.20, 0.15, 0.10]:
                if max_score < min_threshold:
                    if min_threshold <= 0.15:
                        adaptive_pct = 0.20
                    elif min_threshold <= 0.25:
                        adaptive_pct = 0.30
                    else:
                        adaptive_pct = 0.40
                    adaptive_threshold = max_score * adaptive_pct
                    filtered_adaptive = [n for n in retrieved_nodes if (n.score or 0.0) >= adaptive_threshold]
                    print(f"\n   Adaptive threshold at min={min_threshold}:")
                    print(f"      {adaptive_threshold:.4f} ({adaptive_pct*100:.0f}% of max {max_score:.4f})")
                    print(f"      {len(filtered_adaptive)} nodes pass")

        # Show what would happen with current evaluation settings
        print(f"\n3. CURRENT EVALUATION SETTINGS:")
        print(f"   similarity_top_k: 20")
        print(f"   reranker_top_n: 10")
        print(f"   policy_min_score: 0.20")
        print(f"   policy_min_chunks: 3")

        # Simulate current pipeline
        top_20 = retrieved_nodes[:20]
        print(f"   After retrieval (top 20): {len(top_20)} nodes")

        # Simulate reranker (assume top 10)
        top_10_after_rerank = top_20[:10]
        print(f"   After reranking (top 10): {len(top_10_after_rerank)} nodes")

        # Simulate policy with 0.20 threshold
        policy_filtered = [n for n in top_10_after_rerank if (n.score or 0.0) >= 0.20]
        print(f"   After policy (threshold=0.20): {len(policy_filtered)} nodes")

        if len(policy_filtered) < 3:
            print(f"   ❌ FAILURE: Only {len(policy_filtered)} nodes < min_chunks=3")
            print(f"      This query would return ZERO results!")
        else:
            print(f"   ✓ SUCCESS: {len(policy_filtered)} nodes >= min_chunks=3")

    except Exception as e:
        logger.exception(f"Error during retrieval diagnosis: {e}")
        print(f"   ❌ ERROR: {e}")


async def main():
    """Run diagnostic on problematic FiQA queries."""

    print("=" * 80)
    print("FiQA Retrieval Diagnostics")
    print("=" * 80)

    # Load dataset
    print("\nLoading FiQA dataset...")
    dataset = EvaluationDataset.load_from_huggingface(
        dataset_name=DATASET_NAME,
        split=DATASET_SPLIT,
        config_name=DATASET_CONFIG,
        limit=10
    )
    print(f"Loaded {len(dataset)} examples")

    # Initialize query engine
    print("\nInitializing query engine...")
    settings = get_settings()
    query_engine = QueryEngineService(
        streaming=False,
        similarity_top_k=20,
        enable_query_fusion=True,
        fusion_num_queries=4,
        use_hyde=False,
        hybrid_alpha=0.30,
        reranker_top_n=10,
        policy_min_score=0.20,
        policy_min_chunks=3,
        policy_disabled=False,
    )

    # Focus on problematic queries (queries #4, #5, #8 had zero scores)
    problematic_indices = [3, 4, 7]  # 0-indexed: queries 4, 5, 8

    print(f"\nDiagnosing {len(problematic_indices)} problematic queries...")
    print("(These queries had context_recall=0 and context_precision=0)")

    for idx in problematic_indices:
        if idx < len(dataset):
            example = dataset[idx]
            question = example.get("question", "")
            if question:
                await diagnose_single_query(query_engine, question, FIQA_USER_ID, idx)

    # Also check a successful query for comparison
    print(f"\n\n{'='*80}")
    print("COMPARISON: Diagnosing a successful query")
    print(f"{'='*80}")

    successful_idx = 0  # Query #1 had good scores
    if successful_idx < len(dataset):
        example = dataset[successful_idx]
        question = example.get("question", "")
        if question:
            await diagnose_single_query(query_engine, question, FIQA_USER_ID, successful_idx)

    # Check if data is actually indexed
    print(f"\n\n{'='*80}")
    print("VERIFYING DATA INDEXING")
    print(f"{'='*80}")

    vector_store = get_vector_store()

    # Try to count documents with user_id filter
    print(f"\nChecking if FiQA data is indexed with user_id={FIQA_USER_ID}...")

    # Note: Qdrant doesn't have a direct count with filters API in LlamaIndex wrapper
    # We'll try a dummy query to see if we get results
    from src.services.retriever.retriever import get_retriever
    from llama_index.core.schema import QueryBundle
    from llama_index.core import Settings

    test_retriever = get_retriever(
        similarity_top_k=1,
        enable_query_fusion=False,
        llm=Settings.llm,
        alpha=0.70,
    )

    test_query = QueryBundle(query_str="financial advice")
    try:
        test_nodes = await test_retriever.aretrieve(test_query)
        if test_nodes:
            print(f"✓ Found {len(test_nodes)} nodes with user_id filter")
            print(f"  Sample metadata: {test_nodes[0].metadata}")
        else:
            print(f"❌ No nodes found with user_id={FIQA_USER_ID}")
            print(f"   Possible issues:")
            print(f"   - Data not ingested yet (run with --skip-ingestion=False)")
            print(f"   - Data ingested with different user_id")
            print(f"   - Qdrant connection issues")
    except Exception as e:
        logger.exception(f"Error checking indexing: {e}")
        print(f"❌ Error: {e}")

    print(f"\n{'='*80}")
    print("DIAGNOSTIC COMPLETE")
    print(f"{'='*80}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
