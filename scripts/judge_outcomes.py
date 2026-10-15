"""Run a secondary LLM judge or compare its labels to reconciled human outcomes."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from masguardeval.live import GeminiNativeClient, OllamaChatClient, OpenAICompatibleChatClient, OpenAIResponsesClient
from masguardeval.outcome_judge import PROMPT_VERSION, compare_judge_to_humans, council_row, judge_row
from masguardeval.study import canonical_hash, read_jsonl


def save_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def endpoint_identity(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("Invalid model endpoint URL")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    judge = commands.add_parser("judge")
    judge.add_argument("--packet", required=True)
    judge.add_argument("--out", required=True)
    judge.add_argument("--provider", required=True, choices=("openai", "ollama", "gemini", "groq"))
    judge.add_argument("--model", required=True)
    judge.add_argument("--base-url")
    judge.add_argument("--seed", type=int, default=23)
    judge.add_argument("--max-output-tokens", type=int, default=512)
    judge.add_argument("--resume", action="store_true")
    judge.add_argument("--fail-fast", action="store_true")
    council = commands.add_parser("council")
    council.add_argument("--packet", required=True)
    council.add_argument("--out", required=True)
    council.add_argument("--openai-model", default="gpt-4.1-mini")
    council.add_argument("--gemini-model", default="gemini-3.8-flash")
    council.add_argument("--groq-model", default="openai/gpt-oss-20b")
    council.add_argument("--resume", action="store_true")
    compare = commands.add_parser("compare")
    for name in ("packet", "private-map", "judgments", "human-outcomes", "out"):
        compare.add_argument("--" + name, required=True)
    args = parser.parse_args()

    if args.command == "compare":
        packet = read_jsonl(args.packet)
        mapping = json.loads(Path(args.private_map).read_text(encoding="utf-8"))
        judgments = json.loads(Path(args.judgments).read_text(encoding="utf-8"))
        human = json.loads(Path(args.human_outcomes).read_text(encoding="utf-8"))
        output = Path(args.out)
        if output.exists():
            parser.error(f"Output exists: {output}")
        result = compare_judge_to_humans(packet, mapping, judgments["judgments"], human)
        save_json(output, result)
        print(f"Compared {result['model_judgment_rows']} model labels to human outcomes")
        return

    packet = read_jsonl(args.packet)
    if not packet or len({row.get("blind_id") for row in packet}) != len(packet):
        parser.error("Packet must have unique blind IDs")
    output = Path(args.out)
    if output.parent.resolve() == Path(args.packet).parent.resolve():
        parser.error("Keep model judgments outside the human reviewer packet directory")
    if args.command == "council":
        models = {"openai": args.openai_model, "gemini": args.gemini_model, "groq": args.groq_model}
        identity = {"packet_sha256": canonical_hash(packet), "prompt_version": PROMPT_VERSION,
                    "provider": "three_provider_council", "models": models}
    else:
        identity = {"packet_sha256": canonical_hash(packet), "prompt_version": PROMPT_VERSION,
                    "provider": args.provider, "model": args.model,
                    "base_url": endpoint_identity(args.base_url),
                    "seed": args.seed if args.provider == "ollama" else None,
                    "max_output_tokens": args.max_output_tokens if args.provider == "ollama" else None}
    if output.exists():
        if not args.resume:
            parser.error(f"Output exists: {output}; use --resume")
        report = json.loads(output.read_text(encoding="utf-8"))
        if any(report.get(key) != value for key, value in identity.items()):
            parser.error("Existing judge report does not match packet or model settings")
    else:
        if args.resume:
            parser.error("Cannot resume a missing judge report")
        report = {**identity, "created_at": datetime.now(timezone.utc).isoformat(),
                  "status": "partial", "judgments": [], "failures": [],
                  "interpretation": "Secondary model judgments; never human or primary labels."}
    if args.command == "council":
        credentials = {name: os.environ.get(name.upper() + "_API_KEY") for name in ("openai", "gemini", "groq")}
        missing = [name.upper() + "_API_KEY" for name, value in credentials.items() if not value]
        if missing:
            parser.error("Missing environment variables: " + ", ".join(missing))
        members = [
            ("openai", models["openai"], OpenAIResponsesClient(models["openai"], api_key=credentials["openai"]), {"name": models["openai"]}),
            ("gemini", models["gemini"], GeminiNativeClient(models["gemini"], api_key=credentials["gemini"]),
                {"name": models["gemini"]}),
            ("groq", models["groq"], OpenAICompatibleChatClient(models["groq"], api_key=credentials["groq"],
                base_url="https://api.groq.com/openai/v1"), {"name": models["groq"]}),
        ]
        metadata = None
    elif args.provider == "ollama":
        client = OllamaChatClient(args.model, base_url=args.base_url or "http://127.0.0.1:11434",
                                  seed=args.seed, max_output_tokens=args.max_output_tokens)
        metadata = client.model_metadata()
    elif args.provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            parser.error("Missing GEMINI_API_KEY")
        client = GeminiNativeClient(args.model, api_key=key)
        metadata = {"name": args.model}
    elif args.provider == "groq":
        key_name = args.provider.upper() + "_API_KEY"
        key = os.environ.get(key_name)
        if not key:
            parser.error(f"Missing {key_name}")
        url = args.base_url or "https://api.groq.com/openai/v1"
        client = OpenAICompatibleChatClient(args.model, api_key=key, base_url=url)
        metadata = {"name": args.model}
    else:
        client = OpenAIResponsesClient(args.model, base_url=args.base_url)
        metadata = {"name": args.model}
    if metadata is not None and report.get("model_metadata") not in (None, metadata):
        parser.error("Resolved model metadata changed since the earlier run")
    if metadata is not None:
        report["model_metadata"] = metadata
    done = {item["blind_id"] for item in report["judgments"]}
    if len(done) != len(report["judgments"]):
        parser.error("Duplicate completed model judgments")
    for row in packet:
        if row["blind_id"] in done:
            continue
        try:
            result = (council_row(row, members) if args.command == "council" else
                      judge_row(row, client, provider=args.provider, model=args.model, model_metadata=metadata))
            report["judgments"].append(result)
            print(f"Judged {row['blind_id']}")
        except Exception as exc:
            report["failures"].append({"blind_id": row["blind_id"], "error_type": type(exc).__name__,
                                       "recorded_at": datetime.now(timezone.utc).isoformat()})
            print(f"Judge failed for {row['blind_id']}: {type(exc).__name__}")
            if getattr(args, "fail_fast", False):
                report["status"] = "partial"
                save_json(output, report)
                raise
        if len(report["judgments"]) != len(packet):
            report["status"] = "partial"
        elif any(item.get("uncertain") for item in report["judgments"]):
            report["status"] = "complete_with_unresolved"
        else:
            report["status"] = "complete"
        save_json(output, report)


if __name__ == "__main__":
    main()
