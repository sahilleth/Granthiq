from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json
from loguru import logger


class ComparisonReportGenerator:
    """Generate comparison reports for RAGAS evaluation results."""
    
    def __init__(self):
        self.metric_names = [
            "faithfulness",
            "answer_relevancy", 
            "context_precision",
            "context_recall"
        ]
    
    def load_results(self, file_path: str) -> Dict:
        """Load evaluation results from JSON file."""
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def calculate_average(self, results: Dict) -> float:
        """Calculate average score across all metrics."""
        aggregate = results.get("aggregate", {})
        scores = [aggregate.get(metric, 0.0) for metric in self.metric_names if metric in aggregate]
        return sum(scores) / len(scores) if scores else 0.0
    
    def compare_configurations(
        self,
        baseline_results: Dict,
        optimized_results: Dict,
        baseline_name: str = "Baseline",
        optimized_name: str = "Optimized"
    ) -> Dict:
        """
        Compare two evaluation configurations and calculate improvements/regressions.
        
        Returns:
            Dict with comparison data including:
            - metrics: List of metric comparisons
            - improvements: List of improved metrics
            - regressions: List of regressed metrics
            - summary: Overall summary
        """
        comparison = {
            "baseline_name": baseline_name,
            "optimized_name": optimized_name,
            "metrics": [],
            "improvements": [],
            "regressions": [],
            "summary": {}
        }
        
        baseline_avg = self.calculate_average(baseline_results)
        optimized_avg = self.calculate_average(optimized_results)
        
        baseline_aggregate = baseline_results.get("aggregate", {})
        optimized_aggregate = optimized_results.get("aggregate", {})
        
        for metric in self.metric_names:
            baseline_score = baseline_aggregate.get(metric, 0.0)
            optimized_score = optimized_aggregate.get(metric, 0.0)
            
            if baseline_score == 0.0 and optimized_score == 0.0:
                continue  # Skip metrics not evaluated
            
            diff = optimized_score - baseline_score
            percent_change = (diff / baseline_score * 100) if baseline_score > 0 else 0.0
            
            metric_data = {
                "metric": metric,
                "baseline": baseline_score,
                "optimized": optimized_score,
                "diff": diff,
                "percent_change": percent_change,
                "status": "improved" if diff > 0.001 else ("regressed" if diff < -0.001 else "unchanged")
            }
            
            comparison["metrics"].append(metric_data)
            
            # Categorize as improvement or regression
            if diff > 0.001:  # Significant improvement (>0.1%)
                comparison["improvements"].append(metric_data)
            elif diff < -0.001:  # Significant regression (>0.1%)
                comparison["regressions"].append(metric_data)
        
        comparison["summary"] = {
            "baseline_avg": baseline_avg,
            "optimized_avg": optimized_avg,
            "avg_diff": optimized_avg - baseline_avg,
            "avg_percent_change": ((optimized_avg - baseline_avg) / baseline_avg * 100) if baseline_avg > 0 else 0.0
        }
        
        return comparison
    
    def format_comparison_table(
        self,
        comparison: Dict,
        show_advanced: Optional[Dict] = None,
        advanced_name: str = "Advanced (HyDE)"
    ) -> str:
        """
        Format comparison as a table similar to the evaluation image format.
        
        Args:
            comparison: Comparison data from compare_configurations
            show_advanced: Optional third configuration to compare
            advanced_name: Name for advanced configuration
        
        Returns:
            Formatted string table
        """
        lines = []
        lines.append("=" * 80)
        lines.append("Metric Comparison Table")
        lines.append("=" * 80)
        
        # Header
        header = f"{'Metric':<25} {comparison['baseline_name']:<20} {comparison['optimized_name']:<20}"
        if show_advanced:
            header += f" {advanced_name:<20}"
        lines.append(header)
        lines.append("-" * 80)
        
        # Metrics
        for metric_data in comparison["metrics"]:
            metric = metric_data["metric"]
            baseline = metric_data["baseline"]
            optimized = metric_data["optimized"]
            
            row = f"{metric:<25} {baseline:<20.4f} {optimized:<20.4f}"
            if show_advanced:
                advanced_score = show_advanced.get("aggregate", {}).get(metric, 0.0)
                row += f" {advanced_score:<20.4f}"
            lines.append(row)
        
        # Average row
        baseline_avg = comparison["summary"]["baseline_avg"]
        optimized_avg = comparison["summary"]["optimized_avg"]
        avg_row = f"{'AVERAGE':<25} {baseline_avg:<20.4f} {optimized_avg:<20.4f}"
        if show_advanced:
            advanced_avg = self.calculate_average(show_advanced)
            avg_row += f" {advanced_avg:<20.4f}"
        lines.append("-" * 80)
        lines.append(avg_row)
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def format_improvements_regressions(self, comparison: Dict) -> str:
        """Format improvements and regressions section."""
        lines = []
        lines.append(f"\n{comparison['optimized_name']} vs {comparison['baseline_name']}:")
        lines.append("")
        
        # Improvements
        if comparison["improvements"]:
            lines.append("Improvements:")
            for metric_data in comparison["improvements"]:
                metric = metric_data["metric"]
                baseline = metric_data["baseline"]
                optimized = metric_data["optimized"]
                diff = metric_data["diff"]
                percent = metric_data["percent_change"]
                lines.append(
                    f"  [+] {metric}: {baseline:.4f} -> {optimized:.4f} "
                    f"(+{diff:.4f}, +{percent:.1f}%)"
                )
        
        # Regressions
        if comparison["regressions"]:
            lines.append("\nRegressions:")
            for metric_data in comparison["regressions"]:
                metric = metric_data["metric"]
                baseline = metric_data["baseline"]
                optimized = metric_data["optimized"]
                diff = metric_data["diff"]
                percent = metric_data["percent_change"]
                lines.append(
                    f"  ⚠ {metric}: {baseline:.4f} → {optimized:.4f} "
                    f"({diff:.4f}, {percent:.1f}%)"
                )
        
        # Summary
        summary = comparison["summary"]
        lines.append(f"\nOverall Average: {summary['baseline_avg']:.4f} -> {summary['optimized_avg']:.4f} "
                    f"({summary['avg_diff']:+.4f}, {summary['avg_percent_change']:+.1f}%)")
        
        return "\n".join(lines)
    
    def generate_full_report(
        self,
        baseline_path: Optional[str],
        optimized_path: str,
        output_path: Optional[str] = None,
        baseline_name: str = "Baseline",
        optimized_name: str = "Optimized (New Default)",
        show_advanced: Optional[str] = None,
        advanced_name: str = "Advanced (HyDE)"
    ) -> str:
        """
        Generate a full comparison report from result files.
        
        Args:
            baseline_path: Path to baseline results JSON (optional, uses optimized as baseline if None)
            optimized_path: Path to optimized results JSON
            output_path: Path to save report (optional)
            baseline_name: Name for baseline configuration
            optimized_name: Name for optimized configuration
            show_advanced: Optional path to advanced configuration results
            advanced_name: Name for advanced configuration
        
        Returns:
            Full report as string
        """
        # Load results
        optimized_results = self.load_results(optimized_path)
        
        if baseline_path and Path(baseline_path).exists():
            baseline_results = self.load_results(baseline_path)
        else:
            # Use optimized as baseline if no baseline provided
            logger.warning("No baseline file provided, using optimized as baseline")
            baseline_results = optimized_results
            baseline_name = "Previous Run"
        
        advanced_results = None
        if show_advanced and Path(show_advanced).exists():
            advanced_results = self.load_results(show_advanced)
        
        # Compare
        comparison = self.compare_configurations(
            baseline_results,
            optimized_results,
            baseline_name=baseline_name,
            optimized_name=optimized_name
        )
        
        # Format report
        report_lines = []
        report_lines.append(self.format_comparison_table(comparison, show_advanced=advanced_results, advanced_name=advanced_name))
        report_lines.append(self.format_improvements_regressions(comparison))
        
        report = "\n".join(report_lines)
        
        # Save if output path provided
        if output_path:
            with open(output_path, 'w') as f:
                f.write(report)
            logger.info(f"Comparison report saved to: {output_path}")
        
        return report
    
    def analyze_similarity_scores(self, results: Dict) -> Dict:
        """
        Analyze similarity scores from evaluation logs.
        This helps understand why scores might be low.
        
        Returns:
            Dict with similarity score analysis
        """
        analysis = {
            "total_queries": results.get("num_queries", 0),
            "metrics_analyzed": [],
            "low_score_queries": []
        }
        
        scores = results.get("scores", {})
        
        for metric in self.metric_names:
            if metric not in scores:
                continue
            
            metric_scores = scores[metric]
            if not metric_scores:
                continue
            
            # Calculate statistics
            non_zero_scores = [s for s in metric_scores if s > 0]
            zero_count = len(metric_scores) - len(non_zero_scores)
            
            analysis["metrics_analyzed"].append({
                "metric": metric,
                "avg": sum(metric_scores) / len(metric_scores),
                "min": min(metric_scores),
                "max": max(metric_scores),
                "zero_count": zero_count,
                "zero_percentage": (zero_count / len(metric_scores) * 100) if metric_scores else 0.0,
                "non_zero_avg": (sum(non_zero_scores) / len(non_zero_scores)) if non_zero_scores else 0.0
            })
            
            # Find queries with zero scores
            for idx, score in enumerate(metric_scores):
                if score == 0.0:
                    if idx not in [q["query_index"] for q in analysis["low_score_queries"]]:
                        analysis["low_score_queries"].append({
                            "query_index": idx,
                            "zero_metrics": [metric]
                        })
                    else:
                        # Add metric to existing entry
                        for q in analysis["low_score_queries"]:
                            if q["query_index"] == idx:
                                q["zero_metrics"].append(metric)
        
        return analysis
