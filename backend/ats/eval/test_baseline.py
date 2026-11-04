import json
import os
import pytest
from pathlib import Path

# Adjust the path to import from the backend directory
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.ats_scorer import score_resume_baseline

def get_corpus_data():
    labels_file = Path(__file__).parent / "corpus" / "labels.jsonl"
    data_dir = Path(__file__).parent / "corpus" / "data"
    
    if not labels_file.exists():
        return []
        
    records = []
    with open(labels_file, "r") as f:
        for line in f:
            if not line.strip():
                continue
            lbl = json.loads(line)
            res_path = data_dir / f"{lbl['resume_id']}.json"
            if res_path.exists():
                with open(res_path, "r") as rf:
                    resume_json = json.load(rf)
                lbl["resume_json"] = resume_json
                records.append(lbl)
    return records

def spearman_rank_correlation(x, y):
    if not x or not y or len(x) != len(y) or len(x) < 2:
        return 0.0
    n = len(x)
    x_ranks = [sorted(x).index(v) for v in x]
    y_ranks = [sorted(y).index(v) for v in y]
    d_sq = sum((x_ranks[i] - y_ranks[i]) ** 2 for i in range(n))
    return 1 - (6 * d_sq) / (n * (n**2 - 1))

@pytest.mark.corpus
def test_baseline_v2():
    records = get_corpus_data()
    assert len(records) > 0, "Corpus data not found. Run generate_corpus.py first."
    
    results_by_band = {}
    all_true = []
    all_pred = []
    
    for record in records:
        band = record["band"]
        true_score = record["ground_truth_score"]
        
        # Run v2 engine
        score_dict = score_resume_baseline(record["resume_json"])
        
        # The v2 engine returns score out of 100 sometimes, but let's check
        pred_score = score_dict.get("baseline_score", 0)
        
        if band not in results_by_band:
            results_by_band[band] = {"true": [], "pred": []}
            
        results_by_band[band]["true"].append(true_score)
        results_by_band[band]["pred"].append(pred_score)
        
        all_true.append(true_score)
        all_pred.append(pred_score)
        
    # Calculate overall metrics
    overall_rho = spearman_rank_correlation(all_true, all_pred)
    overall_mae = sum(abs(t - p) for t, p in zip(all_true, all_pred)) / len(all_true)
    
    # Calculate per band metrics
    band_metrics = {}
    for band, data in results_by_band.items():
        band_rho = spearman_rank_correlation(data["true"], data["pred"])
        band_mae = sum(abs(t - p) for t, p in zip(data["true"], data["pred"])) / len(data["true"])
        band_metrics[band] = {"rho": band_rho, "mae": band_mae}
        
    # Generate report
    report = f"# BASELINE v2 Metrics\n\n"
    report += f"**Overall**\n"
    report += f"- Spearman ρ: {overall_rho:.3f}\n"
    report += f"- MAE: {overall_mae:.1f}\n\n"
    report += f"**Per Band Metrics**\n\n"
    report += f"| Band | Spearman ρ | MAE |\n"
    report += f"|---|---|---|\n"
    for band in ["student", "entry", "mid", "senior", "exec"]:
        metrics = band_metrics.get(band, {"rho": 0, "mae": 0})
        report += f"| {band} | {metrics['rho']:.3f} | {metrics['mae']:.1f} |\n"
        
    with open(Path(__file__).parent / "BASELINE_v2.md", "w", encoding="utf-8") as f:
        f.write(report)
