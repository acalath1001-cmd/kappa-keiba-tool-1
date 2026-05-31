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
        second = flow[1]
        last = flow[-1]

        # 1-1経験を最重要視
        if first == 1 and second == 1:
            score += 80

            if len(flow) >= 4:
                third = flow[2]

                # 完全逃げ切り型
                if third == 1 and last == 1:
                    score += 80

                # 逃げて2着以内に粘る
                elif third == 1 and last <= 2:
                    score += 50

                # 逃げて3着以内に粘る
                elif last <= 3:
                    score += 30

        # 2番手以内で運べる馬も少しだけ評価
        elif first <= 2 and second <= 2:
            score += 20

        # 逃げて大きく垂れる馬は減点
        if first == 1 and last >= 6:
            score -= 40

    return score
def get_corner_positions(horse_url):
    try:
        r = requests.get(horse_url, timeout=10)
        s = BeautifulSoup(r.text, "html.parser")
        text = s.get_text(" ", strip=True)

        positions = re.findall(
            r"(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})",
            text
        )
        return [int(p[3]) for p in positions[-5:]]

    except:
        return []
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

    for row in rows:
        row_text = row.get_text(" ", strip=True)
        if horse in row_text:
            horse_text = row_text
            break

    flow_matches = re.findall(
        r"\b\d{1,2}(?:\s*-\s*\d{1,2}){1,3}\b",
        horse_text
    )

    race_flows = []

    for m in flow_matches[-5:]:
        nums = [int(x) for x in re.findall(r"\d{1,2}", m)]
        race_flows.append(nums)

    corner_positions = [flow[-1] for flow in race_flows]

    horses.append({
        "馬番": i,
        "馬名": horse,
        "4角位置": corner_positions,
        "通過順": race_flows,
        "望月騎手": "望月" in row_text,
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

    if horse_no == front_best["馬番"]:
        continue

    score = 0

    
        # 名古屋の望月騎手補正
    if "k_babaCode=24" in url and horse.get("望月騎手"):
        score += 2

    for idx, flow in enumerate(race_flows):

        if len(flow) < 4:
            continue

        # 0入りは欠損データ扱い
        if 0 in flow:
            continue

        first = flow[0]
        second = flow[1]
        third = flow[2]
        last = flow[3]

        # 直近レースを重視
        recent_bonus = idx + 1

                # 逃げ馬は除外
        if first == 1:
            continue

        # 後ろすぎる馬も除外
        if first >= 5:
            continue

        # 2〜4番手で運べる馬を高評価
        if 2 <= first <= 4 and 2 <= last <= 5:
            score += 30 * recent_bonus

        # 位置を維持している
        if abs(last - first) <= 1:
            score += 15 * recent_bonus

        # 少し押し上げる
        if last < first and last <= 5:
            score += 10 * recent_bonus

        # 大きく崩れる馬は減点
        if last - first >= 3:
            score -= 35
        # 崩れる馬は減点
        if last - first >= 3:
            score -= 20
        # 3角までは前にいるのに、4角で急に失速する馬は減点
        if third <= 4 and last - third >= 3:
            score -= 35
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
if debug_mode:
    st.subheader("長く脚を使える馬スコア")

    for h in long_spurt_candidates:
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜スコア {h['スコア']} "
            f"｜通過順 {h['通過順']}"
        )
if not long_spurt_candidates:
    st.error("長く脚の評価データが取れていません")
    st.stop()

long_best = long_spurt_candidates[0]
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

if strong_avg_first <= 4 and strong_avg_last <= 5:
    kyakushoku_type = "前で踏み続けるタイプ"
elif strong_avg_first >= 7:
    kyakushoku_type = "差してくるタイプ"
else:
    kyakushoku_type = "中団から長く脚を使うタイプ"

tenkai_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    race_flows = horse["通過順"]

    if horse_no == strong_horse:
        continue

    firsts = [flow[0] for flow in race_flows if len(flow) >= 4]
    lasts = [flow[-1] for flow in race_flows if len(flow) >= 4]

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
# 期待値高めおすすめ穴馬
# 上記4頭（人気馬・前で長く脚・展開・先行気勢）以外から選ぶ

used_numbers = [
    strong_horse,
    long_best["馬番"],
    tenkai_best["馬番"],
    front_best["馬番"]
]

ana_best = None

# 基本は前進気勢スコア順。ただし上記4頭は除外
for h in front_candidates:
    if h["馬番"] not in used_numbers:
        ana_best = h
        break

# もし前進気勢候補に残りがなければ、全馬から除外して探す
if ana_best is None:
    for h in horses:
        if h["馬番"] not in used_numbers:
            ana_best = h
            break

# それでもいなければ最後だけ例外
if ana_best is None:
    ana_best = front_candidates[0]

ana_horse = f"{ana_best['馬番']}番 {ana_best['馬名']}"

st.subheader("人気馬の脚色タイプ")
st.write(f"{strong_horse}番 {real_horses[strong_horse - 1]}")
st.write(kyakushoku_type)
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

st.caption("総合力上位候補")

st.markdown(
    f"""
    <div style="
        background-color:#e8f1fb;
        padding:15px;
        border-radius:10px;
        color:#222222;
        font-size:16px;
        font-weight:400;
    ">
   ○ 前で長く脚を使える馬 {long_spurt_horse}
    </div>
    """,
    unsafe_allow_html=True
)
st.caption("前で踏み続けるタイプ")

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

if long_spurt_horse.split("番")[0] == str(strong_horse):
    main_horses = [strong_horse_name, tenkai_horse]
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

wide_axis = long_spurt_horse

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