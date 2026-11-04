
import json
from services.ats_scorer import score_resume_baseline

with open('latest_resume_json2.txt', 'r', encoding='utf-8') as f:
    data = json.load(f)

result = score_resume_baseline(data, raw_text='')
print('Score:', result['baseline_score'])
print('Issues:')
for issue in result['issues']:
    print('- ' + issue['issue'] + ' (' + str(issue.get('points_deducted', 0)) + ' pts)')

