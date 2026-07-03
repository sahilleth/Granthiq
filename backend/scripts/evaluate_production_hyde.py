#!/usr/bin/env python3
"""
Evaluate on PRODUCTION data (not FiQA)
This will show if HyDE actually helps with your real documents.
"""
import sys
import asyncio
from pathlib import Path

# Add backend to path
current_file = Path(__file__).resolve()
backend_path = current_file.parents[2]
if str(backend_path) not in sys.path:
    sys.path.append(str(backend_path))

from src.evaluation.eval_runner import EvaluationRunner
from src.evaluation.test_dataset import EvaluationDataset
from src.services.query.query_engine import QueryEngineService


# Use your actual production document
PROD_USER_ID = "eaa585c2-9a2c-445e-9b8c-eaf5bb6bf4fa"
PROD_NOTEBOOK_ID = "1504830e-2f2a-426b-a934-0625a3cb9812"


async def main():
    """Run evaluation on production data with HyDE enabled."""
    
    print("=" * 70)
    print(" PRODUCTION DATA EVALUATION (Clinical Trials Paper)")
    print("=" * 70)
    print(f"User ID: {PROD_USER_ID}")
    print(f"Notebook ID: {PROD_NOTEBOOK_ID}")
    print(f"Expected chunks: ~77 (actual document)")
    print("=" * 70)
    
    # Create test queries based on YOUR document content
    test_queries = [
        "What is the novelty of this paper?",
        "What are the main contributions of this research?",
        "How does this approach differ from cloud-based alternatives?",
        "What is the model compression strategy used?",
        "What datasets were used for evaluation?",
        "What are the key findings about privacy-preserving AI?",
        "How does the edge deployment work?",
        "What are the limitations of this approach?",
    ]
    
    # Create dataset manually
    data = {
        "question": test_queries,
        "answer": [""] * len(test_queries),  # Will be generated
        "contexts": [[]] * len(test_queries),  # Will be retrieved
        "ground_truth": [""] * len(test_queries),  # Not used
    }
    
    dataset = EvaluationDataset(data=data)
    
    print(f"\nCreated {len(dataset)} test queries for your clinical trials paper")
    print("\nInitializing query engine WITH HyDE enabled...")
    
    # Test with HyDE ENABLED (production config)
    query_engine_hyde = QueryEngineService(
        streaming=False,
        similarity_top_k=30,
        enable_query_fusion=True,
        fusion_num_queries=4,
        use_hyde=True,  # ✅ ENABLED
        hybrid_alpha=0.7,
        reranker_top_n=10,
        policy_min_score=0.15,  # Production threshold
        policy_min_chunks=1,
    )
    
    runner_hyde = EvaluationRunner(query_engine=query_engine_hyde)
    
    print("\n" + "=" * 70)
    print(" Running Evaluation WITH HyDE")
    print("=" * 70)
    
    results_hyde = await runner_hyde.run_offline_evaluation(
        dataset=dataset,
        output_path="production_eval_WITH_hyde.json",
        user_id=PROD_USER_ID,
        notebook_id=PROD_NOTEBOOK_ID,
        skip_retrieval=False,
    )
    
    # Test with HyDE DISABLED (for comparison)
    query_engine_no_hyde = QueryEngineService(
        streaming=False,
        similarity_top_k=30,
        enable_query_fusion=True,
        fusion_num_queries=4,
        use_hyde=False,  # ❌ DISABLED
        hybrid_alpha=0.7,
        reranker_top_n=10,
        policy_min_score=0.15,
        policy_min_chunks=1,
    )
    
    runner_no_hyde = EvaluationRunner(query_engine=query_engine_no_hyde)
    
    print("\n" + "=" * 70)
    print(" Running Evaluation WITHOUT HyDE")
    print("=" * 70)
    
    results_no_hyde = await runner_no_hyde.run_offline_evaluation(
        dataset=dataset,
        output_path="production_eval_WITHOUT_hyde.json",
        user_id=PROD_USER_ID,
        notebook_id=PROD_NOTEBOOK_ID,
        skip_retrieval=False,
    )
    
    # Compare results
    print("\n" + "=" * 70)
    print(" COMPARISON: Production Data (77 chunks)")
    print("=" * 70)
    
    print("\nWITH HyDE:")
    for metric, score in results_hyde["aggregate"].items():
        print(f"  {metric}: {score:.4f}")
    
    print("\nWITHOUT HyDE:")
    for metric, score in results_no_hyde["aggregate"].items():
        print(f"  {metric}: {score:.4f}")
    
    # Calculate improvement
    hyde_avg = sum(results_hyde["aggregate"].values()) / len(results_hyde["aggregate"])
    no_hyde_avg = sum(results_no_hyde["aggregate"].values()) / len(results_no_hyde["aggregate"])
    improvement = ((hyde_avg - no_hyde_avg) / no_hyde_avg) * 100
    
    print(f"\n{'=' * 70}")
    print(f" HyDE Impact: {improvement:+.1f}%")
    print(f"{'=' * 70}")
    
    if improvement > 0:
        print("✅ HyDE HELPS on production data (keep enabled)")
    else:
        print("⚠️ HyDE HURTS on production data (investigate why)")
    
    print(f"\nResults saved to:")
    print(f"  - production_eval_WITH_hyde.json")
    print(f"  - production_eval_WITHOUT_hyde.json")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
