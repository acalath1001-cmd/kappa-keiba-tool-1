import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
def calc_front_score(horse_no, corner_positions):
    score = 0

    if not corner_positions:
        # 4角位置が取れない場合は内枠だけで仮評価
        if horse_no <= 4:
            score += 2
        return score

    has_front_run = any(pos <= 3 for pos in corner_positions)
    avg_corner = sum(corner_positions) / len(corner_positions)

    if has_front_run:
        score += 5
    else:
        score -= 5

    if avg_corner <= 3:
        score += 3
    elif avg_corner <= 5:
        score += 1
    else:
        score -= 2

    if horse_no <= 4:
        score += 2

    return score
st.set_page_config(
    page_title="地方競馬予想ツール",
    page_icon="🐎",
    layout="centered"
)

st.title("🐎 地方競馬AI")

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
    horses.append({
        "馬番": i,
        "馬名": horse,
        "4角位置": []
    })
for i, horse in enumerate(real_horses, start=1):
        st.write(f"{i}番 {horse}")
        print("展開込み5頭")

import random

yosou = random.sample(numbered_horses, 5)

yosou = random.sample(numbered_horses, 5)

import random

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
yosou = random.sample(others, 4)

front_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    corner_positions = horse["4角位置"]

    front_score = calc_front_score(horse_no, corner_positions)

    front_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "前残りスコア": front_score
    })

front_candidates = sorted(
    front_candidates,
    key=lambda x: x["前残りスコア"],
    reverse=True
)

# 前にいけて逃げれる馬
front_horse = f"{front_candidates[0]['馬番']}番 {front_candidates[0]['馬名']}"

# 他の候補
long_spurt_horse = others[1]
tenkai_horse = others[2]
ana_horse = others[3]

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
    （オッズは変わるので適宜1番人気は変更してください）
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
    ○ 前進気勢強めの馬 {front_horse}
    </div>
    """,
    unsafe_allow_html=True
)
st.caption("先行して粘り込み期待")

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
    ▲ 長く脚を使える馬 {long_spurt_horse}
    </div>
    """,
    unsafe_allow_html=True
)
st.caption("後半まで脚を使えるタイプ")

st.write(f"△ 展開が向く馬\n{tenkai_horse}")
st.caption("流れひとつで浮上")

st.write(f"☆ 穴で残りそうな馬\n{ana_horse}")
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

wide_axis = front_horse

wide_candidates = [
    tenkai_horse,
    long_spurt_horse,
    ana_horse
]

wide_partners = []

for h in wide_candidates:
    if h != wide_axis and h not in wide_partners:
        wide_partners.append(h)

wide_partners = wide_partners[:2]

for h in wide_partners:
    st.write(f"{wide_axis} - {h}")