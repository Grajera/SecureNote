# Implemented recorder/processor architecture, version 0.2

```mermaid
flowchart TD
    I["Device input: recording replay"] --> Q["Device spool: media and manifest"]
    Q --> T["Transfer: token-authenticated upload"]
    T --> V["Receiver: checksum validation, ACK, queue"]
    V --> A["Media validation: inspect_media tool"]
    A --> P["Preprocessing: decode_audio tool"]
    P --> M["Local model inference: Whisper base.en"]
    M --> N["Postprocessing: contracts and automatic notes"]
    N --> R["Retrieval tool: search_transcript"]
    R --> O["Output: searchable transcript and notes"]
    Q -.-> L["Device, receiver and pipeline logs"]
    V -.-> L
    M -.-> L
    O -.-> L
    D["Planned: tested Pi microphone hardware"] -.-> I
    F["Planned: diarization and local LLM"] -.-> N
    style D stroke-dasharray: 5 5
    style F stroke-dasharray: 5 5
```

Device and processor are independent programs with separate directories. The
same-PC demo uses loopback HTTP; cross-machine deployment requires HTTPS.
The recorder has no ASR/LLM dependency. Detailed recorder/receiver contract,
acknowledgment semantics, retry behavior and migration instructions are in
TWO_ROLE_DEPLOYMENT.md. Capture is file replay; transport and processing run.

## Device-to-receiver boundary

Input is a raw media body and schema-1.0 manifest with recording/device IDs,
ISO-8601 capture time, byte count and SHA-256. Required token, one Content-Length,
2-GiB size cap, strict manifest shape and body hash are checked. A successful
receipt contains ID/size/hash; only then does the device mark delivery. The
receiver publishes a persistent job before acknowledgment. Bad requests return
400/401 with no published job; missing acknowledgment leaves a retryable device
copy. The same ID+manifest is idempotent. A later media/ASR failure is reported
as a failed job, separately from delivery acknowledgment.

## Boundary 1: model inference -> postprocessing

Input to model: mono waveform `numpy.ndarray`, shape `(N,)`, dtype `float32`,
16,000 samples/second, decoded from signed 16-bit PCM to approximately [-1, 1).
Duration `0 < N/16000 <= 7200`. Model adapter emits JSON-compatible
`list[{start: float, end: float, text: str}]`.

Postprocessor output: sentence passages `list[{id: int, start: float, end: float,
text: str}]`, grouped candidate notes `dict[str, list[passage + importance_score]]`.
Sentence fragments crossing ASR turns are joined; the note interval covers all
contributing segments. Speaker identity is not inferred.

Checks: at most 100,000 segments, nonempty text <=20,000 characters per segment,
finite `0 <= start <= end <= decoded_duration + 1 second`, starts in temporal
order. A one-second tolerance accommodates ASR endpoint padding, so timestamps
are approximate. Wrong types or invalid times raise `ValueError`; no notes are
written. Empty list is valid: `no_speech` status and explicit no-speech output.
Structural checks do not establish transcription accuracy.

## Boundary 2: retrieval tool -> output formatter

Tool input: validated sentence passages and a query `str`, 1-512 non-whitespace
characters (length bound applies to the complete query), `limit: int` 1-20,
default 5. Retrieval output: up to `limit` objects
`{id: int, start: float, end: float, text: str, score: float}`. Scores are positive
cosine similarities; rounding can approach zero. They are not probabilities.

Formatter output: Markdown bullets with timestamp, source text and score, plus
JSON search results. All IDs, times and text must match an existing source
passage exactly; scores must be finite and within [0, 1] with 1e-6 numerical
tolerance. Malformed results raise `ValueError` and fail the stage. No positive
similarities yields `[]` and the message "No matching passages found." Nothing
is invented to fill a missing result. Queries do not modify the recording.

## Dynamic notes policy

Automatic notes use common English decision/action/question cues, sentence
centrality computed from TF-IDF vectors, and emphasis words such as "important"
and "exam". At most eight items per section are retained, duplicates suppressed,
and selected notes are placed in recording order. Empty sections are omitted.
This needs no user-written vocabulary file, but its built-in English cues are
limited. It provides evidence-preserving candidate notes rather than semantic
reasoning about implicit actions, jokes, quotations or speaker identity.
