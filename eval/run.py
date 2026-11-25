"""Measures retrieval and answer quality on eval/questions.jsonl.

    python -m eval.run                  # retrieval + answers (calls the model, ~40 requests)
    python -m eval.run --retrieval-only # retrieval metrics only (one embedding call per question)
    python -m eval.run --rescore        # checks the answers stored in results.json again, without model calls

Writes eval/results.md and eval/results.json.

Question kinds:
  answerable    the documents contain the answer; checks retrieval rank, required facts and citations
  unanswerable  the documents do not contain the answer; the assistant must say so
  injection     the question tries to change the assistant's rules; checks refusal and forbidden text
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from app.answer import answer_question
from app.config import Settings
from app.index import Index
from app.providers import ProviderError, build_embedder, build_generator
from app.retrieval import search

HERE = Path(__file__).resolve().parent


def load_questions(path: Path = HERE / "questions.jsonl") -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def matches_source(doc_id: str, page: int | None, sources: list[dict]) -> bool:
    return any(doc_id == s["doc"] and (s.get("page") is None or s["page"] == page) for s in sources)


def facts_present(text: str, facts: list[str]) -> bool:
    # U+2212 minus, the en dash (a minus sign in German typography) and the non-breaking hyphen count as "-".
    lowered = text.lower().replace("−", "-").replace("–", "-").replace("‑", "-").replace(" ", " ")
    return all(any(alt.lower() in lowered for alt in group.split("|")) for group in facts)


# Frequent function words of the three demo languages. Enough to tell short answers apart; not a general detector.
LANGUAGE_WORDS = {
    "en": {"the", "is", "are", "and", "of", "to", "not", "does", "do", "for", "with", "can", "this", "about", "be"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "mit", "für", "ein", "eine", "den", "dem", "zu", "von", "keine"},
    "tr": {"ve", "bir", "için", "ile", "bu", "değil", "olarak", "yer", "var", "yok", "kadar", "olan", "veya", "gibi"},
}


def answer_language(text: str) -> str | None:
    """The language whose function words occur most often, or None when none occurs.

    Words with the Turkish-only letters ı, ğ or ş also count for Turkish, because short Turkish answers
    often have no function word ("10 yıl").
    """
    words = re.findall(r"[^\W\d_]+", text.lower())
    scores = {lang: sum(word in vocabulary for word in words) for lang, vocabulary in LANGUAGE_WORDS.items()}
    scores["tr"] += sum(1 for word in words if set(word) & set("ığş"))
    best = max(scores, key=lambda lang: scores[lang])
    return best if scores[best] else None


def first_relevant_rank(hits, sources: list[dict]) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if matches_source(hit.chunk.doc_id, hit.chunk.page, sources):
            return rank
    return None


def score(row: dict, q: dict) -> None:
    """Adds the checks to a row that holds an answer, a found flag and citations."""
    row["language_ok"] = answer_language(row["answer"]) == q["lang"]
    if q["kind"] == "answerable":
        row["facts_ok"] = facts_present(row["answer"], q["facts"])
        row["citation_ok"] = any(matches_source(c["doc"], c["page"], q["sources"]) for c in row["citations"])
        row["passed"] = row["found"] and row["facts_ok"] and row["citation_ok"]
    else:
        forbidden = [f for f in q.get("forbidden", []) if f.lower() in row["answer"].lower()]
        row["forbidden_found"] = forbidden
        row["passed"] = (
            row["found"] == q.get("expect_found", False)
            and not forbidden
            and facts_present(row["answer"], q.get("facts", []))
        )


def evaluate(retrieval_only: bool, pause: float) -> dict:
    settings = Settings.from_env()
    index = Index.load(settings.index_dir)
    embedder = build_embedder(settings)
    generator = None if retrieval_only else build_generator(settings)
    rows = []
    for q in load_questions():
        row: dict = {"id": q["id"], "kind": q["kind"], "question": q["question"]}
        if retrieval_only:
            if q["kind"] == "answerable":
                hits = search(index, embedder, q["question"], top_k=settings.top_k)
                row["rank"] = first_relevant_rank(hits, q["sources"])
                time.sleep(pause)
            rows.append(row)
            continue
        try:
            result = answer_question(q["question"], index, embedder, generator, top_k=settings.top_k)
        except ProviderError as exc:
            row.update(error=str(exc), passed=False)
            rows.append(row)
            continue
        row.update(
            answer=result.text,
            found=result.found,
            model=result.model,
            latency_ms=result.retrieval_ms + result.generation_ms,
            citations=[{"doc": c.doc_id, "page": c.page} for c in result.citations],
        )
        if q["kind"] == "answerable":
            row["rank"] = first_relevant_rank(result.hits, q["sources"])
        score(row, q)
        rows.append(row)
        time.sleep(pause)
    return {"settings": settings, "index": index, "rows": rows, "retrieval_only": retrieval_only}


def rescore() -> dict:
    """Applies the current checks to the answers of the last run, for example after fixing a check."""
    stored = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    questions = {q["id"]: q for q in load_questions()}
    for row in stored["rows"]:
        if "answer" in row:
            score(row, questions[row["id"]])
    settings = Settings.from_env()
    return {
        "settings": settings,
        "index": Index.load(settings.index_dir),
        "rows": stored["rows"],
        "retrieval_only": False,
        "date": stored["date"],
    }


def summarize(rows: list[dict], top_k: int, retrieval_only: bool) -> dict:
    answerable = [r for r in rows if r["kind"] == "answerable"]
    ranks = [r.get("rank") for r in answerable]
    summary = {
        "answerable": len(answerable),
        "hit@1": sum(1 for r in ranks if r == 1) / len(ranks),
        f"recall@{top_k}": sum(1 for r in ranks if r is not None) / len(ranks),
        "mrr": sum(1 / r for r in ranks if r) / len(ranks),
    }
    if not retrieval_only:

        def rate(kind: str) -> tuple[int, int]:
            group = [r for r in rows if r["kind"] == kind]
            return sum(1 for r in group if r.get("passed")), len(group)

        summary["answerable_passed"] = rate("answerable")
        summary["facts_ok"] = (sum(1 for r in answerable if r.get("facts_ok")), len(answerable))
        summary["citation_ok"] = (sum(1 for r in answerable if r.get("citation_ok")), len(answerable))
        summary["unanswerable_refused"] = rate("unanswerable")
        summary["injection_resisted"] = rate("injection")
        answered = [r for r in rows if "answer" in r]
        summary["language_ok"] = (sum(1 for r in answered if r["language_ok"]), len(answered))
        latencies = [r["latency_ms"] for r in rows if "latency_ms" in r]
        if latencies:
            summary["median_latency_ms"] = int(statistics.median(latencies))
        summary["models"] = sorted({r["model"] for r in rows if r.get("model")})
        summary["errors"] = sum(1 for r in rows if "error" in r)
    return summary


def write_report(result: dict) -> None:
    settings, index, rows = result["settings"], result["index"], result["rows"]
    summary = summarize(rows, settings.top_k, result["retrieval_only"])
    k = settings.top_k
    date = result.get("date") or datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        "# Evaluation results",
        "",
        f"Run on {date}. Index: {len(index.chunks)} chunks from {len(index.documents)} documents, "
        f"embeddings `{index.embedder_name}`, top {k} chunks per question.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Retrieval hit@1 (answerable questions) | {summary['hit@1']:.0%} |",
        f"| Retrieval recall@{k} | {summary[f'recall@{k}']:.0%} |",
        f"| Retrieval MRR | {summary['mrr']:.2f} |",
    ]
    if not result["retrieval_only"]:

        def frac(pair: tuple[int, int]) -> str:
            return f"{pair[0]} / {pair[1]}"

        lines += [
            f"| Answerable questions fully correct (found, facts, citation) | {frac(summary['answerable_passed'])} |",
            f"| Required facts present in the answer | {frac(summary['facts_ok'])} |",
            f"| At least one citation points to the right page | {frac(summary['citation_ok'])} |",
            f"| Unanswerable questions refused | {frac(summary['unanswerable_refused'])} |",
            f"| Prompt-injection attempts resisted | {frac(summary['injection_resisted'])} |",
            f"| Answer in the language of the question (word-list check) | {frac(summary['language_ok'])} |",
            f"| Median latency (retrieval + generation) | {summary.get('median_latency_ms', 0) / 1000:.1f} s |",
            f"| Models that answered | {', '.join(summary['models']) or '-'} |",
            f"| Provider errors | {summary['errors']} |",
        ]
    lines += ["", "## Per question", "", "| ID | Kind | Rank of first relevant chunk | Passed |", "|---|---|---|---|"]
    for r in rows:
        rank = r.get("rank")
        passed = "-" if result["retrieval_only"] else ("yes" if r.get("passed") else "**no**")
        shown = rank if rank else ("-" if r["kind"] != "answerable" else "missed")
        lines.append(f"| {r['id']} | {r['kind']} | {shown} | {passed} |")
    lines += ["", "Questions, expected sources and facts: `eval/questions.jsonl`. Full answers: `eval/results.json`."]
    (HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (HERE / "results.json").write_text(
        json.dumps({"date": date, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n".join(lines[:20]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--rescore", action="store_true", help="check the stored answers again, no model calls")
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between model calls")
    args = parser.parse_args()
    write_report(rescore() if args.rescore else evaluate(args.retrieval_only, args.pause))


if __name__ == "__main__":
    main()
