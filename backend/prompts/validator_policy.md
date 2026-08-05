# Deterministic validation policy

Validation remains code-driven even when earlier stages use a language model. It checks:

1. Every cited event exists in the sanitized evidence ledger and uses the matching event type.
2. Every opted-in member receives one distinct perspective; opted-out or unknown players receive
   none and cannot be assigned quest objectives.
3. Concrete player, location, number, action, relationship, emotion, and motive claims stay within
   the validator's supported evidence and lexical rules.
4. Quest assignees, verification targets, metrics, and objectives are traceable to cited events.
5. Source verification and meaning confirmation remain separate and match the submitted v1.1
   review state exactly.
6. Weak, disputed, dismissed, or validation-failing inputs abstain instead of returning generated
   artifacts.

These checks are deterministic but do not prove the truth of arbitrary natural language. Lexical
claim checks are conservative prototype guardrails, and human review remains the authority for
source truth and personal meaning.
