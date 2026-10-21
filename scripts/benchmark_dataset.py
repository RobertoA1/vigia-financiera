"""Offline benchmark: raw URLs are held in memory, never visited or printed."""
import argparse
import csv
import hashlib
import io
import json
import random
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.detection import evaluate_url

EXPECTED_SHA256 = "0a639fd03aea6308c5b1c10c92aa23c2ce1505447a9137271865cd0badc9a59a"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dataset", required=True, type=Path, help="ZIP UCI PhiUSIIL, nunca se navegarán sus URLs")
parser.add_argument("--per-class", type=int, default=1000)
parser.add_argument("--threshold", type=int, default=50)
parser.add_argument("--output", type=Path, default=Path("docs/evidence/dataset-benchmark.json"))
args = parser.parse_args()
digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
if digest != EXPECTED_SHA256:
    raise SystemExit("El checksum no coincide con la versión investigada. Verifica la fuente antes de actualizarlo.")
rng = random.Random(20261020)
reservoir = {0: [], 1: []}
seen = {0: 0, 1: 0}
with zipfile.ZipFile(args.dataset) as archive:
    with archive.open("PhiUSIIL_Phishing_URL_Dataset.csv") as raw:
        for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig")):
            label = int(row["label"])
            seen[label] += 1
            if len(reservoir[label]) < args.per_class:
                reservoir[label].append(row["URL"])
            else:
                index = rng.randrange(seen[label])
                if index < args.per_class:
                    reservoir[label][index] = row["URL"]
matrix = {"true_positive": 0, "false_positive": 0, "true_negative": 0, "false_negative": 0}
rejected = {"phishing": 0, "legitimate": 0}
latencies = []
for label, urls in reservoir.items():
    for url in urls:
        start = time.perf_counter()
        try:
            result = evaluate_url(url)
        except ValueError:
            rejected["phishing" if label == 0 else "legitimate"] += 1
            continue
        latencies.append((time.perf_counter()-start)*1000)
        malicious = result["score"] >= args.threshold
        matrix[("true_positive" if malicious else "false_negative") if label == 0 else ("false_positive" if malicious else "true_negative")] += 1
tp, fp, tn, fn = [matrix[k] for k in ("true_positive", "false_positive", "true_negative", "false_negative")]
latencies.sort()
report = {"dataset": "PhiUSIIL UCI 967", "source": "https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset", "license": "CC BY 4.0", "sha256": digest, "seed": 20261020, "dataset_labels": {"0": "phishing", "1": "legitimate"}, "population": seen, "sample_per_class": args.per_class, "threshold": args.threshold, "mode": "offline lexical only; no reputation, LLM or webpage fetch", "rejected_out_of_scope": rejected, "confusion_matrix": matrix, "precision": tp/(tp+fp) if tp+fp else 0, "recall": tp/(tp+fn) if tp+fn else 0, "false_positive_rate": fp/(fp+tn) if fp+tn else 0, "false_negative_rate": fn/(fn+tp) if fn+tp else 0, "latency_ms": {"p50": latencies[int(len(latencies)*.5)], "p95": latencies[min(len(latencies)-1,int(len(latencies)*.95))], "p99": latencies[min(len(latencies)-1,int(len(latencies)*.99))]}, "limitations": ["Muestra histórica global; no representativa de bancos peruanos ni amenazas actuales", "No es un modelo entrenado ni un detector general de phishing", "Heurísticas orientadas a suplantación BCP/Interbank/BBVA", "Los rechazos por validación se informan aparte; no se cuentan como detecciones"]}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
