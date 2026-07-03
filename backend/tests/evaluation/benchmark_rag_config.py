import sys
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# Add backend to path
current_file = Path(__file__).resolve()
backend_path = current_file.parents[2]
if str(backend_path) not in sys.path:
    sys.path.append(str(backend_path))

from src.evaluation.eval_runner import EvaluationRunner
from src.evaluation.test_dataset import EvaluationDataset
from src.services.query.query_engine import QueryEngineService, get_query_engine
from src.config import get_settings



BASELINE_CONFIG = {
    "name": "Baseline (Legacy Params)",
    "description": "Previous production settings (top_k=15)",
    "config": {
        "streaming": False,
        "similarity_top_k": 15,
        "use_hyde": False,
        "enable_query_fusion": False,
    }
}

OPTIMIZED_CONFIG = {
    "name": "Optimized (New Default)",
    "description": "New production settings (top_k=20, improved prompts)",
    "config": {
        "streaming": False,
        "similarity_top_k": 20,
        "use_hyde": False,
        "enable_query_fusion": True,
        "fusion_num_queries": 4,
    }
}

HYDE_CONFIG = {
    "name": "Advanced (HyDE)",
    "description": "Optimized + HyDE (Hypothetical Document Embeddings)",
    "config": {
        "streaming": False,
        "similarity_top_k": 20,
        "use_hyde": True,
        "enable_query_fusion": True,
        "fusion_num_queries": 4,
    }
}

OPTIMIZED_HYDE_CONFIG = {
    "name": "Production Fast HyDE",
    "description": "Groq-powered HyDE + Compact Synthesis + Reduced Fusion",
    "config": {
        "streaming": False,  # Changed to False for evaluation consistency
        "similarity_top_k": 20,  # Increased for better retrieval
        "use_hyde": True,
        "enable_query_fusion": True,
        "fusion_num_queries": 3,  # Reduced from 4 to 3 for speed
        "reranker_top_n": 10  # Increased for better context
    }
}

TEST_CONFIGS = [
    BASELINE_CONFIG,
    OPTIMIZED_CONFIG,
    HYDE_CONFIG,
    OPTIMIZED_HYDE_CONFIG,
]

# ============================================
# DATASET
# ============================================

DATASET_NAME = "vibrantlabsai/fiqa"
DATASET_SPLIT = "baseline"
DATASET_CONFIG = "ragas_eval_v3"
FIQA_USER_ID = "fiqa-eval-user-2026"
FIQA_NOTEBOOK_ID = "fiqa-eval-notebook-2026"

# ============================================


async def run_ab_test(limit: int = 20, skip_ingestion: bool = True):
    """
    Run A/B test comparing different configurations.
    
    Args:
        limit: Number of examples to test
        skip_ingestion: Whether to skip data ingestion (assumes already indexed)
    """
    print("=" * 80)
    print("🧪 RAG A/B Testing Framework")
    print("=" * 80)
    print(f"Test Dataset: {DATASET_NAME}")
    print(f"Test Size: {limit} examples")
    print(f"Configurations: {len(TEST_CONFIGS)}")
    print("=" * 80)
    
    # 1. Load dataset
    print(f"\n📥 Loading test dataset...")
    dataset = EvaluationDataset.load_from_huggingface(
        dataset_name=DATASET_NAME,
        split=DATASET_SPLIT,
        config_name=DATASET_CONFIG,
        limit=limit
    )
    print(f"✅ Loaded {len(dataset)} examples")
    
    # 2. Run evaluation for each configuration
    results = {}
    
    for i, test_config in enumerate(TEST_CONFIGS, 1):
        config_name = test_config["name"]
        config_desc = test_config["description"]
        
        print(f"\n{'='*80}")
        print(f"🔬 Testing Configuration {i}/{len(TEST_CONFIGS)}: {config_name}")
        print(f"   {config_desc}")
        print(f"{'='*80}")
        
        try:
            # Reset query engine to pick up new settings, passing specific config
            settings_overrides = test_config["config"].copy()
            
            # Add evaluation-specific relaxed policy settings
            # Similarity scores are typically lower than reranker scores
            if "policy_min_score" not in settings_overrides:
                settings_overrides["policy_min_score"] = 0.10  # Relaxed from 0.60
            if "policy_min_chunks" not in settings_overrides:
                settings_overrides["policy_min_chunks"] = 3  # Keep at least 3 chunks
            
            # Ensure reset is True to clear singleton
            query_engine = get_query_engine(reset=True, **settings_overrides)
            
            # Create runner with configured engine
            runner = EvaluationRunner(query_engine=query_engine)
            
            # Run evaluation
            output_path = f"ab_test_{config_name.lower().replace(' ', '_').replace('(', '').replace(')', '')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            result = await runner.run_offline_evaluation(
                dataset=dataset,
                output_path=output_path,
                user_id=FIQA_USER_ID,
                notebook_id=FIQA_NOTEBOOK_ID,
                skip_retrieval=False,  # Always do real retrieval for fair comparison
            )
            
            results[config_name] = {
                **result,
                "config": test_config,
                "output_file": output_path
            }
            
            # Display results
            if result and "aggregate" in result:
                print(f"\n📊 Results for {config_name}:")
                print("-" * 60)
                for metric, score in result["aggregate"].items():
                    print(f"   {metric:<25}: {score:.4f}")
                print("-" * 60)
            
        except Exception as e:
            logger.exception(f"Error testing {config_name}: {e}")
            results[config_name] = {
                "error": str(e),
                "config": test_config
            }
    
    # 3. Compare results
    print(f"\n{'='*80}")
    print("📈 A/B TEST COMPARISON")
    print(f"{'='*80}")
    
    comparison = compare_results(results)
    display_comparison(comparison)
    
    # 4. Save comparison report
    report_path = f"ab_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "test_metadata": {
                "dataset": DATASET_NAME,
                "limit": limit,
                "timestamp": datetime.now().isoformat(),
            },
            "configurations": [TEST_CONFIGS],
            "results": results,
            "comparison": comparison,
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Full report saved to: {report_path}")
    
    return results, comparison


def compare_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare results from different configurations.
    
    Args:
        results: Dictionary of configuration results
        
    Returns:
        Comparison dictionary with improvements and regressions
    """
    comparison = {
        "metrics": {},
        "winner": None,
        "improvements": {},
        "regressions": {},
    }
    
    # Extract aggregate scores
    config_scores = {}
    for config_name, result in results.items():
        if "aggregate" in result:
            config_scores[config_name] = result["aggregate"]
    
    if not config_scores:
        return comparison
    
    # Get metric names from first config
    metrics = list(next(iter(config_scores.values())).keys())
    
    # Compare each metric
    for metric in metrics:
        comparison["metrics"][metric] = {}
        
        for config_name, scores in config_scores.items():
            comparison["metrics"][metric][config_name] = scores.get(metric, 0.0)
    
    # Calculate improvements (compare to baseline/first config)
    baseline_name = list(config_scores.keys())[0]
    baseline_scores = config_scores[baseline_name]
    
    for config_name, scores in config_scores.items():
        if config_name == baseline_name:
            continue
        
        improvements = {}
        regressions = {}
        
        for metric in metrics:
            baseline_val = baseline_scores.get(metric, 0.0)
            test_val = scores.get(metric, 0.0)
            delta = test_val - baseline_val
            percent_change = (delta / baseline_val * 100) if baseline_val > 0 else 0
            
            if delta > 0.001:  # Improvement threshold
                improvements[metric] = {
                    "from": baseline_val,
                    "to": test_val,
                    "delta": delta,
                    "percent_change": percent_change
                }
            elif delta < -0.001:  # Regression threshold
                regressions[metric] = {
                    "from": baseline_val,
                    "to": test_val,
                    "delta": delta,
                    "percent_change": percent_change
                }
        
        comparison["improvements"][config_name] = improvements
        comparison["regressions"][config_name] = regressions
    
    # Determine overall winner (highest average score)
    avg_scores = {}
    for config_name, scores in config_scores.items():
        avg_scores[config_name] = sum(scores.values()) / len(scores)
    
    comparison["winner"] = max(avg_scores.items(), key=lambda x: x[1])[0]
    comparison["avg_scores"] = avg_scores
    
    return comparison


def display_comparison(comparison: Dict[str, Any]):
    """Display comparison results in a readable format."""
    
    # Display metric comparison table
    print("\n📊 Metric Comparison Table")
    print("=" * 80)
    
    metrics = list(comparison["metrics"].keys())
    configs = list(comparison["metrics"][metrics[0]].keys())
    
    # Header
    print(f"{'Metric':<25} | " + " | ".join([f"{c[:20]:<20}" for c in configs]))
    print("-" * 80)
    
    # Rows
    for metric in metrics:
        row = f"{metric:<25} | "
        values = []
        for config in configs:
            score = comparison["metrics"][metric][config]
            values.append(f"{score:.4f}")
        row += " | ".join([f"{v:<20}" for v in values])
        print(row)
    
    # Average
    if "avg_scores" in comparison:
        print("-" * 80)
        row = f"{'AVERAGE':<25} | "
        values = [f"{comparison['avg_scores'][c]:.4f}" for c in configs]
        row += " | ".join([f"{v:<20}" for v in values])
        print(row)
    
    print("=" * 80)
    
    # Display improvements/regressions
    for config_name in comparison["improvements"]:
        improvements = comparison["improvements"][config_name]
        regressions = comparison["regressions"][config_name]
        
        print(f"\n🔬 {config_name} vs Baseline:")
        
        if improvements:
            print("\n   ✅ Improvements:")
            for metric, data in improvements.items():
                print(f"      • {metric}: {data['from']:.4f} → {data['to']:.4f} "
                      f"(+{data['delta']:.4f}, +{data['percent_change']:.1f}%)")
        
        if regressions:
            print("\n   ⚠️  Regressions:")
            for metric, data in regressions.items():
                print(f"      • {metric}: {data['from']:.4f} → {data['to']:.4f} "
                      f"({data['delta']:.4f}, {data['percent_change']:.1f}%)")
        
        if not improvements and not regressions:
            print("   → No significant changes")
    
    # Display winner
    if comparison["winner"]:
        print(f"\n🏆 Winner: {comparison['winner']}")
        print(f"   Average Score: {comparison['avg_scores'][comparison['winner']]:.4f}")


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="A/B test RAG configuration improvements")
    parser.add_argument("--limit", type=int, default=20, 
                       help="Number of examples to test (default: 20)")
    parser.add_argument("--skip-ingestion", action="store_true",
                       help="Skip data ingestion (assumes already indexed)")
    args = parser.parse_args()
    
    await run_ab_test(limit=args.limit, skip_ingestion=args.skip_ingestion)


if __name__ == "__main__":
    # Fix for Windows event loop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
