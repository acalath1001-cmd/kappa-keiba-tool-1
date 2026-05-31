import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin
def calc_front_score(horse_no, race_flows):
    score = 0

    for flow in race_flows:
        if len(flow) < 2:
            continue

        first = flow[0]
        last = flow[-1]

        # 前に行ける
        if first <= 4:
            score += 10

        # 4角でも前にいる
        if last <= 4:
            score += 15
        elif last <= 6:
            score += 7

        # 順位を保つ・上げる
        if last <= first:
            score += 12

        # ズルズル下がる馬は減点
        if last - first >= 3:
            score -= 15

    return score
st.set_page_config(
    page_title="地方競馬予想ツール",
    page_icon="🐎",
    layout="centered"
)

st.title("🐎 地方競馬AI")
debug_mode = st.checkbox("デバッグ表示")

url = st.text_input("出馬表URLを入力してください")

if not url:
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
distance = st.text_input("距離を入力してください（例 1400）:")

if not distance:
    st.stop()
course_name = ""

print(f"{distance}m戦")
# 距離カテゴリ
distance_num = int(distance)

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
print("◎ 本命候補")
print("○ 対抗候補")
print("▲ 穴候補")
print(url)
response = requests.get(url)
soup = BeautifulSoup(response.text, "html.parser")

print("ページ取得成功")

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
pattern = r"(?:^|\s)(?:[1-8]\s+)?([1-9][0-9]?)\s+([ァ-ヴー]{3,})\s+"

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

    # 馬名を含む row から下の15 row をまとめて取得
    for idx, row in enumerate(rows):
        row_text = row.get_text(" ", strip=True)

        if re.search(rf"(?:^|\s){i}\s+{horse}(?:\s|$)", row_text):
            for j in range(idx, min(idx + 15, len(rows))):
                nearby_text = rows[j].get_text(" ", strip=True)
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
    # 通過順の直前にある走破タイムを拾う
    race_times = []

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
    race_flows = flow_matches_raw[-5:]

    corner_positions = [flow[-1] for flow in race_flows]

    horses.append({
        "馬番": i,
        "馬名": horse,
        "4角位置": corner_positions,
        "通過順": race_flows,
        "走破タイム": race_times,
        "望月騎手": "望月" in horse_text,
        "取得テキスト": horse_text,
        })
for i, horse in enumerate(real_horses, start=1):
        st.write(f"{i}番 {horse}")
        print("展開込み5頭")

# ランダム予想を廃止
# ここからはスコア順で選出する

top_popular = numbered_horses

strong_horse = st.number_input(
    "◎ 人気馬番号",
    min_value=1,
    max_value=len(real_horses),
    value=1,
    step=1
)
strong_horse_text = f"{strong_horse}番 {real_horses[strong_horse - 1]}"

others = [
    horse for horse in numbered_horses
    if horse != strong_horse_text
]
# ランダム選出を廃止
yosou = others

# 4角位置が取れていない馬も含めてスコア確認できるようにする
front_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    corner_positions = horse["4角位置"]

    front_score = calc_front_score(horse_no, horse["通過順"])
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
        "4角位置": corner_positions
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
            f"｜4角 {h['4角位置']}"
        )
if not front_candidates:
    st.error("前進気勢の評価データが取れていません")
    st.stop()

front_best = front_candidates[0]
front_horse = f"{front_best['馬番']}番 {front_best['馬名']}"

long_spurt_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    race_flows = horse["通過順"]
    horse_text = horse.get("取得テキスト", "")

    score = 0
    front_keep_count = 0
    tare_count = 0

    if distance_num >= 1900:
        short_distance_count = len(re.findall(r"(?:右|左)?(?:800|900|1000|1200|1300|1400)", horse_text))
        long_distance_count = len(re.findall(r"(?:右|左)?(?:1600|1700|1800|1900|2000)", horse_text))

        if long_distance_count == 0:
            score -= 700
        elif short_distance_count > long_distance_count:
            score -= 500

    if "k_babaCode=24" in url and horse.get("望月騎手"):
        score += 2

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
        if first <= 6 and last <= 7 and max(flow) <= 7:
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
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜スコア {h['スコア']} "
            f"｜通過順 {h['通過順']}"
        )
        st.subheader("着順取得チェック")

    for horse in horses:
        horse_text = horse.get("取得テキスト", "")

        finish_matches = re.findall(
            r"\d{2}\.\d{2}\.\d{2}.*?\d+頭.*?(\d{1,2})番",
            horse_text
        )

        st.write(
            f"{horse['馬番']}番 {horse['馬名']} "
            f"｜着順候補 {finish_matches[-5:]}"
        )

        if horse["馬番"] in [1, 6]:
            st.text_area(
                f"{horse['馬番']}番 {horse['馬名']} の取得テキスト",
                horse_text[:3000],
                height=250
            )
if not long_spurt_candidates:
    st.error("長く脚の評価データが取れていません")
    st.stop()

long_best = long_spurt_display_candidates[0]
long_spurt_horse = f"{long_best['馬番']}番 {long_best['馬名']}"

# 展開が向く馬：人気馬の脚色と合う馬を選ぶ

strong_data = None

for horse in horses:
    if horse["馬番"] == strong_horse:
        strong_data = horse
        break

strong_flows = strong_data["通過順"] if strong_data else []

# 人気馬の脚色タイプを判定し、脚色が合う馬を選ぶ

def avg_nonzero(values):
    values = [v for v in values if v > 0]
    if not values:
        return 99
    return sum(values) / len(values)

strong_firsts = [flow[0] for flow in strong_flows if len(flow) >= 4]
strong_lasts = [flow[-1] for flow in strong_flows if len(flow) >= 4]

strong_avg_first = avg_nonzero(strong_firsts)
strong_avg_last = avg_nonzero(strong_lasts)

# 逃げ・先行性能がかなり高い
if strong_avg_first <= 2 and strong_avg_last <= 4:
    kyakushoku_type = "先行気勢強めのタイプ"

# 前で踏み続けるタイプ
elif strong_avg_first <= 4 and strong_avg_last <= 5:
    kyakushoku_type = "前に行って押し切るタイプ"
elif strong_avg_first >= 7:
    kyakushoku_type = "差してくるタイプ"
else:
    kyakushoku_type = "先行気勢強めのタイプ"
type_comment = {
    "前に行って押し切るタイプ": "",
    "差してくるタイプ": "後方から脚を使って伸びてくる人気馬です",
    "先行気勢強めのタイプ": "先頭で押し切る人気馬です",
}
 
# 人気馬が差してくるタイプなのに先行気勢1位にも出る場合は、
# 先行気勢の馬を次点候補にずらす
if kyakushoku_type == "差してくるタイプ" and front_best["馬番"] == strong_horse:
    for h in front_candidates:
        if h["馬番"] != strong_horse:
            front_best = h
            front_horse = f"{front_best['馬番']}番 {front_best['馬名']}"
            break
tenkai_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    race_flows = horse["通過順"]

    if horse_no == strong_horse:
        continue

    firsts = [flow[0] for flow in race_flows if len(flow) >= 2]
    lasts = [flow[-1] for flow in race_flows if len(flow) >= 2]

    avg_first = avg_nonzero(firsts)
    avg_last = avg_nonzero(lasts)

    score = 0

    # 人気馬が前タイプ → 似た脚色で一緒に前で踏める馬
    if kyakushoku_type == "前で踏み続けるタイプ":
        score -= abs(avg_first - strong_avg_first) * 3
        score -= abs(avg_last - strong_avg_last) * 3
        if avg_first <= 6 and avg_last <= 6:
            score += 30

    # 人気馬が差しタイプ → 前で残れる馬を相手にする
    elif kyakushoku_type == "差してくるタイプ":
        if avg_first <= 5:
            score += 30
        if avg_last <= 6:
            score += 20

    # 人気馬が中団タイプ → 位置取りが近い馬
    else:
        score -= abs(avg_first - strong_avg_first) * 3
        score -= abs(avg_last - strong_avg_last) * 3
        if 3 <= avg_first <= 8 and 3 <= avg_last <= 8:
            score += 25

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

    total_score = (
    front_score_map.get(horse_no, 0)
    + long_score_map.get(horse_no, 0)
    )

    total_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "総合スコア": total_score
    })

total_candidates = sorted(
    total_candidates,
    key=lambda x: x["総合スコア"],
    reverse=True
)

total_best = total_candidates[0]
total_best_horse = f"{total_best['馬番']}番 {total_best['馬名']}"
# 展開が向く馬と先行気勢の馬が同じなら、
# 先行気勢の馬をスコア2位以降にずらす
# 期待値高めおすすめ穴馬
# 上記4頭（人気馬・前で長く脚・展開・先行気勢）以外から選ぶ

used_numbers = [
    strong_horse,
    long_best["馬番"],
    tenkai_best["馬番"],
    front_best["馬番"]
]
# 穴馬候補では、ベストタイム持ちの馬は除外しない

ana_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    horse_text = horse.get("取得テキスト", "")
    race_times = horse.get("走破タイム", [])
    # ベストタイムを持っている馬は除外しない
    # それ以外の重複馬だけ除外

    ana_score = 0
    time_score = 0
    # 距離一致の持ちタイムを自動抽出して評価
    # 例：1200mなら、horse_text内の1200付近にある 1:12.3 などを拾う
    target_distance = distance

    # 距離一致の持ちタイムを広めに拾う
    best_time = None

    for t in race_times:
        minute, sec = t.split(":")
        time_value = int(minute) * 60 + float(sec)
        # 距離ごとの異常タイム除外
        if distance_num == 1000:
            if time_value < 58 or time_value > 66:
                continue

        elif distance_num == 1200:
            if time_value < 65 or time_value > 90:
                continue

        elif distance_num == 1400:
            if time_value < 80 or time_value > 110:
                continue
        if best_time is None or time_value < best_time:
            best_time = time_value

    # 穴馬は「直近5走の最高持ちタイム」に尖らせる
    if best_time is not None:
        time_score = int(10000 - best_time * 100)
    else:
        time_score = 0

    ana_score += time_score
    
    # 穴馬は、すでに主要候補に出ている馬を除外
    if horse_no in used_numbers:
        continue
    ana_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "ベストタイム": best_time,
        "スコア": ana_score
    })

ana_candidates = sorted(
    ana_candidates,
    key=lambda x: x["スコア"],
    reverse=True
)
if debug_mode:
    st.subheader("穴馬候補スコア")
    for h in ana_candidates:
        horse_text = ""
        for horse in horses:
            if horse["馬番"] == h["馬番"]:
                horse_text = horse.get("取得テキスト", "")
                race_times = horse.get("走破タイム", [])
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜穴スコア {h['スコア']} "
            f"｜ベストタイム {h.get('ベストタイム')} "
            f"｜距離一致 {distance in horse_text}"
        )
if ana_candidates:
    ana_best = ana_candidates[0]
else:
    ana_best = front_candidates[0]

ana_horse = f"{ana_best['馬番']}番 {ana_best['馬名']}"

st.subheader("人気馬の脚色タイプ")

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
    <b>{strong_horse}番 {real_horses[strong_horse - 1]}</b><br>
    人気馬：<b>{kyakushoku_type}</b><br>
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
    ◎ 人気の馬 {strong_horse}番 {real_horses[strong_horse - 1]}
    （オッズは変わるので1番人気は適宜変更してください）
    </div>
    """,
    unsafe_allow_html=True
)

# 三連複 軸2頭固定
main_horses = [f"{strong_horse}番 {real_horses[strong_horse - 1]}", long_spurt_horse]

sub_candidates = [front_horse, tenkai_horse, ana_horse]

sub_horses = []
for h in sub_candidates:
    if h not in main_horses and h not in sub_horses:
        sub_horses.append(h)

sub_horses = sub_horses[:2]
st.write(f"◉ 総合力1位 {total_best_horse}")
st.caption("総合力上位候補")


st.info(f"○ 前に行って押し切る馬 {long_spurt_horse}")
st.caption("前に行って力を出せるタイプ")

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
st.caption("人気馬の脚色と合うタイプ")
st.write(f"△ 先行気勢の強い馬\n{front_horse}")
st.caption("積極的に前に行ける")

st.write(f"☆ 期待値高めおすすめ穴馬\n{ana_horse}")
st.caption("人気以上に展開が向けば面白い")
st.subheader("三連複 軸2頭固定買い目")

strong_horse_name = f"{strong_horse}番 {real_horses[strong_horse - 1]}"

# 三連複は 人気馬 + 総合力1位 を軸にする
if total_best["馬番"] != strong_horse:
    main_horses = [strong_horse_name, total_best_horse]
else:
    main_horses = [strong_horse_name, long_spurt_horse]

sub_candidates = [
    front_horse,
    tenkai_horse,
    ana_horse
]

sub_horses = []

for h in sub_candidates:
    h_num = int(h.split("番")[0])
    if h_num != strong_horse and h not in main_horses and h not in sub_horses:
        sub_horses.append(h)

sub_horses = sub_horses[:2]

for h in sub_horses:
    st.write(f"{main_horses[0]} - {main_horses[1]} - {h}")

s= front_horse

# 資金を減らさないワイド2点
st.subheader("資金を減らさないワイド2点")

wide_axis = front_horse

wide_candidates = [
    tenkai_horse,
    long_spurt_horse,
    ana_horse
]
strong_horse_name = ""

for horse in horses:
    if horse["馬番"] == strong_horse:
        strong_horse_name = horse["馬名"]

strong_horse_text = f"{strong_horse}番 {strong_horse_name}"
wide_partners = []

# 展開が向く馬を追加
if tenkai_horse != wide_axis:
    wide_partners.append(tenkai_horse)

# 強い馬を追加
if strong_horse_text != wide_axis and strong_horse_text not in wide_partners:
    wide_partners.append(strong_horse_text)
for h in wide_partners:
    st.write(f"{wide_axis} - {h}")