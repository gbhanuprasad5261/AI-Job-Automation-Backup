import pdfplumber
import re

RESUME_PATH = "resume/resume.pdf"

SKILLS = [
    "java",
    "spring boot",
    "spring",
    "spring mvc",
    "spring data jpa",
    "hibernate",
    "jdbc",
    "mysql",
    "sql",
    "javalin",
    "rest api",
    "restful api",
    "git",
    "github",
    "maven",
    "postman",
    "junit",
    "mockito",
    "docker",
    "aws",
    "microservices",
    "oop",
    "multithreading"
]


def get_resume_text():
    text = ""

    with pdfplumber.open(RESUME_PATH) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text.lower() + "\n"

    return text


def extract_skills(text):
    found = []

    for skill in SKILLS:
        if re.search(r"\b" + re.escape(skill) + r"\b", text):
            found.append(skill)

    return found


resume = get_resume_text()

skills = extract_skills(resume)

print("\n===== YOUR SKILLS =====\n")

for s in skills:
    print("✓", s)

print(f"\nTotal Skills : {len(skills)}")