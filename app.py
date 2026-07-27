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
def calc_time_pressure_response(horse):
    """
    タイム圧馬がいるレースで、
    強い流れに対応できる材料があるかを判定する。

    ① 前で戦って3着以内
    ② 後方から大きく押し上げて5着以内
    """

    flows = horse.get("通過順", [])
    finishes = horse.get("着順", [])

    front_success_count = 0
    strong_push_count = 0
    response_details = []

    check_count = min(
        len(flows),
        len(finishes)
    )

    for idx in range(check_count):
        flow = flows[idx]
        finish = finishes[idx]

        if len(flow) < 2:
            continue

        first = flow[0]
        last = flow[-1]

        # 前でしっかり戦った経験
        # 例：3-3-3-1、2-2-2-2
        front_success = (
            first <= 4
            and last <= 4
            and finish <= 3
        )

        # 後ろから前の集団へ強く取り付いた経験
        # 例：10-9-4-4
        strong_push = (
            first >= 7
            and last <= 4
            and first - last >= 4
            and finish <= 5
        )

        if front_success:
            front_success_count += 1

        if strong_push:
            strong_push_count += 1

        if front_success or strong_push:
            response_details.append({
                "通過順": flow,
                "着順": finish,
                "前成功": front_success,
                "強押し上げ": strong_push,
            })

    return {
        "前成功回数": front_success_count,
        "強押上回数": strong_push_count,
        "両方あり": (
            front_success_count >= 1
            and strong_push_count >= 1
        ),
        "詳細": response_details,
    }


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
    # 4角5番手以内から、着順が3つ以上落ちたレースを数える
    # 過去5走で2回以上なら踏ん張り不足
    # ==================================================

    fumbaribuso_count = 0
    fumbaribuso_details = []

    check_count = min(
        len(race_flows),
        len(finish_positions)
    )

    for idx in range(check_count):
        flow = race_flows[idx]
        finish = finish_positions[idx]

        if len(flow) < 2:
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
        if last <= 5 and goal_drop >= 3:
            reasons.append("4角→着順で失速")

        # ② 1角では4番手以内だったのに、
        # 4角までに4つ以上順位を落とした
        if first <= 4 and corner_drop >= 4:
            reasons.append("1角→4角で失速")

        # ③ 3角では4番手以内だったのに、
        # 4角で3つ以上順位を落とした
        if third <= 4 and late_corner_drop >= 3:
            reasons.append("3角→4角で失速")

        # 同じレースで複数条件に該当しても1回として数える
        if reasons:
            fumbaribuso_count += 1

            fumbaribuso_details.append({
                "通過順": flow,
                "着順": finish,
                "理由": reasons,
            })

    is_fumbaribuso = (
        fumbaribuso_count >= 2
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
            "元通過順": original_race_flows,
            "評価通過順": race_flows,
        })
    horses.append({
        "馬番": i,
        "馬名": horse,
        "取消除外": is_scratched,

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
# JRA転入馬の共通判定
#
# 地方で1回以上走っている元JRA馬は、
# 地方走だけで評価し、警告対象には入れない。
#
# 地方走がまだ0回の馬だけ、
# JRA転入馬として加点・警告の対象にする。
# ==================================================

JRA_TRACKS = set(JRA_PLACES)
LOCAL_TRACKS = set(LOCAL_PLACES)

# 地方未出走のJRA転入馬だけ保存
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

    # 地方で1回でも走っていれば警告対象外
    if local_result_count >= 1:
        continue

    past_places = {
        item.get("競馬場", "")
        for item in all_race_items
    }

    jra_horse_info_map[
        h["馬番"]
    ] = {
        "馬名": h["馬名"],
        "地方走数": local_result_count,
        "JRA競馬場": sorted(
            past_places & JRA_TRACKS
        ),
    }


# 地方未出走のJRA転入馬だけ
jra_horse_numbers = set(
    jra_horse_info_map.keys()
)

jra_count = len(
    jra_horse_numbers
)

jra_rate = (
    jra_count / len(horses)
    if horses
    else 0
)
# 踏ん張り不足の馬
fumbaribuso_horse_numbers = {
    h["馬番"]
    for h in horses
    if h.get("踏ん張り不足", False)
}

# 徐々垂れの馬
jojo_tare_horse_numbers = {
    h["馬番"]
    for h in horses
    if h.get("徐々垂れ", False)
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

    jra_transfer = (
        horse_no in jra_horse_numbers
    )
    if jra_transfer:
        for flow in horse["通過順"]:
            if len(flow) >= 2:
                first = flow[0]

                if first <= 4:
                    front_score += 35
                elif first <= 6:
                    front_score += 15
    # 直近の大失速は、
    # 前へ行ける能力自体は残しつつ信用だけ下げる
    heavy_collapse_front_penalty = round(
        120
        * horse.get(
            "直近大失速強度",
            0
        ),
        1
    )

    front_score -= heavy_collapse_front_penalty
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
        "大失速減点": heavy_collapse_front_penalty,
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
    horse_text = horse.get("取得テキスト", "")

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

    # 複数の失速があっても、
    # 地力全体を破壊しないよう最大260点
    applied_risk_penalty = min(
        risk_penalty,
        260
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
    # 望月騎手補正
    if "望月" in horse_text:
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

        # 能力とは別に管理した失速不安
        "失速減点": applied_risk_penalty,
        "失速詳細": risk_details,
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
        h.get("失速減点", 0) >= 100
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
# 最新走で大失速した馬
#
# 強度1.0＝最新走で大失速。
# ランキングには残すが、
# 次走の「先行代表」には選ばない。
# ==================================================

latest_heavy_collapse_horse_numbers = {
    h["馬番"]
    for h in horses
    if h.get(
        "直近大失速強度",
        0
    ) >= 1.0
}


# 決め手不足＋最新走大失速を
# 先行代表候補から除外
front_candidates_without_risk = [
    h for h in front_candidates
    if (
        h["馬番"]
        not in decisive_shortage_horse_numbers
        and h["馬番"]
        not in latest_heavy_collapse_horse_numbers
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
# 表示用の「長く脚」は、
# 先行気勢1位と踏ん張り不足の馬を外す
long_spurt_display_candidates = [
    h for h in long_spurt_candidates
    if (
        h["馬番"] != front_best["馬番"]
        and h["馬番"] not in fumbaribuso_horse_numbers
    )
]

# 先行気勢との重複より、
# 踏ん張り不足の除外を優先する
if not long_spurt_display_candidates:
    long_spurt_display_candidates = [
        h for h in long_spurt_candidates
        if h["馬番"] not in fumbaribuso_horse_numbers
    ]

# 全馬が踏ん張り不足だった場合だけ元候補へ戻す
if not long_spurt_display_candidates:
    long_spurt_display_candidates = long_spurt_candidates
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
                f"｜前経験減点 "
                f"-{h.get('前経験減点', 0)} "
                f"｜失速減点 "
                f"-{h.get('失速減点', 0)}"
            )

            st.caption(
                f"通過順：{h['通過順']}\n\n"
                f"着順：{finishes}\n\n"
                f"失速詳細："
                f"{h.get('失速詳細', [])}"
            )
        
if not long_spurt_candidates:
    st.error("長く脚の評価データが取れていません")
    st.stop()

long_best = long_spurt_display_candidates[0]
long_spurt_horse = f"{long_best['馬番']}番 {long_best['馬名']}"

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

valid_flow_count = strong_style["有効数"]

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
# 前団に付けたレースが複数ある馬
elif (
    strong_front_count >= 2
    and strong_avg_first <= 5
    and strong_front_count >= strong_push_count
):
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
# 展開馬用の同距離持ちタイム
#
# 今回と完全に同じ距離だけ使用する。
# 同距離馬が2頭未満なら時計による比較は行わない。
# ==================================================

tenkai_same_distance_time_map = {}

for h in horses:

    exact_times = []

    for item in h.get("距離付きタイム", []):

        if item.get("距離") != distance_num:
            continue

        try:
            minutes, seconds = item["タイム"].split(":")
            total_seconds = (
                int(minutes) * 60
                + float(seconds)
            )

            # 園田・姫路の競馬場差補正
            past_place = item.get("競馬場", "")

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

            exact_times.append(total_seconds)

        except (ValueError, TypeError):
            continue

    if exact_times:
        tenkai_same_distance_time_map[
            h["馬番"]
        ] = min(exact_times)


# 2頭以上いないと比較できない
if len(tenkai_same_distance_time_map) >= 2:

    fastest_same_distance_time_for_tenkai = min(
        tenkai_same_distance_time_map.values()
    )

else:
    fastest_same_distance_time_for_tenkai = None


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
    # 直近大失速は、
    # 展開が向いても信用しすぎない
    heavy_collapse_tenkai_penalty = round(
        280
        * horse.get(
            "直近大失速強度",
            0
        ),
        1
    )

    score -= heavy_collapse_tenkai_penalty
    # 展開馬の同距離ベストタイム
    # ==================================================
    # 距離延長・押し上げ型
    #
    # 1900m以上のレースで、
    # 今回より100〜400m短い距離から
    # 後方→前団まで大きく押し上げて好走した馬を評価する。
    #
    # 短距離の時計そのものは比較しない。
    # 「距離延長で追走が楽になれば力を出せるタイプ」
    # として展開評価だけで拾う。
    # ==================================================

    distance_extension_push_count = 0

    if distance_num >= 1900:

        for item in horse.get(
            "距離付きタイム",
            []
        ):

            past_distance = item.get(
                "距離",
                0
            )

            # 今回より100〜400m短い距離だけ
            if not (
                100
                <= distance_num - past_distance
                <= 400
            ):
                continue

            flow = item.get(
                "通過順",
                []
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

            # 後方から前団まで強く押し上げて好走
            if (
                first >= 6
                and last <= 4
                and first - last >= 4
                and finish <= 5
            ):
                distance_extension_push_count += 1


    distance_extension_push = (
        distance_extension_push_count >= 1
    )

    # 距離延長で力を出せそうな材料として加点
    if distance_extension_push:
        score += 120
    tenkai_best_time = (
        tenkai_same_distance_time_map.get(
            horse_no
        )
    )

    # 同距離馬が2頭以上いる場合だけ時計を比較する
    if fastest_same_distance_time_for_tenkai is not None:

        if tenkai_best_time is not None:

            diff = (
                tenkai_best_time
                - fastest_same_distance_time_for_tenkai
            )

            if diff >= 3.0:
                score -= 300
            elif diff >= 2.0:
                score -= 220
            elif diff >= 1.5:
                score -= 140
            elif diff >= 1.0:
                score -= 80

        else:
            # 同距離実績がなくても、
            # 距離延長で押し上げ能力を発揮できそうな馬は
            # 一律－180にはしない
            if distance_extension_push:
                score -= 60
            else:
                score -= 180

    # 同距離馬が1頭以下なら、
    # 全馬の時計評価を行わない
    # 着順が悪い馬は展開評価を少し下げる
    finishes = horse.get("着順", [])

    # 直近3走の好調度を展開評価へ60％反映
    recent_form_bonus, recent_results = calc_recent_form_bonus(
        finishes
    )

    tenkai_recent_bonus = round(
        recent_form_bonus * 0.60,
        1
    )

    score += tenkai_recent_bonus

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
        # 総合順位による加点は、
        # 最終総合ランキング確定後に反映する
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

    # 展開馬候補も、通過順だけで脚質傾向を判定する
    target_style = analyze_flow_style(
        race_flows
    )

    target_valid_count = target_style["有効数"]

    target_escape_count = (
        target_style["逃げ回数"]
    )

    target_front_count = (
        target_style["前団回数"]
    )

    target_front_sustain_count = (
        target_style["前団持続回数"]
    )

    target_middle_sustain_count = (
        target_style["中団持続回数"]
    )

    target_stable_count = (
        target_style["持続回数"]
    )

    target_push_count = (
        target_style["押し上げ回数"]
    )

    target_escape_rate = (
        target_style["逃げ率"]
    )

    target_push_rate = (
        target_style["押し上げ率"]
    )
    target_type = "展開待ち"

    # 逃げ
    if target_escape_rate >= 0.5:
        target_type = "逃げ"

    # 先行
    elif (
        target_front_count >= 2
        and avg_first <= 5
        and target_front_count >= target_push_count
    ):
        target_type = "先行"

    # 前団持続・中団持続をまとめて持続
    elif (
        target_stable_count >= 2
        and target_stable_count >= target_push_count
    ):
        target_type = "持続"

    # 差しは押し上げ経験が複数ある馬だけ
    elif target_push_count >= 2:
        target_type = "差し"

    # ==================================================
    # 裏側だけで持続の位置を使い分ける
    #
    # 点数は控えめにして、
    # タイム・着順・失速評価を上回らないようにする
    # ==================================================

    if kyakushoku_type == "逃げ":

        # 逃げ馬の後ろで流れに乗れる前団持続を優先
        score += (
            target_front_sustain_count * 45
        )

        score += (
            target_middle_sustain_count * 10
        )

    elif kyakushoku_type == "先行":

        score += (
            target_front_sustain_count * 30
        )

        score += (
            target_middle_sustain_count * 15
        )

    elif kyakushoku_type == "持続":

        # 軸馬自身が前団持続寄り
        if (
            strong_front_sustain_count
            >= strong_middle_sustain_count
        ):
            score += (
                target_front_sustain_count * 35
            )

            score += (
                target_middle_sustain_count * 15
            )

        # 軸馬自身が中団持続寄り
        else:
            score += (
                target_middle_sustain_count * 35
            )

            score += (
                target_front_sustain_count * 15
            )

    elif kyakushoku_type == "差し":

        # 差し軸には中団で流れに乗れる馬を少し評価
        score += (
            target_middle_sustain_count * 25
        )

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
        # 最終的な展開馬選出で使用する
        "候補脚質": target_type,
        "前団持続回数": target_front_sustain_count,
        "中団持続回数": target_middle_sustain_count,
        "大失速減点": heavy_collapse_tenkai_penalty,
        "距離延長押上型": distance_extension_push,
        "距離延長押上回数": distance_extension_push_count,
        "直近3走": recent_results,
        "直近ボーナス": tenkai_recent_bonus,
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
# ==================================================
# 決め手不足馬を展開候補から除外
#
# 大きく崩れなくても勝ち切る材料が乏しい馬は、
# 「今回展開が向く代表」には選ばない
# ==================================================

tenkai_candidates_without_decisive = [
    h for h in tenkai_candidates
    if h["馬番"]
    not in decisive_shortage_horse_numbers
]

# 候補が残る場合だけ差し替える
if tenkai_candidates_without_decisive:
    tenkai_candidates = (
        tenkai_candidates_without_decisive
    )
# ==================================================
# 三連複2点目用に、
# 画面の展開ランキング順を保存しておく
#
# 後でタイム圧などによって候補が絞られても、
# ここでの2位・3位・4位…を使用する
# ==================================================

tenkai_rank_for_trio = [
    {
        "馬番": h["馬番"],
        "馬名": h["馬名"],
    }
    for h in tenkai_candidates
]
if debug_mode:

    with st.expander(
        "🌊 展開ランキング",
        expanded=False
    ):

        st.write(
            f"軸タイプ：**{kyakushoku_type}** "
            f"｜前崩れ期待度："
            f"{front_collapse_score} "
            f"｜前圧：{front_pressure_count}"
        )

        for rank, h in enumerate(
            tenkai_candidates[:5],
            start=1
        ):

            time_diff_text = (
                round(h["タイム差"], 2)
                if h.get("タイム差")
                is not None
                else "なし"
            )

            st.write(
                f"{rank}位｜"
                f"{h['馬番']}番 {h['馬名']} "
                f"｜展開 "
                f"{round(h['スコア'], 1)} "
                f"｜脚質 "
                f"{h.get('候補脚質')} "
                f"｜平均 "
                f"{round(h['平均前半'], 1)}"
                f"→"
                f"{round(h['平均4角'], 1)} "
                f"｜タイム差 "
                f"{time_diff_text} "
                f"｜大失速 "
                f"-{h.get('大失速減点', 0)}"
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

# 総合力1位を裏側で判定
front_score_map = {h["馬番"]: h["スコア"] for h in front_candidates}
long_score_map = {h["馬番"]: h["スコア"] for h in long_spurt_candidates}

total_candidates = []

# ==================================================
# 総合力用の持ちタイム
# 各馬の上位2走平均を作り、その平均同士で比較する
# ==================================================

total_time_map = {}

for horse in horses:
    distance_times = horse.get("距離付きタイム", [])

    # 同距離実績がある馬は、同距離だけを使う
    same_distance_exists = any(
        item["距離"] == distance_num
        for item in distance_times
    )

    usable_times = []

    for item in distance_times:
        race_distance = item["距離"]

        if same_distance_exists:
            distance_ok = race_distance == distance_num

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
                    1600, 1700, 1800, 1870,
                    1900, 2000, 2100
                ]

            elif distance_num >= 1500:
                distance_ok = (
                    abs(race_distance - distance_num) <= 300
                )

            else:
                distance_ok = (
                    abs(race_distance - distance_num) <= 100
                )

        if not distance_ok:
            continue

        try:
            minutes, seconds = item["タイム"].split(":")
            total_seconds = (
                int(minutes) * 60
                + float(seconds)
            )

            # 園田・姫路の競馬場差補正
            past_place = item.get("競馬場", "")

            if baba_name == "園田" and past_place == "姫路":
                total_seconds += 5.0

            elif baba_name == "姫路" and past_place == "園田":
                total_seconds -= 5.0

            usable_times.append(total_seconds)

        except (ValueError, TypeError):
            continue

    if not usable_times:
        continue

    # 速い順に並べ、上位2走を使用する
    usable_times.sort()
    top_times = usable_times[:2]

    representative_time = (
        sum(top_times) / len(top_times)
    )

    total_time_map[horse["馬番"]] = {
        # 総合評価では上位2走平均を使用
        "代表タイム": representative_time,

        # タイム圧モードでは最速1走を使用
        "最速1走": top_times[0],

        "使用タイム": top_times,
        "使用数": len(top_times),
        "距離一致": same_distance_exists,
    }
# ==================================================
# 総合評価専用の同距離持ちタイム
#
# 今回1600mなら1600mだけ、
# 今回800mなら800mだけを使用する。
#
# この表は総合評価だけで使用し、
# タイム圧モードには影響させない。
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
# タイム圧モード
#
# 今回と完全に同じ距離の最速1走だけで比較する。
#
# 例：
# 今回1600m戦なら1600mだけ。
# 1400m・1800mなどはタイム圧判定には使わない。
#
# 同距離タイムを持つ馬が2頭以上いて、
# 1位が2位より1.6秒以上速い時だけ発動する。
#
# 普通のレースでは発動せず、
# 明らかに時計が抜けた馬がいる時だけ使う非常モード。
# ==================================================

time_pressure_mode = False

time_pressure_horse_no = None
time_pressure_horse_name = ""

time_pressure_fastest_time = None
time_pressure_second_time = None
time_pressure_gap = None

time_pressure_diff_map = {}

time_pressure_front_diff = None
time_pressure_tenkai_diff = None


original_front_no = (
    front_best["馬番"]
    if front_best
    else None
)

original_tenkai_no = (
    tenkai_best["馬番"]
    if tenkai_best
    else None
)
# ==================================================
# タイム圧専用
#
# 直近3走だけを見る。
# その3走の中に今回と完全に同じ距離があれば、
# その中の最速1走をタイム圧判定に使用する。
#
# 4走前・5走前の時計はタイム圧では完全に無視する。
# ==================================================

time_pressure_best_time_map = {}

for horse in horses:

    horse_no = horse["馬番"]

    # 最新走から直近3走だけ
    recent_three_pairs = horse.get(
        "距離付きタイム",
        []
    )[:3]

    for item in recent_three_pairs:

        # 今回と完全に同じ距離だけ
        if item.get("距離") != distance_num:
            continue

        try:
            minutes, seconds = (
                item["タイム"].split(":")
            )

            race_time = (
                int(minutes) * 60
                + float(seconds)
            )

            # 園田・姫路の競馬場差補正
            past_place = item.get(
                "競馬場",
                ""
            )

            if (
                baba_name == "園田"
                and past_place == "姫路"
            ):
                race_time += 5.0

            elif (
                baba_name == "姫路"
                and past_place == "園田"
            ):
                race_time -= 5.0

        except (ValueError, TypeError, AttributeError):
            continue

        current_best = (
            time_pressure_best_time_map.get(
                horse_no
            )
        )

        if (
            current_best is None
            or race_time < current_best
        ):
            time_pressure_best_time_map[
                horse_no
            ] = race_time
# 同距離の最速1走ランキング
time_pressure_ranking = sorted(
    [
        {
            "馬番": horse_no,
            "最速1走": race_time,
        }
        for horse_no, race_time
        in time_pressure_best_time_map.items()
    ],
    key=lambda x: x["最速1走"]
)


# 最速馬を保存
if time_pressure_ranking:

    time_pressure_fastest_time = (
        time_pressure_ranking[0]["最速1走"]
    )

    time_pressure_horse_no = (
        time_pressure_ranking[0]["馬番"]
    )

    # 各馬が最速馬から何秒遅いか
    time_pressure_diff_map = {
        data["馬番"]: round(
            data["最速1走"]
            - time_pressure_fastest_time,
            3
        )
        for data in time_pressure_ranking
    }

    # デバッグ確認用
    time_pressure_front_diff = (
        time_pressure_diff_map.get(
            original_front_no
        )
    )

    time_pressure_tenkai_diff = (
        time_pressure_diff_map.get(
            original_tenkai_no
        )
    )


# ==================================================
# 同距離タイム持ちが2頭以上いる時だけ判定
#
# 1位と2位が1.6秒以上離れていればタイム圧ON
# ==================================================

if len(time_pressure_ranking) >= 2:

    time_pressure_second_time = (
        time_pressure_ranking[1]["最速1走"]
    )

    time_pressure_gap = round(
        time_pressure_second_time
        - time_pressure_fastest_time,
        3
    )

    time_pressure_mode = (
        time_pressure_gap >= 1.6
    )

horse_data_map = {
    h["馬番"]: h
    for h in horses
}


if time_pressure_horse_no is not None:

    time_pressure_horse_name = (
        horse_data_map
        .get(time_pressure_horse_no, {})
        .get("馬名", "不明")
    )


# 全馬のタイム圧対応力
time_pressure_response_map = {
    h["馬番"]: calc_time_pressure_response(h)
    for h in horses
}
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
        horse_no in jra_horse_numbers
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

        # 同距離タイムが1走しかない馬は、
        # 一発だけ速かった可能性を考えて85％
        if time_info["使用数"] == 1:
            time_weight *= 0.85

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
    # 通過順と着順をセットで残す
    local_flow_finish_pairs = [
        (
            item.get("通過順", []),
            finish
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
            for _, finish
            in evaluation_flow_finish_pairs
        ][:5]

    else:

        use_local_evaluation = True

        evaluation_flow_finish_pairs = list(
            zip(flows, finishes)
        )

        evaluation_finishes = finishes[:5]

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
    # 吉村智洋騎手補正
    if "吉村" in horse_text and "智洋" in horse_text:
        total_score += 35
    # 望月洵輝騎手補正
    if "望月" in horse_text:
        total_score += 35
    # 地方実績を評価できる馬は、
    # JRA転入馬でも地方での垂れを減点する
    if use_local_evaluation:

        for flow, finish in (
            evaluation_flow_finish_pairs
        ):

            if len(flow) < 2:
                continue

            first = flow[0]
            last = flow[-1]

            # 逃げたのに大敗
            if (
                first <= 2
                and finish is not None
                and finish >= 7
            ):
                total_score -= 80
                debug_total_parts["減点"] -= 80

            # 前半から4角で大きく後退
            if (
                first <= 3
                and last - first >= 4
            ):
                total_score -= 60
                debug_total_parts["減点"] -= 60

            # 4角からゴールまでの順位落下
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

                debug_total_parts[
                    "減点"
                ] -= drop_penalty
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
        "内訳": debug_total_parts
    })

total_candidates = sorted(
    total_candidates,
    key=lambda x: x["総合スコア"],
    reverse=True
)
# ==================================================
# タイム圧モード時の最終候補整理
#
# 総合ランキングは変更しない。
# 展開馬・先行力の代表だけ消去法で選び直す。
# ==================================================

pressure_removed_front = []
pressure_removed_tenkai = []

if time_pressure_mode:

    # --------------------------------------------------
    # 先行力候補
    #
    # タイム圧馬本人、または
    # 「前成功＋強い押し上げ」の両方がある馬だけ残す。
    # --------------------------------------------------

    original_front_candidates = front_candidates[:]

    original_front_map = {
        h["馬番"]: h
        for h in original_front_candidates
    }

    pressure_front_candidates = []

    # タイム圧モードでは、
    # 元の前進気勢ランキングに入っていない馬も対象にする
    for horse in horses:
        horse_no = horse["馬番"]

        # 軸馬本人は相手候補にしない
        if horse_no == popular_horse_num:
            continue
        # 決め手不足馬は、
        # タイム圧モードでも先行代表へ戻さない
        if (
            horse_no
            in decisive_shortage_horse_numbers
        ):
            continue
        response = time_pressure_response_map.get(
            horse_no,
            {}
        )

        is_pressure_horse = (
            horse_no == time_pressure_horse_no
        )

        has_both_response = response.get(
            "両方あり",
            False
        )

        candidate_diff = (
            time_pressure_diff_map.get(
                horse_no
            )
        )

        # 最速馬本人は残す
        if is_pressure_horse:
            pass

        # タイム不明、または最速馬より1.0秒以上遅い馬は、
        # 前成功＋強押し上げの両方がなければ消す
        elif (
            candidate_diff is None
            or candidate_diff >= 1.0
        ):

            if not has_both_response:

                if horse_no in original_front_map:
                    pressure_removed_front.append(
                        horse_no
                    )

                continue

        # 1.0秒未満の馬は、
        # タイム圧へ対応できる範囲として候補に残す

        # 元の前進気勢候補にいる場合は、
        # そのスコアをそのまま使用
        candidate = original_front_map.get(
            horse_no
        )

        # 元の前進気勢ランキングにいない馬は、
        # タイム圧モードでも先行代表には新規追加しない
        if candidate is None:
            continue

        pressure_front_candidates.append(
            candidate
        )

    # 候補が残った場合だけ差し替える
    if pressure_front_candidates:
        front_candidates = sorted(
            pressure_front_candidates,
            key=lambda x: x["スコア"],
            reverse=True
        )

    front_best = front_candidates[0]

    front_horse = (
        f"{front_best['馬番']}番 "
        f"{front_best['馬名']}"
    )


    # 先行代表が変わったので、
    # 地力表示も重複しないように選び直す
    long_spurt_display_candidates = [
        h for h in long_spurt_candidates
        if (
            h["馬番"] != front_best["馬番"]
            and h["馬番"]
            not in fumbaribuso_horse_numbers
        )
    ]

    if not long_spurt_display_candidates:
        long_spurt_display_candidates = [
            h for h in long_spurt_candidates
            if h["馬番"]
            not in fumbaribuso_horse_numbers
        ]

    if not long_spurt_display_candidates:
        long_spurt_display_candidates = (
            long_spurt_candidates
        )

    long_best = (
        long_spurt_display_candidates[0]
    )

    long_spurt_horse = (
        f"{long_best['馬番']}番 "
        f"{long_best['馬名']}"
    )


    # --------------------------------------------------
    # 展開候補
    #
    # タイム圧馬本人は残す。
    #
    # その他は、
    # ・踏ん張り不足、徐々垂れ
    # ・前成功も強押し上げもない
    # ・地力マイナスで両対応もない
    # を除外する。
    # --------------------------------------------------

    pressure_tenkai_candidates = []

    for h in tenkai_candidates:
        horse_no = h["馬番"]

        horse_data = horse_data_map.get(
            horse_no,
            {}
        )

        response = time_pressure_response_map.get(
            horse_no,
            {}
        )

        front_success_count = response.get(
            "前成功回数",
            0
        )

        strong_push_count = response.get(
            "強押上回数",
            0
        )

        has_front_response = (
            front_success_count >= 1
        )

        has_push_response = (
            strong_push_count >= 1
        )

        has_both_response = (
            has_front_response
            and has_push_response
        )

        is_fumbaribuso = horse_data.get(
            "踏ん張り不足",
            False
        )

        # 徐々垂れ判定をまだ入れていなくても
        # .getなのでエラーにはならない
        is_jojo_tare = horse_data.get(
            "徐々垂れ",
            False
        )

        long_score = long_score_map.get(
            horse_no,
            0
        )

        remove_candidate = False

        candidate_diff = (
            time_pressure_diff_map.get(
                horse_no
            )
        )

        # 踏ん張り不足・徐々垂れは除外
        if is_fumbaribuso or is_jojo_tare:
            remove_candidate = True

        # タイム不明、または最速馬より1.0秒以上遅い場合は、
        # 前成功＋強押し上げの両方がなければ除外
        elif (
            candidate_diff is None
            or candidate_diff >= 1.0
        ):

            if not has_both_response:
                remove_candidate = True

        # 最速馬との差が1.0秒未満なら、
        # タイム圧へ対応可能な範囲として残す

        if remove_candidate:
            pressure_removed_tenkai.append(
                horse_no
            )
            continue

        pressure_tenkai_candidates.append(h)

    # 全馬消える場合は、元候補へ戻して暴走を防ぐ
    if pressure_tenkai_candidates:
        tenkai_candidates = sorted(
            pressure_tenkai_candidates,
            key=lambda x: x["スコア"],
            reverse=True
        )
# ==================================================
# タイム圧判定デバッグ
#
# 発動・未発動に関係なく、
# 判定に使った最速タイムと差を表示する
# ==================================================

# ==================================================
# タイム圧判定デバッグ
# ==================================================

if debug_mode:

    with st.expander(
        "⏱️ タイム圧判定",
        expanded=False
    ):

        st.write(
            f"発動状況："
            f"**{'ON' if time_pressure_mode else 'OFF'}**"
        )

        if time_pressure_horse_no is not None:

            st.write(
                f"最速馬："
                f"{time_pressure_horse_no}番 "
                f"{time_pressure_horse_name} "
                f"｜"
                f"{round(time_pressure_fastest_time, 2)}秒"
            )
            gap_text = (
                f"{time_pressure_gap}秒"
                if time_pressure_gap is not None
                else "比較不可"
            )

            st.write(
                f"同距離1位－2位差："
                f"**{gap_text}** "
                f"｜発動基準：1.6秒"
            )
            st.write(
                f"変更前の先行代表差："
                f"{time_pressure_front_diff}秒 "
                f"｜展開代表差："
                f"{time_pressure_tenkai_diff}秒"
            )

        st.markdown("#### 最速1走 上位5頭")

        for rank, data in enumerate(
            time_pressure_ranking[:5],
            start=1
        ):

            horse_no = data["馬番"]

            horse_name = (
                horse_data_map
                .get(horse_no, {})
                .get("馬名", "不明")
            )

            diff = time_pressure_diff_map.get(
                horse_no
            )

            st.write(
                f"{rank}位｜"
                f"{horse_no}番 {horse_name} "
                f"｜{round(data['最速1走'], 2)}秒 "
                f"｜差 {diff}秒"
            )

        if time_pressure_mode:

            st.write(
                f"先行候補から除外："
                f"{pressure_removed_front}"
            )

            st.write(
                f"展開候補から除外："
                f"{pressure_removed_tenkai}"
            )


    if time_pressure_mode:

        with st.expander(
            "🔍 タイム圧対応力の詳細",
            expanded=False
        ):

            for horse_no, response in (
                time_pressure_response_map.items()
            ):

                horse_diff = (
                    time_pressure_diff_map.get(
                        horse_no
                    )
                )

                st.write(
                    f"{horse_no}番 "
                    f"｜最速差 {horse_diff}秒 "
                    f"｜前成功 "
                    f"{response.get('前成功回数', 0)}回 "
                    f"｜押し上げ "
                    f"{response.get('強押上回数', 0)}回 "
                    f"｜両対応 "
                    f"{response.get('両方あり', False)}"
                )

                st.caption(
                    f"{response.get('詳細', [])}"
                )
# 最終総合ランキングを作る
final_total_rank_map = {
    h["馬番"]: rank
    for rank, h in enumerate(
        total_candidates,
        start=1
    )
}

# 最終総合順位を展開馬へ反映する
for h in tenkai_candidates:
    horse_no = h["馬番"]
    final_total_rank = final_total_rank_map.get(
        horse_no,
        99
    )

    final_total_bonus = 0

    # 最終総合3位以内だけ＋10
    if final_total_rank <= 3:
        final_total_bonus = 10

    h["スコア"] += final_total_bonus
    h["最終総合順位"] = final_total_rank
    h["最終総合加点"] = final_total_bonus

# 最終総合を反映して展開馬を並べ直す
tenkai_candidates = sorted(
    tenkai_candidates,
    key=lambda x: x["スコア"],
    reverse=True
)

# ==================================================
# 踏ん張り不足の馬は、
# 総合馬・展開馬の最終代表には選ばない
#
# 元のランキングには残すので、
# 前進気勢・地力・穴候補では使用できる
# ==================================================
# ==================================================
# 展開馬の最終候補
#
# 通常時：
# 踏ん張り不足・徐々垂れを除外する
#
# タイム圧モード時：
# タイム圧馬本人だけは、
# 踏ん張り不足・徐々垂れでも候補に残す
# ==================================================
if time_pressure_mode:

    tenkai_base_candidates = [
        h for h in tenkai_candidates
        if (
            # 最新走大失速は、
            # タイム圧でも展開代表には戻さない
            h["馬番"]
            not in latest_heavy_collapse_horse_numbers

            and h["馬番"]
            not in fumbaribuso_horse_numbers

            and h["馬番"]
            not in shissoku_heavy_horse_numbers

            # タイム圧馬本人は、
            # 徐々垂れだけなら救済
            and (
                h["馬番"] == time_pressure_horse_no
                or h["馬番"]
                not in jojo_tare_horse_numbers
            )
        )
    ]

else:

    tenkai_base_candidates = [
        h for h in tenkai_candidates
        if (
            h["馬番"]
            not in latest_heavy_collapse_horse_numbers

            and h["馬番"]
            not in fumbaribuso_horse_numbers

            and h["馬番"]
            not in jojo_tare_horse_numbers

            and h["馬番"]
            not in shissoku_heavy_horse_numbers
        )
    ]


# 候補が0頭になった場合は、
# 徐々垂れだけ戻す
if not tenkai_base_candidates:

    tenkai_base_candidates = [
        h for h in tenkai_candidates
        if (
            # 最新走大失速は戻さない
            h["馬番"]
            not in latest_heavy_collapse_horse_numbers

            and h["馬番"]
            not in fumbaribuso_horse_numbers

            and h["馬番"]
            not in shissoku_heavy_horse_numbers
        )
    ]


# それでも0頭なら、
# 総合上位から安全な馬を代用
if not tenkai_base_candidates:

    total_fallback = next(
        (
            h for h in total_candidates
            if (
                h["馬番"] != popular_horse_num

                and h["馬番"]
                not in latest_heavy_collapse_horse_numbers

                and h["馬番"]
                not in fumbaribuso_horse_numbers

                and h["馬番"]
                not in shissoku_heavy_horse_numbers
            )
        ),
        None
    )

    if total_fallback is not None:

        tenkai_base_candidates = [
            {
                "馬番": total_fallback["馬番"],
                "馬名": total_fallback["馬名"],
                "スコア": total_fallback["総合スコア"],
                "候補脚質": "総合代替",
            }
        ]

    else:

        st.warning(
            "⚠️ 直近大失速・踏ん張り不足ではない"
            "展開候補がいません。"
        )

        st.stop()
# ==================================================
# 軸タイプに合う脚質から展開馬を選ぶ
#
# 第一候補の脚質がいなければ第二候補、
# それもいなければ全候補へ戻す
# ==================================================

tenkai_type_priority = {
    "逃げ": ["逃げ", "先行"],
    "先行": ["先行", "持続"],
    "差し": ["差し", "持続"],
    "持続": ["持続", "差し"],
    "展開待ち": ["先行", "持続"],
}
tenkai_final_candidates = []
selected_target_type = "全候補"

# ==================================================
# タイム圧モード
#
# 持ちタイムが1.6秒以上抜けた馬がいる場合は、
# 軸馬との脚質相性を使わない。
#
# タイム圧対応条件を通過した馬を、
# 展開スコア順でそのまま採用する。
# ==================================================

if time_pressure_mode:

    tenkai_final_candidates = tenkai_base_candidates

    selected_target_type = "タイム圧対応"


# 通常レースだけ、従来の脚質相性を使う
else:

    preferred_types = tenkai_type_priority.get(
        kyakushoku_type,
        []
    )

    # ==================================================
    # 1900m以上＋前崩れ濃厚
    #
    # 通常の軸脚質相性に加えて、
    # 距離延長で押し上げ能力を発揮できそうな馬も
    # 展開代表候補として競わせる。
    # ==================================================

    if (
        distance_num >= 1900
        and front_collapse_score >= 70
    ):

        long_distance_candidates = [
            h
            for h in tenkai_base_candidates
            if (
                h.get("候補脚質")
                in preferred_types
                or h.get(
                    "距離延長押上型",
                    False
                )
            )
        ]

        if long_distance_candidates:

            tenkai_final_candidates = sorted(
                long_distance_candidates,
                key=lambda x: x["スコア"],
                reverse=True
            )

            selected_target_type = (
                "前崩れ＋距離延長"
            )

    # 通常時は今までどおり
    else:

        # 脚質補正は展開ランキング上位2頭まで
        top_tenkai_candidates = tenkai_base_candidates[:2]

        for preferred_type in preferred_types:

            same_type_candidates = [
                h
                for h in top_tenkai_candidates
                if h.get(
                    "候補脚質"
                ) == preferred_type
            ]

            if same_type_candidates:
                tenkai_final_candidates = (
                    same_type_candidates
                )

                selected_target_type = (
                    preferred_type
                )

                break


    # 条件に合う馬がいなければ全候補へ戻す
    if not tenkai_final_candidates:
        tenkai_final_candidates = (
            tenkai_base_candidates
        )


# 展開馬を最終決定
tenkai_best = tenkai_final_candidates[0]

tenkai_horse = (
    f"{tenkai_best['馬番']}番 "
    f"{tenkai_best['馬名']}"
)
# タイム圧馬本人は、
# 踏ん張り不足判定でも総合代表候補に残す

if time_pressure_mode:

    total_final_candidates = [
        h for h in total_candidates
        if (
            h["馬番"] not in shissoku_heavy_horse_numbers
            and (
                h["馬番"] == time_pressure_horse_no
                or h["馬番"] not in fumbaribuso_horse_numbers
            )
        )
    ]

else:

    total_final_candidates = [
        h for h in total_candidates
        if (
            h["馬番"] not in fumbaribuso_horse_numbers
            and h["馬番"] not in shissoku_heavy_horse_numbers
        )
    ]

# 全馬が対象になった場合のエラー回避
if not total_final_candidates:
    total_final_candidates = total_candidates

# 総合馬を最終決定
total_best = total_final_candidates[0]

total_best_horse = (
    f"{total_best['馬番']}番 "
    f"{total_best['馬名']}"
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

    if time_pressure_horse_no is not None:
        key_role_numbers.add(
            time_pressure_horse_no
        )

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
# 抑え候補を最終スコア順に並べ直す
#
# 展開候補や総合候補の元の並びではなく、
# 垂れ減点・距離補正などを反映した
# 最終ana_scoreで穴1〜5を決定する
# ==================================================

ana_candidates = sorted(
    ana_candidates,
    key=lambda x: (
        x.get(
            "同距離逃げ切り警戒",
            False
        ),
        x["スコア"],
    ),
    reverse=True
)
if debug_mode:
    st.subheader("押さえ候補スコア")
    for h in ana_candidates:
        st.write(
            f"{h['馬番']}番 {h['馬名']} "
            f"｜押さえスコア {round(h['スコア'], 1)}"
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

def add_unique_bet(bets, bet, max_count=2):
    nums = [get_num(h) for h in bet]

    # 斬り捨て御免馬を含む買い目は採用しない
    if any(
        num in kirisute_horse_numbers
        for num in nums
    ):
        return bets

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
# 三連複用：通常の先行馬
front_horse_for_trio = front_horse

if get_num(front_horse_for_trio) == popular_horse_num:
    front_horse_for_trio = long_spurt_horse


# 逃げ軸の三連複2点目用：
# 前進気勢ランキング2位を取得する
if len(front_candidates) >= 2:
    front_second = front_candidates[1]
else:
    # 候補が1頭しかいない場合は1位を使う
    front_second = front_candidates[0]

front_second_horse = (
    f"{front_second['馬番']}番 {front_second['馬名']}"
)
popular = f"{popular_horse_num}番 {real_horses[popular_horse_num - 1]}"
total_horse = total_best_horse
long_horse = long_spurt_horse
tenkai_horse_text = tenkai_horse

# 三連複は「軸馬から1点」「総合から1点」で独立して作る

def make_unique_trio(first, second, third, fallback_list):
    trio = [first, second, third]

    # まず従来の予備候補を使い、
    # 足りない時だけ総合順位から補う
    extended_fallbacks = list(fallback_list)

    for h in total_candidates:
        candidate = f"{h['馬番']}番 {h['馬名']}"

        if candidate not in extended_fallbacks:
            extended_fallbacks.append(candidate)

    used_nums = set()
    fixed = []

    for h in trio:
        n = get_num(h)

        # 重複せず、斬り捨て御免馬でもなければそのまま使う
        if (
            n not in used_nums
            and n not in kirisute_horse_numbers
        ):
            fixed.append(h)
            used_nums.add(n)
            continue

        replacement = None

        for fb in extended_fallbacks:
            fb_num = get_num(fb)

            if (
                fb_num not in used_nums
                and fb_num not in kirisute_horse_numbers
                and fb_num != popular_horse_num
            ):
                replacement = fb
                break

        if replacement:
            fixed.append(replacement)
            used_nums.add(
                get_num(replacement)
            )

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

    # 差し軸なら 軸－展開－穴3
    if kyakushoku_type == "差し":
        axis_third = ana_third_horse

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
        ana_second_horse,
        [
            long_horse,
            ana_horse,
            ana_third_horse,
            front_horse_for_trio,
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
# ==================================================
# 三連複2点目
#
# 基本：
# 軸 － 展開ランキング2位以降 － 穴2以降
#
# 1点目で使った相手馬は2点目では使わない。
#
# 穴側：
# 穴2 → 穴3 → 穴4 → 穴5 → 穴1
#
# 展開側：
# 展開2位 → 3位 → 4位 → 5位…
#
# これで2点の相手を入れ替えて
# 別シナリオを作る。
# ==================================================

second_trio = None

# 1点目で使用した馬番
first_trio_nums = set()

if axis_trio:
    first_trio_nums = {
        get_num(h)
        for h in axis_trio
    }


# ==================================================
# ① 2点目の穴馬を決める
#
# 穴2を最優先。
# 1点目で使っていたら穴3→穴4…へ送る
# ==================================================

second_hole_priority = [
    ana_second_horse,   # 穴2
    ana_third_horse,    # 穴3
    ana_fourth_horse,   # 穴4
    ana_fifth_horse,    # 穴5
    ana_horse,          # 穴1
]

second_trio_hole = None

for hole_horse in second_hole_priority:

    hole_num = get_num(
        hole_horse
    )

    # 軸馬は使わない
    if hole_num == popular_horse_num:
        continue

    # 1点目で使った馬は使わない
    if hole_num in first_trio_nums:
        continue

    # 斬り捨て御免馬は使わない
    if hole_num in kirisute_horse_numbers:
        continue

    second_trio_hole = hole_horse
    break


# ==================================================
# ② 展開ランキング上位から選ぶ
#
# 1点目で使った馬・穴馬とは被らせない
# 使っていない中で最上位の展開馬を使う
# ==================================================

tenkai_second_horse = None

for h in tenkai_rank_for_trio:

    horse_no = h["馬番"]

    # 軸馬
    if horse_no == popular_horse_num:
        continue

    # 1点目で使用済み
    if horse_no in first_trio_nums:
        continue

    # 斬り捨て御免馬
    if horse_no in kirisute_horse_numbers:
        continue

    # 今決めた穴馬と重複
    if (
        second_trio_hole is not None
        and horse_no
        == get_num(second_trio_hole)
    ):
        continue

    tenkai_second_horse = (
        f"{h['馬番']}番 "
        f"{h['馬名']}"
    )

    break


# ==================================================
# ③ 2点目を作る
# ==================================================

if (
    tenkai_second_horse is not None
    and second_trio_hole is not None
):

    second_trio = [
        popular,
        tenkai_second_horse,
        second_trio_hole,
    ]


if second_trio:

    trio_bets = add_unique_bet(
        trio_bets,
        second_trio,
        max_count=2
    )

# ==================================================
# 三連複 最終安全装置
#
# 通常ロジックで2点作れなかった場合だけ発動。
#
# ・斬り捨て馬は絶対使わない
# ・軸馬は必ず残す
# ・同じ3頭の組み合わせは作らない
# ・まず評価上位候補を使う
# ・それでも足りなければ全出走馬まで広げる
#
# これにより、斬り捨て御免を使っても
# 原則として三連複は必ず2点出す
# ==================================================

if len(trio_bets) < 2:

    # ------------------------------------------
    # 優先候補
    # ------------------------------------------

    if total_best["馬番"] == popular_horse_num:

        # 軸＝総合なら穴候補を優先
        trio_fallback_pool = [
            ana_second_horse,
            ana_third_horse,
            ana_fourth_horse,
            ana_fifth_horse,
            ana_horse,
            long_horse,
            tenkai_horse_text,
            front_horse_for_trio,
            front_second_horse,
        ]

    else:

        # 通常は地力・総合・展開を優先
        trio_fallback_pool = [
            long_horse,
            total_horse,
            tenkai_horse_text,
            ana_horse,
            ana_second_horse,
            ana_third_horse,
            ana_fourth_horse,
            ana_fifth_horse,
            front_horse_for_trio,
            front_second_horse,
        ]


    # ------------------------------------------
    # 総合ランキングから候補追加
    # ------------------------------------------

    for h in total_candidates:

        candidate = (
            f"{h['馬番']}番 {h['馬名']}"
        )

        if candidate not in trio_fallback_pool:
            trio_fallback_pool.append(candidate)


    # ------------------------------------------
    # 最終的には全出走馬まで候補を広げる
    # ------------------------------------------

    for h in horses:

        candidate = (
            f"{h['馬番']}番 {h['馬名']}"
        )

        if candidate not in trio_fallback_pool:
            trio_fallback_pool.append(candidate)


    # ------------------------------------------
    # 斬り捨て・軸重複・同一馬を整理
    # ------------------------------------------

    cleaned_trio_pool = []
    used_pool_nums = set()

    for horse_text in trio_fallback_pool:

        horse_num = get_num(horse_text)

        # 軸は後で固定して入れる
        if horse_num == popular_horse_num:
            continue

        # 斬り捨て馬は絶対使わない
        if horse_num in kirisute_horse_numbers:
            continue

        # 同じ馬を候補に重複登録しない
        if horse_num in used_pool_nums:
            continue

        cleaned_trio_pool.append(
            horse_text
        )

        used_pool_nums.add(
            horse_num
        )


    # ------------------------------------------
    # 軸＋残った2頭で組み合わせを総当たり
    # ------------------------------------------

    for i in range(
        len(cleaned_trio_pool)
    ):

        if len(trio_bets) >= 2:
            break

        for j in range(
            i + 1,
            len(cleaned_trio_pool)
        ):

            candidate_trio = [
                popular,
                cleaned_trio_pool[i],
                cleaned_trio_pool[j],
            ]

            trio_bets = add_unique_bet(
                trio_bets,
                candidate_trio,
                max_count=2
            )

            if len(trio_bets) >= 2:
                break


for bet in trio_bets:
    st.write(
        f"{bet[0]} - {bet[1]} - {bet[2]}"
    )
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

# ==================================================
# ワイド1点目
#
# 三連複2点が
# A-B-C / A-B-D の形なら、
# ワイド1点目は A－穴3位
# ==================================================

wide_patterns = []

same_two_horses_pattern = False

if len(trio_bets) >= 2:

    first_trio_nums = {
        get_num(h)
        for h in trio_bets[0]
    }

    second_trio_nums = {
        get_num(h)
        for h in trio_bets[1]
    }

    common_nums = (
        first_trio_nums
        & second_trio_nums
    )

    # 軸馬を含む2頭が共通なら
    # A-B-C / A-B-D型
    if (
        len(common_nums) == 2
        and popular_horse_num in common_nums
    ):
        same_two_horses_pattern = True


# A-B-C / A-B-D型
# → ワイド1点目は軸－穴3位
if same_two_horses_pattern:

    first_target = ana_third_horse

    # 軸と穴3位が被った場合の予備
    if get_num(popular) == get_num(first_target):
        first_target = ana_fourth_horse

    if get_num(popular) == get_num(first_target):
        first_target = ana_second_horse

    if get_num(popular) == get_num(first_target):
        first_target = ana_horse


# それ以外は従来どおり
else:

    # 持続軸は軸－地力
    if kyakushoku_type == "持続":
        first_target = long_horse

    else:
        first_target = tenkai_horse_text

    if get_num(popular) == get_num(first_target):
        first_target = long_horse

    if get_num(popular) == get_num(first_target):
        first_target = ana_horse

    if get_num(popular) == get_num(first_target):
        first_target = ana_second_horse

    if get_num(popular) == get_num(first_target):
        first_target = front_horse_for_trio


# ワイド1点目を追加
wide_patterns.append([
    popular,
    first_target,
])
# ==================================================
# ワイド2点目候補
#
# 脚質や「展開＝地力」による特殊処理は行わない。
# 軸－穴候補を優先する。
# ==================================================

wide_patterns += [
    [popular, ana_horse],
    [popular, ana_third_horse],
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

    # 浮き輪は総合－穴2を最優先にする
    # ただし、軸馬と総合馬が同じなら地力－穴2を最優先にする

    if get_num(total_horse) == get_num(popular):

        # 軸＝総合の場合
        float_patterns = [
            [long_horse, ana_second_horse],      # 地力－穴2
            [ana_horse, long_horse],             # 抑え1－地力
            [ana_horse, total_horse],            # 抑え1－総合
            [ana_horse, tenkai_horse_text],      # 抑え1－展開
        ]

    else:

        # 軸と総合が違う場合
        float_patterns = [
            [total_horse, ana_second_horse],     # 総合－穴2
            [long_horse, ana_second_horse],      # 地力－穴2
            [ana_horse, long_horse],             # 抑え1－地力
            [ana_horse, total_horse],            # 抑え1－総合
            [ana_horse, tenkai_horse_text],      # 抑え1－展開
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
    # ==================================================
    # それでも浮き輪が出ない場合
    #
    # 斬り捨て馬は絶対に使わず、
    # 残っている候補から別世界線を必ず1点作る
    # ==================================================

    if not float_bets:

        float_fallback_pool = [
            ana_second_horse,
            ana_third_horse,
            ana_fourth_horse,
            ana_fifth_horse,
            ana_horse,
            long_horse,
            total_horse,
            tenkai_horse_text,
            front_horse,
            front_second_horse,
        ]

        # 総合ランキングからも候補を補充
        for h in total_candidates:
            candidate = f"{h['馬番']}番 {h['馬名']}"

            if candidate not in float_fallback_pool:
                float_fallback_pool.append(candidate)

        # 斬り捨て馬・重複馬を除外
        cleaned_pool = []
        used_nums = set()

        for horse_text in float_fallback_pool:

            horse_num = get_num(horse_text)

            if horse_num in kirisute_horse_numbers:
                continue

            if horse_num in used_nums:
                continue

            cleaned_pool.append(horse_text)
            used_nums.add(horse_num)

        # ① まず軸馬＋本線中心馬を避ける
        strict_pool = [
            h for h in cleaned_pool
            if get_num(h) != popular_horse_num
            and h not in banned
        ]

        # ② 無ければ軸馬だけ避ける
        relaxed_pool = [
            h for h in cleaned_pool
            if get_num(h) != popular_horse_num
        ]

        # ③ 最終手段は斬っていない馬すべて
        float_pools = [
            strict_pool,
            relaxed_pool,
            cleaned_pool,
        ]

        for pool in float_pools:

            if float_bets:
                break

            for i in range(len(pool)):

                for j in range(i + 1, len(pool)):

                    pattern = [
                        pool[i],
                        pool[j],
                    ]

                    pattern_key = tuple(
                        sorted(
                            get_num(h)
                            for h in pattern
                        )
                    )

                    # 既存ワイドと同じ組み合わせは避ける
                    if pattern_key in wide_existing_keys:
                        continue

                    float_bets = add_unique_bet(
                        float_bets,
                        pattern,
                        max_count=1
                    )

                    if float_bets:
                        break

                if float_bets:
                    break

for bet in float_bets:
    st.write(f"{bet[0]} - {bet[1]}")

st.caption(
    "※買い目の一例です。最終判断はオッズや馬場を見て調整してください。"
)