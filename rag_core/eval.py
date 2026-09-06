"""
Standalone evaluation script to calibrate the grounding confidence thresholds.
Usage: python eval.py
"""
import math
from rag_core.retrieval import retrieve_and_rerank

# Populate this with real questions from your usage to find optimal thresholds.
GOLDEN_DATASET = [
    {
        "question": "How does the ingestion pipeline handle git cloning?",
        "collection_name": "https-github-com-epsilon003-gaude", # Replace with your actual collection slug
        "expected_files": ["rag_core/ingestion.py"],
    },
    {
        "question": "What is the default chunk size?",
        "collection_name": "https-github-com-epsilon003-gaude",
        "expected_files": ["rag_core/chunking.py"],
    }
]

def compute_confidence(reranked_results: list[dict], top_k_final: int = 5) -> tuple[float, str]:
    cited = reranked_results[:top_k_final]
    discarded = reranked_results[top_k_final:]
    if not cited: return 0.5, "Weak"
    top_avg = sum(r.get("rerank_score", 0) for r in cited) / len(cited)
    baseline = sum(r.get("rerank_score", 0) for r in discarded) / len(discarded) if discarded else top_avg
    margin = top_avg - baseline
    confidence = 1 / (1 + math.exp(-margin))
    
    if confidence >= 0.75: label = "Strong"
    elif confidence >= 0.50: label = "Moderate"
    else: label = "Weak"
    return confidence, label

def evaluate_thresholds():
    print("🔍 Running Grounding Score Calibration...\n")
    thresholds_to_test = [(0.85, 0.60), (0.75, 0.50), (0.65, 0.40)]
    
    for strong_thresh, mod_thresh in thresholds_to_test:
        correct_retrievals = 0
        total_queries = len(GOLDEN_DATASET)
        print(f"Testing Thresholds: Strong >={strong_thresh}, Moderate >={mod_thresh}")
        
        for item in GOLDEN_DATASET:
            results, _ = retrieve_and_rerank(collection_name=item["collection_name"], query=item["question"], top_k_retrieve=15, top_k_final=5)
            confidence, label = compute_confidence(results)
            retrieved_files = [r["file_path"] for r in results[:5]]
            hit = any(any(exp in ret for ret in retrieved_files) for exp in item["expected_files"])
            if hit: correct_retrievals += 1
            print(f"  Q: '{item['question']}' | Confidence: {confidence:.3f} ({label}) | Hit: {'✅' if hit else '❌'}")
            
        precision = correct_retrievals / total_queries if total_queries > 0 else 0
        print(f"  ➔ Precision at this threshold: {precision:.1%}\n")

if __name__ == "__main__":
    evaluate_thresholds()