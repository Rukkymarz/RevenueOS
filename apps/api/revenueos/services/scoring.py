from dataclasses import dataclass

WEIGHTS = {"seo": 25, "reviews": 20, "website": 25, "social": 10, "market": 20}

@dataclass(frozen=True)
class Score:
    score: int | None
    grade: str
    confidence: int
    explanation: list[str]


def score_lead(metrics: dict[str, int | None]) -> Score:
    """Explainable score across observed, user-supplied 0..100 dimensions.
    Missing data is excluded, never silently treated as poor performance.
    Higher score means healthier online presence, not necessarily stronger sales opportunity.
    """
    known = {k: v for k, v in metrics.items() if k in WEIGHTS and v is not None}
    if not known:
        return Score(None, "Unscored", 0, ["No measured dimensions supplied"])
    if any(type(v) is not int or not 0 <= v <= 100 for v in known.values()):
        raise ValueError("Dimension scores must be integers from 0 to 100")
    total_weight = sum(WEIGHTS[k] for k in known)
    score = round(sum(v * WEIGHTS[k] for k, v in known.items()) / total_weight)
    grade = "Platinum" if score >= 85 else "Gold" if score >= 70 else "Silver" if score >= 50 else "Bronze"
    return Score(score, grade, total_weight, [f"{key}: {val}/100 (weight {WEIGHTS[key]}%)" for key, val in known.items()])


def opportunity_score(metrics: dict[str, int | None]) -> Score:
    """Invert health dimensions only where measurements exist; record confidence separately."""
    return score_lead({key: 100 - val if val is not None else None for key, val in metrics.items()})
