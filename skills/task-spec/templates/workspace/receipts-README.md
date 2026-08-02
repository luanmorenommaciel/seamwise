# Receipts

Receipts are durable settlement evidence. A passing receipt binds a Task-Spec
and execution profile to the verification result that justified completion.

- Keep one canonical `<task-id>.json` receipt per settled task.
- Attempt receipts may be retained when they explain a failure or handoff.
- Never place credentials, raw model secrets, or unredacted environment dumps
  in a receipt.
- Do not rewrite historical receipts to satisfy newer validator preferences.
