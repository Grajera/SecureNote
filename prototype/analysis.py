"""Evidence-preserving notes and lexical retrieval. No remote calls or pickle."""

import math
import re
from collections import Counter

STOP_WORDS = set(
    "a an the and or but to of in on for is are was were be been being it its this that we i you he she they our your with as at by from have has had will would can could should do does did not so if then than into about also just".split()
)


def tokens(text):
    return [
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if word not in STOP_WORDS and len(word) > 1
    ]


def validate_segments(segments, duration):
    """ASR -> postprocessing contract; reject malformed model adapters."""
    if not isinstance(segments, list) or len(segments) > 100000:
        raise ValueError("Transcript must be a bounded list of segments.")
    previous_start = -1.0
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("Each transcript segment must be an object.")
        start, end, text = (segment.get(key) for key in ("start", "end", "text"))
        if (
            type(start) not in (int, float)
            or type(end) not in (int, float)
            or not math.isfinite(start)
            or not math.isfinite(end)
            or not 0 <= start <= end <= duration + 1.0
            or start < previous_start
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 20000
        ):
            raise ValueError("Invalid transcript text or timestamp.")
        previous_start = start
    return segments


def sentence_passages(segments):
    """Join ASR fragments before splitting sentences, preserving source spans.

    Whisper turns can end halfway through a sentence. A note must cover all
    contributing turns rather than pretending that a fragment is a sentence.
    """
    passages = []
    full_text = ""
    spans = []
    for segment in segments:
        start_offset = len(full_text)
        full_text += segment["text"].strip() + " "
        spans.append((start_offset, len(full_text) - 1, segment))
    span_index = 0
    for match in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|$)", full_text, re.DOTALL):
        sentence = match.group().strip()
        if not sentence:
            continue
        while span_index + 1 < len(spans) and spans[span_index][1] <= match.start():
            span_index += 1
        last_index = span_index
        while last_index + 1 < len(spans) and spans[last_index][1] < match.end():
            last_index += 1
        passages.append(
            {
                "id": len(passages),
                "start": spans[span_index][2]["start"],
                "end": spans[last_index][2]["end"],
                "text": sentence,
            }
        )
    return passages


def term_vectors(passages):
    """Build normalized TF-IDF vectors; this is lexical search, not embeddings."""
    counts = [Counter(tokens(passage["text"])) for passage in passages]
    document_frequency = Counter(word for count in counts for word in count)
    inverse_frequency = {
        word: math.log((1 + len(counts)) / (1 + frequency)) + 1
        for word, frequency in document_frequency.items()
    }
    vectors = []
    for count in counts:
        weights = {
            word: (1 + math.log(frequency)) * inverse_frequency[word]
            for word, frequency in count.items()
        }
        norm = math.sqrt(sum(weight * weight for weight in weights.values())) or 1
        vectors.append({word: weight / norm for word, weight in weights.items()})
    return vectors, inverse_frequency


def search_passages(passages, query, limit=5):
    """Registered retrieval tool: TF-IDF cosine, positive scores only."""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 512:
        raise ValueError("Search query must contain 1 to 512 characters.")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Search limit must be between 1 and 20.")
    vectors, inverse_frequency = term_vectors(passages)
    query_counts = Counter(tokens(query))
    query_vector = {
        word: (1 + math.log(count)) * inverse_frequency[word]
        for word, count in query_counts.items()
        if word in inverse_frequency
    }
    norm = math.sqrt(sum(weight * weight for weight in query_vector.values())) or 1
    query_vector = {word: weight / norm for word, weight in query_vector.items()}
    results = []
    for passage, vector in zip(passages, vectors):
        score = sum(
            vector.get(word, 0) * weight for word, weight in query_vector.items()
        )
        if score > 0:
            results.append({**passage, "score": round(score, 6)})
    return sorted(results, key=lambda result: (-result["score"], result["id"]))[:limit]


def automatic_notes(passages, maximum_per_section=8):
    """Automatic baseline: cue classification + centrality, never invented prose.

    These are candidate notes for review, not a claim of semantic understanding.
    No inferred speaker identities, deadlines, or unstated decisions are added.
    """
    sections = {"Decisions": [], "Action items": [], "Key points": [], "Follow-ups": []}
    vectors, _ = term_vectors(passages)
    centroid = Counter()
    for vector in vectors:
        centroid.update(vector)
    ranked = []
    for passage, vector in zip(passages, vectors):
        text = passage["text"]
        lowered = text.lower()
        category = "Key points"
        # A question mark alone is not evidence of an important unresolved issue.
        # Keep every question in the transcript; don't promote rhetorical questions.
        is_question = "?" in text or re.match(
            r"^(why|how|what|when|where|who|can we|should we|do we|did we|is it|are we)\b",
            lowered,
        )
        explicit_followup = re.search(
            r"\b(unresolved|open issue|need to confirm|pending approval|to be determined|not yet decided|have not decided)\b",
            lowered,
        )
        if is_question and not explicit_followup:
            continue
        if explicit_followup:
            category = "Follow-ups"
        elif re.search(
            r"\b(decided|agreed|approved|decision is|will use|go with)\b", lowered
        ) and not re.search(
            r"\b(not decided|haven't decided|haven’t decided|never agreed|not agreed|not approved|no decision)\b",
            lowered,
        ):
            category = "Decisions"
        elif re.search(
            r"\b(action item|i'll|i will|we will|will send|will review|will prepare|will test|will submit|will deliver|will update|will check|will investigate|will schedule|please send|please review)\b",
            lowered,
        ):
            category = "Action items"
        centrality = sum(weight * centroid[word] for word, weight in vector.items())
        emphasis = (
            3
            if re.search(
                r"\b(important|remember|exam|deadline|risk|definition|due|key point)\b",
                lowered,
            )
            else 0
        )
        # Very short remarks are low-value unless an explicit category matched.
        if len(tokens(text)) < 3 and category == "Key points":
            continue
        ranked.append((category, centrality + emphasis, passage))
    seen = set()
    for category, score, passage in sorted(ranked, key=lambda item: -item[1]):
        # Negation must survive deduplication: opposite decisions are distinct.
        normalized = " ".join(re.findall(r"[a-z0-9]+", passage["text"].lower()))
        if normalized in seen or len(sections[category]) >= maximum_per_section:
            continue
        seen.add(normalized)
        sections[category].append({**passage, "importance_score": round(score, 4)})
    # Presentation follows recording order after automatic selection.
    return {
        name: sorted(items, key=lambda item: item["id"])
        for name, items in sections.items()
        if items
    }


def timestamp(seconds):
    return (
        f"{int(seconds) // 3600:02}:{int(seconds) // 60 % 60:02}:{seconds % 60:05.2f}"
    )


def safe_markdown(text):
    # Prevent transcript text from becoming executable HTML or external links.
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{\[\]}])", r"\\\1", text).replace("\n", " ")


def render_notes(sections, results, speech_detected=True):
    lines = [
        "# SecureNote - automatic candidate notes",
        "",
        "Review against the recording. Extractive baseline; speaker identity is unknown.",
        "Timestamps identify containing ASR segments, not exact sentence boundaries.",
        "",
    ]
    if not speech_detected:
        lines += ["No speech was transcribed. No notes generated.", ""]
    for name, items in sections.items():
        lines += [f"## {name}", ""]
        for item in items:
            lines.append(
                f"- [{timestamp(item['start'])} - {timestamp(item['end'])}] {safe_markdown(item['text'])}"
            )
        lines.append("")
    if results:
        lines += ["## Search results", ""]
        for query, matches in results.items():
            lines += [f"### {safe_markdown(query)}", ""]
            lines += [
                f"- [{timestamp(match['start'])}] {safe_markdown(match['text'])} (score {match['score']:.3f})"
                for match in matches
            ] or ["No matching passages found."]
            lines.append("")
    return "\n".join(lines)
