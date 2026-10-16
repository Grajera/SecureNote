"""Build the four-page assignment PDF from actual example artifacts.

Development only: reportlab is not needed by the application.
"""

import json
from html import escape
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, Preformatted,
                               SimpleDocTemplate, Spacer)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = json.loads((ROOT / "examples/verified/evidence.json").read_text())
RUNS = {run["label"]: run for run in EVIDENCE["runs"]}
NAVY = colors.HexColor("#17324d")
TEAL = colors.HexColor("#116c78")
# Embed fonts so another PDF viewer does not substitute the base-14 faces.
font_root = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("ReportSans", str(font_root / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("ReportSansBold", str(font_root / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("ReportMono", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"))
pdfmetrics.registerFontFamily("ReportSans", normal="ReportSans", bold="ReportSansBold", italic="ReportSans", boldItalic="ReportSansBold")
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="Title2", fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=NAVY, spaceAfter=9))
styles.add(ParagraphStyle(name="Sub", fontName="Helvetica", fontSize=10, leading=14, textColor=TEAL, spaceAfter=13))
styles.add(ParagraphStyle(name="H", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=10, spaceAfter=6))
styles.add(ParagraphStyle(name="B", fontName="Helvetica", fontSize=10, leading=13.6, spaceAfter=7))
styles.add(ParagraphStyle(name="Small2", fontName="Helvetica", fontSize=8.8, leading=11.5, spaceAfter=5))
styles.add(ParagraphStyle(name="Code2", fontName="Courier", fontSize=7.8, leading=10.2, backColor=colors.HexColor("#f1f5f8"), borderPadding=7, spaceAfter=9))
for name in ("Title2", "Sub", "H", "B", "Small2", "Code2"):
    styles[name].fontName = {"Helvetica": "ReportSans", "Helvetica-Bold": "ReportSansBold", "Courier": "ReportMono"}[styles[name].fontName]
styles["B"].fontSize = 9.4
styles["B"].leading = 12.7
styles["Small2"].fontSize = 8.3
styles["Small2"].leading = 11.2
story = []
markdown = []


def heading(text):
    story.append(Paragraph(escape(text), styles["H"]))
    markdown.extend(["## " + text, ""])


def paragraph(text, small=False):
    story.append(Paragraph(text, styles["Small2" if small else "B"]))
    markdown.extend([text.replace("<b>", "**").replace("</b>", "**").replace("<br/>", "\n"), ""])


def code(text):
    story.append(Preformatted(text, styles["Code2"]))
    markdown.extend(["```text", text, "```", ""])


def architecture():
    drawing = Drawing(490, 307)
    boxes = [
        ("INPUT", "Local audio/video file + optional query"),
        ("VALIDATION", "Size, duration, audio track; inspect_media tool"),
        ("PREPROCESSING", "decode_audio tool: 16 kHz mono PCM"),
        ("MODEL INFERENCE", "Offline Whisper base.en, CPU int8"),
        ("POSTPROCESSING", "ASR contract; automatic extractive notes"),
        ("RETRIEVAL TOOL", "search_transcript: TF-IDF evidence lookup"),
        ("OUTPUT", "Transcript, notes, search JSON and Markdown"),
    ]
    for index, (title, detail) in enumerate(boxes):
        y = 264 - index * 38
        drawing.add(Rect(5, y, 318, 31, rx=4, fillColor=colors.HexColor("#eef5f8"), strokeColor=colors.HexColor("#b4cbd5")))
        drawing.add(String(15, y + 19, title, fontName="ReportSansBold", fontSize=8.4, fillColor=NAVY))
        drawing.add(String(15, y + 7, detail, fontName="ReportSans", fontSize=8.1))
        if index < len(boxes) - 1:
            drawing.add(Line(164, y, 164, y - 7, strokeColor=TEAL))
            drawing.add(Polygon([161, y - 4, 167, y - 4, 164, y - 7], fillColor=TEAL, strokeColor=TEAL))
        drawing.add(Line(323, y + 15, 350, y + 15, strokeColor=colors.HexColor("#8ba6af"), strokeDashArray=[2, 2]))
    drawing.add(Rect(350, 36, 133, 259, rx=4, fillColor=colors.HexColor("#ecf7f3"), strokeColor=TEAL))
    for index, text in enumerate(["LOGGING", "Run ID and input size", "Stage start / finish / failure", "Stage and total latency", "Output files, counts, hash", "Content omitted by default", "Synthetic demos opt in"]):
        drawing.add(String(359, 274 - 17 * index, text, fontName="ReportSansBold" if index == 0 else "ReportSans", fontSize=8.2, fillColor=NAVY))
    drawing.add(Rect(5, 0, 478, 25, fillColor=None, strokeColor=colors.HexColor("#8b8b8b"), strokeDashArray=[4, 3]))
    drawing.add(String(13, 9, "PLANNED: Pi recorder / secure offload; diarization; local LLM; retention controls", fontName="ReportSans", fontSize=8.1))
    story.append(drawing)
    story.append(Spacer(1, 8))
    markdown.extend([(ROOT / "docs/architecture.md").read_text().split("## Boundary 1")[0], ""])


story.append(Paragraph("SecureNote", styles["Title2"]))
story.append(Paragraph("ECE 6540 | Project Assignment 2 | Michael Grajera | October 22, 2026", styles["Sub"]))
paragraph("<b>First working prototype: local recording to transcript, notes and search.</b> "
          "The target users are students and meeting participants who need useful records without hosted model inference. "
          "This version processes an existing recording on a laptop/server. A dedicated Pi Zero 2 recorder and secure offload remain future work.")
heading("1. Implemented architecture")
architecture()
paragraph("Each box marks a stage boundary. Registered local tools have fixed names and signatures: "
          "<b>inspect_media</b>, <b>decode_audio</b> and <b>search_transcript</b>. The controller chooses these calls, "
          "validates their results and logs execution. This implements the tool-call option; it is not an LLM-selected "
          "agent loop or full RAG. Retrieval uses only this recording's transcript.")
heading("What runs now")
paragraph("The CLI accepts common FFmpeg-decodable audio/video containers, checks for a local nonempty file "
          "up to 2 GiB and 2 hours, validates an audio track and converts it to mono 16 kHz PCM. Whisper produces "
          "text and timestamps. Postprocessing joins sentence fragments, scores importance, groups candidate "
          "decisions/actions/questions/key points and omits empty sections. Notes copy transcript sentences; "
          "owners and deadlines are never invented. A local desktop wrapper is also supplied.")
paragraph("<b>Security boundary:</b> setup downloads code and weights; processing requires local weights and uses "
          "offline mode. There is no network listener or remote inference. Temporary decoded audio is cleaned up "
          "on ordinary completion/errors. Sources and outputs remain plaintext local files for review/search; "
          "encrypted storage and access control must come from the operating environment.", small=True)

story.append(PageBreak())
heading("2. Three actual end-to-end runs")
paragraph("Inputs are included synthetic recordings generated locally with eSpeak. Actual inference ran on "
          "a Linux x86-64 AMD EPYC 9V74 host (9 visible CPUs), Python 3.12.14, four inference threads, CPU int8. "
          "Python socket connections were blocked throughout these runs; media tools allowed only local file "
          "protocol. These are short smoke tests, not laptop benchmarks or meeting-accuracy measurements.", small=True)

examples = [
    ("business", "A. Business meeting / WAV", "We decided to use the local server... Alice will send the revised budget by Friday.",
     "Decision: We decided to use the local server for all meeting recordings.",
     "Action: Alice will send the revised budget by Friday."),
    ("lecture", "B. Class lecture / MP3", "Remember, the discount factor controls how much future rewards matter. The homework is due on Friday.",
     "Key point: Remember, the discount factor controls how much future rewards matter.",
     "Key point: The homework is due on Friday."),
    ("planning", "C. Recorder planning / MP4 video", "We agreed to keep the original recordings on an encrypted drive... The important constraint is battery life.",
     "Decision: We agreed to keep the original recording on an encrypted drive.",
     "Key point: The important constraint is battery life."),
]
for label, title, input_excerpt, note1, note2 in examples:
    example = RUNS[label]
    summary = example["summary"]
    log_events = [json.loads(line) for line in (ROOT / example["run_directory"] / "run.jsonl").read_text().splitlines()]
    asr = next(event for event in log_events if event["stage"] == "model_inference" and event["event"] == "completed")
    heading(title)
    paragraph(f"<b>Input:</b> {escape(Path(example['input']).name)}; {summary['input_bytes']:,} bytes; "
              f"{summary['duration_seconds']:.2f} s. Source excerpt: &quot;{escape(input_excerpt)}&quot;<br/>"
              f"<b>Output excerpts:</b> {escape(note1)} {escape(note2)}<br/>"
              f"<b>Search:</b> &quot;{escape(example['query'])}&quot; returned {summary['output']['search_matches']} "
              f"passage(s), with source intervals in the output. Total: {summary['latency_ms']/1000:.3f} s; "
              f"{summary['output']['note_count']} candidate notes.")
    code(f'{{"stage":"input","event":"received","input_bytes":{summary["input_bytes"]}}}\n'
         f'{{"stage":"model_inference","event":"completed",\n'
         f' "latency_ms":{asr["latency_ms"]}}}\n'
         f'{{"stage":"run","event":"finished","status":"ok",\n'
         f' "latency_ms":{summary["latency_ms"]}}}')
paragraph("Log excerpts above project a few fields from the raw JSONL; full run IDs, stage events, synthetic "
          "logged note bodies, transcripts and search scores are in examples/verified/. The lecture also "
          "misheard 'maps a state' as 'map sustained' and corrupted its last question. These errors remain "
          "in the artifacts and show why review is necessary. Reproduce with: "
          "<b>python tools/run_examples.py --model-dir models/base.en</b>.", small=True)

story.append(PageBreak())
heading("3. Two stage interfaces")
heading("Boundary A - Model inference to postprocessing")
paragraph("<b>Input type/shape:</b> the model receives a one-dimensional float32 waveform (N samples), "
          "mono at 16,000 Hz, approximately [-1,1), with 0 &lt; N/16000 &lt;= 7200 seconds. Its adapter emits "
          "a JSON-compatible list of {start: float, end: float, text: str}.")
paragraph("<b>Output type/shape:</b> postprocessing produces sentence passages "
          "[{id: int, start: float, end: float, text: str}] and a dictionary of nonempty note sections, "
          "each holding selected source passages plus importance_score. Intervals cover all contributing "
          "ASR segments, so sentence times are approximate.")
paragraph("<b>Missing/invalid behavior:</b> at most 100,000 segments; nonempty text up to 20,000 characters "
          "per segment; finite 0 &lt;= start &lt;= end &lt;= duration + 1 second, and ordered starts. "
          "A wrong type or invalid time raises ValueError and stops note output. An empty list is valid "
          "silence: status no_speech, explicit message and no candidate notes. The one-second endpoint "
          "tolerance accommodates ASR padding; it does not establish word-level timing accuracy.")
heading("Boundary B - Retrieval tool to formatter")
paragraph("<b>Input type/shape:</b> validated passages, query string of 1-512 total characters with at "
          "least one non-whitespace character, and integer limit 1-20 (default 5). "
          "<b>Tool output:</b> up to limit objects {id, start, end, text, score}; score is TF-IDF cosine similarity.")
paragraph("<b>Formatter output:</b> timestamped Markdown evidence bullets and JSON results. Every returned "
          "ID/text/time must match an existing passage. Scores must be finite within [0,1], allowing 1e-6 "
          "numerical tolerance. Malformed results fail the stage. No positive matches returns [] and "
          "'No matching passages found'; the system does not manufacture an answer. Scores are not confidence probabilities.")
heading("4. Model choice and assumptions")
paragraph("<b>Whisper base.en</b> (74 million parameters), using faster-whisper 1.2.1/CTranslate2 4.6.0, "
          "was selected for a small, CPU-capable prototype [1,2]. The local model files are about 141 MiB. "
          "No paid inference service is used; costs are local compute/storage. The intended Windows laptop "
          "has an i5-13420H, 32 GB RAM and RTX 4050 6 GB, but its actual performance was not measured here. "
          "The tested path uses CPU and needs no CUDA installation.")
paragraph("<b>Reduced precision:</b> the converted checkpoint stores FP16 weights [2]; runtime uses int8 "
          "compute. Observed end-to-end times for the three short files were "
          f"{RUNS['business']['summary']['latency_ms']/1000:.3f}, {RUNS['lecture']['summary']['latency_ms']/1000:.3f} and "
          f"{RUNS['planning']['summary']['latency_ms']/1000:.3f} seconds. Transcription errors occurred, "
          "but no float32 accuracy comparison was performed, so errors cannot be attributed to quantization.")
paragraph("<b>Assumption 1:</b> intended input is intelligible English speech with limited overlap; "
          "base.en does not promise multilingual or reliable speaker identification. "
          "<b>Assumption 2:</b> ASR text and timestamps are fallible evidence, not authoritative records. "
          "Users must verify high-impact notes; structural validity cannot establish factual correctness.")

story.append(PageBreak())
heading("5. Intentional failure and analysis")
failure = RUNS["malformed_model_output"]
failure_log = [json.loads(line) for line in (ROOT / failure["run_directory"] / "run.jsonl").read_text().splitlines()]
failed_event = next(event for event in failure_log if event["stage"] == "postprocessing" and event["event"] == "failed")
paragraph("<b>What changed:</b> after real ASR on business.wav, --inject-invalid-segment replaces the "
          "adapter output with [{start: 0.0, end: 1.0, text: 123}]. This deliberately simulates a malformed "
          "model adapter, rather than altering the original recording.")
paragraph("<b>Result:</b> the process reported a controlled failure; the CLI maps failed runs to exit code 2. "
          "No notes were written and no silent wrong answer was returned. The run recorded ValueError at "
          "the model-to-postprocessing contract. <b>Which boundary let it through?</b> The simulated ASR "
          "adapter emitted the bad object, but its receiving contract rejected it; no downstream boundary "
          "accepted it. Cleanup removed the temporary decoded WAV.")
code(f'{{"stage":"postprocessing","event":"failed",\n'
     f' "latency_ms":{failed_event["latency_ms"]},"error_type":"ValueError"}}\n'
     f'{{"stage":"run","event":"finished","status":"failed",\n'
     f' "latency_ms":{failure["summary"]["latency_ms"]}}}')
paragraph("<b>What to add:</b> keep the structural checks, validate configuration/schema versions at "
          "startup, and add labeled noisy/overlapping speech tests and human review. Plausible but "
          "incorrect transcript text passes shape validation. Other verification: seven contract tests "
          "passed; malformed retrieval output was rejected; an empty file never reached inference; "
          "two seconds of silence produced no_speech and zero notes. Existing-run search returned an "
          "explicit empty result for an absent term.")
heading("6. Gap analysis and next steps")
paragraph("<b>Built:</b> validated local media input, real ASR, registered tools, automatic extractive "
          "importance/formatting, source-linked lexical search, stage contracts and per-run logging. "
          "<b>Simplified:</b> base.en replaces large-v3; deterministic candidate-note extraction replaces "
          "the proposed Qwen LLM. This is working baseline logic, not a stubbed model. "
          "<b>Missing:</b> Pi capture/offload, diarization and verified speakers, implicit action reasoning, "
          "semantic search, cache, multiuser security and enforced retention. Diagrams mark these as planned.")
paragraph("<b>Most fragile:</b> ASR mistakes and cue-based importance selection, especially indirect "
          "commitments, quotations and jargon. Transcript retention intentionally differs from Part 1 "
          "because this prototype needs searchable evidence. Before real-user operation, add encrypted "
          "storage/ACL deployment, authenticated offload with integrity checks, retention enforcement, "
          "ASR process timeouts/heartbeats, disk/queue monitoring, stage failure rates, latency percentiles "
          "and consented accuracy audits. Keep content out of operational metrics. The next functional "
          "steps are real lecture/meeting evaluation, optional local LLM notes, then Pi capture/transfer.")
heading("Security limits and submission contents")
paragraph("File-only media protocols and argument-list subprocess calls reduce accidental remote access; "
          "they are not a decoder sandbox [3]. This is not a certified confidential system: no built-in "
          "encryption, authentication or secure erasure exists. Use public/synthetic data for this demo. "
          "The ZIP contains the README, runnable code, synthetic media, complete evidence and this report. "
          "Model weights/dependencies require one-time setup or approved offline transfer. The desktop "
          "window was not interactively tested on Windows, and no Pi hardware was tested.", small=True)
paragraph("<b>Primary references:</b><br/>"
          "[1] Whisper model sizes: https://github.com/openai/whisper<br/>"
          "[2] Checkpoint and precision: https://huggingface.co/Systran/faster-whisper-base.en<br/>"
          "[3] FFmpeg protocols: https://ffmpeg.org/ffmpeg-protocols.html", small=True)


def decorate(canvas, document):
    canvas.setStrokeColor(colors.HexColor("#d3e0e7"))
    canvas.line(48, 43, 564, 43)
    canvas.setFillColor(NAVY)
    canvas.setFont("ReportSans", 8)
    canvas.drawString(48, 29, "SecureNote | First working prototype | ECE 6540")
    canvas.drawRightString(564, 29, str(document.page))


destination = ROOT / "docs/Project_Assignment_2.pdf"
document = SimpleDocTemplate(str(destination), pagesize=(612, 792), leftMargin=48, rightMargin=48,
                             topMargin=40, bottomMargin=57, title="SecureNote - Project Assignment 2",
                             author="Michael Grajera")
document.build(story, onFirstPage=decorate, onLaterPages=decorate)
(ROOT / "docs/Project_Assignment_2.md").write_text("# SecureNote - Project Assignment 2\n\n" + "\n".join(markdown), encoding="utf-8")
print(destination)
