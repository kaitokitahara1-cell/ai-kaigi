"""会議室の画面を作る。

personas.json と meetings/*.json を viewer.template.html に埋め込み、
- index.html          … 最新の会議
- m-YYYY-MM-DD.html   … 過去の会議（1回ずつ）
を書き出す。どれも1ファイルで動き、GitHub Pagesにそのまま置ける。
使い方:  python build.py
"""
import json

from generate_meeting import meeting_key
from pathlib import Path

ROOT = Path(__file__).parent


def dump(obj):
    # </script> で埋め込みが切れないようにする
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def main():
    personas = json.loads((ROOT / "personas.json").read_text(encoding="utf-8"))
    template = (ROOT / "viewer.template.html").read_text(encoding="utf-8")
    files = sorted((ROOT / "meetings").glob("*.json"), key=meeting_key)
    meetings = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    archive = [{"date": m["date"], "number": m["number"], "agenda": m["agenda"],
                "href": f"m-{m['date']}.html"} for m in meetings]

    def render(m):
        return (template.replace("__PERSONAS__", dump(personas))
                        .replace("__MEETING__", dump(m))
                        .replace("__ARCHIVE__", dump(archive)))

    for m in meetings:
        (ROOT / f"m-{m['date']}.html").write_text(render(m), encoding="utf-8")
    (ROOT / "index.html").write_text(render(meetings[-1]), encoding="utf-8")
    print(f"index.html と過去の会議 {len(meetings)} 回分を作りました（最新: {meetings[-1]['date']}）")


if __name__ == "__main__":
    main()
