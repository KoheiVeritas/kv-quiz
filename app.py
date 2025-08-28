# app.py
import os
import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # サーバーでGUI不要
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "change_me_secret"  # 任意のランダム文字列に変更してください

# ===== ファイル名 =====
SCORE_FILE = "score_history.csv"   # 日付・モード・得点
STATS_FILE = "word_stats.csv"      # 単語ごとの出題回数・誤答回数
GRAPH_FILE = "static/score_history.png"
ACHIEV_FILE = "achievements.csv"   # 取得済みの称号コード

# ===== 単語データ読み込み =====
def load_words():
    if not os.path.exists("words.xlsx"):
        raise FileNotFoundError("words.xlsx が見つかりません（プロジェクト直下に配置してください）。")
    df = pd.read_excel("words.xlsx")  # 列名：番号 / 英単語 / 意味
    for col in ["番号", "英単語", "意味"]:
        if col not in df.columns:
            raise ValueError("Excelの1行目に 正確に『番号』『英単語』『意味』を入れてください。")
    df = df[df["番号"].between(1, 500)]
    out = [{"word": r["英単語"], "meaning": r["意味"]} for _, r in df.iterrows()]
    if len(out) < 10:
        raise ValueError("出題データが少なすぎます（最低10語以上）。")
    return out

word_list = load_words()

# ===== 統計（苦手単語用） =====
def load_word_stats():
    if os.path.exists(STATS_FILE):
        try:
            df = pd.read_csv(STATS_FILE, index_col="word")
            d = df.to_dict("index")
            # 欠損に備えて初期値補完
            for w in word_list:
                if w["word"] not in d:
                    d[w["word"]] = {"times_shown": 0, "times_wrong": 0}
            return d
        except Exception:
            pass
    # 初期化
    return {w["word"]: {"times_shown": 0, "times_wrong": 0} for w in word_list}

word_stats = load_word_stats()

def update_word_stats(word, correct: bool):
    if word not in word_stats:
        word_stats[word] = {"times_shown": 0, "times_wrong": 0}
    word_stats[word]["times_shown"] += 1
    if not correct:
        word_stats[word]["times_wrong"] += 1

def save_word_stats():
    df = pd.DataFrame.from_dict(word_stats, orient="index")
    df.index.name = "word"
    df.to_csv(STATS_FILE)

# ===== スコア履歴 =====
def save_score_history(score: int, mode: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = pd.DataFrame([[now, mode, score]], columns=["date", "mode", "score"])
    if os.path.exists(SCORE_FILE):
        row.to_csv(SCORE_FILE, mode="a", header=False, index=False)
    else:
        row.to_csv(SCORE_FILE, index=False)

def plot_score_history():
    if not os.path.exists(SCORE_FILE):
        return None
    df = pd.read_csv(SCORE_FILE)
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    plt.figure(figsize=(6, 3))
    plt.plot(df["date"], df["score"], marker="o")
    plt.title("スコア推移")
    plt.xlabel("日付")
    plt.ylabel("得点")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(GRAPH_FILE)
    plt.close()
    return GRAPH_FILE

# ===== 出題セット作成 =====
def choose_words(mode="normal"):
    if mode == "normal":
        return random.sample(word_list, 10)

    # 苦手単語モード：誤答率が高い順に10語
    stats = []
    for w in word_list:
        s = word_stats.get(w["word"], {"times_shown": 0, "times_wrong": 0})
        if s["times_shown"] > 0:
            rate = s["times_wrong"] / max(1, s["times_shown"])
            stats.append((rate, w))
    stats.sort(reverse=True, key=lambda x: x[0])
    weak = [w for _, w in stats[:10]]
    # データが少ない場合、残りはランダム補充
    while len(weak) < 10:
        cand = random.choice(word_list)
        if cand not in weak:
            weak.append(cand)
    return weak

# ===== 称号（CSVベース・単ユーザー想定） =====
def _load_achieved():
    if os.path.exists(ACHIEV_FILE):
        try:
            df = pd.read_csv(ACHIEV_FILE)
            return set(df["code"].tolist())
        except Exception:
            return set()
    return set()

def _save_achieved(codes_new):
    already = _load_achieved()
    merged = sorted(list(already.union(codes_new)))
    pd.DataFrame({"code": merged}).to_csv(ACHIEV_FILE, index=False)

def _read_scores_df():
    if not os.path.exists(SCORE_FILE):
        return pd.DataFrame(columns=["date", "mode", "score"])
    df = pd.read_csv(SCORE_FILE)
    if not {"date", "mode", "score"}.issubset(df.columns):
        return pd.DataFrame(columns=["date", "mode", "score"])
    df["date"] = pd.to_datetime(df["date"])
    return df

def check_new_achievements(latest_score: int):
    """
    最新プレイ後に新規で獲得した称号を返す（表示用辞書のリスト）。
    """
    earned_now = set()
    df = _read_scores_df()

    # 初参加
    if len(df) == 1:
        earned_now.add("TRY_FIRST")
    # 満点王
    if latest_score == 10:
        earned_now.add("PERFECT")
    # 準優秀賞：9/10以上が3回以上
    if (df["score"] >= 9).sum() >= 3:
        earned_now.add("NINETY_MULTI")
    # 皆勤賞：直近7日毎日プレイ
    if not df.empty:
        today = pd.Timestamp("today").normalize()
        dates = set(df["date"].dt.normalize().dt.date.tolist())
        ok = True
        for i in range(7):
            d = (today - pd.Timedelta(days=i)).date()
            if d not in dates:
                ok = False
                break
        if ok:
            earned_now.add("SEVEN_STREAK")
    # 早起き賞/夜ふかし賞
    hour = datetime.now().hour
    if hour <= 7:
        earned_now.add("EARLY_BIRD")
    if hour >= 21:
        earned_now.add("NIGHT_OWL")
    # ラッキービー（3%）
    if random.random() < 0.03:
        earned_now.add("LUCKY_BEE")

    already = _load_achieved()
    fresh = earned_now - already
    if fresh:
        _save_achieved(fresh)

    META = {
        "PERFECT":      {"name": "満点王",     "rank": "gold"},
        "NINETY_MULTI": {"name": "準優秀賞",   "rank": "silver"},
        "TRY_FIRST":    {"name": "挑戦者",     "rank": "bronze"},
        "SEVEN_STREAK": {"name": "皆勤賞",     "rank": "bronze"},
        "EARLY_BIRD":   {"name": "早起き賞",   "rank": "special"},
        "NIGHT_OWL":    {"name": "夜ふかし賞", "rank": "special"},
        "LUCKY_BEE":    {"name": "ラッキービー", "rank": "special"},
    }
    return [{"code": c, **META[c]} for c in fresh if c in META]

# ===== ルーティング =====
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        mode = request.form.get("mode", "normal")
        session["mode"] = mode
        session["questions"] = choose_words(mode)
        session["current"] = 0
        session["score"] = 0
        session["wrong"] = []
        return redirect(url_for("quiz"))
    return render_template("index.html")

@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    current = session.get("current", 0)
    qs = session.get("questions", [])
    if not qs:
        return redirect(url_for("index"))

    if current >= 10:
        return redirect(url_for("result"))

    q = qs[current]
    score = session.get("score", 0)
    wrong = session.get("wrong", [])

    # 回答が送信された場合の処理
    if request.method == "POST":
        selected = request.form.get("answer", "")
        # 正解判定（前半5問＝意味を選ぶ、後半5問＝単語を選ぶ）
        correct = q["meaning"] if current < 5 else q["word"]
        is_correct = (selected == correct)
        if is_correct:
            score += 1
        else:
            # フィードバック用（テンプレートに合わせた形）
            if current < 5:
                wrong.append((q["word"], q["meaning"], selected))  # 単語 / 正解の意味 / あなたの答え
            else:
                wrong.append((q["meaning"], q["word"], selected))  # 意味 / 正解の単語 / あなたの答え

        # 苦手統計の更新は「問われた単語」で行う
        update_word_stats(q["word"], is_correct)

        # 進行更新
        session["score"] = score
        session["wrong"] = wrong
        session["current"] = current + 1

        if session["current"] >= 10:
            return redirect(url_for("result"))
        else:
            return redirect(url_for("quiz"))

        # === 出題（4択） ===
    if current < 5:
        # 前半：意味選択式（問題は英単語、選択肢は意味）
        correct = q["meaning"]
        pool = [w["meaning"] for w in word_list if w["meaning"] != correct]
    else:
        # 後半：英単語選択式（問題は意味、選択肢は英単語）
        correct = q["word"]
        pool = [w["word"] for w in word_list if w["word"] != correct]

    # ダミー3つ + 正解 = 4択（プールが足りない場合の保険つき）
    distractors = random.sample(pool, min(3, len(pool)))
    while len(distractors) < 3 and pool:
        cand = random.choice(pool)
        if cand not in distractors:
            distractors.append(cand)

    choices = distractors + [correct]
    random.shuffle(choices)

    return render_template("quiz.html", question=q, choices=choices, current=current + 1)


@app.route("/result")
def result():
    score = session.get("score", 0)
    mode = session.get("mode", "normal")
    wrong = session.get("wrong", [])

    # 記録とグラフ
    save_score_history(score, mode)
    save_word_stats()
    graph = plot_score_history()
    ts = int(datetime.now().timestamp())

    # 新規称号判定
    new_badges = check_new_achievements(score)

    return render_template(
        "result.html",
        score=score,
        wrong=wrong,
        graph_file=graph,
        ts=ts,
        new_badges=new_badges
    )

# ヘルスチェック（任意）
@app.get("/healthz")
def healthz():
    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
