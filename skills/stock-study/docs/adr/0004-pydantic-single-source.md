# ADR-0004 · Pydantic v2 as Single Schema Source

**Status**: Accepted (2026-05-25)
**Decider**: 王选策, 陈夏童, 张涛

## Context

Cross-component data contracts (DataResponse, FactorVector, StockScore, NarrativeResult, etc.) are touched by 5 engineers across 4 weeks of sprint. Without a single source of truth, we end up with proto3 here, JSON Schema there, hand-rolled dataclass over there, and they drift.

## Decision

1. **All cross-component contracts live in `schemas/` as Pydantic v2 `BaseModel`s.**
2. **`model_config = ConfigDict(extra="forbid", frozen=True)`** on every output / contract model. `extra="forbid"` catches drift; `frozen=True` enforces immutability.
3. **No proto3, no hand-rolled `@dataclass` for cross-component data.** Internal-to-one-file dataclasses are fine.
4. **Tool input schemas also use Pydantic** (registered with `safety.tool_guard.register_tool`).
5. **JSON schemas are auto-derived** via `Model.model_json_schema()` when sending to Anthropic tool_use API.

## Consequences

**Positive**
- One place to find every contract
- Type checking via mypy works
- Anthropic tool_use API gets free JSON schemas from Pydantic
- `extra="forbid"` catches LLM hallucinating field names
- Migration story: add a `_version: int` field if we ever evolve

**Negative**
- All teammates need basic Pydantic v2 literacy
- Slightly slower runtime than raw dicts (irrelevant at our scale)

## Conventions

- Use `Literal[...]` for closed enums (e.g. `Label`, `Regime`).
- Use `Field(pattern=...)` for ticker / date format validation.
- Use `Field(ge=, le=)` for numeric ranges.
- Use `Field(min_length=, max_length=)` for text fields.
- Computed properties (e.g. `FactorAttribution.top_two`) live as `@property` methods.

## Alternatives Considered

1. **proto3** — rejected (overkill, no Python ergonomics, no auto-JSON-schema for LLM tool_use)
2. **dataclasses + cattrs** — rejected (less native LLM-tool-use integration)
3. **TypedDict** — rejected (no runtime validation)

## References

- `schemas/__init__.py`
- `README.md` D3
- `tier2/tools/xt_tools.py` (uses `Model.model_json_schema()` for Anthropic tool_use)
