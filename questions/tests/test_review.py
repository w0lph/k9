import json

from cgq.review import apply_reviews


def _q(i, **over):
    return {"id": f"cgq-{i:04d}", "category": "cognition", "difficulty": 1, "answer_type": "numeric", "question": f"Q{i}?",
            "answer": f"A{i}", "evidence": [{"key": "MED:1", "location": "abstract", "quote": "x" * 30}], "status": "validated"} | over


def test_apply_reviews_fix_drop_pass_and_confidence(tmp_path):
    qp = tmp_path / "q.jsonl"
    qp.write_text("\n".join(json.dumps(_q(i)) for i in range(1, 6)) + "\n", encoding="utf-8")
    r1 = tmp_path / "b1.jsonl"
    r1.write_text("\n".join(json.dumps(v) for v in [
        {"id": "cgq-0001", "verdict": "pass", "issue": "", "confidence": "high"},
        {"id": "cgq-0002", "verdict": "fix", "issue": "units", "fix": {"answer": "12.5 years", "difficulty": 2, "evidence": "ignored"}, "confidence": "high"},
        {"id": "cgq-0003", "verdict": "drop", "issue": "unsupported", "confidence": "high"},
        {"id": "cgq-0004", "verdict": "drop", "issue": "meh", "confidence": "low"},
    ]) + "\n", encoding="utf-8")
    out = tmp_path / "v1.jsonl"
    res = apply_reviews(qp, [r1], out, min_confidence="medium")
    rows = {json.loads(line)["id"]: json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()}
    assert res["reviewed"] == 4 and res["unreviewed"] == 1 and res["output_count"] == 4
    assert "cgq-0003" not in rows and "cgq-0004" in rows  # low-confidence drop ignored
    assert rows["cgq-0002"]["answer"] == "12.5 years" and rows["cgq-0002"]["difficulty"] == 2
    assert rows["cgq-0002"]["review"]["changed"] == ["answer", "difficulty"] and "evidence" not in rows["cgq-0002"]["review"]["changed"]
    assert rows["cgq-0001"]["status"] == "reviewed" and rows["cgq-0005"]["status"] == "validated"
    assert res["verdicts"] == {"pass": 1, "fix": 1, "drop": 2}
