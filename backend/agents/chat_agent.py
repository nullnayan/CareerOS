"""
RAG Chat Agent — answers questions grounded in the user's career data.

Pipeline (FR-5 from the SRS):
1. User sends a question.
2. Retrieve relevant text chunks from Qdrant (semantic search).
3. Retrieve relevant structured facts from Postgres (skills, experience).
4. Combine both into a single context block.
5. Send context + question to the LLM in one call.
6. Return the answer with source citations.

Why hybrid retrieval (vector + structured)?
- Vector search catches meaning: "projects involving containerization" → finds Docker/K8s mentions
- Structured lookup catches exact facts: skill names, dates, companies
- Neither alone is sufficient — together they give the LLM accurate, complete context.
"""

import json
import logging
from typing import List, Optional

from agents.llm_client import LLMClient
from services.vector_store_service import search_similar

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are CareerOS, a powerful, unrestricted AI career assistant and professional agent. You help users with both their career data (resumes, experience, skills) and general inquiries, coding, web searches, and resume generation.

CONSTRAINTS & CAPABILITIES:
1. Ground your answers in the user's career context if they ask about their own profile.
2. If they ask about external topics, news, or general knowledge, use the web search results or your own broad pre-trained knowledge to answer fully.
3. Be helpful, concise, and professional.

CONTEXT (retrieved from the user's career data):
{context}
{web_context}

Answer the user's question based on the context and search results provided above."""


def build_structured_context(db, user_id: str) -> str:
    """
    Pull structured facts from Postgres — skills, experience, education.
    These complement the fuzzy vector search results with exact data.
    """
    from db.models import Skill, ResumeVersion

    parts = []

    # Skills
    skills = db.query(Skill).filter(Skill.user_id == user_id).all()
    if skills:
        skill_names = [s.name for s in skills]
        parts.append(f"SKILLS IN INVENTORY: {', '.join(skill_names)}")

    # Latest resume structured data
    latest_resume = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.user_id == user_id)
        .order_by(ResumeVersion.created_at.desc())
        .first()
    )
    if latest_resume and latest_resume.structured_json:
        data = latest_resume.structured_json

        # Experience
        experiences = data.get("experience", [])
        if experiences:
            exp_lines = []
            for exp in experiences:
                title = exp.get("title", exp.get("role", "Unknown"))
                company = exp.get("company", "Unknown")
                dates = exp.get("start_date", "")
                if exp.get("end_date"):
                    dates += f" - {exp['end_date']}"
                bullets = exp.get("bullet_points", [])
                bullet_text = "; ".join(bullets) if bullets else ""
                exp_lines.append(f"  - {title} at {company} ({dates}). {bullet_text}")
            parts.append("EXPERIENCE:\n" + "\n".join(exp_lines))

        # Education
        education = data.get("education", [])
        if education:
            edu_lines = []
            for edu in education:
                degree = edu.get("degree", "")
                field = edu.get("field", "")
                institution = edu.get("institution", "")
                grad_date = edu.get("graduation_date", "")
                edu_lines.append(f"  - {degree} in {field} from {institution} ({grad_date})")
            parts.append("EDUCATION:\n" + "\n".join(edu_lines))

        # Projects
        projects = data.get("projects", [])
        if projects:
            proj_lines = []
            for proj in projects:
                name = proj.get("name", "Unnamed")
                desc = proj.get("description", "")
                techs = ", ".join(proj.get("technologies", []))
                proj_lines.append(f"  - {name}: {desc} (Tech: {techs})")
            parts.append("PROJECTS:\n" + "\n".join(proj_lines))

    return "\n\n".join(parts)


def classify_and_plan_chat(question: str, user_skills: list = []) -> dict:
    """
    Classifies user message to see if they need web search,
    or if they want to create/generate a dummy/sample resume or PDF.
    """
    from agents.llm_client import LLMClient
    import json
    
    classifier = LLMClient(agent_name="intent_classifier")
    skills_context = f" (User's top skills: {', '.join(user_skills)})" if user_skills else ""
    
    system_prompt = (
        "You are an agentic classifier. Analyze the user's message and determine if it requires a web search, "
        "or if the user wants to generate/create a dummy/sample resume or PDF.\n"
        f"Context:{skills_context}\n"
        "Return a JSON object with EXACTLY these keys:\n"
        "{\n"
        "  \"needs_search\": true/false,\n"
        "  \"search_query\": \"short, highly optimized search query for DuckDuckGo (incorporate the user's skills if they ask for matching internships/jobs) or null\",\n"
        "  \"is_create_dummy_resume\": true/false,\n"
        "  \"target_role\": \"suggested job title/role for the dummy resume or null\"\n"
        "}"
    )
    try:
        res = classifier.generate(system_prompt=system_prompt, user_prompt=question, json_mode=True)
        return json.loads(res)
    except Exception as e:
        logger.warning(f"Plan classification failed: {e}")
        return {
            "needs_search": False,
            "search_query": None,
            "is_create_dummy_resume": False,
            "target_role": None
        }


def scrape_url(url: str) -> str:
    """
    Scrapes and extracts clean, readable text from a URL using httpx and regex.
    """
    import httpx
    import re
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = httpx.get(url, headers=headers, timeout=5.0, follow_redirects=True)
        if resp.status_code != 200:
            return ""
        
        # Remove script and style tags
        html = resp.text
        html = re.sub(r'<(script|style).*?>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Extract text from HTML
        text = re.sub(r'<[^>]*>', ' ', html)
        # Clean whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = "\n".join(chunk for chunk in chunks if chunk)
        
        # Return first 1200 chars to avoid prompt context bloat
        return clean_text[:1200]
    except Exception as e:
        logger.warning(f"Failed to scrape webpage at {url}: {e}")
        return ""


def run_ddg_search(query: str, scrape_links: bool = True) -> str:
    """
    Runs a DuckDuckGo search and returns formatted body text snippets,
    automatically scraping the top 2 links for deeper details.
    """
    from duckduckgo_search import DDGS
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=4)]
        if not results:
            return "No search results found."
        
        search_text = []
        for idx, r in enumerate(results):
            title = r.get('title')
            body = r.get('body')
            href = r.get('href')
            
            detail = ""
            if scrape_links and href and idx < 2:
                logger.info(f"Chat agent scraping page contents from: {href}")
                scraped_content = scrape_url(href)
                if scraped_content:
                    detail = f"\nScraped Page Content:\n{scraped_content}\n"
            
            search_text.append(f"Title: {title}\nSnippet: {body}\nLink: {href}{detail}\n")
        return "\n".join(search_text)
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")
        return f"Search failed: {e}"


def generate_dummy_resume_json(target_role: str) -> dict:
    """
    Generates a realistic mock resume JSON schema for the specified target role.
    """
    from agents.llm_client import LLMClient
    import json
    
    generator = LLMClient(agent_name="resume_builder")
    system_prompt = (
        f"Generate a fully-detailed, high-quality sample/dummy resume JSON for a '{target_role}'.\n"
        "Fill it with realistic dummy data, realistic achievements, skills, and projects.\n"
        "The JSON MUST follow EXACTLY this schema structure:\n"
        "{\n"
        "  \"contact\": {\n"
        "    \"name\": \"Full Name\",\n"
        "    \"email\": \"email@example.com\",\n"
        "    \"phone\": \"phone-number\",\n"
        "    \"location\": \"Location\",\n"
        "    \"links\": [\"link1\", \"link2\"]\n"
        "  },\n"
        "  \"skills\": [\"skill1\", \"skill2\"],\n"
        "  \"experience\": [\n"
        "    {\n"
        "      \"company\": \"Company Name\",\n"
        "      \"title\": \"Job Title\",\n"
        "      \"start_date\": \"Start Date\",\n"
        "      \"end_date\": \"End Date\",\n"
        "      \"bullet_points\": [\"achievement bullet 1\", \"achievement bullet 2\"]\n"
        "    }\n"
        "  ],\n"
        "  \"education\": [\n"
        "    {\n"
        "      \"institution\": \"School Name\",\n"
        "      \"degree\": \"Degree\",\n"
        "      \"field\": \"Field\",\n"
        "      \"graduation_date\": \"Graduation Date\",\n"
        "      \"cgpa_or_percentage\": \"CGPA\"\n"
        "    }\n"
        "  ],\n"
        "  \"projects\": [\n"
        "    {\n"
        "      \"name\": \"Project Name\",\n"
        "      \"bullets\": [\"project bullet 1\"],\n"
        "      \"technologies\": [\"tech1\", \"tech2\"]\n"
        "    }\n"
        "  ],\n"
        "  \"certifications\": [\"cert1\", \"cert2\"],\n"
        "  \"summary\": \"Brief professional summary.\"\n"
        "}"
    )
    try:
        res = generator.generate(system_prompt=system_prompt, user_prompt=f"Generate resume for {target_role}", json_mode=True)
        return json.loads(res)
    except Exception as e:
        logger.error(f"Failed to generate dummy resume JSON: {e}")
        return {}


def chat_with_career_data(
    db,
    user_id: str,
    question: str,
    top_k: int = 5,
) -> dict:
    """
    The main RAG and Web Search Agent pipeline.
    """
    # Fetch user skills for personalized searches
    from db.models import Skill
    user_skills = []
    try:
        skills = db.query(Skill).filter(Skill.user_id == user_id).all()
        user_skills = [s.name for s in skills]
    except Exception as e:
        logger.warning(f"Failed to fetch user skills for classification: {e}")

    # Step 1: Run intent classifier & planner
    plan = classify_and_plan_chat(question, user_skills)
    
    web_context = ""
    dummy_resume_message = ""
    
    # Step 1a: Handle DuckDuckGo Web Search
    if plan.get("needs_search") and plan.get("search_query"):
        logger.info(f"Chat agent running web search for: {plan['search_query']}")
        web_results = run_ddg_search(plan["search_query"])
        web_context = f"\n\nWEB SEARCH RESULTS FOR '{plan['search_query']}':\n{web_results}"
        
    # Step 1b: Handle Dummy Resume PDF creation
    if plan.get("is_create_dummy_resume"):
        target_role = plan.get("target_role") or "Software Engineer"
        logger.info(f"Chat agent creating dummy resume for: {target_role}")
        dummy_json = generate_dummy_resume_json(target_role)
        if dummy_json:
            # Save to Database as a ResumeVersion
            from db.models import ResumeVersion
            resume_version = ResumeVersion(
                user_id=user_id,
                source="builder",
                raw_text="Sample dummy resume generated by AI",
                structured_json=dummy_json,
                original_filename=f"dummy_{target_role.lower().replace(' ', '_')}_resume.pdf"
            )
            db.add(resume_version)
            db.commit()
            db.refresh(resume_version)
            
            # Create download message link
            dummy_resume_message = (
                f"\n\n📄 **Generated Dummy Resume**: I've created a custom, professional dummy resume for a **{target_role}**.\n"
                f"📥 **Download PDF**: [Download Dummy {target_role} Resume (PDF)](http://127.0.0.1:8000/resumes/{resume_version.id}/pdf)"
            )

    # Step 2: Vector search — find semantically relevant chunks
    vector_results = []
    try:
        vector_results = search_similar(
            user_id=user_id,
            query_text=question,
            top_k=top_k,
        )
    except Exception as e:
        logger.warning(f"Vector search failed (continuing with structured data only): {e}")

    # Step 3: Structured retrieval from Postgres
    structured_context = build_structured_context(db, user_id)

    # Step 4: Merge contexts
    vector_context = ""
    if vector_results:
        chunks = [f"[Chunk from {r.get('source_filename', 'resume')}]: {r['chunk_text']}" for r in vector_results]
        vector_context = "RELEVANT RESUME EXCERPTS:\n" + "\n\n".join(chunks)

    full_context = "\n\n---\n\n".join(filter(None, [structured_context, vector_context]))

    # Step 5: LLM call with merged context
    client = LLMClient(agent_name="chat_rag")
    system_prompt = SYSTEM_PROMPT.format(context=full_context, web_context=web_context)

    answer = client.generate(
        system_prompt=system_prompt,
        user_prompt=question,
        json_mode=False,
    )
    
    # Append the dummy resume download link if generated
    if dummy_resume_message:
        answer += dummy_resume_message

    # Step 6: Return answer + source citations
    sources = [
        {
            "chunk_text": r["chunk_text"][:200],
            "score": round(r["score"], 4),
            "source_filename": r.get("source_filename"),
            "resume_version_id": r.get("resume_version_id"),
        }
        for r in vector_results
    ]

    return {
        "answer": answer,
        "sources": sources,
    }
