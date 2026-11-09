from sqlalchemy import select
from services.api.models import Attempt
from services.api.services.learning import LESSONS

def solve(client,lesson='first-hello',wrong=False):
    attempt=client.post('/api/lessons/'+lesson+'/start').json()
    for i,exercise in enumerate(LESSONS[lesson]['exercises']):
        answer='wrong' if wrong else exercise['answers'][0]
        response=client.post(f'/api/attempts/{attempt["id"]}/answer',json={'index':i,'value':answer})
        assert response.status_code==200,response.text
    return attempt

def test_end_to_end_free_lesson_and_paywall(member):
    path=member.get('/api/learning-path').json()
    assert path[0]['id']=='first-hello' and not path[0]['locked']
    assert all(p['locked'] for p in path[1:])
    a=solve(member)
    result=member.post(f'/api/attempts/{a["id"]}/complete').json()
    assert result['score']==100 and result['xp_awarded']==50
    profile=member.get('/api/users/me').json()
    assert profile['xp']==50 and profile['coins']>=10
    assert profile['progress']['completed_lessons']==1
    assert profile['progress']['achievements'][0]['id']=='first-step'
    assert member.post('/api/lessons/cafe/start').status_code==402

def test_incomplete_cannot_complete(member):
    a=member.post('/api/lessons/first-hello/start').json()
    assert member.post(f'/api/attempts/{a["id"]}/complete').status_code==409

def test_answers_not_leaked(member):
    a=member.post('/api/lessons/first-hello/start').json()
    assert 'answers' not in a['exercise'] and 'explanation' not in a['exercise']

def test_answer_idempotency_and_conflict(member):
    a=member.post('/api/lessons/first-hello/start').json()
    route=f'/api/attempts/{a["id"]}/answer'
    payload={'index':0,'value':'Hello'}
    first=member.post(route,json=payload).json()
    assert member.post(route,json=payload).json()==first
    assert member.post(route,json={'index':0,'value':'Goodbye'}).status_code==409
    assert member.post(route,json={'index':4,'value':'bad'}).status_code==409

def test_resume_attempt(member):
    a=member.post('/api/lessons/first-hello/start').json()
    member.post(f'/api/attempts/{a["id"]}/answer',json={'index':0,'value':'Hello'})
    resumed=member.post('/api/lessons/first-hello/start').json()
    assert resumed['id']==a['id'] and resumed['index']==1

def test_no_repeat_reward(member):
    for _ in range(2):
        a=solve(member)
        assert member.post(f'/api/attempts/{a["id"]}/complete').status_code==200
        repeated=member.post(f'/api/attempts/{a["id"]}/complete').json()
        assert repeated['xp_awarded']==0
    assert member.get('/api/users/me').json()['xp']==50

def test_failed_attempt_no_reward(member):
    a=solve(member,wrong=True)
    result=member.post(f'/api/attempts/{a["id"]}/complete').json()
    assert not result['passed'] and result['xp_awarded']==0

def test_attempt_ownership(member):
    a=member.post('/api/lessons/first-hello/start').json()
    member.post('/api/auth/dev');member.patch('/api/users/me/settings',json={})
    assert member.post(f'/api/attempts/{a["id"]}/answer',json={'index':0,'value':'Hello'}).status_code==404

def test_privacy_and_export(member):
    solve(member)
    assert member.get('/api/users/me/export').status_code==200
    assert member.get('/api/leaderboard').json()==[]
    assert member.delete('/api/users/me').status_code==200

def test_settings_validation(member):
    assert member.patch('/api/users/me/settings',json={'timezone':'bad/time'}).status_code==422
    assert member.patch('/api/users/me/settings',json={'minutes':9000}).status_code==422

def test_all_content_answerable():
    assert len(LESSONS)==17
    assert {'A1','A2'}=={l['level'] for l in LESSONS.values()}
    for lesson in LESSONS.values():
        assert len(lesson['exercises'])>=3
        for e in lesson['exercises']:
            assert e['answers'] and e['explanation']
            if e['type']=='choice':assert e['answers'][0] in e['choices']
