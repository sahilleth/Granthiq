from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
import json
from loguru import logger
import pandas as pd

try:
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logger.warning("Pandas not available. HTML reports will be limited.")

class EvaluationReportGenerator:
    """
    Generates evaluation reports in various formats.
    
    Supports:
    - HTML reports with visualizations
    - JSON reports for programmatic access
    - Text summaries
    """
    
    def __init__(self, results: Dict[str, Any]):
        """
        Initialize report generator.
        
        Args:
            results: Evaluation results dictionary from RAGAS
        """
        self.results = results
    
    def generate_html_report(self, output_path: Optional[str] = None) -> str:
        """
        Generate HTML report with visualizations.
        
        Args:
            output_path: Optional path to save HTML file
            
        Returns:
            HTML string
        """
        html_parts = []
        
        # Header
        html_parts.append("""
<!DOCTYPE html>
<html>
<head>
    <title>RAGAS Evaluation Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .metric {{ margin: 20px 0; padding: 15px; background: #f9f9f9; border-left: 4px solid #4CAF50; }}
        .metric-name {{ font-weight: bold; color: #333; }}
        .metric-value {{ font-size: 24px; color: #4CAF50; margin: 10px 0; }}
        .score-bar {{ height: 30px; background: #e0e0e0; border-radius: 15px; margin: 10px 0; position: relative; }}
        .score-fill {{ height: 100%; background: linear-gradient(90deg, #4CAF50, #8BC34A); border-radius: 15px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #4CAF50; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
        .summary {{ background: #e8f5e9; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .timestamp {{ color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>RAGAS Evaluation Report</h1>
        <div class="timestamp">Generated: {timestamp}</div>
        """.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        # Aggregate scores
        if "aggregate" in self.results:
            html_parts.append("<h2>Aggregate Scores</h2>")
            html_parts.append("<div class='summary'>")
            
            for metric_name, score in self.results["aggregate"].items():
                score_pct = score * 100
                html_parts.append(f"""
                <div class="metric">
                    <div class="metric-name">{metric_name.replace('_', ' ').title()}</div>
                    <div class="metric-value">{score:.3f}</div>
                    <div class="score-bar">
                        <div class="score-fill" style="width: {score_pct}%">{score_pct:.1f}%</div>
                    </div>
                </div>
                """)
            
            html_parts.append("</div>")
        
        # Per-query breakdown
        if "per_query" in self.results and self.results["per_query"]:
            html_parts.append("<h2>Per-Query Breakdown</h2>")
            html_parts.append("<table>")
            
            # Table header
            if PANDAS_AVAILABLE:
                df = pd.DataFrame(self.results["per_query"])
                html_parts.append("<tr>")
                for col in df.columns:
                    html_parts.append(f"<th>{col.replace('_', ' ').title()}</th>")
                html_parts.append("</tr>")
                
                # Table rows
                for _, row in df.iterrows():
                    html_parts.append("<tr>")
                    for col in df.columns:
                        value = row[col]
                        if isinstance(value, float):
                            html_parts.append(f"<td>{value:.3f}</td>")
                        else:
                            html_parts.append(f"<td>{str(value)[:100]}</td>")
                    html_parts.append("</tr>")
            else:
                # Fallback without pandas
                html_parts.append("<tr><th>Question</th><th>Answer</th><th>Contexts</th>")
                for metric_name in self.results.get("aggregate", {}).keys():
                    html_parts.append(f"<th>{metric_name.replace('_', ' ').title()}</th>")
                html_parts.append("</tr>")
                
                for query_result in self.results["per_query"]:
                    html_parts.append("<tr>")
                    html_parts.append(f"<td>{str(query_result.get('question', ''))[:100]}</td>")
                    html_parts.append(f"<td>{str(query_result.get('answer', ''))[:100]}</td>")
                    html_parts.append(f"<td>{query_result.get('contexts_count', 0)}</td>")
                    for metric_name in self.results.get("aggregate", {}).keys():
                        score = query_result.get(metric_name, 0)
                        html_parts.append(f"<td>{score:.3f if isinstance(score, float) else score}</td>")
                    html_parts.append("</tr>")
            
            html_parts.append("</table>")
        
        # Recommendations
        html_parts.append("<h2>Recommendations</h2>")
        html_parts.append("<div class='summary'>")
        recommendations = self._generate_recommendations()
        for rec in recommendations:
            html_parts.append(f"<p>• {rec}</p>")
        html_parts.append("</div>")
        
        # Footer
        html_parts.append("""
    </div>
</body>
</html>
        """)
        
        html_content = "".join(html_parts)
        
        # Save if output path provided
        if output_path:
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path_obj, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            logger.info(f"HTML report saved to {output_path}")
        
        return html_content
    
    def generate_json_report(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate JSON report.
        
        Args:
            output_path: Optional path to save JSON file
            
        Returns:
            JSON dictionary
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "results": self.results,
            "summary": self.generate_summary(),
        }
        
        if output_path:
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path_obj, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"JSON report saved to {output_path}")
        
        return report
    
    def generate_summary(self) -> str:
        """
        Generate text summary of evaluation results.
        
        Returns:
            Summary string
        """
        summary_parts = []
        summary_parts.append("RAGAS Evaluation Summary\n")
        summary_parts.append("=" * 50 + "\n\n")
        
        if "aggregate" in self.results:
            summary_parts.append("Aggregate Scores:\n")
            summary_parts.append("-" * 30 + "\n")
            
            for metric_name, score in self.results["aggregate"].items():
                summary_parts.append(f"{metric_name.replace('_', ' ').title()}: {score:.3f}\n")
            
            summary_parts.append("\n")
        
        if "num_queries" in self.results:
            summary_parts.append(f"Total Queries Evaluated: {self.results['num_queries']}\n\n")
        
        # Recommendations
        summary_parts.append("Recommendations:\n")
        summary_parts.append("-" * 30 + "\n")
        recommendations = self._generate_recommendations()
        for i, rec in enumerate(recommendations, 1):
            summary_parts.append(f"{i}. {rec}\n")
        
        return "".join(summary_parts)
    
    def _generate_recommendations(self) -> List[str]:
        """
        Generate recommendations based on evaluation scores.
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        if "aggregate" not in self.results:
            return ["No aggregate scores available for recommendations."]
        
        aggregate = self.results["aggregate"]
        
        # Faithfulness recommendations
        faithfulness = aggregate.get("faithfulness", 1.0)
        if faithfulness < 0.7:
            recommendations.append(
                "Faithfulness score is low. Consider improving retrieval quality or "
                "ensuring the LLM stays grounded in the provided context."
            )
        
        # Answer relevancy recommendations
        answer_relevancy = aggregate.get("answer_relevancy", 1.0)
        if answer_relevancy < 0.7:
            recommendations.append(
                "Answer relevancy is low. The generated answers may not be directly "
                "addressing the questions. Consider improving prompt engineering."
            )
        
        # Context precision recommendations
        context_precision = aggregate.get("context_precision", 1.0)
        if context_precision < 0.7:
            recommendations.append(
                "Context precision is low. The retrieved contexts may not be highly "
                "relevant. Consider improving retrieval or reranking."
            )
        
        # Context recall recommendations
        context_recall = aggregate.get("context_recall", 1.0)
        if context_recall < 0.7:
            recommendations.append(
                "Context recall is low. Important relevant contexts may be missing. "
                "Consider increasing top_k or improving retrieval strategy."
            )
        
        # Context utilization recommendations
        context_utilization = aggregate.get("context_utilization", 1.0)
        if context_utilization < 0.7:
            recommendations.append(
                "Context utilization is low. The LLM may not be effectively using "
                "the provided contexts. Consider improving prompt templates."
            )
        
        if not recommendations:
            recommendations.append("All metrics are performing well! Keep up the good work.")
        
        return recommendations
    
    def save_report(
        self,
        output_dir: str,
        formats: List[str] = ["html", "json", "txt"],
    ) -> Dict[str, str]:
        """
        Save report in multiple formats.
        
        Args:
            output_dir: Directory to save reports
            formats: List of formats to generate (html, json, txt)
            
        Returns:
            Dictionary mapping format to file path
        """
        output_dir_obj = Path(output_dir)
        output_dir_obj.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_files = {}
        
        if "html" in formats:
            html_path = output_dir_obj / f"evaluation_report_{timestamp}.html"
            self.generate_html_report(str(html_path))
            saved_files["html"] = str(html_path)
        
        if "json" in formats:
            json_path = output_dir_obj / f"evaluation_report_{timestamp}.json"
            self.generate_json_report(str(json_path))
            saved_files["json"] = str(json_path)
        
        if "txt" in formats:
            txt_path = output_dir_obj / f"evaluation_report_{timestamp}.txt"
            summary = self.generate_summary()
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(summary)
            saved_files["txt"] = str(txt_path)
        
        return saved_files

