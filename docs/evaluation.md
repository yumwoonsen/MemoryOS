# Phase 1 evaluation

## Required checks

Score each generated result from 0 to 1 on four dimensions already represented in the validation
report:

| Dimension | Passing evidence |
|---|---|
| Specificity | Three or more anchors tied to this squad, match, location, or player roles |
| Evidence grounding | Every event reference resolves to the input Memory Pack |
| Perspective distinctness | Every opted-in teammate receives different role-specific content |
| Quest connection | Quest objectives cite and remix the discovered memory evidence |

## Golden cases

1. Confirmed chaos must become `ready` with four distinct perspectives.
2. Unconfirmed comeback must remain `needs_human_confirmation`.
3. Insufficient evidence must become `rejected` with no generated content.
4. Unknown players or duplicate events must fail at input validation.
5. Invented evidence or unsupported relationship labels must fail final validation.

## Prompt evaluation workflow

For any prompt or model change:

1. Run the full deterministic suite to protect contracts and guardrails.
2. Run every eligible fixture in OpenAI mode and save the JSON results outside the fixture folder.
3. Compare stage outputs against the four dimensions above.
4. Add a regression fixture for each new failure mode before changing the prompt.
5. Promote a model or prompt only when it improves specificity without reducing grounding.

Fluent prose alone is not a success criterion.

