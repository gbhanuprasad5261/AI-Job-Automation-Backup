import csv
import os
from collections import Counter
from skill_matcher import match_resume

try:
    from config import MIN_MATCH_SCORE, TARGET_LOCATIONS, EASY_APPLY_FILTER
except ImportError:
    MIN_MATCH_SCORE = 70
    TARGET_LOCATIONS = ('bengaluru','bangalore','hyderabad','chennai','remote')
    EASY_APPLY_FILTER = True

INPUT_FILE='data/job_details.csv'
OUTPUT_FILE='data/job_analysis.csv'
TOP_JOBS=10

def location_allowed(location):
    text=(location or '').strip().lower()
    return bool(text) and any(target in text for target in TARGET_LOCATIONS)

def analyze_jobs():
    if not os.path.exists(INPUT_FILE):
        print('job_details.csv not found.'); return
    jobs=[]
    with open(INPUT_FILE,'r',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            score, matched, missing = match_resume(row.get('Description',''))
            priority='HIGH' if score>=80 else ('MEDIUM' if score>=70 else 'LOW')
            jobs.append({'Title':row.get('Title',''),'Company':row.get('Company',''),'Location':row.get('Location',''),'Easy Apply':row.get('Easy Apply',''),'Match Score':f'{score}%','Priority':priority,'Matched Skills':', '.join(sorted(matched)),'Missing Skills':', '.join(sorted(missing)),'Link':row.get('Link','')})
    os.makedirs(os.path.dirname(OUTPUT_FILE),exist_ok=True)
    fields=['Title','Company','Location','Easy Apply','Match Score','Priority','Matched Skills','Missing Skills','Link']
    with open(OUTPUT_FILE,'w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(jobs)
    recommended=[]
    for job in jobs:
        score=int(job['Match Score'].replace('%',''))
        if score < MIN_MATCH_SCORE or not location_allowed(job['Location']): continue
        if EASY_APPLY_FILTER and job['Easy Apply'].strip().lower()!='yes': continue
        recommended.append(job)
    recommended.sort(key=lambda x:int(x['Match Score'].replace('%','')),reverse=True)
    print('\n'+'='*60); print('AI JOB ANALYSIS COMPLETED'); print('='*60)
    print(f'Jobs analyzed : {len(jobs)}'); print(f'Saved file    : {OUTPUT_FILE}')
    print('\n'+'='*60); print('TOP JOB RECOMMENDATIONS'); print('='*60)
    if recommended:
        for i,job in enumerate(recommended[:TOP_JOBS],1):
            print(f"\n{i}. {job['Title']}\n   Company : {job['Company']}\n   Location: {job['Location']}\n   Score   : {job['Match Score']}\n   Priority: {job['Priority']}\n   Easy Apply: {job['Easy Apply'] or 'Unknown'}\n   Missing : {job['Missing Skills'] or 'None'}")
    else:
        print(f"\nNo jobs currently meet the {MIN_MATCH_SCORE}% score and configured Easy Apply/location filters.")
    print('\n'+'='*60); print('RECOMMENDATION SUMMARY'); print('='*60)
    print(f'Minimum Match Score : {MIN_MATCH_SCORE}%'); print(f'Easy Apply Filter   : {EASY_APPLY_FILTER}'); print(f'Recommended Jobs     : {len(recommended)}')
    counter=Counter()
    for job in jobs:
        counter.update(s.strip() for s in job['Missing Skills'].split(',') if s.strip())
    print('\n'+'='*60); print('SKILL GAP ANALYSIS'); print('='*60)
    if counter:
        print('\nSkills to improve based on collected jobs:\n')
        for rank,(skill,count) in enumerate(counter.most_common(10),1): print(f'{rank}. {skill} -> {count} job(s)')
        print('\nRecommended Focus:'); print(', '.join(s for s,_ in counter.most_common(5)))
    else: print('\nNo missing skills identified.')

if __name__=='__main__': analyze_jobs()
