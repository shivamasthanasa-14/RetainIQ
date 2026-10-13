"""Repair demonstrably invalid fixture escalations while retaining the original audit."""
import json
from pathlib import Path
from .prepared import PreparedAI
from .knowledge import Knowledge
from .workflow import Workflow

GENERIC='Review incident context and agree next update'

def repair_seed_escalations(store,root):
    key=store.metadata('scenario')
    if key not in {'routine','backlog','complex'} or Path(store.path).stem!=key:
        return
    scenario=json.loads((Path(root)/'data'/'scenarios'/f'{key}.json').read_text())
    fixtures={t['ticket_id']:t for t in scenario['tickets']}
    prepared=PreparedAI(root); knowledge=Knowledge(Path(root)/'knowledge_base')
    permitted={'Scenario intake','Classified','Owner identifier migrated','Seed escalation reviewed'}
    for ticket in store.tickets():
        fixture=fixtures.get(ticket['ticket_id'])
        if not fixture or ticket['status']!='Escalated' or ticket['revision']!=1 or ticket['follow_up']!=GENERIC:
            continue
        if any(ticket[k]!=fixture[k] for k in ('subject','message','received_at','due_date','customer')):
            continue
        history=store.history(ticket['ticket_id'])
        if not any(e['action']=='Scenario intake' for e in history) or any(e['action'] not in permitted for e in history):
            continue  # Employee escalation, follow-up, imports and draft decisions take precedence.
        if store.query('SELECT id FROM dispatches WHERE ticket_id=?',(ticket['ticket_id'],)):
            continue
        try:
            classification=prepared.classify(ticket)
            docs=knowledge.retrieve(ticket['subject']+' '+ticket['message'])
            draft=prepared.draft(ticket,docs)
        except Exception:
            continue
        correction=fixture.get('seed_escalation_before')
        routine=correction and not classification['needs_specialist'] and not classification['missing_information'] and draft['supported'] and not draft['missing_information']
        explanation=classification['summary']+' '+classification['reason']
        if routine:
            explanation='Seed-only escalation reviewed: documented request, no specialist flag or missing information; no employee escalation or later action in history.'
        elif not classification['needs_specialist']:
            # Incomplete information or permission circumstances remain for individual review.
            missing=classification['missing_information'] or draft['missing_information']
            explanation+=' Information needed: '+('; '.join(missing) if missing else 'Confirm why this request was escalated before approving a reply.')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=dict(db.execute('SELECT * FROM tickets WHERE ticket_id=?',(ticket['ticket_id'],)).fetchone())
            if current!=ticket: continue
            # Re-check history under the write lock before changing any seeded escalation.
            if any(r['action'] not in permitted for r in db.execute('SELECT action FROM history WHERE ticket_id=?',(ticket['ticket_id'],))): continue
            if routine:
                processing='Pending AI' if ticket['processing_status'] in {'Pending AI','AI Failed'} else 'Processed'
                db.execute("UPDATE tickets SET status='Open',processing_status=?,attention_reason='',follow_up=? WHERE ticket_id=?",(processing,fixture['follow_up'],ticket['ticket_id']))
                store.lifecycle_event(db,ticket['ticket_id'],'Open',ticket['due_date'],ticket['received_at'])
            else:
                db.execute('UPDATE tickets SET attention_reason=?,follow_up=? WHERE ticket_id=?',(explanation,explanation,ticket['ticket_id']))
            store.event(db,ticket['ticket_id'],'Seed escalation reviewed','Support Lead',{'before':ticket,'decision':'Routine documented request' if routine else 'Escalation retained','reason':explanation})
        if routine and store.ticket(ticket['ticket_id'])['processing_status']=='Processed':
            Workflow(store,prepared,knowledge).prepare_draft(ticket['ticket_id'],'Support Lead')
