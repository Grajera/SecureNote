"""Local retrieval-augmented generation over one recording's transcript.

Retrieval supplies the context consumed by a real generative language model.
No hosted inference, arbitrary tool execution, or model-generated source paths.
"""
import hashlib
import json
import math
import os
import platform
import re
import threading
import time
from functools import lru_cache
from pathlib import Path

from .analysis import safe_markdown, search_passages, sentence_passages, timestamp, validate_segments
from .pipeline import RunLog, create_run, save_json

MODEL_REPOSITORY = 'google/flan-t5-small'
MODEL_REVISION = '0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab'
MAX_CHUNKS = 3
MIN_SCORE = 0.20
MAX_CHUNK_CHARS = 600
MAX_PROMPT_TOKENS = 512
MAX_NEW_TOKENS = 64
NOT_FOUND = 'Not found in this recording.'
GENERATION_LOCK = threading.Lock()


def validate_question(question):
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 512:
        raise ValueError('Question must contain 1 to 512 characters.')
    return question.strip()


def retrieve(segments, question, source):
    """Bound sentence chunks, then rank them with the existing TF-IDF retriever."""
    passages = []
    for passage in sentence_passages(segments):
        # Long sentences are split at word boundaries. All fragments retain the
        # containing ASR interval rather than claiming exact word alignment.
        words = passage['text'].split()
        fragment = ''
        for word in words:
            if len(word) > MAX_CHUNK_CHARS:
                raise ValueError('Transcript contains an oversized unbroken word.')
            if fragment and len(fragment) + 1 + len(word) > MAX_CHUNK_CHARS:
                passages.append({'id': len(passages), 'start': passage['start'], 'end': passage['end'], 'text': fragment})
                fragment = ''
            fragment = (fragment + ' ' + word).strip()
        if fragment:
            passages.append({'id': len(passages), 'start': passage['start'], 'end': passage['end'], 'text': fragment})
    hits = search_passages(passages, question, MAX_CHUNKS)
    return [{**hit, 'source': source} for hit in hits if hit['score'] >= MIN_SCORE]


def validate_chunks(chunks):
    if not isinstance(chunks, list) or len(chunks) > MAX_CHUNKS:
        raise ValueError('Retriever must return a list of at most three chunks.')
    seen = set()
    for chunk in chunks:
        if not isinstance(chunk, dict) or set(chunk) != {'id', 'text', 'start', 'end', 'source', 'score'}:
            raise ValueError('Invalid retrieval chunk fields.')
        if type(chunk['id']) is not int or chunk['id'] < 0 or chunk['id'] in seen:
            raise ValueError('Invalid retrieval chunk ID.')
        seen.add(chunk['id'])
        if not isinstance(chunk['text'], str) or not 1 <= len(chunk['text'].strip()) <= MAX_CHUNK_CHARS:
            raise ValueError('Invalid retrieval text.')
        if not isinstance(chunk['source'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', chunk['source']):
            raise ValueError('Invalid source ID.')
        if any(type(chunk[k]) not in (int, float) or not math.isfinite(chunk[k]) for k in ('start', 'end', 'score')):
            raise ValueError('Invalid retrieval score or timestamp.')
        if not 0 <= chunk['start'] <= chunk['end'] <= 7201 or not MIN_SCORE <= chunk['score'] <= 1.000001:
            raise ValueError('Retrieval value is outside its permitted range.')
    return chunks


@lru_cache(maxsize=1)
def load_answer_model(model_directory):
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    directory = Path(model_directory).resolve()
    required = ('config.json', 'model.safetensors', 'tokenizer.json', 'tokenizer_config.json')
    if not directory.is_dir() or not all((directory / name).is_file() for name in required):
        raise ValueError('RAG model is missing. Run: python ask.py download-model')
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    import torch
    torch.set_num_threads(4)
    tokenizer = AutoTokenizer.from_pretrained(str(directory), local_files_only=True, trust_remote_code=False)
    model = AutoModelForSeq2SeqLM.from_pretrained(str(directory), local_files_only=True,
        trust_remote_code=False, use_safetensors=True).to('cpu').eval()
    return tokenizer, model


def build_prompt(question, chunks, tokenizer):
    validate_question(question)
    validate_chunks(chunks)
    if not chunks:
        return None, [], 0
    def prompt_for(selected):
        context = '\n'.join(chunk['text'] for chunk in selected)
        return ('Answer the question using only the context. If the answer is not in the context, say "not found".\n'
                'Context: ' + context + '\nQuestion: ' + question + '\nAnswer:')
    if len(tokenizer.encode(prompt_for([]))) > 160:
        raise ValueError('Question uses too many tokens; please shorten it.')
    selected = []
    for chunk in chunks:
        candidate = prompt_for(selected + [chunk])
        if len(tokenizer.encode(candidate)) <= MAX_PROMPT_TOKENS:
            selected.append(chunk)
    if not selected:
        raise ValueError('No complete retrieval chunk fits the model context.')
    prompt = prompt_for(selected)
    return prompt, selected, len(tokenizer.encode(prompt))


def generate_answer(prompt, tokenizer, model):
    import torch
    encoded = tokenizer(prompt, return_tensors='pt', truncation=False)
    if encoded['input_ids'].shape[1] > MAX_PROMPT_TOKENS:
        raise ValueError('Prompt exceeds the model token budget.')
    with torch.inference_mode():
        output = model.generate(**encoded, max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False, num_beams=1, max_time=30)
    if output.shape[1] >= MAX_NEW_TOKENS + 1 and int(output[0, -1]) != tokenizer.eos_token_id:
        raise ValueError('Answer reached its generation limit; ask a narrower question.')
    return tokenizer.decode(output[0], skip_special_tokens=True)


def normalize(text):
    return ' '.join(re.findall(r'\w+', text.casefold()))


def postprocess_answer(raw_answer, chunks):
    """Keep short answers only when their wording occurs in supplied evidence.

    This is a conservative lexical check, not proof that an answer is correct.
    Citations are assigned by code to retrieved passages, never invented by T5.
    """
    if not isinstance(raw_answer, str) or not 1 <= len(raw_answer.strip()) <= 2000:
        raise ValueError('Model returned an empty, oversized or malformed answer.')
    answer = ' '.join(raw_answer.split())
    normalized = normalize(answer)
    if normalized in ('not found', 'not found in this recording', 'unknown', 'unanswerable'):
        return NOT_FOUND, [], 'not_found'
    sources = [chunk for chunk in chunks if normalized and
        (' ' + normalized + ' ') in (' ' + normalize(chunk['text']) + ' ')]
    if not sources:
        return 'The model response could not be matched to the retrieved evidence. Review the passages below.', [], 'needs_review'
    return answer, sources, 'answered'


def answer_question(segments, duration, question, model_directory, output_root,
                    source='recording', log_content=False, inject_empty_retrieval=False):
    """Validate -> retrieve -> build context -> generate -> postprocess -> output."""
    directory = create_run(output_root)
    log = RunLog(directory, log_content)
    summary = {'schema_version': '1.0', 'run_id': directory.name, 'source': source,
        'status': 'running', 'model': {'name': MODEL_REPOSITORY, 'device': 'cpu', 'compute_type': 'float32'},
        'runtime': {'os': platform.system(), 'python': platform.python_version(), 'cpu_threads': 4},
        'content_logging': log_content, 'failure_injection': inject_empty_retrieval}
    result = {'answer': None, 'sources': [], 'retrieved': []}
    locked = False
    try:
        log.emit('input', 'received', input_characters=len(question) if isinstance(question, str) else 0)
        with log.stage('validation'):
            question = validate_question(question)
            if type(duration) not in (float, int) or not math.isfinite(duration) or not 0 < duration <= 7200:
                raise ValueError('Invalid recording duration.')
            validate_segments(segments, duration)
            if not isinstance(source, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', source):
                raise ValueError('Invalid source ID.')
            summary['input_characters'] = len(question)
            summary['transcript_characters'] = sum(len(segment['text']) for segment in segments)
        with log.stage('retrieval'):
            chunks = [] if inject_empty_retrieval else retrieve(segments, question, source)
            validate_chunks(chunks)
            result['retrieved'] = chunks
            summary['retrieved_count'] = len(chunks)
            log.emit('retrieval', 'result', chunk_count=len(chunks), threshold=MIN_SCORE,
                scores=[chunk['score'] for chunk in chunks])
        if not chunks:
            result.update(answer=NOT_FOUND, sources=[])
            summary['status'] = 'not_found'
            log.emit('prompt_building', 'skipped', reason='no_evidence')
            log.emit('model_inference', 'skipped', reason='no_evidence')
        else:
            locked = GENERATION_LOCK.acquire(blocking=False)
            if not locked:
                raise RuntimeError('Another local answer is being generated. Try again shortly.')
            with log.stage('model_loading'):
                tokenizer, model = load_answer_model(str(Path(model_directory).resolve()))
            with log.stage('prompt_building'):
                prompt, supplied, token_count = build_prompt(question, chunks, tokenizer)
                summary['prompt_tokens'] = token_count
                summary['supplied_count'] = len(supplied)
                result['retrieved'] = supplied
                log.emit('prompt_building', 'result', prompt_tokens=token_count,
                    chunk_ids=[chunk['id'] for chunk in supplied])
            with log.stage('model_inference'):
                raw_answer = generate_answer(prompt, tokenizer, model)
                log.emit('model_inference', 'result', output_characters=len(raw_answer))
            with log.stage('postprocessing'):
                answer, sources, status = postprocess_answer(raw_answer, supplied)
                result.update(answer=answer, sources=sources)
                summary['status'] = status
        if not chunks:
            with log.stage('postprocessing'):
                log.emit('postprocessing', 'result', status='not_found', source_count=0)
        with log.stage('output'):
            result.update(question=question, status=summary['status'], run_id=directory.name)
            save_json(directory / 'answer.json', result)
            lines = ['# Recording answer', '', '**Question:** ' + safe_markdown(question), '',
                safe_markdown(result['answer']), '', '## Retrieved evidence', '']
            lines += [f"- [{timestamp(chunk['start'])}] {safe_markdown(chunk['text'])}" for chunk in result['retrieved']]
            (directory / 'answer.md').write_text('\n'.join(lines), encoding='utf-8')
            log.emit('output', 'result', files=['answer.json', 'answer.md'],
                status=summary['status'], source_count=len(result['sources']),
                answer_characters=len(result['answer']),
                answer_sha256=hashlib.sha256(result['answer'].encode()).hexdigest(),
                **({'answer': result['answer']} if log_content else {}))
    except Exception as error:
        summary.update(status='failed', error_type=type(error).__name__,
            error=str(error) if isinstance(error, (ValueError, RuntimeError)) else
                'Local RAG failed. Check requirements-rag.txt and the local model files.')
        result.update(status='failed', error=summary['error'], run_id=directory.name)
        log.emit('run', 'failed', error_type=type(error).__name__)
    finally:
        if locked:
            GENERATION_LOCK.release()
        summary['latency_ms'] = round((time.perf_counter() - log.started) * 1000, 2)
        result['latency_ms'] = summary['latency_ms']
        save_json(directory / 'summary.json', summary)
        log.emit('run', 'finished', status=summary['status'], latency_ms=summary['latency_ms'])
    return directory, result, summary


def answer_from_directory(run_directory, question, model_directory, output_root, **kwargs):
    directory = Path(run_directory)
    transcript = json.loads((directory / 'transcript.json').read_text(encoding='utf-8'))
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    return answer_question(transcript['segments'], summary['decoded_audio']['duration_seconds'],
        question, model_directory, output_root, source=directory.name, **kwargs)
