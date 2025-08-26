import os, random
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # サーバでGUI不要
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "change_me_secret"
PORT = int(os.environ.get("PORT", 5000))

# === 設定 ===
SCORE_FILE = "score_history.csv"
STATS_FILE = "word_stats.csv"
GRAPH_FILE = "static/score_history.png"

# === 単語データ読み込み ===
def load_words():
    if not os.path.exists("words.xlsx"):
        raise FileNotFoundError("words.xlsx が見つかりません。プロジェクト直下に置いてください。")
    df = pd.read_excel("words.xlsx")  # 列名: 番号, 英単語, 意味
    for col in ["番号","英単語","意味"]:
        if col not in df.columns:
            raise ValueError("Excelの1行目に 列名「番号」「英単語」「意味」を入れてください。")
    df = df[df["番号"].between(1, 500)]
    return [{"word": r["英単語"], "meaning": r["意味"]} for _, r in df.iterrows()]

word_list = load_words()

# === 統計ファイルのロード/初期化 ===
def load_word_stats():
    if os.path.exists(STATS_FILE):
        return pd.read_csv(STATS_FILE, index_col="word").to_dict("index")
    else:
        return {w["word"]: {"times_shown": 0, "times_wrong": 0} for w in word_list}

word_stats = load_word_stats()

def update_word_stats(word, correct):
    if word not in word_stats:
        word_stats[word] = {"times_shown": 0, "times_wrong": 0}
    word_stats[word]["times_shown"] += 1
    if not correct:
        word_stats[word]["times_wrong"] += 1

def save_word_stats():
    df = pd.DataFrame.from_dict(word_stats, orient="index")
    df.index.name = "word"
    df.to_csv(STATS_FILE)

def save_score_history(score, mode):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = pd.DataFrame([[now, mode, score]], columns=["date","mode","score"])
    if os.path.exists(SCORE_FILE):
        row.to_csv(SCORE_FILE, mode="a", header=False, index=False)
    else:
        row.to_csv(SCORE_FILE, index=False)

def plot_score_history():
    if not os.path.exists(SCORE_FILE): return None
    df = pd.read_csv(SCORE_FILE)
    if df.empty: return None
    df["date"] = pd.to_datetime(df["date"])
    plt.figure(figsize=(6,3))
    plt.plot(df["date"], df["score"], marker="o")
    plt.title("スコア推移")
    plt.xlabel("日付"); plt.ylabel("得点")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(GRAPH_FILE)
    plt.close()
    return GRAPH_FILE

def choose_words(mode="normal"):
    if mode == "normal":
        return random.sample(word_list, 10)
    # 苦手単語モード
    stats = []
    for w in word_list:
        name = w["word"]
        s = word_stats.get(name, {"times_shown":0, "times_wrong":0})
        if s["times_shown"] > 0:
            stats.append((s["times_wrong"]/s["times_shown"], w))
    stats.sort(reverse=True, key=lambda x: x[0])
    weak = [w for _, w in stats[:10]]
    while len(weak) < 10:
        weak.append(random.choice(word_list))
    return weak

@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        mode = request.form.get("mode","normal")
        session["mode"] = mode
        session["questions"] = choose_words(mode)
        session["current"] = 0
        session["score"] = 0
        session["wrong"] = []
        return redirect(url_for("quiz"))
    return render_template("index.html")

@app.route("/quiz", methods=["GET","POST"])
def quiz():
    current = session.get("current", 0)
    qs = session.get("questions", [])
    if not qs: return redirect(url_for("index"))

    if current >= 10:
        return redirect(url_for("result"))

    q = qs[current]
    if current < 5:
        correct = q["meaning"]
        choices = random.sample([w["meaning"] for w in word_list], 3)
    else:
        correct = q["word"]
        choices = random.sample([w["word"] for w in word_list], 3)

    if correct not in choices:
        choices[random.randrange(3)] = correct
    random.shuffle(choices)

    if request.method == "POST":
        ans = request.form.get("answer")
        is_correct = (ans == correct)
        if is_correct:
            session["score"] += 1
        else:
            # wrong: (単語, 正解, あなたの答え)
            if current < 5:
                session["wrong"].append((q["word"], q["meaning"], ans))
            else:
                session["wrong"].append((q["meaning"], q["word"], ans))
        update_word_stats(q["word"], is_correct)
        session["current"] = current + 1
        return redirect(url_for("quiz"))

    return render_template("quiz.html", question=q, choices=choices, current=current+1)

@app.route("/result")
def result():
    score = session.get("score", 0)
    mode = session.get("mode", "normal")
    wrong = session.get("wrong", [])
    save_score_history(score, mode)
    save_word_stats()
    graph = plot_score_history()
    ts = int(datetime.now().timestamp())
    return render_template("result.html", score=score, wrong=wrong, graph_file=graph, ts=ts)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)