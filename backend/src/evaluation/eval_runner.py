from typing import List, Dict, Any, Optional
from pathlib import Path
from loguru import logger

from src.config import get_settings
from src.evaluation.ragas_evaluator import get_ragas_evaluator
from src.evaluation.test_dataset import EvaluationDataset
from src.services.query.query_engine import QueryEngineService
from src.services.query.response_utils import extract_response_text, extract_contexts_from_nodes


class EvaluationRunner:
    """
    Runner for offline batch evaluation of RAG pipeline.
    
    Supports:
    - Evaluating datasets from files
    - Evaluating queries from Langfuse traces
    - Comparing different configurations
    """
    
    def __init__(self, query_engine: Optional[QueryEngineService] = None):
        """
        Initialize evaluation runner.
        
        Args:
            query_engine: Optional query engine instance. If None, creates a new one.
        """
        self.query_engine = query_engine
        self.evaluator = get_ragas_evaluator()
        
        if not self.evaluator:
            raise RuntimeError("RAGAS evaluator is not available")
    
    async def run_offline_evaluation(
        self,
        dataset: Optional[EvaluationDataset] = None,
        dataset_path: Optional[str] = None,
        output_path: Optional[str] = None,
        user_id: Optional[str] = None,
        notebook_id: Optional[str] = None,
        skip_retrieval: bool = False,
    ) -> Dict[str, Any]:
        """
        Run offline batch evaluation on a dataset.
        
        Args:
            dataset: Optional EvaluationDataset instance
            dataset_path: Optional path to dataset file (JSON/CSV)
            output_path: Optional path to save results
            user_id: Optional user ID to use for queries (defaults to anonymous)
            notebook_id: Optional notebook ID to filter retrieval (for testing specific notebook)
            skip_retrieval: If True, use contexts from dataset instead of retrieving
            
        Returns:
            Dictionary with evaluation results
        """
      
        if dataset is None:
            if dataset_path is None:
                settings = get_settings()
                dataset_path = settings.evaluation.evaluation_dataset_path
            
            if dataset_path is None:
                raise ValueError("Either dataset or dataset_path must be provided")
            
            dataset = EvaluationDataset.load_from_file(dataset_path)
        
        if len(dataset) == 0:
            raise ValueError("Dataset is empty")
        
        logger.info(f"Running offline evaluation on {len(dataset)} examples")
        
        if self.query_engine is None:
            # Use higher similarity_top_k and evaluation-friendly settings
            settings = get_settings()
            default_top_k = settings.rag.top_k_results
            # Increase retrieval for evaluation (20 chunks for better RAGAS scores)
            eval_top_k = max(default_top_k, 20)
            
            # Evaluation-specific policy: use the same stable settings as A/B tests
            # (0.20 / 3) to avoid over-drops while still filtering absolute junk.
            eval_policy_min_score = 0.20
            eval_policy_min_chunks = 3

            # Evaluation retrieval tuning:
            # - reduce alpha to give sparse (BM42) more influence (helps keyword-y queries)
            # - increase reranker_top_n so good chunks aren't pruned too early
            eval_hybrid_alpha = 0.30
            eval_reranker_top_n = 10
            
            self.query_engine = QueryEngineService(
                streaming=False,
                similarity_top_k=eval_top_k,
                enable_query_fusion=True,
                fusion_num_queries=4,
                use_hyde=False,
                hybrid_alpha=eval_hybrid_alpha,
                reranker_top_n=eval_reranker_top_n,
                policy_min_score=eval_policy_min_score,
                policy_min_chunks=eval_policy_min_chunks,
            )
            logger.info(
                f"Created query engine for evaluation: "
                f"similarity_top_k={eval_top_k}, "
                f"policy_min_score={eval_policy_min_score}, "
                f"policy_min_chunks={eval_policy_min_chunks}, "
                f"hybrid_alpha={eval_hybrid_alpha}, "
                f"reranker_top_n={eval_reranker_top_n}"
            )
        
       
        questions = []
        answers = []
        contexts_list = []
        ground_truths = []
        
        for i in range(len(dataset)):
            example = dataset[i]
            question = example["question"]
            ground_truth = example.get("ground_truth")
            provided_contexts = example.get("contexts", [])
            provided_answer = example.get("answer", "")
            
            logger.info(f"Processing query {i+1}/{len(dataset)}: {question[:50]}...")
            
            try:
                if skip_retrieval:
                    answer = provided_answer
                    contexts = provided_contexts
                    if not answer:
                        logger.warning(f"No answer found in dataset for query {i+1}, skipping")
                        continue
                else:
                    settings = get_settings()
                    target_user_id = user_id or str(settings.anonymous_user_id)
                    
                    # Build filters for proper retrieval
                    filters = {}
                    if notebook_id:
                        filters['notebook_id'] = str(notebook_id)
                        logger.debug(f"Using notebook_id filter: {notebook_id}")
                    
                    response = await self.query_engine.aquery(
                        question, 
                        filters=filters,
                        user_id=target_user_id
                    )
                    
                    answer = extract_response_text(response)
                    source_nodes = getattr(response, 'source_nodes', [])
                    contexts = extract_contexts_from_nodes(source_nodes)
                    
                    # Log retrieval quality
                    logger.info(
                        f"Query {i+1} retrieved {len(contexts)} chunks "
                        f"(answer length: {len(answer)} chars)"
                    )
                
                questions.append(question)
                answers.append(answer)
                contexts_list.append(contexts)
                if ground_truth:
                    ground_truths.append(ground_truth)
                
            except Exception as e:
                logger.error(f"Error processing query {i+1}: {repr(e)}", exc_info=True)
                continue
        
        if not questions:
            raise ValueError("No successful queries to evaluate")
        
        logger.info(f"Running RAGAS evaluation on {len(questions)} queries...")
        
        result = await self.evaluator.evaluate_batch(
            questions=questions,
            answers=answers,
            contexts_list=contexts_list,
            ground_truths=ground_truths if ground_truths else None,
            timeout=1200.0,
        )
        
        if output_path:
            import json
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path_obj, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Results saved to {output_path}")
        
        return result
    
    async def evaluate_from_langfuse_traces(
        self,
        trace_name: Optional[str] = None,
        limit: Optional[int] = None,
        user_id: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate historical queries from Langfuse traces.
        
        Args:
            trace_name: Optional trace name filter
            limit: Maximum number of traces to evaluate
            user_id: Optional user ID filter
            output_path: Optional path to save results
            
        Returns:
            Dictionary with evaluation results
        """
        logger.info("Loading dataset from Langfuse traces...")
        
        # Load dataset from Langfuse
        dataset = EvaluationDataset.load_from_langfuse(
            trace_name=trace_name,
            limit=limit,
            user_id=user_id,
        )
        
        if len(dataset) == 0:
            raise ValueError("No traces found in Langfuse")
        
        logger.info(f"Loaded {len(dataset)} examples from Langfuse")
        
        # Run evaluation
        return await self.run_offline_evaluation(
            dataset=dataset,
            output_path=output_path,
            user_id=user_id,
        )
    
    async def compare_configurations(
        self,
        dataset: EvaluationDataset,
        configs: List[Dict[str, Any]],
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compare different RAG configurations on the same dataset.
        
        Args:
            dataset: Evaluation dataset
            configs: List of configuration dictionaries
            output_path: Optional path to save comparison results
            
        Returns:
            Dictionary with comparison results
        """
        results = {}
        
        for i, config in enumerate(configs):
            logger.info(f"Evaluating configuration {i+1}/{len(configs)}: {config}")
            
            # Create query engine with this configuration
            query_engine = QueryEngineService(**config)
            
            # Create runner with this query engine
            runner = EvaluationRunner(query_engine=query_engine)
            
            # Run evaluation
            result = await runner.run_offline_evaluation(dataset=dataset)
            
            config_name = config.get("name", f"config_{i+1}")
            results[config_name] = result
        
        # Save comparison if output path provided
        if output_path:
            import json
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path_obj, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Comparison results saved to {output_path}")
        
        return results

