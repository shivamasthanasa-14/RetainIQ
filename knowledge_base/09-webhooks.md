# Webhook delivery guidance

Webhook triggers accept HTTPS JSON requests at the URL displayed in the trigger configuration. The sender must use the configured authentication method and required fields. Inspect Run history for validation errors. For delivery failures, collect timestamp, response status and a redacted payload. Do not share secret webhook URLs or keys. Duplicate events and uncertain delivery require technical investigation before replaying production events.
