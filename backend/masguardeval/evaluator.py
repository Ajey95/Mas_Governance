from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgreementResult:
    label_count: int
    observed_agreement: float
    expected_agreement: float
    kappa: float
    confusion_table: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "label_count": self.label_count,
            "observed_agreement": round(self.observed_agreement, 4),
            "expected_agreement": round(self.expected_agreement, 4),
            "kappa": round(self.kappa, 4),
            "confusion_table": self.confusion_table,
        }


class EvaluatorAgreement:
    """Inter-rater agreement utilities for validating human/LLM metric labels."""

    @staticmethod
    def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> AgreementResult:
        if len(labels_a) != len(labels_b):
            raise ValueError("Cohen's Kappa requires equal-length label sequences")
        if not labels_a:
            raise ValueError("Cohen's Kappa requires at least one paired label")

        total = len(labels_a)
        labels = sorted(set(labels_a) | set(labels_b))
        counts_a = Counter(labels_a)
        counts_b = Counter(labels_b)
        observed = sum(1 for left, right in zip(labels_a, labels_b) if left == right) / total
        expected = sum((counts_a[label] / total) * (counts_b[label] / total) for label in labels)
        kappa = 1.0 if expected == 1.0 else (observed - expected) / (1.0 - expected)

        table: dict[str, dict[str, int]] = {label: {inner: 0 for inner in labels} for label in labels}
        for left, right in zip(labels_a, labels_b):
            table[left][right] += 1

        return AgreementResult(
            label_count=total,
            observed_agreement=observed,
            expected_agreement=expected,
            kappa=kappa,
            confusion_table=table,
        )

