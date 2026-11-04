"""
Readability checker — Flesch Reading Ease and Flesch-Kincaid Grade
Level, implemented from scratch (no dependency needed, though the
`textstat` library does the same thing if you'd rather install it:
`pip install textstat --break-system-packages`).

Resumes should generally land in "fairly easy" to "standard" range.
Overly dense, jargon-packed sentences hurt human review even when
they pass keyword matching.
"""

import re
from typing import Dict


def _count_syllables(word: str) -> int:
    word = word.lower().strip()
    word = re.sub(r"[^a-z]", "", word)
    if not word:
        return 0
    vowels = "aeiouy"
    count = 0
    prev_was_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_was_vowel:
            count += 1
        prev_was_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def flesch_scores(text: str) -> Dict:
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = [w for w in re.findall(r"[A-Za-z']+", text)]

    if not sentences or not words:
        return {"flesch_reading_ease": None, "flesch_kincaid_grade": None, "note": "insufficient text"}

    num_sentences = len(sentences)
    num_words = len(words)
    num_syllables = sum(_count_syllables(w) for w in words)

    words_per_sentence = num_words / num_sentences
    syllables_per_word = num_syllables / num_words

    reading_ease = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
    grade_level = (0.39 * words_per_sentence) + (11.8 * syllables_per_word) - 15.59

    return {
        "flesch_reading_ease": round(reading_ease, 1),
        "flesch_kincaid_grade": round(grade_level, 1),
        "words_per_sentence": round(words_per_sentence, 1),
        "syllables_per_word": round(syllables_per_word, 2),
    }


def check_readability(text: str) -> Dict:
    """
    Returns a 0-1 score for use in the content_quality bucket.
    Target range for technical resumes: reading ease 15-75. Technical resumes
    with domain vocabulary (e.g. 'recursive descent parsing', 'JWT authentication',
    'vulnerabilities', 'microservices') naturally score lower on Flesch-Kincaid.
    Penalizing them for using accurate terminology is unfair. Below 10
    (near-unreadable walls of jargon) or above 80 (likely fragmented bullets) get penalized.
    """
    scores = flesch_scores(text)
    ease = scores.get("flesch_reading_ease")

    if ease is None:
        return {"score": 0.5, "details": scores, "note": "not enough text to score"}

    # Clamp Flesch score to reasonable range
    ease = max(-10, min(120, ease))

    if 10 <= ease <= 80:
        score = 1.0
    elif ease < 10:
        score = max(0.3, 1.0 - (10 - ease) / 20)
    else:
        score = max(0.3, 1.0 - (ease - 80) / 40)

    return {"score": round(score, 3), "details": scores}
