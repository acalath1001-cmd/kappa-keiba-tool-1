import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin
def calc_front_score(horse_no, race_flows, finish_positions=None):
    score = 0
    finish_positions = finish_positions or []

    for idx, flow in enumerate(race_flows):
        if len(flow) < 2:
            continue

        first = flow[0]
        last = flow[-1]
        finish = finish_positions[idx] if idx < len(finish_positions) else None

        # 前進気勢は1角の位置取りを重視する
        if first == 1:
            score += 50
        elif first == 2:
            score += 40
        elif first == 3:
            score += 30
        elif first == 4:
            score += 20
        elif first == 5:
            score += 10

        # 前に行った馬だけ、順位維持を評価
        if first <= 5 and last <= first:
            score += 12

        # 通過順でズルズル下がる馬は減点
        if last - first >= 3:
            score -= 25

        # 4角前にいたのに着順で垂れた馬を減点
        if finish is not None:
            if last <= 4 and finish >= 6:
                score -= 40

            if last <= 3 and finish >= 8:
                score -= 70

            if first <= 4 and last <= 4 and finish <= 3:
                score += 25

    return score
st.set_page_config(
    page_title="地方競馬予想ツール",
    page_icon="favicon.png",
    layout="centered"
)

st.title("🐎 地方競馬AI")
debug_mode = st.checkbox("デバッグ表示")

if "race_url" not in st.session_state:
    st.session_state.race_url = ""

url = st.text_input(
    "出馬表URLを入力してください",
    value=st.session_state.race_url
)

col1, col2 = st.columns(2)

with col1:
    analyze = st.button("🔍 分析開始")
if "analyzed" not in st.session_state:
    st.session_state.analyzed = False
with col2:
    clear_url = st.button("🗑 URL削除")
if analyze:
    st.session_state.analyzed = True
if clear_url:
    st.session_state.race_url = ""
    st.rerun()

st.session_state.race_url = url
if not st.session_state.analyzed:
    st.stop()

if not url:
    st.warning("出馬表URLを入力してください")
    st.stop()

st.write("分析開始...")

keibajo = {
    "10": "帯広競馬",
    "11": "盛岡・水沢競馬",
    "18": "浦和競馬",
    "19": "船橋競馬",
    "20": "大井競馬",
    "21": "川崎競馬",
    "22": "金沢競馬",
    "23": "笠松競馬",
    "24": "名古屋競馬",
    "27": "園田競馬",
    "28": "姫路競馬",
    "31": "高知競馬",
    "32": "佐賀競馬",
    "36": "門別競馬",
}

found = False

for code, name in keibajo.items():
    if f"k_babaCode={code}" in url:
        print(name)
        found = True

if not found:
    print("競馬場不明")

query = urlparse(url).query
params = parse_qs(query)

race_no = params.get("k_raceNo", ["不明"])[0]
race_date = params.get("k_raceDate", ["不明"])[0]

print(f"レース番号：{race_no}R")
print(f"開催日：{race_date}")




print("◎ 本命候補")
print("○ 対抗候補")
print("▲ 穴候補")
print(url)
response = requests.get(url)
soup = BeautifulSoup(response.text, "html.parser")

print("ページ取得成功")
page_text = soup.get_text(" ", strip=True)
distance_match = re.search(
    r"([０-９0-9]{3,4})\s*(?:m|ｍ|メートル)",
    page_text
)

if distance_match:
    distance = distance_match.group(1)
    distance = distance.translate(
        str.maketrans("０１２３４５６７８９", "0123456789")
    )

    baba_name = "競馬場不明"

    for code, name in keibajo.items():
        if f"k_babaCode={code}" in url:
            baba_name = name.replace("競馬", "")
            break

    st.success(
        f"距離を自動取得しました：{baba_name}{race_no}R　{distance}m戦"
    )

else:
    distance = st.text_input("距離を入力してください（例 1400）:")

    if not distance:
        st.warning("距離が自動取得できませんでした。手入力してください。")
        st.stop()

course_name = ""

print(f"{distance}m戦")

# 距離カテゴリ
distance_num = int(distance) if str(distance).isdigit() else 1400
if distance_num <= 1400:
    distance_type = "short"

elif distance_num <= 1800:
    distance_type = "middle"

else:
    distance_type = "long"

if distance == "1400":
    print("前有利コース")

elif distance == "1200":
    print("先行有利")

elif distance == "1800":
    print("差し注意")

else:
    print("データ不足")
st.write("出走馬一覧")
horse_list = []

rows = soup.find_all("tr")
for row in rows:
        texts = row.get_text("\n").split("\n")

for t in texts:
        t = t.strip()

        if 3 <= len(t) <= 9:
            if "牡" in t or "牝" in t:
                continue

            if "名" in t:
                continue

            if "（" in t or "(" in t:
                continue

            ng = [
                "グランド牧場",
                "シンボリ牧場",
                "オルフェーヴル",
                "ロードカロア",
                "ロードカナロア",
                "社台ファーム",
                "オッズ",
                "最高タイム",
                "ダート左回り成績",
                "ダート右回り成績",
                "騎乗成績",
                "誕生日",
                "負担重量",
                "変更情報",
                "生産牧場",
                "馬体重"
                "ベルシャザール",
                "プリマフェーヴル",
                "ロードモーダル",
            ]

            if t in ng:
                continue

            if not any(char.isdigit() for char in t):

                if " " not in t: 
                    if not any(char in t for char in "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン"):
                        continue
                    horse_list.append(t)

                    unique_horses = list(dict.fromkeys(horse_list))

                    real_horses = [
    "ノースザワールド",
    "ティープインパクト",
    "バスオブドリームズ",
    "トーホウランボ",
    "ダンカーグ"
]

import re

page_text = soup.get_text(" ", strip=True)
pattern = r"(?:^|\s)(?:[1-8]\s+)?([1-9][0-9]?)\s+([ァ-ヴー]{2,})\s+"

matches = re.findall(pattern, page_text)

real_horses = []

for num, name in matches:
        if name not in real_horses:
            real_horses.append(name)
numbered_horses = []

for i, horse in enumerate(real_horses, start=1):
        numbered_horses.append(f"{i}番 {horse}")
horses = []

for i, horse in enumerate(real_horses, start=1):
    horse_text = ""

    horse_texts = []

    horse_text = ""
    horse_row = None
    # 馬名を含む row から下の15 row をまとめて取得
    for idx, row in enumerate(rows):
        row_text = row.get_text(" ", strip=True)

        if re.search(rf"(?:^|\s){i}\s+{horse}(?:\s|$)", row_text):
            horse_row = row
            for j in range(idx, len(rows)):
                nearby_text = rows[j].get_text(" ", strip=True)

                # 次の馬の行に入ったら終了
                if j > idx and i < len(real_horses):
                    next_horse = real_horses[i]
                    if re.search(rf"(?:^|\s){i+1}\s+{next_horse}(?:\s|$)", nearby_text):
                        break

                horse_text += nearby_text + "\n"
    # 着別成績・最高タイム側の 3-2-1-4 などを除外するため、
    # 日付つきの過去走セルにある通過順だけ拾う
        # 走破タイムの直後にある通過順だけ拾う
    # 例：1:51.6  7-7-6-5  40.4
        # 走破タイムの直後にある通過順だけ拾う
    # 例：1:51.6  7-7-6-5  40.4
    flow_matches_raw = []

    for m in re.findall(
        r"(\d{1,2})-(\d{1,2})(?:-(\d{1,2}))?(?:-(\d{1,2}))?",
        horse_text
    ):
        nums = [int(x) for x in m if x != ""]

        if 0 in nums:
            continue

        if any(n >= 30 for n in nums):
            continue

        if len(nums) == 4 and nums[3] >= 10 and max(nums[:3]) <= 5:
            continue

        flow_matches_raw.append(nums)
        race_flows = flow_matches_raw[-5:]
    race_times = []
    distance_time_pairs = []

    # 距離一覧を取得
    distance_matches = re.findall(
        r"(?:右|左|芝|ダ)\s*(820|850|900|920|1000|1200|1230|1300|1400|1500|1600|1700|1870|1800|1900|2000|2100|2200)",
        horse_text
    )


    distance_matches = distance_matches[-5:]
    # 過去走の競馬場名を取得（園田・姫路補正用）
    place_matches = re.findall(
        r"(園田|姫路)",
        horse_text
    )

    place_matches = place_matches[-5:]
    # タイム＋通過順を取得
    time_flow_matches = re.findall(
        r"(\d+:\d{2}\.\d+)[\s　]+(\d{1,2}-\d{1,2}(?:-\d{1,2})?(?:-\d{1,2})?)",
        horse_text
    )

    for time_text, flow_text in time_flow_matches:

        flow_nums = [int(x) for x in flow_text.split("-")]

        if 0 in flow_nums:
            continue

        if any(n >= 30 for n in flow_nums):
            continue

        race_times.append(time_text)

    race_times = race_times[-5:]

    # 距離とタイムを結合
    distance_time_pairs = []

    for idx, (d, t) in enumerate(zip(distance_matches, race_times)):
        place = place_matches[idx] if idx < len(place_matches) else ""

        distance_time_pairs.append({
            "距離": int(d),
            "タイム": t,
            "競馬場": place
        })

    race_times = race_times[-5:]
    distance_time_pairs = distance_time_pairs[-5:]
    # 過去5走の着順をセルの先頭から取得
    finish_positions = []

    if horse_row:
        for cell in horse_row.find_all(["td", "th"]):
            cell_text = cell.get_text(" ", strip=True)

            m = re.match(
                r"^(\d{1,2})\s+\d{2}\.\d{2}\.\d{2}",
                cell_text
            )

            if m:
                finish_positions.append(int(m.group(1)))

    finish_positions = finish_positions[-5:]
    corner_positions = [flow[-1] for flow in race_flows]
    # 出走取消・競走除外判定
    is_scratched = any(
        word in horse_text
        for word in ["出走取消", "競走除外", "出走除外"]
    )
    horses.append({
        "馬番": i,
        "馬名": horse,
        "取消除外": is_scratched,
        "4角位置": corner_positions,
        "通過順": race_flows,
        "走破タイム": race_times,
        "距離付きタイム": distance_time_pairs,
        "着順": finish_positions,
        "望月騎手": "望月" in horse_text,
        "取得テキスト": horse_text,
        })

for h in horses:
    if h.get("取消除外", False):
        st.markdown(
        f"<span style='color:red'>{h['馬番']}番 {h['馬名']}（競走除外）</span>",
        unsafe_allow_html=True
    )
    else:
        st.write(f"{h['馬番']}番 {h['馬名']}")
horses = [
    h for h in horses
    if not h.get("取消除外", False)
]
# ランダム予想を廃止
# ここからはスコア順で選出する

top_popular = numbered_horses

st.markdown("### 🎯 最初に軸馬を番号で選んでください")

popular_horse_num = st.number_input(
    "軸馬の馬番",
    min_value=1,
    max_value=len(real_horses),
    value=1,
    step=1
)

if popular_horse_num > len(real_horses):
    st.error(f"軸馬は1〜{len(real_horses)}番を選択してください")
    st.stop()

st.info(
    "※オッズは変動するため、現在の1番人気や\n"
    "自分が来ると思う馬を選択してください。\n\n"
    "※選択した馬を軸に展開分析と\n"
    "買い目を表示します。"
)
popular_horse_num_text = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"
popular_horse_label = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"

others = [
    horse for horse in numbered_horses
    if horse != popular_horse_num_text
]
# ランダム選出を廃止
yosou = others

# 4角位置が取れていない馬も含めてスコア確認できるようにする
front_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    corner_positions = horse["4角位置"]

    front_score = calc_front_score(
        horse_no,
        horse["通過順"],
        horse.get("着順", [])
    )
    # JRA転入馬は、前に行けた実績を少し評価する
    horse_text = horse.get("取得テキスト", "")

    jra_transfer = any(
        word in horse_text
        for word in [
            "東京", "中山", "京都", "阪神",
            "中京", "新潟", "福島",
            "小倉", "札幌", "函館"
        ]
    )
    if jra_transfer:
        for flow in horse["通過順"]:
            if len(flow) >= 2:
                first = flow[0]

                if first <= 4:
                    front_score += 35
                elif first <= 6:
                    front_score += 15
    # 長距離では、短距離だけの先行実績を少し弱める
    if distance_num >= 1900:
        horse_text = horse.get("取得テキスト", "")

        short_distance_count = len(re.findall(r"(?:右|左)?(?:800|900|1000|1200|1300|1400)", horse_text))
        long_distance_count = len(re.findall(r"(?:右|左)?(?:1600|1700|1800|1900|2000)", horse_text))

        if distance_num >= 1900:
            if long_distance_count == 0:
                front_score -= 120
            elif short_distance_count > long_distance_count:
                front_score -= 80
    front_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "スコア": front_score,
        "1角位置": [flow[0] for flow in horse["通過順"] if len(flow) >= 1]
    })

front_candidates = sorted(
    front_candidates,
    key=lambda x: x["スコア"],
    reverse=True
)

front_candidates = [h for h in front_candidates if h["スコア"] > 0]
if debug_mode:
    st.subheader("前進気勢スコア")

    for h in front_candidates:
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜スコア {h['スコア']} "
            f"｜1角 {h['1角位置']}"
        )
if debug_mode:
    st.subheader("通過順確認")

    for horse in horses:
        st.write(
            f"{horse['馬番']}番 {horse['馬名']} "
            f"｜通過順 {horse['通過順']} "
            f"｜着順 {horse['着順']}"
        )
if not front_candidates:
    st.info(
        """
🐎 新馬戦

過去レースデータが無いため、
前進気勢・地力・展開分析は行えません。

オッズ・馬体重・騎手を参考にしてください。
        """
    )
    st.stop()

front_best = front_candidates[0]

front_horse = f"{front_best['馬番']}番 {front_best['馬名']}"
front_score_map = {h["馬番"]: h["スコア"] for h in front_candidates}
long_spurt_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    race_flows = horse["通過順"]
    horse_text = horse.get("取得テキスト", "")

    score = 0
    front_keep_count = 0
    tare_count = 0
    # 2〜4番手維持型を評価
    first_positions = [flow[0] for flow in race_flows if len(flow) >= 2]
    last_positions = [flow[-1] for flow in race_flows if len(flow) >= 2]

    avg_first = sum(first_positions) / len(first_positions) if first_positions else 99
    avg_last = sum(last_positions) / len(last_positions) if last_positions else 99

    # 2〜4番手維持型
    if 2 <= avg_first <= 4:
        score += 300

    # 中団から押し上げ型
    if avg_first >= 5 and avg_last <= avg_first - 2:
        score += 200
    if distance_num >= 1900:
        short_distance_count = len(re.findall(r"(?:右|左)?(?:800|900|1000|1200|1300|1400)", horse_text))
        long_distance_count = len(re.findall(r"(?:右|左)?(?:1600|1700|1800|1900|2000)", horse_text))

        if long_distance_count == 0:
            score -= 700
        elif short_distance_count > long_distance_count:
            score -= 500

    for idx, flow in enumerate(race_flows):
        if len(flow) < 2:
            continue

        if 0 in flow:
            continue

        first = flow[0]
        second = flow[1] if len(flow) > 1 else flow[0]
        third = flow[2] if len(flow) > 2 else flow[-1]
        last = flow[-1]

        recent_bonus = idx + 1

        # 1番グラファス型：前〜中団で流れに乗って大きく崩れない
        if 2 <= first <= 6 and last <= 7 and max(flow) <= 7:
            score += 45 * recent_bonus
            front_keep_count += 1

        # 前で押し切る型：2-3-3-3 / 3-4-4-4 など
        if first <= 5 and last <= 5 and max(flow) <= 6 and abs(last - first) <= 2:
            score += 35 * recent_bonus
            front_keep_count += 1

        # 最後に垂れる馬を減点
        if last - first >= 3:
            score -= 80 * recent_bonus
            tare_count += 1
        # 4角では前にいたのに、着順で垂れた馬を地力評価から下げる
        finishes = horse.get("着順", [])
        finish = finishes[idx] if idx < len(finishes) else None

        if finish is not None:
            drop = finish - last

            if drop >= 5:
                score -= 100 * recent_bonus
                tare_count += 1
            elif drop >= 3:
                score -= 60 * recent_bonus
                tare_count += 1
            elif drop >= 2:
                score -= 30 * recent_bonus
        # 3角までは前、4角で急に下がる馬を強く減点
        if third <= 4 and last - third >= 3:
            score -= 120 * recent_bonus
            tare_count += 1

        # 後方維持だけは評価しない
        if first >= 8 and last >= 8:
            score -= 40 * recent_bonus

        # 少し押し上げる馬は加点
        if last < first and last <= 6:
            score += 20 * recent_bonus

    score += front_keep_count * 60
    score -= tare_count * 180
        # 地力評価にも前進気勢を少し反映
    score += front_score_map.get(horse_no, 0) * 0.25
    # 望月騎手補正
    if "望月" in horse_text:
        score += 80
    long_spurt_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "スコア": score,
        "通過順": race_flows
    })

long_spurt_candidates = sorted(
    long_spurt_candidates,
    key=lambda x: x["スコア"],
    reverse=True
)
# スコア0以下でも、候補として残す
# ただし通過順データがある馬を優先する
long_spurt_candidates = [
    h for h in long_spurt_candidates
    if h["通過順"]
]
# 表示用の「長く脚」は、先行気勢1位と被らないようにする
long_spurt_display_candidates = [
    h for h in long_spurt_candidates
    if h["馬番"] != front_best["馬番"]
]
if debug_mode:
    st.subheader("長く脚を使える馬スコア")

    for h in long_spurt_candidates:

        finishes = []

        for horse in horses:
            if horse["馬番"] == h["馬番"]:
                finishes = horse.get("着順", [])

        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜スコア {h['スコア']} "
            f"｜通過順 {h['通過順']} "
            f"｜着順 {finishes}"
        )
        
if not long_spurt_candidates:
    st.error("長く脚の評価データが取れていません")
    st.stop()

long_best = long_spurt_display_candidates[0]
long_spurt_horse = f"{long_best['馬番']}番 {long_best['馬名']}"
# 先行気勢と地力馬が被ったら、先行気勢を次点へ
if front_best["馬番"] == long_best["馬番"]:
    for h in front_candidates:
        if h["馬番"] != long_best["馬番"]:
            front_best = h
            front_horse = f"{front_best['馬番']}番 {front_best['馬名']}"
            break
# 仮の総合力1位を先に決める
front_score_map = {h["馬番"]: h["スコア"] for h in front_candidates}
long_score_map = {h["馬番"]: h["スコア"] for h in long_spurt_candidates}

pre_total_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]

    pre_total_score = 0
    total_score = 0

    horse_text = horse.get("取得テキスト", "")

    jra_transfer = any(
        word in horse_text
        for word in [
            "東京", "中山", "京都", "阪神",
            "中京", "新潟", "福島",
            "小倉", "札幌", "函館",
            "3歳未勝利", "３歳未勝利",
            "2歳未勝利", "２歳未勝利"
        ]
    )

    # 前進気勢は全馬共通
    pre_total_score = front_score_map.get(horse_no, 0) * 0.10


    race_times = horse.get("走破タイム", [])
    time_seconds = []
    time_score = 0
    best_time = None
    time_weight = 0
    for t in race_times:
        try:
            minutes, seconds = t.split(":")
            total_seconds = int(minutes) * 60 + float(seconds)
            time_seconds.append(total_seconds)
        except:
            pass

    if time_seconds:
        best_time = min(time_seconds)
        pre_total_score += max(0, 200 - best_time) * 3

    finishes = horse.get("着順", [])

    for finish in finishes:
        if finish <= 3:
            pre_total_score += 40
        elif finish <= 5:
            pre_total_score += 20
        elif finish >= 8:
            pre_total_score -= 30

    if finishes:
        avg_finish = sum(finishes) / len(finishes)

        if avg_finish <= 3:
            pre_total_score += 100
        elif avg_finish <= 5:
            pre_total_score += 60
        elif avg_finish <= 7:
            pre_total_score += 20
        elif avg_finish >= 8:
            pre_total_score -= 50

    pre_total_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "総合スコア": pre_total_score
    })

pre_total_candidates = sorted(
    pre_total_candidates,
    key=lambda x: x["総合スコア"],
    reverse=True
)

pre_total_best = pre_total_candidates[0]
pre_total_rank_map = {}

for rank, h in enumerate(pre_total_candidates, start=1):
    pre_total_rank_map[h["馬番"]] = rank
# 展開が向く馬：人気馬の脚色と合う馬を選ぶ

# 展開馬は、使用者が選んだ人気馬の脚色から算出する
base_horse_no = popular_horse_num

strong_data = None

for horse in horses:
    if horse["馬番"] == base_horse_no:
        strong_data = horse
        break

strong_flows = strong_data["通過順"] if strong_data else []
# レース全体の前崩れ警戒判定
front_pressure_count = 0

for horse in horses:
    flows = horse.get("通過順", [])

    for flow in flows[-3:]:
        if len(flow) < 2:
            continue

        first = flow[0]
        last = flow[-1]

        # 近走で前に行く意思がある馬
        if first <= 4:
            front_pressure_count += 1
            break

runner_count = len(horses)

# 前崩れ山型理論
# 2〜4頭が一番やり合いやすい
# 多すぎると逆に前残りしやすい

if front_pressure_count <= 1:
    front_collapse_score = 10

elif front_pressure_count == 2:
    front_collapse_score = 40

elif front_pressure_count == 3:
    front_collapse_score = 70

elif front_pressure_count == 4:
    front_collapse_score = 90

elif front_pressure_count == 5:
    front_collapse_score = 70

elif front_pressure_count == 6:
    front_collapse_score = 50

elif front_pressure_count == 7:
    front_collapse_score = 30

else:
    front_collapse_score = 15

# 人気馬の脚色タイプを判定し、脚色が合う馬を選ぶ

def avg_nonzero(values):
    values = [v for v in values if v > 0]
    if not values:
        return 99
    return sum(values) / len(values)

strong_firsts = [flow[0] for flow in strong_flows if len(flow) >= 2]
strong_lasts = [flow[-1] for flow in strong_flows if len(flow) >= 2]

strong_avg_first = avg_nonzero(strong_firsts)
strong_avg_last = avg_nonzero(strong_lasts)

# 軸馬の脚色タイプを5種類に統一する
# 逃げ・先行・差し・展開待ち・惰性で長く脚を使えるタイプ

strong_stable_count = 0
strong_push_count = 0
strong_back_count = 0
strong_front_count = 0

for flow in strong_flows:
    if len(flow) < 2:
        continue

    first = flow[0]
    last = flow[-1]

    # 逃げ・先行経験
    if first <= 2:
        strong_front_count += 1

    # 前〜中団で大きく崩れず長く脚を使う
    if 3 <= first <= 6 and 3 <= last <= 6 and abs(last - first) <= 2:
        strong_stable_count += 1

    # 中団〜後方から押し上げる
    if first >= 5 and last < first:
        strong_push_count += 1

    # 後方のまま
    if first >= 7 and last >= 7:
        strong_back_count += 1


# ①逃げ
if strong_avg_first <= 2 and strong_front_count >= 2:
    kyakushoku_type = "逃げ"

# ②先行
elif strong_avg_first <= 4 and strong_avg_last <= 5:
    kyakushoku_type = "先行"

# ③惰性で長く脚を使えるタイプ
elif (
    strong_stable_count >= 2
    or (
        3 <= strong_avg_first <= 6
        and 3 <= strong_avg_last <= 6
        and abs(strong_avg_last - strong_avg_first) <= 2
    )
):
    kyakushoku_type = "惰性で長く脚を使えるタイプ"

# ④差し
elif strong_push_count >= 2 or (strong_avg_first >= 5 and strong_avg_last < strong_avg_first):
    kyakushoku_type = "差し"

# ⑤展開待ち
else:
    kyakushoku_type = "展開待ち"
type_comment = {
    "逃げ": "ハナを切って粘り込むタイプです",
    "先行": "前目で流れに乗るタイプです",
    "差し": "中団以降から脚を使うタイプです",
    "展開待ち": "展開がハマると浮上するタイプです",
    "惰性で長く脚を使えるタイプ": "前〜中団で長く脚を使えるタイプです",
}
 
# 人気馬が差してくるタイプなのに先行気勢1位にも出る場合は、
# 先行気勢の馬を次点候補にずらす
if kyakushoku_type == "差し" and front_best["馬番"] == popular_horse_num:
    for h in front_candidates:
        if h["馬番"] != popular_horse_num:
            front_best = h
            front_horse = f"{front_best['馬番']}番 {front_best['馬名']}"
            break
tenkai_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    race_flows = horse["通過順"]

    if horse_no == base_horse_no:
        continue

    firsts = [flow[0] for flow in race_flows if len(flow) >= 2]
    lasts = [flow[-1] for flow in race_flows if len(flow) >= 2]

    avg_first = avg_nonzero(firsts)
    avg_last = avg_nonzero(lasts)
    
    score = 0
    # 着順が悪い馬は展開評価を少し下げる
    finishes = horse.get("着順", [])

    if finishes:
        avg_finish = sum(finishes) / len(finishes)
        bad_finish_count = sum(1 for f in finishes if f >= 8)

        if avg_finish >= 8:
            score -= 80
        elif avg_finish >= 6:
            score -= 40

        if bad_finish_count >= 3:
            score -= 80
        elif bad_finish_count >= 2:
            score -= 40
    # 前で競馬したのに最後垂れる馬は展開評価を下げる
    for idx, flow in enumerate(race_flows):

        if len(flow) < 2:
            continue

        last = flow[-1]
        finish = finishes[idx] if idx < len(finishes) else None

        if finish is None:
            continue

    # 軸馬が逃げで前崩れ期待が低い時は、前残り想定なので減点をゆるめる
    if kyakushoku_type == "逃げ" and front_collapse_score <= 30:
        tare_penalty_1 = 20
        tare_penalty_2 = 40
        tare_penalty_3 = 60
    else:
        tare_penalty_1 = 40
        tare_penalty_2 = 70
        tare_penalty_3 = 100

    # 4角5番手以内から6着以下
    if finish is not None:

        if last <= 5 and finish >= 6:
            score -= tare_penalty_1

        # 4角4番手以内から8着以下
        if last <= 4 and finish >= 8:
            score -= tare_penalty_2

        # 4角3番手以内から10着以下
        if last <= 3 and finish >= 10:
            score -= tare_penalty_3
    # 軸馬タイプに合わせて、展開馬をシンプルに評価する
    # 軸馬が逃げ・先行なら、
    # 前進気勢の強い馬を展開馬候補として加点
    if kyakushoku_type in ["逃げ", "先行"]:
        score += front_score_map.get(horse_no, 0) * 0.5
    # 逃げ：一緒に前で残れる馬
    if kyakushoku_type == "逃げ":
        if avg_first <= 5:
            score += 45
        if avg_last <= 5:
            score += 45
        if abs(avg_last - avg_first) <= 2:
            score += 30

    # 先行：前〜中団で流れに乗れる馬
    elif kyakushoku_type == "先行":
        if avg_first <= 6:
            score += 40
        if avg_last <= 6:
            score += 40
        if abs(avg_last - avg_first) <= 2:
            score += 35
        score += long_score_map.get(horse_no, 0) * 0.04

    # 差し：前で残れる馬を相手にする
    elif kyakushoku_type == "差し":
        if avg_first <= 5:
            score += 50
        if avg_last <= 6:
            score += 40
        if avg_first >= 8:
            score -= 30

    # 展開待ち：相手は安定して前〜中団にいる馬
    elif kyakushoku_type == "展開待ち":
        if avg_first <= 6:
            score += 45
        if avg_last <= 6:
            score += 45
        if abs(avg_last - avg_first) <= 2:
            score += 35
        if avg_first >= 8 and avg_last >= 8:
            score -= 60

    # 惰性で長く脚を使えるタイプ：
    # 軸馬の位置に近く、同じように長く脚を使える馬
    elif kyakushoku_type == "惰性で長く脚を使えるタイプ":
        position_gap = abs(avg_last - strong_avg_last)

        # 軸馬の4角位置に近い馬
        score += max(0, 70 - position_gap * 15)

        # 前〜中団で流れに乗れる馬
        if 2 <= avg_first <= 7:
            score += 35

        if 2 <= avg_last <= 7:
            score += 35

        # 大きく崩れない馬
        if abs(avg_last - avg_first) <= 2:
            score += 45

        # 長く脚を使えるスコアを少し反映
        score += long_score_map.get(horse_no, 0) * 0.05

        # 完全後方型は下げる
        if avg_first >= 8 and avg_last >= 8:
            score -= 70

    # 前崩れ警戒時だけ、後ろから押し上げる馬を少し加点
        # 前崩れ山型理論
    # 完全後方馬ではなく、
    # 押し上げられる馬を少し評価する

    if front_collapse_score >= 40:

        for flow in race_flows[-3:]:

            if len(flow) < 2:
                continue

            first = flow[0]
            last = flow[-1]

            # 少し後ろから脚を使える馬
            if first >= 5 and last <= 6:
                score += front_collapse_score * 0.3

            # 完全後方馬は評価しない
            if first >= 8 and last >= 8:
                score -= 50
    # 総合3位以内だけ、展開馬スコアに控えめ加点
    # 展開相性を壊さず、相棒としての信頼度だけ少し上げる
    total_rank = pre_total_rank_map.get(horse_no, 99)

    if total_rank <= 3:
        score += 20
        # ほんのり内枠補正：4角である程度前に来れる馬だけ
    if avg_last <= 5:
        if horse_no == 1:
            score += 4
        elif horse_no == 2:
            score += 3.5
        elif horse_no == 3:
            score += 3
        elif horse_no <= 5:
            score += 1.5
    tenkai_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "スコア": score,
        "平均前半": avg_first,
        "平均4角": avg_last,
        "通過順": race_flows
    })

tenkai_candidates = sorted(
    tenkai_candidates,
    key=lambda x: x["スコア"],
    reverse=True
)
if debug_mode:
    st.subheader("展開が向く馬スコア")
    st.write(f"人気馬タイプ：{kyakushoku_type}")
    st.write(f"前崩れ期待度：{front_collapse_score}｜前圧カウント：{front_pressure_count}")
    st.write(f"人気馬 平均前半：{strong_avg_first}｜平均4角：{strong_avg_last}")

    for h in tenkai_candidates:
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜展開スコア {h['スコア']} "
            f"｜平均前半 {h['平均前半']} "
            f"｜平均4角 {h['平均4角']}"
        )

tenkai_best = tenkai_candidates[0]
tenkai_horse = f"{tenkai_best['馬番']}番 {tenkai_best['馬名']}"
# 総合力1位を裏側で判定
front_score_map = {h["馬番"]: h["スコア"] for h in front_candidates}
long_score_map = {h["馬番"]: h["スコア"] for h in long_spurt_candidates}
tenkai_score_map = {h["馬番"]: h["スコア"] for h in tenkai_candidates}

total_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    
    total_score = 0
    finishes = horse.get("着順", [])
    flows = horse.get("通過順", [])
    horse_text = horse.get("取得テキスト", "")

    jra_transfer = any(
        word in horse_text
        for word in [
            "東京", "中山", "京都", "阪神",
            "中京", "新潟", "福島",
            "小倉", "札幌", "函館",
            "3歳未勝利", "３歳未勝利",
            "2歳未勝利", "２歳未勝利"
            
        ]
    )
    # 前進気勢も少しだけ
    total_score += front_score_map.get(horse_no, 0) * 0.10
    # 走破タイムが速い馬を総合力に加点
    distance_times = horse.get("距離付きタイム", [])

    time_seconds = []
    time_score = 0
    best_time = None
    time_weight = 0
    for item in distance_times:

        race_distance = item["距離"]

        # 距離帯が近いものだけ採用
        # 短距離は距離一致を重視
        if distance_num in [1000, 1200, 1230, 1300, 1400]:
            distance_ok = (race_distance == distance_num)

        # 中長距離は近い距離も評価
        elif distance_num >= 1500:
            distance_ok = abs(race_distance - distance_num) <= 300

        else:
            distance_ok = abs(race_distance - distance_num) <= 100
        if not distance_ok:
            continue

        try:
            minutes, seconds = item["タイム"].split(":")
            total_seconds = int(minutes) * 60 + float(seconds)

            past_place = item.get("競馬場", "")

            # 園田・姫路タイム補正
            # 園田開催で姫路の過去タイムを見る時は +5秒
            # 姫路開催で園田の過去タイムを見る時は -5秒
            if baba_name == "園田" and past_place == "姫路":
                total_seconds += 5.0

            elif baba_name == "姫路" and past_place == "園田":
                total_seconds -= 5.0

            time_seconds.append(total_seconds)

        except:
            pass

    if time_seconds:
        best_time = min(time_seconds)

        # 距離一致タイムがある馬の数で、持ちタイム評価の強さを変える
        distance_match_count = 0

        for h in horses:
            if h.get("走破タイム", []):
                distance_match_count += 1

        if distance_match_count >= len(horses) * 0.5:
            time_weight = 2.2
        elif distance_match_count >= 3:
            time_weight = 2.5
        elif distance_match_count >= 1:
            time_weight = 1.2
        else:
            time_weight = 0

        time_score = max(0, 200 - best_time) * time_weight
        total_score += time_score
    # 着順重視（JRA馬はスキップ）
    if not jra_transfer:

        for finish in finishes:

            if finish <= 3:
                total_score += 40

            elif finish <= 5:
                total_score += 20

            elif finish >= 8:
                total_score -= 30

    # 平均着順（JRA馬はスキップ）
    if finishes and not jra_transfer:

        avg_finish = sum(finishes) / len(finishes)

        if avg_finish <= 3:
            total_score += 100

        elif avg_finish <= 5:
            total_score += 60

        elif avg_finish <= 7:
            total_score += 20

        elif avg_finish >= 8:
            total_score -= 50
    horse_text = horse.get("取得テキスト", "")

    
    # 地力（通過順）はJRA馬だけ無視
    if not jra_transfer:
        total_score += long_score_map.get(horse_no, 0) * 0.25
    if jra_transfer:
        # 実験用：JRA転入馬は加点だけ残して減点なし
        total_score += 30
    # 吉村智洋騎手補正
    if "吉村" in horse_text and "智洋" in horse_text:
        total_score += 35
    # 望月洵輝騎手補正
    if "望月" in horse_text:
        total_score += 35
    if not jra_transfer:

        flows = horse.get("通過順", [])
        finishes = horse.get("着順", [])

        for idx, flow in enumerate(flows):
            if len(flow) < 2:
                continue

            first = flow[0]
            last = flow[-1]
            finish = finishes[idx] if idx < len(finishes) else None

            # 逃げたのに大敗
            if first <= 2 and finish is not None and finish >= 7:
                total_score -= 80

            # 前半から4角で大きく後退
            if first <= 3 and last - first >= 4:
                total_score -= 60

            # 4角前にいたのに着順が悪い
            if last <= 4 and finish is not None and finish >= 7:
                total_score -= 70
    total_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "総合スコア": total_score,
        "持ちタイムスコア": time_score,
        "ベストタイム": best_time,
        "タイム係数": time_weight
    })

total_candidates = sorted(
    total_candidates,
    key=lambda x: x["総合スコア"],
    reverse=True
)

total_best = total_candidates[0]
total_fourth = total_candidates[3]
total_fourth_horse = f"{total_fourth['馬番']}番 {total_fourth['馬名']}"
total_best_horse = f"{total_best['馬番']}番 {total_best['馬名']}"
# 総合力1位と先行気勢が被ったら、遊び心で先行気勢4位を採用
if front_best["馬番"] == total_best["馬番"]:
    if len(front_candidates) >= 4:
        front_best = front_candidates[3]
        front_horse = f"{front_best['馬番']}番 {front_best['馬名']}"
if debug_mode:
    st.subheader("総合力ランキング")

    for h in total_candidates:
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜総合スコア {round(h['総合スコア'], 1)} "
            f"｜持ちタイム {round(h['持ちタイムスコア'], 1)} "
            f"｜ベスト {h['ベストタイム']} "
            f"｜係数 {h['タイム係数']}"
        )
# 展開が向く馬と先行気勢の馬が同じなら、
# 先行気勢の馬をスコア2位以降にずらす
# 期待値高めおすすめ穴馬
# 穴馬は「前進気勢スコア3位」を採用する
# ただし、人気馬・展開馬・長く脚の馬と被る場合は次点へずらす

used_for_ana = [
    popular_horse_num,      # 軸馬とは被らない
    total_best["馬番"],     # 総合力1位とは被らない
    front_best["馬番"],     # 先行気勢とは被らない
]

ana_candidates = []

for h in front_candidates:
    if h["馬番"] in used_for_ana:
        continue

    # 最後に垂れる馬は期待値馬から除外
    target_horse = None
    for horse in horses:
        if horse["馬番"] == h["馬番"]:
            target_horse = horse
            break

    ana_score = h["スコア"]

    if target_horse:
        flows = target_horse.get("通過順", [])
        finishes = target_horse.get("着順", [])

        for idx, flow in enumerate(flows):
            if len(flow) < 2:
                continue

            last = flow[-1]
            finish = finishes[idx] if idx < len(finishes) else None

            # 4角前にいたのに着順が悪い馬は、除外せず減点だけ
            if finish is not None and last <= 4 and finish >= 6:
                ana_score -= 50

            # 4角3番手以内から8着以下は強めに減点
            if finish is not None and last <= 3 and finish >= 8:
                ana_score -= 80

    ana_candidates.append({
        "馬番": h["馬番"],
        "馬名": h["馬名"],
        "スコア": ana_score
    })
# 穴候補が少ない時は、他カテゴリの残り馬から掘り返す
if len(ana_candidates) < 3:
    extra_ana_pool = []

    for h in total_candidates:
        if h["馬番"] in used_for_ana:
            continue
        if any(a["馬番"] == h["馬番"] for a in ana_candidates):
            continue

        extra_ana_pool.append({
            "馬番": h["馬番"],
            "馬名": h["馬名"],
            "スコア": h["総合スコア"] * 0.3
        })

    for h in tenkai_candidates:
        if h["馬番"] in used_for_ana:
            continue
        if any(a["馬番"] == h["馬番"] for a in ana_candidates):
            continue

        extra_ana_pool.append({
            "馬番": h["馬番"],
            "馬名": h["馬名"],
            "スコア": h["スコア"] + 20
        })

    extra_ana_pool = sorted(
        extra_ana_pool,
        key=lambda x: x["スコア"],
        reverse=True
    )

    for h in extra_ana_pool:
        if len(ana_candidates) >= 3:
            break
        ana_candidates.append(h)
if debug_mode:
    st.subheader("穴馬候補スコア")
    for h in ana_candidates:
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜前進気勢スコア {h['スコア']}"
        )

if ana_candidates:
    ana_best = ana_candidates[0]
else:
    ana_best = front_candidates[0]

ana_horse = f"{ana_best['馬番']}番 {ana_best['馬名']}"
# 穴馬候補2位
if len(ana_candidates) >= 2:
    ana_second = ana_candidates[1]
else:
    ana_second = ana_candidates[-1]

ana_second_horse = f"{ana_second['馬番']}番 {ana_second['馬名']}"

# 穴馬候補3位
if len(ana_candidates) >= 3:
    ana_third = ana_candidates[2]
else:
    ana_third = ana_candidates[-1]

ana_third_horse = f"{ana_third['馬番']}番 {ana_third['馬名']}"
st.subheader("軸馬の脚色タイプ")

st.markdown(
    f"""
    <div style="
        background-color:#f3f6fb;
        padding:14px;
        border-radius:10px;
        color:#222222;
        font-size:16px;
        font-weight:400;
        margin-bottom:10px;
    ">
    <b>{popular_horse_num}番 {real_horses[popular_horse_num - 1]}</b><br>
    軸馬：<b>{kyakushoku_type}</b><br>
    </div>
    """,
    unsafe_allow_html=True
)
st.markdown(
    f"""
    <div style="
        background-color:#f8eaea;
        padding:15px;
        border-radius:10px;
        color:#222222;
        font-size:16px;
font-weight:400;
    ">
    ◎ 軸馬 {popular_horse_label}
    （オッズは変わるので軸は適宜変更してください）
    </div>
    """,
    unsafe_allow_html=True
)
st.write(f"◉ 総合力1位 {total_best_horse}")
st.caption("総合力上位候補")


st.info(f"○ 地力があり狙い目の馬 {long_spurt_horse}")
st.caption("長く脚を使えるタイプ")

st.markdown(
    f"""
    <div style="
        background-color:#f6f3df;
        padding:15px;
        border-radius:10px;
        color:#222222;
        font-weight:400;
        font-size:16px;
    ">
    ▲ 展開が向く馬 {tenkai_horse}
    </div>
    """,
    unsafe_allow_html=True
)
st.caption("軸馬の脚色と合うタイプ")
st.write(f"△ 先行気勢の強い馬\n{front_horse}")
st.caption("積極的に前に行けるタイプ")

st.write(f"☆ 押さえておきたい馬\n{ana_horse}")
st.caption("拾っておきたいタイプ")
def get_num(horse_text):
    return int(horse_text.split("番")[0])

def add_unique_bet(bets, bet, max_count=2):
    nums = [get_num(h) for h in bet]

    # 1つの買い目内で同じ馬がいたら除外
    if len(nums) != len(set(nums)):
        return bets

    # 同じ買い目の重複を除外
    bet_key = tuple(sorted(nums))
    existing_keys = [
        tuple(sorted(get_num(h) for h in b))
        for b in bets
    ]

    if bet_key not in existing_keys and len(bets) < max_count:
        bets.append(bet)

    return bets

def candidate_text_list(candidates):
    result = []
    for h in candidates:
        text = f"{h['馬番']}番 {h['馬名']}"
        if text not in result:
            result.append(text)
    return result


popular = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"

tenkai_list = candidate_text_list(tenkai_candidates)
front_list = candidate_text_list(front_candidates)
ana_list = candidate_text_list(ana_candidates)
long_list = candidate_text_list(long_spurt_candidates)

# 念のため空なら現在の選出馬を入れる
if not ana_list:
    ana_list = [ana_horse]

if not tenkai_list:
    tenkai_list = [tenkai_horse]

if not front_list:
    front_list = [front_horse]
# 三連複2点
st.subheader("おすすめの三連複 2点")

trio_bets = []
# 南関判定
is_nankan = any(
    x in baba_name
    for x in ["浦和", "船橋", "大井", "川崎"]
)

# 南関用の先行気勢2位
nankan_front_horse = front_horse

if is_nankan and len(front_candidates) >= 2:
    second_front = front_candidates[1]

    nankan_front_horse = (
        f"{second_front['馬番']}番 "
        f"{second_front['馬名']}"
    )
popular = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"
total_horse = total_best_horse
long_horse = long_spurt_horse
tenkai_horse_text = tenkai_horse

# 本線
henna_ba_active = (
    total_best["馬番"] == long_best["馬番"]
    and total_best["馬番"] == popular_horse_num
)
trio_patterns = [

    # ◎1点目基本：軸馬－展開馬－先行馬
    [popular, tenkai_horse_text, front_horse],

    # ◎2点目基本：総合1位－地力馬－穴3位
    [total_horse, long_horse, ana_third_horse],

    # 総合と地力が被った時の逃げ道
    [total_horse, ana_horse, ana_third_horse],

    # 地力と総合が被った時
    [total_horse, popular, ana_third_horse],
    # 穴2位・穴3位へ逃がす
    [total_horse, popular, ana_second_horse],
    [total_horse, popular, ana_third_horse],
    [total_horse, long_horse, ana_second_horse],
    [total_horse, long_horse, ana_third_horse],
    [popular, tenkai_horse_text, ana_second_horse],
    [popular, tenkai_horse_text, ana_third_horse],
    # 総合と軸馬が被った時
    [total_horse, long_horse, ana_horse],
    # 総合と軸馬が被った時の追加保険
    [total_horse, long_horse, ana_third_horse],
    [total_horse, tenkai_horse_text, ana_third_horse],
    [popular, long_horse, ana_third_horse],
    [total_horse, tenkai_horse_text, nankan_front_horse],
    [popular, tenkai_horse_text, nankan_front_horse],
    [total_horse, nankan_front_horse, ana_third_horse],
    # 保険
    [popular, tenkai_horse_text, ana_horse],
    [total_horse, tenkai_horse_text, ana_third_horse],

    # 南関
    [total_horse, long_horse, nankan_front_horse],
    [popular, tenkai_horse_text, nankan_front_horse],
]
if henna_ba_active:
        trio_patterns.append(
            [
                popular,
                ana_third_horse,
                total_fourth_horse
            ]
        )

for pattern in trio_patterns:
    trio_bets = add_unique_bet(
        trio_bets,
        pattern,
        max_count=2
    )

    if len(trio_bets) >= 2:
        break
# 軸馬流しを先に表示
trio_bets = sorted(
    trio_bets,
    key=lambda x: 0 if (tenkai_horse_text in x and front_horse in x) else 1
)
for bet in trio_bets:
    st.write(f"{bet[0]} - {bet[1]} - {bet[2]}")
# ワイド 本線2点＋カッパの浮き輪保険1点
st.subheader("おすすめのワイド２点")

wide_bets = []

popular = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"
tenkai_horse_text = tenkai_horse

# 本線2点
wide_patterns = [
    # 本線1：軸馬 × 展開馬
    [popular, tenkai_horse_text],

    # 本線2：軸馬 × 押さえておきたい馬
    [popular, ana_horse],

    # 被った時の逃げ道
    [popular, long_spurt_horse],
    [popular, total_best_horse],
]

for pattern in wide_patterns:
    wide_bets = add_unique_bet(
        wide_bets,
        pattern,
        max_count=2
    )

    if len(wide_bets) >= 2:
        break

for bet in wide_bets:
    st.write(f"{bet[0]} - {bet[1]}")

# カッパの浮き輪保険
st.markdown("### 🛟 カッパの浮き輪保険")

float_bets = []

float_patterns = [
    # 初心者さん向けの保険：軸馬 × 先行気勢の強い馬
    [popular, front_horse],

    # 被った時の逃げ道
    [popular, long_spurt_horse],
    [popular, tenkai_horse_text],
    [popular, ana_horse],
]

for pattern in float_patterns:
    float_bets = add_unique_bet(
        float_bets,
        pattern,
        max_count=1
    )

    if len(float_bets) >= 1:
        break

for bet in float_bets:
    st.write(f"{bet[0]} - {bet[1]}")

st.caption(
    "※買い目の一例です。最終判断はオッズや馬場を見て調整してください。"
)