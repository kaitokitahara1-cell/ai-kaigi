"""キャラクターの記憶（Obsidianでそのまま開けるMarkdown）。

memory/<名前>.md に1人1ファイル。中身は3つの見出し：
- 「自分について」   … 人が自由に書き足してよい設定メモ。AIは書き換えない
- 「ほかの人の印象」 … 会議のたびにAIが本人目線で書き直す
- 「覚えていること」 … 会議のたびに本人目線で1〜2行ずつ足していく
kaigi-log/<日付> 第N回.md には会議の全文を残し、[[名前]] でキャラとつなぐ
（Obsidianのグラフビューで、誰がどの会議に出たかが見える）。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
MEM_DIR = ROOT / "memory"
LOG_DIR = ROOT / "kaigi-log"
SECTIONS = ["自分について", "ほかの人の印象", "覚えていること"]
RECENT = 10  # 会議で思い出す「覚えていること」の件数


def path_of(p):
    return MEM_DIR / f"{p['name']}.md"


def log_title(m):
    return f"{m['date']} 第{m['number']}回"


def load(p):
    """見出しごとの中身（行のリスト）を返す。ファイルがなければ空。"""
    data = {s: [] for s in SECTIONS}
    f = path_of(p)
    if not f.exists():
        return data
    cur = None
    for line in f.read_text(encoding="utf-8").splitlines():
        h = re.match(r"^##\s+(.+?)\s*(（.*）)?\s*$", line)
        if h:
            cur = h.group(1) if h.group(1) in data else None
            continue
        if cur and line.strip():
            data[cur].append(line.rstrip())
    return data


def save(p, data):
    MEM_DIR.mkdir(exist_ok=True)
    body = [
        "---",
        f"name: {p['name']}",
        f"id: {p['id']}",
        "tags: [AI会議, キャラクター]",
        "---",
        f"# {p['name']}",
        "",
        "## 自分について（自由に書き足してOK。会議のときに本人が読みます）",
        *(data["自分について"] or ["- "]),
        "",
        "## ほかの人の印象（会議のたびにAIが書き直します）",
        *data["ほかの人の印象"],
        "",
        "## 覚えていること（会議のたびにAIが足していきます）",
        *data["覚えていること"],
        "",
    ]
    path_of(p).write_text("\n".join(body), encoding="utf-8")


def prompt_text(p):
    """会議の発言を作るときに本人に渡す記憶。"""
    d = load(p)
    parts = []
    if any(x.strip("- ").strip() for x in d["自分について"]):
        parts.append("自分についてのメモ:\n" + "\n".join(d["自分について"]))
    if d["ほかの人の印象"]:
        parts.append("ほかの人の印象:\n" + "\n".join(d["ほかの人の印象"]))
    if d["覚えていること"]:
        parts.append("これまでの会議で覚えていること（新しいものほど下）:\n"
                     + "\n".join(d["覚えていること"][-RECENT:]))
    return _plain("\n\n".join(parts))


def _plain(text):
    return re.sub(r"\[\[([^\]|]+)(\|[^\]]+)?\]\]", r"\1", text)


def update_after_meeting(meeting, personas, ask, persona_prompt, shop):
    """会議のあと、1人ずつ本人目線で記憶と印象を書き足す。"""
    by_id = {p["id"]: p for p in personas}
    talk = "\n".join(f"{by_id[l['speaker']]['name']}: {l['text']}" for l in meeting["lines"])
    title = log_title(meeting)
    for p in personas:
        others = [q for q in personas if q["id"] != p["id"]]
        d = load(p)
        user = (
            f"今日の会議（{title}、議題: {meeting['agenda']}）の全文:\n{talk}\n\n"
            f"今のあなたの記憶:\n{_plain(prompt_text(p)) or '（まだない）'}\n\n"
            "会議を終えたあなたの頭に残ったことを、あなた自身の口調で書いてください。JSONだけを返す。\n"
            '形式: {"memories": ["今日のことで覚えておきたいこと（1〜2個、各40字以内）"], '
            '"impressions": {' + ", ".join(f'"{q["id"]}": "{q["name"]}への今の印象（30字以内）"' for q in others) + "}}"
        )
        try:
            raw = ask(persona_prompt(p, shop), user, 500)
            j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        except Exception as e:  # 1人失敗しても会議全体は止めない
            print(f"記憶の更新をとばしました（{p['name']}）: {e}")
            continue
        for mem in j.get("memories", [])[:2]:
            d["覚えていること"].append(f"- [[{title}]] {mem}")
        imp = j.get("impressions", {})
        if imp:
            d["ほかの人の印象"] = [f"- [[{by_id[k]['name']}]]：{v}" for k, v in imp.items() if k in by_id]
        save(p, d)


def write_log(meeting, personas):
    """会議の全文を Obsidian 用のMarkdownに残す。"""
    by_id = {p["id"]: p for p in personas}
    LOG_DIR.mkdir(exist_ok=True)
    lines = [
        "---",
        f"date: {meeting['date']}",
        f"number: {meeting['number']}",
        "tags: [AI会議, 会議ログ]",
        "---",
        f"# 第{meeting['number']}回 {meeting['agenda']}",
        "",
        f"状況: {meeting.get('context', '')}",
        "",
        "出席: " + "、".join(f"[[{p['name']}]]" for p in personas),
        "",
        "## 会話",
    ]
    for l in meeting["lines"]:
        lines.append(f"- **[[{by_id[l['speaker']]['name']}]]**：{l['text'].replace(chr(10), ' ')}")
    lines += ["", "## 投票にかけた案"]
    for o in meeting.get("options", []):
        pr = by_id.get(o.get("proposer"), {}).get("name", "")
        lines.append(f"- **{o['id']}案** {o['title']}（提案: [[{pr}]]）　票: {o.get('votes', 0)}")
    (LOG_DIR / f"{log_title(meeting)}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
