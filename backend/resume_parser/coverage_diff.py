"""
Phase 9 Addition — Coverage Diff & Missed Content Classifier
=============================================================
Calculates the word-level coverage overlap between raw resume text
and the final parsed JSON structure.

If significant unparsed text blocks are found, uses the configured NIM LLM
to classify whether they represent valuable missed candidate information
(e.g., patents, security clearance, military service) or standard noise,
generating warning flags for review without modifying the structured JSON.
"""

import re
import json
import logging
from typing import List, Dict, Set, Tuple, Optional
from agents.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Words/Phrases that represent noise or boilerplate to filter out before LLM call
_BOILERPLATE_PATTERNS = [
    r"^page\s+\d+\s+(?:of|/)\s+\d+$",
    r"^\d+\s*$",
    r"^resume\s*$",
    r"^curriculum\s+vitae\s*$",
    r"^references\s+available\s+upon\s+request$",
    r"^confidential\s*$",
]
_BOILERPLATE_RE = [re.compile(p, re.IGNORECASE) for p in _BOILERPLATE_PATTERNS]


def _extract_all_words(val) -> Set[str]:
    """Helper to recursively extract all lowercase words from parsed JSON structure."""
    words: Set[str] = set()
    if isinstance(val, str):
        # Normalize and split into alphanumeric tokens
        for w in re.split(r"\W+", val.lower()):
            if len(w) > 1:
                words.add(w)
    elif isinstance(val, list):
        for item in val:
            words.update(_extract_all_words(item))
    elif isinstance(val, dict):
        for k, v in val.items():
            # Skip metadata and quality scores
            if k not in ["metadata", "quality", "unknown_sections", "failed_sections", "section_order"]:
                words.update(_extract_all_words(v))
    return words


def _is_boilerplate(line: str) -> bool:
    """Check if a line of text is clear boilerplate or noise."""
    cleaned = line.strip()
    if not cleaned or len(cleaned) < 5:
        return True
    
    # Check regular boilerplate patterns
    for pattern in _BOILERPLATE_RE:
        if pattern.match(cleaned):
            return True
            
    # Check if it looks like standard horizontal dividers
    if re.match(r"^[\s\-_=*•#\+]+$", cleaned):
        return True
        
    return False


def find_unmatched_blocks(raw_text: str, parsed_json: dict) -> List[str]:
    """
    Computes a text subtraction between the raw resume text and parsed fields.
    Groups contiguous unmatched lines into distinct unparsed blocks.
    """
    parsed_words = _extract_all_words(parsed_json)
    if not parsed_words:
        return []

    lines = [line.strip() for line in raw_text.split("\n")]
    unmatched_lines = []
    
    for line in lines:
        if _is_boilerplate(line):
            continue
            
        # Tokenize the line
        line_words = [w for w in re.split(r"\W+", line.lower()) if len(w) > 1]
        if not line_words:
            continue
            
        # Calculate coverage ratio
        matched_count = sum(1 for w in line_words if w in parsed_words)
        coverage_ratio = matched_count / len(line_words)
        
        # If less than 40% of the words on this line are present in the parsed JSON,
        # it is considered unmatched.
        if coverage_ratio < 0.40:
            unmatched_lines.append(line)

    # Group contiguous lines into blocks
    blocks = []
    current_block = []
    
    for line in unmatched_lines:
        if current_block:
            # Check if this line is close to the previous line in original text
            # (We treat everything sequentially in this pass)
            current_block.append(line)
        else:
            current_block = [line]
            
        # Flush block if it is getting large or at end of loop
        if len(current_block) >= 5:
            blocks.append("\n".join(current_block))
            current_block = []
            
    if current_block:
        blocks.append("\n".join(current_block))
        
    return [b for b in blocks if len(b.split()) >= 4]


def classify_unparsed_blocks(blocks: List[str]) -> List[dict]:
    """
    Sends all unparsed blocks to the NIM LLM in a single batch call.
    Classifies blocks into valuable vs. noise categories.
    """
    if not blocks:
        return []
        
    system_prompt = """You are a professional resume auditor.
You are given a list of text blocks extracted from a resume that were NOT successfully captured by our parser rules.
Your job is to identify if any block contains valuable candidate information (such as: patents, military service, publications, speakings, security clearance, major awards, research interests, portfolio highlights, or custom sections not standard in templates) or if it is just noise/boilerplate.

Analyze each text block and return a valid JSON object matching the exact schema:
{
  "unparsed_content": [
    {
      "text": "Verbatim copy of the input text block",
      "is_valuable": true or false,
      "suspected_category": "Name of category e.g., 'Security Clearance', 'Publications', 'Military Service' or null if not valuable",
      "reason": "Brief, clear explanation of why this was missed or why it is important, or null if not valuable"
    }
  ]
}

CRITICAL: Return ONLY valid JSON, nothing else (do not wrap in ```json fences, do not output explanatory text).
"""

    user_prompt = "Verify and classify the following unparsed resume text blocks:\n\n"
    for i, block in enumerate(blocks):
        user_prompt += f"--- Block {i+1} ---\n{block}\n\n"
        
    response = None
    # Try Primary Model (Mistral Small)
    try:
        logger.info("Invoking primary coverage model (mistralai/mistral-small-24b-instruct)...")
        client = LLMClient("coverage_diff")
        response = client.generate(system_prompt, user_prompt, json_mode=True)
    except Exception as primary_err:
        logger.warning(f"Primary model mistral-small failed: {primary_err}. Trying fallback model...")
        
        # Try Fallback Model (DeepSeek Flash)
        try:
            logger.info("Invoking fallback coverage model (deepseek-ai/deepseek-v4-flash)...")
            client = LLMClient("coverage_diff_fallback")
            response = client.generate(system_prompt, user_prompt, json_mode=True)
        except Exception as fallback_err:
            logger.error(f"Fallback model deepseek-flash also failed: {fallback_err}")
            return []
            
    if not response:
        return []

    try:
        # Clean up response in case Nim wraps it in markdown fences
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"^```[a-zA-Z]*\n?", "", response)
            response = re.sub(r"\n?```\s*$", "", response)
            
        # Robustly extract JSON block in case LLM outputs conversational prefix
        first_brace = response.find("{")
        last_brace = response.rfind("}")
        if first_brace != -1 and last_brace != -1:
            response = response[first_brace:last_brace+1]
            
        data = json.loads(response)
        
        # Filter to only valuable blocks for reporting
        valuable_items = []
        for item in data.get("unparsed_content", []):
            if item.get("is_valuable"):
                valuable_items.append({
                    "text": item.get("text", "").strip(),
                    "suspected_category": item.get("suspected_category"),
                    "reason": item.get("reason")
                })
        return valuable_items
        
    except Exception as parse_err:
        logger.warning(f"Failed to parse LLM response JSON: {parse_err}. Raw response: {response[:300]}")
        return []


def audit_coverage(raw_text: str, parsed_json: dict) -> Tuple[List[dict], float]:
    """
    Runs the full coverage audit pipeline:
    1. Finds unmatched text blocks
    2. Runs batch AI classification on them
    3. Calculates an overall text coverage ratio (percentage of words captured)
    """
    # 1. Coverage Ratio Calculation
    raw_words = [w for w in re.split(r"\W+", raw_text.lower()) if len(w) > 1]
    parsed_words = _extract_all_words(parsed_json)
    
    if not raw_words:
        coverage_ratio = 1.0
    else:
        matched_words = sum(1 for w in raw_words if w in parsed_words)
        coverage_ratio = round(matched_words / len(raw_words), 3)

    # 2. Block Classification
    unmatched = find_unmatched_blocks(raw_text, parsed_json)
    missed_info = classify_unparsed_blocks(unmatched) if unmatched else []
    
    return missed_info, coverage_ratio
