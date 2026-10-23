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
EVIDENCE = json.loads((ROOT / "examples/distributed-verified/evidence.json").read_text())
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
    drawing = Drawing(490, 305)
    boxes = [
        ("INPUT - RECORDER ROLE", "Replay audio/video as emulated capture"),
        ("DEVICE QUEUE", "Persist media, ID, size and SHA-256 manifest"),
        ("TRANSFER", "Token-authenticated upload; retain until ACK"),
        ("VALIDATION - PROCESSOR ROLE", "Verify size/hash -> ACK; validate media/audio"),
        ("MODEL INFERENCE", "decode_audio tool -> offline Whisper CPU int8"),
        ("POSTPROCESSING", "ASR contract; importance scoring; dynamic notes"),
        ("OUTPUT + RETRIEVAL TOOL", "Transcript, notes, timestamped search_transcript"),
    ]
    for index, (title, detail) in enumerate(boxes):
        y = 264 - index * 38
        fill = "#ecf7f3" if index < 3 else "#eef5f8"
        drawing.add(Rect(5, y, 318, 31, rx=4, fillColor=colors.HexColor(fill), strokeColor=colors.HexColor("#b4cbd5")))
        drawing.add(String(14, y+19, title, fontName="ReportSansBold", fontSize=8))
        drawing.add(String(14, y+7, detail, fontName="ReportSans", fontSize=7.8))
        if index < 6:
            drawing.add(Line(164, y, 164, y-7, strokeColor=TEAL))
            drawing.add(Polygon([161,y-4,167,y-4,164,y-7], fillColor=TEAL, strokeColor=TEAL))
        drawing.add(Line(323,y+15,350,y+15,strokeColor=TEAL,strokeDashArray=[2,2]))
    drawing.add(Rect(350,36,133,259,rx=4,fillColor=colors.HexColor("#f2f5f8"),strokeColor=TEAL))
    for index,text in enumerate(["LOGGING", "Recorder: capture + queue", "Transfers: ACK / retry", "Receiver: accept / reject", "Job: queued / processing", "Pipeline: stage latency", "Output: files, counts, hash", "No transcript bodies", "in deployment logs"]):
        drawing.add(String(358,274-index*17,text,fontName="ReportSansBold" if index==0 else "ReportSans",fontSize=7.6))
    drawing.add(Rect(5,0,478,25,fillColor=None,strokeColor=colors.grey,strokeDashArray=[4,3]))
    drawing.add(String(12,9,"PLANNED / UNTESTED: Pi microphone hardware; diarization; local LLM; retention controls",fontName="ReportSans",fontSize=7.7))
    story.extend([drawing,Spacer(1,8)])
    markdown.extend([(ROOT/'docs/architecture.md').read_text().split('## Boundary 1')[0], ''])


story.append(Paragraph('SecureNote',styles['Title2']))
story.append(Paragraph('ECE 6540 | Project Assignment 2 | Michael Grajera | October 22, 2026',styles['Sub']))
paragraph('<b>First working prototype: emulated recorder to laptop processor.</b> Two independent roles run on one laptop now: a lightweight recorder queues and transfers media; the receiver runs local AI and produces searchable notes. Later, the recorder moves to a Pi Zero 2 W and the receiver moves to a server. Their transfer contract remains the same.')
heading('1. Implemented prototype architecture')
architecture()
paragraph('<b>Device side:</b> device.py imports a recording to emulate capture, writes a persistent spool and manifest, uploads bytes and records acknowledgment. Failed transfers remain queued for retry. <b>Laptop side:</b> laptop.py authenticates the request, verifies its size/hash, publishes a stored job, acknowledges delivery and processes one recording at a time. Acknowledgment means stored, not that transcription succeeded.')
paragraph('Processing validates media, invokes allowlisted inspect_media/decode_audio tools, runs local Whisper, validates ASR segments, selects important transcript sentences, omits empty note sections and calls the search_transcript retrieval tool. This satisfies the tool-call option. Search is lexical retrieval, not full RAG or an LLM agent loop.')
paragraph('<b>Separation and security:</b> the device uses only Python standard-library code; all model dependencies remain on the laptop. Loopback HTTP emulates transfer on one computer. Separate-machine operation requires HTTPS with certificate verification. A bearer token protects uploads/status. Media, queue data and results are plaintext and require protected storage. No hosted model API is used.',small=True)

story.append(PageBreak())
heading('2. Three real recorder-to-processor runs')
paragraph('The demo launches the laptop receiver and invokes the recorder as separate OS processes. Synthetic recordings are imported, actually uploaded over loopback HTTP, acknowledged and transcribed locally. Execution used Linux x86-64, AMD EPYC 9V74, Python 3.12.14 and four CPU inference threads. These are short smoke tests, not performance estimates for the Windows laptop. The earlier standalone inference tests also blocked Python socket connections.',small=True)
receiver_events=[json.loads(line) for line in (ROOT/'examples/distributed-verified/laptop/receiver.jsonl').read_text().splitlines()]
examples=[
 ('business','A. Business meeting / WAV','Alice will send the revised budget by Friday.',
  'Decision: We decided to use the local server for all meeting recordings.','Action: Alice will send the revised budget by Friday.'),
 ('lecture','B. Class lecture / MP3','Remember, the discount factor controls how much future rewards matter.',
  'Key point: Remember, the discount factor controls how much future rewards matter.','Key point: The homework is due on Friday.'),
 ('planning','C. Recorder planning / MP4','We agreed to keep the original recordings on an encrypted drive.',
  'Decision: We agreed to keep the original recording on an encrypted drive.','Key point: The important constraint is battery life.'),
]
for label,title,source,note1,note2 in examples:
    example=RUNS[label]
    summary=example['summary']
    identifier=example['manifest']['recording_id']
    accepted=next(e for e in receiver_events if e.get('recording_id')==identifier and e['stage']=='transfer_validation')
    heading(title)
    paragraph(f"<b>Input:</b> {escape(example['input'])}; {summary['input_bytes']:,} bytes; {summary['duration_seconds']:.2f} s. Source excerpt: &quot;{escape(source)}&quot;<br/>"
              f"<b>Output:</b> {escape(note1)} {escape(note2)}<br/>"
              f"<b>Result:</b> device delivered; processor completed; {summary['output']['note_count']} notes. Pipeline {summary['latency_ms']/1000:.3f} s; capture/transfer/processing {example['transfer_and_processing_ms']/1000:.3f} s.")
    code(f'{{"stage":"transfer_validation","event":"accepted",\n'
         f' "input_bytes":{summary["input_bytes"]},"latency_ms":{accepted["latency_ms"]}}}\n'
         f'{{"stage":"processor","event":"finished",\n'
         f' "status":"completed","latency_ms":{summary["latency_ms"]}}}')
paragraph('Excerpts project fields from genuine JSONL records. Full manifests, delivery receipts, receiver logs, ASR transcripts, notes and job states are under examples/distributed-verified/. Automatic notes also include timestamped search results. Query an existing transcript using securenote.py search RESULT-DIRECTORY "budget". The lecture misheard parts of its definition and final question; the artifacts preserve these errors rather than concealing them.',small=True)
paragraph('<b>Reproduce:</b> python tools/run_distributed_demo.py --output demo-two-role. This also performs the intentional corrupt-transfer failure test. No Pi, microphone or external server is needed for the demo.',small=True)

story.append(PageBreak())
heading('3. Two stage interfaces')
heading('Boundary A - Recorder transfer to receiver queue')
paragraph('<b>Input:</b> POST /v1/recordings with raw media bytes, one Content-Length, bearer token and a base64 JSON manifest: {schema_version: "1.0", recording_id: 32-char hex, device_id: 1-64 safe characters, captured_at: ISO-8601, input_bytes: int, sha256: 64-char hex}. Maximum size is 2 GiB; manifest header is at most 2048 bytes. Device filenames never choose receiver paths.')
paragraph('<b>Output:</b> a stored recording, manifest and queued job, plus HTTP 201 receipt {recording_id, input_bytes, sha256, status: "accepted"}; an identical repeat returns HTTP 200 without a second job. The recorder compares the receipt before marking delivered. A separate authenticated status query reports queued, processing, completed or failed.')
paragraph('<b>Missing/invalid:</b> missing authentication returns 401. Invalid manifest, size disagreement, corrupt bytes or conflicting ID return 400 without publishing a job. Interrupted uploads are not processed. Failed/missing acknowledgment leaves the recorder item queued for retry. Accepted media still undergoes audio-track/duration/format validation before inference. Delivery does not imply valid speech.')
heading('Boundary B - Model inference to postprocessing')
paragraph('<b>Input:</b> mono waveform float32 array (N,), 16,000 Hz, approximately [-1,1), duration 0-7200 s excluding zero. The ASR adapter emits list[{start: float, end: float, text: str}]. <b>Output:</b> sentence passages [{id, start, end, text}] and nonempty note sections containing selected source passages plus importance scores. Sentence fragments are joined across ASR segments; intervals are approximate.')
paragraph('<b>Missing/invalid:</b> reject non-list/oversized output, empty or wrong-type text, nonfinite times, inverted intervals or unordered starts. Limits: 100,000 segments, 20,000 characters/segment, 0 &lt;= start &lt;= end &lt;= duration + 1 s. Invalid results fail the job before notes. An empty list yields no_speech with an explicit message and zero notes. Structural checks cannot establish transcription accuracy.')
heading('4. Model choice and assumptions')
paragraph('<b>Whisper base.en</b>, 74M parameters [1], runs with faster-whisper 1.2.1/CTranslate2 4.6.0 on the processor. The checkpoint stores FP16 weights [2]; inference uses CPU int8. Local weights occupy about 141 MiB; there is no paid inference service. Three short two-role runs completed successfully with pipeline times of '+', '.join(f"{RUNS[label]['summary']['latency_ms']/1000:.3f}" for label in ['business','lecture','planning'])+' s. ASR mistakes occurred. No float32 accuracy comparison was done, so their cause cannot be attributed to quantization.')
paragraph('The intended laptop has an i5-13420H, 32 GB RAM and RTX 4050 6 GB; its actual performance was not measured. CPU mode avoids GPU driver requirements. <b>Assumption 1:</b> intelligible English speech, limited overlap; no reliable speaker identity is assumed. <b>Assumption 2:</b> transcripts/timestamps are fallible evidence; a user verifies consequential notes. Neither note selection nor the model invents an action owner or deadline intentionally.')

story.append(PageBreak())
heading('5. Intentional transfer failure')
paragraph('<b>What changed:</b> after the emulated device prepared a legitimate recording and SHA-256 manifest, the demo flipped one byte of the uploaded body while retaining the original checksum. Authentication and byte count were correct. This intentionally breaks the recorder-to-receiver data contract.')
paragraph('<b>Result:</b> the receiver returned HTTP 400, logged a validation failure, cleaned up partial storage and published no processing job. It did not crash or silently generate wrong notes. The device copy remained queued and intact. <b>Which boundary let it through?</b> the simulated sender supplied corrupt bytes; the receiver intake boundary caught them before ASR. No downstream stage accepted the damaged payload.')
rejected=next(e for e in receiver_events if e['stage']=='transfer_validation' and e['event']=='rejected')
code(f'{{"stage":"transfer_validation","event":"rejected",\n'
     f' "error_type":"ValueError","latency_ms":{rejected["latency_ms"]}}}\n'
     '{"http_status":400,"published_job":false,\n "device_status":"queued"}')
paragraph('<b>What to add:</b> the checksum catches accidental corruption, while the token and TLS protect the channel. Add per-device credentials, key rotation, storage quotas, explicit retry scheduling/backoff and labeled speech-quality checks. A checksum alone cannot establish sender identity or factual accuracy. Fourteen tests passed, including corrupted transfer, wrong token, queue persistence across receiver restart, unavailable receiver, idempotent retransmission and model/retrieval contracts.')
heading('6. Gap analysis and next steps')
paragraph('<b>Built:</b> portable recorder role, persistent spool, real authenticated upload/ACK, receiver queue, restart handling, local ASR, registered tools, automatic extractive notes, lexical retrieval, contracts and logs. <b>Emulated:</b> microphone capture is replayed from a local recording. An optional Linux arecord adapter is supplied but not hardware-tested. <b>Simplified:</b> base.en replaces large-v3 and extractive importance scoring replaces the proposed local LLM. These stages execute; they are not mocked model responses.')
paragraph('<b>Missing/fragile:</b> tested Pi hardware, continuous recorder service, robust power-loss recovery, diarization, semantic notes/search, per-device enrollment, enforced retention and production service hardening. ASR mistakes and cue-based importance selection are most fragile. Before real users, add encrypted storage/ACLs, authenticated TLS deployment, consent indicators, disk/queue alerts, job heartbeats, ASR timeouts, failure-rate and latency-percentile monitoring, and consented accuracy audits. Move device code to Pi and processor code to server without changing the manifest protocol. Retained transcripts support search and differ intentionally from Part 1 deletion plans.')
heading('Security limits and run instructions')
paragraph('Loopback HTTP is only for same-PC emulation; remote endpoints/listeners require HTTPS. Certificate loading and verification are implemented; actual remote TLS and Pi hardware deployment were not tested. The minimal HTTP server has no production traffic hardening. The shared token is not per-device authorization. Media, transcripts and notes are plaintext: local AI is not disk encryption or a security certification. Use public/synthetic inputs for this demo.',small=True)
paragraph('<b>Run:</b> follow README setup, then python tools/run_distributed_demo.py. For manual use, run laptop.py serve in one terminal and device.py enqueue FILE followed by device.py send --token-file laptop-state/device.token in another. docs/TWO_ROLE_DEPLOYMENT.md explains later Pi/server placement. Code, synthetic media and authentic evidence accompany this four-page PDF.',small=True)
paragraph('<b>Primary references:</b><br/>[1] Model sizes: https://github.com/openai/whisper<br/>[2] Checkpoint/precision: https://huggingface.co/Systran/faster-whisper-base.en<br/>[3] Media protocol restrictions: https://ffmpeg.org/ffmpeg-protocols.html',small=True)


def decorate(canvas,document):
    canvas.setStrokeColor(colors.HexColor('#d3e0e7'))
    canvas.line(48,43,564,43)
    canvas.setFillColor(NAVY)
    canvas.setFont('ReportSans',8)
    canvas.drawString(48,29,'SecureNote | Recorder + processor prototype | ECE 6540')
    canvas.drawRightString(564,29,str(document.page))


destination=ROOT/'docs/Project_Assignment_2.pdf'
document=SimpleDocTemplate(str(destination),pagesize=(612,792),leftMargin=48,rightMargin=48,topMargin=40,bottomMargin=57,title='SecureNote - Recorder and Processor Prototype',author='Michael Grajera')
document.build(story,onFirstPage=decorate,onLaterPages=decorate)
(ROOT/'docs/Project_Assignment_2.md').write_text('# SecureNote - Project Assignment 2\n\n'+'\n'.join(markdown),encoding='utf-8')
print(destination)
