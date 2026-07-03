from typing import List, Dict, Any, Optional
import asyncio
from loguru import logger
from datasets import Dataset

from ragas import aevaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)

from langchain_litellm import ChatLiteLLM
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from src.config import get_settings
from src.utils.json_cleaning import JSONCleaningLLM
from langchain_community.embeddings import OpenAIEmbeddings


class RAGASEvaluator:
    """
    RAGAS evaluator for evaluating RAG pipeline responses.
    """
    
    def __init__(self, metrics: Optional[List[str]] = None):
        settings = get_settings()
        self.metrics = metrics or settings.evaluation.metrics
        
        # Metric mapping
        self.metric_map = {
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_precision": context_precision,
            "context_recall": context_recall,
        }
        
        self.ragas_metrics = []
        for metric_name in self.metrics:
            if metric_name in self.metric_map:
                self.ragas_metrics.append(self.metric_map[metric_name])
            else:
                logger.warning(f"Unknown metric: {metric_name}. Skipping.")
        
        if not self.ragas_metrics:
            raise ValueError("No valid RAGAS metrics specified")
        
        logger.info(f"Initialized RAGAS evaluator with metrics: {self.metrics}")

    def _get_llm_and_embeddings(self, settings):
        """
        Setup LLM and Embeddings using LiteLLM for better rate limit handling.
        """
        
        if settings.llm.gemini_api_key:
            logger.info("Using Gemini via LiteLLM for RAGAS evaluation (unlimited tier)")
            model = "gemini/gemini-2.5-flash"
            api_key = settings.llm.gemini_api_key
            needs_json_cleaning = True
        elif settings.llm.groq_api_key:
            logger.info("Using Groq via LiteLLM for RAGAS evaluation")
            model = "groq/llama-3.1-70b-versatile"  # Higher TPM limit than 8b
            api_key = settings.llm.groq_api_key
            needs_json_cleaning = False
        elif settings.llm.openai_api_key:
            logger.info("Using OpenAI via LiteLLM for RAGAS evaluation")
            model = "gpt-4o-mini"
            api_key = settings.llm.openai_api_key
            needs_json_cleaning = False
        else:
            raise ValueError("No LLM API key available")
        
        # Create LiteLLM chat model with robust retry settings
        base_llm = ChatLiteLLM(
            model=model,
            api_key=api_key,
            temperature=0,
            max_retries=5,  # Automatic retries for rate limits
            request_timeout=60,
            # LiteLLM-specific settings for rate limiting
            num_retries=3,  # Additional retry layer
        )
        
        # Wrap with JSON cleaning for Gemini
        if needs_json_cleaning:
            logger.info("Wrapping LLM with JSON cleaning to handle Gemini's markdown responses")
            base_llm = JSONCleaningLLM(llm=base_llm)

        # 2. Setup Embeddings
        # Priority: Gemini (free, unlimited) → OpenAI → HuggingFace (fallback)
        if settings.llm.gemini_api_key:
            
            logger.info("Using Gemini embeddings for RAGAS (free, unlimited)")
            base_embeddings = GoogleGenerativeAIEmbeddings(
                google_api_key=settings.llm.gemini_api_key,
                model="models/embedding-001"  # Free embedding model
            )
        elif settings.llm.openai_api_key:
            logger.info("Using OpenAI embeddings for RAGAS")
            base_embeddings = OpenAIEmbeddings(api_key=settings.llm.openai_api_key)
        else:
            # Last resort: local HuggingFace (slow, may fail)
            logger.warning("Using HuggingFace embeddings - may be slow or fail silently")
            base_embeddings = HuggingFaceEmbeddings(
                model_name="BAAI/bge-small-en-v1.5",
                model_kwargs={'device': 'cpu'}
            )

        # 3. Return LangChain objects (RAGAS 0.4.0 compatibility)
        return base_llm, base_embeddings

    def _prepare_metrics(self, ground_truth: bool, ragas_llm, ragas_embeddings):
        """
        Filter metrics based on whether ground truth is available.
        
        In RAGAS 0.4.0, metrics need to be explicitly initialized with LLM and embeddings
        to avoid AssertionErrors like 'answer_relevancy requires embeddings to be set'.
        """
        metrics_to_use = []

        for metric in self.ragas_metrics:
            metric_name = metric.name if hasattr(metric, "name") else str(metric)
            
            
            if not ground_truth and metric_name in ["context_precision", "context_recall", "context_entities_recall"]:
                logger.debug(f"Skipping {metric_name} (requires ground truth)")
                continue
            try:
                if hasattr(metric, 'llm'):
                    metric.llm = ragas_llm
                if hasattr(metric, 'embeddings'):
                    metric.embeddings = ragas_embeddings
            except Exception as e:
                logger.warning(f"Failed to set dependencies on {metric_name}: {e}")

            metrics_to_use.append(metric)
            
        return metrics_to_use

    async def evaluate_single(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: Optional[str] = None,
        timeout: float = 120.0,
    ) -> Dict[str, float]:
        """
        Evaluate a single query by treating it as a batch of size 1.
        """
        # Validate inputs
        if not contexts or not answer:
            logger.warning("Empty contexts or answer, skipping evaluation")
            return {}
        
        
        if not all(isinstance(c, str) for c in contexts):
            logger.error("All contexts must be strings")
            return {}
        
        try:
            settings = get_settings()
            ragas_llm, ragas_embeddings = self._get_llm_and_embeddings(settings)
            
            # Prepare dataset (Batch of 1)
            data = {
                "question": [str(question)],
                "answer": [str(answer)],
                "contexts": [contexts], # List of lists
            }
            if ground_truth:
                data["ground_truth"] = [str(ground_truth)]
                data["reference"] = [str(ground_truth)]
            
            dataset = Dataset.from_dict(data)
            
            # Get metrics (filtered and initialized with LLM/embeddings)
            metrics_to_use = self._prepare_metrics(ground_truth is not None, ragas_llm, ragas_embeddings)
            
            if not metrics_to_use:
                return {}

            # USE aevaluate DIRECTLY (Async Native)
            # Pass llm and embeddings explicitly here as well for safety
            result = await asyncio.wait_for(
                aevaluate(
                    dataset, 
                    metrics=metrics_to_use,
                    llm=ragas_llm,
                    embeddings=ragas_embeddings
                ),
                timeout=timeout
            )
            
         
            scores = {}
            
            # Convert to pandas DataFrame and extract scores
            try:
                result_df = result.to_pandas()
                for metric_name in self.metrics:
                    if metric_name in result_df.columns:
                            
                        metric_value = result_df[metric_name].iloc[0]
                        scores[metric_name] = float(metric_value) if metric_value is not None else 0.0
            except Exception as e:
                logger.warning(f"Failed to extract scores via to_pandas(), trying direct access: {e}")
                if hasattr(result, '_scores_dict'):
                    for metric_name in self.metrics:
                        if metric_name in result._scores_dict:
                            metric_values = result._scores_dict[metric_name]
                            scores[metric_name] = float(metric_values[0]) if metric_values else 0.0
            
            logger.info(f"Evaluation Scores: {scores}")
            return scores
            
        except Exception as e:
            logger.error(f"Error in RAGAS single evaluation: {repr(e)}", exc_info=True)
            logger.exception("Full traceback:")
            return {}
    
    async def evaluate_batch(
        self,
        questions: List[str],
        answers: List[str],
        contexts_list: List[List[str]],
        ground_truths: Optional[List[str]] = None,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Evaluate multiple queries.
        """
        try:
            logger.info(f"Starting batch evaluation for {len(questions)} queries...")
            settings = get_settings()
            ragas_llm, ragas_embeddings = self._get_llm_and_embeddings(settings)
            
            data = {
                "question": questions,
                "answer": answers,
                "contexts": contexts_list,
            }
            if ground_truths:
                data["ground_truth"] = ground_truths
                data["reference"] = ground_truths

            dataset = Dataset.from_dict(data)

            # Get metrics (filtered and initialized with LLM/embeddings)
            metrics_to_use = self._prepare_metrics(ground_truths is not None, ragas_llm, ragas_embeddings)

            result = await asyncio.wait_for(
                aevaluate(
                    dataset, 
                    metrics=metrics_to_use,
                    llm=ragas_llm,
                    embeddings=ragas_embeddings
                ),
                timeout=timeout
            )
            
            # Process results from RAGAS 0.4.0 EvaluationResult object
            scores = {}
            aggregate = {}
            
            try:
                # Convert to pandas DataFrame
                result_df = result.to_pandas()
                
                for metric_name in self.metrics:
                    if metric_name in result_df.columns:
                        metric_scores = result_df[metric_name].tolist()
                        
                        # Clean NaN values
                        clean_scores = []
                        for s in metric_scores:
                            try:
                                f = float(s)
                                clean_scores.append(0.0 if str(f) == 'nan' else f)
                            except (ValueError, TypeError) as e:
                                logger.debug(f"Could not convert score to float: {s}, error: {e}")
                                clean_scores.append(0.0)
                                
                        scores[metric_name] = clean_scores
                        
                        if clean_scores:
                            aggregate[metric_name] = sum(clean_scores) / len(clean_scores)
            
            except Exception as e:
                logger.warning(f"Failed to extract scores via to_pandas(), trying direct access: {e}")
                # Fallback: access _scores_dict directly
                if hasattr(result, '_scores_dict'):
                    for metric_name in self.metrics:
                        if metric_name in result._scores_dict:
                            metric_values = result._scores_dict[metric_name]
                            
                            # Clean NaN values
                            clean_scores = []
                            for s in metric_values:
                                try:
                                    f = float(s)
                                    clean_scores.append(0.0 if str(f) == 'nan' else f)
                                except (ValueError, TypeError) as e:
                                    logger.debug(f"Could not convert metric value to float: {s}, error: {e}")
                                    clean_scores.append(0.0)
                                    
                            scores[metric_name] = clean_scores
                            
                            if clean_scores:
                                aggregate[metric_name] = sum(clean_scores) / len(clean_scores)
            
            print("\n=== RAGAS Evaluation Results ===")
            for metric, score in aggregate.items():
                print(f"{metric}: {score:.4f}")
            print("================================\n")
            
            return {
                "scores": scores,
                "aggregate": aggregate,
                "num_queries": len(questions),
            }
            
        except Exception as e:
            logger.error(f"Error in RAGAS batch evaluation: {repr(e)}", exc_info=True)
            logger.exception("Full traceback:")
            return {}


def get_ragas_evaluator(metrics: Optional[List[str]] = None) -> Optional[RAGASEvaluator]: 
    try:
        return RAGASEvaluator(metrics=metrics)
    except Exception as e:
        logger.error(f"Failed to create RAGAS evaluator: {e}")
        return None
