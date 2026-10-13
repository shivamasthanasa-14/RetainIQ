import json
from datetime import date
import pytest
from retainiq.scenarios import Workspaces,generate_scenario,SCENARIOS,fingerprint
from retainiq.store import Store
from retainiq.reporting import report
from retainiq.imports import import_records
from retainiq.workflow import Workflow
from retainiq.groups import issue_groups
from retainiq.prepared import PreparedAI
from retainiq.ai import AIUnavailable
from retainiq.constants import OWNERS

@pytest.fixture
def manager(tmp_path): return Workspaces(tmp_path,'reviewer_one')

def test_dataset_consistency():
    for key in SCENARIOS.values():
        scenario=generate_scenario(key)
        assert scenario==generate_scenario(key)
        tickets=scenario['tickets']
        assert len(tickets)==100
        assert len({t['ticket_id'] for t in tickets})==100
        assert {t['status'] for t in tickets}=={'Open','In Progress','Escalated','Resolved'}
        assert set(t['owner'] for t in tickets)<=set(OWNERS)
        assert len({t['received_at'][:10] for t in tickets})>25
        for t in tickets:
            assert t['received_at'][:10]<='2026-09-30'
            if t['resolved_at']:
                assert t['received_at']<t['resolved_at']
                assert t['resolved_at'][:10]<='2026-09-30'

def test_scenario_and_reviewer_isolation(manager):
    a=manager.open('routine'); b=manager.open('backlog')
    t=a.tickets()[0]
    with a.connect() as db: db.execute('UPDATE tickets SET owner=? WHERE ticket_id=?',('Support Lead',t['ticket_id']))
    assert len(b.tickets())==100
    another=Workspaces(manager.root,'reviewer_two').open('routine')
    assert another.ticket(t['ticket_id'])['owner']==t['owner']
    assert manager.open('routine').ticket(t['ticket_id'])['owner']=='Support Lead'

def test_reset_is_selected_and_recoverable(manager):
    a=manager.open('routine'); b=manager.open('backlog')
    old=a.tickets()[0]
    with a.connect() as db: db.execute("UPDATE tickets SET follow_up='Changed' WHERE ticket_id=?",(old['ticket_id'],))
    before=b.tickets()
    snapshot=manager.reset('routine')
    assert snapshot.exists()
    assert Store(snapshot).ticket(old['ticket_id'])['follow_up']=='Changed'
    assert manager.open('routine').ticket(old['ticket_id'])['follow_up']==old['follow_up']
    assert b.tickets()==before

def test_custom_upload_does_not_change_scenario(manager):
    scenario=manager.open('routine'); custom=manager.open('routine',custom=True)
    original=scenario.tickets()
    import_records(custom,[{'ticket_id':'CUSTOM-1','customer':'Demo','received_at':'2026-09-01','subject':'Question','message':'How do I invite an Editor?'}])
    assert len(custom.tickets())==1
    assert scenario.tickets()==original
    assert custom.metadata('reference_date') is None

def test_backlog_scenario_rises(manager):
    a=report(manager.open('routine'),'All Time'); b=report(manager.open('backlog'),'All Time')
    assert b['metrics']['Open Requests']>a['metrics']['Open Requests']
    assert b['weeks'][-1]['Open Requests']>b['weeks'][2]['Open Requests']
    assert sum(w['Incoming'] for w in b['weeks'])==100
    assert sum(w['Resolved'] for w in b['weeks'])==b['metrics']['Requests Resolved']

@pytest.fixture
def timeline(tmp_path):
    s=Store(tmp_path/'timeline.db'); s.set_metadata('reference_date','2026-01-31')
    for tid,received,resolved,due in [('A','2026-01-01','2026-01-08','2026-01-05'),('B','2026-01-15',None,'2026-01-20'),('C','2026-01-25','2026-01-28','2026-02-01'),('FUTURE','2026-02-02',None,'2026-02-05')]:
        with s.connect() as db:
            db.execute('INSERT INTO tickets(ticket_id,customer,received_at,subject,message,due_date,status,resolved_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                (tid,'Demo',received,'Question','Question',due,'Resolved' if resolved else 'Open',resolved,received))
            s.lifecycle_event(db,tid,'Open',due,received)
            if resolved: s.lifecycle_event(db,tid,'Resolved',due,resolved)
    return s

def test_reporting_periods_and_previous_cutoff(timeline):
    r=report(timeline,'Last 7 Days')
    assert r['metrics']=={'Requests Received':1,'Requests Resolved':1,'Open Requests':1,'Overdue Requests':1}
    assert r['comparisons']=={'Requests Received':1,'Requests Resolved':1,'Open Requests':0,'Overdue Requests':0}
    r=report(timeline,'Last 30 Days')
    assert r['metrics']['Requests Received']==2
    assert r['metrics']['Requests Resolved']==2
    assert report(timeline,'All Time')['comparisons'] is None
    assert report(timeline,'All Time')['metrics']['Requests Received']==3
    historic=report(timeline,'All Time',date(2026,1,7))
    assert historic['metrics']['Open Requests']==1
    assert historic['metrics']['Overdue Requests']==1

def test_reopening_preserves_historical_backlog(timeline):
    with timeline.connect() as db:
        db.execute("UPDATE tickets SET status='Open',resolved_at=NULL WHERE ticket_id='A'")
        timeline.lifecycle_event(db,'A','Open','2026-02-01','2026-01-30')
    assert report(timeline,'All Time',date(2026,1,20))['metrics']['Open Requests']==1
    assert report(timeline,'All Time')['metrics']['Open Requests']==2
    assert report(timeline,'All Time')['metrics']['Requests Resolved']==2

def test_due_date_history(timeline):
    with timeline.connect() as db:
        db.execute("UPDATE tickets SET due_date='2026-02-15' WHERE ticket_id='B'")
        timeline.lifecycle_event(db,'B','Open','2026-02-15','2026-01-29')
    assert report(timeline,'All Time',date(2026,1,25))['metrics']['Overdue Requests']==1
    assert report(timeline,'All Time')['metrics']['Overdue Requests']==0

def test_grouping_different_handling():
    base={'category':'Account Access','summary':'Login','status':'Open','processing_status':'Processed'}
    records=[dict(base,ticket_id='1',issue_group='Password reset'),dict(base,ticket_id='2',issue_group='SSO access'),
             dict(base,ticket_id='3',issue_group='Password reset'),dict(base,ticket_id='4',issue_group='Password reset',processing_status='Needs Review')]
    groups=issue_groups(records)
    assert len(groups)==3
    assert groups[0]['Number of Requests']==2
    assert sum(g['Number of Requests'] for g in groups)==4

def test_prepared_mode_does_not_invent_unknown_outputs(tmp_path):
    p=PreparedAI(tmp_path)
    with pytest.raises(AIUnavailable,match='No reviewed'):
        p.classify({'subject':'Custom','message':'A new customer message'})

def test_owner_migration_preserves_audit(tmp_path):
    s=Store(tmp_path/'legacy.db')
    import_records(s,[{'ticket_id':'OLD','customer':'Demo','received_at':'2026-01-01','subject':'Question','message':'Original'}])
    with s.connect() as db: db.execute("UPDATE tickets SET owner='Alex Reed — Engineering' WHERE ticket_id='OLD'")
    history_before=s.history('OLD')
    s.migrate_owners(); s.migrate_owners()
    assert s.ticket('OLD')['owner']=='Support Lead'
    assert s.history('OLD')[-1]==history_before[-1]
    assert len(s.history('OLD'))==len(history_before)+1

def test_update_creation_date_rejected(timeline):
    with pytest.raises(ValueError,match='immutable'):
        import_records(timeline,[{'ticket_id':'B','customer':'Demo','received_at':'2026-01-16','subject':'Question','message':'Changed','operation':'update'}])
    assert timeline.ticket('B')['received_at']=='2026-01-15'
