import json
import os
import uuid
from datetime import date,timedelta
from pathlib import Path
import pandas as pd
import streamlit as st
from retainiq.ai import AIService
from retainiq.constants import OWNERS,STATUSES,LEGACY_OWNERS
from retainiq.dispatch import dispatch
from retainiq.groups import issue_groups,problem_description
from retainiq.imports import read_workbook,validate_records,import_records,template_bytes
from retainiq.knowledge import Knowledge
from retainiq.prepared import PreparedAI
from retainiq.reporting import report
from retainiq.scenarios import SCENARIOS,Workspaces,fingerprint
from retainiq.workflow import Workflow

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title='RetainIQ | RelayOps',page_icon='◈',layout='wide')
st.markdown('''<style>
[data-testid="stSidebar"]{background:#14243b;} [data-testid="stSidebar"] *{color:#edf3fc;}
[data-testid="stSidebar"] [role="combobox"], [data-testid="stSidebar"] [role="combobox"] *{color:#172b46 !important;}
[data-testid="stMetric"]{background:white;border:1px solid #e1e7ef;border-radius:12px;padding:17px;}
[data-testid="stMetricValue"]{font-size:30px;} .block-container{padding-top:3rem;max-width:1500px;}
[data-testid="stMetricLabel"] p{white-space:normal;overflow:visible;}
h1{letter-spacing:-.04em;font-size:2.1rem;} .eyebrow{color:#146d78;font-weight:700;font-size:12px;letter-spacing:.14em;}
</style>''',unsafe_allow_html=True)
if 'reviewer_session' not in st.session_state: st.session_state.reviewer_session=uuid.uuid4().hex
local=os.getenv('RETAINIQ_WORKSPACE_MODE','session')=='local'
manager=Workspaces(os.getenv('RETAINIQ_WORKSPACE_ROOT',str(ROOT)),'local' if local else st.session_state.reviewer_session)
with st.sidebar:
    st.title('◈ RetainIQ')
    st.caption('RELAYOPS · SUPPORT OPERATIONS')
    section=st.radio('Workspace',['Support Overview','Customer Issues & Responses','Needs Attention'])
    st.divider()
    actor=st.selectbox('Reviewing as',OWNERS,index=2)

    with st.expander('About this demo'):
        st.write('RelayOps and its customers are fictional. Prepared results are actual recorded Ollama outputs reviewed during development, with original outputs and corrections preserved. They are replayed, not newly inferred. Every response still needs per-ticket employee approval. No customer messages are sent.')
        st.write('Scenarios are isolated. Reset retains a recovery snapshot. Default reviewer sessions are private; local persistence is available through RETAINIQ_WORKSPACE_MODE=local.')
        st.caption('Local model: '+AIService().label)
st.markdown('<div class="eyebrow">RELAYOPS / CUSTOMER OPERATIONS</div>',unsafe_allow_html=True)
SAMPLES={'Normal Operations':'routine','Busy Support Period':'backlog','Complex Customer Requests':'complex'}
name=st.selectbox('Choose Sample Data',list(SAMPLES),key='scenario')
key=SAMPLES[name]
advanced=st.expander('Advanced Settings')
with advanced:
    mode=st.selectbox('Processing mode',['Prepared AI Demo Results','Live AI'])
    if st.session_state.pop('switch_to_custom',False): st.session_state['data_source']='Custom uploads'
    source=st.selectbox('Data workspace',['Scenario','Custom uploads'],key='data_source')
    st.caption('Prepared results replay reviewed local model outputs. Live AI processes new messages using the configured local model. No customer messages are sent.')
store=manager.open(key,custom=source=='Custom uploads')
store.migrate_owners()
ref=store.reference_date()
kb=Knowledge(ROOT/'knowledge_base')
prepared=PreparedAI(ROOT)
workflow=Workflow(store,prepared if mode=='Prepared AI Demo Results' else AIService(),kb)
st.caption(f'{name} · Reporting as of {ref}' + (' · Uploaded requests' if source=='Custom uploads' else ''))
live_ready=True
if mode=='Live AI' or source=='Custom uploads':
    live_ready,availability=AIService().availability()
    if live_ready: st.caption(availability)
    else: st.warning(availability)
def action(fn,text,refresh=False):
    try:
        value=fn()
        if refresh:
            st.session_state['notice']=text
            st.rerun()
        st.success(text)
        return True if value is None else value
    except Exception as error:
        st.error(str(error))
        return None
if 'notice' in st.session_state: st.success(st.session_state.pop('notice'))
with advanced:
    cols=st.columns([3,1])
    with cols[0]:
        st.caption('Imports go to this scenario’s separate Custom uploads workspace. Canonical scenarios remain intact. Custom uploads use today as the reporting reference.')
        path=ROOT/'data'/'RetainIQ_Import_Template.xlsx'
        st.download_button('Download Excel Template',path.read_bytes() if path.exists() else template_bytes(),file_name='RetainIQ_Import_Template.xlsx')
        upload=st.file_uploader('Upload Completed File',type=['xlsx'],key='upload_'+key)
        if upload:
            target=manager.open(key,custom=True)
            try:
                records=read_workbook(upload.getvalue())
                preview,errors=validate_records(target,records)
                st.dataframe(pd.DataFrame(preview),hide_index=True,width='stretch')
                for error in errors: st.error(error)
                if not errors:
                    st.success(f'{len(preview)} valid records. Nothing imported yet.')
                    if any(r['operation']=='update' for r in preview):
                        st.warning('Updates supersede old drafts and reset processing; original values stay in history. received_at cannot change.')
                        st.dataframe([target.ticket(r['ticket_id']) for r in preview if r['operation']=='update'],hide_index=True)
                    checked=st.checkbox('I reviewed the import preview',key='import_check_'+key)
                    if st.button('Confirm Import',disabled=not checked):
                        if action(lambda:import_records(target,records,actor),'Import persisted in Custom uploads.'):
                            st.session_state['switch_to_custom']=True
                            st.rerun()
            except Exception as error: st.error('Validation failed: '+str(error))
    with cols[1]:
        checked=st.checkbox('Restore selected scenario to its original state',key='reset_check_'+key)
        if st.button('Reset Scenario',disabled=not checked):
            action(lambda:manager.reset(key),'Scenario restored; a recovery snapshot was saved.',True)
if source=='Scenario' and any(t['processing_status'] in {'Pending AI','AI Failed'} for t in store.tickets()):
    prepared.load(store,kb,'Support Lead')
st.title(section)
tickets=[t for t in store.tickets() if date.fromisoformat(t['received_at'][:10])<=ref]
suffix=key+'_'+source
TABLE_LABELS={'ticket_id':'Ticket ID','customer':'Customer','subject':'Request','received_at':'Received','category':'Category','processing_status':'Preparation','owner':'Owner','status':'Status','attention_reason':'Reason for attention','summary':'Summary'}
def select(rows,label,widget):
    if not rows:
        st.info('No requests in this view.')
        return None
    lookup={t['ticket_id']:t for t in rows}
    tid=st.selectbox(label,list(lookup),format_func=lambda x:x+' · '+lookup[x]['subject'],key=widget+'_'+suffix)
    return lookup[tid]
def message(ticket):
    st.subheader(ticket['subject'])
    st.caption(f"{ticket['ticket_id']} · {ticket['customer']} · {ticket['status']} · {ticket['owner'] or 'Unassigned'}")
    with st.container(border=True): st.text(ticket['message'])
    if ticket['summary']: st.write('Summary: '+ticket['summary'])
def history(ticket):
    with st.expander('What Has Happened'):
        for event in sorted(store.history(ticket['ticket_id']),key=lambda e:(e['created_at'],e['id'])):
            detail=json.loads(event['detail'])
            actor_name=LEGACY_OWNERS.get(event['actor'],event['actor'])
            event_name={'Scenario intake':'Customer request received','Classified':'Customer problem identified','Prepared historical classification loaded':'Previous request categorized','Draft created':'Suggested response prepared','Follow-up updated':'Next step updated'}.get(event['action'],event['action'])
            st.markdown(f"**{event_name}** · {actor_name} · {event['created_at'][:16].replace('T',' ')}")
            if isinstance(detail,dict):
                readable=[]
                for field,value in detail.items():
                    if field.lower() in {'provider','fingerprint','draft_id','dispatch_id','generated_at','request_hash','sources','revision','case_index','fixture_category','fixture_metadata_is_not_ai','origin','source_ids'}: continue
                    if value in ('',None,[]): continue
                    if isinstance(value,dict):
                        value='; '.join(f"{k.replace('_',' ').title()}: {v}" for k,v in value.items() if v not in ('',None,[]) and k in {'customer','subject','message','status','owner','follow_up','due_date','resolution_notes','category','summary','reason','missing_information'})
                    elif isinstance(value,list): value='; '.join(str(v) for v in value)
                    value=str(value)
                    for old,new in LEGACY_OWNERS.items(): value=value.replace(old,new)
                    if value: readable.append({'before':'Previously','after':'Updated to','result':'Assessment'}.get(field,field.replace('_',' ').title())+': '+value)
                if readable: st.write(' • '.join(readable))
            elif detail: st.write(str(detail))

def attention(ticket):
    if ticket['status']=='Resolved': return ''
    reasons=[]
    if ticket['status']=='Escalated': reasons.append('Escalated')
    if ticket['processing_status'] in {'Needs Review','AI Failed'} or ticket['attention_reason']:
        reasons.append(ticket['attention_reason'] or 'Manual review required')
    if ticket['due_date'] and ticket['due_date']<ref.isoformat(): reasons.append('Overdue follow-up')
    if ticket['follow_up'].strip() and ticket['follow_up'].strip() not in {'Check customer context and prepare a response','Review and approve draft'}: reasons.append(ticket['follow_up'])
    return ' · '.join(dict.fromkeys(reasons))

def update_request(ticket,context):
    st.markdown('**Next Step**')
    st.write(ticket['follow_up'] or ticket['attention_reason'] or 'Review the request and agree a next step.')
    st.caption(f"Responsible: {ticket['owner'] or 'Unassigned'} · Deadline: {ticket['due_date'] or 'Not set'}")
    with st.expander('Update Request',expanded=context=='attention'):
        with st.form('follow_'+context+'_'+suffix+'_'+ticket['ticket_id']):
            cols=st.columns(3)
            owner=cols[0].selectbox('Assigned owner',OWNERS,index=OWNERS.index(ticket['owner']) if ticket['owner'] in OWNERS else 0)
            due=cols[1].date_input('Due date',date.fromisoformat(ticket['due_date']) if ticket['due_date'] else ref+timedelta(days=1))
            status=cols[2].selectbox('Current status',STATUSES,index=STATUSES.index(ticket['status']))
            follow=st.text_area('Required follow-up',ticket['follow_up'])
            notes=st.text_area('Resolution notes',ticket['resolution_notes'])
            if st.form_submit_button('Save follow-up',type='primary'):
                action(lambda:workflow.follow_up(ticket['ticket_id'],owner,follow,due.isoformat(),status,notes,actor),'Follow-up and activity history saved.',True)

def escalate(ticket,context):
    with st.expander('Escalate / manual review'):
        owner=st.selectbox('Responsible owner',OWNERS,index=OWNERS.index(ticket['owner']) if ticket['owner'] in OWNERS else 2,key='owner_'+context+'_'+ticket['ticket_id'])
        reason=st.text_area('Reason and next step',ticket['attention_reason'],key='reason_'+context+'_'+ticket['ticket_id'])
        if st.button('Escalate Ticket',disabled=ticket['status']=='Escalated' or not reason.strip(),key='esc_'+context+'_'+ticket['ticket_id']):
            action(lambda:workflow.escalate(ticket['ticket_id'],owner,reason,actor),'Escalation saved. Continue in Needs Attention.',True)
def review(ticket,group):
    drafts=store.draft(ticket['ticket_id'])
    d=drafts[0] if drafts and drafts[0]['ticket_revision']==ticket['revision'] else None
    if d and d['status'] in {'Draft','Approved'}:
        st.subheader('Suggested response' if d['status']=='Draft' else 'Approved response')
        body=st.text_area('Response draft',d['body'],height=180,key=f"body_{suffix}_{d['id']}_{d['body'][:16]}",disabled=d['status']!='Draft')
        with st.expander('Relevant knowledge-base sources',expanded=True):
            for doc in json.loads(d['sources']):
                st.markdown('**'+doc['title']+'**')
                st.text(doc['text'])
        if json.loads(d['missing']): st.warning('Missing information: '+'; '.join(json.loads(d['missing'])))
        checked=st.checkbox('I checked this customer’s context and every claim against the sources',key='checked_'+ticket['ticket_id'])
        buttons=st.columns(3)
        if buttons[0].button('Save Edits',disabled=d['status']!='Draft',key='edit_'+ticket['ticket_id']):
            action(lambda:workflow.edit_draft(d['id'],body,actor),'Response edited; original draft preserved.',True)
        if buttons[1].button('Approve Response',type='primary',disabled=d['status']!='Draft' or ticket['status'] in {'Escalated','Resolved'} or not checked or body!=d['body'],key='approve_'+ticket['ticket_id']):
            action(lambda:workflow.approve(d['id'],actor),'Approved for export; ticket remains unresolved. No message sent.',True)
        reason=st.text_input('Reason if rejecting',key='reject_reason_'+ticket['ticket_id'])
        if buttons[2].button('Reject Draft',disabled=d['status']!='Draft' or not reason.strip(),key='reject_'+ticket['ticket_id']):
            action(lambda:workflow.reject(d['id'],reason,actor),'Response rejected; human attention required.',True)
        if body!=d['body']: st.caption('Save edits before approval.')
        if d['status']=='Approved':
            st.success(f"Approved by {d['approved_by']} at {d['approved_at']}")
            st.download_button('Export approved response',d['body'],file_name=ticket['ticket_id']+'_approved.txt')
        if group['Suggested Handling']=='Standard documentation':
            with st.expander('Reusable response review'):
                st.caption('Review once for the group; context checks and approval still apply to each ticket.')
                if st.button('Save reviewed reusable response',disabled=not checked):
                    action(lambda:workflow.review_template(group['key'],d['id'],body,actor),'Reusable response reviewed; no ticket approved.')
                templates=store.query('SELECT * FROM response_templates WHERE group_key=? ORDER BY id DESC LIMIT 1',(group['key'],))
                if templates and st.button('Apply reusable response to this ticket',disabled=d['status']!='Draft'):
                    action(lambda:workflow.apply_template(ticket['ticket_id'],templates[0]['id'],group['key'],actor),'Response applied. Check this ticket before approval.',True)
    elif ticket['processing_status']=='Processed' and ticket['status'] not in {'Escalated','Resolved'}:
        if st.button('Prepare response draft'):
            with st.spinner('Drafting from company documentation…'): action(lambda:workflow.prepare_draft(ticket['ticket_id'],actor),'Preparation finished.',True)
    elif ticket['status']!='Resolved': st.info('Individual review or processing is required before response approval.')

if section=='Support Overview':
    period=st.segmented_control('Reporting period',['Last 7 Days','Last 30 Days','All Time'],default='Last 7 Days') or 'Last 7 Days'
    r=report(store,period)
    for col,(label,value) in zip(st.columns(4),r['metrics'].items()):
        col.metric(label,value)
        if r['comparisons'] is not None:
            delta=r['comparisons'][label]
            col.caption(('up '+str(delta) if delta>0 else 'down '+str(-delta) if delta<0 else 'unchanged')+' vs previous '+('7 days' if period=='Last 7 Days' else '30 days'))
    st.caption(f"Reporting {r['start']} to {r['reference']}. Open and overdue use the period-end cutoff. All Time has no prior-period comparison.")
    weeks=pd.DataFrame(r['weeks']).set_index('Week')
    left,right=st.columns(2)
    with left:
        st.subheader('Weekly Support Activity')
        if r['metrics']['Requests Received'] or r['metrics']['Requests Resolved']:
            st.line_chart(weeks[['Incoming','Resolved']],color=['#146d78','#8cabc8'],height=230)
        else: st.info('No incoming or resolved requests in this period.')
    with right:
        st.subheader('Open Ticket Trend')
        if any(w['Open Requests'] for w in r['weeks']): st.line_chart(weeks[['Open Requests']],color='#146d78',height=230)
        else: st.info('No unresolved backlog in this period.')
    left,right=st.columns([2,1])
    with left:
        st.subheader('Most Common Customer Problems')
        if r['categories']: st.bar_chart(pd.Series(r['categories']).sort_values(),horizontal=True,color='#587a9d',height=230)
        else: st.info('No received requests in this period.')
    with right:
        st.subheader('Current Workload')
        st.dataframe(pd.DataFrame([{'Status':k,'Requests':v} for k,v in r['distribution'].items()]),hide_index=True,width='stretch')
elif section=='Customer Issues & Responses':
    st.caption('Review recurring problems and documented responses. Check each customer’s context before approval. No messages are sent.')
    period=st.segmented_control('Reporting period',['Last 7 Days','Last 30 Days','All Time'],default='Last 7 Days',key='issues_period') or 'Last 7 Days'
    r=report(store,period)
    rows=[t for t in tickets if r['start']<=t['received_at'][:10]<=r['reference']]
    st.caption(f"{len(rows)} requests received from {r['start']} to {r['reference']}")
    if source=='Custom uploads':
        eligible=[t for t in tickets if t['processing_status'] in {'Pending AI','AI Failed'} and t['status']!='Resolved']
        if eligible:
            ready,availability=AIService().availability()
            if not ready: st.warning('Live AI unavailable. New messages need manual review until the local model is available. '+availability)
            if st.button('Process New Requests',disabled=not ready,type='primary'):
                live_workflow=Workflow(store,AIService(),kb)
                with st.spinner('Processing new customer messages with local live AI…'):
                    for ticket in eligible[:5]:
                        if live_workflow.process(ticket['ticket_id'],actor)=='Processed':
                            action(lambda t=ticket:live_workflow.prepare_draft(t['ticket_id'],actor),'Response prepared.')
                st.session_state['notice']='Processed up to five new requests. Review each response before approval.'
                st.rerun()
            st.caption('Processes up to five new requests per click.')
    problems={}
    for ticket in rows:
        problem=ticket['issue_group'] or ticket['category'] or 'Uncategorized request'
        problems.setdefault(problem,[]).append(ticket)
    choices=[]
    for problem,members in sorted(problems.items(),key=lambda item:(-len(item[1]),item[0])):
        responses={}
        exceptions=[]
        for ticket in members:
            if ticket['status']!='Resolved' and (ticket['status']=='Escalated' or ticket['processing_status'] in {'Needs Review','AI Failed','Pending AI'} or ticket['attention_reason']):
                exceptions.append(ticket)
            drafts=store.draft(ticket['ticket_id'])
            current=drafts[0] if drafts and drafts[0]['ticket_revision']==ticket['revision'] and drafts[0]['status'] in {'Draft','Approved'} else None
            if current:
                body=current['body']; docs=json.loads(current['sources'])
            else:
                # Read existing reviewed results for historical requests; never infer here.
                try:
                    docs=kb.retrieve(ticket['subject']+' '+ticket['message'])
                    recorded=prepared.draft(ticket,docs)
                    if not recorded['supported']: continue
                    body=recorded['body']
                    docs=[d for d in docs if d['id'] in recorded['source_ids']]
                except Exception:
                    continue
            if body.strip():
                response=responses.setdefault(body,{'subjects':[],'docs':docs})
                if ticket['subject'] not in response['subjects']: response['subjects'].append(ticket['subject'])
        handling='Needs Investigation' if not responses or len(exceptions)==len(members) else 'Review Reply' if exceptions or len(responses)>1 else 'Standard Reply'
        choices.append({'problem':problem,'tickets':members,'responses':responses,'exceptions':exceptions,'handling':handling})
    if not choices:
        st.info('No customer requests in this period.')
    else:
        table=pd.DataFrame([{'Customer Problem':g['problem'],'Number of Requests':len(g['tickets']),'Recommended Handling':g['handling']} for g in choices])
        selection=st.dataframe(table,hide_index=True,width='stretch',on_select='rerun',selection_mode='single-row',key='problem_table_'+suffix+'_'+period)
        st.caption('Select a row to see the recommended handling.')
        selected=selection.selection.rows
        group=choices[selected[0] if selected and selected[0]<len(choices) else 0]
        st.subheader(group['problem'])
        st.markdown('**What customers are asking about**')
        subjects=list(dict.fromkeys(t['subject'] for t in group['tickets']))
        st.write(problem_description(group['problem'],group['tickets']))
        st.markdown('**Recommended handling: '+group['handling']+'**')
        if group['handling']=='Standard Reply':
            st.write('A documented reply is available. Check the customer’s situation before approving it.')
        elif group['handling']=='Review Reply':
            st.write('Customer situations differ. Use the relevant reply and review each request individually.')
        else:
            st.write('A support employee needs to investigate before an appropriate reply can be approved.')
        if group['exceptions']:
            reasons=list(dict.fromkeys(t['attention_reason'] or t['follow_up'] or 'Information or investigation needed' for t in group['exceptions']))
            st.warning(f"{len(group['exceptions'])} requests need individual attention: "+'; '.join(reasons[:3]))
        if group['responses']:
            st.markdown('**Suggested response**' if len(group['responses'])==1 else '**Distinct suggested responses**')
            for body,response in group['responses'].items():
                if len(group['responses'])>1: st.markdown('**'+ ' / '.join(response['subjects'])+'**')
                st.write(body)
                st.caption('Based on: '+', '.join(dict.fromkeys(doc['title'] for doc in response['docs'])))
        else:
            st.info('No documented response is available for this problem. Review the request and agree the next step.')
        if st.checkbox('View customer requests',key='view_requests_'+suffix+'_'+period+'_'+group['problem']):
            lookup={t['ticket_id']:t for t in group['tickets']}
            tid=st.selectbox('Open customer request',[None]+list(lookup),format_func=lambda value:'Choose a customer request' if value is None else lookup[value]['customer']+' · '+lookup[value]['subject']+' · '+value,key='open_request_'+suffix+'_'+period+'_'+group['problem'])
            if tid:
                ticket=lookup[tid]
                message(ticket)
                if ticket['attention_reason']: st.warning(ticket['attention_reason'])
                missing=json.loads(ticket['missing_information'])
                if missing: st.write('Information needed: '+'; '.join(missing))
                individual_group=next((g for g in issue_groups([ticket])),{'key':group['problem'],'Suggested Handling':'Individual review'})
                review(ticket,individual_group)
                if ticket['status']!='Resolved': escalate(ticket,'selected_request')
                history(ticket)
elif section=='Needs Attention':
    st.caption('Escalations, manual reviews, overdue follow-ups and specific outstanding actions.')
    rows=[t for t in tickets if attention(t)]
    st.dataframe(pd.DataFrame([{'Customer':t['customer'],'Problem':t['issue_group'] or t['subject'],'Reason attention is needed':attention(t),'Assigned owner':t['owner'],'Due date':t['due_date'],'Status':t['status']} for t in rows],columns=['Customer','Problem','Reason attention is needed','Assigned owner','Due date','Status']),hide_index=True,width='stretch')
    ticket=select(rows,'Select request','attention_ticket')
    if ticket:
        st.markdown('**Customer Message**')
        message(ticket)
        history(ticket)
        update_request(ticket,'attention')

