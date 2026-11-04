"""Constrained, append-only editing of category values in a Skills section."""
import hashlib
import re


def digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def group_end(source: str, start: int) -> int:
    if start >= len(source) or source[start] != "{":
        raise ValueError("Expected a braced category value.")
    depth = 0
    comment = False
    for index in range(start, len(source)):
        char = source[index]
        # An odd number of immediately preceding backslashes escapes braces.
        slashes = len(source[:index]) - len(source[:index].rstrip("\\"))
        if char in "\r\n": comment = False
        if comment: continue
        if char == "%" and not slashes % 2:
            comment = True
            continue
        if slashes % 2:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("Unbalanced LaTeX braces.")


def uncomment(source: str) -> str:
    return re.sub(r"(?<!\\)%[^\r\n]*", "", source)


def skill_section(source: str) -> tuple:
    # Ignore comment lines when locating section commands without changing offsets.
    masked = re.sub(r"(?<!\\)%[^\r\n]*", lambda m: " " * len(m[0]), source)
    sections = list(re.finditer(r"\\(?:section|cvsection|sectiontitle|resumesection)\*?\s*\{([^{}]+)\}", masked))
    headings = {"skills", "technical skills", "technical expertise", "technical proficiencies", "technologies", "core competencies", "programming skills", "skills & tools"}
    skills = [i for i, m in enumerate(sections) if re.sub(r"\\([&])", r"\1", m[1]).strip().lower() in headings]
    if len(skills) != 1:
        raise ValueError("Identify one Skills heading using \\section{Skills}, \\cvsection{Skills}, or \\sectiontitle{Skills} before mapping editable values.")
    i = skills[0]
    start = sections[i].end()
    end = sections[i + 1].start() if i + 1 < len(sections) else masked.find(r"\end{document}", start)
    if end < start:
        raise ValueError("Cannot find the end of the Skills section.")
    return start, end, sections[i][1], sections[i + 1][1] if i + 1 < len(sections) else None, masked


def category_regions(source: str) -> dict:
    markers = list(re.finditer(r"(?m)^[ \t]*%\s*CAREEROS_SKILL_(START\s*:\s*([^\r\n]+)|END)\s*\r?$", source))
    try:
        start, end, _, _, masked = skill_section(source)
    except ValueError:
        if not markers: raise
        # Explicit user mappings also work with custom heading commands. Only
        # body values are editable; the preamble and document structure stay fixed.
        masked = re.sub(r"(?<!\\)%[^\r\n]*", lambda m: " " * len(m[0]), source)
        begin = re.search(r"\\begin\s*\{document\}", masked)
        end = masked.find(r"\end{document}")
        if not begin or end < begin.end(): raise ValueError("Place explicit Skills markers inside the document body.")
        start = begin.end()
    categories = {}
    def add(name, left, right):
        name = re.sub(r"\\([&%#$])", r"\1", name.strip()).rstrip(":").strip()
        if not name or len(name) > 100 or name in categories:
            raise ValueError(f"Ambiguous or invalid Skills category: {name}.")
        value = source[left:right]
        if left < start or right > end or re.search(r"\\(?:section|cvsection|begin|end|input|include|newcommand)\b", uncomment(value)):
            raise ValueError(f"Mark only the skill value for {name}, without sections or environments.")
        enclosed = "{" + value + "}"
        if group_end(enclosed, 0) != len(enclosed) - 1:
            raise ValueError(f"Keep the command's braces outside the mapped value for {name}.")
        categories[name] = {"start": left, "end": right, "value": value}
    # Explicit mappings support templates using unfamiliar presentation commands.
    if markers:
        opened = None
        for marker in markers:
            if marker[1].startswith("START"):
                if opened: raise ValueError("Skills mapping markers cannot overlap.")
                opened = marker
            else:
                if not opened: raise ValueError("Skills mapping end has no start marker.")
                left = opened.end()
                if source[left:left + 2] == "\r\n": left += 2
                elif source[left:left + 1] == "\n": left += 1
                add(opened[2], left, marker.start())
                opened = None
        if opened: raise ValueError("Skills mapping start has no end marker.")
        return categories
    pattern = re.compile(r"\\textbf\s*\{([^{}]+)\}\s*(\{)")
    for match in pattern.finditer(masked, start, end):
        name = re.sub(r"\\([&%#$])", r"\1", match[1].strip())
        value_start = match.start(2)
        value_end = group_end(source, value_start)
        value = source[value_start + 1:value_end]
        add(name, value_start + 1, value_end)
    for match in re.finditer(r"\\(?:cvskill|skill|skillrow|skillitem|resumeSkill)\s*\{([^{}]+)\}\s*(\{)", masked[start:end]):
        left = start + match.start(2)
        add(match[1], left + 1, group_end(source, left))
    # Common unbraced form: \textbf{Languages:} Python, SQL \\
    for match in re.finditer(r"\\textbf\s*\{([^{}]+:)\}[ \t]*|\\textbf\s*\{([^{}]+)\}[ \t]*:[ \t]*", masked[start:end]):
        left = start + match.end()
        if masked[left:left + 1] == "{": continue
        stop = re.search(r"\\\\|\\(?:item|end)\b|\\textbf\s*\{|\n\s*\n", masked[left:end])
        right = left + stop.start() if stop else end
        add(match[1] or match[2], left, right)
    if not categories:
        raise ValueError("Skills values need mapping. Use a recognized category command or CAREEROS_SKILL_START/END comments around each editable value.")
    ordered = sorted(categories.values(), key=lambda r: r["start"])
    if any(a["end"] > b["start"] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Skills mappings overlap; mark each value separately.")
    return categories


def plain_text(source: str) -> str:
    body = source.split(r"\begin{document}", 1)[-1]
    body = uncomment(body)
    body = re.sub(r"\\[a-zA-Z]+\*?", " ", body)
    body = re.sub(r"\\([^a-zA-Z])", r"\1", body)
    return re.sub(r"\s+", " ", body.replace("{", " ").replace("}", " "))


def escape_latex(value: str) -> str:
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
                    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(c, c) for c in value)


def patch(source: str, additions: list[dict]) -> tuple[str, list[dict]]:
    if len(additions) > 5:
        raise ValueError("At most five skill additions are allowed.")
    regions = category_regions(source)
    grouped: dict[str, list[str]] = {}
    seen = set()
    from tailoring.selection import canonical, contains
    for item in additions:
        name, category = item["name"].strip(), item["category"]
        key = canonical(name)
        if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise ValueError("Invalid skill name.")
        if category not in regions:
            raise ValueError("Unknown Skills category.")
        if key in seen or contains(plain_text(source), name):
            raise ValueError(f"Skill already present or duplicated: {name}")
        seen.add(key)
        grouped.setdefault(category, []).append(name)
    result = source
    changes = []
    for category in sorted(grouped, key=lambda c: regions[c]["start"], reverse=True):
        region = regions[category]
        value = region["value"]
        suffix = value[len(value.rstrip()):]
        separator = ", " if plain_text(value).strip().strip(":").strip() else " " if value.rstrip().endswith(":") else ""
        updated = value.rstrip() + separator + ", ".join(escape_latex(s) for s in grouped[category]) + suffix
        result = result[:region["start"]] + updated + result[region["end"]:]
        changes.append({"category": category, "before": value, "after": updated, "added": grouped[category]})
    # Strong invariant: reconstruction of all protected pieces stays identical.
    new_regions = category_regions(result)
    def protected(text, mapping):
        parts, cursor = [], 0
        for region in sorted(mapping.values(), key=lambda r: r["start"]):
            parts.append(text[cursor:region["start"]])
            cursor = region["end"]
        return parts + [text[cursor:]]
    if protected(source, regions) != protected(result, new_regions):
        raise ValueError("Protected source changed; patch rejected.")
    return result, list(reversed(changes))
