# RetainIQ — automating support preparation

RelayOps is a simulated 20-person B2B workflow automation startup. Its support employees repeatedly read requests, identify the issue, look up company documentation, write an initial reply, decide who should investigate and track the next action.

RetainIQ turns that preparation into an inspectable operational workflow: choose a support dataset → understand workload → process requests → group similar problems → draft from documentation or flag an exception → employee review → assigned follow-up → resolution.

## Business and implementation decisions

The tool concentrates work into three pages. Support Overview answers how much work arrived, how much was resolved and what remains overdue. AI Processing & Review brings language interpretation, issue grouping, source inspection and response decisions together. Follow-up Tracker keeps unresolved cases assigned and visible.

The model interprets each request and returns a category, specific handling group, summary, missing context and specialist decision. Grouping uses that model-understood handling label, separated into standard documentation and individual review. Password reset and company SSO investigation therefore remain distinct even though both involve account access. Python validates output, retrieves documents with TF-IDF, assigns neutral owner identifiers and enforces review and state transitions. There is no predictive score or autonomous agent framework.

Drafts are based on a twelve-document fictional knowledge base. Unsupported answers are rejected or escalated. Employees inspect the original message and cited documents, edit wording, reject unsuitable replies or approve a specific ticket. A reviewed reusable response can reduce repeated wording review, but it neither approves tickets nor resolves them. Context and source checks remain per-ticket responsibilities.

## Scenario design

Each reproducible scenario contains 100 customer requests over eight operating weeks, using reference date 30 September 2026. Routine Operations has greater resolution throughput and recurring documented questions. Growing Support Backlog increases incoming demand across the period while more requests remain unresolved. Complex Customer Issues contains more integration incidents, security concerns, unclear requests and unsupported capabilities.

Ticket dates, resolution dates, due dates and status events drive the dashboard. Last 7 Days and Last 30 Days compare against the immediately preceding equivalent window. Open and overdue counts are snapshots at each cutoff; lifecycle events preserve historical results after resolution, reopening or deadline changes. All Time omits the prior-period comparison.

## An interactive portfolio without mandatory model setup

Prepared AI Demo Results replays genuine recorded local Ollama outputs. Repeated messages reuse an exact subject-and-message content-hash cache. The catalogue retains the input, model, generation timestamp, raw classification, raw draft, retrieved documents and development-review notes. Development review is performed by the build operator using Codex; it is distinct from an employee’s approval in the interface. There is no claim that cached outputs represent fresh inference or independent human evaluation.

Live AI uses the existing Ollama integration for new or changed messages. Custom inputs without an exact reviewed catalogue entry are never assigned invented prepared results. An unavailable provider leaves a retry/manual-review path. Every visitor can use a separate SQLite reviewer workspace; local mode persists one workstation workspace across browser sessions. Imports are isolated from canonical scenario files. Reset affects only the selected scenario and saves the prior workspace as a recovery snapshot.

## Operational value and limits

The automated preparation reduces repeated reading, initial categorization, document search and first-draft writing. Employees remain responsible for context, policy interpretation, production investigation, approval and resolution. No measured manual baseline was collected, so no time-saving percentage, financial impact or hours-saved figure is claimed.

This is an internal portfolio demonstration, with demonstration owner selection rather than production authentication. It has no public deployment, outbound customer email or real customer credentials. See the verification report for actual tests, observed model behavior, screenshots and measured run times.
