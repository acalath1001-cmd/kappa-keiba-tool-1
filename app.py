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

    for time_text, flow_text in time_flow_pairs:

        try:
            minutes, seconds = time_text.split(":")
            total_sec = int(minutes) * 60 + float(seconds)

            # 短すぎる区間タイムを除外
            if distance_num >= 1400:
                if total_sec < 70:
                    continue

            elif distance_num >= 1200:
                if total_sec < 60:
                    continue

            elif distance_num >= 1000:
                if total_sec < 50:
                    continue

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
    corner_positions = [flow[-1] for flow in race_flows]
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

    # 中団〜後方からしっかり押し上げる馬だけ差し候補
    # 軽く押し上げるだけの馬は展開待ちに回す
    if first >= 5 and last <= 5 and last < first:
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
elif strong_avg_first <= 4 and strong_avg_last <= 5:
    kyakushoku_type = "先行"

# ③差し
elif push_rate >= 0.4:
    kyakushoku_type = "差し"

# ④持続
elif (
    strong_stable_count >= 2
    or (
        3 <= strong_avg_first <= 6
        and 3 <= strong_avg_last <= 6
        and abs(strong_avg_last - strong_avg_first) <= 2
    )
):
    kyakushoku_type = "持続"

# ⑤展開待ち
else:
    kyakushoku_type = "展開待ち"
 
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
    # 展開馬の一次試験：今回距離で戦えるタイムがあるか
    tenkai_best_time = None
    distance_times = horse.get("距離付きタイム", [])

    same_distance_exists = any(
        x["距離"] == distance_num
        for x in distance_times
    )

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

        last = flow[-1]
        finish = finishes[idx] if idx < len(finishes) else None

        if finish is None:
            continue

        # 4角5番手以内から6着以下
        if last <= 5 and finish >= 6:
            score -= tare_penalty_1

        # 4角4番手以内から8着以下
        if last <= 4 and finish >= 8:
            score -= tare_penalty_2

        # 4角3番手以内から10着以下
        if last <= 3 and finish >= 10:
            score -= tare_penalty_3
     # 軸馬タイプを大きく2系統で見る
    # 逃げ・先行・展開待ち
    # → 先行できて垂れない馬を相手にする
# 逃げ → 先行馬
    if kyakushoku_type == "逃げ":

        score += front_score_map.get(horse_no, 0) * 0.7

        if 2 <= avg_first <= 5:
            score += 80

        if 2 <= avg_last <= 5:
            score += 70

        if abs(avg_last - avg_first) <= 2:
            score += 50

    # 先行 → 先行＋持続
    elif kyakushoku_type == "先行":

        score += front_score_map.get(horse_no, 0) * 0.5

        long_score = long_score_map.get(horse_no, 0)
        if long_score > 0:
            score += long_score * 0.08

        if avg_first <= 5:
            score += 60

        if avg_last <= 6:
            score += 60

    # 持続 → 持続＋先行
    elif kyakushoku_type == "持続":

        long_score = long_score_map.get(horse_no, 0)
        if long_score > 0:
            score += long_score * 0.15

        score += front_score_map.get(horse_no, 0) * 0.25

        if 2 <= avg_first <= 6:
            score += 60

        if abs(avg_last - avg_first) <= 2:
            score += 60

    # 差し → 逃げ馬
    elif kyakushoku_type == "差し":

        score += front_score_map.get(horse_no, 0) * 0.8

        if avg_first <= 3:
            score += 80

        if avg_last <= 5:
            score += 50

    # 展開待ち → 総合力1位寄り
    elif kyakushoku_type == "展開待ち":

        total_rank = pre_total_rank_map.get(horse_no, 99)

        if total_rank == 1:
            score += 120

        elif total_rank == 2:
            score += 80

        elif total_rank == 3:
            score += 40
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

tenkai_best = tenkai_candidates[0]
tenkai_horse = f"{tenkai_best['馬番']}番 {tenkai_best['馬名']}"
# JRA転入馬が多いレースは警告表示
jra_count = 0

for horse in horses:
    horse_text = horse.get("取得テキスト", "")

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

if jra_rate >= 0.7:
    st.warning(
        "⚠️ JRA転入馬が多いレースです。\n\n"
        "地力・展開評価の信頼度が低くなるため、"
        "総合力や持ちタイムも参考にしてください。"
    )
# 総合力1位を裏側で判定
front_score_map = {h["馬番"]: h["スコア"] for h in front_candidates}
long_score_map = {h["馬番"]: h["スコア"] for h in long_spurt_candidates}
tenkai_score_map = {h["馬番"]: h["スコア"] for h in tenkai_candidates}

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
    front_part = front_score_map.get(horse_no, 0) * 0.06
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

        time_score = max(0, 200 - best_time) * time_weight

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

            # 4角前にいたのに着順が悪い
            if last <= 4 and finish is not None and finish >= 7:
                total_score -= 70

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
total_fourth = total_candidates[3]
total_fourth_horse = f"{total_fourth['馬番']}番 {total_fourth['馬名']}"
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

ana_base_candidates = []

for h in tenkai_candidates:
    if h["馬番"] in used_for_ana:
        continue

    ana_base_candidates.append({
        "馬番": h["馬番"],
        "馬名": h["馬名"],
        "スコア": h["スコア"]
    })

for h in total_candidates:
    if h["馬番"] in used_for_ana:
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
            if distance_num >= 1600 and target_horse:

                flows = target_horse.get("通過順", [])

                front_positions = [
                    flow[0] for flow in flows
                    if len(flow) >= 2
                ]

                last_positions = [
                    flow[-1] for flow in flows
                    if len(flow) >= 2
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
    "👑",
    "総合力1位",
    "総合力上位候補",
    total_best_horse,
    "#f5f0ff",
    "#d8c7ff",
    "#7e22ce"
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
    "🌊",
    "展開の向く馬",
    "軸馬と脚色が合うタイプ",
    tenkai_horse,
    "#e0f2fe",
    "#7dd3fc",
    "#0369a1"
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

def candidate_text_list(candidates):
    result = []
    for h in candidates:
        text = f"{h['馬番']}番 {h['馬名']}"
        if text not in result:
            result.append(text)
    return result


popular = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"

# 三連複2点
st.subheader("おすすめの三連複 2点")

trio_bets = []
# 南関判定
is_nankan = any(
    x in baba_name
    for x in ["浦和", "船橋", "大井", "川崎"]
)
# 三連複1点目用：先行馬が軸馬と被ったら先行2位を使う
front_horse_for_trio = front_horse

if get_num(front_horse_for_trio) == popular_horse_num:
    for h in front_candidates:
        candidate = f"{h['馬番']}番 {h['馬名']}"
        if get_num(candidate) != popular_horse_num:
            front_horse_for_trio = candidate
            break
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
elif kyakushoku_type in ["逃げ", "先行", "展開待ち"]:
    axis_third = front_horse_for_trio

# 差し
elif kyakushoku_type == "差し":
    axis_third = ana_horse

# 持続
else:
    axis_third = front_horse_for_trio

axis_fallbacks = [
    ana_horse,
    ana_second_horse,
    ana_third_horse,
    long_horse,
    total_horse,
]

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


# 2点目：総合から
total_fallbacks = [
    ana_horse,
    ana_second_horse,
    ana_third_horse,
    tenkai_horse_text,
    front_horse_for_trio,
]

total_trio = make_unique_trio(
    total_horse,
    long_horse,
    ana_third_horse,
    total_fallbacks
)

if total_trio:
    trio_bets = add_unique_bet(
        trio_bets,
        total_trio,
        max_count=2
    )


# 念のため2点未満なら保険候補で補充
backup_patterns = [
    [popular, tenkai_horse_text, ana_horse],
    [total_horse, tenkai_horse_text, ana_third_horse],
    [popular, tenkai_horse_text, front_horse_for_trio],
    [total_horse, ana_horse, ana_second_horse],
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
tenkai_horse_text = tenkai_horse

# 本線2点
wide_patterns = [
    # 本線1：軸馬 × 展開馬
    [popular, tenkai_horse_text],

    # 本線2：総合力1位 × 地力馬
    [total_horse, long_horse],

    # 被った時の逃げ道
    [popular, ana_horse],
    [popular, ana_second_horse],
    [total_horse, ana_horse],
    [total_horse, ana_second_horse],
    [tenkai_horse_text, ana_horse],
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

# 軸・総合・展開が被った時は
# 人気馬シナリオを捨てて、
# 穴2－穴3の別世界線を買う

main_nums = {
    popular_horse_num,
    total_best["馬番"],
    tenkai_best["馬番"],
}

# 軸が総合 or 展開と被った時は、人気馬依存が強いので穴2－穴3
if (
    popular_horse_num == total_best["馬番"]
    or popular_horse_num == tenkai_best["馬番"]
):

    float_patterns = [
        [ana_second_horse, ana_third_horse],
        [ana_horse, ana_third_horse],
        [long_horse, ana_third_horse],
    ]

# 総合と展開だけが被った時は、総合－穴2
elif total_best["馬番"] == tenkai_best["馬番"]:

    float_patterns = [
        [total_horse, ana_second_horse],
        [total_horse, ana_third_horse],
        [popular, ana_second_horse],
    ]

# 3頭とも別なら通常保険
else:

    float_patterns = [
        [total_horse, ana_third_horse],
        [total_horse, ana_second_horse],
        [popular, ana_third_horse],
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