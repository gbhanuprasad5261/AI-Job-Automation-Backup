from skill_matcher import match_resume

job = """
Java
Spring Boot
Hibernate
MySQL
REST API
Git
Docker
AWS
Kafka
JUnit
"""

score, matched, missing = match_resume(job)

print("Score:", score)
print("Matched:", matched)
print("Missing:", missing)