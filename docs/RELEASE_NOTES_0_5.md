# SecureNote 0.5: local transcript RAG

Adds actual retrieved-context generation using google/flan-t5-small, with local
CPU float32 inference, a bounded prompt, no-evidence abstention, evidence matching,
timestamp links and save-to-notebook. Available through ask.py and the review UI.
This meets the assignment through RAG. Deterministic media utility calls are not
presented as model-directed AI tool calls.

The download command pins the checkpoint revision. The runtime refuses missing
models, uses safetensors and offline loading, and never executes model output.
Models are retained in memory for subsequent questions. Generation is serialized;
concurrent questions receive a retry message. The token cap and soft generation
time budget bound normal decoding, but a hung native call still needs a future
process supervisor with a hard timeout.

Tests exercise retrieval contracts, context inclusion, missing evidence, unsupported
answers, private logging defaults, session/CSRF checks and deletion of answer files.
Actual examples and logs are under examples/assignment-v05. Generated answers are
short drafts; matching wording to a source is not factual or semantic verification.
The Windows GPU setup applies to Whisper only. RAG runs on CPU.
