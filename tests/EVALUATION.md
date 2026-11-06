# HW2 Test Suite Evaluation

## Target and requirements

The target is the submitted Flask application in `app.py` from <https://github.com/sivab193/research-assistant>. Its main behaviors include Semantic Scholar search with OpenAlex fallback, SQLite library storage, PDF upload and extraction, LM Studio/OpenRouter routing, and grounded summarize/ask endpoints. Coverage is measured against the `app` module.

## Initial evaluation (frozen before improvement)

The initial Codex-generated suite contained 21 tests. Its recorded command was:

```bash
pytest --cov=app --cov-report=term-missing --cov-branch
```

| Measure | Initial result |
| --- | ---: |
| Tests collected | 21 |
| Passed / failed / skipped | 21 / 0 / 0 |
| Runtime | 0.06 s |
| Statements covered / total | 169 / 279 |
| Line coverage | 60.57% |
| Branches covered / total | 23 / 66 |
| Branch coverage | 34.85% |
| Combined coverage.py result | 56% |

### Initial correctness review

- **Incorrect tests:** none. The generated expectations matched the Flask application.
- **Redundant tests:** none. Each test exercised a distinct contract.
- **Weak assertions:** `test_ask_unknown_paper_returns_404` and `test_summarize_unknown_paper_returns_404` checked status only; the OpenAlex fallback test did not prove call order; the upload success test used a mocked parser and did not prove end-to-end PDF parsing.
- **Important omissions:** direct `extract_pdf` behavior, LM Studio/OpenRouter adapters, `lm_chat` routing, downloadable PDFs in `paper_source`, index/config/health routes, provider failures, stored-file deletion, limit capping, real-PDF upload, 413 handling, URL fallbacks, malformed authors JSON, and prompt-grounding assertions.
- **Flakiness:** none observed. Network and LLM boundaries were mocked and database state was isolated.

### Initial fault detection

The initial database-backed tests exposed an existing resource-lifecycle defect: `get_db()` returns a `sqlite3.Connection`, but application call sites use `with get_db() as db`, whose context manager commits or rolls back without closing the connection. Python emitted `ResourceWarning: unclosed database` messages. The functional assertions still passed because the leak affects cleanup rather than response payloads. The application was not changed.

## Evaluation after improvement round 1

The coverage-driven first round produced 42 tests. All 42 passed in 1.36 seconds on the final verification machine. Coverage rose to 93.55% for lines, 84.85% for branches, and 92% combined.

| Measure | After round 1 |
| --- | ---: |
| Tests collected | 42 |
| Passed / failed / skipped | 42 / 0 / 0 |
| Runtime | 1.36 s |
| Line coverage | 93.55% (261 / 279) |
| Branch coverage | 84.85% (56 / 66) |
| Combined coverage.py result | 92% |

The first round closed the largest coverage gaps in PDF extraction, provider adapters, LLM routing, `paper_source`, health/configuration, and analysis error handling. Its remaining weaknesses were incomplete normalization fallbacks, limited provider edge cases, no end-to-end real-PDF upload, and several assertions that could be made more exact. The SQLite connection warnings remained visible, and no additional application defect was detected.

## Final evaluation

Final verification was performed on Windows with Python 3.13.15, pytest 8.4.2, pytest-cov 7.0.0, and coverage.py 7.17.2:

```bash
python -m pytest --cov=app --cov-report=term-missing --cov-branch
```

| Measure | Initial | Round 1 | Round 2 / final |
| --- | ---: | ---: | ---: |
| Tests | 21 | 42 | 68 |
| Passed / failed / skipped | 21 / 0 / 0 | 42 / 0 / 0 | 68 / 0 / 0 |
| Runtime | 0.06 s | 1.36 s | 2.60 s |
| Statements covered / total | 169 / 279 | 261 / 279 | 276 / 279 |
| Line coverage | 60.57% | 93.55% | 98.92% |
| Branches covered / total | 23 / 66 | 56 / 66 | 64 / 66 |
| Branch coverage | 34.85% | 84.85% | 96.97% |
| Combined coverage.py result | 56% | 92% | 98.55% (99% displayed) |
| Existing bugs detected | 1 | 1 | 1 |

Only three statements and two branches remain uncovered: defensive OpenRouter error-detail parsing and the direct `app.run` development-server entry point. Launching the blocking development server inside the unit suite would reduce safety and speed without testing an application contract.

### Final correctness review

- **Correct inputs and outputs:** endpoint tests assert status codes and exact or semantically complete JSON bodies. Unit tests assert normalized field values, fallback order, persistence, truncation, and exceptions.
- **Meaningful assertions:** summarize/ask tests verify answer, basis, title, question, and source text in the LLM prompt. Search tests verify provider order and request parameters. Delete tests verify the empty 204 response and file removal.
- **External isolation:** an autouse guard fails any unexpected `requests` call. All expected HTTP and LLM boundaries use controlled doubles.
- **Database isolation:** module import uses `.pytest_cache/atlas-import-data`; each database test monkeypatches `DATA_DIR`, `UPLOAD_DIR`, and `DB_PATH` to pytest's temporary area. No real `data/papers.db` existed before or after verification.
- **PDF behavior:** the suite covers controlled parser edge cases and a real PDF generated with ReportLab, including metadata extraction and upload persistence.
- **Incorrect, redundant, or flaky final tests:** none identified in the final review. The suite completes well below the 60-second target.

### Final fault-detection assessment

The final suite continues to expose the SQLite connection leak through repeated `ResourceWarning` messages; garbage-collection timing affects the exact count. No additional existing application bugs were detected. The defect was documented rather than fixed because HW2 is test-focused and the user required production code to remain unchanged.
