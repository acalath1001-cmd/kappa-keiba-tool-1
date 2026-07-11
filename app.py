import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
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
    "10": "盛岡競馬",
    "11": "水沢競馬",
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
# 馬場状態を自動判定
baba_match = re.search(r"馬場[:：]\s*(良|稍重|重|不良)", page_text)

if baba_match:
    baba_status = baba_match.group(1)
else:
    baba_status = "不明"

if baba_status in ["重", "不良"]:
    st.info("馬場状態：重・不良")
else:
    st.info("馬場状態：良")
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

print(f"{distance}m戦")

# 距離カテゴリ
distance_num = int(distance) if str(distance).isdigit() else 1400

if distance == "1400":
    print("前有利コース")

elif distance == "1200":
    print("先行有利")

elif distance == "1800":
    print("差し注意")

else:
    print("データ不足")
st.write("出走馬一覧")

rows = soup.find_all("tr")

pattern = r"(?:^|\s)(?:[1-8]\s+)?([1-9][0-9]?)\s+([ァ-ヴー]{2,})\s+"

matches = re.findall(pattern, page_text)

real_horses = []

for num, name in matches:
    if name not in real_horses:
        real_horses.append(name)

horses = []

for i, horse in enumerate(real_horses, start=1):

    horse_text = ""
    horse_row = None
    # 馬名を含む row から下の15 row をまとめて取得
    for idx, row in enumerate(rows):
        row_text = row.get_text(" ", strip=True)
# 着別成績・最高タイム側の 3-2-1-4 などを除外するため、
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

    # 距離・タイム・通過順を取得
    # 笠松など「タイムと距離が別行」の競馬場に対応するため
    # 除外・取消を除いた日付行から距離を取得し、
    # タイムと通過順はhorse_text全体から別途取得してインデックス対応

    distance_time_pairs = []
    race_times = []

    # ① 除外・取消を除いた日付行から距離を順番に取得
    valid_distances = []
    valid_places = []

    date_blocks = re.split(r"(?=\d{2}\.\d{2}\.\d{2})", horse_text)

    for block in date_blocks:
        if any(word in block for word in ["除外", "取消", "中止", "競走除外", "出走取消"]):
            continue

        d_match = re.search(
            r"(?:右|左|芝|ダ)\s*"
            r"(800|820|850|900|920|1000|1200|1230|1300|1400|1500|1600|1700|1800|1870|1900|2000|2100|2200)",
            block
        )
        if not d_match:
            continue

        place_match = re.search(r"(園田|姫路)", block)
        valid_distances.append(int(d_match.group(1)))
        valid_places.append(place_match.group(1) if place_match else "")

    # ② タイム＋通過順のペアをhorse_text全体から順番に取得
    time_flow_pairs = re.findall(
        r"(\d+:\d{2}\.\d+)[\s　]{1,6}(\d{1,2}-\d{1,2}(?:-\d{1,2})?(?:-\d{1,2})?)",
        horse_text
    )

    valid_time_flows = []

    for idx, (time_text, flow_text) in enumerate(time_flow_pairs):

        try:
            minutes, seconds = time_text.split(":")
            total_sec = int(minutes) * 60 + float(seconds)

            # 今回の距離ではなく、過去走の距離を使う
            past_distance = (
                valid_distances[idx]
                if idx < len(valid_distances)
                else 0
            )

            # 過去走距離に応じて短すぎる区間タイムを除外
            if past_distance >= 1400:
                if total_sec < 70:
                    continue

            elif past_distance >= 1200:
                if total_sec < 60:
                    continue

            elif past_distance >= 1000:
                if total_sec < 50:
                    continue

            # 800m・820m・850m・900mは
            # 50秒前後になるので、ここでは除外しない

        except:
            continue

        flow_nums = [int(x) for x in flow_text.split("-")]

        if 0 in flow_nums:
            continue

        if any(n >= 30 for n in flow_nums):
            continue

        valid_time_flows.append((time_text, flow_nums))

    # ③ インデックスで対応付け（件数が少ない方に合わせる）
    pair_count = min(len(valid_distances), len(valid_time_flows))

    for idx in range(pair_count):
        time_text, flow_nums = valid_time_flows[idx]
        distance_time_pairs.append({
            "距離": valid_distances[idx],
            "タイム": time_text,
            "競馬場": valid_places[idx],
            "通過順": flow_nums
        })
        race_times.append(time_text)

    # 最後の5走分に絞る
    distance_time_pairs = distance_time_pairs[-5:]
    race_times = race_times[-5:]

    # race_flowsも distance_time_pairs から取り直す
    race_flows = [pair["通過順"] for pair in distance_time_pairs]
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
    # 出走取消・競走除外判定
    is_scratched = any(
        word in horse_text
        for word in ["出走取消", "競走除外", "出走除外"]
    )
    if debug_mode:
        st.write(
            f"{i}番 {horse}｜距離付きタイム数 {len(distance_time_pairs)} "
            f"｜通過順数 {len(race_flows)} "
            f"｜着順数 {len(finish_positions)}"
        )
    horses.append({
        "馬番": i,
        "馬名": horse,
        "取消除外": is_scratched,
        "通過順": race_flows,
        "走破タイム": race_times,
        "距離付きタイム": distance_time_pairs,
        "着順": finish_positions,
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
# データ不足注意
low_data_horses = []

for h in horses:
    # 着順数（取得できたレース数）
    result_count = len(h.get("着順", []))

    # 過去5走ある中で、取得できたレースが2走以下なら警告
    if result_count <= 2:
        low_data_horses.append(
            f"{h['馬番']}番 {h['馬名']}"
        )

if low_data_horses:
    st.warning(
        "⚠️ 過去データが不足している馬がいます。\n\n"
        + "・" + "\n・".join(low_data_horses)
        + "\n\n過去5走ある中で取得できたデータが少ないため、"
        "評価の信頼度は少し下がります。"
    )
# ランダム予想を廃止
# ここからはスコア順で選出する

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
popular_horse_label = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"

# 4角位置が取れていない馬も含めてスコア確認できるようにする
front_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]

    front_score = calc_front_score(
        horse_no,
        horse["通過順"],
        horse.get("着順", [])
    )
    # 距離短縮で逃げ経験がある馬は、前進気勢にだけ加点
    if distance_num <= 1400:
        for item in horse.get("距離付きタイム", []):
            past_distance = item["距離"]
            flow = item["通過順"]

            if past_distance > distance_num and len(flow) >= 2:
                if flow[0] == 1:
                    front_score += 120
                elif flow[0] == 2:
                    front_score += 60
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
    # 持続評価にも距離フィルターを入れる
    filtered_flows = []

    for item in horse.get("距離付きタイム", []):
        race_distance = item["距離"]

        if distance_num == 1400:
            distance_ok = (
                abs(race_distance - distance_num) <= 200
                and race_distance >= 1200
            )
        elif distance_num >= 1500:
            distance_ok = abs(race_distance - distance_num) <= 300
        else:
            distance_ok = abs(race_distance - distance_num) <= 100

        if distance_ok:
            filtered_flows.append(item["通過順"])

    if filtered_flows:
        race_flows = filtered_flows[-5:]

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
    # ただし後方すぎる馬は地力馬としては評価しすぎない
    if 5 <= avg_first <= 7 and avg_last <= avg_first - 2:
        score += 80

    elif avg_first >= 8 and avg_last <= avg_first - 2:
        score += 20
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
                score -= 180 * recent_bonus
                tare_count += 1

            elif drop >= 3:
                score -= 120 * recent_bonus
                tare_count += 1

            elif drop >= 2:
                score -= 60 * recent_bonus
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
if not long_spurt_display_candidates:
    long_spurt_display_candidates = long_spurt_candidates
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

# 仮の総合力1位を先に決める
front_score_map = {h["馬番"]: h["スコア"] for h in front_candidates}
long_score_map = {h["馬番"]: h["スコア"] for h in long_spurt_candidates}

pre_total_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]

    # 前進気勢は全馬共通
    pre_total_score = front_score_map.get(horse_no, 0) * 0.10


    # 距離フィルター付きのタイムだけ使う
    distance_times = horse.get("距離付きタイム", [])
    same_distance_exists = any(
        x["距離"] == distance_num for x in distance_times
    )
    pre_time_seconds = []

    for item in distance_times:
        race_distance = item["距離"]
        if same_distance_exists:
            distance_ok = (race_distance == distance_num)
        else:
            if distance_num == 1400:
                distance_ok = (abs(race_distance - distance_num) <= 200 and race_distance >= 1200)
            elif distance_num >= 1500:
                distance_ok = abs(race_distance - distance_num) <= 300
            else:
                distance_ok = abs(race_distance - distance_num) <= 100
        if not distance_ok:
            continue
        try:
            minutes, seconds = item["タイム"].split(":")
            pre_time_seconds.append(int(minutes) * 60 + float(seconds))
        except:
            pass

    if pre_time_seconds:
        best_time = min(pre_time_seconds)
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

for idx, flow in enumerate(strong_flows):
    if len(flow) < 2:
        continue

    first = flow[0]
    last = flow[-1]
    finishes = strong_data.get("着順", []) if strong_data else []
    finish = finishes[idx] if idx < len(finishes) else None
    # 逃げ・先行経験
    if first <= 2:
        strong_front_count += 1

    # 前〜中団で大きく崩れず長く脚を使う
    if 3 <= first <= 6 and 3 <= last <= 6 and abs(last - first) <= 2:
        strong_stable_count += 1
    # 中団〜後方から脚を使える馬を差し候補にする
    if distance_num >= 1500:
        if (
            first >= 6
            and finish is not None
            and (
                (
                    last <= 7
                    and last < first
                    and (first - last) >= 2
                    and finish <= 5
                )
                or (
                    first >= 7
                    and finish <= 3
                )
            )
        ):
            strong_push_count += 1
    else:
        if first >= 6 and last <= 5 and last < first:
            strong_push_count += 1

        # ジワ差し救済：後方から4角7番手以内まで押し上げて、着順も悪くない馬
        if (
            first >= 6
            and last < first
            and last <= 7
            and finish is not None
            and finish <= 4
        ):
            strong_push_count += 1

    # 押し上げ差し型の救済
    # 押し上げ差し型の救済
    # 1400m以上なら、後方〜中団から4角で射程圏に来る馬を差しで拾う
    if (
        distance_num >= 1400
        and finish is not None
        and first >= 5
        and last <= 4
        and last < first
        and finish <= 5
    ):
        strong_push_count += 1
    if first >= 7 and last >= 7 and finish is not None and finish <= 2:
        strong_push_count += 1

    # 後方のまま
    if first >= 7 and last >= 7:
        strong_back_count += 1


# 逃げ判定：2角・3角に1が多い馬を逃げにする
# 通過順が2個しかない場合は、1-1 / 1-2 / 2-1 を逃げ扱いにする

strong_escape_count = 0

for flow in strong_flows:
    if len(flow) >= 4:
        second = flow[1]
        third = flow[2]

        if second == 1 or third == 1:
            strong_escape_count += 1

    elif len(flow) == 2:
        first = flow[0]
        second = flow[1]

        if first == 1 or second == 1:
            strong_escape_count += 1

# 逃げ率を計算
valid_flow_count = len(
    [flow for flow in strong_flows if len(flow) >= 2]
)

escape_rate = (
    strong_escape_count / valid_flow_count
    if valid_flow_count > 0
    else 0
)

push_rate = (
    strong_push_count / valid_flow_count
    if valid_flow_count > 0
    else 0
)

# ①逃げ：過去走の50%以上で逃げっぽい競馬
if escape_rate >= 0.5:
    kyakushoku_type = "逃げ"

# ②先行
elif (
    (strong_avg_first <= 4 and strong_avg_last <= 5)
    or strong_front_count >= 2
):
    kyakushoku_type = "先行"

# ③差し
elif (
    push_rate >= 0.4
    or (
        distance_num >= 1500
        and push_rate >= 0.3
    )
    # ジワ差し昇格：差し回数は少なくても、後方のままではなく4角で射程圏に来る馬
    or (
        strong_push_count >= 1
        and strong_back_count <= 2
        and strong_avg_last <= 7
        and strong_avg_first >= 6
    )
):
    kyakushoku_type = "差し"

# ④持続
elif (
    strong_stable_count >= 2
    or (
        3 <= strong_avg_first <= 6
        and 3 <= strong_avg_last <= 6
        and abs(strong_avg_last - strong_avg_first) <= 2
    )
    # 強い持続差し型の救済
    # 例：平均前半4〜5番手 → 4角1〜2番手、着順も安定
    or (
        strong_stable_count >= 1
        and strong_push_count >= 1
        and strong_avg_last <= 3
    )
):
    kyakushoku_type = "持続"

# ⑤展開待ち
else:
    kyakushoku_type = "展開待ち"
    if debug_mode:
        st.subheader("軸馬脚色デバッグ")

        st.write(f"逃げ率：{round(escape_rate,2)}")
        st.write(f"差し率：{round(push_rate,2)}")

        st.write(f"平均前半：{round(strong_avg_first,2)}")
        st.write(f"平均4角：{round(strong_avg_last,2)}")

        st.write(f"逃げカウント：{strong_escape_count}")
        st.write(f"先行カウント：{strong_front_count}")
        st.write(f"持続カウント：{strong_stable_count}")
        st.write(f"差しカウント：{strong_push_count}")
        st.write(f"後方カウント：{strong_back_count}")

        st.write(f"最終判定：{kyakushoku_type}")
# 軸馬が展開待ちになった時だけ、近いタイプへ逃がす
if kyakushoku_type == "展開待ち":

    if strong_avg_first <= 4:
        kyakushoku_type = "先行"

    elif strong_push_count >= 1:
        kyakushoku_type = "差し"

    elif strong_stable_count >= 1:
        kyakushoku_type = "持続"

    elif strong_avg_first <= 6:
        kyakushoku_type = "持続"

    else:
        kyakushoku_type = "差し"
# 人気馬が差してくるタイプなのに先行気勢1位にも出る場合は、
# 先行気勢の馬を次点候補にずらす
if kyakushoku_type == "差し" and front_best["馬番"] == popular_horse_num:
    for h in front_candidates:
        if h["馬番"] != popular_horse_num:
            front_best = h
            front_horse = f"{front_best['馬番']}番 {front_best['馬名']}"
            break
# 展開馬用：今回距離で使える最速タイムを先に探す
# 1400m戦では820m・900mなどは使わない
fastest_same_distance_time_for_tenkai = None

for h in horses:
    distance_times = h.get("距離付きタイム", [])

    same_distance_exists = any(
        x["距離"] == distance_num
        for x in distance_times
    )

    for item in distance_times:
        race_distance = item["距離"]

        if same_distance_exists:
            distance_ok = (race_distance == distance_num)
        else:
            if distance_num == 1400:
                distance_ok = (
                    abs(race_distance - distance_num) <= 200
                    and race_distance >= 1200
                )
            elif distance_num in [1200, 1230, 1300]:
                distance_ok = (
                    abs(race_distance - distance_num) <= 200
                    and race_distance >= 1000
                )
            elif distance_num >= 1900:
                distance_ok = race_distance in [
                    1600, 1700, 1800, 1870, 1900, 2000, 2100
                ]
            elif distance_num >= 1500:
                distance_ok = abs(race_distance - distance_num) <= 300
            else:
                distance_ok = abs(race_distance - distance_num) <= 100

        if not distance_ok:
            continue

        try:
            minutes, seconds = item["タイム"].split(":")
            t = int(minutes) * 60 + float(seconds)

            if (
                fastest_same_distance_time_for_tenkai is None
                or t < fastest_same_distance_time_for_tenkai
            ):
                fastest_same_distance_time_for_tenkai = t

        except:
            pass
  # JRA転入馬の割合を先に計算しておく
jra_count = 0

for h in horses:
    horse_text = h.get("取得テキスト", "")

    if any(
        word in horse_text
        for word in [
            "東京", "中山", "京都", "阪神",
            "中京", "新潟", "福島",
            "小倉", "札幌", "函館",
            "3歳未勝利", "３歳未勝利",
            "2歳未勝利", "２歳未勝利"
        ]
    ):
        jra_count += 1

jra_rate = (
    jra_count / len(horses)
    if len(horses) > 0
    else 0
)     
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
    long_score = long_score_map.get(horse_no, 0)
    # 展開馬の一次試験：今回距離で戦えるタイムがあるか
    tenkai_best_time = None
    distance_times = horse.get("距離付きタイム", [])

    # 展開馬のタイム評価
    # 距離一致を最優先。
    # 1400m戦で800m・820m・900mのタイムを評価しない。

    same_distance_exists = any(
        x["距離"] == distance_num
        for x in distance_times
    )

    for item in distance_times:
        race_distance = item["距離"]

        if same_distance_exists:
            distance_ok = (race_distance == distance_num)
        else:
            if distance_num == 1400:
                distance_ok = (
                    abs(race_distance - distance_num) <= 200
                    and race_distance >= 1200
                )
            elif distance_num in [1200, 1230, 1300]:
                distance_ok = (
                    abs(race_distance - distance_num) <= 200
                    and race_distance >= 1000
                )
            elif distance_num >= 1900:
                distance_ok = race_distance in [
                    1600, 1700, 1800, 1870, 1900, 2000, 2100
                ]
            elif distance_num >= 1500:
                distance_ok = abs(race_distance - distance_num) <= 300
            else:
                distance_ok = abs(race_distance - distance_num) <= 100

        if not distance_ok:
            continue

        try:
            minutes, seconds = item["タイム"].split(":")
            t = int(minutes) * 60 + float(seconds)

            if tenkai_best_time is None or t < tenkai_best_time:
                tenkai_best_time = t

        except:
            pass

    if (
        tenkai_best_time is not None
        and fastest_same_distance_time_for_tenkai is not None
    ):
        diff = tenkai_best_time - fastest_same_distance_time_for_tenkai

        if diff >= 3.0:
            score -= 300
        elif diff >= 2.0:
            score -= 220
        elif diff >= 1.5:
            score -= 140
        elif diff >= 1.0:
            score -= 80

    else:
        # 今回距離で使える展開タイムがない馬は未知数として強めに減点
        score -= 180
    # 着順が悪い馬は展開評価を少し下げる
    finishes = horse.get("着順", [])

    if finishes:
        # 展開馬の足切り：近走で着順が悪すぎる馬は除外
        # 例：10,6,12,12,11 みたいな馬
        if finishes:
            avg_finish = sum(finishes) / len(finishes)
            best_finish = min(finishes)
            bad_finish_count = sum(1 for f in finishes if f >= 8)

        # JRA転入馬が多いレースは足切りしない


        if jra_rate < 0.7:

            if avg_finish >= 8 and best_finish >= 6:
                continue

            if bad_finish_count >= 4:
                continue

        if avg_finish >= 8:
            score -= 80
        elif avg_finish >= 6:
            score -= 40

        if bad_finish_count >= 3:
            score -= 80
        elif bad_finish_count >= 2:
            score -= 40
    # 軸馬が逃げで前崩れ期待が低い時は、前残り想定なので減点をゆるめる
    if kyakushoku_type == "逃げ" and front_collapse_score <= 30:
        tare_penalty_1 = 20
        tare_penalty_2 = 40
        tare_penalty_3 = 60
    else:
        tare_penalty_1 = 40
        tare_penalty_2 = 70
        tare_penalty_3 = 100

    # 前で競馬したのに最後垂れる馬は展開評価を下げる
    for idx, flow in enumerate(race_flows):

        if len(flow) < 2:
            continue

        first = flow[0]
        last = flow[-1]
        finish = finishes[idx] if idx < len(finishes) else None

        # 前に行けるけど大きく順位を落とす馬は展開馬から下げる
        if first <= 3 and last - first >= 3:
            score -= 180

        elif first <= 5 and last - first >= 4:
            score -= 140

        if finish is None:
            continue

        # 4角からゴールまでに何頭に抜かれたかを評価
        drop = finish - last

        # 地方競馬では、4角から大きく順位を落とす馬は
        # 踏ん張れない・走るのを止める可能性があるため強く減点
        if drop >= 5:
            score -= 260

        elif drop >= 4:
            score -= 180

        elif drop >= 3:
            score -= 110

        elif drop >= 2:
            score -= 40
     # 軸馬タイプを大きく2系統で見る
    # 逃げ・先行・展開待ち
    # → 先行できて垂れない馬を相手にする
    # 逃げ軸は前残り狙い
    if kyakushoku_type == "逃げ":

        score += front_score_map.get(horse_no, 0) * 0.9

        if avg_first <= 2:
            score += 140
        elif avg_first <= 4:
            score += 100

        if avg_last <= 4:
            score += 100

        # 前で粘れる馬を高評価
        if abs(avg_last - avg_first) <= 2:
            score += 80

        # 後方待機馬は評価しない
        if avg_first >= 6:
            score -= 120

    # 先行 → 先行＋持続
    elif kyakushoku_type == "先行":

        score += front_score_map.get(horse_no, 0) * 0.8

        long_score = long_score_map.get(horse_no, 0)
        if long_score > 0:
            score += long_score * 0.04

        if avg_first <= 3:
            score += 120
        elif avg_first <= 5:
            score += 90

        if avg_last <= 4:
            score += 100
        elif avg_last <= 6:
            score += 70

    # 前圧が高い時だけ、差し・地力タイプを少し評価する
    if front_collapse_score >= 70:

        # 中団から4角までに押し上げる馬
        if avg_first >= 5 and avg_last < avg_first and avg_last <= 6:
            score += 50

        # 地力上位馬を少しだけ上げる
        if long_score > 0:
            score += long_score * 0.07

    # 持続 → 持続馬を展開馬にする
    elif kyakushoku_type == "持続":

        long_score = long_score_map.get(horse_no, 0)
        if long_score > 0:
            score += long_score * 0.25

        # 持続型：前〜中団で大きく動かず脚を使える馬
        if 3 <= avg_first <= 6 and 3 <= avg_last <= 6:
            score += 160

        # 位置取りが安定している馬を評価
        if abs(avg_last - avg_first) <= 2:
            score += 120

        # 前すぎる逃げ馬は少し下げる
        if avg_first <= 2:
            score -= 80

        # 後方すぎる馬も下げる
        if avg_first >= 8:
            score -= 80

    # 差し
    elif kyakushoku_type == "差し":

        # 差し軸なら距離に関係なく差し・持続タイプを相手にする
        long_score = long_score_map.get(horse_no, 0)
        if long_score > 0:
            score += long_score * 0.20

        # 前〜中団で長く脚を使える馬
        if 3 <= avg_first <= 6 and 3 <= avg_last <= 6:
            score += 160

        # 中団〜後方から差して来る馬も少し評価
        if avg_first >= 5 and avg_last < avg_first:
            score += 90

        # 位置取りが安定している馬
        if abs(avg_last - avg_first) <= 2:
            score += 120

        # 逃げ・先行タイプは少し減点
        if avg_first <= 2:
            score -= 80
        elif avg_first <= 4:
            score -= 40

    # 展開待ち → 前で残れる先行馬を展開馬にする
    elif kyakushoku_type == "展開待ち":

        score += front_score_map.get(horse_no, 0) * 0.8

        if avg_first <= 3:
            score += 120
        elif avg_first <= 5:
            score += 90

        if avg_last <= 4:
            score += 100
        elif avg_last <= 6:
            score += 70

        # 後方タイプは展開馬にしにくくする
        if avg_first >= 7:
            score -= 100
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
        score += 10
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
    # 展開候補の脚色タイプを判定する
    target_stable_count = 0
    target_push_count = 0
    target_escape_count = 0

    target_valid_count = len([
        flow for flow in race_flows
        if len(flow) >= 2
    ])

    for idx2, flow2 in enumerate(race_flows):
        if len(flow2) < 2:
            continue

        first2 = flow2[0]
        last2 = flow2[-1]
        finish2 = finishes[idx2] if idx2 < len(finishes) else None

        # 逃げ判定
        if len(flow2) >= 4:
            second2 = flow2[1]
            third2 = flow2[2]

            if second2 == 1 or third2 == 1:
                target_escape_count += 1

        elif len(flow2) == 2:
            second2 = flow2[1]

            if first2 == 1 or second2 == 1:
                target_escape_count += 1

        # 持続判定
        if 3 <= first2 <= 6 and 3 <= last2 <= 6 and abs(last2 - first2) <= 2:
            target_stable_count += 1

        # 差し判定
        if distance_num >= 1500:
            if (
                first2 >= 6
                and finish2 is not None
                and (
                    (
                        last2 <= 7
                        and last2 < first2
                        and (first2 - last2) >= 2
                        and finish2 <= 5
                    )
                    or (
                        first2 >= 7
                        and finish2 <= 3
                    )
                )
            ):
                target_push_count += 1
        else:
            if first2 >= 6 and last2 <= 5 and last2 < first2:
                target_push_count += 1

            # ジワ差し救済：後方から4角7番手以内まで押し上げて、着順も悪くない馬
            if (
                first2 >= 6
                and last2 < first2
                and last2 <= 7
                and finish2 is not None
                and finish2 <= 4
            ):
                target_push_count += 1

        # 押し上げ差し型の救済
        if (
            distance_num >= 1400
            and finish2 is not None
            and first2 >= 5
            and last2 <= 4
            and last2 < first2
            and finish2 <= 5
        ):
            target_push_count += 1

        # 後方から着に来た馬
        if first2 >= 7 and last2 >= 7 and finish2 is not None and finish2 <= 2:
            target_push_count += 1

    target_escape_rate = (
        target_escape_count / target_valid_count
        if target_valid_count > 0
        else 0
    )

    target_push_rate = (
        target_push_count / target_valid_count
        if target_valid_count > 0
        else 0
    )

    target_type = "展開待ち"

    if target_escape_rate >= 0.5:
        target_type = "逃げ"

    elif avg_first <= 4 and avg_last <= 5:
        target_type = "先行"

    elif (
        target_push_rate >= 0.4
        or (
            distance_num >= 1500
            and target_push_rate >= 0.3
        )
    ):
        target_type = "差し"

    elif (
        target_stable_count >= 2
        or (
            3 <= avg_first <= 6
            and 3 <= avg_last <= 6
            and abs(avg_last - avg_first) <= 2
        )
        or (
            target_stable_count >= 1
            and target_push_count >= 1
            and avg_last <= 3
        )
    ):
        target_type = "持続"

    # 展開待ちタイプは除外せず、減点して候補には残す
    if target_type == "展開待ち":
        score -= 120
    tenkai_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "スコア": score,
        "平均前半": avg_first,
        "平均4角": avg_last,
        "通過順": race_flows,
        "展開タイム": tenkai_best_time,
        "タイム差": (
            tenkai_best_time - fastest_same_distance_time_for_tenkai
            if tenkai_best_time is not None
            and fastest_same_distance_time_for_tenkai is not None
            else None
        )
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
            f"｜平均4角 {h['平均4角']} "
            f"｜展開タイム {h.get('展開タイム')} "
            f"｜最速差 {h.get('タイム差')}"
        )

if not tenkai_candidates:
    st.error("展開馬候補が0頭になりました")
    st.stop()
# 850m以下で軸が逃げなら、展開馬も逃げ・先行寄りにする
tenkai_best = tenkai_candidates[0]
tenkai_horse = f"{tenkai_best['馬番']}番 {tenkai_best['馬名']}"

# 念のため、軸馬と展開馬が被ったら展開2位へずらす
if tenkai_best["馬番"] == popular_horse_num:
    for h in tenkai_candidates:
        if h["馬番"] != popular_horse_num:
            tenkai_best = h
            tenkai_horse = f"{h['馬番']}番 {h['馬名']}"
            break
# JRA転入馬が多いレースは警告表示

if jra_rate >= 0.7:
    st.warning(
        "⚠️ JRA転入馬が多いレースです。\n\n"
        "地力・展開評価の信頼度が低くなるため、"
        "総合力や持ちタイムも参考にしてください。"
    )
# 総合力1位を裏側で判定
front_score_map = {h["馬番"]: h["スコア"] for h in front_candidates}
long_score_map = {h["馬番"]: h["スコア"] for h in long_spurt_candidates}

total_candidates = []
# 今回の距離と完全一致する最速タイムを探す
fastest_same_distance_time = None

for horse in horses:
    for item in horse.get("距離付きタイム", []):

        if item["距離"] != distance_num:
            continue

        try:
            minutes, seconds = item["タイム"].split(":")
            t = int(minutes) * 60 + float(seconds)

            if fastest_same_distance_time is None or t < fastest_same_distance_time:
                fastest_same_distance_time = t

        except:
            pass

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    
    total_score = 0
    finishes = horse.get("着順", [])
    flows = horse.get("通過順", [])
    horse_text = horse.get("取得テキスト", "")
    # 平均1角位置補正
    first_positions = []

    for flow in flows:
        if len(flow) >= 1:
            first_positions.append(flow[0])

    if first_positions:

        avg_first = sum(first_positions) / len(first_positions)

        if avg_first <= 4:
            total_score += 15

        elif avg_first <= 6:
            total_score += 5

        elif avg_first >= 7:
            total_score -= 15
    debug_total_parts = {
        "前進気勢": 0,
        "持ちタイム": 0,
        "着順": 0,
        "平均着順": 0,
        "地力": 0,
        "JRA": 0,
        "騎手": 0,
        "減点": 0,
    }
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
    front_part = front_score_map.get(horse_no, 0) * 0.12
    total_score += front_part
    debug_total_parts["前進気勢"] += front_part
    # 走破タイムが速い馬を総合力に加点
    distance_times = horse.get("距離付きタイム", [])

    time_seconds = []
    time_score = 0
    best_time = None
    time_weight = 0

    # 総合力のタイム評価（距離一致を最優先）
    same_distance_exists = any(
        x["距離"] == distance_num
        for x in distance_times
    )

    for item in distance_times:
        race_distance = item["距離"]

        if same_distance_exists:
            distance_ok = (race_distance == distance_num)
        else:
            if distance_num == 1400:
                distance_ok = (
                    abs(race_distance - distance_num) <= 200
                    and race_distance >= 1200
                )
            elif distance_num in [1200, 1230, 1300]:
                distance_ok = (
                    abs(race_distance - distance_num) <= 200
                    and race_distance >= 1000
                )
            elif distance_num >= 1900:
                distance_ok = race_distance in [
                    1600, 1700, 1800, 1870, 1900, 2000, 2100
                ]
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
            if baba_name == "園田" and past_place == "姫路":
                total_seconds += 5.0
            elif baba_name == "姫路" and past_place == "園田":
                total_seconds -= 5.0

            time_seconds.append(total_seconds)
        except:
            pass

    if time_seconds:
        best_time = min(time_seconds)

        distance_match_count = sum(
            1 for h in horses
            if any(x["距離"] == distance_num for x in h.get("距離付きタイム", []))
        )

        if distance_match_count >= len(horses) * 0.5:
            time_weight = 3.0
        elif distance_match_count >= 3:
            time_weight = 3.3
        elif distance_match_count >= 1:
            time_weight = 1.8
        else:
            time_weight = 0

        if same_distance_exists:
            distance_match_bonus = 1.0
        else:
            distance_match_bonus = 0.9

        time_score = max(0, 200 - best_time) * time_weight * distance_match_bonus

        if fastest_same_distance_time is not None and best_time is not None:
            diff = best_time - fastest_same_distance_time
            if diff >= 3.0:
                total_score -= 300
                debug_total_parts["減点"] -= 300
            elif diff >= 2.0:
                total_score -= 220
                debug_total_parts["減点"] -= 220
            elif diff >= 1.5:
                total_score -= 140
                debug_total_parts["減点"] -= 140
            elif diff >= 1.0:
                total_score -= 80
                debug_total_parts["減点"] -= 80

        total_score += time_score
        debug_total_parts["持ちタイム"] += time_score
    # 過去5走の着順スコア
    # 距離は関係なく、実際に着に残れている馬を評価する
    if not jra_transfer:

        finish_part = 0

        for finish in finishes[-5:]:

            if finish == 1:
                finish_part += 80

            elif finish == 2:
                finish_part += 60

            elif finish == 3:
                finish_part += 45

            elif finish <= 5:
                finish_part += 20

            elif finish >= 10:
                finish_part -= 60

            elif finish >= 8:
                finish_part -= 35

        total_score += finish_part
        debug_total_parts["着順"] += finish_part

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
        long_part = long_score_map.get(horse_no, 0) * 0.12
        total_score += long_part
        debug_total_parts["地力"] += long_part
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

            # 4角からゴールまでの順位落下を総合力にも反映
            if finish is not None:
                drop = finish - last
                drop_penalty = 0

                if drop >= 5:
                    drop_penalty = 180

                elif drop >= 4:
                    drop_penalty = 120

                elif drop >= 3:
                    drop_penalty = 70

                elif drop >= 2:
                    drop_penalty = 25

                total_score -= drop_penalty
                debug_total_parts["減点"] -= drop_penalty
    total_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "総合スコア": total_score,
        "持ちタイムスコア": time_score,
        "ベストタイム": best_time,
        "タイム係数": time_weight,
        "内訳": debug_total_parts
    })

total_candidates = sorted(
    total_candidates,
    key=lambda x: x["総合スコア"],
    reverse=True
)

total_best = total_candidates[0]
total_best_horse = f"{total_best['馬番']}番 {total_best['馬名']}"

if debug_mode:
    st.subheader("総合力ランキング")

    for h in total_candidates:
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜総合 {round(h['総合スコア'], 1)} "
            f"｜前進 {round(h['内訳']['前進気勢'], 1)} "
            f"｜タイム {round(h['内訳']['持ちタイム'], 1)} "
            f"｜地力 {round(h['内訳']['地力'], 1)} "
            f"｜着順 {round(h['内訳']['着順'], 1)} "
            f"｜平均 {round(h['内訳']['平均着順'], 1)} "
            f"｜減点 {round(h['内訳']['減点'], 1)}"
        )
# 展開が向く馬と先行気勢の馬が同じなら、
# 先行気勢の馬をスコア2位以降にずらす
# 期待値高めおすすめ馬
# 穴馬は前進気勢固定をやめる
# 上位4頭と被らない残り馬から、展開・総合寄りで拾う

used_for_ana = [
    popular_horse_num,      # 軸馬とは被らない
    total_best["馬番"],     # 総合力1位とは被らない
    tenkai_best["馬番"],    # 展開馬とは被らない
    long_best["馬番"],      # 地力馬とは被らない
    front_best["馬番"],     # 先行気勢とは被らない
]

ana_candidates = []

# 総合最下位2頭を取得
total_bottom_two = {
    h["馬番"]
    for h in total_candidates[-2:]
}

# 地力最下位2頭を取得
long_bottom_two = {
    h["馬番"]
    for h in long_spurt_candidates[-2:]
}

# 総合・地力の両方で最下位2頭に入る馬だけ足切り
ana_cut_horse_numbers = total_bottom_two & long_bottom_two

ana_base_candidates = []

for h in tenkai_candidates:
    if h["馬番"] in used_for_ana:
        continue

    # 総合・地力ともに最下位2頭なら穴候補から除外
    if h["馬番"] in ana_cut_horse_numbers:
        continue

    ana_base_candidates.append({
        "馬番": h["馬番"],
        "馬名": h["馬名"],
        "スコア": h["スコア"]
    })

for h in total_candidates:
    if h["馬番"] in used_for_ana:
        continue

    # 総合・地力ともに最下位2頭なら穴候補から除外
    if h["馬番"] in ana_cut_horse_numbers:
        continue

    if any(a["馬番"] == h["馬番"] for a in ana_base_candidates):
        continue

    ana_base_candidates.append({
        "馬番": h["馬番"],
        "馬名": h["馬名"],
        "スコア": h["総合スコア"] * 0.5
    })

for h in ana_base_candidates:

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

            # 1600m以上は差し・押し上げ型を少し評価
            if distance_num >= 1600:

                front_positions = [
                    target_flow[0]
                    for target_flow in flows
                    if len(target_flow) >= 2
                ]

                last_positions = [
                    target_flow[-1]
                    for target_flow in flows
                    if len(target_flow) >= 2
                ]

                if front_positions and last_positions:
                    avg_front = sum(front_positions) / len(front_positions)
                    avg_last = sum(last_positions) / len(last_positions)

                    if avg_front >= 7 and avg_last <= 5:
                        ana_score += 50

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

        if h["馬番"] in ana_cut_horse_numbers:
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

        if h["馬番"] in ana_cut_horse_numbers:
            continue

        if any(a["馬番"] == h["馬番"] for a in ana_candidates):
            continue

        if any(a["馬番"] == h["馬番"] for a in extra_ana_pool):
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
        if len(ana_candidates) >= 5:
            break

        ana_candidates.append(h)
if debug_mode:
    st.subheader("押さえ候補スコア")
    for h in ana_candidates:
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜押さえスコア {round(h['スコア'], 1)}"
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
# 穴馬候補4位
if len(ana_candidates) >= 4:
    ana_fourth = ana_candidates[3]
else:
    ana_fourth = ana_candidates[-1]

ana_fourth_horse = f"{ana_fourth['馬番']}番 {ana_fourth['馬名']}"

# 穴馬候補5位
if len(ana_candidates) >= 5:
    ana_fifth = ana_candidates[4]
else:
    ana_fifth = ana_candidates[-1]

ana_fifth_horse = f"{ana_fifth['馬番']}番 {ana_fifth['馬名']}"

def show_card(icon, title, subtitle, horse_text, bg_color, border_color, title_color):
    st.markdown(
        f"""
        <div style="
            background-color:{bg_color};
            border:1.5px solid {border_color};
            padding:10px 14px;
            border-radius:8px;
            margin-bottom:6px;
            color:#222222;
        ">
            <div style="
                font-size:18px;
                font-weight:700;
                color:{title_color};
                margin-bottom:6px;
            ">
                {icon} {title}
                <span style="
                    font-size:12px;
                    font-weight:500;
                ">（{subtitle}）</span>
            </div>
            <div style="
                font-size:18px;
                font-weight:700;
                color:#111827;
            ">
                {horse_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


show_card(
    "🎯",
    "軸馬",
    f"脚色タイプ：{kyakushoku_type}",
    popular_horse_label,
    "#fff1f2",
    "#f5b5c0",
    "#e11d48"
)


show_card(
    "🌊",
    "展開の向く馬",
    "相手候補",
    tenkai_horse,
    "#e0f2fe",
    "#7dd3fc",
    "#0369a1"
)

show_card(
    "🌋",
    "地力のある馬",
    "持続して脚を使えるタイプ",
    long_spurt_horse,
    "#fff9e8",
    "#f3d58b",
    "#d97706"
)

show_card(
    "☄️",
    "先行力のある馬",
    "前に行けるタイプ",
    front_horse,
    "#f0fdf4",
    "#bbf7d0",
    "#16a34a"
)

show_card(
    "⭐",
    "抑え馬",
    "拾っておきたいタイプ",
    ana_horse,
    "#fff7ed",
    "#fed7aa",
    "#f97316"
)

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

popular = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"

# 三連複2点
st.subheader("おすすめの三連複 2点")

trio_bets = []
# 三連複用：先行馬が軸馬と被ったら地力馬を使う
front_horse_for_trio = front_horse

if get_num(front_horse_for_trio) == popular_horse_num:
    front_horse_for_trio = long_spurt_horse
popular = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"
total_horse = total_best_horse
long_horse = long_spurt_horse
tenkai_horse_text = tenkai_horse

# 三連複は「軸馬から1点」「総合から1点」で独立して作る

def make_unique_trio(first, second, third, fallback_list):
    trio = [first, second, third]
    nums = [get_num(h) for h in trio]

    if len(nums) == len(set(nums)):
        return trio

    used_nums = set()
    fixed = []

    for h in trio:
        n = get_num(h)

        if n not in used_nums:
            fixed.append(h)
            used_nums.add(n)
        else:
            replacement = None

            for fb in fallback_list:
                fb_num = get_num(fb)

                if fb_num not in used_nums:
                    replacement = fb
                    break

            if replacement:
                fixed.append(replacement)
                used_nums.add(get_num(replacement))

    if len(fixed) == 3:
        return fixed

    return None


# 1点目：軸馬から

# 総合と展開が被った時は押さえ1位を使う
if total_best["馬番"] == tenkai_best["馬番"]:
    axis_third = ana_horse

# 通常
else:

    # 三連複1点目：軸馬から

    # 差し軸なら 軸－展開－穴4
    if kyakushoku_type == "差し":
        axis_third = ana_fourth_horse

    # 逃げ軸なら 軸－展開－穴2
    elif kyakushoku_type == "逃げ":
        axis_third = ana_second_horse

    # 持続・展開待ちは 軸－持続(地力)－先行
    elif kyakushoku_type in ["持続", "展開待ち"]:
        axis_third = front_horse_for_trio

    # 総合と地力が同じ馬なら 軸－展開－地力
    elif total_best["馬番"] == long_best["馬番"]:
        axis_third = long_horse

    # 先行馬と軸が被った時は地力馬
    elif front_best["馬番"] == popular_horse_num:
        axis_third = long_horse

    # 通常は 軸－展開－先行
    else:
        axis_third = front_horse_for_trio

axis_fallbacks = [
    ana_horse,
    ana_second_horse,
    ana_third_horse,
    long_horse,
    total_horse,
]

# 持続・先行・展開待ちは個別処理

if kyakushoku_type == "持続":
    axis_trio = make_unique_trio(
        popular,
        tenkai_horse_text,
        long_horse,
        [
            front_horse_for_trio,
            ana_horse,
            ana_second_horse,
            ana_third_horse,
            total_horse,
        ]
    )

elif kyakushoku_type == "先行":
    axis_trio = make_unique_trio(
        popular,
        tenkai_horse_text,
        front_horse_for_trio,
        [
            long_horse,
            ana_horse,
            ana_second_horse,
            ana_third_horse,
            total_horse,
        ]
    )

elif kyakushoku_type == "展開待ち":
    axis_trio = make_unique_trio(
        popular,
        front_horse_for_trio,
        ana_horse,
        axis_fallbacks
    )

else:
    axis_trio = make_unique_trio(
        popular,
        tenkai_horse_text,
        axis_third,
        axis_fallbacks
    )

if axis_trio:
    trio_bets = add_unique_bet(
        trio_bets,
        axis_trio,
        max_count=2
    )
# 2点目
if kyakushoku_type == "先行":
    second_trio = make_unique_trio(
        popular,
        front_horse_for_trio,
        ana_fourth_horse,
        [
            ana_horse,
            ana_second_horse,
            ana_third_horse,
            long_horse,
            tenkai_horse_text,
        ]
    )

elif kyakushoku_type == "差し":
    second_trio = make_unique_trio(
        popular,
        long_horse,
        ana_third_horse,
        [
            ana_horse,
            ana_second_horse,
            front_horse_for_trio,
            tenkai_horse_text,
        ]
    )

else:
    second_trio = make_unique_trio(
        popular,
        long_horse,
        ana_horse,
        [
            ana_second_horse,
            ana_third_horse,
            front_horse_for_trio,
            tenkai_horse_text,
        ]
    )

if second_trio:
    trio_bets = add_unique_bet(
        trio_bets,
        second_trio,
        max_count=2
    )

# 念のため2点未満なら保険候補で補充
backup_patterns = [
    [total_horse, long_horse, ana_horse],
    [total_horse, long_horse, ana_second_horse],
    [total_horse, ana_horse, ana_third_horse],
    [popular, ana_horse, ana_second_horse],
]

for pattern in backup_patterns:
    if len(trio_bets) >= 2:
        break

    trio_bets = add_unique_bet(
        trio_bets,
        pattern,
        max_count=2
    )


for bet in trio_bets:
    st.write(f"{bet[0]} - {bet[1]} - {bet[2]}")
# ワイド 本線2点＋カッパの浮き輪保険1点
st.subheader("おすすめのワイド２点")

wide_bets = []

popular = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"
tenkai_horse_text = f"{tenkai_best['馬番']}番 {tenkai_best['馬名']}"

if get_num(tenkai_horse_text) == popular_horse_num:
    for h in tenkai_candidates:
        candidate = f"{h['馬番']}番 {h['馬名']}"
        if get_num(candidate) != popular_horse_num:
            tenkai_horse_text = candidate
            break

# 本線2点
# 総合力1位と地力馬が同じなら、
# その馬は3着以内期待が高いのでワイド1点目に優先する
# ワイド1点目を明確に決める
wide_patterns = []

# 1点目：軸－展開
first_target = tenkai_horse_text

# 軸＝展開なら軸－地力
if get_num(popular) == get_num(first_target):
    first_target = long_horse

# 軸＝地力なら抑え1
if get_num(popular) == get_num(first_target):
    first_target = ana_horse

# それでも被るなら抑え2
if get_num(popular) == get_num(first_target):
    first_target = ana_second_horse

wide_patterns.append([popular, first_target])

# 2点目候補
wide_patterns += [

    # 2点目は軸－抑え1を最優先
    [popular, ana_horse],

    # 被った時は穴3
    [popular, ana_third_horse],

    # さらに被った時は穴2
    [popular, ana_second_horse],

    [total_horse, ana_third_horse],
    [tenkai_horse_text, ana_third_horse],
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
# 三連複2点が A-B-C / A-B-D の形なら、
# C－地力を浮き輪保険の最優先にする
# 浮き輪は「本線・対抗が沈んだ時の別世界線」にするため、
# ここでは先に決めない

# 軸・総合・展開が被った時は
# 人気馬シナリオを捨てて、
# 穴2－穴3の別世界線を買う

if not float_bets:

    from collections import Counter

    # 本線（三連複＋ワイド）の使用回数を集計
    use_count = Counter()

    for bet in trio_bets:
        for horse in bet:
            use_count[horse] += 1

    for bet in wide_bets:
        for horse in bet:
            use_count[horse] += 1

    max_count = max(use_count.values()) if use_count else 0
    banned = {
        horse
        for horse, cnt in use_count.items()
        if cnt == max_count
    }

    wide_existing_keys = [
        tuple(sorted(get_num(h) for h in bet))
        for bet in wide_bets
    ]

    # 浮き輪は必ず抑え馬を1頭入れる
    float_patterns = [
        [ana_horse, ana_third_horse],
        [ana_horse, ana_second_horse],
        [ana_horse, long_horse],
        [ana_horse, total_horse],
        [ana_horse, tenkai_horse_text],
    ]

    # まずは本線の中心馬を避ける
    for pattern in float_patterns:
        pattern_key = tuple(sorted(get_num(h) for h in pattern))

        if any(horse in banned for horse in pattern):
            continue

        if pattern_key in wide_existing_keys:
            continue

        float_bets = add_unique_bet(float_bets, pattern, max_count=1)

        if len(float_bets) >= 1:
            break

    # それでも出ない時は、bannedを少し緩めて必ず出す
    if not float_bets:
        for pattern in float_patterns:
            pattern_key = tuple(sorted(get_num(h) for h in pattern))

            if pattern_key in wide_existing_keys:
                continue

            float_bets = add_unique_bet(float_bets, pattern, max_count=1)

            if len(float_bets) >= 1:
                break

for bet in float_bets:
    st.write(f"{bet[0]} - {bet[1]}")

st.caption(
    "※買い目の一例です。最終判断はオッズや馬場を見て調整してください。"
)