import json
from pathlib import Path
import pytest
from retainiq.scenarios import Workspaces,fingerprint
from retainiq.prepared import PreparedAI
from retainiq.knowledge import Knowledge
from retainiq.workflow import Workflow
from retainiq.reporting import report
from retainiq.groups import issue_groups
from retainiq.store import Store

ROOT=Path(__file__).parents[1]

def ready_prepared():
    p=PreparedAI(ROOT)
    if not p.catalog['entries'] or not all(e.get('reviewed') for e in p.catalog['entries'].values()):
        pytest.skip('Actual recorded catalogue awaits development review')
    return p

@pytest.mark.parametrize('key',['routine','backlog','complex'])
def test_actual_prepared_results_load_without_model(tmp_path,key,monkeypatch):
    prepared=ready_prepared()
    monkeypatch.setenv('OLLAMA_URL','http://127.0.0.1:1')
    store=Workspaces(tmp_path).open(key)
    kb=Knowledge(ROOT/'knowledge_base')
    before=report(store,'All Time')
    result=prepared.load(store,kb)
    assert len(result)==100
    assert not any('Manual review:' in r['result'] for r in result)
    assert all(t['result_origin']=='Prepared AI Demo Results' for t in store.tickets())
    assert len(issue_groups(store.tickets()))>=5
    assert not any(d['status']=='Approved' for d in store.query('SELECT * FROM drafts'))
    assert report(store,'All Time')['metrics']['Requests Resolved']==before['metrics']['Requests Resolved']
    assert report(store,'All Time')['metrics']['Open Requests']==before['metrics']['Open Requests']
    assert report(store,'All Time')['metrics']['Overdue Requests']==before['metrics']['Overdue Requests']
    history_count=len(store.query('SELECT * FROM history'))
    assert prepared.load(store,kb)==[]
    assert len(store.query('SELECT * FROM history'))==history_count

def test_template_review_requires_per_ticket_approval(tmp_path):
    p=ready_prepared(); store=Workspaces(tmp_path).open('routine'); kb=Knowledge(ROOT/'knowledge_base')
    p.load(store,kb)
    workflow=Workflow(store,p,kb)
    group=next(g for g in issue_groups(store.tickets()) if g['Suggested Handling']=='Standard documentation' and any(t['processing_status']=='Draft Ready' for t in g['tickets']))
    ticket=next(t for t in group['tickets'] if t['processing_status']=='Draft Ready')
    draft=store.draft(ticket['ticket_id'])[0]
    template=workflow.review_template(group['key'],draft['id'],draft['body'],'Support Lead')
    workflow.apply_template(ticket['ticket_id'],template,group['key'],'Agent X')
    assert store.draft(ticket['ticket_id'])[0]['status']=='Draft'
    workflow.approve(draft['id'],'Agent X')
    assert store.ticket(ticket['ticket_id'])['status']!='Resolved'
    assert Store(store.path).draft(ticket['ticket_id'])[0]['approved_by']=='Agent X'
    with pytest.raises(ValueError): workflow.approve(draft['id'],'Agent X')

def test_reject_supported_draft(tmp_path):
    p=ready_prepared(); s=Workspaces(tmp_path).open('routine'); kb=Knowledge(ROOT/'knowledge_base'); p.load(s,kb)
    ticket=next(t for t in s.tickets() if t['processing_status']=='Draft Ready')
    d=s.draft(ticket['ticket_id'])[0]; w=Workflow(s,p,kb)
    w.reject(d['id'],'Customer context needs checking','Support Lead')
    assert s.draft(ticket['ticket_id'])[0]['status']=='Rejected'
    assert s.ticket(ticket['ticket_id'])['processing_status']=='Needs Review'
    with pytest.raises(ValueError): w.approve(d['id'],'Support Lead')

def test_reusable_reply_cannot_cross_materially_different_role_requests(tmp_path):
    from retainiq.scenarios import CASES
    from retainiq.imports import import_records
    from retainiq.groups import group_key
    p=ready_prepared();s=Workspaces(tmp_path).open('routine',custom=True);kb=Knowledge(ROOT/'knowledge_base')
    import_records(s,[{'ticket_id':f'ROLE-{i}','customer':'Demo','received_at':'2026-09-01','subject':CASES[i][2],'message':CASES[i][3]} for i in [0,1]])
    p.load(s,kb);w=Workflow(s,p,kb)
    editor=s.ticket('ROLE-0');viewer=s.ticket('ROLE-1')
    draft=s.draft('ROLE-0')[0]
    template=w.review_template(group_key(editor),draft['id'],draft['body'],'Support Lead')
    assert group_key(editor)==group_key(viewer)
    with pytest.raises(ValueError,match='different request context'):
        w.apply_template('ROLE-1',template,group_key(viewer),'Support Lead')
    assert s.draft('ROLE-1')[0]['status']=='Draft'
