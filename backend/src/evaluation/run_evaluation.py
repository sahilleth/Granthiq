
import sys

import asyncio
import argparse
import logging
from pathlib import Path



current_file = Path(__file__).resolve()

src_path = current_file.parents[1]
backend_path = current_file.parents[2]

if str(backend_path) not in sys.path:
    sys.path.append(str(backend_path))
if str(src_path) not in sys.path:
    sys.path.append(str(src_path))

from loguru import logger
from src.evaluation.eval_runner import EvaluationRunner
from src.evaluation.test_dataset import EvaluationDataset
from src.config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
# Configure loguru to print to stderr
logger.remove()
logger.add(sys.stderr, level="INFO")

async def main():
    parser = argparse.ArgumentParser(description="Run offline RAG evaluation")
    parser.add_argument("--dataset-name", type=str, default="explodinggradients/fiqa", help="Hugging Face dataset name")
    parser.add_argument("--split", type=str, default="baseline", help="Dataset split (e.g., baseline, train, test)")
    parser.add_argument("--config-name", type=str, default="ragas_eval_v3", help="Dataset config name")
    parser.add_argument("--limit", type=int, default=10, help="Number of examples to evaluate")
    parser.add_argument("--output-file", type=str, default="evaluation_results.json", help="Path to save results")
    parser.add_argument("--skip-retrieval", action="store_true", help="Skip retrieval and use dataset contexts/answers if available")
    parser.add_argument("--user-id", type=str, default=None, help="User ID for retrieval filtering (optional)")
    parser.add_argument("--notebook-id", type=str, default=None, help="Notebook ID for retrieval filtering (optional)")
    
    args = parser.parse_args()
    
    print(f"\nStarting RAG Evaluation")
    print(f"Dataset: {args.dataset_name} ({args.split})")
    print(f"Limit: {args.limit}")
    print(f"Output: {args.output_file}")
    print("-" * 50)

    try:
        # 1. Load Dataset
        print(f"\nLoading dataset from Hugging Face...")
        dataset = EvaluationDataset.load_from_huggingface(
            dataset_name=args.dataset_name,
            split=args.split,
            config_name=args.config_name,
            limit=args.limit
        )
        print(f"Loaded {len(dataset)} examples")

        # 2. Initialize Runner
        print(f"\nInitializing Evaluation Runner...")
        # The runner will initialize the QueryEngineService (with streaming=False) and RAGASEvaluator
        runner = EvaluationRunner()

        # 3. Run Evaluation
        print(f"\nRunning Evaluation (this may take a while)...")
        results = await runner.run_offline_evaluation(
            dataset=dataset,
            output_path=args.output_file,
            user_id=args.user_id,
            notebook_id=args.notebook_id,
            skip_retrieval=args.skip_retrieval
        )

        # 4. Display Results
        if results and "aggregate" in results:
            print("\n" + "="*50)
            print("Evaluation Results")
            print("="*50)
            for metric, score in results["aggregate"].items():
                print(f"{metric:<25}: {score:.4f}")
            print("="*50)
            print(f"\nResults saved to {args.output_file}")
        else:
            print("\nEvaluation returned no results.")

    except Exception as e:
        logger.exception(f"Evaluation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Fix for Windows event loop policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
