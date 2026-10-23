"""Reproduce three media -> ASR -> retrieval -> generation runs and a failure."""
import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prototype.rag import answer_from_directory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('demo-assignment'))
    parser.add_argument('--model-dir', type=Path, default=Path('models/base.en'))
    parser.add_argument('--rag-model-dir', type=Path, default=Path('models/flan-t5-small'))
    args = parser.parse_args()
    output = args.output.resolve()
    subprocess.run([sys.executable, str(ROOT / 'tools/run_distributed_demo.py'),
        '--output', str(output), '--model-dir', str(args.model_dir.resolve())], check=True)
    evidence = json.loads((output / 'evidence.json').read_text(encoding='utf-8'))
    questions = ['When will Alice send the revised budget?',
                 'What controls how much future rewards matter?',
                 'Where did we agree to keep the original recording?']
    evidence['rag'] = []
    for run, question in zip(evidence['runs'], questions):
        transcript = output / 'laptop/results' / run['job']['result_directory']
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('Network is disabled during RAG')):
            directory, result, summary = answer_from_directory(transcript, question,
                args.rag_model_dir, output / 'answers', log_content=True)
        evidence['rag'].append({'media': run['input'], 'question': question,
            'result_directory': str(directory.relative_to(output)), 'result': result, 'summary': summary})
        print(run['input'], result['status'], repr(result['answer']), summary['latency_ms'], 'ms')
        if result['status'] != 'answered':
            raise RuntimeError('RAG example did not produce a grounded answer: ' + str(result))
    first_run = output / 'laptop/results' / evidence['runs'][0]['job']['result_directory']
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('Network is disabled during RAG')):
        directory, result, summary = answer_from_directory(first_run, questions[0], args.rag_model_dir,
            output / 'answers', log_content=True, inject_empty_retrieval=True)
    assert result['status'] == 'not_found' and not result['sources'], result
    evidence['rag_failure'] = {'change': 'Replace retrieved chunks with an empty list before prompt building',
        'result_directory': str(directory.relative_to(output)), 'result': result, 'summary': summary}
    evidence['rag_network_check'] = 'Python socket.connect blocked during all four RAG runs'
    (output / 'assignment-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print('Assignment evidence:', output / 'assignment-evidence.json')


if __name__ == '__main__':
    main()
