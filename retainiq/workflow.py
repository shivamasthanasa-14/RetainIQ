import json
from datetime import date, timedelta
from .ai import validate_classification, validate_draft
from .constants import OWNERS, ROUTING, STATUSES, TRANSITIONS
from .store import now

class Workflow:
    def __init__(self, store, ai, knowledge):
        self.store, self.ai, self.knowledge = store, ai, knowledge

    def _escalate(self, db, tid, owner, reason, actor):
        if owner not in OWNERS or not reason.strip():
            raise ValueError('Choose an owner and enter an escalation reason')
        ticket = dict(db.execute('SELECT * FROM tickets WHERE ticket_id=?', (tid,)).fetchone())
        due=ticket['due_date'] or (self.store.reference_date()+timedelta(days=1)).isoformat()
        db.execute("UPDATE tickets SET status='Escalated',owner=?,processing_status='Needs Review',follow_up=?,due_date=?,resolved_at=NULL,updated_at=? WHERE ticket_id=?",
                   (owner, reason, due, now(), tid))
        self.store.lifecycle_event(db, tid, 'Escalated', due)
        event_id = self.store.event(db, tid, 'Escalated', actor, {'owner': owner, 'reason': reason})
        payload = {'ticket_id': tid, 'owner': owner, 'subject': ticket['subject'], 'reason': reason, 'escalation_id': event_id}
        db.execute('INSERT INTO dispatches(ticket_id,escalation_id,owner,payload,updated_at) VALUES (?,?,?,?,?)',
                   (tid, event_id, owner, json.dumps(payload), now()))

    def process(self, tid, actor='Demo owner'):
        ticket = self.store.ticket(tid)
        if ticket['status'] == 'Resolved':
            return 'Skipped: ticket is resolved'
        if ticket['processing_status'] not in {'Pending AI', 'AI Failed'}:
            return 'Skipped: already processed'
        try:
            result = validate_classification(self.ai.classify(ticket))
        except Exception as error:
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                current = dict(db.execute('SELECT * FROM tickets WHERE ticket_id=?', (tid,)).fetchone())
                if current['revision'] == ticket['revision'] and current['processing_status'] in {'Pending AI', 'AI Failed'}:
                    db.execute("UPDATE tickets SET processing_status='AI Failed',updated_at=? WHERE ticket_id=?", (now(), tid))
                    self.store.event(db, tid, 'AI processing failed', actor, {'error': str(error)[:500]})
            return 'AI Failed: ' + str(error)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = dict(db.execute('SELECT * FROM tickets WHERE ticket_id=?', (tid,)).fetchone())
            if current['status']=='Resolved' or current['revision'] != ticket['revision'] or current['processing_status'] not in {'Pending AI', 'AI Failed'}:
                return 'Skipped: ticket changed during processing'
            owner = current['owner'] or ROUTING[result['category']]
            review = result['needs_specialist'] or bool(result['missing_information']) or result['category'] == 'Other' or current['status'] == 'Escalated'
            reason = result['summary']+' '+result['reason'] if review else ''
            if current['status']=='Escalated':
                previous=db.execute("SELECT detail FROM history WHERE ticket_id=? AND action='Escalated' ORDER BY id DESC LIMIT 1",(tid,)).fetchone()
                prior_reason=json.loads(previous['detail']).get('reason','') if previous else ''
                reason=prior_reason or current['attention_reason'] or (current['follow_up'] if current['follow_up']!='Review incident context and agree next update' else '') or ('Previous escalation needs review: '+result['summary'])
            db.execute('UPDATE tickets SET category=?,summary=?,owner=?,processing_status=?,ai_provider=?,updated_at=? WHERE ticket_id=?',
                       (result['category'], result['summary'], owner, 'Needs Review' if review else 'Processed', self.ai.label, now(), tid))
            db.execute('UPDATE tickets SET issue_group=?,attention_reason=?,missing_information=?,result_origin=? WHERE ticket_id=?',
                       (result.get('issue_group', result['category']), reason, json.dumps(result['missing_information']), getattr(self.ai, 'origin', 'Live AI'), tid))
            self.store.event(db, tid, 'Classified', actor, {'result': result, 'provider': self.ai.label, 'revision': ticket['revision']})
            if review and current['status'] != 'Escalated':
                specialist = OWNERS[2]
                self._escalate(db, tid, specialist, reason or 'Human review required', actor)
        return 'Needs Review' if review else 'Processed'

    def batch(self, tids, actor='Demo owner'):
        return [{'ticket_id': tid, 'result': self.process(tid, actor)} for tid in dict.fromkeys(tids)]

    def prepare_draft(self, tid, actor='Demo owner'):
        ticket = self.store.ticket(tid)
        current = self.store.draft(tid)
        if current and current[0]['ticket_revision'] == ticket['revision'] and current[0]['status'] in {'Draft', 'Approved'}:
            return current[0]['id']
        if ticket['processing_status'] != 'Processed' or ticket['status'] in {'Escalated', 'Resolved'}:
            raise ValueError('Only processed standard-support tickets can receive an AI draft')
        docs = self.knowledge.retrieve(ticket['subject'] + ' ' + ticket['message'])
        if not docs:
            self.escalate(tid, ticket['owner'] or OWNERS[0], 'No relevant company documentation', actor)
            return None
        result = validate_draft(self.ai.draft(ticket, docs), docs)
        if not result['supported']:
            self.escalate(tid, ticket['owner'] or OWNERS[0], 'Retrieved documentation does not support an answer', actor)
            return None
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            latest = dict(db.execute('SELECT * FROM tickets WHERE ticket_id=?', (tid,)).fetchone())
            if latest['revision'] != ticket['revision'] or latest['status'] in {'Escalated', 'Resolved'} or latest['processing_status'] != 'Processed':
                raise ValueError('Ticket changed during drafting; reopen the workspace')
            existing = db.execute('SELECT id FROM drafts WHERE ticket_id=? AND ticket_revision=?', (tid, ticket['revision'])).fetchone()
            if existing:
                return existing['id']
            draft_id = db.execute('INSERT INTO drafts(ticket_id,ticket_revision,body,original_body,sources,missing,provider,created_at) VALUES (?,?,?,?,?,?,?,?)',
                (tid, ticket['revision'], result['body'], result['body'], json.dumps([d for d in docs if d['id'] in result['source_ids']]),
                 json.dumps(result['missing_information']), self.ai.label, now())).lastrowid
            db.execute("UPDATE tickets SET processing_status='Draft Ready',updated_at=? WHERE ticket_id=?", (now(), tid))
            self.store.event(db, tid, 'Draft created', actor, {'draft_id': draft_id, 'provider': self.ai.label, 'source_ids': result['source_ids'], 'origin':getattr(self.ai,'origin','Live AI')})
            return draft_id

    def edit_draft(self, draft_id, body, actor):
        if not body.strip() or len(body) > 12000:
            raise ValueError('Enter a response between 1 and 12000 characters')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            draft = db.execute('SELECT * FROM drafts WHERE id=?', (draft_id,)).fetchone()
            if not draft or draft['status'] != 'Draft':
                raise ValueError('Only an unapproved current draft can be edited')
            db.execute('UPDATE drafts SET body=? WHERE id=?', (body.strip(), draft_id))
            self.store.event(db, draft['ticket_id'], 'Draft edited', actor, {'draft_id': draft_id, 'before': draft['body'], 'after': body.strip()})

    def approve(self, draft_id, actor):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            draft = db.execute('SELECT * FROM drafts WHERE id=?', (draft_id,)).fetchone()
            if not draft or draft['status'] != 'Draft':
                raise ValueError('Draft already approved or superseded')
            ticket = db.execute('SELECT * FROM tickets WHERE ticket_id=?', (draft['ticket_id'],)).fetchone()
            if ticket['revision'] != draft['ticket_revision'] or ticket['status'] in {'Escalated', 'Resolved'}:
                raise ValueError('Ticket requires review before approval')
            db.execute("UPDATE drafts SET status='Approved',approved_at=?,approved_by=? WHERE id=?", (now(), actor, draft_id))
            db.execute("UPDATE tickets SET processing_status='Approved',updated_at=? WHERE ticket_id=?", (now(), draft['ticket_id']))
            self.store.event(db, draft['ticket_id'], 'Response approved', actor, {'draft_id': draft_id, 'body': draft['body']})

    def escalate(self, tid, owner, reason, actor):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT status FROM tickets WHERE ticket_id=?', (tid,)).fetchone()
            if not current:
                raise ValueError('Ticket not found')
            if current['status'] == 'Escalated':
                raise ValueError('Ticket is already escalated; update follow-up instead')
            self._escalate(db, tid, owner, reason, actor)
            db.execute('UPDATE tickets SET attention_reason=? WHERE ticket_id=?', (reason, tid))

    def reject(self, draft_id, reason, actor):
        if not reason.strip():
            raise ValueError('Enter why the response is unsuitable')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            draft = db.execute('SELECT * FROM drafts WHERE id=?', (draft_id,)).fetchone()
            if not draft or draft['status'] != 'Draft':
                raise ValueError('Only a current unapproved draft can be rejected')
            db.execute("UPDATE drafts SET status='Rejected' WHERE id=?", (draft_id,))
            db.execute("UPDATE tickets SET processing_status='Needs Review',attention_reason=?,updated_at=? WHERE ticket_id=?", (reason, now(), draft['ticket_id']))
            self.store.event(db, draft['ticket_id'], 'Response rejected', actor, {'draft_id':draft_id,'reason':reason})

    def review_template(self, group_key, draft_id, body, actor):
        if not body.strip() or not actor.strip():
            raise ValueError('A response and reviewer are required')
        with self.store.connect() as db:
            draft = db.execute('SELECT * FROM drafts WHERE id=?', (draft_id,)).fetchone()
            if not draft or draft['status'] not in {'Draft','Approved'}:
                raise ValueError('Choose a supported current draft')
            from .scenarios import fingerprint
            ticket=dict(db.execute('SELECT * FROM tickets WHERE ticket_id=?',(draft['ticket_id'],)).fetchone())
            template_id = db.execute('INSERT INTO response_templates(group_key,body,sources,reviewed_by,reviewed_at,request_hash) VALUES (?,?,?,?,?,?)',
                       (group_key, body.strip(), draft['sources'], actor, now(),fingerprint(ticket))).lastrowid
            self.store.event(db, draft['ticket_id'], 'Reusable response reviewed', actor, {'template_id':template_id,'group_key':group_key,'body':body})
            return template_id

    def apply_template(self, tid, template_id, expected_group, actor):
        template = self.store.query('SELECT * FROM response_templates WHERE id=?', (template_id,))[0]
        if template['group_key'] != expected_group:
            raise ValueError('Template belongs to a different handling group')
        from .groups import group_key
        ticket = self.store.ticket(tid)
        from .scenarios import fingerprint
        if template['request_hash']!=fingerprint(ticket):
            raise ValueError('This ticket has different request context; review its own response')
        if group_key(ticket) != expected_group or ticket['status'] in {'Resolved','Escalated'}:
            raise ValueError('Ticket requires individual handling')
        draft = self.store.draft(tid)
        if not draft or draft[0]['status'] != 'Draft':
            raise ValueError('Prepare and inspect a per-ticket draft before applying a template')
        draft_sources = {d['id'] for d in json.loads(draft[0]['sources'])}
        if not {d['id'] for d in json.loads(template['sources'])}.issubset(draft_sources):
            raise ValueError('Template sources do not match this ticket; use individual review')
        self.edit_draft(draft[0]['id'], template['body'], actor)

    def follow_up(self, tid, owner, follow_up, due_date, status, notes, actor):
        if owner not in OWNERS or status not in STATUSES:
            raise ValueError('Invalid owner or status')
        if due_date:
            date.fromisoformat(due_date)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            ticket = dict(db.execute('SELECT * FROM tickets WHERE ticket_id=?', (tid,)).fetchone())
            if due_date and due_date < ticket['received_at'][:10]:
                raise ValueError('Due date cannot precede receipt date')
            if status != ticket['status'] and status not in TRANSITIONS[ticket['status']]:
                raise ValueError('Invalid status transition')
            if status == 'Resolved' and not notes.strip():
                raise ValueError('Resolution notes are required')
            if status != 'Resolved' and not follow_up.strip():
                raise ValueError('Describe the required follow-up')
            if status == 'Escalated' and ticket['status'] != 'Escalated':
                self._escalate(db, tid, owner, follow_up, actor)
            db.execute('UPDATE tickets SET owner=?,follow_up=?,due_date=?,status=?,resolution_notes=?,resolved_at=?,updated_at=? WHERE ticket_id=?',
                (owner, follow_up, due_date, status, notes, (ticket['resolved_at'] if ticket['status']=='Resolved' else self.store.effective_now()) if status == 'Resolved' else None, now(), tid))
            self.store.lifecycle_event(db, tid, status, due_date)
            self.store.event(db, tid, 'Follow-up updated', actor, {'before': ticket, 'status': status, 'owner': owner, 'follow_up': follow_up, 'due_date': due_date, 'notes': notes})

def metrics(tickets, today=None):
    today = (today or date.today()).isoformat()
    return {'New Requests': sum(t['status'] != 'Resolved' and t['processing_status'] in {'Pending AI', 'AI Failed'} for t in tickets),
            'Open Requests': sum(t['status'] != 'Resolved' for t in tickets),
            'Resolved Requests': sum(t['status'] == 'Resolved' for t in tickets),
            'Requests Needing Review': sum(t['status'] != 'Resolved' and (t['processing_status'] in {'Needs Review', 'Draft Ready'} or t['status'] == 'Escalated') for t in tickets),
            'Overdue Requests': sum(bool(t['due_date']) and t['due_date'] < today and t['status'] != 'Resolved' for t in tickets)}
