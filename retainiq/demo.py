import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .imports import import_records, template_bytes

CUSTOMERS = ['Northstar Labs', 'Juniper Logistics', 'Beacon Analytics', 'Atlas Supply', 'Cedar Studio', 'Mosaic Health Demo', 'Harbor Systems', 'Lumen Works']
DOCUMENTS = {
'01-getting-started': ('Getting started with RelayOps', 'RelayOps automates business workflows using triggers and actions. Create a workspace, invite teammates, connect an integration, then build a draft workflow. Test it with sample data before publishing. Only published workflows run automatically. Workspace settings are available to Admins and Owners.'),
'02-account-permissions': ('Account access and permissions', 'Workspace roles are Owner, Admin, Editor and Viewer. Owners manage billing and transfer ownership. Admins invite users from Settings > Members > Invite and select their role. Editors create and edit workflows but cannot manage billing or members. Viewers can inspect workflows and run history but cannot edit. An Admin or Owner can change roles in Settings > Members. Invitations expire after seven days; resend expired invitations from Members.'),
'03-sign-in': ('Sign-in troubleshooting', 'Use the same email address used for the invitation. For password-based accounts, use Forgot password on the sign-in page and check spam for the reset link. Links expire after 30 minutes. If the account uses company SSO, ask the company identity administrator to check access. Do not request passwords or authentication codes. If access still fails, collect the workspace name, timestamp and exact error text for technical support.'),
'04-billing': ('Subscription and billing policies', 'Subscriptions are billed monthly or annually according to the signed order. Owners can download invoices and update payment details in Settings > Billing. Support cannot promise refunds, discounts or credits. Refund, cancellation and contract-change requests go to the billing specialist for review against the customer agreement. Do not quote pricing without the applicable agreement. A failed payment notification should be reviewed by the workspace Owner.'),
'05-workflow': ('Workflow configuration', 'A workflow consists of one trigger followed by actions. Editors and Admins can create workflows from Workflows > New workflow. Add the trigger, map required fields, then add actions. Save as Draft and use Test with sample data. Review test results in Run history before selecting Publish. Pausing a published workflow stops new runs; existing runs may continue. Do not publish a workflow until its test succeeds.'),
'06-conditions': ('Conditions and field mapping', 'Use a condition step to send records down different branches. A condition compares an input field to a chosen value. Map action inputs to fields returned by the trigger or preceding steps. Required fields must be present. Test each branch with sample records, including empty values. If fields are missing, refresh the sample from the trigger and remap inputs. Complex branching design can be reviewed by support.'),
'07-slack': ('Slack integration troubleshooting', 'A workspace Admin connects Slack from Settings > Integrations > Slack. Authorize the intended Slack workspace and invite the RelayOps app to the destination channel. Private channels require an explicit app invitation. If authentication expires, reconnect Slack and test the action. For permission errors, collect the error text, channel type and last successful run time. Do not post access tokens in support messages.'),
'08-salesforce': ('Salesforce integration troubleshooting', 'Connect Salesforce with a dedicated authorized integration user. Confirm that user can access the target object and required fields. For INVALID_SESSION_ID, reconnect Salesforce from Settings > Integrations and test a single sample record. For field permission errors, ask the Salesforce administrator to verify object and field access. For repeated failures, collect run IDs, error text, last successful run time and scope of impact. Bulk replay, lost data recovery and production outages require engineering review; support must not promise a fix or recommend blind replay.'),
'09-webhooks': ('Webhook delivery guidance', 'Webhook triggers accept HTTPS JSON requests at the URL displayed in the trigger configuration. The sender must use the configured authentication method and required fields. Inspect Run history for validation errors. For delivery failures, collect timestamp, response status and a redacted payload. Do not share secret webhook URLs or keys. Duplicate events and uncertain delivery require technical investigation before replaying production events.'),
'10-errors': ('Run errors and troubleshooting', 'Open Workflows > Run history and select the failed run. Record the workflow name, run ID, timestamp, failing step and exact error. Check required field mappings and integration permissions. A single test can help isolate the failing step. Do not retry large batches or delete data as a general fix. Repeated production failures, possible data loss or business-critical outages must be escalated to engineering.'),
'11-onboarding': ('Customer onboarding checklist', 'Agree on the first workflow and appoint a workspace Owner and an operational contact. Invite the team with the minimum required roles. Connect a test integration, build a sample workflow and validate sample results before publishing. The support team can arrange an onboarding session; ask for workspace name, intended use case and two preferred time windows. Do not promise a specific appointment until confirmed.'),
'12-escalation': ('Specialist escalation procedure', 'Escalate production outages, possible data loss, security incidents and unresolved integration errors. Assign engineering for production incidents, technical support for integration investigation and billing for contract decisions. Record business impact, affected workflow, time of onset, redacted error and last successful run. A human owner decides mitigation and next update time. Never promise recovery or a service-level deadline without a confirmed agreement. Security reports must avoid transmitting secrets.'),
}

# Curated message variants; no synthetic classification is stored as model output.
REQUESTS = [
('Inviting our ops lead', 'Hi team, I need to add our operations lead. She should edit workflows, but not touch invoices. Where do I send the invite?'),
('Viewer access', 'Can our finance analyst see run history without changing the workflow? I am the workspace admin and want to keep permissions narrow.'),
('Invite expired', 'The invite from last week says it expired. Do I need to remove my colleague and start over, or can I resend it?'),
('Unable to sign in', 'I am getting an expired password reset link. I requested it yesterday. What should I do next?'),
('SSO loop', 'Our login keeps returning to the company SSO page. We moved teams yesterday. Who should check the access?'),
('Invoice copy', 'Morning — our accountant needs the latest invoice. I am the workspace Owner. Where can I download it?'),
('Card changed', 'We have a new company payment card. Can I update it myself? I have Owner access.'),
('Refund request', 'We paid annually but are closing this department. Please refund the unused months. Can someone review our agreement?'),
('Change contract', 'We need a custom renewal discount and different payment terms. Could billing look at this before Friday?'),
('First workflow', 'I have a trigger and two actions saved. Does saving start the workflow, or do I need to publish it after testing?'),
('Pause automation', 'We are doing maintenance tomorrow. How do I stop new runs for a few hours without deleting the workflow?'),
('Field missing', 'The action wants a customer reference but I cannot see it in the mapping picker. The trigger sample is old. How should I refresh it?'),
('Branches', 'We want orders over a certain amount to go to one action and the rest to another. How do condition steps work?'),
('Slack private channel', 'The Slack action works for a public channel but fails for our private ops channel. Do we need to invite the app?'),
('Slack authentication', 'Slack says authentication expired after our admin changed accounts. What is the supported way to reconnect?'),
('Salesforce session error', 'One test run returned INVALID_SESSION_ID from Salesforce. No production impact yet. Should I reconnect the integration?'),
('Salesforce outage', 'URGENT: every production Salesforce sync is failing and orders have stopped. We may have lost records. Can you investigate before anyone replays the queue?'),
('Field permission error', 'Our Salesforce integration user cannot write to a custom field. Which permissions should our administrator check?'),
('Webhook format', 'We are configuring a webhook trigger. Does it expect JSON, and where can I find the endpoint?'),
('Duplicate webhook events', 'The same order appears twice after a webhook timeout. We cannot tell whether delivery succeeded. Please investigate before we replay anything.'),
('Failed run details', 'Support asked for a run ID. Where do I find the failing step and error details?'),
('Error, not sure where', 'It is broken again. I cannot remember which workflow. Can someone help me figure out what details you need?'),
('Onboarding session', 'We have just created a workspace for our operations team. Can we arrange a session to plan the first workflow?'),
('Getting started', 'Thanks for setting up our account. What should we do first before switching on our first workflow?'),
('Data loss concern', 'After a failed production run we cannot find several customer records. We need a person to review this. Please do not retry the batch yet.'),
('Security concern', 'An unfamiliar user appears in our members list. We suspect unauthorized access. Please have a specialist contact our workspace owner.'),
('Unsupported feature', 'Can RelayOps automatically translate handwritten scanned contracts into Japanese and sign them for us? We cannot find this documented.'),
('Pricing question', 'What would a special unlimited enterprise plan cost? We have not signed an order yet and need a binding quote.'),
('New team member', 'Hello, our new analyst only needs to read workflow history. Is Viewer the right role?'),
('Test before publish', 'I am nervous about our first live automation. What should I check in the test run before publishing?'),
('Missing integration details', 'The integration failed this morning but I do not have the exact error. What information would help your technical team?'),
('Production errors', 'All scheduled production runs are failing since 09:00. This blocks fulfilment for our biggest customer. We need engineering assistance.'),
]

def initialize(root, store):
    root = Path(root)
    kb = root / 'knowledge_base'
    kb.mkdir(exist_ok=True)
    for key, (title, text) in DOCUMENTS.items():
        path = kb / (key + '.md')
        if not path.exists():
            path.write_text('# ' + title + '\n\n' + text + '\n', encoding='utf-8')
    template = root / 'data' / 'RetainIQ_Import_Template.xlsx'
    if not template.exists():
        template.parent.mkdir(exist_ok=True)
        template.write_bytes(template_bytes())
    if store.tickets():
        return
    rng = random.Random(41)
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30)
    records = []
    for i in range(100):
        subject, body = REQUESTS[i % len(REQUESTS)]
        customer = CUSTOMERS[rng.randrange(len(CUSTOMERS))]
        intro = ['', 'Hi RelayOps,\n\n', 'Following up from our team: ', 'Quick question from operations. '][rng.randrange(4)]
        suffix = ['', '\n\nThanks for your help.', '\nOur workspace is ' + customer + '.', '\nHappy to provide more details if useful.'][rng.randrange(4)]
        records.append({'ticket_id': f'RLY-{i+1:04}', 'customer': customer, 'received_at': (base + timedelta(hours=i*7)).isoformat(),
                        'subject': subject, 'message': intro + body + suffix})
    import_records(store, records, 'Demo data initialization')
