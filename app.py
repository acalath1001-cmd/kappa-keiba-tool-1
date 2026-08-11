import streamlit as st
import re
from urllib.parse import urlparse, parse_qs
def expand_flow_to_four(flow):
    """
    2地点・3地点の通過順を、評価用の4地点に補完する。

    4地点：そのまま
    3地点：中央の位置を複製
    2地点：前半・後半をそれぞれ複製
    """
    if not flow:
        return []

    flow = flow[:]

    # 通常の4地点データは変更しない
    if len(flow) >= 4:
        return flow[:4]

    # 例：5-3-2 → 5-3-3-2
    if len(flow) == 3:
        first, middle, last = flow
        return [first, middle, middle, last]

    # 例：4-3 → 4-4-3-3
    if len(flow) == 2:
        first, last = flow
        return [first, first, last, last]

    # 念のため1地点しかない場合
    if len(flow) == 1:
        return [flow[0]] * 4

    return []
def calc_front_score(race_flows):
    """
    前進気勢は「前へ行ける力」に特化する。

    着順・踏ん張り・失速はここでは評価しない。
    1角でどれだけ前に付けられたかだけを見る。
    """

    score = 0

    for flow in race_flows:

        if not flow:
            continue

        first = flow[0]

        # 1角位置だけで前進気勢を評価
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

    return score


def get_distance_aware_front_data(
    horse,
    current_distance,
):
    """
    前進気勢を「今回距離で前へ行けるか」に寄せるため、
    今回距離に近い過去走だけを基本評価に使う。

    距離帯は既存の踏ん張り不足判定と揃える。

    ・1000m以下  → 800〜1000m
    ・1200〜1400m → 1200〜1400m
    ・1500m以上  → 今回距離±300m

    例：
    今回1500mなら1200〜1800mが基本対象。
    800mの通過順は基本の前進気勢には混ぜない。

    ただし対象距離の過去走が1走もない馬を
    完全に0点にしないため、最も近い距離の走だけを
    低い倍率でフォールバック評価する。
    """

    valid_items = []

    for item in horse.get(
        "距離付きタイム",
        []
    ):

        past_distance = item.get(
            "距離",
            0
        )

        flow = item.get(
            "通過順",
            []
        )

        if (
            not past_distance
            or len(flow) < 1
        ):
            continue

        valid_items.append(
            {
                "距離": past_distance,
                "通過順": flow,
            }
        )

    if not valid_items:

        return {
            "通過順": [],
            "対象距離": [],
            "倍率": 0.0,
            "モード": "データなし",
            "最短距離差": None,
        }

    def distance_ok(
        past_distance
    ):

        if current_distance <= 1000:

            return (
                800
                <= past_distance
                <= 1000
            )

        elif current_distance <= 1400:

            return (
                1200
                <= past_distance
                <= 1400
            )

        else:

            return (
                abs(
                    past_distance
                    - current_distance
                )
                <= 300
            )

    matched_items = [
        item
        for item in valid_items
        if distance_ok(
            item["距離"]
        )
    ]

    # 今回距離に近い実績がある場合は、
    # その距離帯だけを100％評価。
    if matched_items:

        return {
            "通過順": [
                item["通過順"]
                for item in matched_items
            ],
            "対象距離": [
                item["距離"]
                for item in matched_items
            ],
            "倍率": 1.0,
            "モード": "今回距離帯",
            "最短距離差": min(
                abs(
                    item["距離"]
                    - current_distance
                )
                for item in matched_items
            ),
        }

    # --------------------------------------------------
    # フォールバック
    #
    # 対象距離走がない場合だけ、
    # 最も近い距離の走を弱く評価する。
    #
    # これにより1500m戦で800m実績しかない馬が、
    # 800mの位置取りだけで前進上位になるのを防ぐ。
    # --------------------------------------------------
    nearest_gap = min(
        abs(
            item["距離"]
            - current_distance
        )
        for item in valid_items
    )

    nearest_items = [
        item
        for item in valid_items
        if abs(
            item["距離"]
            - current_distance
        ) == nearest_gap
    ]

    if nearest_gap <= 200:
        fallback_weight = 0.50

    elif nearest_gap <= 400:
        fallback_weight = 0.30

    elif nearest_gap <= 600:
        fallback_weight = 0.20

    else:
        fallback_weight = 0.10

    return {
        "通過順": [
            item["通過順"]
            for item in nearest_items
        ],
        "対象距離": [
            item["距離"]
            for item in nearest_items
        ],
        "倍率": fallback_weight,
        "モード": "近似距離フォールバック",
        "最短距離差": nearest_gap,
    }

def calc_recent_form_bonus(finish_positions):
    """
    直近3走の着順を評価する。
    finish_positionsは最新走から順に並んでいる前提。
    """
    recent_results = (finish_positions or [])[:3]

    point_tables = [
        {1: 30, 2: 24, 3: 18, 4: 12, 5: 8},
        {1: 21, 2: 17, 3: 13, 4: 8, 5: 6},
        {1: 12, 2: 10, 3: 7, 4: 5, 5: 3},
    ]

    bonus = 0

    for idx, finish in enumerate(recent_results):
        bonus += point_tables[idx].get(finish, 0)

    top5_count = sum(
        1
        for finish in recent_results
        if finish <= 5
    )

    # 直近3走すべて5着以内
    if len(recent_results) == 3 and top5_count == 3:
        bonus += 15

    # 直近3走のうち2走が5着以内
    elif top5_count >= 2:
        bonus += 8

    return bonus, recent_results
def calc_distance_change_score(
    horse,
    current_distance,
):
    """
    距離短縮・距離延長の適性を、
    展開評価専用の加点として判定する。

    同じ馬に複数の該当走があっても、
    最も強い1走だけを採用する。

    1900m以上の距離延長は、
    既存の距離延長・押し上げ型ロジックへ任せる。
    """

    best_score = 0
    best_type = "なし"
    best_detail = None

    for item in horse.get(
        "距離付きタイム",
        [],
    ):

        past_distance = item.get(
            "距離",
            0,
        )

        flow = item.get(
            "通過順",
            [],
        )

        finish = item.get(
            "着順"
        )

        if (
            finish is None
            or len(flow) < 2
        ):
            continue

        first = flow[0]
        last = flow[-1]

        shortening = (
            past_distance
            - current_distance
        )

        extension = (
            current_distance
            - past_distance
        )

        race_score = 0
        change_type = "なし"
        reasons = []

        # ------------------------------------------
        # 100〜300mの距離短縮
        # 長い距離でも前で運べた馬、
        # 最後だけ少し甘くなった馬を拾う。
        # ------------------------------------------
        if 100 <= shortening <= 300:

            change_type = "短縮"

            if (
                first <= 4
                and last <= 5
            ):
                race_score += 40
                reasons.append(
                    "長い距離でも前で運べた"
                )

            goal_drop = finish - last

            if (
                first <= 4
                and last <= 5
                and 2 <= goal_drop <= 4
            ):
                race_score += 30
                reasons.append(
                    "最後だけ少し甘くなった"
                )

        # ------------------------------------------
        # 100〜300mの距離延長
        # 1900m未満だけを対象にする。
        # 位置を保って好走した持続型、
        # 押し上げて好走した馬を拾う。
        # ------------------------------------------
        elif (
            current_distance < 1900
            and 100 <= extension <= 300
        ):

            change_type = "延長"

            if (
                2 <= first <= 7
                and abs(last - first) <= 2
                and finish <= 5
            ):
                race_score += 50
                reasons.append(
                    "短い距離で位置を保って好走"
                )

            elif (
                first >= 6
                and last <= first - 3
                and finish <= 5
            ):
                race_score += 30
                reasons.append(
                    "短い距離で押し上げて好走"
                )

            # 踏ん張り不足馬は、
            # 距離延長のプラス評価を弱める。
            if (
                race_score > 0
                and horse.get(
                    "踏ん張り不足",
                    False,
                )
            ):
                race_score = max(
                    0,
                    race_score - 60,
                )
                reasons.append(
                    "踏ん張り不足で延長加点を抑制"
                )

        if (
            race_score > best_score
            or (
                race_score == best_score == 0
                and reasons
                and best_detail is None
            )
        ):
            best_score = race_score
            best_type = change_type
            best_detail = {
                "過去距離": past_distance,
                "今回距離": current_distance,
                "通過順": flow,
                "着順": finish,
                "理由": reasons,
            }

    # 最新走で大失速した馬は、
    # 距離変化だけで信用を戻さない。
    if (
        best_score > 0
        and horse.get(
            "直近大失速強度",
            0,
        ) >= 1.0
    ):
        best_score = 0
        best_type = "大失速で無効"

        if best_detail is not None:
            best_detail["理由"].append(
                "最新走大失速のため加点なし"
            )

    return {
        "スコア": best_score,
        "種類": best_type,
        "詳細": best_detail,
    }


def extract_current_jockey(horse_row):
    """
    NAR出馬表の現在騎手だけを取得する。

    過去走の騎手名は使用せず、
    RiderMarkへのリンクになっている今回騎手だけを見る。
    """

    if horse_row is None:
        return ""

    jockey_link = horse_row.find(
        "a",
        href=re.compile(
            r"DataRoom/RiderMark"
        )
    )

    if jockey_link is None:
        return ""

    jockey_name = jockey_link.get_text(
        " ",
        strip=True
    )

    # 例：
    # 望月洵（愛知） → 望月洵
    # 吉村智（兵庫） → 吉村智
    jockey_name = jockey_name.split("（")[0]

    jockey_name = (
        jockey_name
        .replace(" ", "")
        .replace("　", "")
    )

    return jockey_name


def parse_time_to_seconds(time_text):
    """
    0:47.2 / 1:31.9 のようなNAR表示タイムを秒へ変換する。
    変換できない場合はNone。
    """
    if not time_text:
        return None

    try:
        minutes, seconds = time_text.split(":")
        return int(minutes) * 60 + float(seconds)
    except (ValueError, TypeError, AttributeError):
        return None


def extract_display_best_time(horse_row):
    """
    NAR出馬表の「最高タイム」欄から、
    その馬の表示上の最高タイムを取得する。

    過去走の走破タイムを誤取得しないため、
    ・日付を含むセル
    ・通過順を含むセル
    ・長すぎるセル
    は対象外にする。

    例：
      0:47.2 良0:49.3
    の場合は先頭の 0:47.2 を採用する。
    """

    if horse_row is None:
        return None

    for cell in horse_row.find_all(["td", "th"]):
        cell_text = cell.get_text(
            " ",
            strip=True
        )

        if not cell_text:
            continue

        # 過去走セルは除外
        if re.search(
            r"\d{2}\.\d{2}\.\d{2}",
            cell_text
        ):
            continue

        # 通過順を含む過去走セルは除外
        if re.search(
            r"\d{1,2}-\d{1,2}",
            cell_text
        ):
            continue

        # 「最高タイム」欄は短いセルなので、
        # レース名などを含む長いセルは除外
        if len(cell_text) > 60:
            continue

        time_matches = re.findall(
            r"\b\d+:\d{2}\.\d\b",
            cell_text
        )

        if not time_matches:
            continue

        # 最高タイム欄では最初のタイムが
        # 全馬場を含む最高タイム。
        return time_matches[0]

    return None


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
    st.session_state.analyzed = False
    st.rerun()

st.session_state.race_url = url
if not st.session_state.analyzed:
    st.stop()

if not url:
    st.warning("出馬表URLを入力してください")
    st.stop()

# 初期画面では読み込まず、
# 分析開始ボタンを押した後だけ読み込む
import requests
from bs4 import BeautifulSoup

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
LOCAL_PLACES = [
    "帯広", "盛岡", "水沢", "浦和", "船橋",
    "大井", "川崎", "金沢", "笠松", "名古屋",
    "園田", "姫路", "高知", "佐賀", "門別"
]

JRA_PLACES = [
    "東京", "中山", "京都", "阪神", "中京",
    "新潟", "福島", "小倉", "札幌", "函館"
]

RACE_PLACE_PATTERN = "|".join(
    LOCAL_PLACES + JRA_PLACES
)
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

# 出走馬データ取得状況のデバッグ保存用
horse_parse_debug = []

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
    # 今回騎乗する騎手だけを取得
    current_jockey = extract_current_jockey(
        horse_row
    )

    # NAR出馬表の「最高タイム」欄を取得。
    # 850m以下の最高タイム警戒で使用する。
    display_best_time = extract_display_best_time(
        horse_row
    )

    display_best_time_seconds = (
        parse_time_to_seconds(
            display_best_time
        )
    )

    # 距離・タイム・通過順を取得
    # 笠松など「タイムと距離が別行」の競馬場に対応するため
    # 除外・取消を除いた日付行から距離を取得し、
    # タイムと通過順はhorse_text全体から別途取得してインデックス対応

    distance_time_pairs = []
    race_times = []

    # ① 除外・取消を除いた日付行から距離を順番に取得
    valid_distances = []
    valid_places = []

    date_blocks = re.split(
        r"(?=(?:取消|除外|中止|競走除外|出走取消|出走除外)?\s*\d{2}\.\d{2}\.\d{2})",
        horse_text
    )

    for block in date_blocks:
        if any(word in block for word in ["除外", "取消", "中止", "競走除外", "出走取消"]):
            continue

        d_match = re.search(
            r"(?:右|左|芝|ダ)\s*"
            r"(800|820|850|900|920|1000|1200|1230|1300|1400|1500|1580|1600|1650|1700|1800|1870|1900|2000|2100|2200)",
            block
        )
        if not d_match:
            continue
        place_match = re.search(
            rf"({RACE_PLACE_PATTERN})",
            block
        )
        valid_distances.append(int(d_match.group(1)))
        valid_places.append(place_match.group(1) if place_match else "")

    # ② タイム＋通過順＋上がり3Fを
    # horse_text全体から順番に取得
    #
    # NAR出馬表の過去走は基本的に
    # 「走破タイム → コーナー通過順 → 上がり3F」
    # の順で表示される。
    #
    # 例：
    # 1:25.7 5-4 37.1
    #
    # 上がり3Fが取得できないレースもあるため、
    # 3つ目は任意取得にしておく。
    time_flow_pairs = re.findall(
        r"(\d+:\d{2}\.\d+)"
        r"[\s　]{1,8}"
        r"(\d{1,2}-\d{1,2}(?:-\d{1,2})?(?:-\d{1,2})?)"
        r"(?:[\s　]{1,8}(\d{2}(?:\.\d)?))?",
        horse_text
    )

    valid_time_flows = []

    for idx, (
        time_text,
        flow_text,
        agari_text
    ) in enumerate(time_flow_pairs):

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

        # 上がり3Fを数値化。
        # 地方競馬の通常値から大きく外れるものは
        # 誤取得の可能性が高いのでNoneにする。
        agari_3f = None

        if agari_text:
            try:
                agari_candidate = float(
                    agari_text
                )

                if 30.0 <= agari_candidate <= 50.0:
                    agari_3f = agari_candidate

            except (ValueError, TypeError):
                agari_3f = None

        valid_time_flows.append(
            (
                time_text,
                flow_nums,
                agari_3f,
            )
        )

    # ③ インデックスで対応付け（件数が少ない方に合わせる）
    pair_count = min(len(valid_distances), len(valid_time_flows))

    for idx in range(pair_count):
        (
            time_text,
            flow_nums,
            agari_3f,
        ) = valid_time_flows[idx]

        past_distance = valid_distances[idx]
        past_place = valid_places[idx]

        adjusted_time_text = time_text
        time_adjustment = 0.0

        try:
            minutes, seconds = time_text.split(":")
            adjusted_seconds = int(minutes) * 60 + float(seconds)

            # 盛岡・水沢1400mの競馬場差を補正
            # 水沢の方が約1〜1.5秒速い前提で、中間の1.2秒を採用
            if past_distance == 1400:

                # 今回が盛岡で、過去走が水沢
                # 水沢タイムを1.2秒遅くして盛岡基準に合わせる
                if baba_name == "盛岡" and past_place == "水沢":
                    time_adjustment = 1.2

                # 今回が水沢で、過去走が盛岡
                # 盛岡タイムを1.2秒速くして水沢基準に合わせる
                elif baba_name == "水沢" and past_place == "盛岡":
                    time_adjustment = -1.2
            # ==================================================
            # 浦和 ⇔ 川崎・船橋のタイム差補正
            #
            # 浦和は川崎・船橋より約2秒速い傾向として、
            # 少し丸めて1.8秒補正する。
            #
            # 対象：1400m・1500m
            # ==================================================
            if past_distance in [1400, 1500]:

                # 今回が川崎・船橋で、過去走が浦和
                # 浦和の速い時計を1.8秒遅くして比較
                if (
                    baba_name in ["川崎", "船橋"]
                    and past_place == "浦和"
                ):
                    time_adjustment += 1.8

                # 今回が浦和で、過去走が川崎・船橋
                # 川崎・船橋の時計を1.8秒速くして浦和基準へ
                elif (
                    baba_name == "浦和"
                    and past_place in ["川崎", "船橋"]
                ):
                    time_adjustment -= 1.8
            adjusted_seconds += time_adjustment

            adjusted_minutes = int(adjusted_seconds // 60)
            adjusted_second_part = adjusted_seconds % 60

            adjusted_time_text = (
                f"{adjusted_minutes}:{adjusted_second_part:04.1f}"
            )

        except (ValueError, TypeError):
            pass

        distance_time_pairs.append({
            "距離": past_distance,
            "タイム": adjusted_time_text,
            "元タイム": time_text,
            "競馬場": past_place,
            "タイム補正": time_adjustment,

            # NAR出馬表に表示されている
            # その過去走の上がり3F
            "上がり3F": agari_3f,

            # 画面確認・デバッグ用の本来の通過順
            "元通過順": flow_nums[:],

            # 前進気勢・地力・展開・総合で使う4地点化した通過順
            "通過順": expand_flow_to_four(flow_nums)
        })

        race_times.append(adjusted_time_text)

    # 最後の5走分に絞る
    distance_time_pairs = distance_time_pairs[-5:]
    race_times = race_times[-5:]
    # race_flowsも distance_time_pairs から取り直す
    race_flows = [pair["通過順"] for pair in distance_time_pairs]
    # 表示・確認用の本来の通過順
    original_race_flows = [
        pair.get("元通過順", pair["通過順"])
        for pair in distance_time_pairs
    ]
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
    # ==================================================
    # JRA履歴馬の評価対象を整理
    #
    # JRAで走ったあと地方で1回でも走っていれば、
    # 前進気勢・地力・展開・総合は地方走だけを使う。
    #
    # 地方未出走のJRA転入馬だけ、
    # JRA実績を残して警告対象にする。
    # ==================================================
    for idx, pair in enumerate(distance_time_pairs):
        pair["着順"] = (
            finish_positions[idx]
            if idx < len(finish_positions)
            else None
        )

    # 警告判定用に、絞り込み前の全過去走を保存
    all_distance_time_pairs = [
        dict(pair)
        for pair in distance_time_pairs
    ]

    has_jra_run = any(
        pair.get("競馬場", "") in JRA_PLACES
        for pair in all_distance_time_pairs
    )

    local_pairs = [
        pair
        for pair in all_distance_time_pairs
        if pair.get("競馬場", "") in LOCAL_PLACES
    ]

    has_local_run = bool(local_pairs)

    # JRA履歴があり、地方で1回以上走っていれば、
    # 今後の評価は地方走だけに限定する
    if has_jra_run and has_local_run:
        distance_time_pairs = local_pairs

        race_times = [
            pair["タイム"]
            for pair in distance_time_pairs
        ]

        race_flows = [
            pair["通過順"]
            for pair in distance_time_pairs
        ]

        original_race_flows = [
            pair.get(
                "元通過順",
                pair["通過順"]
            )
            for pair in distance_time_pairs
        ]

        finish_positions = [
            pair["着順"]
            for pair in distance_time_pairs
            if pair.get("着順") is not None
        ]
    # ==================================================
    # 踏ん張り不足判定
    #
    # 今回の距離に近い過去走だけで判定する。
    #
    # 1000m以下 → 800〜1000m
    # 1200〜1400m → 1200〜1400m
    # 1500m以上 → 今回距離±300m
    #
    # 違う距離帯でのスタミナ切れを、
    # 今回の踏ん張り不足として扱わない。
    # ==================================================
    fumbaribuso_count = 0
    fumbaribuso_details = []

    for item in distance_time_pairs:

        past_distance = item.get(
            "距離",
            0
        )

        flow = item.get(
            "通過順",
            []
        )

        finish = item.get(
            "着順"
        )

        if finish is None:
            continue

        if len(flow) < 2:
            continue

        # ------------------------------------------
        # 今回距離に近い過去走だけを対象にする
        # ------------------------------------------

        if distance_num <= 1000:

            distance_ok = (
                800 <= past_distance <= 1000
            )

        elif distance_num <= 1400:

            distance_ok = (
                1200 <= past_distance <= 1400
            )

        else:

            distance_ok = (
                abs(
                    past_distance
                    - distance_num
                ) <= 300
            )

        if not distance_ok:
            continue

        first = flow[0]

        third = (
            flow[2]
            if len(flow) >= 3
            else flow[-1]
        )

        last = flow[-1]

        goal_drop = finish - last
        corner_drop = last - first
        late_corner_drop = last - third

        reasons = []

        # ① 4角では5番手以内だったのに、
        # ゴールまでに3つ以上順位を落とした
        if (
            last <= 5
            and goal_drop >= 3
        ):
            reasons.append(
                "4角→着順で失速"
            )

        # ② 1角では4番手以内だったのに、
        # 4角までに4つ以上順位を落とした
        if (
            first <= 4
            and corner_drop >= 4
        ):
            reasons.append(
                "1角→4角で失速"
            )

        # ③ 3角では4番手以内だったのに、
        # 4角で3つ以上順位を落とした
        if (
            third <= 4
            and late_corner_drop >= 3
        ):
            reasons.append(
                "3角→4角で失速"
            )

        # 同じレースで複数条件に該当しても1回
        if reasons:

            fumbaribuso_count += 1

            fumbaribuso_details.append({
                "距離": past_distance,
                "通過順": flow,
                "着順": finish,
                "理由": reasons,
            })

    is_fumbaribuso = (
        fumbaribuso_count >= 2
    )


    # 後ろの徐々垂れ判定で使うため残す
    check_count = min(
        len(race_flows),
        len(finish_positions)
    )

    # ==================================================
    # 直近大失速判定
    #
    # 距離に関係なく直近2走だけを見る。
    # 4角5番手以内から、
    # ・ゴールまでに6つ以上後退
    # ・または10着以下まで沈んだ
    # 場合は、次走の信用を大きく下げる。
    #
    # 最新走なら100％、2走前なら60％の強度。
    # ==================================================

    heavy_collapse_count = 0
    heavy_collapse_details = []
    heavy_collapse_strength = 0.0

    recent_heavy_check_count = min(
        2,
        len(race_flows),
        len(finish_positions)
    )

    for idx in range(recent_heavy_check_count):
        flow = race_flows[idx]
        finish = finish_positions[idx]

        if len(flow) < 2:
            continue

        last = flow[-1]
        goal_drop = finish - last

        is_heavy_this_race = (
            last <= 5
            and (
                goal_drop >= 6
                or finish >= 10
            )
        )

        if not is_heavy_this_race:
            continue

        heavy_collapse_count += 1

        # 最新走は100％、2走前は60％
        race_strength = (
            1.0
            if idx == 0
            else 0.6
        )

        heavy_collapse_strength = max(
            heavy_collapse_strength,
            race_strength
        )

        heavy_collapse_details.append({
            "何走前": idx + 1,
            "通過順": flow,
            "着順": finish,
            "4角からの後退": goal_drop,
            "強度": race_strength,
        })

    is_heavy_collapse = (
        heavy_collapse_strength > 0
    )
    # ==================================================
    # 徐々垂れ判定
    #
    # 前に付けたあと、
    # 4角までに2つ以上後退し、
    # ゴールでもさらに1つ以上落としたレースを数える
    #
    # 過去5走で2回以上なら徐々垂れ
    # ==================================================

    jojo_tare_count = 0
    jojo_tare_details = []

    for idx in range(check_count):
        flow = race_flows[idx]
        finish = finish_positions[idx]

        if len(flow) < 2:
            continue

        # レース中に最も前へ行った位置
        best_position = min(flow)

        # 4角位置
        last = flow[-1]

        # 最前位置から4角までの後退
        corner_drop = last - best_position

        # 4角から着順までの後退
        goal_drop = finish - last

        # 最前位置から最終着順までの後退
        total_drop = finish - best_position

        if (
            best_position <= 4
            and corner_drop >= 2
            and goal_drop >= 1
            and total_drop >= 3
        ):
            jojo_tare_count += 1

            jojo_tare_details.append({
                "通過順": flow,
                "着順": finish,
                "最前位置": best_position,
                "4角までの後退": corner_drop,
                "4角から着順の後退": goal_drop,
            })

    is_jojo_tare = (
        jojo_tare_count >= 2
    )

    # 出走取消・競走除外判定
    is_scratched = any(
        word in horse_text
        for word in ["出走取消", "競走除外", "出走除外"]
    )
    if debug_mode:

        horse_parse_debug.append({
            "馬番": i,
            "馬名": horse,
            "距離付きタイム数": len(
                distance_time_pairs
            ),
            "通過順数": len(
                race_flows
            ),
            "着順数": len(
                finish_positions
            ),
            "最高タイム": display_best_time,
            "最高タイム秒": display_best_time_seconds,
            "上がり3F": [
                item.get("上がり3F")
                for item in distance_time_pairs
            ],
            "元通過順": original_race_flows,
            "評価通過順": race_flows,
        })
    horses.append({
        "馬番": i,
        "馬名": horse,
        "今回騎手": current_jockey,
        "取消除外": is_scratched,

        # NAR出馬表に表示されている当距離系の最高タイム。
        # 850m以下の「最高タイム警戒」に使う。
        "最高タイム": display_best_time,
        "最高タイム秒": display_best_time_seconds,

        # 評価用の4地点通過順
        "通過順": race_flows,

        # 表示・確認用の本来の通過順
        "元通過順": original_race_flows,

        "走破タイム": race_times,

        # 評価用。JRA履歴馬に地方走があれば地方走だけ
        "距離付きタイム": distance_time_pairs,

        # JRA警告判定用。絞り込み前の全過去走
        "全距離付きタイム": all_distance_time_pairs,

        "着順": finish_positions,
        "JRA履歴あり": has_jra_run,
        "地方走あり": has_local_run,

        # 総合馬・展開馬の最終選出に使う
        "踏ん張り不足": is_fumbaribuso,
        "踏ん張り不足回数": fumbaribuso_count,
        "踏ん張り不足詳細": fumbaribuso_details,

        "直近大失速": is_heavy_collapse,
        "直近大失速回数": heavy_collapse_count,
        "直近大失速強度": heavy_collapse_strength,
        "直近大失速詳細": heavy_collapse_details,

        "徐々垂れ": is_jojo_tare,
        "徐々垂れ回数": jojo_tare_count,
        "徐々垂れ詳細": jojo_tare_details,

        "取得テキスト": horse_text,
    })
# ==================================================
# 出走馬のデータ取得状況
# デバッグ時だけ折りたたみ表示する
# ==================================================

if debug_mode:

    with st.expander(
        "📋 出走馬データ取得状況",
        expanded=False
    ):

        for data in horse_parse_debug:

            st.write(
                f"**{data['馬番']}番 "
                f"{data['馬名']}** "
                f"｜タイム "
                f"{data['距離付きタイム数']} "
                f"｜通過順 "
                f"{data['通過順数']} "
                f"｜着順 "
                f"{data['着順数']}"
            )

            st.caption(
                f"最高タイム："
                f"{data.get('最高タイム') or 'なし'} "
                f"｜上がり3F："
                f"{data.get('上がり3F', [])}\n\n"
                f"元通過順："
                f"{data['元通過順']}\n\n"
                f"評価通過順："
                f"{data['評価通過順']}"
            )
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

# ==================================================
# 🔥 持続上がり評価
#
# 地方競馬では、
# 後方で脚を溜めて上がりだけ速い馬よりも、
#
# ・前半から前に付ける
# ・4角でも前にいる
# ・それでも上がり3Fが速い
#
# 馬を「持続して脚を使える強い馬」として評価する。
#
# 重要：
# 上がり3Fが速いだけでは加点しない。
# 必ず前の位置を維持できた過去走だけが対象。
# ==================================================

def agari_distance_is_comparable(
    past_distance,
    current_distance,
):
    """
    上がり3F比較に使う距離帯。

    距離が離れすぎると上がり時計の意味が変わるため、
    地力評価より少し狭く比較する。
    """

    if current_distance <= 1000:
        return (
            abs(
                past_distance
                - current_distance
            ) <= 100
        )

    if current_distance <= 1400:
        return (
            abs(
                past_distance
                - current_distance
            ) <= 100
        )

    return (
        abs(
            past_distance
            - current_distance
        ) <= 200
    )


# 現在の出走馬が過去に地方で出した、
# 今回距離に近い上がり3Fを比較母集団にする。
#
# 後方馬の上がりも「基準値」には含める。
# その速い基準と同等以上の脚を
# 前で使えた馬だけを後段で加点する。
agari_reference_values = []

for h in horses:

    for item in h.get(
        "距離付きタイム",
        []
    ):

        past_place = item.get(
            "競馬場",
            ""
        )

        # JRAの芝などの速い上がりで
        # 地方ダートの基準を壊さない
        if past_place not in LOCAL_PLACES:
            continue

        past_distance = item.get(
            "距離",
            0
        )

        if not agari_distance_is_comparable(
            past_distance,
            distance_num,
        ):
            continue

        agari = item.get(
            "上がり3F"
        )

        if (
            agari is None
            or not (30.0 <= agari <= 50.0)
        ):
            continue

        agari_reference_values.append(
            float(agari)
        )


agari_reference_values.sort()

agari_top25_cut = None
agari_top40_cut = None

# 最低6走分はないと、
# 1〜2走の偶然値で「速い上がり」を決めない。
if len(agari_reference_values) >= 6:

    top25_index = min(
        len(agari_reference_values) - 1,
        max(
            0,
            int(
                (
                    len(agari_reference_values)
                    - 1
                )
                * 0.25
            )
        )
    )

    top40_index = min(
        len(agari_reference_values) - 1,
        max(
            0,
            int(
                (
                    len(agari_reference_values)
                    - 1
                )
                * 0.40
            )
        )
    )

    agari_top25_cut = (
        agari_reference_values[
            top25_index
        ]
    )

    agari_top40_cut = (
        agari_reference_values[
            top40_index
        ]
    )


for h in horses:

    sustained_agari_score = 0
    sustained_agari_count = 0
    sustained_agari_details = []

    # 最新走ほど少し強く評価する。
    recent_weights = [
        1.00,
        0.85,
        0.70,
        0.55,
        0.40,
    ]

    for idx, item in enumerate(
        h.get(
            "距離付きタイム",
            []
        )[:5]
    ):

        if (
            agari_top25_cut is None
            or agari_top40_cut is None
        ):
            break

        past_place = item.get(
            "競馬場",
            ""
        )

        if past_place not in LOCAL_PLACES:
            continue

        past_distance = item.get(
            "距離",
            0
        )

        if not agari_distance_is_comparable(
            past_distance,
            distance_num,
        ):
            continue

        agari = item.get(
            "上がり3F"
        )

        flow = item.get(
            "通過順",
            []
        )

        finish = item.get(
            "着順"
        )

        if (
            agari is None
            or len(flow) < 2
        ):
            continue

        first = flow[0]
        last = flow[-1]

        # --------------------------------------------------
        # 「前で脚を使った」条件
        #
        # 1角5番手以内
        # ＋4角5番手以内
        # ＋前半から4角まで3つ以上ズルズル下がっていない
        #
        # 後方から上がりだけ速い馬はここで対象外。
        # --------------------------------------------------
        forward_sustain = (
            first <= 5
            and last <= 5
            and (
                last - first
            ) <= 2
        )

        if not forward_sustain:
            continue

        base_score = 0
        level = ""

        # 同距離帯の上がり上位25％
        if agari <= agari_top25_cut:
            base_score = 80
            level = "上位25％"

        # 同距離帯の上がり上位40％
        elif agari <= agari_top40_cut:
            base_score = 50
            level = "上位40％"

        else:
            continue

        # 3番手以内で運びながら速い上がりなら
        # さらに価値を上げる。
        if (
            first <= 3
            and last <= 3
        ):
            base_score += 20

        # 実際に3着以内まで残した場合は
        # 「前で速い上がりが結果につながった」実績として加点。
        if (
            finish is not None
            and finish <= 3
        ):
            base_score += 20

        weight = (
            recent_weights[idx]
            if idx < len(recent_weights)
            else 0.40
        )

        applied_score = round(
            base_score * weight,
            1
        )

        sustained_agari_score += (
            applied_score
        )

        sustained_agari_count += 1

        sustained_agari_details.append({
            "何走前": idx + 1,
            "距離": past_distance,
            "競馬場": past_place,
            "通過順": flow,
            "着順": finish,
            "上がり3F": agari,
            "判定": level,
            "加点": applied_score,
        })


    # 1回だけの一発より、
    # 何度も「前で速い上がり」を使える馬を強く評価。
    repeat_bonus = 0

    if sustained_agari_count >= 3:
        repeat_bonus = 80

    elif sustained_agari_count >= 2:
        repeat_bonus = 50

    sustained_agari_score += (
        repeat_bonus
    )

    # 既存の地力ロジックを壊さないよう上限を設定。
    sustained_agari_score = min(
        sustained_agari_score,
        260
    )

    h[
        "持続上がりスコア"
    ] = round(
        sustained_agari_score,
        1
    )

    h[
        "持続上がり回数"
    ] = sustained_agari_count

    h[
        "持続上がり反復ボーナス"
    ] = repeat_bonus

    h[
        "持続上がり詳細"
    ] = sustained_agari_details


if debug_mode:

    with st.expander(
        "🔥 持続上がり判定",
        expanded=False
    ):

        st.write(
            f"上がり比較対象："
            f"{len(agari_reference_values)}走"
        )

        if (
            agari_top25_cut is None
            or agari_top40_cut is None
        ):

            st.write(
                "比較対象が6走未満のため、"
                "持続上がり加点は行いません。"
            )

        else:

            st.write(
                f"上位25％ライン："
                f"{agari_top25_cut:.1f}秒 "
                f"｜上位40％ライン："
                f"{agari_top40_cut:.1f}秒"
            )

            shown = False

            for h in sorted(
                horses,
                key=lambda x: x.get(
                    "持続上がりスコア",
                    0
                ),
                reverse=True
            ):

                if h.get(
                    "持続上がりスコア",
                    0
                ) <= 0:
                    continue

                shown = True

                st.write(
                    f"🔥 {h['馬番']}番 "
                    f"{h['馬名']} "
                    f"｜持続上がり "
                    f"{h.get('持続上がりスコア', 0)}点 "
                    f"｜該当 "
                    f"{h.get('持続上がり回数', 0)}回"
                )

                st.caption(
                    f"{h.get('持続上がり詳細', [])}"
                )

            if not shown:
                st.write(
                    "持続上がり該当馬なし"
                )


# ==================================================
# 850m以下・最高タイム警戒
#
# 目的：
# 800〜850mでは、長い距離の着順よりも
# 「実際に短距離で出した最高速度」を見逃さない。
#
# 条件：
# ① 今回850m以下
# ② NAR出馬表の最高タイムを取得できている
# ③ メンバー最速の最高タイムから0.5秒以内
# ④ 過去走で一度でも前半4番手以内の経験がある
#
# この判定では総合点そのものは加点しない。
# 主要5役に出ていない場合だけ、
# 抑え候補で優先的に救済する。
# ==================================================

ultra_short_best_time_watch_numbers = set()
ultra_short_best_time_info = {}
ultra_short_fastest_best_time = None

if distance_num <= 850:

    ultra_short_best_time_records = []

    for h in horses:

        best_time_sec = h.get(
            "最高タイム秒"
        )

        if best_time_sec is None:
            continue

        # 800〜850mの最高タイムとして
        # 明らかに不自然な値は除外する。
        if not (40.0 <= best_time_sec <= 70.0):
            continue

        front_experience = any(
            len(flow) >= 1
            and flow[0] <= 4
            for flow in h.get(
                "通過順",
                []
            )
        )

        ultra_short_best_time_records.append({
            "馬番": h["馬番"],
            "馬名": h["馬名"],
            "最高タイム": h.get(
                "最高タイム"
            ),
            "最高タイム秒": best_time_sec,
            "前4番手以内経験": front_experience,
        })

    if ultra_short_best_time_records:

        ultra_short_fastest_best_time = min(
            record["最高タイム秒"]
            for record
            in ultra_short_best_time_records
        )

        for record in ultra_short_best_time_records:

            time_diff = (
                record["最高タイム秒"]
                - ultra_short_fastest_best_time
            )

            is_watch = (
                time_diff <= 0.5
                and record[
                    "前4番手以内経験"
                ]
            )

            if not is_watch:
                continue

            horse_no = record["馬番"]

            ultra_short_best_time_watch_numbers.add(
                horse_no
            )

            ultra_short_best_time_info[
                horse_no
            ] = {
                **record,
                "最速差": round(
                    time_diff,
                    2
                ),
            }

if debug_mode and distance_num <= 850:

    with st.expander(
        "⚡ 850m以下・最高タイム警戒",
        expanded=False
    ):

        if ultra_short_fastest_best_time is None:

            st.write(
                "最高タイムを比較できる馬がいません。"
            )

        else:

            st.write(
                f"メンバー最速最高タイム："
                f"{round(ultra_short_fastest_best_time, 1)}秒"
            )

            if ultra_short_best_time_watch_numbers:

                for horse_no in sorted(
                    ultra_short_best_time_watch_numbers
                ):

                    info = (
                        ultra_short_best_time_info[
                            horse_no
                        ]
                    )

                    st.write(
                        f"⚡ {horse_no}番 "
                        f"{info['馬名']} "
                        f"｜最高 "
                        f"{info['最高タイム']} "
                        f"｜最速差 "
                        f"{info['最速差']}秒 "
                        f"｜前4番手以内経験あり"
                    )

            else:

                st.write(
                    "最高タイム警戒馬なし"
                )

# ==================================================
# 南関から他地区への転入初戦を判定
#
# 今回が南関以外で、過去走に南関実績があり、
# 南関以外の地方実績がまだない馬を対象にする。
#
# 大井・船橋・川崎・浦和での失速を、
# 移籍先でも同じ重さの能力不足として扱わない。
# ==================================================

NANKAN_TRACKS = {
    "浦和",
    "船橋",
    "大井",
    "川崎",
}

NON_NANKAN_LOCAL_TRACKS = (
    set(LOCAL_PLACES)
    - NANKAN_TRACKS
)

# 通常の失速・着順マイナスを40％へ弱める
NANKAN_TRANSFER_PENALTY_WEIGHT = 0.4

# 地力の通常失速減点は最大100点まで
NANKAN_TRANSFER_RISK_CAP = 100

nankan_transfer_first_horse_numbers = set()

for h in horses:

    past_places = [
        item.get("競馬場", "")
        for item in h.get(
            "全距離付きタイム",
            []
        )
    ]

    has_nankan_history = any(
        place in NANKAN_TRACKS
        for place in past_places
    )

    has_non_nankan_local_history = any(
        place in NON_NANKAN_LOCAL_TRACKS
        for place in past_places
    )

    is_nankan_transfer_first = (
        baba_name not in NANKAN_TRACKS
        and has_nankan_history
        and not has_non_nankan_local_history
    )

    h["南関転入初戦"] = (
        is_nankan_transfer_first
    )

    if is_nankan_transfer_first:
        nankan_transfer_first_horse_numbers.add(
            h["馬番"]
        )
# ==================================================
# JRA転入馬の3段階判定
#
# 地方0走      ＝ JRA転入直後
# 地方1〜2走   ＝ 地方慣らし中
# 地方3走以上 ＝ 通常の地方馬として評価
#
# jra_horse_numbers は従来どおり
# 「地方0走」の警告・初転入救済専用として残す。
# ==================================================

JRA_TRACKS = set(JRA_PLACES)
LOCAL_TRACKS = set(LOCAL_PLACES)

# JRA履歴馬ごとの地方出走数
jra_local_result_count_map = {}

# JRA履歴が確認できる全馬
jra_all_horse_numbers = set()

# 地方0走のJRA転入馬だけ、従来の警告表示に使う
jra_horse_info_map = {}

for h in horses:

    if not h.get("JRA履歴あり", False):
        continue

    all_race_items = h.get(
        "全距離付きタイム",
        []
    )

    local_result_count = sum(
        1
        for item in all_race_items
        if item.get(
            "競馬場",
            ""
        ) in LOCAL_TRACKS
    )

    horse_no = h["馬番"]

    jra_all_horse_numbers.add(
        horse_no
    )

    jra_local_result_count_map[
        horse_no
    ] = local_result_count

    # 各馬データにも保存してデバッグしやすくする
    h["JRA地方走数"] = local_result_count

    # 従来のJRA警告は地方0走だけ
    if local_result_count != 0:
        continue

    past_places = {
        item.get("競馬場", "")
        for item in all_race_items
    }

    jra_horse_info_map[
        horse_no
    ] = {
        "馬名": h["馬名"],
        "地方走数": local_result_count,
        "JRA競馬場": sorted(
            past_places & JRA_TRACKS
        ),
    }

# 地方0走：JRA転入直後
jra_horse_numbers = {
    horse_no
    for horse_no, local_count
    in jra_local_result_count_map.items()
    if local_count == 0
}

# 地方1〜2走：地方慣らし中
jra_acclimating_horse_numbers = {
    horse_no
    for horse_no, local_count
    in jra_local_result_count_map.items()
    if 1 <= local_count <= 2
}

# 前進気勢・総合評価でJRA転入扱いを残す範囲
jra_transfer_watch_numbers = (
    jra_horse_numbers
    | jra_acclimating_horse_numbers
)

# 従来の警告件数は地方0走だけ
jra_count = len(
    jra_horse_numbers
)

# 展開の足切り判断では、
# 地方慣らし中もJRA転入の影響馬として数える
jra_rate = (
    len(jra_transfer_watch_numbers)
    / len(horses)
    if horses
    else 0
)

if debug_mode:

    with st.expander(
        "🏇 JRA転入段階",
        expanded=False
    ):

        for h in horses:

            horse_no = h["馬番"]

            if horse_no not in jra_all_horse_numbers:
                continue

            local_count = (
                jra_local_result_count_map.get(
                    horse_no,
                    0
                )
            )

            if local_count == 0:
                stage = "転入直後"

            elif local_count <= 2:
                stage = "地方慣らし中"

            else:
                stage = "通常評価"

            st.write(
                f"{horse_no}番 {h['馬名']} "
                f"｜地方{local_count}走 "
                f"｜{stage}"
            )
# 踏ん張り不足の馬
fumbaribuso_horse_numbers = {
    h["馬番"]
    for h in horses
    if (
        h.get("踏ん張り不足", False)
        and h["馬番"]
        not in nankan_transfer_first_horse_numbers
    )
}

# 徐々垂れの馬
jojo_tare_horse_numbers = {
    h["馬番"]
    for h in horses
    if (
        h.get("徐々垂れ", False)
        and h["馬番"]
        not in nankan_transfer_first_horse_numbers
    )
}

if debug_mode:

    with st.expander(
        "⚠️ 踏ん張り・徐々垂れ判定",
        expanded=False
    ):

        if fumbaribuso_horse_numbers:

            st.markdown("#### 踏ん張り不足")

            for h in horses:

                if not h.get(
                    "踏ん張り不足",
                    False
                ):
                    continue

                st.write(
                    f"{h['馬番']}番 {h['馬名']} "
                    f"｜該当 "
                    f"{h.get('踏ん張り不足回数', 0)}回"
                )

                st.caption(
                    f"{h.get('踏ん張り不足詳細', [])}"
                )

        else:
            st.write("踏ん張り不足馬なし")

        if jojo_tare_horse_numbers:

            st.markdown("#### 徐々垂れ")

            for h in horses:

                if not h.get(
                    "徐々垂れ",
                    False
                ):
                    continue

                st.write(
                    f"{h['馬番']}番 {h['馬名']} "
                    f"｜該当 "
                    f"{h.get('徐々垂れ回数', 0)}回"
                )

                st.caption(
                    f"{h.get('徐々垂れ詳細', [])}"
                )

        else:
            st.write("徐々垂れ馬なし")

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

st.info(
    "※オッズは変動するため、現在の1番人気や\n"
    "自分が来ると思う馬を選択してください。\n\n"
    "※選択した馬を軸に展開分析と\n"
    "買い目を表示します。"
)

popular_horse_num = st.number_input(
    "軸馬の馬番",
    min_value=1,
    max_value=len(real_horses),
    value=1,
    step=1
)

# 出走取消・競走除外馬は軸にできない
active_horse_numbers = {
    h["馬番"]
    for h in horses
}

if popular_horse_num not in active_horse_numbers:
    st.error(
        f"⚠️ {popular_horse_num}番は出走取消・競走除外のため、"
        "軸馬には選択できません。"
    )
    st.stop()

popular_horse_data = next(
    h for h in horses
    if h["馬番"] == popular_horse_num
)

popular_horse_label = (
    f"{popular_horse_num}番 "
    f"{popular_horse_data['馬名']}"
)

# 4角位置が取れていない馬も含めてスコア確認できるようにする
front_candidates = []

for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]

    # ==================================================
    # 距離対応・前進気勢
    #
    # これまでは全距離の通過順を同じ重みで
    # calc_front_score() に入れていたため、
    # 1500m戦でも800mの位置取りが強く効いていた。
    #
    # 今回からは「今回距離帯」を最優先し、
    # 対象距離実績がない馬だけ近似距離を弱く使う。
    # ==================================================

    distance_front_data = (
        get_distance_aware_front_data(
            horse,
            distance_num,
        )
    )

    distance_front_raw_score = (
        calc_front_score(
            distance_front_data[
                "通過順"
            ]
        )
    )

    front_score = round(
        distance_front_raw_score
        * distance_front_data[
            "倍率"
        ],
        1,
    )

    # ==================================================
    # 距離短縮時の前進気勢加点
    #
    # 通常（1400m以下）：
    #   100〜300m短縮だけを対象。
    #
    # 850m以下：
    #   スタミナより初速・前へ行ける力を重視するため、
    #   100〜600m短縮まで対象を拡大する。
    #
    # 例：
    #   1400m → 800mで2番手経験なら +60
    #
    # 加点幅そのものは従来どおり。
    # ==================================================
    if distance_num <= 1400:

        max_shortening_for_front = (
            600
            if distance_num <= 850
            else 300
        )

        for item in horse.get("距離付きタイム", []):
            past_distance = item["距離"]
            flow = item["通過順"]

            shortening = (
                past_distance
                - distance_num
            )

            if (
                100
                <= shortening
                <= max_shortening_for_front
                and len(flow) >= 2
            ):
                if flow[0] == 1:
                    front_score += 120

                elif flow[0] == 2:
                    front_score += 60
    # JRA転入馬は、前に行けた実績を少し評価する
    horse_text = horse.get("取得テキスト", "")

    jra_transfer = (
        horse_no
        in jra_transfer_watch_numbers
    )
    if jra_transfer:
        for flow in horse["通過順"]:
            if len(flow) >= 2:
                first = flow[0]

                if first <= 4:
                    front_score += 35
                elif first <= 6:
                    front_score += 15
    # ==================================================
    # 前進気勢では「前へ行ける能力」だけを見る
    #
    # 直近大失速は、
    # ・地力
    # ・総合
    # ・抑え
    # 側で信用度として評価する。
    #
    # 先行Dでは失速を減点しない。
    # そのため確認用の値だけ保持し、front_scoreからは引かない。
    # ==================================================
    heavy_collapse_front_penalty = 0
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
        # 先行Dでは大失速を減点しないため常に0。
        # 地力・総合・抑え側の大失速評価は従来どおり残る。
        "大失速減点": heavy_collapse_front_penalty,
        "スコア": front_score,

        # 全過去走の1角位置は確認用に残す
        "1角位置": [
            flow[0]
            for flow in horse["通過順"]
            if len(flow) >= 1
        ],

        # 実際に前進気勢の基本点へ使った距離情報
        "前進距離対象": (
            distance_front_data[
                "対象距離"
            ]
        ),
        "前進距離対象1角": [
            flow[0]
            for flow
            in distance_front_data[
                "通過順"
            ]
            if len(flow) >= 1
        ],
        "前進距離倍率": (
            distance_front_data[
                "倍率"
            ]
        ),
        "前進距離モード": (
            distance_front_data[
                "モード"
            ]
        ),
        "前進最短距離差": (
            distance_front_data[
                "最短距離差"
            ]
        ),
        "前進距離基本点": (
            distance_front_raw_score
        ),
    })
front_candidates = sorted(
    front_candidates,
    key=lambda x: x["スコア"],
    reverse=True
)
# ==================================================
# 南関・逃げ先行軸専用の前進気勢ランキング
#
# 通常の前進気勢そのものが
# 「今回距離で前へ行ける能力」だけを見る仕様になったため、
# 南関でも大失速による追加補正は行わない。
#
# 後段の候補調整から独立して参照できるよう、
# 現在の前進ランキングを別保存しておく。
# ==================================================

nankan_front_candidates = [
    dict(h)
    for h in front_candidates
]

# 通常の前進気勢ランキング
front_candidates = [
    h for h in front_candidates
    if h["スコア"] > 0
]

# ==================================================
# 展開馬選出用・前進気勢TOP5
#
# この直後の画面表示と同じ順位を保存する。
# 後段で「先行代表」用のリスク除外が入っても、
# 展開馬はこのTOP5を基準にする。
# ==================================================
front_top5_for_tenkai = [
    dict(h)
    for h in front_candidates[:5]
]
if debug_mode:

    with st.expander(
        "☄️ 前進気勢ランキング",
        expanded=False
    ):

        for rank, h in enumerate(
            front_candidates[:5],
            start=1
        ):

            st.write(
                f"{rank}位｜"
                f"{h['馬番']}番 {h['馬名']} "
                f"｜{round(h['スコア'], 1)}点 "
                f"｜距離対象 "
                f"{h.get('前進距離対象', [])} "
                f"｜対象1角 "
                f"{h.get('前進距離対象1角', [])} "
                f"｜倍率 "
                f"{h.get('前進距離倍率', 1.0)} "
                f"｜{h.get('前進距離モード', '')}"
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
    horse_text = horse.get("取得テキスト", "")

    is_nankan_transfer_first = (
        horse_no
        in nankan_transfer_first_horse_numbers
    )

    # ==================================================
    # 地力評価に使う過去走
    #
    # 通過順と着順を別々に取得せず、
    # 同じ過去走データからセットで使用する
    # ==================================================

    evaluation_pairs = []

    for item in horse.get("距離付きタイム", []):
        race_distance = item["距離"]

        if distance_num == 1400:
            distance_ok = (
                abs(race_distance - distance_num) <= 200
                and race_distance >= 1200
            )

        elif distance_num >= 1500:
            distance_ok = (
                abs(race_distance - distance_num) <= 300
            )

        else:
            distance_ok = (
                abs(race_distance - distance_num) <= 100
            )

        if distance_ok:
            evaluation_pairs.append(item)

    # 対象距離がない場合だけ、
    # 取得済みの過去走全体へ戻す
    if not evaluation_pairs:
        evaluation_pairs = horse.get(
            "距離付きタイム",
            []
        )

    evaluation_pairs = evaluation_pairs[-5:]

    race_flows = [
        item.get("通過順", [])
        for item in evaluation_pairs
    ]

    race_finishes = [
        item.get("着順")
        for item in evaluation_pairs
    ]

    score = 0

    # 前〜中団で位置を維持した回数
    front_keep_count = 0

    # 前で運んで3着以内に入った実績
    front_success_count = 0

    # 失速は能力点と分離して管理する
    risk_penalty = 0
    risk_details = []

    # 過去5走すべてから、前に行った経験を数える
    # 距離フィルター前の通過順を使う
    all_recent_flows = horse.get("通過順", [])[-5:]

    front_experience_count = sum(
        1
        for flow in all_recent_flows
        if len(flow) >= 2 and flow[0] <= 4
    )

    # 2〜4番手維持型を評価
    first_positions = [
        flow[0]
        for flow in race_flows
        if len(flow) >= 2
    ]
    last_positions = [
        flow[-1]
        for flow in race_flows
        if len(flow) >= 2
    ]

    # 平均の前半位置・4角位置を計算
    avg_first = (
        sum(first_positions) / len(first_positions)
        if first_positions
        else 99
    )

    avg_last = (
        sum(last_positions) / len(last_positions)
        if last_positions
        else 99
    )

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

        third = (
            flow[2]
            if len(flow) > 2
            else flow[-1]
        )

        last = flow[-1]

        finish = (
            race_finishes[idx]
            if idx < len(race_finishes)
            else None
        )

        # 能力加点は従来どおり、
        # 新しいレースほど強く評価する
        recent_bonus = (
            [5, 4, 3, 2, 1][idx]
            if idx < 5
            else 1
        )

        # ==================================================
        # 能力評価
        # ==================================================

        # 前〜中団で流れに乗り、大きく崩れない
        if (
            2 <= first <= 6
            and last <= 7
            and max(flow) <= 7
        ):
            score += 45 * recent_bonus
            front_keep_count += 1

        # 前で位置を維持している
        if (
            first <= 5
            and last <= 5
            and max(flow) <= 6
            and abs(last - first) <= 2
        ):
            score += 35 * recent_bonus
            front_keep_count += 1

        # 実際に前で運んで3着以内に入った経験
        if (
            finish is not None
            and first <= 4
            and last <= 4
            and finish <= 3
        ):
            front_success_count += 1

        # 少し押し上げた実績
        if last < first and last <= 6:
            score += 20 * recent_bonus

        # 後方のままのレースは地力評価を下げる
        if first >= 8 and last >= 8:
            score -= 40 * recent_bonus

        # ==================================================
        # 不安・失速評価
        #
        # 同じレースで複数条件に該当しても、
        # 最も大きい減点を1回だけ採用する
        # ==================================================

        race_risk = 0
        race_risk_reasons = []

        # レース中に大きく後退
        if last - first >= 3:

            position_drop_penalty = (
                80
                if idx == 0
                else 50
            )

            race_risk = max(
                race_risk,
                position_drop_penalty
            )

            race_risk_reasons.append(
                "道中で後退"
            )

        # 3角から4角で急に後退
        if (
            third <= 4
            and last - third >= 3
        ):

            late_corner_penalty = (
                100
                if idx == 0
                else 60
            )

            race_risk = max(
                race_risk,
                late_corner_penalty
            )

            race_risk_reasons.append(
                "3角から4角で失速"
            )

        if finish is not None:

            goal_drop = finish - last

            # 最新走の失速は強めに見るが、
            # 5倍にはしない
            if idx == 0:

                if (
                    last <= 4
                    and finish >= 8
                ):
                    goal_penalty = 180

                elif goal_drop >= 5:
                    goal_penalty = 160

                elif goal_drop >= 3:
                    goal_penalty = 100

                elif goal_drop >= 2:
                    goal_penalty = 50

                else:
                    goal_penalty = 0

            # 古い失速は少し弱める
            else:

                if (
                    last <= 4
                    and finish >= 8
                ):
                    goal_penalty = 100

                elif goal_drop >= 5:
                    goal_penalty = 90

                elif goal_drop >= 3:
                    goal_penalty = 60

                elif goal_drop >= 2:
                    goal_penalty = 30

                else:
                    goal_penalty = 0

            if goal_penalty > 0:

                race_risk = max(
                    race_risk,
                    goal_penalty
                )

                race_risk_reasons.append(
                    "4角から着順で失速"
                )

        # このレースの失速減点は1回だけ
        if race_risk > 0:

            risk_penalty += race_risk

            risk_details.append({
                "通過順": flow,
                "着順": finish,
                "減点": race_risk,
                "理由": race_risk_reasons,
            })
    # ==================================================
    # 能力点と不安点を最後に合成する
    # ==================================================

    # 前で安定して運べた回数
    score += front_keep_count * 60

    # 前で実際に結果を出した能力
    score += front_success_count * 120

    # ==================================================
    # 持続上がり加点
    #
    # 「後ろから速い上がり」ではなく、
    # 前半から前に付けて4角でも前を維持し、
    # そのうえで速い上がりを使えた実績だけを
    # 地力へ加える。
    # ==================================================
    sustained_agari_bonus = horse.get(
        "持続上がりスコア",
        0
    )

    score += sustained_agari_bonus

    # 複数の失速があっても、
    # 地力全体を破壊しないよう通常は最大260点
    raw_applied_risk_penalty = min(
        risk_penalty,
        260
    )

    # 南関から他地区への転入初戦は、
    # 格上の南関での通常失速を40％へ弱め、
    # 最大100点までに抑える。
    #
    # 直近大失速はこの下の別枠減点として残す。
    if is_nankan_transfer_first:

        applied_risk_penalty = min(
            round(
                raw_applied_risk_penalty
                * NANKAN_TRANSFER_PENALTY_WEIGHT,
                1
            ),
            NANKAN_TRANSFER_RISK_CAP
        )

    else:
        applied_risk_penalty = (
            raw_applied_risk_penalty
        )

    score -= applied_risk_penalty
    # 直近大失速は通常の失速減点とは別枠。
    # 能力そのものではなく、次走の信用を強く下げる。
    heavy_collapse_long_penalty = round(
        300
        * horse.get(
            "直近大失速強度",
            0
        ),
        1
    )

    score -= heavy_collapse_long_penalty
    
    # 過去5走で一度も前に行っていない馬を強く減点
    front_experience_penalty = 0

    if front_experience_count == 0:
        front_experience_penalty = 400
        score -= front_experience_penalty

    # 地力評価にも前進気勢を少し反映
    score += front_score_map.get(horse_no, 0) * 0.25
    # 今回騎手が望月騎手の場合だけ地力補正
    current_jockey = horse.get(
        "今回騎手",
        ""
    )

    if current_jockey.startswith(
        "望月"
    ):
        score += 80
    # ==================================================
    # 善戦止まり・決め手不足減点
    #
    # 大きく崩れない一方で、
    # 近走ずっと4〜6着付近に留まり、
    # 勝ち切る材料が少ない馬を地力評価から少し下げる
    # ==================================================

    decisive_penalty = 0

    decisive_finishes = horse.get(
        "着順",
        []
    )[:5]

    recent_three_finishes = (
        decisive_finishes[:3]
    )

    win_count = sum(
        1
        for finish in decisive_finishes
        if finish == 1
    )

    top3_count = sum(
        1
        for finish in decisive_finishes
        if finish <= 3
    )

    top5_count = sum(
        1
        for finish in decisive_finishes
        if finish <= 5
    )

    recent_three_are_minor_places = (
        len(recent_three_finishes) == 3
        and all(
            4 <= finish <= 6
            for finish in recent_three_finishes
        )
    )

    if (
        len(decisive_finishes) >= 4
        and win_count == 0
        and top3_count <= 1
        and top5_count >= 4
        and recent_three_are_minor_places
    ):
        decisive_penalty = 400
        score -= decisive_penalty
    long_spurt_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "スコア": score,
        "通過順": race_flows,
        "前経験回数": front_experience_count,
        "前経験減点": front_experience_penalty,

        # 前で実際に3着以内へ入った回数
        "前成功回数": front_success_count,

        # 前で運びながら速い上がりを使えた評価
        "持続上がり点": sustained_agari_bonus,
        "持続上がり回数": horse.get(
            "持続上がり回数",
            0
        ),
        "持続上がり詳細": horse.get(
            "持続上がり詳細",
            []
        ),

        # 能力とは別に管理した失速不安
        "元失速減点": raw_applied_risk_penalty,
        "失速減点": applied_risk_penalty,
        "失速詳細": risk_details,
        "南関転入初戦": is_nankan_transfer_first,
        "大失速減点": heavy_collapse_long_penalty,
        # 善戦止まり確認用
        "決め手不足減点": decisive_penalty,
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

# ==================================================
# 展開馬選出用・地力TOP5
# ==================================================
long_top5_for_tenkai = [
    dict(h)
    for h in long_spurt_candidates[:5]
]
# ==================================================
# 失速不安が強い馬
#
# 失速減点100以上かつ、
# 失速したレースが2回以上ある馬を対象にする
#
# 地力ランキングには残すが、
# 展開馬・後詰めの馬には選ばない
# ==================================================

shissoku_heavy_horse_numbers = {
    h["馬番"]
    for h in long_spurt_candidates
    if (
        h["馬番"]
        not in nankan_transfer_first_horse_numbers
        and h.get("失速減点", 0) >= 100
        and len(h.get("失速詳細", [])) >= 2
    )
}
# ==================================================
# 決め手不足馬
#
# 地力・総合のランキングには残すが、
# 展開馬・先行代表には選ばない
# ==================================================

decisive_shortage_horse_numbers = {
    h["馬番"]
    for h in long_spurt_candidates
    if h.get("決め手不足減点", 0) > 0
}
# ==================================================
# 先行代表Dの候補調整
#
# 先行Dは「今回距離で前へ行ける能力」を優先する。
#
# 最新走で大失速していても、
# 前へ行ける能力そのものは消さないため除外しない。
#
# 決め手不足馬だけは、
# 先行代表としての期待値を下げるため従来どおり除外する。
# ==================================================

front_candidates_without_risk = [
    h for h in front_candidates
    if (
        h["馬番"]
        not in decisive_shortage_horse_numbers
    )
]

# 全馬消える場合だけ元候補へ戻す
if front_candidates_without_risk:
    front_candidates = (
        front_candidates_without_risk
    )

# 先行代表を選び直す
front_best = front_candidates[0]

front_horse = (
    f"{front_best['馬番']}番 "
    f"{front_best['馬名']}"
)

front_score_map = {
    h["馬番"]: h["スコア"]
    for h in front_candidates
}
# 地力ランキングは評価順位をそのまま使う。
# 踏ん張り不足・失速不安はランキング上の評価にすでに反映済み。

if debug_mode:

    with st.expander(
        "🌋 地力ランキング",
        expanded=False
    ):

        for rank, h in enumerate(
            long_spurt_candidates[:5],
            start=1
        ):

            st.write(
                f"{rank}位｜"
                f"{h['馬番']}番 {h['馬名']} "
                f"｜地力 {round(h['スコア'], 1)} "
                f"｜前成功 "
                f"{h.get('前成功回数', 0)}回 "
                f"｜持続上がり "
                f"{h.get('持続上がり点', 0)} "
                f"｜失速 "
                f"-{h.get('失速減点', 0)} "
                f"｜大失速 "
                f"-{h.get('大失速減点', 0)} "
                f"｜決め手不足 "
                f"-{h.get('決め手不足減点', 0)}"
            )

    with st.expander(
        "🔍 地力の詳細データ",
        expanded=False
    ):

        for h in long_spurt_candidates:

            finishes = []

            for horse in horses:
                if horse["馬番"] == h["馬番"]:
                    finishes = horse.get(
                        "着順",
                        []
                    )
                    break

            st.markdown(
                f"**{h['馬番']}番 "
                f"{h['馬名']}**"
            )

            st.write(
                f"地力：{round(h['スコア'], 1)} "
                f"｜前経験 "
                f"{h.get('前経験回数', 0)}回 "
                f"｜前成功 "
                f"{h.get('前成功回数', 0)}回 "
                f"｜持続上がり "
                f"{h.get('持続上がり点', 0)} "
                f"｜該当 "
                f"{h.get('持続上がり回数', 0)}回 "
                f"｜前経験減点 "
                f"-{h.get('前経験減点', 0)} "
                f"｜失速減点 "
                f"-{h.get('失速減点', 0)} "
                f"｜元減点 "
                f"-{h.get('元失速減点', 0)} "
                f"｜南関転入初戦 "
                f"{h.get('南関転入初戦', False)}"
            )

            st.caption(
                f"通過順：{h['通過順']}\n\n"
                f"着順：{finishes}\n\n"
                f"持続上がり詳細："
                f"{h.get('持続上がり詳細', [])}\n\n"
                f"失速詳細："
                f"{h.get('失速詳細', [])}"
            )
        
if not long_spurt_candidates:
    st.error("長く脚の評価データが取れていません")
    st.stop()

# 地力ランキング1位をそのまま代表馬にする
long_best = long_spurt_candidates[0]

long_spurt_horse = (
    f"{long_best['馬番']}番 "
    f"{long_best['馬名']}"
)

# 展開評価で使用するスコアマップ
front_score_map = {
    h["馬番"]: h["スコア"]
    for h in front_candidates
}

long_score_map = {
    h["馬番"]: h["スコア"]
    for h in long_spurt_candidates
}
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
def analyze_flow_style(race_flows):
    """
    通過順だけで大まかな脚質傾向を判定する。

    着順・タイムは使わない。
    強いか弱いかではなく、普段どの位置で走るかを見る。
    """
    valid_count = 0
    escape_count = 0
    front_count = 0
    front_sustain_count = 0
    middle_sustain_count = 0
    push_count = 0
    back_count = 0

    for flow in race_flows:
        if len(flow) < 2:
            continue

        valid_count += 1

        first = flow[0]
        last = flow[-1]

        # 逃げ経験
        if len(flow) >= 4:
            second = flow[1]
            third = flow[2]

            if second == 1 or third == 1:
                escape_count += 1

        else:
            if first == 1 or last == 1:
                escape_count += 1

        # 前団に取り付けた経験
        if first <= 4:
            front_count += 1

        position_width = max(flow) - min(flow)

        # 前団持続
        # 2-2-2-2、3-2-3-3、3-4-4-4など
        is_front_sustain = (
            2 <= first <= 4
            and 2 <= last <= 5
            and position_width <= 2
        )

        # 中団持続
        # 5-5-6-6、6-6-7-7、4-5-6-6など
        is_middle_sustain = (
            4 <= first <= 7
            and 4 <= last <= 7
            and position_width <= 2
        )

        if is_front_sustain:
            front_sustain_count += 1

        elif is_middle_sustain:
            middle_sustain_count += 1

        # 差し・押し上げ
        # 5番手以下から2つ以上位置を上げたレース
        if first >= 5 and last <= first - 2:
            push_count += 1

        # 後方のまま
        if first >= 7 and last >= 7:
            back_count += 1

    stable_count = (
        front_sustain_count
        + middle_sustain_count
    )

    escape_rate = (
        escape_count / valid_count
        if valid_count > 0
        else 0
    )

    push_rate = (
        push_count / valid_count
        if valid_count > 0
        else 0
    )

    return {
        "有効数": valid_count,
        "逃げ回数": escape_count,
        "逃げ率": escape_rate,
        "前団回数": front_count,
        "前団持続回数": front_sustain_count,
        "中団持続回数": middle_sustain_count,
        "持続回数": stable_count,
        "押し上げ回数": push_count,
        "押し上げ率": push_rate,
        "後方回数": back_count,
    }
strong_firsts = [flow[0] for flow in strong_flows if len(flow) >= 2]
strong_lasts = [flow[-1] for flow in strong_flows if len(flow) >= 2]

strong_avg_first = avg_nonzero(strong_firsts)
strong_avg_last = avg_nonzero(strong_lasts)


# ==================================================
# 軸馬の脚質傾向
# 通過順だけで判定し、着順やタイムは混ぜない
# ==================================================

strong_style = analyze_flow_style(
    strong_flows
)

strong_escape_count = strong_style["逃げ回数"]
strong_front_count = strong_style["前団回数"]

strong_front_sustain_count = (
    strong_style["前団持続回数"]
)

strong_middle_sustain_count = (
    strong_style["中団持続回数"]
)

strong_stable_count = strong_style["持続回数"]
strong_push_count = strong_style["押し上げ回数"]
strong_back_count = strong_style["後方回数"]

escape_rate = strong_style["逃げ率"]
push_rate = strong_style["押し上げ率"]
# ==================================================
# 軸馬の大まかな脚色判定
#
# 表示は従来どおり、
# 逃げ・先行・持続・差し・展開待ちの5種類
#
# 強いか弱いかではなく、
# 過去5走で大体どこを走る馬かだけを見る
# ==================================================
# ① 逃げ
if escape_rate >= 0.5:
    kyakushoku_type = "逃げ"

# ② 先行
# 過去5走で前団（1角4番手以内）が2回以上あれば、
# 後方回数や平均位置より、前へ行けた実績を優先する
elif strong_front_count >= 2:
    kyakushoku_type = "先行"

# ③ 持続
# 前団持続と中団持続をまとめて「持続」と表示
elif (
    strong_stable_count >= 2
    and strong_stable_count >= strong_push_count
):
    kyakushoku_type = "持続"

# ④ 差し
# 後方から押し上げたレースが複数ある馬
elif strong_push_count >= 2:
    kyakushoku_type = "差し"

# ⑤ 差し救済
# 押し上げが1回でも、
# 平均的に中団以降から大きく前進している馬
elif (
    strong_push_count >= 1
    and strong_avg_first >= 4.5
    and strong_avg_last
        <= strong_avg_first - 1.5
):
    kyakushoku_type = "差し"

# ⑥ 持続救済
# 持続経験が1回でも、
# 普段から前〜中団で位置取りが安定している馬
elif (
    strong_stable_count >= 1
    and 3 <= strong_avg_first <= 6
    and abs(
        strong_avg_last
        - strong_avg_first
    ) <= 1.0
):
    kyakushoku_type = "持続"

# ⑦ 先行救済
# 前団経験が1回でも、
# 平均的に前で運べている馬
elif (
    strong_front_count >= 1
    and strong_avg_first <= 4
    and strong_avg_last <= 5
):
    kyakushoku_type = "先行"

# ⑧ 本当に傾向が定まらない馬
else:
    kyakushoku_type = "展開待ち"
# ==================================================
# 南関から他地区への転入初戦・脚色補正
#
# 南関で1角2番手以内を2回以上取れている馬は、
# 格が下がる転入初戦では主導権を取れる可能性を優先し「逃げ」。
#
# 2番手以内が2回未満でも、
# 1角4番手以内が2回以上なら「先行」とする。
# ==================================================
if popular_horse_num in nankan_transfer_first_horse_numbers:

    nankan_front_two_count = sum(
        1
        for flow in strong_flows
        if len(flow) >= 2
        and flow[0] <= 2
    )

    nankan_front_four_count = sum(
        1
        for flow in strong_flows
        if len(flow) >= 2
        and flow[0] <= 4
    )

    # 南関で2番手以内を複数回取れていれば逃げを優先
    if nankan_front_two_count >= 2:
        kyakushoku_type = "逃げ"

    # 逃げ条件には届かなくても、前団2回以上なら先行
    elif nankan_front_four_count >= 2:
        kyakushoku_type = "先行"
# ==================================================
# 展開待ち救済
# ==================================================

if kyakushoku_type == "展開待ち":

    # ------------------------------------------
    # ① 今回競馬場で既に差して好走している馬
    # ------------------------------------------
    current_track_races = [
        item
        for item in strong_data.get("距離付きタイム", [])
        if item.get("競馬場", "") == baba_name
    ]

    for item in current_track_races:

        flow = item.get("通過順", [])
        finish = item.get("着順")

        if not flow or finish is None:
            continue

        last_corner = flow[-1]

        if (
            finish <= 3
            and last_corner - finish >= 2
        ):
            kyakushoku_type = "差し"
            break
# ==================================================
# ② 地方未出走のJRA初転入馬
# ==================================================

if (
    kyakushoku_type == "展開待ち"
    and popular_horse_num in jra_horse_numbers
):

    # 前寄りなら先行
    if strong_avg_first <= 4.5:
        kyakushoku_type = "先行"

    # 中団で位置を保つタイプ
    elif (
        strong_avg_first <= 7
        and abs(
            strong_avg_last
            - strong_avg_first
        ) <= 1.5
    ):
        kyakushoku_type = "持続"

    # それ以外は後方型として差し
    else:
        kyakushoku_type = "差し"

if debug_mode:

    with st.expander(
        "🎯 軸馬の脚色判定",
        expanded=False
    ):

        st.write(
            f"最終判定：**{kyakushoku_type}**"
        )

        st.write(
            f"平均前半："
            f"{round(strong_avg_first, 2)} "
            f"｜平均4角："
            f"{round(strong_avg_last, 2)}"
        )

        st.write(
            f"逃げ {strong_escape_count}回 "
            f"｜前団 {strong_front_count}回 "
            f"｜持続 {strong_stable_count}回 "
            f"｜押し上げ {strong_push_count}回 "
            f"｜後方 {strong_back_count}回"
        )

        st.caption(
            f"逃げ率：{round(escape_rate, 2)} "
            f"｜差し率：{round(push_rate, 2)} "
            f"｜前団持続："
            f"{strong_front_sustain_count} "
            f"｜中団持続："
            f"{strong_middle_sustain_count}"
        )
# 人気馬が差してくるタイプなのに先行気勢1位にも出る場合は、
# 先行気勢の馬を次点候補にずらす
if kyakushoku_type == "差し" and front_best["馬番"] == popular_horse_num:
    for h in front_candidates:
        if h["馬番"] != popular_horse_num:
            front_best = h
            front_horse = f"{front_best['馬番']}番 {front_best['馬名']}"
            break

# ==================================================
# 地力Cと先行Dだけは同じ馬にしない
#
# 展開Bと地力Cの重複は許可する。
# 展開Bと先行Dの重複も許可する。
#
# ただし、
# 「地力1位」と「先行代表」が同じ馬になった場合だけ、
# 先行代表Dを前進気勢ランキングの次点へずらす。
#
# 次点選出では
# ・地力代表C
# ・軸馬A
# を除外する。
#
# 例：
# 前進 1位=11、2位=4(軸)、3位=9
# 地力 1位=11
# → 先行Dは9番になる。
#
# 地力評価や前進ランキング自体は変更しない。
# あくまで「先行代表D」だけを繰り下げる。
# ==================================================

cd_overlap_shifted = False
cd_overlap_original_front = None

if (
    front_best["馬番"]
    == long_best["馬番"]
):
    cd_overlap_original_front = {
        "馬番": front_best["馬番"],
        "馬名": front_best["馬名"],
    }

    for h in front_candidates:

        # 地力代表Cとは被らせない
        if h["馬番"] == long_best["馬番"]:
            continue

        # 軸馬Aとも被らせない
        if h["馬番"] == popular_horse_num:
            continue

        front_best = h

        front_horse = (
            f"{front_best['馬番']}番 "
            f"{front_best['馬名']}"
        )

        cd_overlap_shifted = True
        break


if debug_mode and cd_overlap_original_front is not None:

    with st.expander(
        "☄️ 地力C × 先行D 被り調整",
        expanded=False
    ):

        if cd_overlap_shifted:

            st.write(
                f"地力Cと先行Dが "
                f"{cd_overlap_original_front['馬番']}番 "
                f"{cd_overlap_original_front['馬名']} "
                f"で重複したため、"
            )

            st.write(
                f"先行Dを "
                f"{front_best['馬番']}番 "
                f"{front_best['馬名']} "
                f"へ繰り下げました。"
            )

        else:

            st.write(
                "地力Cと先行Dが重複しましたが、"
                "軸馬・地力馬以外の有効な先行候補がないため、"
                "重複を維持しました。"
            )

# ==================================================
# 新・展開馬候補ロジック
#
# ① 軸タイプを先に判定する
# ② 前進気勢ランキングTOP5と地力ランキングTOP5の
#    「両方」に入っている馬だけを共通候補にする
# ③ 軸タイプに合う脚質の馬を共通候補から選ぶ
# ④ 共通候補に軸タイプ適合馬がいない場合は、
#    総合ランキング確定後に総合上位から選ぶ
#
# ※軸馬自身は展開馬候補から除外する
# ==================================================

front_rank_map_for_tenkai = {
    h["馬番"]: rank
    for rank, h in enumerate(
        front_top5_for_tenkai,
        start=1,
    )
}

long_rank_map_for_tenkai = {
    h["馬番"]: rank
    for rank, h in enumerate(
        long_top5_for_tenkai,
        start=1,
    )
}

front_top5_numbers_for_tenkai = set(
    front_rank_map_for_tenkai.keys()
)

long_top5_numbers_for_tenkai = set(
    long_rank_map_for_tenkai.keys()
)

# 前進TOP5 ∩ 地力TOP5
common_top5_numbers_for_tenkai = (
    front_top5_numbers_for_tenkai
    & long_top5_numbers_for_tenkai
)

# 軸馬自身は除外
common_top5_numbers_for_tenkai.discard(
    popular_horse_num
)


def classify_tenkai_candidate(horse):
    """
    展開候補の脚質を通過順だけで判定する。

    軸馬の脚質判定と同じ考え方で、
    逃げ・先行・持続・差し・展開待ちの5種類に分ける。
    """

    race_flows = horse.get(
        "通過順",
        [],
    )

    style = analyze_flow_style(
        race_flows
    )

    firsts = [
        flow[0]
        for flow in race_flows
        if len(flow) >= 2
    ]

    lasts = [
        flow[-1]
        for flow in race_flows
        if len(flow) >= 2
    ]

    avg_first = avg_nonzero(
        firsts
    )

    avg_last = avg_nonzero(
        lasts
    )

    escape_rate = style[
        "逃げ率"
    ]

    front_count = style[
        "前団回数"
    ]

    stable_count = style[
        "持続回数"
    ]

    push_count = style[
        "押し上げ回数"
    ]

    # ① 逃げ
    if escape_rate >= 0.5:
        target_type = "逃げ"

    # ② 先行
    elif front_count >= 2:
        target_type = "先行"

    # ③ 持続
    elif (
        stable_count >= 2
        and stable_count >= push_count
    ):
        target_type = "持続"

    # ④ 差し
    elif push_count >= 2:
        target_type = "差し"

    # ⑤ 差し救済
    elif (
        push_count >= 1
        and avg_first >= 4.5
        and avg_last
        <= avg_first - 1.5
    ):
        target_type = "差し"

    # ⑥ 持続救済
    elif (
        stable_count >= 1
        and 3 <= avg_first <= 6
        and abs(
            avg_last
            - avg_first
        ) <= 1.0
    ):
        target_type = "持続"

    # ⑦ 先行救済
    elif (
        front_count >= 1
        and avg_first <= 4
        and avg_last <= 5
    ):
        target_type = "先行"

    else:
        target_type = "展開待ち"

    return {
        "候補脚質": target_type,
        "平均前半": avg_first,
        "平均4角": avg_last,
        "逃げ率": escape_rate,
        "前団回数": front_count,
        "持続回数": stable_count,
        "押し上げ回数": push_count,
    }


# 軸タイプごとに、展開相手として優先する脚質
# 最上位の脚質が1頭でもいれば、その脚質内だけで選ぶ。
tenkai_type_priority = {
    "逃げ": [
        "逃げ",
        "先行",
        "持続",
    ],
    "先行": [
        "先行",
        "持続",
        "逃げ",
    ],
    "持続": [
        "持続",
        "差し",
        "先行",
    ],
    "差し": [
        "差し",
        "持続",
    ],
    "展開待ち": [
        "先行",
        "持続",
        "差し",
    ],
}


# 軸タイプごとの前進・地力の比重
# これは展開候補スコア表示と、同脚質内の補助比較に使う。
tenkai_rank_weights = {
    "逃げ": (0.70, 0.30),
    "先行": (0.60, 0.40),
    "持続": (0.35, 0.65),
    "差し": (0.25, 0.75),
    "展開待ち": (0.50, 0.50),
}

front_weight, long_weight = (
    tenkai_rank_weights.get(
        kyakushoku_type,
        (0.50, 0.50),
    )
)


# 共通TOP5候補を作る
tenkai_common_candidates = []

for horse_no in sorted(
    common_top5_numbers_for_tenkai
):

    horse = next(
        (
            h
            for h in horses
            if h["馬番"] == horse_no
        ),
        None,
    )

    if horse is None:
        continue

    front_rank = (
        front_rank_map_for_tenkai[
            horse_no
        ]
    )

    long_rank = (
        long_rank_map_for_tenkai[
            horse_no
        ]
    )

    style_info = (
        classify_tenkai_candidate(
            horse
        )
    )

    # 1位=5点、2位=4点 ... 5位=1点
    front_rank_point = (
        6 - front_rank
    )

    long_rank_point = (
        6 - long_rank
    )

    # 0〜500程度の比較用スコア
    rank_score = (
        front_rank_point
        * front_weight
        * 100
        + long_rank_point
        * long_weight
        * 100
    )

    tenkai_common_candidates.append({
        "馬番": horse_no,
        "馬名": horse["馬名"],
        "スコア": rank_score,
        "前進順位": front_rank,
        "地力順位": long_rank,
        "順位合計": (
            front_rank + long_rank
        ),
        "候補脚質": style_info[
            "候補脚質"
        ],
        "平均前半": style_info[
            "平均前半"
        ],
        "平均4角": style_info[
            "平均4角"
        ],
        "逃げ率": style_info[
            "逃げ率"
        ],
        "前団回数": style_info[
            "前団回数"
        ],
        "持続回数": style_info[
            "持続回数"
        ],
        "押し上げ回数": style_info[
            "押し上げ回数"
        ],
        "選出元": "前進TOP5×地力TOP5",
    })


def tenkai_candidate_sort_key(h):
    """
    同じ優先脚質の中での並べ方。

    逃げ：前進順位を最優先
    先行：前進＋地力のバランス、同点なら前進
    持続：地力順位を最優先
    差し：地力順位 → 押し上げ実績 → 前進順位
    展開待ち：前進＋地力のバランス
    """

    front_rank = h.get(
        "前進順位",
        99,
    )

    long_rank = h.get(
        "地力順位",
        99,
    )

    rank_sum = (
        front_rank
        + long_rank
    )

    if kyakushoku_type == "逃げ":
        return (
            front_rank,
            long_rank,
        )

    if kyakushoku_type == "先行":
        return (
            rank_sum,
            front_rank,
            long_rank,
        )

    if kyakushoku_type == "持続":
        return (
            long_rank,
            front_rank,
        )

    if kyakushoku_type == "差し":
        return (
            long_rank,
            -h.get(
                "押し上げ回数",
                0,
            ),
            front_rank,
        )

    return (
        rank_sum,
        long_rank,
        front_rank,
    )


# --------------------------------------------------
# 軸タイプに合う馬を、共通TOP5から探す
# --------------------------------------------------
preferred_types = (
    tenkai_type_priority.get(
        kyakushoku_type,
        [],
    )
)

selected_target_type = None
compatible_common_candidates = []

for preferred_type in preferred_types:

    same_type_candidates = [
        h
        for h in tenkai_common_candidates
        if h.get(
            "候補脚質"
        ) == preferred_type
    ]

    if not same_type_candidates:
        continue

    compatible_common_candidates = sorted(
        same_type_candidates,
        key=tenkai_candidate_sort_key,
    )

    selected_target_type = (
        preferred_type
    )

    break


# 共通TOP5の中に軸タイプ適合馬がいる場合は、
# 採用脚質を先頭にし、その後ろも軸タイプの脚質優先順で並べる。
# これで三連複Bが被って繰り下がる時も、
# なるべく軸タイプに合う相手から順番に使える。
if compatible_common_candidates:

    ranked_common_candidates = []
    ranked_common_numbers = set()

    for preferred_type in preferred_types:

        type_group = sorted(
            [
                h
                for h in tenkai_common_candidates
                if (
                    h.get("候補脚質")
                    == preferred_type
                    and h["馬番"]
                    not in ranked_common_numbers
                )
            ],
            key=tenkai_candidate_sort_key,
        )

        ranked_common_candidates.extend(
            type_group
        )

        ranked_common_numbers.update(
            h["馬番"]
            for h in type_group
        )

    # 優先脚質に入らなかった馬は最後尾へ
    leftover_candidates = sorted(
        [
            h
            for h in tenkai_common_candidates
            if h["馬番"]
            not in ranked_common_numbers
        ],
        key=tenkai_candidate_sort_key,
    )

    tenkai_candidates = (
        ranked_common_candidates
        + leftover_candidates
    )

    tenkai_selection_source = (
        "前進TOP5×地力TOP5"
    )

else:

    # 総合ランキングがまだ未確定なので、
    # ここでは空のまま待つ。
    tenkai_candidates = []

    tenkai_selection_source = (
        "総合ランキング待ち"
    )

# 総合力1位を裏側で判定
front_score_map = {h["馬番"]: h["スコア"] for h in front_candidates}
long_score_map = {h["馬番"]: h["スコア"] for h in long_spurt_candidates}

total_candidates = []

# ==================================================
# 総合評価専用の同距離持ちタイム
#
# 今回1600mなら1600mだけ、
# 今回800mなら800mだけを使用する。
#
# この表は総合評価だけで使用し、
# この表は総合評価だけで使用する。
# ==================================================
total_same_distance_time_map = {}

for horse in horses:

    exact_distance_times = []

    for item in horse.get(
        "距離付きタイム",
        []
    ):

        # 今回と完全に同じ距離だけ使用する
        if item.get("距離") != distance_num:
            continue

        try:
            minutes, seconds = (
                item["タイム"].split(":")
            )

            total_seconds = (
                int(minutes) * 60
                + float(seconds)
            )

            # 園田・姫路の競馬場差補正は残す
            past_place = item.get(
                "競馬場",
                ""
            )

            if (
                baba_name == "園田"
                and past_place == "姫路"
            ):
                total_seconds += 5.0

            elif (
                baba_name == "姫路"
                and past_place == "園田"
            ):
                total_seconds -= 5.0

            exact_distance_times.append(
                total_seconds
            )

        except (ValueError, TypeError):
            continue

    if not exact_distance_times:
        continue

    # 同距離タイムの速い順
    exact_distance_times.sort()

    # 総合評価は同距離の上位2走平均
    top_exact_times = (
        exact_distance_times[:2]
    )

    representative_time = (
        sum(top_exact_times)
        / len(top_exact_times)
    )

    total_same_distance_time_map[
        horse["馬番"]
    ] = {
        "代表タイム": representative_time,
        "使用タイム": top_exact_times,
        "使用数": len(top_exact_times),
    }

# 同距離タイムを持つ馬が2頭以上いる場合だけ、
# 総合の持ちタイム点を有効にする
same_distance_time_horse_count = len(
    total_same_distance_time_map
)

if same_distance_time_horse_count >= 2:

    fastest_same_distance_average_time = min(
        data["代表タイム"]
        for data
        in total_same_distance_time_map.values()
    )

else:

    # 0頭または1頭なら比較できないため、
    # 全馬の総合タイム点を0にする
    fastest_same_distance_average_time = None
# ==================================================
# 同距離・逃げ切り警戒馬
#
# ① 今回と完全に同じ距離
# ② 逃げ切って1着
# ③ 全馬の同距離最速タイムから0.5秒以内
#
# 過去に失速歴があっても、
# 「逃げれば勝てる時計」を持つ馬として抑えで拾う
# ==================================================
same_distance_single_records = []

for horse in horses:

    horse_no = horse["馬番"]

    for item in horse.get(
        "距離付きタイム",
        []
    ):

        # 今回と完全に同じ距離だけ
        if item.get("距離") != distance_num:
            continue

        try:
            minutes, seconds = (
                item["タイム"].split(":")
            )

            total_seconds = (
                int(minutes) * 60
                + float(seconds)
            )

            # 総合タイムと同じ園田・姫路補正
            past_place = item.get(
                "競馬場",
                ""
            )

            if (
                baba_name == "園田"
                and past_place == "姫路"
            ):
                total_seconds += 5.0

            elif (
                baba_name == "姫路"
                and past_place == "園田"
            ):
                total_seconds -= 5.0

        except (ValueError, TypeError):
            continue

        flow = item.get(
            "元通過順",
            item.get("通過順", [])
        )

        same_distance_single_records.append({
            "馬番": horse_no,
            "タイム": total_seconds,
            "通過順": flow,
            "着順": item.get("着順"),
        })


# 全馬の同距離最速1走
fastest_same_distance_single_time = min(
    (
        record["タイム"]
        for record
        in same_distance_single_records
    ),
    default=None
)

same_distance_escape_win_horse_numbers = set()
same_distance_escape_win_info = {}

if fastest_same_distance_single_time is not None:

    for record in same_distance_single_records:

        flow = record["通過順"]
        finish = record["着順"]
        horse_no = record["馬番"]
        race_time = record["タイム"]

        # 同距離を最初から最後まで先頭で逃げ切った
        is_escape_win = (
            finish == 1
            and len(flow) >= 2
            and flow[0] == 1
            and flow[-1] == 1
        )

        # 全馬最速から0.5秒以内
        is_fast_enough = (
            race_time
            <= fastest_same_distance_single_time + 0.5
        )

        if (
            is_escape_win
            and is_fast_enough
        ):

            same_distance_escape_win_horse_numbers.add(
                horse_no
            )

            old_info = (
                same_distance_escape_win_info.get(
                    horse_no
                )
            )

            # 複数の逃げ切りがある場合は、
            # 最も速かったレースを保存する
            if (
                old_info is None
                or race_time < old_info["タイム"]
            ):
                same_distance_escape_win_info[
                    horse_no
                ] = {
                    "タイム": race_time,
                    "通過順": flow,
                }

if debug_mode:

    st.write(
        "同距離・逃げ切り警戒馬：",
        sorted(
            same_distance_escape_win_horse_numbers
        )
    )

    for horse_no in sorted(
        same_distance_escape_win_horse_numbers
    ):
        info = (
            same_distance_escape_win_info[
                horse_no
            ]
        )

        st.write(
            f"{horse_no}番 "
            f"{real_horses[horse_no - 1]} "
            f"｜タイム "
            f"{round(info['タイム'], 1)}秒 "
            f"｜通過順 "
            f"{info['通過順']}"
        )

if debug_mode:

    same_distance_horse_numbers = sorted(
        total_same_distance_time_map.keys()
    )

    st.write(
        f"総合同距離タイム対象："
        f"{distance_num}m "
        f"｜対象馬数 "
        f"{same_distance_time_horse_count}頭 "
        f"｜馬番 "
        f"{same_distance_horse_numbers}"
    )
# ==================================================
for horse in horses:
    horse_no = horse["馬番"]
    horse_name = horse["馬名"]
    
    total_score = 0
    finishes = horse.get("着順", [])
    flows = horse.get("通過順", [])
    horse_text = horse.get("取得テキスト", "")

    is_nankan_transfer_first = (
        horse_no
        in nankan_transfer_first_horse_numbers
    )

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
        "南関転入": 0,
        "直近3走": 0,
        "騎手": 0,
        "減点": 0,
    }
    # 直近大失速は総合にも信用減点を入れる。
    # 地力・展開よりは弱めにして、能力評価は残す。
    heavy_collapse_total_penalty = round(
        120
        * horse.get(
            "直近大失速強度",
            0
        ),
        1
    )

    total_score -= heavy_collapse_total_penalty

    debug_total_parts["減点"] -= (
        heavy_collapse_total_penalty
    )
    # 直近3走の好調度を総合評価へ100％反映
    recent_form_bonus, recent_results = calc_recent_form_bonus(
        finishes
    )

    total_score += recent_form_bonus
    debug_total_parts["直近3走"] += recent_form_bonus

    jra_transfer = (
        horse_no
        in jra_transfer_watch_numbers
    )
    # 前進気勢も少しだけ
    front_part = front_score_map.get(horse_no, 0) * 0.12
    total_score += front_part
    debug_total_parts["前進気勢"] += front_part
    # ==================================================
    # 持ちタイム評価
    # 上位2走平均を、最速馬との差で0〜120点にする
    # ==================================================
    time_score = 0
    best_time = None
    time_weight = 0
    time_diff = None
    used_times = []

    # 総合評価では、
    # 今回と完全に同じ距離のタイムだけを使用する
    time_info = (
        total_same_distance_time_map.get(
            horse_no
        )
    )

    if (
        time_info is not None
        and fastest_same_distance_average_time
        is not None
    ):

        best_time = time_info[
            "代表タイム"
        ]

        used_times = time_info[
            "使用タイム"
        ]

        time_diff = max(
            0,
            best_time
            - fastest_same_distance_average_time
        )

        # 同距離最速馬は120点
        # 1秒遅いごとに40点ずつ下げる
        # 3秒以上遅ければ0点
        time_score = max(
            0,
            120 - time_diff * 40
        )

        # 完全同距離なので基本係数は100％
        time_weight = 1.0

        local_result_count_for_jra = (
            jra_local_result_count_map.get(
                horse_no,
                0
            )
        )

        # JRA転入後の地方1〜2走は、
        # 地方で実際に出した同距離タイムを少し重く見る
        if (
            horse_no
            in jra_acclimating_horse_numbers
        ):

            # 地方1走：一発時計なので95％
            if local_result_count_for_jra == 1:
                time_weight = 0.95

            # 地方2走：地方適性が見え始めるので110％
            elif local_result_count_for_jra == 2:
                time_weight = 1.10

        # 通常馬・地方3走以上の元JRA馬
        # 同距離タイムが1走だけなら85％
        elif time_info["使用数"] == 1:
            time_weight = 0.85

        time_score *= time_weight

        total_score += time_score

        debug_total_parts[
            "持ちタイム"
        ] += time_score
    # ==================================================
    # 総合評価に使う地方実績を決める
    #
    # JRA転入馬でも、地方で2走以上していれば
    # 地方の着順・通過順を総合評価へ反映する
    # ==================================================
    local_tracks = {
        "盛岡", "水沢", "浦和", "船橋",
        "大井", "川崎", "金沢", "笠松",
        "名古屋", "園田", "姫路",
        "高知", "佐賀", "門別",
    }

    race_items = horse.get("距離付きタイム", [])

    # 地方競馬で走ったレースだけ、
    # 通過順・着順・距離を同じレース単位でセットにして残す。
    #
    # 距離を一緒に保持するのは、
    # 850m以下で「長い距離のゴール前失速」を
    # 軽減判定するため。
    local_flow_finish_pairs = [
        (
            item.get("通過順", []),
            finish,
            item.get("距離", 0),
        )
        for item, finish in zip(
            race_items,
            finishes
        )
        if item.get("競馬場", "") in local_tracks
    ]

    local_result_count = len(
        local_flow_finish_pairs
    )

    if jra_transfer:

        # JRA転入馬は地方実績2走以上で評価を解禁
        use_local_evaluation = (
            local_result_count >= 2
        )

        evaluation_flow_finish_pairs = (
            local_flow_finish_pairs
            if use_local_evaluation
            else []
        )

        evaluation_finishes = [
            finish
            for _, finish, _
            in evaluation_flow_finish_pairs
        ][:5]

    else:

        use_local_evaluation = True

        evaluation_flow_finish_pairs = [
            (
                item.get("通過順", []),
                finish,
                item.get("距離", 0),
            )
            for item, finish in zip(
                race_items,
                finishes
            )
        ]

        evaluation_finishes = [
            finish
            for _, finish, _
            in evaluation_flow_finish_pairs
        ][:5]
    # ==================================================
    # 過去5走の着順スコア
    # 最新走ほど重く、古い実績は少しずつ弱める
    # ==================================================
    if use_local_evaluation:

        finish_weights = [
            1.00,
            0.80,
            0.60,
            0.30,
            0.15,
        ]

        finish_part = 0

        for idx, finish in enumerate(
            evaluation_finishes
        ):

            if finish == 1:
                base_finish_point = 80

            elif finish == 2:
                base_finish_point = 60

            elif finish == 3:
                base_finish_point = 45

            elif finish <= 5:
                base_finish_point = 20

            elif finish >= 10:
                base_finish_point = -60

            elif finish >= 8:
                base_finish_point = -35

            else:
                base_finish_point = 0

            # 南関転入初戦では、
            # 南関時代の悪い着順だけ40％評価へ弱める。
            # 好走加点はそのまま残す。
            if (
                is_nankan_transfer_first
                and base_finish_point < 0
            ):
                base_finish_point *= (
                    NANKAN_TRANSFER_PENALTY_WEIGHT
                )

            weight = (
                finish_weights[idx]
                if idx < len(finish_weights)
                else 0.15
            )

            finish_part += (
                base_finish_point * weight
            )

        finish_part = round(
            finish_part,
            1
        )

        total_score += finish_part
        debug_total_parts["着順"] += finish_part
    # ==================================================
    # 平均着順
    # JRA転入馬は地方での着順だけを使用する
    # ==================================================
    if evaluation_finishes:

        avg_finish = (
            sum(evaluation_finishes)
            / len(evaluation_finishes)
        )

        average_finish_part = 0

        if avg_finish <= 3:
            average_finish_part = 100

        elif avg_finish <= 5:
            average_finish_part = 60

        elif avg_finish <= 7:
            average_finish_part = 20

        elif avg_finish >= 8:
            average_finish_part = -50

        if (
            is_nankan_transfer_first
            and average_finish_part < 0
        ):
            average_finish_part *= (
                NANKAN_TRANSFER_PENALTY_WEIGHT
            )

        total_score += average_finish_part

        debug_total_parts[
            "平均着順"
        ] += average_finish_part

    # ==================================================
    # 地力評価
    #
    # 通常馬は12％
    # 地方実績があるJRA転入馬は70％相当の8.4％
    # ==================================================

    if use_local_evaluation:

        if jra_transfer:
            long_weight = 0.084
        else:
            long_weight = 0.12

        long_part = (
            long_score_map.get(
                horse_no,
                0
            )
            * long_weight
        )

        total_score += long_part
        debug_total_parts["地力"] += long_part

    else:

        # 地方実績が1走以下のJRA転入馬だけ、
        # 従来どおり未知数として30点を加える
        total_score += 30
        debug_total_parts["JRA"] += 30
    # ==================================================
    # 南関転入成功ボーナス
    # 南関経験があり、今回の競馬場でも好走している馬を評価
    # ==================================================

    nankan_tracks = ["浦和", "船橋", "大井", "川崎"]

    is_nankan_transfer = (
        baba_name not in nankan_tracks
        and any(
            track in horse_text
            for track in nankan_tracks
        )
    )

    nankan_transfer_bonus = 0

    if is_nankan_transfer:

        past_races = horse.get("距離付きタイム", [])

        # 距離付きタイムと着順は過去走順で対応している
        for item, finish in zip(past_races, finishes):

            past_place = item.get("競馬場", "")

            # 今回と同じ競馬場での成績だけ評価する
            if past_place != baba_name:
                continue

            if finish == 1:
                nankan_transfer_bonus += 35

            elif finish <= 3:
                nankan_transfer_bonus += 25

            elif finish <= 5:
                nankan_transfer_bonus += 10

        # 着順加点との二重評価が強くなりすぎないよう上限を設定
        nankan_transfer_bonus = min(
            nankan_transfer_bonus,
            60
        )

        total_score += nankan_transfer_bonus

    debug_total_parts["南関転入"] += nankan_transfer_bonus
    # 今回騎手だけを使った騎手補正
    current_jockey = horse.get(
        "今回騎手",
        ""
    )

    jockey_bonus = 0

    # NAR出馬表では「吉村智」表記の場合がある
    if current_jockey.startswith(
        "吉村智"
    ):
        jockey_bonus = 35

    # 「望月洵」「望月」などの表記に対応
    elif current_jockey.startswith(
        "望月"
    ):
        jockey_bonus = 35

    total_score += jockey_bonus

    debug_total_parts[
        "騎手"
    ] += jockey_bonus
    # ==================================================
    # 総合評価の失速減点
    #
    # 改良①：
    # 同じ過去レースで複数の失速条件に該当しても、
    # 一番大きい減点だけを1回採用する。
    #
    # 改良②：
    # 今回850m以下で、
    # 過去1200m以上のレースを4番手以内から運んだ馬は、
    # 「ゴール前の失速」による減点を20％まで弱める。
    #
    # 長い距離で最後に止まったことと、
    # 800〜850mで前へ行ける能力を分けて評価する。
    #
    # ※道中ですでに大きく後退した減点は軽減しない。
    # ==================================================

    total_risk_details = []

    # 地方実績を評価できる馬は、
    # JRA転入馬でも地方での垂れを減点する
    if use_local_evaluation:

        for flow, finish, past_distance in (
            evaluation_flow_finish_pairs
        ):

            if len(flow) < 2:
                continue

            first = flow[0]
            last = flow[-1]

            # この1レース内の減点候補。
            # 最後に最大のもの1つだけ採用する。
            race_penalty_candidates = []

            # ① 逃げ・2番手から大敗
            if (
                first <= 2
                and finish is not None
                and finish >= 7
            ):
                race_penalty_candidates.append({
                    "理由": "逃げ・2番手から大敗",
                    "減点": 80,
                    "ゴール前失速系": True,
                })

            # ② 前半から4角で大きく後退
            if (
                first <= 3
                and last - first >= 4
            ):
                race_penalty_candidates.append({
                    "理由": "前半から4角で大きく後退",
                    "減点": 60,
                    "ゴール前失速系": False,
                })

            # ③ 4角からゴールまでの順位落下
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

                if drop_penalty > 0:
                    race_penalty_candidates.append({
                        "理由": "4角からゴールで失速",
                        "減点": drop_penalty,
                        "ゴール前失速系": True,
                    })

            # このレースで減点条件がなければ次へ
            if not race_penalty_candidates:
                continue

            # 同一レースでは最大減点だけを採用
            strongest_penalty = max(
                race_penalty_candidates,
                key=lambda x: x["減点"],
            )

            base_race_penalty = (
                strongest_penalty["減点"]
            )

            penalty_weight = 1.0
            relief_reasons = []

            # 南関から他地区への転入初戦は、
            # 従来どおり通常失速減点を40％へ弱める
            if is_nankan_transfer_first:
                penalty_weight *= (
                    NANKAN_TRANSFER_PENALTY_WEIGHT
                )
                relief_reasons.append(
                    "南関転入初戦40％"
                )

            # 850m以下専用。
            # 1200m以上で前へ行けた馬の
            # ゴール前スタミナ切れは20％評価へ弱める。
            ultra_short_fade_relief = (
                distance_num <= 850
                and past_distance >= 1200
                and first <= 4
                and strongest_penalty.get(
                    "ゴール前失速系",
                    False,
                )
            )

            if ultra_short_fade_relief:
                penalty_weight *= 0.20
                relief_reasons.append(
                    "850m以下・長距離ゴール前失速20％"
                )

            applied_race_penalty = round(
                base_race_penalty
                * penalty_weight,
                1,
            )

            total_score -= applied_race_penalty

            debug_total_parts[
                "減点"
            ] -= applied_race_penalty

            total_risk_details.append({
                "過去距離": past_distance,
                "通過順": flow,
                "着順": finish,
                "候補": race_penalty_candidates,
                "採用理由": strongest_penalty["理由"],
                "元減点": base_race_penalty,
                "適用減点": applied_race_penalty,
                "軽減": relief_reasons,
            })
    total_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "総合スコア": total_score,
        "持ちタイムスコア": time_score,

        # 現在は上位2走の平均タイム
        "ベストタイム": best_time,
        "代表タイム": best_time,

        "使用タイム": used_times,
        "タイム差": time_diff,
        "タイム係数": time_weight,
        "直近3走": recent_results,
        "南関転入初戦": is_nankan_transfer_first,

        # デバッグ確認用。
        # 同一レース最大1回・850m以下軽減の内容を保存。
        "総合失速詳細": total_risk_details,

        "内訳": debug_total_parts
    })

total_candidates = sorted(
    total_candidates,
    key=lambda x: x["総合スコア"],
    reverse=True
)
# ==================================================
# 総合ランキング確定
# ==================================================

if not total_candidates:
    st.error(
        "総合ランキングを作成できませんでした"
    )
    st.stop()

final_total_rank_map = {
    h["馬番"]: rank
    for rank, h in enumerate(
        total_candidates,
        start=1,
    )
}

# 総合ランキング1位をそのまま代表馬にする
# 踏ん張り不足・失速不安だけで代表から消さない。
total_best = total_candidates[0]

total_best_horse = (
    f"{total_best['馬番']}番 "
    f"{total_best['馬名']}"
)


# ==================================================
# 展開馬の最終決定
#
# 前進TOP5×地力TOP5の共通候補に、
# 軸タイプへ合う馬がいた場合はその候補を採用。
#
# 共通候補が0頭、または軸タイプへ合う馬が0頭なら、
# 総合ランキング上位から軸馬自身を飛ばして採用する。
# ==================================================

if tenkai_candidates:

    # 共通TOP5方式で決定
    for h in tenkai_candidates:
        h["最終総合順位"] = (
            final_total_rank_map.get(
                h["馬番"],
                99,
            )
        )

    tenkai_selection_source = (
        "前進TOP5×地力TOP5"
    )

else:

    # --------------------------------------------------
    # 共通TOP5に適合馬がいない場合だけ総合へフォールバック
    # --------------------------------------------------
    tenkai_candidates = []

    for rank, h in enumerate(
        total_candidates,
        start=1,
    ):

        # 軸馬自身は展開馬にしない
        if h["馬番"] == popular_horse_num:
            continue

        tenkai_candidates.append({
            "馬番": h["馬番"],
            "馬名": h["馬名"],
            "スコア": h[
                "総合スコア"
            ],
            "前進順位": (
                front_rank_map_for_tenkai.get(
                    h["馬番"],
                    99,
                )
            ),
            "地力順位": (
                long_rank_map_for_tenkai.get(
                    h["馬番"],
                    99,
                )
            ),
            "順位合計": 198,
            "候補脚質": "総合代替",
            "平均前半": 99,
            "平均4角": 99,
            "押し上げ回数": 0,
            "選出元": "総合ランキング",
            "最終総合順位": rank,
        })

    selected_target_type = (
        "総合代替"
    )

    tenkai_selection_source = (
        "総合ランキング"
    )


if not tenkai_candidates:
    st.error(
        "展開馬候補を作成できませんでした"
    )
    st.stop()


# 展開馬を最終決定
tenkai_final_candidates = (
    tenkai_candidates
)

tenkai_best = (
    tenkai_final_candidates[0]
)

tenkai_horse = (
    f"{tenkai_best['馬番']}番 "
    f"{tenkai_best['馬名']}"
)


# 三連複Bの繰り下げ候補にも、
# 最終の展開ランキング順をそのまま使う。
tenkai_rank_for_trio = [
    {
        "馬番": h["馬番"],
        "馬名": h["馬名"],
    }
    for h in tenkai_candidates
]


if debug_mode:

    with st.expander(
        "🌊 新・展開馬ランキング",
        expanded=False,
    ):

        st.write(
            f"軸タイプ：**{kyakushoku_type}** "
            f"｜選出元：**{tenkai_selection_source}** "
            f"｜採用脚質："
            f"**{selected_target_type or 'なし'}**"
        )

        st.write(
            "前進TOP5："
            + "、".join(
                f"{h['馬番']}番"
                for h in front_top5_for_tenkai
            )
        )

        st.write(
            "地力TOP5："
            + "、".join(
                f"{h['馬番']}番"
                for h in long_top5_for_tenkai
            )
        )

        common_numbers_text = (
            "、".join(
                f"{horse_no}番"
                for horse_no in sorted(
                    common_top5_numbers_for_tenkai
                )
            )
            if common_top5_numbers_for_tenkai
            else "なし"
        )

        st.write(
            f"共通TOP5：{common_numbers_text}"
        )

        for rank, h in enumerate(
            tenkai_candidates[:5],
            start=1,
        ):

            front_rank_text = (
                h.get("前進順位")
                if h.get("前進順位", 99) <= 5
                else "圏外"
            )

            long_rank_text = (
                h.get("地力順位")
                if h.get("地力順位", 99) <= 5
                else "圏外"
            )

            st.write(
                f"{rank}位｜"
                f"{h['馬番']}番 {h['馬名']} "
                f"｜脚質 {h.get('候補脚質', '不明')} "
                f"｜前進 {front_rank_text}位 "
                f"｜地力 {long_rank_text}位 "
                f"｜総合 "
                f"{h.get('最終総合順位', 99)}位 "
                f"｜選出元 {h.get('選出元', '')}"
            )

# ==================================================
# JRA転入馬の2段階警告
#
# 通常案内：
# JRA転入馬が1頭以上いる
#
# 強い警告：
# ・軸馬がJRA転入馬
# ・地方実績1走以下のJRA転入馬がいる
# ・JRA転入馬が複数いる
# ・主要評価にJRA転入馬が入っている
# ==================================================
if jra_count >= 1:

    jra_display_names = [
        (
            f"{horse_no}番 "
            f"{info['馬名']}"
        )
        for horse_no, info
        in jra_horse_info_map.items()
    ]

    key_role_numbers = {
        total_best["馬番"],
        tenkai_best["馬番"],
    }


    jra_key_role_numbers = (
        key_role_numbers
        & jra_horse_numbers
    )

    strong_warning_reasons = []

    # 軸馬がJRA転入馬
    if (
        popular_horse_num
        in jra_horse_numbers
    ):
        strong_warning_reasons.append(
            "軸馬がJRA転入馬"
        )

    # 地方実績が少ない
    strong_warning_reasons.append(
        "地方実績なし"
    )

    # JRA転入馬が複数
    if jra_count >= 2:
        strong_warning_reasons.append(
            "JRA転入馬が複数"
        )

    # 総合・展開・タイム最上位にいる
    if jra_key_role_numbers:
        strong_warning_reasons.append(
            "主要評価にJRA転入馬"
        )


    # 影響が大きい場合は強い警告
    if strong_warning_reasons:

        st.warning(
            "⚠️ JRA転入馬の影響が大きいレースです。\n\n"
            f"対象：{'、'.join(jra_display_names)}\n\n"
            f"理由：{'、'.join(strong_warning_reasons)}\n\n"
            "地方馬とのタイム・通過順を"
            "単純比較できない場合があります。\n\n"
            "展開・タイム評価の信頼度が"
            "通常より下がります。"
        )

    # 影響が限定的なら軽い案内
    else:

        st.info(
            "ℹ️ JRA転入馬がいます。\n\n"
            f"対象：{'、'.join(jra_display_names)}\n\n"
            "地方馬とのタイム・通過順を"
            "単純比較できない場合があります。"
        )
if debug_mode:

    with st.expander(
        "🌊 最終展開候補",
        expanded=False
    ):

        st.write(
            f"軸タイプ：**{kyakushoku_type}** "
            f"｜採用脚質："
            f"**{selected_target_type}**"
        )

        for rank, h in enumerate(
            tenkai_final_candidates[:5],
            start=1
        ):

            st.write(
                f"{rank}位｜"
                f"{h['馬番']}番 {h['馬名']} "
                f"｜{h.get('候補脚質', '不明')} "
                f"｜展開 "
                f"{round(h['スコア'], 1)} "
                f"｜総合 "
                f"{h.get('最終総合順位', 99)}位"
            )
if debug_mode:

    with st.expander(
        "👑 総合力ランキング",
        expanded=False
    ):

        for rank, h in enumerate(
            total_candidates[:5],
            start=1
        ):

            st.write(
                f"{rank}位｜"
                f"{h['馬番']}番 {h['馬名']} "
                f"｜総合 "
                f"{round(h['総合スコア'], 1)} "
                f"｜タイム "
                f"{round(h['内訳']['持ちタイム'], 1)} "
                f"｜地力 "
                f"{round(h['内訳']['地力'], 1)} "
                f"｜着順 "
                f"{round(h['内訳']['着順'], 1)} "
                f"｜平均 "
                f"{round(h['内訳']['平均着順'], 1)} "
                f"｜減点 "
                f"{round(h['内訳']['減点'], 1)}"
            )

    with st.expander(
        "🔍 総合力の詳細データ",
        expanded=False
    ):

        for h in total_candidates:

            st.markdown(
                f"**{h['馬番']}番 "
                f"{h['馬名']} "
                f"｜総合 "
                f"{round(h['総合スコア'], 1)}**"
            )

            st.caption(
                f"前進："
                f"{round(h['内訳']['前進気勢'], 1)} "
                f"｜タイム："
                f"{round(h['内訳']['持ちタイム'], 1)} "
                f"｜地力："
                f"{round(h['内訳']['地力'], 1)} "
                f"｜直近："
                f"{round(h['内訳']['直近3走'], 1)} "
                f"｜着順："
                f"{round(h['内訳']['着順'], 1)} "
                f"｜平均："
                f"{round(h['内訳']['平均着順'], 1)} "
                f"｜減点："
                f"{round(h['内訳']['減点'], 1)}"
            )

            # 850m以下軽減や同一レース最大1回が
            # 実際にどう適用されたか確認できるようにする
            if h.get("総合失速詳細"):
                st.caption(
                    "総合失速詳細："
                    f"{h['総合失速詳細']}"
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

# ==================================================
# 抑え候補用・地力TOP5マップ
#
# 抑え候補でも「地力が高いのに主要5役から漏れた馬」を
# 少し持ち上げる。
#
# 地力順位だけではスコア差を表現しきれないため、
# ・順位ボーナス
# ・地力スコアの12％（上限180点）
# の両方を使う。
#
# 例：
# 地力4位・地力1200点前後なら
# 70点 + 約144点 = 約214点の救済。
# ==================================================

long_rank_map_for_ana = {
    h["馬番"]: rank
    for rank, h in enumerate(
        long_spurt_candidates,
        start=1,
    )
}

long_score_map_for_ana = {
    h["馬番"]: h["スコア"]
    for h in long_spurt_candidates
}

ana_long_rank_bonus_table = {
    1: 150,
    2: 120,
    3: 90,
    4: 70,
    5: 50,
}


for h in ana_base_candidates:

    target_horse = None

    for horse in horses:
        if horse["馬番"] == h["馬番"]:
            target_horse = horse
            break

    ana_score = h["スコア"]

    # --------------------------------------------------
    # 地力TOP5を抑えスコアへ反映
    # --------------------------------------------------
    ana_long_rank = long_rank_map_for_ana.get(
        h["馬番"],
        99,
    )

    ana_long_score = long_score_map_for_ana.get(
        h["馬番"],
        0,
    )

    ana_long_rank_bonus = (
        ana_long_rank_bonus_table.get(
            ana_long_rank,
            0,
        )
    )

    ana_long_strength_bonus = 0

    if ana_long_rank <= 5:

        # 地力そのものの強さも少し反映。
        # ただし強すぎないよう180点で頭打ち。
        ana_long_strength_bonus = min(
            max(
                ana_long_score,
                0,
            )
            * 0.12,
            180,
        )

    ana_long_bonus = round(
        ana_long_rank_bonus
        + ana_long_strength_bonus,
        1,
    )

    ana_score += ana_long_bonus

    # --------------------------------------------------
    # 抑え用・失速減点
    #
    # 同じ過去レースで複数条件に該当しても、
    # 一番大きい減点だけを1回採用する。
    #
    # さらに「前に行って10着以下まで完全に止まった」
    # レースだけは致命的垂れとして強めに扱う。
    #
    # この判定は抑えランキング専用。
    # 前進気勢・先行代表Dの評価は下げない。
    # --------------------------------------------------
    ana_fade_penalty_total = 0
    ana_fade_details = []

    if target_horse:
        flows = target_horse.get("通過順", [])
        finishes = target_horse.get("着順", [])

        for idx, flow in enumerate(flows):
            if len(flow) < 2:
                continue

            last = flow[-1]
            finish = (
                finishes[idx]
                if idx < len(finishes)
                else None
            )

            if finish is None:
                continue

            race_penalty_candidates = []

            # 軽い垂れ：
            # 4角4番手以内から6着以下
            if last <= 4 and finish >= 6:
                race_penalty_candidates.append({
                    "理由": "4角前から6着以下",
                    "減点": 50,
                    "深度": "軽",
                })

            # 大きい垂れ：
            # 4角3番手以内から8〜9着
            if last <= 3 and 8 <= finish <= 9:
                race_penalty_candidates.append({
                    "理由": "4角3番手以内から8〜9着",
                    "減点": 80,
                    "深度": "大",
                })

            # 致命的な垂れ：
            # 4角3番手以内から10着以下
            #
            # 例：2-3 → 11着
            # 前へ行ける能力は認めつつ、
            # 抑え馬としての信頼だけ強く下げる。
            if last <= 3 and finish >= 10:
                race_penalty_candidates.append({
                    "理由": "4角3番手以内から10着以下",
                    "減点": 150,
                    "深度": "致命的",
                })

            if race_penalty_candidates:

                strongest = max(
                    race_penalty_candidates,
                    key=lambda x: x["減点"],
                )

                race_penalty = strongest["減点"]

                # 同一レースは最大減点1回だけ
                ana_score -= race_penalty
                ana_fade_penalty_total += race_penalty

                ana_fade_details.append({
                    "何走前": idx + 1,
                    "通過順": flow,
                    "着順": finish,
                    "採用理由": strongest["理由"],
                    "深度": strongest["深度"],
                    "減点": race_penalty,
                })

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
                avg_front = (
                    sum(front_positions)
                    / len(front_positions)
                )
                avg_last = (
                    sum(last_positions)
                    / len(last_positions)
                )

                if avg_front >= 7 and avg_last <= 5:
                    ana_score += 50

    ana_candidates.append({
        "馬番": h["馬番"],
        "馬名": h["馬名"],
        "スコア": ana_score,

        # デバッグ確認用
        "抑え地力順位": (
            ana_long_rank
            if ana_long_rank <= 5
            else None
        ),
        "抑え地力加点": ana_long_bonus,
        "抑え失速減点": ana_fade_penalty_total,
        "抑え失速詳細": ana_fade_details,
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
# ==================================================
# 850m以下・最高タイム警戒馬を抑え候補へ残す
#
# すでに軸・総合・展開・地力・先行に出ている場合は、
# 重複させず現在の役割を優先する。
#
# 主要5役に出ていない場合は、
# 通常の抑えスコアに関係なく候補へ復活させる。
# ==================================================

for watch_horse_no in sorted(
    ultra_short_best_time_watch_numbers
):

    if watch_horse_no in used_for_ana:
        continue

    watch_horse_data = next(
        (
            horse
            for horse in horses
            if horse["馬番"] == watch_horse_no
        ),
        None
    )

    if watch_horse_data is None:
        continue

    existing_watch_candidate = next(
        (
            h
            for h in ana_candidates
            if h["馬番"] == watch_horse_no
        ),
        None
    )

    if existing_watch_candidate is not None:

        existing_watch_candidate[
            "超短距離最高タイム警戒"
        ] = True

    else:

        ana_candidates.append({
            "馬番": watch_horse_no,
            "馬名": watch_horse_data["馬名"],
            "スコア": 0,
            "超短距離最高タイム警戒": True,
        })

# 通常候補にも警戒印を付ける
for h in ana_candidates:

    h["超短距離最高タイム警戒"] = (
        h["馬番"]
        in ultra_short_best_time_watch_numbers
    )

# ==================================================
# 同距離・逃げ切り警戒馬を抑え候補へ残す
#
# すでに軸・総合・展開・地力・先行に出ている場合は、
# 重複させず現在の役割を優先する
# ==================================================

for watch_horse_no in sorted(
    same_distance_escape_win_horse_numbers
):

    # すでに主要5役に出ている馬は、
    # 抑え馬へ重複させない
    if watch_horse_no in used_for_ana:
        continue

    watch_horse_data = next(
        (
            horse
            for horse in horses
            if horse["馬番"] == watch_horse_no
        ),
        None
    )

    if watch_horse_data is None:
        continue

    existing_watch_candidate = next(
        (
            h
            for h in ana_candidates
            if h["馬番"] == watch_horse_no
        ),
        None
    )

    # すでに抑え候補にいる場合は警戒印だけ付ける
    if existing_watch_candidate is not None:

        existing_watch_candidate[
            "同距離逃げ切り警戒"
        ] = True

    # 足切りなどで候補から消えていた場合も復活させる
    else:

        ana_candidates.append({
            "馬番": watch_horse_no,
            "馬名": watch_horse_data["馬名"],
            "スコア": 0,
            "同距離逃げ切り警戒": True,
        })

# 通常候補にも警戒印を付ける
for h in ana_candidates:

    h["同距離逃げ切り警戒"] = (
        h["馬番"]
        in same_distance_escape_win_horse_numbers
    )

# ==================================================
# 総合TOP3 × 地力TOP3 救済
#
# 目的：
# 総合ランキングと地力ランキングの両方で
# TOP3に入っている高評価馬が、
# 主要5役にも抑え1にも出ず消えるのを防ぐ。
#
# 条件：
# ① 総合TOP3
# ② 地力TOP3
# ③ 軸・総合1位・展開・地力1位・先行1位の
#    主要5役にはすでに出ていない
#
# 条件を満たす馬は、
# 通常の抑えスコアより優先して抑え候補へ残す。
#
# 例：
# 総合3位 ＋ 地力3位なのに主要5役に未表示
# → 抑え馬として優先救済
# ==================================================

total_top3_numbers = {
    h["馬番"]
    for h in total_candidates[:3]
}

long_top3_numbers = {
    h["馬番"]
    for h in long_spurt_candidates[:3]
}

top3_double_watch_numbers = (
    total_top3_numbers
    & long_top3_numbers
)

# 主要5役にすでに出ている馬は、
# 重複表示させない
top3_double_watch_numbers -= set(
    used_for_ana
)

top3_double_watch_info = {}

for watch_horse_no in sorted(
    top3_double_watch_numbers
):

    watch_horse_data = next(
        (
            horse
            for horse in horses
            if horse["馬番"] == watch_horse_no
        ),
        None
    )

    if watch_horse_data is None:
        continue

    total_rank = next(
        (
            rank
            for rank, h in enumerate(
                total_candidates,
                start=1
            )
            if h["馬番"] == watch_horse_no
        ),
        99
    )

    long_rank = next(
        (
            rank
            for rank, h in enumerate(
                long_spurt_candidates,
                start=1
            )
            if h["馬番"] == watch_horse_no
        ),
        99
    )

    top3_double_watch_info[
        watch_horse_no
    ] = {
        "馬名": watch_horse_data["馬名"],
        "総合順位": total_rank,
        "地力順位": long_rank,
    }

    existing_watch_candidate = next(
        (
            h
            for h in ana_candidates
            if h["馬番"] == watch_horse_no
        ),
        None
    )

    # すでに抑え候補にいる場合は、
    # 元の抑えスコアをそのまま残して救済印だけ付ける
    if existing_watch_candidate is not None:

        existing_watch_candidate[
            "総合TOP3地力TOP3救済"
        ] = True

        existing_watch_candidate[
            "総合TOP3順位"
        ] = total_rank

        existing_watch_candidate[
            "地力TOP3順位"
        ] = long_rank

    # 足切りなどで抑え候補から消えていた場合も復活
    else:

        ana_candidates.append({
            "馬番": watch_horse_no,
            "馬名": watch_horse_data["馬名"],
            "スコア": 0,
            "総合TOP3地力TOP3救済": True,
            "総合TOP3順位": total_rank,
            "地力TOP3順位": long_rank,
        })

# 通常候補にも救済印を付ける
for h in ana_candidates:

    is_top3_double_watch = (
        h["馬番"]
        in top3_double_watch_numbers
    )

    h[
        "総合TOP3地力TOP3救済"
    ] = is_top3_double_watch

    if is_top3_double_watch:

        info = (
            top3_double_watch_info.get(
                h["馬番"],
                {}
            )
        )

        h["総合TOP3順位"] = (
            info.get(
                "総合順位",
                99
            )
        )

        h["地力TOP3順位"] = (
            info.get(
                "地力順位",
                99
            )
        )

if debug_mode:

    with st.expander(
        "👑 総合TOP3 × 地力TOP3 救済",
        expanded=False
    ):

        if not top3_double_watch_numbers:

            st.write(
                "主要5役に未表示の救済対象馬なし"
            )

        else:

            for horse_no in sorted(
                top3_double_watch_numbers
            ):

                info = (
                    top3_double_watch_info[
                        horse_no
                    ]
                )

                st.write(
                    f"👑 {horse_no}番 "
                    f"{info['馬名']} "
                    f"｜総合{info['総合順位']}位 "
                    f"｜地力{info['地力順位']}位 "
                    f"｜抑え優先救済"
                )

# ==================================================
# 抑え候補を最終スコア順に並べ直す
#
# 展開候補や総合候補の元の並びではなく、
# 垂れ減点・距離補正などを反映した
# 最終ana_scoreで穴1〜5を決定する
# ==================================================
ana_candidates = sorted(
    ana_candidates,
    key=lambda x: (
        # 850m以下の最高タイム警戒を最優先
        x.get(
            "超短距離最高タイム警戒",
            False
        ),

        # 次に従来の同距離逃げ切り警戒
        x.get(
            "同距離逃げ切り警戒",
            False
        ),

        # 総合TOP3 × 地力TOP3で、
        # 主要5役に未表示の馬を通常抑えより優先
        x.get(
            "総合TOP3地力TOP3救済",
            False
        ),

        # 最後に通常の抑えスコア
        x["スコア"],
    ),
    reverse=True
)

if debug_mode:
    st.subheader("押さえ候補スコア")

    for h in ana_candidates:

        watch_marks = []

        if h.get(
            "超短距離最高タイム警戒",
            False
        ):
            watch_marks.append(
                "⚡最高タイム警戒"
            )

        if h.get(
            "同距離逃げ切り警戒",
            False
        ):
            watch_marks.append(
                "🏁逃げ切り警戒"
            )

        if h.get(
            "総合TOP3地力TOP3救済",
            False
        ):
            watch_marks.append(
                "👑総合TOP3×地力TOP3"
            )

        watch_text = (
            " ｜" + "・".join(
                watch_marks
            )
            if watch_marks
            else ""
        )

        extra_debug = ""

        if h.get(
            "抑え地力順位"
        ) is not None:

            extra_debug += (
                f" ｜地力"
                f"{h['抑え地力順位']}位"
                f"+{round(h.get('抑え地力加点', 0), 1)}"
            )

        if h.get(
            "抑え失速減点",
            0
        ) > 0:

            extra_debug += (
                f" ｜抑え失速"
                f"-{round(h.get('抑え失速減点', 0), 1)}"
            )

        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜押さえスコア "
            f"{round(h['スコア'], 1)}"
            f"{watch_text}"
            f"{extra_debug}"
        )

        if h.get(
            "抑え失速詳細"
        ):
            st.caption(
                f"失速詳細："
                f"{h['抑え失速詳細']}"
            )
# ==================================================
# 穴1〜穴5を安全に決定
#
# 通常の穴候補を最優先。
# 頭数不足の時だけ他ランキングから掘り返し、
# できるだけ別々の馬で穴1〜5を作る。
# ==================================================
ana_fallback = []

def add_ana_fallback(horse_no, horse_name):
    # 軸馬は穴候補にしない
    if horse_no == popular_horse_num:
        return

    # 現在選択されている斬り捨て御免馬
    current_kirisute_numbers = {
        int(horse_text.split("番")[0])
        for horse_text in st.session_state.get(
            "kirisute_horses",
            []
        )
    }

    if horse_no in current_kirisute_numbers:
        return

    # 同じ馬は追加しない
    if any(
        h["馬番"] == horse_no
        for h in ana_fallback
    ):
        return

    ana_fallback.append({
        "馬番": horse_no,
        "馬名": horse_name,
    })

# ① 本来の穴候補を最優先
for h in ana_candidates:
    add_ana_fallback(
        h["馬番"],
        h["馬名"]
    )

# ② 足りなければ総合から補充
for h in total_candidates:
    add_ana_fallback(
        h["馬番"],
        h["馬名"]
    )

# ③ 展開から補充
for h in tenkai_candidates:
    add_ana_fallback(
        h["馬番"],
        h["馬名"]
    )

# ④ 地力から補充
for h in long_spurt_candidates:
    add_ana_fallback(
        h["馬番"],
        h["馬名"]
    )

# ⑤ 前進気勢から補充
for h in front_candidates:
    add_ana_fallback(
        h["馬番"],
        h["馬名"]
    )

# ⑥ 最後に全出走馬から補充
for h in horses:
    add_ana_fallback(
        h["馬番"],
        h["馬名"]
    )
# 南関専用の抑え1強制変更は廃止。
# 抑え馬は通常の抑え候補順位をそのまま使用する。

# 念のため候補0頭なら停止
if not ana_fallback:
    st.error("穴候補を作成できませんでした")
    st.stop()

# 穴1
ana_best = ana_fallback[0]

# 穴2
ana_second = (
    ana_fallback[1]
    if len(ana_fallback) >= 2
    else ana_fallback[-1]
)

# 穴3
ana_third = (
    ana_fallback[2]
    if len(ana_fallback) >= 3
    else ana_fallback[-1]
)

# 穴4
ana_fourth = (
    ana_fallback[3]
    if len(ana_fallback) >= 4
    else ana_fallback[-1]
)

# 穴5
ana_fifth = (
    ana_fallback[4]
    if len(ana_fallback) >= 5
    else ana_fallback[-1]
)

ana_horse = (
    f"{ana_best['馬番']}番 {ana_best['馬名']}"
)

ana_second_horse = (
    f"{ana_second['馬番']}番 {ana_second['馬名']}"
)

ana_third_horse = (
    f"{ana_third['馬番']}番 {ana_third['馬名']}"
)

ana_fourth_horse = (
    f"{ana_fourth['馬番']}番 {ana_fourth['馬名']}"
)

ana_fifth_horse = (
    f"{ana_fifth['馬番']}番 {ana_fifth['馬名']}"
)

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
# 軸馬と総合評価1位が異なる時だけ、後詰めの馬を小さく表示
if total_best["馬番"] != popular_horse_num:
    st.markdown(
        f'<div style="font-size:14px; line-height:1.8; color:#111111; margin:8px 2px 12px 2px;">'
        f'<div style="font-weight:600;">⚔️ 後詰めの馬（軸飛び対策）</div>'
        f'<div style="font-weight:600;">{total_best_horse}</div>'
        f'<div style="margin-top:5px;">⚠️ 軸馬が崩れた場合は、この馬を中心にした買い目も検討してください。</div>'
        f'</div>',
        unsafe_allow_html=True
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
# ==================================================
# 斬り捨て御免馬
# 分析結果には影響させず、最終買い目からだけ除外する
# ==================================================

kirisute_options = [
    f"{h['馬番']}番 {h['馬名']}"
    for h in horses
    if h["馬番"] != popular_horse_num
]

if "kirisute_limit_warning" not in st.session_state:
    st.session_state.kirisute_limit_warning = False

def limit_kirisute_horses():
    selected = st.session_state.get(
        "kirisute_horses",
        []
    )

    if len(selected) > 2:
        st.session_state.kirisute_horses = selected[:2]
        st.session_state.kirisute_limit_warning = True
    else:
        st.session_state.kirisute_limit_warning = False

with st.expander(
    "⚔️ 斬り捨て御免馬（任意で斬りたい馬を選択）",
    expanded=False
):
    kirisute_horses = st.multiselect(
        "斬り捨て御免馬",
        options=kirisute_options,
        placeholder="斬りたい馬を選択",
        label_visibility="collapsed",
        key="kirisute_horses",
        on_change=limit_kirisute_horses,
    )

    if st.session_state.kirisute_limit_warning:
        st.warning(
            "⚠️ 斬り捨て御免馬は2頭までです"
        )

kirisute_horse_numbers = {
    int(horse_text.split("番")[0])
    for horse_text in kirisute_horses
}
def get_num(horse_text):
    return int(horse_text.split("番")[0])

def horse_text(h):
    return f"{h['馬番']}番 {h['馬名']}"

def unique_texts(items):
    result = []
    used = set()

    for item in items:
        num = get_num(item)
        if num not in used:
            result.append(item)
            used.add(num)

    return result

popular = (
    f"{popular_horse_num}番 "
    f"{real_horses[popular_horse_num - 1]}"
)

# ==================================================
# 手書き設計版・最終買い目
#
# 表示中の5頭は一切変更しない。
# ここから下は「買い目専用」のアルファベット馬を作る。
#
# A：軸
# B：展開
# C：地力
# D：先行
# E：抑え
# F：後詰め
# G：穴3
# I：穴2
#
# 異なる記号が同じ馬になった場合の優先順位：
# A → F → C → E → D → B → G → I
#
# 先に確定した記号を残し、
# 後から確定する記号だけ自分の候補2位以降へ移動する。
#
# 同じ記号を複数の買い目で使う場合は、
# 同じ馬をそのまま再使用する。
#
# I（穴2）だけは例外で、
# 穴3を飛ばし、穴4 → 穴5 → 穴1の順に進む。
# ==================================================

# --------------------------------------------------
# 軸タイプ別・手書き買い目
# --------------------------------------------------
handwritten_bet_templates = {
    "逃げ": {
        "三連複": [
            ["A", "B", "D"],
            ["A", "G", "C"],
        ],
        "ワイド": [
            ["A", "B"],
            ["A", "I"],
        ],
        "浮き輪": [
            ["D", "I"],
        ],
    },
    "先行": {
        "三連複": [
            ["A", "B", "F"],
            ["A", "E", "C"],
        ],
        "ワイド": [
            ["A", "B"],
            ["A", "G"],
        ],
        "浮き輪": [
            ["D", "E"],
        ],
    },
    "持続": {
        "三連複": [
            ["A", "B", "C"],
            ["A", "C", "E"],
        ],
        "ワイド": [
            ["A", "B"],
            ["D", "C"],
        ],
        "浮き輪": [
            ["E", "G"],
        ],
    },
    "差し": {
        "三連複": [
            ["A", "B", "E"],
            ["A", "D", "I"],
        ],
        "ワイド": [
            ["A", "B"],
            ["A", "C"],
        ],
        "浮き輪": [
            ["I", "G"],
        ],
    },
    "展開待ち": {
        "三連複": [
            ["A", "B", "F"],
            ["A", "F", "D"],
        ],
        "ワイド": [
            ["A", "B"],
            ["F", "C"],
        ],
        "浮き輪": [
            ["E", "G"],
        ],
    },
}

current_bet_template = handwritten_bet_templates.get(
    kyakushoku_type,
    handwritten_bet_templates["展開待ち"],
)

# ==================================================
# 1580m以下・先行軸専用の三連複2点目
#
# 浦和800mの検証から、
# 先行軸では
#
# A：軸
# D：先行
# E：抑え
#
# の組み合わせを2点目で拾う。
#
# 通常の先行軸：
#   1点目 A-B-F
#   2点目 A-E-C
#
# 1580m以下・先行軸：
#   1点目 A-B-F
#   2点目 A-D-E
#
# ワイド・浮き輪は変更しない。
# 特に浮き輪 D-E は従来どおり残す。
# ==================================================
if (
    distance_num <= 1580
    and kyakushoku_type == "先行"
):
    # 元テンプレート本体を直接変更しないように、
    # 買い目配列をコピーしてから1580m以下専用形へ変更する。
    current_bet_template = {
        bet_type: [
            bet[:] for bet in bets
        ]
        for bet_type, bets
        in current_bet_template.items()
    }

    current_bet_template[
        "三連複"
    ][1] = [
        "A",
        "D",
        "E",
    ]

# --------------------------------------------------
# 買い目専用の候補プール
#
# 1頭目には画面表示中の代表馬を置く。
# その後ろに各ランキング順をつなぐ。
#
# これにより、画面表示は変えず、
# 買い目内で被った時だけ2位・3位へ移動できる。
# --------------------------------------------------

all_bet_pool = unique_texts(
    [horse_text(h) for h in horses]
)

f_pool = unique_texts(
    [total_best_horse]
    + [horse_text(h) for h in total_candidates]
    + all_bet_pool
)

c_pool = unique_texts(
    [long_spurt_horse]
    + [horse_text(h) for h in long_spurt_candidates]
    + all_bet_pool
)

e_pool = unique_texts(
    [
        ana_horse,
        ana_second_horse,
        ana_third_horse,
        ana_fourth_horse,
        ana_fifth_horse,
    ]
    + [horse_text(h) for h in ana_fallback]
    + all_bet_pool
)

d_pool = unique_texts(
    [front_horse]
    + [horse_text(h) for h in front_candidates]
    + all_bet_pool
)

b_pool = unique_texts(
    [tenkai_horse]
    + [horse_text(h) for h in tenkai_rank_for_trio]
    + [horse_text(h) for h in tenkai_candidates]
    + all_bet_pool
)

# G＝穴3
# 穴3 → 穴4 → 穴5 → 穴1 → 穴2
g_pool = unique_texts(
    [
        ana_third_horse,
        ana_fourth_horse,
        ana_fifth_horse,
        ana_horse,
        ana_second_horse,
    ]
    + [horse_text(h) for h in ana_fallback]
    + all_bet_pool
)

# I＝穴2
# 穴2 → 穴4 → 穴5 → 穴1
# 穴3の馬は、別ランキング経由でもIには入れない。
hole3_number_for_i = get_num(
    ana_third_horse
)

i_pool = [
    item
    for item in unique_texts(
        [
            ana_second_horse,
            ana_fourth_horse,
            ana_fifth_horse,
            ana_horse,
        ]
        + [horse_text(h) for h in ana_fallback]
        + all_bet_pool
    )
    if get_num(item) != hole3_number_for_i
]

alphabet_candidate_pools = {
    "A": [popular],
    "F": f_pool,
    "C": c_pool,
    "E": e_pool,
    "D": d_pool,
    "B": b_pool,
    "G": g_pool,
    "I": i_pool,
}

alphabet_role_names = {
    "A": "軸",
    "F": "後詰め",
    "C": "地力",
    "E": "抑え",
    "D": "先行",
    "B": "展開",
    "G": "穴3",
    "I": "穴2",
}

alphabet_priority = [
    "A",
    "F",
    "C",
    "E",
    "D",
    "B",
    "G",
    "I",
]


def collect_required_symbols(template):
    """
    今回の軸タイプで実際に使う記号だけを集める。

    使わない記号が、使う記号の馬を奪わないようにする。
    """

    required = set()

    for bet_group in template.values():
        for symbol_list in bet_group:
            required.update(symbol_list)

    return required


def build_symbol_conflicts(template):
    """
    同じ買い目内に出る記号同士を保存する。

    さらに、同じ軸を共有するワイド2点では、
    相手記号同士も同じ馬にならないようにする。

    例：A-B / A-E の場合はBとEも競合扱いにする。
    これにより、A-BとA-Eが同じワイドになるのを防ぐ。
    """

    conflicts = {}

    # 同じ1つの買い目内に出る記号同士
    for bet_group in template.values():
        for symbol_list in bet_group:
            for symbol in symbol_list:
                conflicts.setdefault(
                    symbol,
                    set(),
                )

                conflicts[symbol].update(
                    other_symbol
                    for other_symbol in symbol_list
                    if other_symbol != symbol
                )

    # 同じ軸を共有するワイド同士の重複を防ぐ。
    # 例：A-B / A-Eなら、BとEを別馬にする。
    wide_templates = [
        symbol_list
        for symbol_list in template.get(
            "ワイド",
            [],
        )
        if len(symbol_list) == 2
    ]

    for first_index in range(
        len(wide_templates)
    ):
        for second_index in range(
            first_index + 1,
            len(wide_templates),
        ):
            first_pair = wide_templates[
                first_index
            ]
            second_pair = wide_templates[
                second_index
            ]

            shared_symbols = (
                set(first_pair)
                & set(second_pair)
            )

            # 1つの記号を共通で使うワイドだけ対象
            if len(shared_symbols) != 1:
                continue

            shared_symbol = next(
                iter(shared_symbols)
            )

            first_other = next(
                symbol
                for symbol in first_pair
                if symbol != shared_symbol
            )

            second_other = next(
                symbol
                for symbol in second_pair
                if symbol != shared_symbol
            )

            conflicts.setdefault(
                first_other,
                set(),
            ).add(second_other)

            conflicts.setdefault(
                second_other,
                set(),
            ).add(first_other)

    return conflicts


required_symbols = collect_required_symbols(
    current_bet_template
)

symbol_conflicts = build_symbol_conflicts(
    current_bet_template
)


def choose_alphabet_horse(
    symbol,
    selected_symbols,
    excluded_numbers,
    require_global_unique=True,
):
    """
    記号専用候補から最上位馬を選ぶ。

    通常は、すでに他記号で使った馬をすべて避ける。
    少頭数で候補が足りない時だけ、
    同じ買い目に出ない記号との重複を許す。
    """

    candidate_pool = alphabet_candidate_pools.get(
        symbol,
        all_bet_pool,
    )

    used_numbers = {
        get_num(horse_name)
        for horse_name
        in selected_symbols.values()
    }

    conflicting_symbols = symbol_conflicts.get(
        symbol,
        set(),
    )

    for candidate in candidate_pool:
        candidate_number = get_num(
            candidate
        )

        if candidate_number in excluded_numbers:
            continue

        if (
            require_global_unique
            and candidate_number in used_numbers
        ):
            continue

        # 全体重複を許す最終救済でも、
        # 同じ買い目内の記号とは絶対に被らせない。
        same_bet_duplicate = any(
            other_symbol in selected_symbols
            and get_num(
                selected_symbols[other_symbol]
            ) == candidate_number
            for other_symbol in conflicting_symbols
        )

        if same_bet_duplicate:
            continue

        return candidate

    return None

def select_bet_alphabet_horses(
    excluded_numbers=None,
):
    """
    今回使う記号だけを、
    A → F → C → E → D → B → G → I
    の順で確定する。

    別の買い目に出る記号同士は、
    同じ馬を使用してもよい。

    同じ買い目内に登場する記号同士だけ、
    同じ馬にならないようにする。
    """

    excluded_numbers = set(
        excluded_numbers or set()
    )

    selected_symbols = {}

    selection_order = [
        symbol
        for symbol in alphabet_priority
        if symbol in required_symbols
    ]
    # B＝展開、F＝後詰めを同じ買い目で使う場合は、
    # 展開馬を優先して先に確定する。
    #
    # 例：A-B-FでBとFが同じ8番なら、
    # B＝展開1位の8番を残し、
    # F＝総合2位へ繰り下げる。
    if (
        "B" in selection_order
        and "F" in selection_order
    ):
        selection_order.remove("B")

        f_index = selection_order.index("F")

        selection_order.insert(
            f_index,
            "B",
        )
    for symbol in selection_order:

        selected_horse = choose_alphabet_horse(
            symbol,
            selected_symbols,
            excluded_numbers,

            # 全記号を別馬にはしない。
            # 同じ買い目内の重複だけ防ぐ。
            require_global_unique=False,
        )

        if selected_horse is not None:
            selected_symbols[symbol] = (
                selected_horse
            )

    return selected_symbols

def make_bets_from_symbols(
    symbol_templates,
    selected_symbols,
):
    """
    記号の買い目を実際の馬名へ変換する。
    """

    result = []

    for symbol_list in symbol_templates:

        if not all(
            symbol in selected_symbols
            for symbol in symbol_list
        ):
            continue

        bet = [
            selected_symbols[symbol]
            for symbol in symbol_list
        ]

        bet_numbers = [
            get_num(horse_name)
            for horse_name in bet
        ]

        # 同じ買い目内で同じ馬になったものは出さない。
        if len(bet_numbers) != len(
            set(bet_numbers)
        ):
            continue

        result.append(
            bet
        )

    return result
def make_unique_trio_bets(
    symbol_templates,
    selected_symbols,
    excluded_numbers=None,
):
    """
    三連複を上から順番に作る。

    三連複1点目にFがあり、
    後詰めFの本来1位が軸Aと同じ馬だった場合だけ、
    1点目のFを先行馬へ変更する。

    先行馬1位が軸・別枠・斬り捨て馬と被る場合は、
    先行馬2位、3位へ順番に繰り下げる。

    有効な先行馬がいない場合は、
    通常の後詰めFの繰り下げ馬をそのまま使う。

    2点目以降のFには影響させない。
    軸Aは固定する。
    """

    excluded_numbers = set(
        excluded_numbers or set()
    )

    result = []
    used_trio_keys = set()

    # 後詰めFと展開Bが同じ馬なら、
    # 三連複の重複解消時にその馬を優先して残す
    protected_fb_number = None

    if (
        f_pool
        and b_pool
        and get_num(f_pool[0]) == get_num(b_pool[0])
    ):
        protected_fb_number = get_num(
            f_pool[0]
        )

    # 三連複1点目のF置き換え専用
    # all_bet_poolは入れず、本当の先行候補だけを使う
    first_trio_front_pool = unique_texts(
        [front_horse]
        + [
            horse_text(h)
            for h in front_candidates
        ]
    )

    for bet_index, symbol_list in enumerate(
        symbol_templates
    ):

        # この買い目だけで使う記号
        # 元のselected_symbolsは変更しない
        bet_selected_symbols = dict(
            selected_symbols
        )

        # ==================================================
        # 三連複1点目限定
        #
        # 後詰めFの本来1位が軸Aと同じ馬なら、
        # 1点目のFだけ先行馬へ変更する。
        #
        # 脚色タイプ名では判定しないため、
        # どの脚色でも1点目にFがあれば共通で適用される。
        # ==================================================
        if (
            bet_index == 0
            and "F" in symbol_list
            and f_pool
            and get_num(f_pool[0]) == popular_horse_num
        ):

            # F以外ですでに使われる馬番
            other_numbers = {
                get_num(
                    bet_selected_symbols[symbol]
                )
                for symbol in symbol_list
                if (
                    symbol != "F"
                    and symbol in bet_selected_symbols
                )
            }

            front_replacement = next(
                (
                    candidate
                    for candidate
                    in first_trio_front_pool
                    if (
                        get_num(candidate)
                        not in excluded_numbers

                        and get_num(candidate)
                        not in other_numbers
                    )
                ),
                None,
            )

            # 有効な先行馬が見つかった時だけ変更
            # 見つからなければ通常のFを維持する
            if front_replacement is not None:
                bet_selected_symbols["F"] = (
                    front_replacement
                )

        if not all(
            symbol in bet_selected_symbols
            for symbol in symbol_list
        ):
            continue

        bet = [
            bet_selected_symbols[symbol]
            for symbol in symbol_list
        ]

        bet_numbers = [
            get_num(horse_name)
            for horse_name in bet
        ]

        bet_key = frozenset(
            bet_numbers
        )

        # 同じ買い目内で3頭が別馬、
        # かつ過去の三連複と同じ組み合わせでなければ確定
        if (
            len(bet_numbers) == 3
            and len(set(bet_numbers)) == 3
            and bet_key not in used_trio_keys
        ):
            result.append(bet)
            used_trio_keys.add(bet_key)
            continue

        resolved_bet = None

        # 右側の記号から順番に次候補を探す。
        # Aは軸なので変更しない。
        for change_index in range(
            len(symbol_list) - 1,
            -1,
            -1,
        ):

            change_symbol = symbol_list[
                change_index
            ]

            if change_symbol == "A":
                continue

            candidate_pool = (
                alphabet_candidate_pools.get(
                    change_symbol,
                    all_bet_pool,
                )
            )

            current_horse = (
                bet_selected_symbols[
                    change_symbol
                ]
            )

            current_number = get_num(
                current_horse
            )

            # 後詰めFと展開Bが一致した馬は、
            # 重複解消でも動かさず優先して残す
            if (
                protected_fb_number is not None
                and current_number
                == protected_fb_number
            ):
                continue

            # 現在選ばれている馬が、
            # 候補プールの何番目かを確認
            current_pool_index = next(
                (
                    index
                    for index, candidate
                    in enumerate(candidate_pool)
                    if get_num(candidate)
                    == current_number
                ),
                -1,
            )

            # 現在馬より下位の候補だけを試す
            next_candidates = candidate_pool[
                current_pool_index + 1:
            ]

            for candidate in next_candidates:

                candidate_number = get_num(
                    candidate
                )

                if (
                    candidate_number
                    in excluded_numbers
                ):
                    continue

                test_bet = bet[:]

                test_bet[
                    change_index
                ] = candidate

                test_numbers = [
                    get_num(horse_name)
                    for horse_name in test_bet
                ]

                # 同じ三連複内で馬が被る候補は不可
                if len(set(test_numbers)) != 3:
                    continue

                test_key = frozenset(
                    test_numbers
                )

                # 1点目と同じ3頭なら、
                # さらに次候補へ進む
                if test_key in used_trio_keys:
                    continue

                resolved_bet = test_bet
                break

            if resolved_bet is not None:
                break

        if resolved_bet is not None:

            result.append(
                resolved_bet
            )

            used_trio_keys.add(
                frozenset(
                    get_num(horse_name)
                    for horse_name
                    in resolved_bet
                )
            )

    return result

# --------------------------------------------------
# 斬り捨て前の通常選出
# --------------------------------------------------
normal_bet_symbols = select_bet_alphabet_horses()

# --------------------------------------------------
# 斬り捨て後の最終選出
#
# 斬られた記号だけではなく、
# 優先順位の先頭から再計算することで、
# 各記号の順位関係を崩さない。
# --------------------------------------------------
final_bet_symbols = select_bet_alphabet_horses(
    excluded_numbers=kirisute_horse_numbers
)

trio_bets = make_unique_trio_bets(
    current_bet_template["三連複"],
    final_bet_symbols,
    excluded_numbers=kirisute_horse_numbers,
)

wide_bets = make_bets_from_symbols(
    current_bet_template["ワイド"],
    final_bet_symbols,
)

float_bets = make_bets_from_symbols(
    current_bet_template["浮き輪"],
    final_bet_symbols,
)

# 必要な買い目を作れなかった場合は、
# 斬り捨て前の通常選出へ戻す。
if len(trio_bets) < 2:
    trio_bets = make_unique_trio_bets(
        current_bet_template["三連複"],
        normal_bet_symbols,
    )

if len(wide_bets) < 2:
    wide_bets = make_bets_from_symbols(
        current_bet_template["ワイド"],
        normal_bet_symbols,
    )

if len(float_bets) < 1:
    float_bets = make_bets_from_symbols(
        current_bet_template["浮き輪"],
        normal_bet_symbols,
    )


if debug_mode:

    with st.expander(
        "🔤 買い目用アルファベット選出",
        expanded=False,
    ):

        st.write(
            "優先順位："
            "A → F → C → E → D → B → G → I"
        )

        st.write(
            f"軸タイプ：{kyakushoku_type}"
        )

        for symbol in alphabet_priority:

            if symbol not in required_symbols:
                continue

            normal_horse = normal_bet_symbols.get(
                symbol,
                "候補なし",
            )

            final_horse = final_bet_symbols.get(
                symbol,
                "候補なし",
            )

            st.write(
                f"{symbol}（"
                f"{alphabet_role_names[symbol]}"
                f"）｜通常：{normal_horse}"
                f"｜最終：{final_horse}"
            )

        st.caption(
            f"三連複記号："
            f"{current_bet_template['三連複']}\n\n"
            f"ワイド記号："
            f"{current_bet_template['ワイド']}\n\n"
            f"浮き輪記号："
            f"{current_bet_template['浮き輪']}"
        )

# ==================================================
# 最終表示
# ==================================================
st.subheader("おすすめの三連複 2点")

for bet in trio_bets:
    st.write(
        f"{bet[0]} - {bet[1]} - {bet[2]}"
    )

st.subheader("おすすめのワイド２点")

for bet in wide_bets:
    st.write(
        f"{bet[0]} - {bet[1]}"
    )

st.markdown("### 🛟 カッパの浮き輪保険")

for bet in float_bets:
    st.write(
        f"{bet[0]} - {bet[1]}"
    )

# ==================================================
# 📋 ChatGPT用コピー
#
# 予想ロジックには一切触れず、
# 最終的に決まった記号・買い目だけを
# ChatGPTへ貼り付けやすい形で出力する。
#
# st.code() の右上に出るコピーボタンから
# スマホでも一発コピー可能。
# ==================================================

def bet_to_numbers_text(bet):
    """買い目の馬名表示を、馬番だけのハイフン区切りへ変換する。"""
    return "-".join(
        str(get_num(horse_text))
        for horse_text in bet
    )


chatgpt_lines = [
    f"{race_date} {baba_name}{race_no}R",
    f"軸：{popular_horse_num}番",
    f"軸タイプ：{kyakushoku_type}",
    "",
    "【最終記号】",
]

# A〜Iのうち、実際に存在する記号だけ出力
for symbol in ["A", "B", "C", "D", "E", "F", "G", "I"]:
    horse_text = final_bet_symbols.get(symbol)

    if horse_text:
        role_name = alphabet_role_names.get(
            symbol,
            symbol
        )

        chatgpt_lines.append(
            f"{symbol}（{role_name}）="
            f"{get_num(horse_text)}番"
        )

chatgpt_lines.extend([
    "",
    "【買い目】",
])

for index, bet in enumerate(
    trio_bets,
    start=1
):
    chatgpt_lines.append(
        f"三連複{index}："
        f"{bet_to_numbers_text(bet)}"
    )

for index, bet in enumerate(
    wide_bets,
    start=1
):
    chatgpt_lines.append(
        f"ワイド{index}："
        f"{bet_to_numbers_text(bet)}"
    )

for index, bet in enumerate(
    float_bets,
    start=1
):
    label = (
        "浮き輪"
        if len(float_bets) == 1
        else f"浮き輪{index}"
    )

    chatgpt_lines.append(
        f"{label}："
        f"{bet_to_numbers_text(bet)}"
    )

chatgpt_text = "\n".join(
    chatgpt_lines
)

st.markdown("### 📋 ChatGPT用コピー")
st.caption(
    "右上のコピーボタンを押して、そのままChatGPTへ貼り付けてください。"
)

st.code(
    chatgpt_text,
    language=None
)


# ==================================================
# 📊 結果自動取得・回収率計算
#
# 出馬表URLの DebaTable を RaceMarkTable に置き換え、
# 同じ開催日・競馬場・R番号の公式結果ページを自動取得する。
#
# 予想ロジックには一切触れない。
# すでに確定した trio_bets / wide_bets / float_bets と
# 公式払戻を照合するだけ。
# ==================================================

def normalize_bet_numbers(bet):
    """買い目を馬番の昇順タプルへ変換する。"""
    return tuple(
        sorted(
            get_num(horse_text)
            for horse_text in bet
        )
    )


def yen_to_int(text):
    """1,400円 → 1400"""
    if not text:
        return None

    m = re.search(
        r"([\d,]+)\s*円",
        text,
    )

    if not m:
        return None

    return int(
        m.group(1).replace(",", "")
    )


def extract_race_result_and_payouts(result_soup):
    """
    NAR RaceMarkTable から
    ・1〜3着馬番
    ・ワイド3通りの払戻
    ・三連複の払戻
    を取得する。
    """

    # ------------------------------------------
    # 1〜3着
    # ------------------------------------------
    top3 = {}

    for row in result_soup.find_all("tr"):

        cells = [
            cell.get_text(
                " ",
                strip=True,
            )
            for cell in row.find_all(
                ["td", "th"]
            )
        ]

        # 成績表は
        # 着順 / 枠 / 馬番 / 馬名 ...
        if len(cells) < 4:
            continue

        if (
            cells[0] in {"1", "2", "3"}
            and cells[1].isdigit()
            and cells[2].isdigit()
        ):
            finish = int(cells[0])
            horse_no = int(cells[2])

            if finish not in top3:
                top3[finish] = horse_no

        if len(top3) == 3:
            break

    # ------------------------------------------
    # 払戻
    # ------------------------------------------
    result_text = result_soup.get_text(
        " ",
        strip=True,
    )

    wide_payouts = {}
    trio_payouts = {}

    # ワイドは通常3通り。
    # 「ワイド」から「三連複」までの区間だけを見る。
    wide_section_match = re.search(
        r"ワイド\s+(.*?)\s+三連複",
        result_text,
        flags=re.S,
    )

    if wide_section_match:

        wide_section = (
            wide_section_match.group(1)
        )

        for combo, payout in re.findall(
            r"(\d{1,2}\s*-\s*\d{1,2})"
            r"\s+([\d,]+)\s*円",
            wide_section,
        ):

            nums = tuple(
                sorted(
                    int(x)
                    for x in re.findall(
                        r"\d+",
                        combo,
                    )
                )
            )

            if len(nums) == 2:
                wide_payouts[nums] = int(
                    payout.replace(",", "")
                )

    # 三連複
    trio_match = re.search(
        r"三連複\s+"
        r"(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{1,2})"
        r"\s+([\d,]+)\s*円",
        result_text,
    )

    if trio_match:

        nums = tuple(
            sorted(
                int(x)
                for x in re.findall(
                    r"\d+",
                    trio_match.group(1),
                )
            )
        )

        if len(nums) == 3:
            trio_payouts[nums] = int(
                trio_match.group(2).replace(
                    ",",
                    "",
                )
            )

    return {
        "着順": top3,
        "ワイド払戻": wide_payouts,
        "三連複払戻": trio_payouts,
    }


st.markdown("### 📊 結果・回収率")

check_result = st.button(
    "🏁 結果を取得して回収率を計算"
)

if check_result:

    result_url = url.replace(
        "/DebaTable?",
        "/RaceMarkTable?",
    )

    # 万一URL形式が少し違う場合も対応
    if result_url == url:
        result_url = url.replace(
            "DebaTable",
            "RaceMarkTable",
        )

    try:
        result_response = requests.get(
            result_url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; KappaKeibaTool/1.0)"
                )
            },
        )

        result_response.raise_for_status()

        result_soup = BeautifulSoup(
            result_response.text,
            "html.parser",
        )

        result_data = (
            extract_race_result_and_payouts(
                result_soup
            )
        )

        top3 = result_data["着順"]
        wide_payouts = (
            result_data["ワイド払戻"]
        )
        trio_payouts = (
            result_data["三連複払戻"]
        )

        # 結果がまだ確定していない時
        if (
            len(top3) < 3
            or not wide_payouts
            or not trio_payouts
        ):
            st.warning(
                "まだ公式結果・払戻が確定していないか、"
                "結果ページを正常に読み取れませんでした。"
            )

            with st.expander(
                "取得状況を確認",
                expanded=False,
            ):
                st.write(
                    f"結果URL：{result_url}"
                )
                st.write(
                    f"1〜3着：{top3}"
                )
                st.write(
                    f"ワイド払戻："
                    f"{wide_payouts}"
                )
                st.write(
                    f"三連複払戻："
                    f"{trio_payouts}"
                )

        else:

            finish_order = [
                top3[1],
                top3[2],
                top3[3],
            ]

            st.success(
                "公式結果："
                f"{finish_order[0]} → "
                f"{finish_order[1]} → "
                f"{finish_order[2]}"
            )

            # --------------------------------------
            # 各買い目を照合
            # --------------------------------------
            total_return = 0
            ticket_rows = []

            for index, bet in enumerate(
                trio_bets,
                start=1,
            ):
                key = normalize_bet_numbers(
                    bet
                )

                payout = trio_payouts.get(
                    key,
                    0,
                )

                total_return += payout

                ticket_rows.append({
                    "券種": f"三連複{index}",
                    "買い目": "-".join(
                        str(x)
                        for x in key
                    ),
                    "的中": payout > 0,
                    "払戻": payout,
                })

            for index, bet in enumerate(
                wide_bets,
                start=1,
            ):
                key = normalize_bet_numbers(
                    bet
                )

                payout = wide_payouts.get(
                    key,
                    0,
                )

                total_return += payout

                ticket_rows.append({
                    "券種": f"ワイド{index}",
                    "買い目": "-".join(
                        str(x)
                        for x in key
                    ),
                    "的中": payout > 0,
                    "払戻": payout,
                })

            for index, bet in enumerate(
                float_bets,
                start=1,
            ):
                key = normalize_bet_numbers(
                    bet
                )

                payout = wide_payouts.get(
                    key,
                    0,
                )

                total_return += payout

                label = (
                    "浮き輪"
                    if len(float_bets) == 1
                    else f"浮き輪{index}"
                )

                ticket_rows.append({
                    "券種": label,
                    "買い目": "-".join(
                        str(x)
                        for x in key
                    ),
                    "的中": payout > 0,
                    "払戻": payout,
                })

            ticket_count = (
                len(trio_bets)
                + len(wide_bets)
                + len(float_bets)
            )

            investment = (
                ticket_count * 100
            )

            profit = (
                total_return - investment
            )

            recovery_rate = (
                total_return
                / investment
                * 100
                if investment > 0
                else 0.0
            )

            # --------------------------------------
            # 表示
            # --------------------------------------
            for row in ticket_rows:

                mark = (
                    "🎯"
                    if row["的中"]
                    else "❌"
                )

                payout_text = (
                    f"{row['払戻']:,}円"
                    if row["払戻"] > 0
                    else "0円"
                )

                st.write(
                    f"{mark} "
                    f"{row['券種']} "
                    f"{row['買い目']} "
                    f"｜{payout_text}"
                )

            st.markdown("---")

            col_a, col_b = st.columns(2)

            with col_a:
                st.metric(
                    "投資",
                    f"{investment:,}円",
                )

                st.metric(
                    "払戻",
                    f"{total_return:,}円",
                )

            with col_b:
                st.metric(
                    "収支",
                    f"{profit:+,}円",
                )

                st.metric(
                    "回収率",
                    f"{recovery_rate:.1f}%",
                )

            # ChatGPTへ貼る時にも使える簡易結果
            result_copy_lines = [
                f"{race_date} "
                f"{baba_name}{race_no}R",
                "公式結果："
                f"{finish_order[0]}-"
                f"{finish_order[1]}-"
                f"{finish_order[2]}",
                f"投資：{investment}円",
                f"払戻：{total_return}円",
                f"収支：{profit:+d}円",
                f"回収率："
                f"{recovery_rate:.1f}%",
            ]

            st.markdown(
                "#### 📋 検証結果コピー"
            )

            st.code(
                "\n".join(
                    result_copy_lines
                ),
                language=None,
            )

    except requests.RequestException as e:
        st.error(
            "公式結果ページの取得に失敗しました。"
        )

        st.caption(
            f"エラー：{e}"
        )

    except Exception as e:
        st.error(
            "結果の解析中にエラーが発生しました。"
        )

        st.caption(
            f"エラー：{e}"
        )


st.caption(
    "※買い目の一例です。最終判断はオッズや馬場を見て調整してください。"
)