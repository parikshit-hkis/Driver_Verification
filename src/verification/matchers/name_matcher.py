from rapidfuzz import fuzz
from typing import Tuple, Optional
from src.core.config import settings
from src.schemas.response_schemas import MatchResult
from src.normalization.name_normalizer import (
    clean_and_normalize_name,
    get_name_tokens,
    remove_single_letter_initials
)

class NameMatcher:
    """
    Multi-tiered name matching engine:
    Level 1: Exact Normalized Match
    Level 2: Token-Based Invariant Match
    Level 3: Initials-tolerant Match
    Level 4: RapidFuzz Fuzzy Comparison (>= threshold)
    """
    def __init__(self, threshold: Optional[int] = None):
        self.threshold = threshold or settings.NAME_MATCH_THRESHOLD

    def compare_names(self, name1: Optional[str], name2: Optional[str]) -> MatchResult:
        if not name1 or not name2:
            return MatchResult(match=False, score=0.0, details="One or both names missing")

        clean1 = clean_and_normalize_name(name1)
        clean2 = clean_and_normalize_name(name2)

        if not clean1 or not clean2:
            return MatchResult(match=False, score=0.0, details="Empty name after normalization")

        # Level 1: Exact match
        if clean1 == clean2:
            return MatchResult(match=True, score=100.0, details="Exact normalized match")

        # Level 2: Token-based match (order invariant)
        tokens1 = get_name_tokens(clean1)
        tokens2 = get_name_tokens(clean2)
        if tokens1 == tokens2:
            return MatchResult(match=True, score=100.0, details="Token set match (reordered)")

        # Level 3: Initials-tolerant match (e.g. Parikshit A Panchal vs Parikshit Panchal)
        no_init1 = remove_single_letter_initials(clean1)
        no_init2 = remove_single_letter_initials(clean2)
        if no_init1 == no_init2 and len(no_init1) >= 4:
            return MatchResult(match=True, score=98.0, details="Initials-tolerant match")

        # Level 3.5: Token subset match (e.g. Patil Jeetendra Narayan vs Jitendra Patil)
        # Handles Indian document patterns where middle name or father's name is omitted on Licence
        shorter_tokens = tokens1 if len(tokens1) <= len(tokens2) else tokens2
        longer_tokens = tokens2 if len(tokens1) <= len(tokens2) else tokens1

        if len(shorter_tokens) >= 2 and len(longer_tokens) > len(shorter_tokens):
            match_scores = []
            for s_tok in shorter_tokens:
                best_match = max(fuzz.ratio(s_tok, l_tok) for l_tok in longer_tokens)
                match_scores.append(best_match)

            if all(s >= 80 for s in match_scores):
                avg_score = round(sum(match_scores) / len(match_scores), 1)
                if avg_score >= 85.0:
                    return MatchResult(
                        match=True,
                        score=avg_score,
                        details="Token subset match (middle/father name omitted)"
                    )

        # Level 4: Fuzzy matching using RapidFuzz token_sort_ratio
        score = fuzz.token_sort_ratio(clean1, clean2)
        is_match = score >= self.threshold

        return MatchResult(
            match=is_match,
            score=round(float(score), 1),
            details="Fuzzy match above threshold" if is_match else f"Score {score} below threshold {self.threshold}"
        )

name_matcher = NameMatcher()
