
from typing import List, Dict, Any, Optional
import json
import csv
from pathlib import Path
from loguru import logger
from datasets import Dataset , load_dataset

from src.services.observability.langfuse_config import get_langfuse_client


class EvaluationDataset:
    """
    Manages evaluation datasets for RAGAS evaluation.
    
    Supports loading from files (JSON/CSV) and from Langfuse traces.
    """
    
    def __init__(self, data: Optional[Dict[str, List[Any]]] = None):
        """
        Initialize evaluation dataset.
        
        Args:
            data: Optional dictionary with keys: question, answer, contexts, ground_truth
        """
        self.data = data or {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
        }
    
    @classmethod
    def load_from_file(cls, file_path: str) -> "EvaluationDataset":
        """
        Load dataset from JSON or CSV file.
        
        Args:
            file_path: Path to dataset file
            
        Returns:
            EvaluationDataset instance
            
        Raises:
            ValueError: If file format is invalid
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Dataset file not found: {file_path}")
        
        if path.suffix.lower() == ".json":
            return cls._load_from_json(file_path)
        elif path.suffix.lower() == ".csv":
            return cls._load_from_csv(file_path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}. Use .json or .csv")
    
    @classmethod
    def _load_from_json(cls, file_path: str) -> "EvaluationDataset":
        """Load dataset from JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        cls._validate_format(data)
        
        return cls(data=data)
    
    @classmethod
    def _load_from_csv(cls, file_path: str) -> "EvaluationDataset":
        """Load dataset from CSV file."""
        data = {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
        }
        
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "question" in row:
                    data["question"].append(row["question"])
                if "answer" in row:
                    data["answer"].append(row["answer"])
                if "contexts" in row:
                    try:
                        contexts = json.loads(row["contexts"]) if row["contexts"] else []
                    except json.JSONDecodeError:
                        contexts = [row["contexts"]] if row["contexts"] else []
                    data["contexts"].append(contexts)
                if "ground_truth" in row:
                    data["ground_truth"].append(row["ground_truth"])
        
        return cls(data=data)
    
    @staticmethod
    def _validate_format(data: Dict[str, List[Any]]) -> None:
        """
        Validate dataset format.
        
        Args:
            data: Dataset dictionary
            
        Raises:
            ValueError: If format is invalid
        """
        required_keys = ["question", "answer", "contexts"]
        
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Missing required key: {key}")
            if not isinstance(data[key], list):
                raise ValueError(f"Key {key} must be a list")
        
        # Check all lists have same length
        lengths = [len(data[key]) for key in required_keys]
        if len(set(lengths)) > 1:
            raise ValueError(
                f"All lists must have the same length. Got: {dict(zip(required_keys, lengths))}"
            )
        
        # Validate contexts format (must be list of lists)
        for i, ctx in enumerate(data["contexts"]):
            if not isinstance(ctx, list):
                raise ValueError(
                    f"contexts[{i}] must be a list of strings, got {type(ctx)}"
                )
    
    def to_ragas_format(self) -> Dataset:
        """
        Convert to RAGAS Dataset format.
        
        Returns:
            RAGAS Dataset object
        """
        return Dataset.from_dict(self.data)
    
    def save_to_file(self, file_path: str, format: str = "json") -> None:
        """
        Save dataset to file.
        
        Args:
            file_path: Path to save file
            format: File format ("json" or "csv")
        """
        path = Path(file_path)
        
        if format.lower() == "json":
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        elif format.lower() == "csv":
            # Flatten contexts for CSV
            rows = []
            for i in range(len(self.data["question"])):
                row = {
                    "question": self.data["question"][i],
                    "answer": self.data["answer"][i],
                    "contexts": json.dumps(self.data["contexts"][i]) if i < len(self.data["contexts"]) else "[]",
                }
                if self.data.get("ground_truth") and i < len(self.data["ground_truth"]):
                    row["ground_truth"] = self.data["ground_truth"][i]
                rows.append(row)
            
            with open(path, "w", encoding="utf-8", newline="") as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'json' or 'csv'")
    
    @classmethod
    def load_from_huggingface(
        cls,
        dataset_name: str,
        split: str = "test",
        subset: Optional[str] = None,
        column_mapping: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        config_name: Optional[str] = None,
    ) -> "EvaluationDataset":
        """
        Load dataset from Hugging Face Datasets.

        Args:
            dataset_name: Name of the dataset (e.g., "explodinggradients/fiqa")
            split: Dataset split to load (default: "test")
            subset: Optional subset name
            column_mapping: Optional mapping from HF columns to required keys
                           (question, answer, contexts, ground_truth)
            limit: Optional number of examples to load

        Returns:
            EvaluationDataset instance
        """
        
        logger.info(f"Loading Hugging Face dataset: {dataset_name} (split={split})")
        
        try:
            # Use subset or config_name as the configuration name (second positional argument)
            target_config = subset or config_name
            if target_config:
                ds = load_dataset(dataset_name, target_config, split=split)
            else:
                ds = load_dataset(dataset_name, split=split)
        except Exception as e:
            raise ValueError(f"Failed to load dataset {dataset_name}: {e}")

        if limit:
            ds = ds.select(range(min(len(ds), limit)))

        mapping = column_mapping or {}
        
        def get_col(standard_name: str, alternatives: List[str]) -> List[Any]:
            if standard_name in mapping:
                col_name = mapping[standard_name]
                if col_name in ds.features:
                    return ds[col_name]
                logger.warning(f"Mapped column '{col_name}' not found in dataset")
            
            if standard_name in ds.features:
                return ds[standard_name]
                
            for alt in alternatives:
                if alt in ds.features:
                    return ds[alt]
            
            return []

        questions = get_col("question", ["query", "input", "question_text", "user_input"])
        answers = get_col("answer", ["response", "output", "answer_text"])
        contexts = get_col("contexts", ["context", "documents", "retrieved_contexts"])
        ground_truths = get_col("ground_truth", ["ground_truths", "reference", "gold_answer"])

        if not questions:
            raise ValueError(f"Could not find 'question' column in dataset {dataset_name}. Available: {ds.column_names}")
        
        if not answers:
             answers = [""] * len(questions)
        if not contexts:
             contexts = [[]] * len(questions)
        if not ground_truths:
             ground_truths = [""] * len(questions)

        formatted_contexts = []
        for ctx in contexts:
            if isinstance(ctx, str):
                try:
                    parsed = json.loads(ctx)
                    formatted_contexts.append(parsed if isinstance(parsed, list) else [str(parsed)])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.debug(f"Could not parse context as JSON: {ctx[:50]}..., error: {e}")
                    formatted_contexts.append([ctx])
            elif isinstance(ctx, list):
                formatted_contexts.append([str(c) for c in ctx])
            else:
                formatted_contexts.append([])

        data = {
            "question": questions,
            "answer": answers,
            "contexts": formatted_contexts,
            "ground_truth": ground_truths,
        }

        # Validate lengths
        min_len = min(len(data["question"]), len(data["answer"]), len(data["contexts"]))
        if len(data["question"]) != min_len:
             logger.warning(f"Truncating dataset to shortest column length: {min_len}")
             for k in data:
                 data[k] = data[k][:min_len]

        return cls(data=data)
    
    @classmethod
    def load_from_langfuse(
        cls,
        trace_name: Optional[str] = None,
        limit: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> "EvaluationDataset":
        """
        Load dataset from Langfuse traces.
        
        Args:
            trace_name: Optional trace name filter
            limit: Maximum number of traces to load
            user_id: Optional user ID filter
            
        Returns:
            EvaluationDataset instance
        """
        langfuse = get_langfuse_client()
        if not langfuse:
            raise RuntimeError("Langfuse client is not available")
        
        try:
            # Fetch traces from Langfuse
            all_traces = []
            page = 1
            
            while True:
                response = langfuse.api.trace.list(
                    name=trace_name,
                    page=page,
                    user_id=user_id,
                )
                
                if not response.data:
                    break
                
                all_traces.extend(response.data)
                
                if limit and len(all_traces) >= limit:
                    all_traces = all_traces[:limit]
                    break
                
                page += 1
            
            # Extract data from traces
            data = {
                "question": [],
                "answer": [],
                "contexts": [],
                "ground_truth": [],
            }
            
            for trace in all_traces:
                # Get observations for this trace
                observations = []
                if hasattr(trace, 'observations') and trace.observations:
                    for obs_id in trace.observations:
                        try:
                            obs = langfuse.api.observations.get(obs_id)
                            observations.append(obs)
                        except Exception as e:
                            logger.warning(f"Failed to get observation {obs_id}: {e}")
                
                # Extract question, answer, and contexts from observations
                question = None
                answer = None
                contexts = []
                
                for obs in observations:
                    if obs.name == "retrieval" and obs.input:
                        question = obs.input.get("question") or obs.input.get("query")
                        if obs.output and "contexts" in obs.output:
                            contexts = obs.output["contexts"]
                    elif obs.name == "generation" or obs.name == "synthesis":
                        if obs.output and "answer" in obs.output:
                            answer = obs.output["answer"]
                        elif obs.output and "response" in obs.output:
                            answer = obs.output["response"]
                
                # Only add if we have all required data
                if question and answer and contexts:
                    data["question"].append(question)
                    data["answer"].append(answer)
                    data["contexts"].append(contexts)
                    data["ground_truth"].append("")  # No ground truth from traces
            
            return cls(data=data)
            
        except Exception as e:
            logger.error(f"Error loading dataset from Langfuse: {e}", exc_info=True)
            raise
    
    def __len__(self) -> int:
        """Return number of examples in dataset."""
        return len(self.data["question"])
    
    def __getitem__(self, index: int) -> Dict[str, Any]:
        """Get a single example by index."""
        return {
            "question": self.data["question"][index],
            "answer": self.data["answer"][index],
            "contexts": self.data["contexts"][index],
            "ground_truth": self.data["ground_truth"][index] if self.data.get("ground_truth") and index < len(self.data["ground_truth"]) else None,
        }

