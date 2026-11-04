import yaml
from pathlib import Path
from typing import Optional, List

ONTOLOGY_DIR = Path(__file__).parent

class SkillOntology:
    def __init__(self):
        self.skills = []
        self._id_map = {}
        self._alias_map = {}
        self._load()

    def _load(self):
        skills_path = ONTOLOGY_DIR / "skills.yaml"
        if not skills_path.exists():
            return
            
        with open(skills_path, "r", encoding="utf-8") as f:
            self.skills = yaml.safe_load(f) or []
            
        for skill in self.skills:
            skill_id = skill["id"]
            self._id_map[skill_id] = skill
            
            # Map canonical name
            self._alias_map[skill["canonical"].lower()] = skill_id
            
            # Map aliases
            for alias in skill.get("aliases", []):
                self._alias_map[alias.lower()] = skill_id

    def canonicalize(self, term: str) -> Optional[str]:
        term = term.lower().strip()
        return self._alias_map.get(term)

    def aliases_of(self, skill_id: str) -> List[str]:
        skill = self._id_map.get(skill_id)
        if not skill:
            return []
        aliases = [skill["canonical"]] + skill.get("aliases", [])
        return list(dict.fromkeys(aliases))

    def kind_of(self, skill_id: str) -> Optional[str]:
        skill = self._id_map.get(skill_id)
        if not skill:
            return None
        return skill.get("kind")
