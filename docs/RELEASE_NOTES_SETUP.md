# Submission cleanup and portable launcher

The main README is the current setup guide. Older release notes and validation
files describe earlier builds; they are retained as historical evidence.

- Added standard-library `start.py` with CPU/NVIDIA setup, saved device choice,
  offline workspace launch, tests and the complete assignment demo.
- Added Linux `start.sh` and routed the main Windows launcher through the menu.
- Kept models and recordings separate from application files; setup never deletes them.
- Set Linux CUDA loader paths before starting model processes.
- Added model inference smoke checks and fail-fast dependency installation.
- Expanded comments and docstrings at validation, retrieval, transfer and security
  boundaries. Applied Black 25.1.0 formatting to Python source/tests/tools.
- Included the previously delivered RAG retry fix and updated four-page report.

Validation on Linux x86-64, Python 3.12.14:
42 unit tests passed. The menu's noninteractive demo path completed all three
transfers/transcriptions/answers and failure injection. Setup succeeded using
an existing environment and cached models; this was not a clean-machine install.
Both model inference smoke checks passed. Starting from outside the project and
Ctrl+C shutdown passed. No Windows or hardware GPU execution was available.

The PDF's 37-test count describes the RAG patch validation before five launcher
tests were added. Its three timing measurements remain the original evidence;
new launcher/demo timings do not replace those measurements.

No further answer-quality improvements are claimed in this cleanup release.
