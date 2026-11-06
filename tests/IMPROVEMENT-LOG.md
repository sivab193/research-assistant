# Test Suite Improvement Log

## Initial generation

### Representative prompt supplied to Codex

> Examine the existing Flask HW1 application and generate an executable pytest suite for its main behavior, edge cases, and error handling. Use Flask's test client, isolate SQLite and uploads under temporary directories, mock all search and LLM calls, and do not change production code. Run the suite and evaluate coverage, correctness, and existing-bug detection.

The generated baseline contained 21 passing tests and reached 60.57% line coverage, 34.85% branch coverage, and 56% combined coverage.

## Round 1 - coverage-driven

### Prompt/feedback supplied to Codex

> The initial suite has 21 passing tests and 56% combined coverage. The `term-missing` report shows major uncovered regions in `extract_pdf`, LM Studio/OpenRouter adapters and `lm_chat` dispatch, `paper_source`, index/config/health routes, and analysis error handlers. Add focused tests for these uncovered behaviors only. Use meaningful output, payload, persistence, and call-contract assertions. Keep every network and LLM boundary mocked, use the temporary database fixture, and do not modify application behavior merely to increase coverage.

### Changes

- Added controlled PDF-reader tests for metadata, fallbacks, scanned/no-text rejection, and abstract handling.
- Added provider adapter and routing tests for LM Studio, OpenRouter, and automatic fallback.
- Added `paper_source`, index, config, health, and analysis-error tests.
- Preserved the no-network and temporary-database constraints.

### Result after Round 1

The locally reverified intermediate suite contained 42 tests: 42 passed in 1.36 seconds, with 93.55% line coverage, 84.85% branch coverage, and 92% combined coverage.

## Round 2 - correctness-driven and edge-case focused

### Prompt/feedback supplied to Codex

> Audit the 42-test suite for weak assertions and missing edge cases using the submitted Flask application's intended behavior as the source of truth. Strengthen response and prompt assertions; cover normalization, provider, health, CRUD, upload, and PDF-source fallbacks; exercise a real generated PDF; prove Flask's 413 behavior without allocating a 30 MB payload; and add a fail-fast live-network guard. Do not edit `app.py`, templates, static assets, or any production behavior.

### Changes

- Added exact normalizer defaults, OpenAlex URL/PDF fallback order, empty/malformed authors handling, and metadata year/abstract bounds.
- Added CRUD normalization, newest-first listing, stored-file deletion, and empty 204 body assertions.
- Added Semantic Scholar/OpenAlex limit capping and configured OpenAlex-key assertions.
- Added LM Studio no-model behavior, OpenRouter error/malformed-response behavior, `auto` success/no-key paths, and all health provider modes.
- Added stronger summarize/ask prompt grounding and no-usable-text 503 assertions.
- Added a real ReportLab PDF upload test and a low-configured-limit 413 test that avoids allocating 30 MB.
- Added `.pytest_cache`-based import and `tmp_path` bases so the suite runs in managed Windows environments as well as ordinary local shells.
- Added comments that document the submitted Flask target and security expectations.

### Result after Round 2 / final

| Measure | Final result |
| --- | ---: |
| Tests | 68 |
| Passed / failed / skipped | 68 / 0 / 0 |
| Runtime | 2.60 s |
| Line coverage | 98.92% (276 / 279) |
| Branch coverage | 96.97% (64 / 66) |
| Combined coverage.py result | 98.55% (99% displayed) |
| Existing bugs detected | 1 SQLite connection leak |

Round 1 produced the largest coverage gain. Round 2 added 26 tests, raised combined coverage by 6.55 points, strengthened behavioral oracles, and demonstrated a real PDF path. The suite remained fast and used no live network, real API key, or production database.

## Significant manual interventions

- Inspected `app.py` line by line before expanding the tests.
- Corrected pytest's temporary-directory base for the managed Windows sandbox after the first local run failed during fixture setup. This was a test-harness portability issue, not an application failure.
- Added ReportLab only to `requirements-dev.txt` so runtime dependencies remain unchanged.
- Reviewed failures and warnings to distinguish the SQLite resource leak from test mistakes.
- Did not change application code, rewrite history, commit, push, or contact a live external service.
