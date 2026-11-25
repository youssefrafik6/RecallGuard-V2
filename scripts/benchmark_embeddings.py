"""Compare train-only word TF-IDF and a frozen local MiniLM encoder."""

import argparse
import hashlib
import io
import json
import resource
import sys
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss

from recallguard.data import TARGET, feature_frame, load_incidents
from recallguard.evaluation import partitions, score_metrics
from recallguard.training import probability, threshold_for

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def benchmark(data: Path, representation: str, cache: Path) -> dict:
    splits, _ = partitions(
        load_incidents(data, labeled=True), "chronological", 42, True
    )
    train, validation, calibration, test = splits
    started = perf_counter()
    encoder_bytes = 0
    model_sha256 = {}
    if representation == "minilm":
        from fastembed import TextEmbedding

        encoder = TextEmbedding(
            MODEL, cache_dir=str(cache), threads=2, providers=["CPUExecutionProvider"]
        )

        def transform(text):
            return np.asarray(list(encoder.embed(text.tolist(), batch_size=32)))

        for weight in sorted(cache.rglob("*.onnx")):
            if "minilm" in str(weight.parent).lower():
                encoder_bytes += weight.stat().st_size
                with weight.open("rb") as source:
                    model_sha256[weight.name] = hashlib.file_digest(
                        source, "sha256"
                    ).hexdigest()

        serializable_encoder = None
    else:
        words = TfidfVectorizer(ngram_range=(1, 2), max_features=8000)
        words.fit(feature_frame(train).text)
        transform = words.transform
        serializable_encoder = words
    if representation == "minilm" and not model_sha256:
        raise ValueError(
            "MiniLM cache does not expose an identifiable ONNX weight file"
        )
    setup_seconds = perf_counter() - started

    started = perf_counter()
    train_matrix = transform(feature_frame(train).text)
    validation_matrix = transform(feature_frame(validation).text)
    variants = []
    for weight in (None, "balanced"):
        for c in (0.3, 1.0, 3.0):
            classifier = LogisticRegression(
                C=c,
                class_weight=weight,
                max_iter=2000,
                solver="liblinear",
                random_state=42,
            ).fit(train_matrix, train[TARGET])
            raw = classifier.decision_function(validation_matrix)
            variants.append(
                (
                    average_precision_score(validation[TARGET], raw),
                    weight,
                    c,
                    classifier,
                    raw,
                )
            )
    val_ap, weight, c, classifier, val_raw = max(variants, key=lambda item: item[0])

    cal_raw = classifier.decision_function(transform(feature_frame(calibration).text))
    calibrator = LogisticRegression(C=10.0).fit(
        cal_raw.reshape(-1, 1), calibration[TARGET]
    )
    if calibrator.coef_[0, 0] < 0:
        calibrator.fit(np.zeros((len(calibration), 1)), calibration[TARGET])
    threshold = threshold_for(validation[TARGET], probability(calibrator, val_raw))
    development_seconds = perf_counter() - started

    started = perf_counter()
    scores = probability(
        calibrator, classifier.decision_function(transform(feature_frame(test).text))
    )
    inference_ms = (perf_counter() - started) * 1000 / len(test)
    metadata = score_metrics(test[TARGET], scores, threshold)
    with data.open("rb") as source:
        dataset_hash = hashlib.file_digest(source, "sha256").hexdigest()
    bundle = io.BytesIO()
    joblib.dump((serializable_encoder, classifier, calibrator), bundle, compress=3)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "representation": MODEL if representation == "minilm" else "word_tfidf",
        "dataset_sha256": dataset_hash,
        "design": "chronological_campaign_purged",
        "seed": 42,
        "partition_rows": [len(part) for part in splits],
        "test_positive_rate": float(test[TARGET].mean()),
        "hyperparameters": {"C": c, "class_weight": weight},
        "threshold": threshold,
        "validation_average_precision": float(val_ap),
        "setup_seconds": setup_seconds,
        "development_seconds": development_seconds,
        "test_inference_ms_per_row": inference_ms,
        "peak_process_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        "compressed_classifier_bundle_bytes": len(bundle.getbuffer()),
        "encoder_onnx_bytes": encoder_bytes,
        "encoder_sha256": model_sha256,
        "brier": brier_score_loss(test[TARGET], scores),
        "log_loss": log_loss(test[TARGET], scores),
        "test": metadata,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/training_data.csv"))
    parser.add_argument("--cache", type=Path, default=Path("models/fastembed"))
    parser.add_argument("--representation", choices=["word", "minilm"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = benchmark(args.data, args.representation, args.cache)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
