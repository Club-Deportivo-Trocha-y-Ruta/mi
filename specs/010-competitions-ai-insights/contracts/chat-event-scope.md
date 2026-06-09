# Contract: Chat event scoping (additive extension)

## POST /api/race-analysis/chat — extended request

```json
{
  "session_id": "uuid-v4 (client-generated, ≤64 chars)",
  "query": "¿Quién mejoró más respecto a Ginebra?",
  "athlete_id": null,
  "race_event_id": 42        // NEW, optional
}
```

Response (unchanged shape):
```json
{ "answer": "…", "citations_used": ["…"], "tools_called": ["…"] }
```

Rules:
- `race_event_id` omitted/null → behavior identical to today (backward compatible; existing clients unaffected).
- `race_event_id` set → `RaceChatAgent` tools constrain insight/result retrieval to that event (and its season for comparatives); the session seed includes the event label so answers ground on "esta válida".
- `athlete_id` and `race_event_id` may combine (athlete within event).
- Unknown `race_event_id` → 404. Roles `coach | admin`; `AI_ENABLED` gated (503 when off). Privacy: same anonymization/no-prompt-logging guarantees as existing chat.

## Frontend consumer
- `CompetitionChatPanel` (`src/components/competitions/chat/CompetitionChatPanel.tsx`): generates one `session_id` per mounted competition, calls existing `chatTurn()` with `race_event_id`; renders `ChatMessage[]` locally (no persistence — sessions are in-memory server-side, 1h TTL). Disabled state with es-CO copy when AI unavailable (FR-010, User Story 5 scenario 2).
