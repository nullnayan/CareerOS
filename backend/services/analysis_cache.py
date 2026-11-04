"""
Simple in-memory cache for Phase 1 JD analysis results.
Key = hash(resume_text + jd_text), Value = analysis result + timestamp.
TTL = 1 hour. Max entries = 100.
"""
import hashlib
import time
from collections import OrderedDict

class AnalysisCache:
    def __init__(self, max_entries=100, ttl_seconds=3600):
        self._cache: OrderedDict = OrderedDict()
        self._max = max_entries
        self._ttl = ttl_seconds
    
    def _key(self, resume_text: str, jd_text: str) -> str:
        combined = ((resume_text or "").strip()[:2000] + "|||" + (jd_text or "").strip()[:2000])
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def get(self, resume_text: str, jd_text: str):
        key = self._key(resume_text, jd_text)
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["ts"] < self._ttl:
                self._cache.move_to_end(key)
                return entry["data"]
            else:
                del self._cache[key]
        return None
    
    def set(self, resume_text: str, jd_text: str, data):
        key = self._key(resume_text, jd_text)
        self._cache[key] = {"data": data, "ts": time.time()}
        self._cache.move_to_end(key)
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)

# Singleton instance
analysis_cache = AnalysisCache()
