# CS 59300 HW2 Report Outline - Atlas Research Assistant

## 1. Test Generation Approach

- Agent: Codex; framework: pytest and Flask test client.
- Target: submitted Flask `app.py` in <https://github.com/sivab193/research-assistant>.
- Isolation: temporary SQLite/upload paths; mocked HTTP and LLM calls; no real key or production database.
- Initial suite: 21 tests covering normalization, CRUD, search/fallback, upload routing, and summarize/ask.

## 2. Initial Test Evaluation

- Result: 21/21 passed in 0.06 s.
- Coverage: 60.57% lines (169/279), 34.85% branches (23/66), 56% combined.
- Weaknesses: status-only 404 checks, incomplete fallback proof, mocked-only upload success.
- Missing: PDF extraction, provider adapters/routing, PDF download/persistence, health/config details, real PDF and 413 behavior.
- Existing bug: repeated unclosed SQLite connection `ResourceWarning`s.

## 3. Iterative Test Improvement

- Round 1, coverage-driven: used `term-missing` to target PDF parsing, provider adapters, routing, `paper_source`, health/config, and 503 paths. Result: 42 passed, 93.55% line, 84.85% branch, 92% combined.
- Round 2, correctness-driven: strengthened response, prompt, and call-order assertions; added normalization and provider edge cases, real PDF upload, 413 behavior, file deletion, all health modes, URL fallbacks, and portable temp paths. Result: 68 passed, 98.92% line, 96.97% branch, 98.55% combined.
- Manual intervention: reviewed `app.py`, interpreted warnings, added ReportLab as a development-only dependency, and fixed the pytest temp base for Windows.

## 4. Final Evaluation

| Measure | Initial | Round 1 | Round 2 / final |
| --- | ---: | ---: | ---: |
| Tests | 21 | 42 | 68 |
| Pass / fail / skip | 21 / 0 / 0 | 42 / 0 / 0 | 68 / 0 / 0 |
| Runtime | 0.06 s | 1.36 s | 2.60 s |
| Line coverage | 60.57% | 93.55% | 98.92% |
| Branch coverage | 34.85% | 84.85% | 96.97% |
| Combined coverage | 56% | 92% | 98.55% |
| Existing bugs | 1 | 1 | 1 |

- Round 1 was most effective for coverage breadth.
- Round 2 added a smaller coverage gain but improved oracle quality, edge-case depth, portability, and network safety.
- Remaining uncovered paths: defensive OpenRouter detail parsing and direct `app.run`.

## 5. Reflection

- Codex understood route and service structure well after receiving direct source context.
- Strongest outputs: JSON contracts, provider fallback, persistence, and error translation.
- Initial struggles: incomplete PDF/provider coverage and several weak assertions.
- Coverage feedback found omissions efficiently; correctness feedback improved oracle strength and portability.
- Main lesson: agents generate useful breadth quickly, but require authoritative requirements, execution feedback, and human review.

## 6. GitHub Repository

- Repository: <https://github.com/sivab193/research-assistant>
- Final suite: `tests/`
- Install: `python -m venv .venv`, activate it, then `pip install -r requirements-dev.txt`.
- Run/coverage: `python -m pytest --cov=app --cov-report=term-missing --cov-branch`.
