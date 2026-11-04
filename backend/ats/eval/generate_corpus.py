import json
import os
import random
from pathlib import Path

BANDS = ["student", "entry", "mid", "senior", "exec"]
DOMAINS = ["software", "data", "professional", "trades"]

def generate_resume(band, domain, quality):
    # Base structure
    resume = {
        "contact": {
            "name": f"Test {band.capitalize()} {domain.capitalize()}",
            "email": f"test.{band}.{domain}@example.com",
            "phone": "+1-555-0100",
            "location": "New York, NY",
            "links": ["https://linkedin.com/in/test"] if quality > 0.3 else []
        },
        "summary": "",
        "experience": [],
        "education": [],
        "skills": [],
        "projects": [],
        "certifications": [],
        "formatting_metadata": {
            "has_columns": False,
            "has_tables": False,
            "is_scanned_pdf": False
        }
    }
    
    num_roles = {"student": 0, "entry": 1, "mid": 2, "senior": 3, "exec": 4}[band]
    
    # Generate experience
    for i in range(num_roles):
        bullets = []
        num_bullets = random.randint(2, 5)
        for b in range(num_bullets):
            # Quality determines chance of action verbs and metrics
            text = "Worked on tasks."
            if random.random() < quality:
                verb = random.choice(["Engineered", "Optimized", "Designed", "Led", "Developed"])
                metric = random.choice(["by 20%", "$1M", "for 50,000 users", "3x", ""])
                text = f"{verb} system {metric}".strip()
            bullets.append(text)
            
        resume["experience"].append({
            "company": f"Company {i+1}",
            "title": f"{band.capitalize()} Role",
            "startDate": f"202{i}-01",
            "endDate": f"202{i+1}-01" if i > 0 else "Present",
            "bullets": bullets
        })
        
    # Generate skills based on domain and quality
    if quality > 0.2:
        if domain == "software":
            resume["skills"] = ["Python", "JavaScript", "React", "Docker", "AWS", "Git"]
        elif domain == "data":
            resume["skills"] = ["SQL", "Python", "Tableau", "Pandas", "Machine Learning"]
        elif domain == "professional":
            resume["skills"] = ["Project Management", "Excel", "Communication", "Leadership"]
        else:
            resume["skills"] = ["Safety", "Customer Service", "Scheduling"]
            
    # Add education
    resume["education"].append({
        "institution": "University of Technology",
        "degree": "Bachelor of Science",
        "field": domain.capitalize(),
        "endYear": "2020",
        "gpa": {"raw": "3.8"} if band == "student" else {}
    })
    
    return resume

def main():
    out_dir = Path(__file__).parent / "corpus" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    labels_file = Path(__file__).parent / "corpus" / "labels.jsonl"
    labels = []
    
    idx = 1
    for band in BANDS:
        for domain in DOMAINS:
            # Generate 6 resumes per combo, scaling quality from 0.2 to 1.0
            for q_idx in range(6):
                quality = 0.2 + (q_idx * (0.8 / 5))
                resume = generate_resume(band, domain, quality)
                
                # Special adversarial cases injection
                is_adversarial = False
                if band == "senior" and q_idx == 0:
                    resume["formatting_metadata"]["is_scanned_pdf"] = True # Scanned PDF
                    is_adversarial = True
                
                resume_id = f"res_{idx:03d}_{band}_{domain}"
                
                with open(out_dir / f"{resume_id}.json", "w") as f:
                    json.dump(resume, f, indent=2)
                    
                # Ground truth score depends on quality, but we systematically drop student scores in baseline
                true_score = int(quality * 100)
                if is_adversarial:
                    true_score = max(0, true_score - 40)
                    
                labels.append({
                    "resume_id": resume_id,
                    "band": band,
                    "domain": domain,
                    "ground_truth_score": true_score
                })
                idx += 1
                
    with open(labels_file, "w") as f:
        for lbl in labels:
            f.write(json.dumps(lbl) + "\n")

    print(f"Generated {idx-1} synthetic resumes and labels.")

if __name__ == "__main__":
    main()
