"""Local transcript RAG: python ask.py ask RUN_DIRECTORY 'Your question'."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='SecureNote local retrieval-augmented answers')
    commands = parser.add_subparsers(dest='command', required=True)
    download = commands.add_parser('download-model', help='SETUP ONLY: download the local answer model')
    download.add_argument('--destination', type=Path, default=Path('models/flan-t5-small'))
    ask = commands.add_parser('ask', help='Retrieve transcript context and generate a local answer')
    ask.add_argument('run_directory', type=Path)
    ask.add_argument('question')
    ask.add_argument('--model-dir', type=Path, default=Path('models/flan-t5-small'))
    ask.add_argument('--output', type=Path, default=Path('rag-runs'))
    ask.add_argument('--log-content', action='store_true', help='Synthetic examples only')
    ask.add_argument('--inject-empty-retrieval', action='store_true', help='Failure test')
    args = parser.parse_args()
    from prototype.rag import MODEL_REPOSITORY, MODEL_REVISION, answer_from_directory
    if args.command == 'download-model':
        os.environ.pop('HF_HUB_OFFLINE', None)
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        from huggingface_hub import snapshot_download
        snapshot_download(MODEL_REPOSITORY, revision=MODEL_REVISION, local_dir=args.destination,
            allow_patterns=['config.json', 'generation_config.json', 'model.safetensors', 'tokenizer.json',
                            'tokenizer_config.json', 'special_tokens_map.json', 'spiece.model'])
        print('Local answer model ready:', args.destination)
        return 0
    directory, result, summary = answer_from_directory(args.run_directory, args.question,
        args.model_dir, args.output, log_content=args.log_content, inject_empty_retrieval=args.inject_empty_retrieval)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('Run directory:', directory)
    return 2 if summary['status'] == 'failed' else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError):
        raise SystemExit('Unable to read the transcript. Supply a completed processing result directory.')
