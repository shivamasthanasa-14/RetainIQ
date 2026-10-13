import json
from pathlib import Path
from .ai import AIUnavailable, validate_classification, validate_draft
from .scenarios import fingerprint
from .store import now

class PreparedAI:
    origin = 'Prepared AI Demo Results'
    label = 'Prepared AI Demo Results'
    def __init__(self, root):
        path = Path(root)/'data'/'prepared_catalog.json'
        self.catalog=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'entries':{}}

    def entry(self,ticket):
        entry=self.catalog['entries'].get(fingerprint(ticket))
        if not entry or not entry.get('reviewed'):
            raise AIUnavailable('No reviewed prepared result for this exact request. Switch to Live AI or route for manual review.')
        self.label='Prepared AI Demo Results · '+entry['provider']
        return entry

    def classify(self,ticket):
        return validate_classification(self.entry(ticket)['classification'])

    def draft(self,ticket,docs):
        entry=self.entry(ticket)
        if not entry.get('draft'):
            return {'supported':False,'body':'','source_ids':[],'missing_information':[]}
        recorded={d['id']:d['text'] for d in entry.get('retrieved_documents',[])}
        current={d['id']:d['text'] for d in docs}
        if any(recorded.get(doc_id)!=current.get(doc_id) for doc_id in entry['draft']['source_ids']):
            raise AIUnavailable('Knowledge documents changed since preparation; use Live AI or human review')
        return validate_draft(entry['draft'],docs)

    def load(self,store,knowledge,actor='Support Lead'):
        from .workflow import Workflow
        workflow=Workflow(store,self,knowledge)
        results=[]
        for ticket in store.tickets():
            if ticket['processing_status'] not in {'Pending AI','AI Failed'}: continue
            try:
                entry=self.entry(ticket)
                classification=self.classify(ticket)
                if ticket['status']=='Resolved':
                    with store.connect() as db:
                        db.execute("UPDATE tickets SET category=?,summary=?,issue_group=?,attention_reason=?,missing_information=?,processing_status='Historical',result_origin=?,ai_provider=? WHERE ticket_id=? AND processing_status IN ('Pending AI','AI Failed')",
                            (classification['category'],classification['summary'],classification.get('issue_group',classification['category']),classification['reason'] if classification['needs_specialist'] else '',json.dumps(classification['missing_information']),self.origin,entry['provider'],ticket['ticket_id']))
                        store.event(db,ticket['ticket_id'],'Prepared historical classification loaded',actor,{'provider':entry['provider'],'fingerprint':fingerprint(ticket),'generated_at':entry['generated_at']})
                    result='Historical'
                else:
                    result=workflow.process(ticket['ticket_id'],actor)
                    if result=='Processed':
                        workflow.prepare_draft(ticket['ticket_id'],actor)
                results.append({'ticket_id':ticket['ticket_id'],'result':result})
            except Exception as error:
                current=store.ticket(ticket['ticket_id'])
                if current['status'] not in {'Resolved','Escalated'}:
                    workflow.escalate(ticket['ticket_id'],current['owner'] or 'Support Lead',str(error),actor)
                results.append({'ticket_id':ticket['ticket_id'],'result':'Manual review: '+str(error)})
        return results
