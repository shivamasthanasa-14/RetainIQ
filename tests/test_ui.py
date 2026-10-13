from pathlib import Path
from streamlit.testing.v1 import AppTest
from retainiq.scenarios import Workspaces

def instance(tmp_path,monkeypatch):
    monkeypatch.setenv('RETAINIQ_WORKSPACE_ROOT',str(tmp_path))
    monkeypatch.setenv('RETAINIQ_WORKSPACE_MODE','local')
    monkeypatch.setenv('OLLAMA_URL','http://127.0.0.1:1')
    return AppTest.from_file(str(Path(__file__).parents[1]/'app.py')).run(timeout=60)

def test_three_pages_and_scenario_switch(tmp_path,monkeypatch):
    app=instance(tmp_path,monkeypatch)
    assert not app.exception
    assert app.sidebar.radio[0].options==['Support Overview','Customer Issues & Responses','Needs Attention']
    assert len(app.metric)==4
    before=[m.value for m in app.metric]
    next(w for w in app.selectbox if w.label=='Choose Sample Data').set_value('Busy Support Period').run(timeout=60)
    assert not app.exception
    assert [m.value for m in app.metric]!=before
    for page in ['Customer Issues & Responses','Needs Attention']:
        app.sidebar.radio[0].set_value(page).run(timeout=60)
        assert not app.exception

def test_custom_empty_dashboard(tmp_path,monkeypatch):
    app=instance(tmp_path,monkeypatch)
    next(w for w in app.selectbox if w.label=='Data workspace').set_value('Custom uploads').run()
    assert not app.exception
    assert all(m.value=='0' for m in app.metric)

def test_invalid_followup_does_not_hide_error(tmp_path,monkeypatch):
    app=instance(tmp_path,monkeypatch)
    app.sidebar.radio[0].set_value('Needs Attention').run()
    next(w for w in app.text_area if w.label=='Required follow-up').set_value('')
    next(w for w in app.selectbox if w.label=='Current status').set_value('Open')
    next(b for b in app.button if b.label=='Save follow-up').click().run()
    assert not app.exception
    assert any('follow-up' in e.value for e in app.error)

def test_default_prepared_period_and_selected_approval(tmp_path,monkeypatch):
    app=instance(tmp_path,monkeypatch)
    store=Workspaces(tmp_path,'local').open('routine')
    assert all(t['result_origin']=='Prepared AI Demo Results' for t in store.tickets())
    app.sidebar.radio[0].set_value('Customer Issues & Responses').run(timeout=60)
    assert not app.exception
    assert not any(w.label=='Select issue group' for w in app.selectbox)
    assert len(app.text_area)>0
    check=next(w for w in app.checkbox if w.label.startswith('Approve for this customer'))
    tid=check.key.rsplit('_',1)[-1]
    check.check().run(timeout=60)
    next(b for b in app.button if b.label=='Approve selected responses' and not b.disabled).click().run(timeout=60)
    assert not app.exception
    assert store.ticket(tid)['processing_status']=='Approved'
    assert store.ticket(tid)['status']!='Resolved'
    next(w for w in app.get('segmented_control') if w.label=='Reporting period').set_value('All Time').run(timeout=60)
    assert not app.exception
    assert any('100 requests received' in c.value for c in app.caption)

def test_attention_excludes_unactionable_open_and_history_is_readable(tmp_path,monkeypatch):
    app=instance(tmp_path,monkeypatch)
    store=Workspaces(tmp_path,'local').open('routine')
    with store.connect() as db:
        db.execute("UPDATE tickets SET status='Open',processing_status='Approved',attention_reason='',follow_up='',due_date='2026-10-05' WHERE ticket_id='ROUTINE-100'")
    app.sidebar.radio[0].set_value('Needs Attention').run()
    assert not app.exception
    select=next(w for w in app.selectbox if w.label=='Select request')
    assert 'ROUTINE-100' not in select.options
    assert not app.get('json')
    assert not any('Dispatch' in b.label for b in app.button)
