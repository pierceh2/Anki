# Anki

## Question bank counts

The `Update question bank counts` GitHub Actions workflow records MKSAP's
completed-question count and AMBOSS's answered-question count by date. AMBOSS
history is separated by the bank name shown on its performance analysis page.
The scheduled run targets 8:45pm Eastern and adds a random delay of up to
30 minutes. Use `workflow_dispatch` to run it immediately.

Add these repository Actions secrets before enabling the workflow:

- `MKSAP_USERNAME`
- `MKSAP_PASSWORD`
- `AMBOSS_EMAIL`
- `AMBOSS_PASSWORD`