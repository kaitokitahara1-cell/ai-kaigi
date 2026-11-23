# AI経営会議室（蒲田シミュ）

人格を設定したAI 4人が、1店舗（架空の「大衆酒場 にしぐち」）の経営について毎朝会議し、
最後にA案／B案をフォロワーの投票に回す仕組み。会議の様子は会議室の画面（GitHub Pages）で見られる。

## ファイル
| ファイル | 役割 |
|---|---|
| `personas.json` | 4人の人格（年齢・性格・口調・好き嫌い・色）と店の設定。書き換えると人格が変わる |
| `agendas.json` | 議題の予定表。上から順に使い、使った日が `used` に入る。足りなくなったら追加する |
| `meetings/*.json` | 会議1回ぶんの会話・議題・A/B案（同じ日の2回目は `-2` が付く） |
| `memory/<名前>.md` | 1人ずつの記憶（Obsidian形式）。「自分について」は人が書き足してOK、「ほかの人の印象」「覚えていること」は会議のたびにAIが更新 |
| `kaigi-log/<日付> 第N回.md` | 会議の全文（Obsidian形式）。[[名前]]でキャラとつながる |
| `memory.py` | 記憶の読み書き |
| `generate_meeting.py` | Claude APIで会議を自動生成。前回の議題と投票結果にも触れる |
| `viewer.template.html` | 会議室の画面のひな形 |
| `build.py` | `index.html`（最新）と `m-日付.html`（過去の回）を作る |
| `.github/workflows/daily-meeting.yml` | 毎朝6:47（日本時間）に 生成→画面作成→保存→公開 を自動で行う |

## 手元で動かす
```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
python generate_meeting.py                 # 次の議題で会議
python generate_meeting.py "議題" --context "状況"
python generate_meeting.py --dry-run       # APIを使わずに流れだけ確認
python build.py
```

## GitHubでの初期設定（1回だけ）
1. リポジトリの Settings → Secrets and variables → Actions に `ANTHROPIC_API_KEY` を登録
2. Settings → Pages → Source を「GitHub Actions」にする
3. Actions → daily-meeting → Run workflow で試しに1回動かす

## 費用の目安
1回の会議で APIを約30回呼ぶ（発言16回＋話す人の選択＋まとめ）。Haiku なら1回数円〜十数円程度の見込み。
モデルは環境変数 `KAIGI_MODEL` で変えられる。

## 今後つなぐもの
- `agendas.json` の代わりに、前日のInstagramコメントから議題を作る
- `options[].forecast` に経済モデルの予測を入れる
- `options[].votes` にInstagramのコメント数（A/B）を入れる

## Obsidianで記憶を見る・育てる
1. Obsidianのコミュニティプラグイン「Git」を入れる
2. このリポジトリをMacにクローンし、フォルダをObsidianの保管庫として開く
3. Gitプラグインで「Pull」すると、毎朝の会議ログと記憶が届く
4. `memory/<名前>.md` の「自分について」に設定を書き足して「Commit and push」すると、次の会議から本人がそれを踏まえて話す
   （例：トメさんの欄に「最近、孫が生まれた」と足すと、会議で孫の話をし始める）
