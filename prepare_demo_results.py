"""Record genuine local model outputs; review is a separate development step."""
import json
import time
from pathlib import Path
from retainiq.ai import AIService, validate_classification, validate_draft
from retainiq.constants import CATEGORIES
from retainiq.knowledge import Knowledge
from retainiq.scenarios import CASES, fingerprint, ensure_scenarios
from retainiq.store import now

ROOT=Path(__file__).parent
GROUPS=['User invitations','Password reset','SSO access','Invoice downloads','Payment details','Contract review','Workflow publishing','Pause workflows','Field mapping','Conditional branches','Slack permissions','Slack authorization','Salesforce authorization','Production integration incident','Webhook investigation','Onboarding session','Unclear request','Security incident','Unsupported feature','Run investigation']

def main():
    ensure_scenarios(ROOT)
    ai=AIService()
    kb=Knowledge(ROOT/'knowledge_base')
    path=ROOT/'data'/'prepared_catalog.json'
    catalog=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1,'entries':{}}
    requests=[{'subject':c[2],'message':c[3]} for c in CASES]
    def save(): path.write_text(json.dumps(catalog,indent=2,ensure_ascii=False),encoding='utf-8')
    pending=[(i,t) for i,t in enumerate(requests) if fingerprint(t) not in catalog['entries']]
    for offset in range(0,len(pending),4):
        batch=pending[offset:offset+4]
        properties={'id':{'type':'integer'},'category':{'type':'string','enum':CATEGORIES},'issue_group':{'type':'string','enum':GROUPS},'summary':{'type':'string'},'needs_specialist':{'type':'boolean'},'reason':{'type':'string'},'missing_information':{'type':'array','items':{'type':'string'}}}
        ai.output_schema={'type':'object','properties':{'results':{'type':'array','minItems':len(batch),'maxItems':len(batch),'items':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}},'required':['results'],'additionalProperties':False}
        started=time.perf_counter()
        result=ai.generate(
            'Classify EACH RelayOps request separately. Return a JSON object with results: a list, one object per input id. '
            'Each object must contain id, category, issue_group, summary (one short sentence), needs_specialist (boolean), reason, missing_information (list). '
            'Use exactly the supplied categories and specific issue_group labels. Understand meaning, not keyword frequency. '
            'Account Access: invitations, roles, login, security. Billing: invoices, payment details and contracts. '
            'Workflow Configuration: mapping, conditions, publish/pause. Integrations: named external services and webhooks. '
            'Product Errors: internal errors or possible data loss. Onboarding: onboarding help. Product Guidance: capability questions. Other: unclear messages. '
            'Set needs_specialist true for vague context, SSO investigation, unauthorized access, production outages, possible data loss, duplicate events, '
            'refunds or custom contract decisions and unsupported product capabilities. Do not flag ordinary password reset, invoice downloads, invitations or documented how-to as specialist. '
            'Use distinct groups for different handling even within a category.',
            {'categories':CATEGORIES,'issue_groups':GROUPS,'requests':[{'id':local,**t} for local,(i,t) in enumerate(batch)]})
        (ROOT/'verification'/'last_preparation_output.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        results=result.get('results',[])
        for row in results:
            if isinstance(row.get('id'),str) and row['id'].isdigit(): row['id']=int(row['id'])
        if {r.get('id') for r in results}!=set(range(len(batch))) or len(results)!=len(batch):
            raise ValueError('Model batch IDs do not match')
        for local,(i,t) in enumerate(batch):
            raw=next(r for r in results if r['id']==local)
            classification=validate_classification({k:v for k,v in raw.items() if k!='id'})
            if classification.get('issue_group') not in GROUPS:
                raise ValueError('Invalid issue group')
            catalog['entries'][fingerprint(t)]={'input':t,'case_index':i,'provider':ai.label,'generated_at':now(),
                'classification':classification,'raw_classification':raw,'draft':None,'reviewed':False,
                'classification_batch_seconds':round(time.perf_counter()-started,3)}
        save()
        print(f'Classified {len(catalog["entries"])} / {len(requests)} distinct messages',flush=True)
    routine=[entry for entry in catalog['entries'].values() if not entry['classification']['needs_specialist'] and not entry.get('draft_attempted')]
    for offset in range(0,len(routine),3):
        batch=routine[offset:offset+3]
        properties={'id':{'type':'integer'},'supported':{'type':'boolean'},'body':{'type':'string'},'source_ids':{'type':'array','items':{'type':'string'}},'missing_information':{'type':'array','items':{'type':'string'}}}
        ai.output_schema={'type':'object','properties':{'results':{'type':'array','minItems':len(batch),'maxItems':len(batch),'items':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}},'required':['results'],'additionalProperties':False}
        input_rows=[]
        for local,entry in enumerate(batch):
            t=entry['input']; docs=kb.retrieve(t['subject']+' '+t['message'])
            entry['retrieved_documents']=docs
            input_rows.append({'id':local,**t,'documents':docs})
        started=time.perf_counter()
        result=ai.generate(
            'Prepare one RelayOps response for EACH request using ONLY its own provided documents. '
            'Return results: list of objects with id, supported (boolean), body, source_ids (list), missing_information (list). '
            'Answer the actual question in 2-4 sentences. Cite the document title in the response where useful. '
            'Do not invent fixes, features, guarantees, appointments, refunds or prices. Where documents cannot answer, supported=false and body="". '
            'Do not mix documents between requests. Never treat a security incident or production failure as a routine how-to.',
            {'requests':input_rows})
        if {r.get('id') for r in result.get('results',[])}!=set(range(len(batch))):
            raise ValueError('Draft IDs do not match')
        for local,entry in enumerate(batch):
            raw=next(r for r in result['results'] if r['id']==local)
            draft=validate_draft({k:v for k,v in raw.items() if k!='id'},entry['retrieved_documents'])
            entry.update(draft=draft,raw_draft=raw,draft_attempted=True,draft_batch_seconds=round(time.perf_counter()-started,3))
        save()
        print(f'Drafted batch {[e["case_index"] for e in batch]}',flush=True)
    print('Raw catalogue recorded. Development source review still required.',flush=True)

if __name__=='__main__': main()
