"""RAG contracts and refusal behavior; real generation is exercised by the demo."""
import json
import tempfile
import unittest
from unittest.mock import patch
from prototype.rag import (answer_question, build_prompt, postprocess_answer,
    retrieve, validate_chunks, validate_question, NOT_FOUND)

SEGMENTS = [{'start': 0., 'end': 5., 'text': 'Alice will send the revised budget by Friday.'}]

class RagTests(unittest.TestCase):
    def test_question_and_chunk_boundaries(self):
        for bad in ('', 'x' * 513, None, 123):
            with self.assertRaises(ValueError): validate_question(bad)
        chunks = retrieve(SEGMENTS, 'When is the budget due?', 'test')
        self.assertEqual(len(chunks), 1)
        validate_chunks(chunks)
        for key, value in [('score', float('nan')), ('source', '../escape'), ('text', ''), ('start', -1)]:
            with self.assertRaises(ValueError): validate_chunks([{**chunks[0], key: value}])

    def test_retrieved_evidence_reaches_prompt(self):
        chunks = retrieve(SEGMENTS, 'budget', 'test')
        class Tokenizer:
            def encode(self, text): return text.split()
        prompt, supplied, count = build_prompt('When is the budget due?', chunks, Tokenizer())
        self.assertIn(SEGMENTS[0]['text'], prompt)
        self.assertIn('When is the budget due?', prompt)
        self.assertEqual(supplied, chunks)
        self.assertLessEqual(count, 512)

    def test_missing_evidence_skips_model_and_logs_explicit_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch('prototype.rag.load_answer_model') as model:
                directory, result, summary = answer_question(SEGMENTS, 5, 'quartz volcano',
                    'missing-model', temporary, source='test')
            model.assert_not_called()
            self.assertEqual(result['answer'], NOT_FOUND)
            self.assertEqual(summary['status'], 'not_found')
            events = [json.loads(line) for line in (directory / 'run.jsonl').read_text().splitlines()]
            self.assertTrue(any(e['stage'] == 'model_inference' and e['event'] == 'skipped' for e in events))
            self.assertTrue((directory / 'answer.json').is_file())

    def test_malformed_retriever_output_fails_before_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch('prototype.rag.retrieve', return_value=[{'text': 123}]), patch('prototype.rag.load_answer_model') as model:
                directory, result, summary = answer_question(SEGMENTS, 5, 'budget', 'missing', temporary)
            model.assert_not_called()
            self.assertEqual(summary['status'], 'failed')
            self.assertEqual(summary['error_type'], 'ValueError')
            self.assertFalse((directory / 'answer.json').exists())

    def test_postprocessing_does_not_invent_citations_or_accept_unmatched_answer(self):
        chunks = retrieve(SEGMENTS, 'budget', 'test')
        answer, sources, status = postprocess_answer('  by Friday\n', chunks)
        self.assertEqual((answer, status), ('by Friday', 'answered'))
        self.assertEqual(sources[0]['start'], 0)
        self.assertEqual(postprocess_answer('by Monday', chunks)[2], 'needs_review')
        with self.assertRaises(ValueError): postprocess_answer({'answer': 'Friday'}, chunks)

    def test_default_logs_do_not_duplicate_question_or_answer(self):
        class Tokenizer:
            def encode(self, text): return text.split()
        with tempfile.TemporaryDirectory() as temporary:
            with patch('prototype.rag.load_answer_model', return_value=(Tokenizer(), object())), patch('prototype.rag.generate_answer', return_value='by Friday'):
                directory, result, summary = answer_question(SEGMENTS, 5, 'When is the budget due?', 'missing', temporary)
            logs = (directory / 'run.jsonl').read_text()
            self.assertNotIn('When is the budget due?', logs)
            self.assertNotIn('by Friday', logs)
            self.assertEqual(result['status'], 'answered')

    def test_model_abstention_does_not_claim_recording_has_no_answer(self):
        chunks = retrieve(SEGMENTS, 'budget', 'test')
        answer, sources, status = postprocess_answer('not found', chunks)
        self.assertEqual(status, 'needs_review')
        self.assertIn('Could not answer', answer)
        self.assertEqual(sources, [])

    def test_retry_is_bounded_and_uses_strongest_evidence(self):
        class Tokenizer:
            def encode(self, text): return text.split()
        for responses, expected in [(['not found', 'by Friday'], 'answered'),
                                    (['not found', 'not found'], 'needs_review'),
                                    (['not found', 'by Monday'], 'needs_review')]:
            with self.subTest(responses=responses), tempfile.TemporaryDirectory() as temporary:
                with patch('prototype.rag.load_answer_model', return_value=(Tokenizer(), object())), \
                     patch('prototype.rag.generate_answer', side_effect=responses) as generate:
                    directory, result, summary = answer_question(SEGMENTS, 5,
                        'When is the budget due?', 'missing', temporary)
                self.assertEqual(generate.call_count, 2)
                self.assertIn(SEGMENTS[0]['text'], generate.call_args.args[0])
                self.assertEqual(result['status'], expected)
                self.assertEqual(summary['retry_count'], 1)
                self.assertEqual(len(result['retrieved']), 1)
                logs = (directory / 'run.jsonl').read_text()
                self.assertNotIn('raw_answer', logs)
                self.assertNotIn('by Friday', logs)

if __name__ == '__main__': unittest.main()
