"""
Investigate zero-score queries from FiQA evaluation.

This script analyzes queries that received zero scores in RAGAS evaluation
to understand why retrieval failed.
"""
import sys
from pathlib import Path

# Add backend to path
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import asyncio
from src.evaluation.test_dataset import EvaluationDataset
from src.db.vector_store import get_vector_store
from src.services.query.query_engine import QueryEngineService
from src.config import get_settings

FIQA_USER_ID = "fiqa-eval-user-2024"
DATASET_NAME = "vibrantlabsai/fiqa"
DATASET_SPLIT = "baseline"
DATASET_CONFIG = "ragas_eval_v3"


async def investigate_query(dataset: EvaluationDataset, query_index: int, user_id: str):
    """Investigate a specific query to understand why it got zero scores."""
    print(f"\n{'='*80}")
    print(f"Investigating Query {query_index + 1}")
    print(f"{'='*80}")
    
    example = dataset[query_index]
    question = example.get("question", "")
    contexts = example.get("contexts", [])
    ground_truth = example.get("ground_truth", "")
    
    print(f"\nQuestion: {question}")
    print(f"\nGround Truth: {ground_truth[:200]}..." if len(ground_truth) > 200 else f"\nGround Truth: {ground_truth}")
    print(f"\nNumber of ground truth contexts: {len(contexts)}")
    
    # Check if contexts exist
    if not contexts:
        print("⚠️  WARNING: No ground truth contexts found for this query!")
        return
    
    print(f"\nFirst context preview:")
    for i, ctx in enumerate(contexts[:2]):
        print(f"  Context {i+1}: {ctx[:150]}...")
    
    # Initialize query engine
    settings = get_settings()
    eval_top_k = max(settings.rag.top_k_results, 20)
    
    query_engine = QueryEngineService(
        streaming=False,
        similarity_top_k=eval_top_k,
        enable_query_fusion=True,
        fusion_num_queries=3,
        use_hyde=False,
        policy_min_score=0.20,
        policy_min_chunks=3,
        policy_disabled=False,  # Test with policy enabled first
    )
    
    # Run query
    print(f"\n{'='*80}")
    print("Running Query (with policy enabled)...")
    print(f"{'='*80}")

    # IMPORTANT: QueryEngineService.aquery expects query_str (string), not a QueryBundle.
    # Passing a QueryBundle will break retrieval and can accidentally fall back to anonymous_user_id.
    # Add an extra filter to ensure we're only searching FiQA-ingested nodes
    extra_filters = {"source_type": "fiqa_dataset"}
    response = await query_engine.aquery(
        question,
        filters=extra_filters,
        user_id=user_id,
    )
    
    print(f"\nAnswer: {response.response[:300]}..." if len(response.response) > 300 else f"\nAnswer: {response.response}")
    print(f"\nNumber of source nodes: {len(response.source_nodes)}")
    
    # Analyze retrieved nodes
    if response.source_nodes:
        print(f"\nRetrieved Nodes:")
        for i, node in enumerate(response.source_nodes[:5]):
            score = getattr(node, "score", None)
            score_str = f"{score:.4f}" if isinstance(score, (int, float)) else "N/A"
            text_preview = node.text[:100] if hasattr(node, 'text') else str(node)[:100]
            print(f"  Node {i+1}: score={score_str}, text={text_preview}...")
    else:
        print("\n⚠️  WARNING: No nodes retrieved!")
    
    # Check vector store directly
    print(f"\n{'='*80}")
    print("Checking Vector Store Directly...")
    print(f"{'='*80}")
    
    vector_store = get_vector_store()
    
    # Try to find relevant chunks by searching for keywords from the question
    import re
    keywords = re.findall(r'\b\w{4,}\b', question.lower())
    print(f"\nSearching for keywords: {keywords[:5]}")
    
    # Count chunks for this user
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    user_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.user_id",
                match=MatchValue(value=user_id)
            )
        ]
    )
    
    # Scroll to count chunks
    scroll_result = vector_store.client.scroll(
        collection_name=vector_store.collection_name,
        scroll_filter=user_filter,
        limit=100
    )
    
    total_chunks = len(scroll_result[0])
    print(f"\nTotal chunks for user '{user_id}': {total_chunks}")
    
    # Check if any chunks contain keywords from the question
    matching_chunks = []
    for point in scroll_result[0][:50]:  # Check first 50
        payload = point.payload
        text = payload.get("text", "") if isinstance(payload, dict) else ""
        if text:
            text_lower = text.lower()
            matches = sum(1 for kw in keywords[:5] if kw in text_lower)
            if matches > 0:
                matching_chunks.append((point.id, matches, text[:100]))
    
    print(f"\nChunks matching question keywords: {len(matching_chunks)}")
    if matching_chunks:
        print("Top matching chunks:")
        for chunk_id, match_count, text_preview in sorted(matching_chunks, key=lambda x: x[1], reverse=True)[:5]:
            print(f"  Matches: {match_count}, ID: {chunk_id}, Text: {text_preview}...")
    
    # Test with policy disabled
    print(f"\n{'='*80}")
    print("Testing with Policy Disabled...")
    print(f"{'='*80}")
    
    query_engine_no_policy = QueryEngineService(
        streaming=False,
        similarity_top_k=eval_top_k,
        enable_query_fusion=True,
        fusion_num_queries=3,
        use_hyde=False,
        policy_disabled=True,  # Disable policy
    )

    response_no_policy = await query_engine_no_policy.aquery(
        question,
        filters=extra_filters,
        user_id=user_id,
    )
    
    print(f"\nAnswer (no policy): {response_no_policy.response[:300]}..." if len(response_no_policy.response) > 300 else f"\nAnswer (no policy): {response_no_policy.response}")
    print(f"\nNumber of source nodes (no policy): {len(response_no_policy.source_nodes)}")
    
    if response_no_policy.source_nodes:
        print(f"\nRetrieved Nodes (no policy):")
        for i, node in enumerate(response_no_policy.source_nodes[:5]):
            score = getattr(node, "score", None)
            score_str = f"{score:.4f}" if isinstance(score, (int, float)) else "N/A"
            text_preview = node.text[:100] if hasattr(node, 'text') else str(node)[:100]
            print(f"  Node {i+1}: score={score_str}, text={text_preview}...")


async def main():
    """Main investigation function."""
    import argparse
    parser = argparse.ArgumentParser(description="Investigate zero-score queries")
    parser.add_argument(
        "--queries",
        type=str,
        default="5,8",
        help="Comma-separated list of query numbers (1-based, as shown in evaluation output). Example: \"5,8\"",
    )
    args = parser.parse_args()
    
    # Parse query indices (treat as 1-based query numbers)
    query_numbers = [int(q.strip()) for q in args.queries.split(",")]
    query_indices = [q - 1 for q in query_numbers]
    
    print("="*80)
    print("Zero-Score Query Investigation")
    print("="*80)
    print(f"Investigating queries: {query_numbers}")
    print(f"User ID: {FIQA_USER_ID}")
    print("="*80)
    
    # Load dataset
    print("\nLoading FiQA dataset...")
    dataset = EvaluationDataset.load_from_huggingface(
        dataset_name=DATASET_NAME,
        split=DATASET_SPLIT,
        config_name=DATASET_CONFIG,
        limit=max(query_indices) + 1
    )
    print(f"Loaded {len(dataset)} examples")
    
    # Investigate each query
    for query_idx in query_indices:
        if query_idx >= len(dataset) or query_idx < 0:
            print(f"\n⚠️  Query number {query_idx + 1} is out of range (dataset has {len(dataset)} examples)")
            continue
        
        await investigate_query(dataset, query_idx, FIQA_USER_ID)
    
    print("\n" + "="*80)
    print("Investigation Complete")
    print("="*80)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
