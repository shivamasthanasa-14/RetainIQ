import pytest
from retainiq.store import Store
from retainiq.imports import import_records
from retainiq.workflow import Workflow
from retainiq.constants import OWNERS

def test_resolved_during_inference_cannot_be_reopened(tmp_path):
    store=Store(tmp_path/'race.db')
    import_records(store,[{'ticket_id':'RACE','customer':'Demo','received_at':'2026-01-01','subject':'Invite','message':'Invite an Editor'}])
    class AI:
        label='Explicit test double'
        def classify(self,ticket):
            with store.connect() as db:
                db.execute("UPDATE tickets SET status='Resolved',resolved_at='2026-01-02' WHERE ticket_id='RACE'")
            return {'category':'Account Access','summary':'Invite','needs_specialist':True,'reason':'Test escalation','missing_information':[]}
    result=Workflow(store,AI(),None).process('RACE')
    assert result.startswith('Skipped')
    assert store.ticket('RACE')['status']=='Resolved'
    assert not store.query('SELECT * FROM dispatches')

def test_due_date_before_receipt_is_rejected(tmp_path):
    store=Store(tmp_path/'due.db')
    import_records(store,[{'ticket_id':'DUE','customer':'Demo','received_at':'2026-01-02','subject':'Invite','message':'Invite an Editor'}])
    with pytest.raises(ValueError,match='precede'):
        Workflow(store,None,None).follow_up('DUE',OWNERS[0],'Check','2026-01-01','Open','','Support Lead')

def test_resolution_recalculates_dashboard(tmp_path):
    from retainiq.reporting import report
    store=Store(tmp_path/'dashboard.db');store.set_metadata('reference_date','2026-01-31')
    import_records(store,[{'ticket_id':'D','customer':'Demo','received_at':'2026-01-29','subject':'Invite','message':'Invite an Editor'}])
    before=report(store)['metrics']
    Workflow(store,None,None).follow_up('D',OWNERS[0],'','2026-02-01','Resolved','Customer confirmed','Support Lead')
    after=report(store)['metrics']
    assert before['Open Requests']==1 and after['Open Requests']==0
    assert after['Requests Resolved']==before['Requests Resolved']+1
