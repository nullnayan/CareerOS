
import urllib.request
import json
from services.ats_scorer import score_resume_baseline

req = urllib.request.Request('http://127.0.0.1:8000/resumes/')
with urllib.request.urlopen(req) as response:
    resumes = json.loads(response.read())

latest = resumes[0] 
resume_id = latest['id']
req2 = urllib.request.Request(f'http://127.0.0.1:8000/resumes/{resume_id}')
with urllib.request.urlopen(req2) as resp2:
    data = json.loads(resp2.read())

result = score_resume_baseline(data['structured_json'], raw_text=latest.get('text', data.get('raw_text', '')))
print('Score:', result['baseline_score'])
print('Issues:')
for issue in result['issues']:
    print('- ' + issue['issue'] + ' (' + str(issue.get('points_deducted', 0)) + ' pts)')

