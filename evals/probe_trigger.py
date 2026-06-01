#!/usr/bin/env python3
"""真實路由觸發率探針（faithful trigger probe）for 已安裝的多 skill。

為什麼不直接用 skill-creator-advanced/run_eval.py：它寫一個臨時 slash-command
（描述＝被測 skill description）測「未安裝的 description 會不會觸發」。但本專案的
company-ops 等 skill 已安裝，模型會載入「真的」skill、不是臨時 command，run_eval 的
clean_name 比對因此漏判（assistant_other_tool:Skill）。

本探針改測「真實路由」：開一個乾淨 workspace（不帶專案 hooks / CLAUDE.md 干擾）、把
真的 .claude/skills symlink 進去，跑 `claude -p <query>`，偵測模型實際載入哪個**真**
skill（Skill tool_use 的 skill 參數）與讀了哪個 reference（Read /references/*.md）。
→ 直接驗「ops query 載 company-ops、social/design query 不載 company-ops」。

訂閱安全：spawn `claude -p`（非 API）、子程序 env 去掉 CLAUDECODE + ANTHROPIC_API_KEY。

用法：
  python3 evals/probe_trigger.py --eval-set evals/company-ops-trigger.json \
      --target-skill company-ops --runs 2 --workers 4 --output /tmp/probe_out.json
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = "/mnt/d/gitDir/sme-ai-kit"


def run_one(query: str, cwd: str, timeout: int, target: str) -> dict:
    cmd = ["claude", "-p", query, "--output-format", "stream-json",
           "--verbose", "--include-partial-messages"]
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY", "SME_FLOOR", "SME_NOTIFIER")}
    skills, refs = [], []
    start = time.time()
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {"error": "claude CLI not found", "skills": [], "refs": [], "loaded_target": False}
    try:
        for line in p.stdout:
            if time.time() - start > timeout:
                break
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "assistant":
                for c in ev.get("message", {}).get("content", []):
                    if c.get("type") != "tool_use":
                        continue
                    name, inp = c.get("name", ""), (c.get("input") or {})
                    if name == "Skill":
                        s = str(inp.get("skill", "") or inp.get("command", "")).strip()
                        if s:
                            skills.append(s)
                    elif name == "Read":
                        fp = str(inp.get("file_path", ""))
                        if "/references/" in fp and fp.endswith(".md"):
                            refs.append(fp.split("/references/")[-1])
            if skills:  # 路由已決定（第一個 Skill 載入），停
                break
    finally:
        if p.poll() is None:
            p.kill()
            try:
                p.wait(timeout=5)
            except Exception:
                pass
        if p.stdout:
            p.stdout.close()
    loaded = any(target in s for s in skills)
    return {"skills": skills, "refs": refs, "loaded_target": loaded,
            "dur": round(time.time() - start, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", required=True)
    ap.add_argument("--skills-src", default=f"{REPO}/.claude/skills")
    ap.add_argument("--workspace", default="/tmp/sme_trigger_probe")
    ap.add_argument("--target-skill", default="company-ops")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--output", default=None)
    a = ap.parse_args()

    data = json.loads(Path(a.eval_set).read_text(encoding="utf-8"))
    queries = data["queries"] if isinstance(data, dict) else data

    # 乾淨 workspace：symlink 真 skills、無 settings(hooks)/CLAUDE.md
    ws = Path(a.workspace)
    sk = ws / ".claude" / "skills"
    if sk.is_symlink() or sk.exists():
        if sk.is_symlink():
            sk.unlink()
        else:
            shutil.rmtree(sk)
    sk.parent.mkdir(parents=True, exist_ok=True)
    sk.symlink_to(a.skills_src)

    jobs = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        fut = {}
        for q in queries:
            for _ in range(a.runs):
                fut[ex.submit(run_one, q["query"], str(ws), a.timeout, a.target_skill)] = q["id"]
        per = {}
        meta = {q["id"]: q for q in queries}
        for f in as_completed(fut):
            per.setdefault(fut[f], [])
            try:
                per[fut[f]].append(f.result())
            except Exception as e:
                per[fut[f]].append({"error": str(e), "skills": [], "refs": [], "loaded_target": False})

    rows, tp, fp, tn, fn = [], 0, 0, 0, 0
    for qid, runs in per.items():
        q = meta[qid]
        n = len(runs)
        loaded = sum(1 for r in runs if r.get("loaded_target"))
        rate = loaded / n if n else 0.0
        should = bool(q.get("should_trigger"))
        ok = (rate >= a.threshold) == should
        if should and rate >= a.threshold: tp += 1
        elif should: fn += 1
        elif rate >= a.threshold: fp += 1
        else: tn += 1
        seen = sorted({s for r in runs for s in r.get("skills", [])})
        refs = sorted({x for r in runs for x in r.get("refs", [])})
        rows.append({"id": qid, "query": q["query"], "should_trigger": should,
                     "target_load_rate": round(rate, 3), "ok": ok,
                     "skills_seen": seen, "refs_seen": refs, "runs": runs})

    rows.sort(key=lambda r: r["id"])
    total = len(rows); passed = sum(1 for r in rows if r["ok"])
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    out = {"target_skill": a.target_skill, "total": total, "passed": passed,
           "failed": total - passed,
           "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
                         "precision": round(prec, 3), "recall": round(rec, 3)},
           "results": rows}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if a.output:
        Path(a.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[{a.target_skill}] pass {passed}/{total} | P={prec:.0%} R={rec:.0%} | TP{tp} FP{fp} TN{tn} FN{fn}", file=sys.stderr)
    for r in rows:
        mark = "OK " if r["ok"] else "XX "
        print(f"  {mark}{r['id']:18s} load={r['target_load_rate']:.0%} expect={int(r['should_trigger'])} seen={r['skills_seen']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
