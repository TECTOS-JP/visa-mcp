# Changelog

## v0.4.0 — Safety hardening

This release responds to external code review identifying critical safety
bypass paths and stability concerns. All P0 items from the review are
addressed.

### Breaking changes

- **Default safety mode changed from `advisory` to `strict`.**
  LLM-driven operation is the primary use case, so the conservative default
  is more appropriate. Users who relied on advisory behaviour must now
  explicitly set `VISA_MCP_SAFETY_MODE=advisory`.
- **`send_command` / `query_instrument` removed by default.** Raw SCPI
  passthrough is now opt-in via `VISA_MCP_ENABLE_RAW_COMMANDS=1` and is
  renamed to `unsafe_send_command` / `unsafe_query_instrument`. In `strict`
  mode these are never registered, regardless of the environment variable.

### Security / Safety

- **Per-resource `asyncio.Lock`** in `VisaManager`. Concurrent calls to the
  same VISA resource are now serialised; different resources continue to run
  in parallel. Prevents packet interleaving and response misattribution when
  an LLM issues multiple tool calls concurrently.
- **Dangerous keyword detection** for raw SCPI commands. Commands containing
  `VOLT`, `CURR`, `OUTP`, `SOUR`, `CONF`, `FUNC`, `RANG`, `*RST`, `*CLS`,
  `*SAV`, `INIT`, `TRIG`, `MEM`, `STOR`, `RECALL` (and not containing `?`)
  are flagged and require `override_safety=True` + `override_reason`.
- **Startup warning** when `VISA_MCP_SAFETY_MODE` is not explicitly set.

### Documentation

- Version integrity fixed: `pyproject.toml` updated from `0.1.0` to `0.4.0`.
- README tool count corrected from 12 to 17 (plus 2 opt-in raw tools).
- `docs/safety.md` updated to reflect new defaults and raw command policy.

### Tests

- 71 tests passing (up from 63 in v0.3.0). 8 new tests cover dangerous
  keyword detection and per-resource locking.

---

## v0.3.0 — Recipes, response parsing, operational states

- **Recipes**: declarative multi-step workflows in YAML with safe
  arithmetic expression evaluation (`$var * 1.1`).
- **Response parser**: vendor-specific data (e.g., Yokogawa 7563's
  `NTKC+00027.0E+0`) converted to structured dictionaries via regex.
- **Operational states / physical interface**: YAML sections describing
  startup sequences, modes, and terminal information.
- New MCP tools: `list_recipes`, `execute_recipe` (17 total, up from 15).
- 63 tests passing (up from 43).

## v0.2.0 — Safety constraint system

- YAML `safety` section: `ratings`, `preconditions`, `cautions`,
  `hardware_protections`.
- Three safety modes via `VISA_MCP_SAFETY_MODE`: `strict`, `advisory`,
  `permissive` (default was `advisory` in this version).
- `override_safety` + `override_reason` mechanism on
  `execute_named_command`.
- Audit log (JSON Lines) at `~/.visa-mcp/audit.log`.
- New MCP tools: `get_instrument_info`, `list_safety_constraints`,
  `validate_operation` (15 total).

## v0.1.0 — Initial public release

- 12 MCP tools (discovery, identification, execution, PDF extraction).
- YAML-based instrument command definitions.
- Automatic `*IDN?` identification + manual binding for legacy non-SCPI
  devices.
- Type/range/enum parameter validation.
- FastMCP + asyncio.
- Verified with Kikusui PMX35-3A (USB, SCPI) and Yokogawa 7563 (GPIB,
  proprietary).
