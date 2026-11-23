"""AIの会議を1回ぶん自動で作る（Claude APIを使用）。

personas.json の人格どうしで議題について話し合わせ、最後に会長が
A案／B案にまとめて meetings/YYYY-MM-DD.json に保存する。
前回の会議の議題と投票結果を覚えていて、話の中で触れる。

準備:  pip install anthropic
       export ANTHROPIC_API_KEY=...   （GitHub Actions では Secrets に登録）
使い方:
  python generate_meeting.py                      # agendas.json の次の議題で会議
  python generate_meeting.py "議題" --context "状況"  # 議題を指定
  python generate_meeting.py --dry-run            # APIを使わずに流れだけ試す
"""
import argparse
import datetime as dt
import json
import os
import random
import re
from pathlib import Path

ROOT = Path(__file__).parent
MODEL = os.environ.get("KAIGI_MODEL", "claude-haiku-5-5")  # 安く回すなら Haiku
JST = dt.timezone(dt.timedelta(hours=9))


class DryClient:
    """APIキーなしで流れを確かめるための、決まった返事をするだけの代役。"""
    class _M:
        def create(self, model, max_tokens, system, messages, **kw):
            u = messages[0]["content"]
            if "候補:" in u:
                ids = re.findall(r"(\w+)=", u.split("候補:")[1])
                text = random.choice(ids)
            elif "形式:" in u:
                text = '{"options":[{"id":"A","title":"（試し）A案","proposer":"kenji"},{"id":"B","title":"（試し）B案","proposer":"tome"}]}'
            else:
                text = "（試しの発言です）"
            return type("R", (), {"content": [type("C", (), {"text": text})()]})()
    messages = _M()


client = None


def ask(system, user, max_tokens):
    r = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system,
                               thinking={"type": "disabled"},  # 短い発言なので考えるステップは使わない
                               messages=[{"role": "user", "content": user}])
    # 返事には「考え中のメモ」など本文以外が混ざることがあるので、本文だけを集める
    return "".join(getattr(b, "text", "") for b in r.content
                   if getattr(b, "type", "text") == "text").strip()


def persona_prompt(p, shop):
    return (
        f"あなたは「{shop['place']}」にある「{shop['name']}」の経営会議に出ている{p['name']}"
        f"（{p['role']}、{p['age']}歳）です。\n"
        f"性格: {p['personality']}\n話し方: {p['tone']}\n"
        f"好きなもの: {p['likes']}\n嫌いなもの: {p['dislikes']}\n"
        "ルール:\n- 自分の人格を必ず守る。安易に他の人に同意しない。\n"
        "- 1回の発言は1〜2文、60字以内。会話らしく、前の人の発言に反応する。\n"
        "- 発言の本文だけを書く（名前やかっこは付けない）。"
    )


def transcript(lines, by_id):
    return "\n".join(f"{by_id[l['speaker']]['name']}: {l['text']}" for l in lines)


def say(p, shop, agenda, context, recap, lines, by_id, extra=""):
    msg = (
        f"議題: {agenda}\n状況: {context}\n"
        + (f"前回の会議: {recap}\n" if recap else "")
        + f"\nここまでの会話:\n{transcript(lines, by_id) or '（まだ誰も話していない）'}\n\n"
        f"{extra}あなた（{p['name']}）の次の発言を書いてください。"
    )
    return ask(persona_prompt(p, shop), msg, 200).strip("「」")


def choose_next(others, agenda, lines, by_id):
    """次に話す人を選ぶ（同じ人が続かないようにする）。"""
    last = lines[-1]["speaker"] if lines else None
    cands = [p for p in others if p["id"] != last]
    names = "、".join(f"{p['id']}={p['name']}" for p in cands)
    text = ask("あなたは会議の進行役。次に発言させると議論が一番盛り上がる人のidだけを返す。",
               f"議題: {agenda}\n会話:\n{transcript(lines, by_id)}\n\n候補: {names}", 20)
    for p in cands:
        if p["id"] in text:
            return p
    return cands[0]


def summarize(agenda, lines, by_id):
    text = ask("会議の内容を、フォロワーに投票してもらう2つの案にまとめる。JSONだけを返す。",
               f"議題: {agenda}\n会話:\n{transcript(lines, by_id)}\n\n"
               '形式: {"options":[{"id":"A","title":"20字以内","proposer":"人物id"},'
               '{"id":"B","title":"20字以内","proposer":"人物id"}]}', 600)
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))["options"]


def previous_recap(meetings):
    """前回の議題と、票が多かった案を1行にする。"""
    if not meetings:
        return "", None
    prev = json.loads(meetings[-1].read_text(encoding="utf-8"))
    opts = prev.get("options", [])
    if opts and any(o.get("votes") for o in opts):
        win = max(opts, key=lambda o: o.get("votes", 0))
        return f"「{prev['agenda']}」→ フォロワーの投票で{win['id']}案「{win['title']}」に決定。", prev
    return f"「{prev['agenda']}」（投票結果はまだ出ていない）", prev


def meeting_key(path):
    """2026-11-25.json → (2026-11-25, 1)、2026-11-25-2.json → (2026-11-25, 2) の順に並べる。"""
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:-(\d+))?$", path.stem)
    return (m.group(1), int(m.group(2) or 1)) if m else (path.stem, 0)


def next_agenda(today):
    path = ROOT / "agendas.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    for it in items:
        if not it.get("used"):
            it["used"] = today
            path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return it["agenda"], it.get("context", "")
    raise SystemExit("agendas.json に未使用の議題がありません。議題を追加してください。")


def main():
    global client
    ap = argparse.ArgumentParser()
    ap.add_argument("agenda", nargs="?")
    ap.add_argument("--context", default="")
    ap.add_argument("--turns", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.dry_run:
        client = DryClient()
    else:
        import anthropic
        client = anthropic.Anthropic()

    today = dt.datetime.now(JST).date().isoformat()
    meetings = sorted((ROOT / "meetings").glob("*.json"), key=meeting_key)
    # 同じ日に2回目を作ったら 2026-11-25-2.json のように別名で保存する
    out, n = ROOT / "meetings" / f"{today}.json", 2
    while out.exists():
        out, n = ROOT / "meetings" / f"{today}-{n}.json", n + 1

    if a.agenda:
        agenda, context = a.agenda, a.context
    elif a.dry_run:
        agenda, context = "（試し）議題", "（試し）状況"
    else:
        agenda, context = next_agenda(today)

    cfg = json.loads((ROOT / "personas.json").read_text(encoding="utf-8"))
    shop, ps = cfg["shop"], cfg["personas"]
    by_id = {p["id"]: p for p in ps}
    chair = next(p for p in ps if p.get("is_chair"))
    others = [p for p in ps if not p.get("is_chair")]
    recap, prev = previous_recap(meetings)

    lines = [{"speaker": chair["id"], "text": say(
        chair, shop, agenda, context, recap, [], by_id,
        "会議の開始を告げ、前回の結果にひとこと触れてから、議題と状況を短く説明してください。")}]
    for i in range(a.turns):
        # 4回に1回は会長が流れを整理する
        p = chair if i % 4 == 3 else choose_next(others, agenda, lines, by_id)
        lines.append({"speaker": p["id"], "text": say(p, shop, agenda, context, recap, lines, by_id)})
    lines.append({"speaker": chair["id"], "text": say(
        chair, shop, agenda, context, recap, lines, by_id,
        "会議を締めくくり、AかBかをフォロワーにコメントで決めてもらうよう呼びかけてください。")})

    options = summarize(agenda, lines, by_id)
    for o in options:
        o.setdefault("forecast", "（経済モデルの予測をここに入れる）")
        o["votes"] = 0

    meeting = {
        "date": out.stem,
        "number": (prev["number"] + 1) if prev else 1,
        "agenda": agenda,
        "context": context,
        "lines": lines,
        "options": options,
        "forecast_note": "予測は経済モデルの計算値（つなぎ込み前は仮）。",
    }
    if a.dry_run:
        print(json.dumps(meeting, ensure_ascii=False, indent=2)[:800])
        print("…（dry-run のため保存しません）")
        return
    out.write_text(json.dumps(meeting, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"保存しました: {out}")


def run():
    """失敗したら、GitHubの画面（ログインなしでも見える注記）に理由を出す。"""
    import sys
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    if in_actions and not os.environ.get("ANTHROPIC_API_KEY") and "--dry-run" not in sys.argv:
        print("::error title=APIキーがありません::Secrets に ANTHROPIC_API_KEY が登録されていないか、名前が違います")
        sys.exit(1)
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {e}".replace("\n", " ")[:900]
        if in_actions:
            print(f"::error title=会議の生成に失敗::{msg}")
        raise


if __name__ == "__main__":
    run()
