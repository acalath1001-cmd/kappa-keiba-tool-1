import streamlit as st
import re
from urllib.parse import urlparse, parse_qs, urlencode
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

        elif current_distance == 1100:

            # 門別1100mなど。
            # 同距離1100mを中心に、1000〜1200mまでを近似帯として扱う。
            return (
                1000
                <= past_distance
                <= 1200
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



# ==================================================
# 🌊 展開馬専用・クラス補正
#
# 目的：
# 下級条件で積んだ「近況・前進・地力・共通TOP5」の点を、
# 今回クラスでもそのまま100％信用しすぎないようにする。
#
# 重要：
# ・総合Fには入れない
# ・地力Cには入れない
# ・先行Dには入れない
# ・抑えEにも入れない
# ・展開馬Bの候補スコアだけに使用する
#
# 今回よりかなり下のクラス中心なら、
# 近況・前進・地力・共通TOP5のプラス点だけを割り引く。
#
# 今回と同格以上を複数回経験していれば100％評価。
# ==================================================

CLASS_LETTER_BASE = {
    "A": 0,
    "B": 30,
    "C": 60,
}


def normalize_race_class_text(text):
    """
    全角のＡＢＣ・数字・ハイフンを半角へ寄せる。
    """
    if not text:
        return ""

    translation = str.maketrans(
        {
            "Ａ": "A",
            "Ｂ": "B",
            "Ｃ": "C",
            "０": "0",
            "１": "1",
            "２": "2",
            "３": "3",
            "４": "4",
            "５": "5",
            "６": "6",
            "７": "7",
            "８": "8",
            "９": "9",
            "－": "-",
            "ー": "-",
        }
    )

    return text.translate(
        translation
    )


def extract_race_class_from_text(text):
    """
    NARの表記から A1 / B5 / C1 / C12 などを拾う。

    例：
      入道雲特別Ｃ１－１ → C1
      Ｂ５組             → B5
      Ｃ１２組           → C12

    「C級セレクション」のように数字が無いものは
    無理に判定せずNoneにする。
    """
    normalized = normalize_race_class_text(
        text
    )

    match = re.search(
        r"(?<![A-Z0-9])"
        r"([ABC])"
        r"\s*"
        r"(\d{1,2})"
        r"(?:\s*-\s*\d{1,2})?",
        normalized,
    )

    if not match:
        return None

    letter = match.group(1)
    number = int(
        match.group(2)
    )

    return {
        "記号": letter,
        "番号": number,
        "表示": f"{letter}{number}",
    }


def extract_all_race_classes_from_text(text):
    """
    1頭分の出馬表テキストから、過去走クラスを表示順にすべて拾う。

    NARの出馬表は、
    「前走〜5走前の日付・距離」の行と
    「前走〜5走前のレース名（クラス）」の行が分かれている。

    そのため日付でテキストを分割してクラスを取ると、
    各過去走とクラスの列がずれてしまう。

    ここでは馬ごとのhorse_text全体から
    A1 / B5 / C2 などを表示順に抜き出し、
    過去走の1列目→2列目→…とそのまま対応させる。
    """
    if not text:
        return []

    normalized = normalize_race_class_text(
        text
    )

    matches = re.finditer(
        r"(?<![A-Z0-9])"
        r"([ABC])"
        r"\s*"
        r"(\d{1,2})"
        r"(?:\s*-\s*\d{1,2})?",
        normalized,
    )

    classes = []

    for match in matches:
        letter = match.group(1)
        number = int(
            match.group(2)
        )

        classes.append({
            "記号": letter,
            "番号": number,
            "表示": f"{letter}{number}",
        })

    return classes


def get_race_class_value(class_info):
    """
    数字が小さいほど強い値にする。

    A > B > C を大きな帯で分け、
    同じ記号内では数字が小さい方を強く扱う。

    例：
      B5  → 35
      C1  → 61
      C12 → 72

    値が小さいほど上位クラス。
    """
    if not class_info:
        return None

    letter = class_info.get(
        "記号"
    )

    number = class_info.get(
        "番号"
    )

    if (
        letter not in CLASS_LETTER_BASE
        or not isinstance(number, int)
    ):
        return None

    return (
        CLASS_LETTER_BASE[letter]
        + number
    )


def apply_positive_class_factor(
    score,
    factor,
):
    """
    クラス倍率はプラス点だけに適用する。

    マイナスの近況点まで0.6倍すると、
    下級で負けている馬の減点まで軽くなってしまうため、
    マイナス点はそのまま残す。
    """
    if score > 0:
        return round(
            score * factor,
            1,
        )

    return score


def calc_tenkai_class_adjustment(
    horse,
    current_class,
    current_distance=None,
):
    """
    展開馬Bだけに使うクラス補正。

    方針：
    ・下級戦で積んだプラス材料は従来どおり割り引く。
    ・今回と同格以上の経験があれば過剰に割り引かない。
    ・特に「今回より1段上」「2段以上上」の経験を明確に評価する。
    ・格上経験が今回と同距離ならさらに加点する。

    格上経験加点：
      1段上      +20
      2段以上上  +30
      格上＋同距離 +10
      最大 +40

    同格経験だけの場合：
      1回 +5
      2回以上 +10

    ※総合F・地力C・先行D・抑えEには使わない。
    """

    current_value = get_race_class_value(
        current_class
    )

    if current_value is None:
        return {
            "係数": 1.0,
            "経験加点": 0,
            "同格以上回数": 0,
            "格上回数": 0,
            "格上同距離回数": 0,
            "最上位クラス差": None,
            "平均クラス差": None,
            "過去クラス": [],
            "判定": "今回クラス判定なし",
        }

    class_records = []

    for item in horse.get(
        "距離付きタイム",
        []
    )[:5]:

        past_class = item.get(
            "クラス"
        )

        past_value = get_race_class_value(
            past_class
        )

        if past_value is None:
            continue

        class_records.append({
            "クラス": past_class,
            "値": past_value,
            "差": (
                past_value
                - current_value
            ),
            "距離": item.get(
                "距離"
            ),
            "着順": item.get(
                "着順"
            ),
        })

    # --------------------------------------------------
    # 基本倍率
    # --------------------------------------------------
    if class_records:

        recent_weights = [
            1.00,
            0.85,
            0.70,
            0.55,
            0.40,
        ]

        weighted_gap_sum = 0.0
        weight_sum = 0.0

        for idx, record in enumerate(
            class_records
        ):
            weight = (
                recent_weights[idx]
                if idx < len(recent_weights)
                else 0.40
            )

            weighted_gap_sum += (
                record["差"]
                * weight
            )
            weight_sum += weight

        average_gap = (
            weighted_gap_sum
            / weight_sum
            if weight_sum > 0
            else 0.0
        )

        if average_gap <= 1:
            factor = 1.00
            judgement = "ほぼ同格"

        elif average_gap <= 3:
            factor = 0.95
            judgement = "少し下級"

        elif average_gap <= 5:
            factor = 0.85
            judgement = "下級寄り"

        elif average_gap <= 9:
            factor = 0.70
            judgement = "明確な下級"

        else:
            factor = 0.60
            judgement = "大幅な下級"

    else:
        # クラスが取れない場合は能力点を落とさない。
        factor = 1.00
        average_gap = None
        judgement = "過去クラス判定なし"

    same_or_stronger_records = [
        record
        for record in class_records
        if record["差"] <= 0
    ]

    stronger_records = [
        record
        for record in class_records
        if record["差"] < 0
    ]

    same_class_records = [
        record
        for record in class_records
        if record["差"] == 0
    ]

    same_or_stronger_count = len(
        same_or_stronger_records
    )

    stronger_count = len(
        stronger_records
    )

    # 同格以上経験がある馬は、
    # 下級戦が混ざっていても倍率を落としすぎない。
    if same_or_stronger_count >= 2:
        factor = 1.00

    elif same_or_stronger_count == 1:
        factor = max(
            factor,
            0.90,
        )

    best_class_gap = (
        min(
            record["差"]
            for record in class_records
        )
        if class_records
        else None
    )

    # --------------------------------------------------
    # 格上経験を展開Bへ明確に加点
    # --------------------------------------------------
    experience_bonus = 0
    experience_reasons = []

    if best_class_gap is not None:

        if best_class_gap <= -2:
            experience_bonus = 30
            experience_reasons.append(
                "2段以上上のクラス経験"
            )

        elif best_class_gap == -1:
            experience_bonus = 20
            experience_reasons.append(
                "1段上のクラス経験"
            )

        elif same_class_records:
            experience_bonus = (
                10
                if len(same_class_records) >= 2
                else 5
            )
            experience_reasons.append(
                "同格経験"
            )

    stronger_same_distance_count = 0

    if current_distance is not None:
        stronger_same_distance_count = sum(
            1
            for record in stronger_records
            if record.get("距離")
                == current_distance
        )

    if stronger_same_distance_count >= 1:
        experience_bonus += 10
        experience_reasons.append(
            "格上＋今回同距離"
        )

    experience_bonus = min(
        experience_bonus,
        40,
    )

    if experience_reasons:
        judgement += (
            "＋"
            + "・".join(
                experience_reasons
            )
        )

    return {
        "係数": round(
            factor,
            2,
        ),
        "経験加点": experience_bonus,
        "同格以上回数": (
            same_or_stronger_count
        ),
        "格上回数": stronger_count,
        "格上同距離回数": (
            stronger_same_distance_count
        ),
        "最上位クラス差": (
            best_class_gap
        ),
        "平均クラス差": (
            round(average_gap, 2)
            if average_gap is not None
            else None
        ),
        "過去クラス": [
            record["クラス"].get(
                "表示",
                ""
            )
            for record in class_records
        ],
        "判定": judgement,
    }


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

# 既存の競馬場コードを入口画面でも共通利用する。
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

st.title("🐎 地方競馬AI")

# ==================================================
# 全R一括検証用の内部状態
# ※通常分析のUIやURLは触らない
# ==================================================
if "batch_mode" not in st.session_state:
    st.session_state.batch_mode = False
if "batch_race_no" not in st.session_state:
    st.session_state.batch_race_no = 1
if "batch_last_race" not in st.session_state:
    st.session_state.batch_last_race = 12
if "batch_results" not in st.session_state:
    st.session_state.batch_results = []
if "batch_date" not in st.session_state:
    st.session_state.batch_date = ""
if "batch_baba_code" not in st.session_state:
    st.session_state.batch_baba_code = ""

# 一括検証の軸モード
# favorite = NAR1番人気軸
# backfill = 通常分析で出た後詰めFを軸にして再計算
if "batch_axis_mode" not in st.session_state:
    st.session_state.batch_axis_mode = "favorite"

# 後詰め軸モードは1レースを2段階で処理する。
# 1回目：NAR1番人気をAにして通常分析 → Fを確定
# 2回目：そのFを新しいAにして買い目を再計算
if "batch_axis_override_num" not in st.session_state:
    st.session_state.batch_axis_override_num = None

if "batch_axis_override_race" not in st.session_state:
    st.session_state.batch_axis_override_race = None

if "batch_original_a" not in st.session_state:
    st.session_state.batch_original_a = None

if "batch_original_f" not in st.session_state:
    st.session_state.batch_original_f = None

if "batch_af_match" not in st.session_state:
    st.session_state.batch_af_match = None


# ==================================================
# 全R一括検証 共通UI / 集計ヘルパー
# 新馬戦などで分析を途中終了する場合でも、
# 一括検証ボタンと回収率結果を表示できるようにする。
# ==================================================
def reset_batch_axis_temp_state():
    st.session_state.batch_axis_override_num = None
    st.session_state.batch_axis_override_race = None
    st.session_state.batch_original_a = None
    st.session_state.batch_original_f = None
    st.session_state.batch_af_match = None


def start_batch_validation_for_url(
    source_url,
    last_race,
    axis_mode,
):
    batch_query = urlparse(source_url).query
    batch_params = parse_qs(batch_query)

    batch_date = batch_params.get(
        "k_raceDate",
        [""],
    )[0]

    batch_baba_code = batch_params.get(
        "k_babaCode",
        [""],
    )[0]

    if not batch_date or not batch_baba_code:
        st.error(
            "出馬表URLから開催日または競馬場コードを取得できません。"
        )
        return

    st.session_state.batch_mode = True
    st.session_state.batch_axis_mode = axis_mode
    st.session_state.batch_race_no = 1
    st.session_state.batch_last_race = int(last_race)
    st.session_state.batch_results = []
    st.session_state.batch_date = batch_date
    st.session_state.batch_baba_code = batch_baba_code

    reset_batch_axis_temp_state()

    st.session_state.analyzed = True
    st.rerun()


def render_batch_results_summary():
    if not (
        st.session_state.get("batch_results")
        and not st.session_state.get("batch_mode", False)
    ):
        return

    completed_batch_results = [
        r
        for r in st.session_state.batch_results
        if r.get("状態") in {"完了", "対象外"}
    ]

    total_batch_investment = sum(
        r.get("投資", 0)
        for r in completed_batch_results
    )

    total_batch_return = sum(
        r.get("払戻", 0)
        for r in completed_batch_results
    )

    total_batch_profit = (
        total_batch_return
        - total_batch_investment
    )

    total_batch_rate = (
        total_batch_return
        / total_batch_investment
        * 100
        if total_batch_investment > 0
        else 0.0
    )

    st.markdown("### 📈 全R一括検証結果")

    total_col1, total_col2 = st.columns(2)

    with total_col1:
        st.metric(
            "総投資",
            f"{total_batch_investment:,}円",
        )
        st.metric(
            "総払戻",
            f"{total_batch_return:,}円",
        )

    with total_col2:
        st.metric(
            "総収支",
            f"{total_batch_profit:+,}円",
        )
        st.metric(
            "全体回収率",
            f"{total_batch_rate:.1f}%",
        )

    batch_copy_lines = [
        "【全R一括検証】",
    ]

    for r in sorted(
        completed_batch_results,
        key=lambda x: x["R"],
    ):
        if r.get("状態") == "対象外":
            batch_copy_lines.append(
                f"{r['R']}R｜"
                f"新馬戦・対象外｜"
                f"投資0円｜"
                f"払戻0円｜"
                f"回収率0.0%"
            )
        elif r.get("検証モード") == "backfill":
            batch_copy_lines.append(
                f"{r['R']}R｜"
                f"後詰め軸{r['軸']}番 "
                f"{r['軸タイプ']}｜"
                f"1番人気A{r.get('元A')}番｜"
                f"後詰めF{r.get('元F')}番｜"
                f"A-F"
                f"{'一致' if r.get('AF一致') else '不一致'}｜"
                f"結果{r['結果']}｜"
                f"払戻{r['払戻']:,}円｜"
                f"回収率{r['回収率']:.1f}%"
            )
        else:
            batch_copy_lines.append(
                f"{r['R']}R｜"
                f"軸{r['軸']}番 "
                f"{r['軸タイプ']}｜"
                f"結果{r['結果']}｜"
                f"払戻{r['払戻']:,}円｜"
                f"回収率{r['回収率']:.1f}%"
            )

    batch_copy_lines.extend([
        "",
        f"総投資：{total_batch_investment:,}円",
        f"総払戻：{total_batch_return:,}円",
        f"総収支：{total_batch_profit:+,}円",
        f"全体回収率：{total_batch_rate:.1f}%",
    ])

    st.markdown("### 📋 全R結果をコピー")
    st.code(
        "\n".join(batch_copy_lines),
        language=None,
    )

    if st.button(
        "🗑 一括検証結果をクリア",
        key="clear_batch_results_shared",
    ):
        st.session_state.batch_results = []
        st.rerun()


def render_batch_controls(source_url, key_suffix):
    st.markdown("---")
    st.markdown("## 🏇 全R一括検証")

    st.caption(
        "現在入力している出馬表URLの開催日・競馬場を使い、"
        "1Rから最終Rまで自動検証します。"
    )

    batch_last_race_input = st.number_input(
        "一括検証の最終R",
        min_value=1,
        max_value=12,
        value=12,
        step=1,
        key=f"batch_last_race_input_{key_suffix}",
    )

    batch_button_col1, batch_button_col2 = st.columns(2)

    with batch_button_col1:
        start_batch = st.button(
            "🚀 1番人気軸で全R一括検証",
            use_container_width=True,
            key=f"start_batch_{key_suffix}",
        )

    with batch_button_col2:
        start_backfill_batch = st.button(
            "⚔️ 後詰め馬軸で全R一括検証",
            use_container_width=True,
            key=f"start_backfill_batch_{key_suffix}",
        )

    if start_batch:
        start_batch_validation_for_url(
            source_url,
            batch_last_race_input,
            "favorite",
        )

    if start_backfill_batch:
        start_batch_validation_for_url(
            source_url,
            batch_last_race_input,
            "backfill",
        )

    render_batch_results_summary()


if "race_url" not in st.session_state:
    st.session_state.race_url = ""

if "race_url_input" not in st.session_state:
    st.session_state.race_url_input = (
        st.session_state.race_url
    )

if "analyzed" not in st.session_state:
    st.session_state.analyzed = False

if "race_nav_message" not in st.session_state:
    st.session_state.race_nav_message = ""


# ==================================================
# 通常分析用・一括検証状態リセット
# ==================================================
def reset_normal_analysis_state():
    st.session_state.batch_mode = False
    st.session_state.batch_race_no = 1
    st.session_state.batch_axis_mode = "favorite"
    st.session_state.batch_axis_override_num = None
    st.session_state.batch_axis_override_race = None
    st.session_state.batch_original_a = None
    st.session_state.batch_original_f = None
    st.session_state.batch_af_match = None


# ==================================================
# URLから現在のレース番号を取得
# ==================================================
def get_race_no_from_url(source_url):
    if not source_url:
        return None

    try:
        parsed = urlparse(
            source_url.strip()
        )

        params = parse_qs(
            parsed.query
        )

        race_no_value = params.get(
            "k_raceNo",
            [None]
        )[0]

        if race_no_value is None:
            return None

        return int(race_no_value)

    except (
        ValueError,
        TypeError,
        AttributeError,
    ):
        return None


# ==================================================
# URLのレース番号を前後へ変更
# ==================================================
def make_race_url(
    source_url,
    move,
):
    if not source_url:
        return (
            None,
            None,
            "出馬表URLを入力してください"
        )

    try:
        parsed = urlparse(
            source_url.strip()
        )

        params = parse_qs(
            parsed.query,
            keep_blank_values=True
        )

        if "k_raceNo" not in params:
            return (
                None,
                None,
                "URLからレース番号を取得できません"
            )

        current_race = int(
            params["k_raceNo"][0]
        )

        new_race = (
            current_race
            + move
        )

        if new_race < 1:
            return (
                None,
                current_race,
                "1Rより前には移動できません"
            )

        if new_race > 12:
            return (
                None,
                current_race,
                "12Rより先には移動できません"
            )

        params["k_raceNo"] = [
            str(new_race)
        ]

        new_query = urlencode(
            params,
            doseq=True
        )

        new_url = parsed._replace(
            query=new_query
        ).geturl()

        return (
            new_url,
            new_race,
            ""
        )

    except (
        ValueError,
        TypeError,
        AttributeError,
    ):
        return (
            None,
            None,
            "URLの変更に失敗しました"
        )


# ==================================================
# 通常の「分析開始」
# ==================================================
def start_normal_analysis():
    current_url = (
        st.session_state
        .race_url_input
        .strip()
    )

    if not current_url:
        st.session_state.race_nav_message = (
            "出馬表URLを入力してください"
        )
        st.session_state.analyzed = False
        return

    st.session_state.race_url = (
        current_url
    )

    st.session_state.race_nav_message = ""

    reset_normal_analysis_state()

    st.session_state.analyzed = True


# ==================================================
# 前のR / 次のR
#
# ボタンを押す
# ↓
# URLのk_raceNoを変更
# ↓
# そのまま自動分析
# ==================================================
def move_race(move):
    current_url = (
        st.session_state
        .race_url_input
        .strip()
    )

    (
        new_url,
        new_race,
        message,
    ) = make_race_url(
        current_url,
        move,
    )

    if not new_url:
        st.session_state.race_nav_message = (
            message
        )
        return

    st.session_state.race_url_input = (
        new_url
    )

    st.session_state.race_url = (
        new_url
    )

    if move > 0:
        st.session_state.race_nav_message = (
            f"➡ {new_race}Rへ移動しました"
        )
    else:
        st.session_state.race_nav_message = (
            f"⬅ {new_race}Rへ移動しました"
        )

    # 一括検証中だった場合は通常分析へ戻す
    reset_normal_analysis_state()

    # 前R・次Rボタンだけで自動分析
    st.session_state.analyzed = True


# ==================================================
# URL削除
# ==================================================
def clear_race_url():
    st.session_state.race_url = ""
    st.session_state.race_url_input = ""
    st.session_state.analyzed = False
    st.session_state.race_nav_message = ""

    reset_normal_analysis_state()


# ==================================================
# 本日の開催会場・レース選択
#
# NAR公式「本日のレース」表だけを対象に、
# 当日の競馬場コードと実在するレース番号を取得する。
# 前日・翌日以降の開催場や重賞競走のリンクは参照しない。
#
# 終了済み判定は時刻の推測ではなく、
# NAR側の各Rリンクが「競走成績 RaceMarkTable」に
# 切り替わっているかで判定する。
# 取得失敗時は例外を入口内で受け止め、従来のURL入力へ進む。
# ==================================================
@st.cache_data(ttl=60, show_spinner=False)
def get_today_race_schedule(race_date):
    import requests
    from bs4 import BeautifulSoup

    response = requests.get(
        (
            "https://www.keiba.go.jp/KeibaWeb/"
            "TodayRaceInfo/TodayRaceInfoTop"
        ),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; "
                "KappaKeibaTool/1.0)"
            )
        },
        timeout=10,
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.content,
        "html.parser",
    )

    # ページ下部には前日・翌日以降の開催場や重賞リンクもあるため、
    # 「本日のレース」の表だけに取得範囲を限定する。
    race_table = soup.select_one(
        "article.todayRace table.today"
    )

    if race_table is None:
        raise ValueError(
            "NAR公式の本日のレース表を取得できませんでした"
        )

    schedule = {}
    finished_races = {}

    for row in race_table.select("tbody tr"):
        venue_link = row.select_one(
            'a[href*="/TodayRaceInfo/RaceList"]'
        )

        if venue_link is None:
            continue

        venue_params = parse_qs(
            urlparse(
                venue_link.get("href", "")
            ).query
        )

        venue_date = venue_params.get(
            "k_raceDate",
            [None],
        )[0]
        baba_code = venue_params.get(
            "k_babaCode",
            [None],
        )[0]

        # NAR側のURLに入っている日付が、日本時間の今日と
        # 完全一致する行だけを採用する。
        if (
            venue_date != race_date
            or baba_code not in keibajo
        ):
            continue

        race_numbers = set()
        venue_finished_races = set()

        # 当日表の各レースボタンに設定されたURLから、
        # k_raceDate・k_babaCode・k_raceNoを一組で取得する。
        # RaceMarkTableへ切り替わったRは「終了済み」として保持する。
        for button in row.select("button[onclick]"):
            onclick = button.get("onclick", "")
            url_match = re.search(
                r"location\.href\s*=\s*['\"]([^'\"]+)['\"]",
                onclick,
            )

            if url_match is None:
                continue

            race_url = url_match.group(1)
            race_path = urlparse(race_url).path

            if not race_path.endswith((
                "/DebaTable",
                "/RaceMarkTable",
            )):
                continue

            race_params = parse_qs(
                urlparse(race_url).query
            )

            race_date_value = race_params.get(
                "k_raceDate",
                [None],
            )[0]
            race_baba_code = race_params.get(
                "k_babaCode",
                [None],
            )[0]
            race_no_value = race_params.get(
                "k_raceNo",
                [None],
            )[0]

            if (
                race_date_value != race_date
                or race_baba_code != baba_code
                or race_no_value is None
            ):
                continue

            try:
                race_no_value = int(race_no_value)
            except (TypeError, ValueError):
                continue

            if 1 <= race_no_value <= 12:
                race_numbers.add(race_no_value)

                if race_path.endswith("/RaceMarkTable"):
                    venue_finished_races.add(
                        race_no_value
                    )

        if race_numbers:
            schedule[baba_code] = race_numbers
            finished_races[baba_code] = (
                venue_finished_races
            )

    if not schedule:
        raise ValueError(
            f"{race_date}の開催情報を取得できませんでした"
        )

    sorted_schedule = {
        baba_code: sorted(race_numbers)
        for baba_code, race_numbers in schedule.items()
    }

    sorted_finished_races = {
        baba_code: sorted(race_numbers)
        for baba_code, race_numbers in finished_races.items()
    }

    return sorted_schedule, sorted_finished_races


@st.cache_data(ttl=30, show_spinner=False)
def get_current_first_favorite_from_win_odds(
    race_date_value,
    baba_code,
    race_no_value,
):
    """
    NAR公式の単勝・複勝オッズから、現在の単勝1番人気を取得する。

    オッズ未発表・取得失敗時は None を返す。
    予想ロジックには使わず、入口で軸馬の初期値を自動セットするためだけに使う。
    """
    import requests
    from bs4 import BeautifulSoup

    try:
        odds_url = (
            "https://www.keiba.go.jp/KeibaWeb/"
            "TodayRaceInfo/OddsTanFuku"
        )

        response = requests.get(
            odds_url,
            params={
                "k_raceDate": race_date_value,
                "k_raceNo": int(race_no_value),
                "k_babaCode": baba_code,
                # 人気順。NAR側で人気列が表示されるため、
                # 1番人気を直接拾いやすくする。
                "odds_flg": 5,
            },
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; "
                    "KappaKeibaTool/1.0)"
                )
            },
            timeout=8,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.content,
            "html.parser",
        )

        # --------------------------------------------------
        # 1) 人気列がある表なら「人気=1」を直接取得
        # 2) 人気列が取れない場合は単勝オッズ最小をフォールバック
        # --------------------------------------------------
        fallback_candidates = []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            header_map = None

            for row_index, row in enumerate(rows):
                header_cells = row.find_all(["th", "td"])
                header_texts = [
                    re.sub(
                        r"\s+",
                        "",
                        cell.get_text(" ", strip=True),
                    )
                    for cell in header_cells
                ]

                horse_no_index = next(
                    (
                        i
                        for i, value in enumerate(header_texts)
                        if value == "馬番"
                    ),
                    None,
                )
                win_odds_index = next(
                    (
                        i
                        for i, value in enumerate(header_texts)
                        if "単勝" in value
                        and "オッズ" in value
                    ),
                    None,
                )
                popularity_index = next(
                    (
                        i
                        for i, value in enumerate(header_texts)
                        if value == "人気"
                    ),
                    None,
                )

                if (
                    horse_no_index is not None
                    and win_odds_index is not None
                ):
                    header_map = {
                        "row_index": row_index,
                        "馬番": horse_no_index,
                        "単勝": win_odds_index,
                        "人気": popularity_index,
                    }
                    break

            if header_map is None:
                continue

            for row in rows[header_map["row_index"] + 1:]:
                cells = row.find_all(["td", "th"])
                texts = [
                    re.sub(
                        r"\s+",
                        "",
                        cell.get_text(" ", strip=True),
                    )
                    for cell in cells
                ]

                required_index = max(
                    header_map["馬番"],
                    header_map["単勝"],
                    header_map["人気"]
                    if header_map["人気"] is not None
                    else 0,
                )

                if len(texts) <= required_index:
                    continue

                try:
                    horse_no = int(
                        re.sub(
                            r"[^0-9]",
                            "",
                            texts[header_map["馬番"]],
                        )
                    )
                except (TypeError, ValueError):
                    continue

                win_odds_text = texts[
                    header_map["単勝"]
                ].replace(",", "")

                odds_match = re.search(
                    r"\d+(?:\.\d+)?",
                    win_odds_text,
                )
                if odds_match is None:
                    continue

                try:
                    win_odds = float(
                        odds_match.group(0)
                    )
                except ValueError:
                    continue

                if win_odds <= 0:
                    continue

                popularity_index = header_map["人気"]
                if popularity_index is not None:
                    popularity_match = re.search(
                        r"\d+",
                        texts[popularity_index],
                    )
                    if (
                        popularity_match is not None
                        and int(popularity_match.group(0)) == 1
                    ):
                        return {
                            "馬番": horse_no,
                            "単勝": win_odds,
                            "取得方法": "人気1位",
                        }

                fallback_candidates.append(
                    (win_odds, horse_no)
                )

        if fallback_candidates:
            win_odds, horse_no = min(
                fallback_candidates,
                key=lambda item: (item[0], item[1]),
            )
            return {
                "馬番": horse_no,
                "単勝": win_odds,
                "取得方法": "単勝最小",
            }

        return None

    except Exception:
        return None


def select_today_venue(baba_code):
    st.session_state.selected_venue = baba_code
    st.session_state.selected_race = None


def select_today_race(race_no_value):
    baba_code = st.session_state.selected_venue
    race_date_value = st.session_state.race_picker_date

    race_url = (
        "https://www.keiba.go.jp/"
        "KeibaWeb/TodayRaceInfo/DebaTable?"
        + urlencode({
            "k_raceDate": race_date_value,
            "k_raceNo": int(race_no_value),
            "k_babaCode": baba_code,
        })
    )

    # レースボタンを押した瞬間の単勝1番人気を自動取得。
    # オッズ未発表なら従来どおり1番を初期値にして、手動変更できる。
    current_favorite = get_current_first_favorite_from_win_odds(
        race_date_value,
        baba_code,
        race_no_value,
    )

    race_key = (
        f"{race_date_value}|"
        f"{baba_code}|"
        f"{int(race_no_value)}"
    )

    st.session_state.auto_axis_race_key = race_key
    st.session_state.auto_axis_info = current_favorite

    if current_favorite is not None:
        st.session_state.axis_horse_input = int(
            current_favorite["馬番"]
        )
    else:
        st.session_state.axis_horse_input = 1

    st.session_state.selected_race = int(race_no_value)
    st.session_state.race_url_input = race_url
    st.session_state.race_url = race_url
    st.session_state.race_nav_message = ""

    reset_normal_analysis_state()
    st.session_state.analyzed = True


def reselect_today_race():
    st.session_state.selected_race = None
    st.session_state.analyzed = False


def reselect_today_venue():
    st.session_state.selected_venue = None
    st.session_state.selected_race = None
    st.session_state.analyzed = False


def use_manual_race_url():
    st.session_state.race_picker_manual = True
    st.session_state.selected_venue = None
    st.session_state.selected_race = None
    st.session_state.analyzed = False


def use_today_race_picker():
    st.session_state.race_picker_manual = False
    st.session_state.selected_venue = None
    st.session_state.selected_race = None
    st.session_state.analyzed = False


def render_today_race_picker():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today_value = datetime.now(
        ZoneInfo("Asia/Tokyo")
    ).strftime("%Y/%m/%d")

    # 日付をまたいだセッションでは、前日の選択だけを解除する。
    if st.session_state.race_picker_date != today_value:
        st.session_state.race_picker_date = today_value
        st.session_state.selected_venue = None
        st.session_state.selected_race = None
        st.session_state.analyzed = False

    if st.session_state.race_picker_manual:
        st.button(
            "🏇 本日の開催から選ぶ",
            on_click=use_today_race_picker,
        )
        return

    try:
        (
            schedule,
            finished_races,
        ) = get_today_race_schedule(
            today_value
        )
    except Exception:
        st.warning(
            "本日の開催情報を取得できませんでした"
        )
        st.caption(
            "従来どおり出馬表URLを入力して利用できます。"
        )
        return

    selected_venue = st.session_state.selected_venue
    selected_race = st.session_state.selected_race

    # キャッシュ更新や日付変更で対象外になった選択を安全に解除する。
    if selected_venue not in schedule:
        selected_venue = None
        selected_race = None
        st.session_state.selected_venue = None
        st.session_state.selected_race = None
        st.session_state.analyzed = False

    if (
        selected_race is not None
        and selected_race not in schedule.get(
            selected_venue,
            [],
        )
    ):
        selected_race = None
        st.session_state.selected_race = None
        st.session_state.analyzed = False

    if selected_venue is None:
        st.subheader("🏇 本日の開催")

        today_venues = [
            (baba_code, baba_name)
            for baba_code, baba_name in keibajo.items()
            if baba_code in schedule
        ]

        for row_start in range(
            0,
            len(today_venues),
            4,
        ):
            columns = st.columns(4)

            for column, venue_item in zip(
                columns,
                today_venues[row_start:row_start + 4],
            ):
                baba_code, baba_name = venue_item

                with column:
                    st.button(
                        baba_name.removesuffix("競馬"),
                        key=f"today_venue_{baba_code}",
                        on_click=select_today_venue,
                        args=(baba_code,),
                        use_container_width=True,
                    )

        st.button(
            "出馬表URLを直接入力する",
            on_click=use_manual_race_url,
        )
        st.stop()

    venue_name = keibajo[
        selected_venue
    ].removesuffix("競馬")

    if selected_race is None:
        st.subheader(
            f"🏇 {venue_name}競馬"
        )

        race_numbers = schedule[
            selected_venue
        ]
        venue_finished_races = set(
            finished_races.get(
                selected_venue,
                [],
            )
        )

        for row_start in range(
            0,
            len(race_numbers),
            4,
        ):
            columns = st.columns(4)

            for column, race_no_value in zip(
                columns,
                race_numbers[row_start:row_start + 4],
            ):
                with column:
                    race_label = (
                        f"{race_no_value}R 済"
                        if race_no_value
                        in venue_finished_races
                        else f"{race_no_value}R"
                    )

                    st.button(
                        race_label,
                        key=(
                            f"today_race_"
                            f"{selected_venue}_"
                            f"{race_no_value}"
                        ),
                        on_click=select_today_race,
                        args=(race_no_value,),
                        use_container_width=True,
                    )

        st.button(
            "← 会場を選び直す",
            on_click=reselect_today_venue,
        )
        st.stop()

    st.subheader(
        f"🏇 {venue_name} {selected_race}R"
    )

    back_col1, back_col2 = st.columns(2)

    with back_col1:
        st.button(
            "← レースを選び直す",
            on_click=reselect_today_race,
            use_container_width=True,
        )

    with back_col2:
        st.button(
            "← 会場を選び直す",
            on_click=reselect_today_venue,
            use_container_width=True,
        )


if "selected_venue" not in st.session_state:
    st.session_state.selected_venue = None

if "selected_race" not in st.session_state:
    st.session_state.selected_race = None

if "race_picker_date" not in st.session_state:
    st.session_state.race_picker_date = ""

if "race_picker_manual" not in st.session_state:
    st.session_state.race_picker_manual = False

if "axis_horse_input" not in st.session_state:
    st.session_state.axis_horse_input = 1

if "auto_axis_race_key" not in st.session_state:
    st.session_state.auto_axis_race_key = ""

if "auto_axis_info" not in st.session_state:
    st.session_state.auto_axis_info = None


render_today_race_picker()

debug_mode = st.checkbox("デバッグ表示")


# ==================================================
# URL入力
# ==================================================
url = st.text_input(
    "出馬表URLを入力してください",
    key="race_url_input"
)


# ==================================================
# 現在のRを表示
# ==================================================
current_race_no = get_race_no_from_url(
    url
)

if current_race_no is not None:
    st.caption(
        f"🏇 現在 {current_race_no}R"
    )


# ==================================================
# 操作ボタン
# ==================================================
col1, col2, col3, col4 = st.columns(
    [1.35, 1, 1, 1.15]
)

with col1:
    st.button(
        "🔍 分析開始",
        on_click=start_normal_analysis,
        use_container_width=True
    )

with col2:
    st.button(
        "⬅ 前のR",
        on_click=move_race,
        args=(-1,),
        use_container_width=True
    )

with col3:
    st.button(
        "次のR ➡",
        on_click=move_race,
        args=(1,),
        use_container_width=True
    )

with col4:
    st.button(
        "🗑 URL削除",
        on_click=clear_race_url,
        use_container_width=True
    )


# ==================================================
# 前R / 次Rメッセージ
# ==================================================
if st.session_state.race_nav_message:
    st.caption(
        st.session_state.race_nav_message
    )


# ==================================================
# 通常分析用URLを同期
# ==================================================
url = (
    st.session_state
    .race_url_input
    .strip()
)

st.session_state.race_url = url


# ==================================================
# 分析開始前は停止
# ==================================================
if not st.session_state.analyzed:
    st.stop()

# ==================================================
# 一括検証実行中だけ内部URLを差し替える
# 通常の「分析開始」では絶対に差し替えない
# ==================================================
if st.session_state.batch_mode:

    if (
        not st.session_state.batch_date
        or not st.session_state.batch_baba_code
    ):
        # 古いセッション状態などで壊れた一括モードが残った場合は解除
        st.session_state.batch_mode = False
        st.session_state.batch_race_no = 1

    else:
        current_batch_race = st.session_state.batch_race_no
        batch_date_encoded = (
            st.session_state.batch_date
            .replace("/", "%2F")
        )

        url = (
            "https://www.keiba.go.jp/"
            "KeibaWeb/TodayRaceInfo/DebaTable"
            f"?k_raceDate={batch_date_encoded}"
            f"&k_raceNo={current_batch_race}"
            f"&k_babaCode={st.session_state.batch_baba_code}"
        )


if not url:
    st.warning("出馬表URLを入力してください")
    st.stop()

# 初期画面では読み込まず、
# 分析開始ボタンを押した後だけ読み込む
import requests
from bs4 import BeautifulSoup

st.write("分析開始...")

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

# ==================================================
# 今回レースのクラス
#
# ページ上部のレース名から、
# A1 / B5 / C1 などを取得する。
# 取得できない競馬場・レースではNoneのままにして、
# 展開馬クラス補正は自動的に無効化する。
# ==================================================
current_race_class = extract_race_class_from_text(
    page_text[:1200]
)

if debug_mode:
    st.caption(
        "展開馬クラス補正｜今回クラス："
        + (
            current_race_class.get(
                "表示",
                "不明",
            )
            if current_race_class
            else "判定なし"
        )
    )
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

for _, name in matches:
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

    # 展開馬クラス補正用。
    #
    # NAR出馬表では、前走〜5走前の
    # 「日付・距離」と「レース名（クラス）」が別行に並ぶ。
    # 日付ブロック内からクラスを探す方式だと列ズレが起きるため、
    # クラスだけはhorse_text全体から表示順に抜き出して後で対応させる。
    valid_classes = []

    date_blocks = re.split(
        r"(?=(?:取消|除外|中止|競走除外|出走取消|出走除外)?\s*\d{2}\.\d{2}\.\d{2})",
        horse_text
    )

    for block in date_blocks:
        if any(word in block for word in ["除外", "取消", "中止", "競走除外", "出走取消"]):
            continue

        d_match = re.search(
            r"(?:右|左|芝|ダ)\s*"
            r"(800|820|850|900|920|1000|1100|1200|1230|1300|1400|1500|1580|1600|1650|1700|1800|1870|1900|2000|2100|2200)",
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

    # 前走→前々走→3走前→4走前→5走前の順で
    # クラス行も同じ列順に並んでいるため、そのまま対応させる。
    ordered_class_history = (
        extract_all_race_classes_from_text(
            horse_text
        )
    )

    valid_classes = (
        ordered_class_history[
            :len(valid_distances)
        ]
    )

    # クラス表記が無い列が混じる競馬場では、
    # 距離数に足りない分だけNoneで埋める。
    if len(valid_classes) < len(valid_distances):
        valid_classes.extend(
            [None]
            * (
                len(valid_distances)
                - len(valid_classes)
            )
        )

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

        past_class = (
            valid_classes[idx]
            if idx < len(valid_classes)
            else None
        )

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

            # 展開馬専用クラス補正で使用。
            # 総合・地力・先行・抑えには使わない。
            "クラス": past_class,

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

        elif distance_num == 1100:

            distance_ok = (
                1000 <= past_distance <= 1200
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

    # ==================================================
    # 近走前崩れ判定
    #
    # 目的：
    # 「昔は前で残せた」実績だけで、現在も持続型・展開型として
    # 高く評価されるのを防ぐ。
    #
    # 直近3走のうち、
    # ・前半4番手以内
    # ・最終着順までに3つ以上後退
    # が2回以上あれば「近走前崩れ」とする。
    #
    # これは「前へ行ける能力」そのものを消す判定ではない。
    # そのため先行力Dには残せるが、
    # ・地力代表C（持続して脚を使える馬）
    # ・展開馬B
    # には採用しない。
    # ==================================================
    recent_front_break_count = 0
    recent_front_break_details = []

    recent_front_break_check_count = min(
        3,
        len(race_flows),
        len(finish_positions),
    )

    for idx in range(
        recent_front_break_check_count
    ):
        flow = race_flows[idx]
        finish = finish_positions[idx]

        if (
            finish is None
            or len(flow) < 1
        ):
            continue

        first = flow[0]
        total_drop = finish - first

        if (
            first <= 4
            and total_drop >= 3
        ):
            recent_front_break_count += 1

            recent_front_break_details.append({
                "何走前": idx + 1,
                "通過順": flow,
                "着順": finish,
                "前半から着順の後退": total_drop,
            })

    is_recent_front_break = (
        recent_front_break_count >= 2
    )

    # 出走取消・競走除外判定
    is_scratched = any(
        word in horse_text
        for word in ["出走取消", "競走除外", "出走除外"]
    )
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

        # 直近3走で前から繰り返し崩れている馬。
        # 先行力は残すが、地力代表・展開馬からは外す。
        "近走前崩れ": is_recent_front_break,
        "近走前崩れ回数": recent_front_break_count,
        "近走前崩れ詳細": recent_front_break_details,

        "取得テキスト": horse_text,
    })
# ==================================================
# 出走馬のデータ取得状況
# デバッグ時だけ折りたたみ表示する
# ==================================================

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

# 直近3走で前から繰り返し崩れている馬。
# 前進気勢・先行力Dには残すが、
# 地力代表Cと展開馬Bには採用しない。
recent_front_break_horse_numbers = {
    h["馬番"]
    for h in horses
    if h.get("近走前崩れ", False)
}


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

# ==================================================
# 軸馬指定
#
# 通常：手入力
# 一括検証：NAR出馬表の「1人気」を自動取得
# ==================================================

auto_first_favorite_num = None

if st.session_state.batch_mode:

    # 各馬の取得テキスト内にある "(1人気)" を探す
    for h in horses:

        horse_text_for_popularity = h.get(
            "取得テキスト",
            "",
        )

        if re.search(
            r"\(\s*1人気\s*\)",
            horse_text_for_popularity,
        ):
            auto_first_favorite_num = h["馬番"]
            break

    # 表記ゆれ対策：全ページ文字列から馬名近辺も確認
    if auto_first_favorite_num is None:

        for h in horses:

            horse_name = re.escape(
                h["馬名"]
            )

            popularity_pattern = (
                horse_name
                + r".{0,250}?"
                + r"\(\s*1人気\s*\)"
            )

            if re.search(
                popularity_pattern,
                page_text,
                flags=re.S,
            ):
                auto_first_favorite_num = h["馬番"]
                break

    if auto_first_favorite_num is None:

        st.session_state.batch_results.append({
            "R": int(race_no),
            "状態": "失敗",
            "理由": "1番人気を自動取得できませんでした",
            "投資": 0,
            "払戻": 0,
        })

        if (
            st.session_state.batch_race_no
            < st.session_state.batch_last_race
        ):
            st.session_state.batch_race_no += 1
            st.rerun()

        else:
            st.session_state.batch_mode = False
            st.rerun()

    # ------------------------------------------
    # 一括検証の軸
    #
    # 通常一括：
    #   A = NAR1番人気
    #
    # 後詰め軸一括：
    #   1回目はNAR1番人気をAにしてFを確定。
    #   2回目はそのFをAにして全ロジックを再計算。
    # ------------------------------------------
    use_backfill_override = (
        st.session_state.batch_axis_mode == "backfill"
        and st.session_state.batch_axis_override_num is not None
        and st.session_state.batch_axis_override_race == int(race_no)
    )

    if use_backfill_override:

        popular_horse_num = int(
            st.session_state.batch_axis_override_num
        )

        st.success(
            f"⚔️ 後詰め軸：{popular_horse_num}番 "
            "（通常分析のFをAとして再計算）"
        )

    else:

        popular_horse_num = int(
            auto_first_favorite_num
        )

        if st.session_state.batch_axis_mode == "backfill":
            st.info(
                f"後詰め軸を選定中："
                f"まずNAR1番人気 {popular_horse_num}番で通常分析します"
            )
        else:
            st.success(
                f"自動軸：{popular_horse_num}番 "
                "（NAR 1番人気）"
            )

else:

    # 会場→レースボタンから入った場合は、
    # ボタン押下時点の単勝1番人気を初期値として自動セットする。
    # ただし使用者はこの入力欄から自由に変更できる。
    if st.session_state.axis_horse_input > len(real_horses):
        st.session_state.axis_horse_input = 1

    popular_horse_num = st.number_input(
        "軸馬の馬番",
        min_value=1,
        max_value=len(real_horses),
        step=1,
        key="axis_horse_input",
    )

    current_axis_race_key = (
        f"{race_date}|"
        f"{params.get('k_babaCode', [''])[0]}|"
        f"{race_no}"
    )

    auto_axis_info = (
        st.session_state.auto_axis_info
        if st.session_state.auto_axis_race_key
        == current_axis_race_key
        else None
    )

    if auto_axis_info is not None:
        auto_axis_num = int(
            auto_axis_info["馬番"]
        )
        auto_axis_odds = auto_axis_info.get(
            "単勝"
        )

        if int(popular_horse_num) == auto_axis_num:
            st.success(
                f"🎯 現在の単勝1番人気 "
                f"{auto_axis_num}番を自動で軸にセットしました"
                + (
                    f"（単勝 {auto_axis_odds:.1f}倍）"
                    if isinstance(auto_axis_odds, (int, float))
                    else ""
                )
            )
        else:
            st.caption(
                f"自動取得時の単勝1番人気は "
                f"{auto_axis_num}番"
                + (
                    f"（{auto_axis_odds:.1f}倍）"
                    if isinstance(auto_axis_odds, (int, float))
                    else ""
                )
                + "。現在は手動で軸を変更しています。"
            )
    elif st.session_state.auto_axis_race_key == current_axis_race_key:
        st.caption(
            "単勝オッズがまだ出ていないため、軸馬は手動選択です。"
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
    # ==================================================
    # 長距離では、短距離だけの先行実績を少し弱める
    if distance_num >= 1900:
        short_distance_count = len(re.findall(r"(?:右|左)?(?:800|900|1000|1200|1300|1400)", horse_text))
        long_distance_count = len(re.findall(r"(?:右|左)?(?:1600|1700|1800|1900|2000)", horse_text))

        if long_distance_count == 0:
            front_score -= 120
        elif short_distance_count > long_distance_count:
            front_score -= 80
    front_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
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


# ==================================================
# 🚀 2〜4角・押上ランキング（デバッグ専用）
#
# 目的：
# 「差し」「押上」という脚質名だけではなく、
# 実際にどの勝負所で位置を上げたかを見る。
#
# ランキング：
# ① 2角 → 3角
# ② 3角 → 4角
# ③ 2角 → 4角
#
# 重要：
# ・補完後の「通過順」は使わない。
# ・必ず「元通過順」を使う。
# ・通常会場は元通過順が4地点ある過去走だけを対象にする。
# ・盛岡だけは2地点・3地点が多いため、既存の4地点補完後「通過順」を使う。
# ・門別・大井だけは同会場の過去走に限り、3地点を2角・3角・4角、
#   2地点を3角・4角としてK/L評価用の4地点へ変換する。
# ・今回距離帯を最優先。
# ・該当距離がない馬だけ、最も近い距離を弱く評価する。
# ・最新走ほど少し強く評価する。
#
# ※デバッグ表示だけで、買い目・B〜J選出には一切影響しない。
# ==================================================


def corner_push_distance_is_match(
    past_distance,
    current_distance,
):
    """押上評価で今回距離と比較可能か判定する。"""

    if current_distance <= 1000:
        return 800 <= past_distance <= 1000

    if current_distance == 1100:
        return 1000 <= past_distance <= 1200

    if current_distance <= 1400:
        return 1200 <= past_distance <= 1400

    return (
        abs(
            past_distance
            - current_distance
        ) <= 300
    )


def get_corner_push_runs(
    horse,
    current_distance,
):
    """
    押上ランキングに使う過去走を返す。

    通常会場：
      元通過順が4地点ある走だけを対象にする。

    盛岡だけ：
      2地点・3地点の通過順が多いため、
      既存の expand_flow_to_four() で補完済みの
      「通過順」を押上ランキングにも使用する。

      例：10-5 → 10-10-5-5
      この場合、2角→4角は 10→5 なので5頭押上として評価。

    門別・大井だけ：
      今回会場と過去走会場が同じ場合に限り、元通過順が3地点なら
      2角・3角・4角、2地点なら3角・4角として扱う。

      例：5-3-2 → 5-5-3-2
          4-2 → 4-4-4-2

      大井1200mのように2地点・3地点表示が多い条件でも、
      K＝3角→4角、L＝2角→4角の押上評価へ入れられる。

    今回距離帯があればその走だけを100％評価し、
    今回距離帯が1走もない場合だけ、
    最も近い距離の走を弱く評価する。

    K/Lの質補正に使うため、各走の
    ・走破タイム
    ・クラス
    ・着順
    も一緒に保持する。
    """

    valid_runs = []

    recent_weights = [
        1.00,
        0.85,
        0.70,
        0.55,
        0.40,
    ]

    for idx, item in enumerate(
        horse.get(
            "距離付きタイム",
            [],
        )[:5]
    ):
        raw_flow = item.get(
            "元通過順",
            [],
        )

        # 距離付きタイム作成時に保存されている
        # 実際の過去走競馬場。
        past_place = item.get(
            "競馬場",
            "",
        )

        # 盛岡だけは、2地点・3地点を4地点へ補完済みの
        # 評価用通過順を押上ランキングにも使う。
        # 門別・大井は、今回会場と過去走会場が同じ場合だけ、
        # 3地点を2角・3角・4角、2地点を3角・4角として扱う。
        # その他会場は従来どおり「元通過順4地点のみ」。
        if baba_name == "盛岡":
            push_flow = item.get(
                "通過順",
                [],
            )
        elif (
            baba_name in ["門別", "大井"]
            and past_place == baba_name
        ):
            if len(raw_flow) >= 4:
                push_flow = raw_flow[:4]
            elif len(raw_flow) == 3:
                push_flow = [
                    raw_flow[0],
                    raw_flow[0],
                    raw_flow[1],
                    raw_flow[2],
                ]
            elif len(raw_flow) == 2:
                push_flow = [
                    raw_flow[0],
                    raw_flow[0],
                    raw_flow[0],
                    raw_flow[1],
                ]
            else:
                push_flow = raw_flow
        else:
            push_flow = raw_flow

        past_distance = item.get(
            "距離",
            0,
        )

        if (
            not past_distance
            or len(push_flow) < 4
        ):
            continue

        time_text = item.get(
            "タイム",
            "",
        )

        time_seconds = parse_time_to_seconds(
            time_text
        )

        # 園田⇔姫路は既存の同距離タイム比較と同じ補正。
        if time_seconds is not None:
            if (
                baba_name == "園田"
                and past_place == "姫路"
            ):
                time_seconds += 5.0

            elif (
                baba_name == "姫路"
                and past_place == "園田"
            ):
                time_seconds -= 5.0

        valid_runs.append({
            "何走前": idx + 1,
            "距離": past_distance,
            "競馬場": past_place,
            # 下流の押上計算はこのキーを参照しているため、
            # キー名は維持し、中身だけ盛岡・門別・大井では
            # 上記のK/L評価用通過順にする。
            "元通過順": push_flow[:4],
            "着順": item.get(
                "着順"
            ),
            "タイム": time_text,
            "タイム秒": time_seconds,
            "クラス": item.get(
                "クラス"
            ),
            "新しさ倍率": (
                recent_weights[idx]
                if idx < len(recent_weights)
                else 0.40
            ),
        })

    if not valid_runs:
        return {
            "走": [],
            "距離倍率": 0.0,
            "モード": "4地点データなし",
            "最短距離差": None,
        }

    matched_runs = [
        run
        for run in valid_runs
        if corner_push_distance_is_match(
            run["距離"],
            current_distance,
        )
    ]

    if matched_runs:
        return {
            "走": matched_runs,
            "距離倍率": 1.0,
            "モード": "今回距離帯",
            "最短距離差": min(
                abs(
                    run["距離"]
                    - current_distance
                )
                for run in matched_runs
            ),
        }

    nearest_gap = min(
        abs(
            run["距離"]
            - current_distance
        )
        for run in valid_runs
    )

    nearest_runs = [
        run
        for run in valid_runs
        if abs(
            run["距離"]
            - current_distance
        ) == nearest_gap
    ]

    if nearest_gap <= 200:
        distance_weight = 0.50

    elif nearest_gap <= 400:
        distance_weight = 0.30

    elif nearest_gap <= 600:
        distance_weight = 0.20

    else:
        distance_weight = 0.10

    return {
        "走": nearest_runs,
        "距離倍率": distance_weight,
        "モード": "近似距離フォールバック",
        "最短距離差": nearest_gap,
    }


# ==================================================
# 🚀 K/L押上ランキング・質補正
#
# 押上頭数だけでなく、
# 「どのレベル・どの時計で押し上げたか」を評価する。
#
# 基本式：
#   押上スコア × タイム補正 × クラス補正
#
# ① 走破タイム補正
#    同じ競馬場・同じ距離の時計を優先して比較。
#    サンプル不足時のみ同距離全体へフォールバック。
#
# ② クラス補正
#    下級条件での押上は少し割り引く。
#
# ※着順・押上後の失速はK/Lの質補正には入れない。
# ※K＝3角→4角、L＝2角→4角の意味自体は変えない。
# ==================================================


def build_corner_push_time_reference(
    horse_list,
):
    """K/L用の走破タイム比較母集団を作る。"""

    by_track_distance = {}
    by_distance = {}

    for horse in horse_list:
        for item in horse.get(
            "距離付きタイム",
            [],
        )[:5]:
            past_distance = item.get(
                "距離",
                0,
            )

            past_place = item.get(
                "競馬場",
                "",
            )

            time_seconds = parse_time_to_seconds(
                item.get(
                    "タイム",
                    "",
                )
            )

            if (
                not past_distance
                or time_seconds is None
            ):
                continue

            # 園田⇔姫路は既存比較と同じ補正。
            if (
                baba_name == "園田"
                and past_place == "姫路"
            ):
                time_seconds += 5.0

            elif (
                baba_name == "姫路"
                and past_place == "園田"
            ):
                time_seconds -= 5.0

            by_track_distance.setdefault(
                (
                    past_place,
                    past_distance,
                ),
                [],
            ).append(
                time_seconds
            )

            by_distance.setdefault(
                past_distance,
                [],
            ).append(
                time_seconds
            )

    for values in by_track_distance.values():
        values.sort()

    for values in by_distance.values():
        values.sort()

    return {
        "競馬場距離": by_track_distance,
        "距離": by_distance,
    }


corner_push_time_reference = (
    build_corner_push_time_reference(
        horses
    )
)


def calc_corner_push_time_factor(
    run,
):
    """
    押し上げた走の時計の質を倍率化する。

    同競馬場・同距離が3走以上あれば最優先。
    足りなければ同距離全体が6走以上の時だけ比較する。
    データ不足は1.00で中立。
    """

    time_seconds = run.get(
        "タイム秒"
    )

    if time_seconds is None:
        return {
            "倍率": 1.00,
            "判定": "タイムなし・中立",
            "順位率": None,
            "母数": 0,
        }

    track_key = (
        run.get(
            "競馬場",
            "",
        ),
        run.get(
            "距離",
            0,
        ),
    )

    track_values = (
        corner_push_time_reference[
            "競馬場距離"
        ].get(
            track_key,
            [],
        )
    )

    if len(track_values) >= 3:
        values = track_values
        mode = "同競馬場・同距離"

    else:
        distance_values = (
            corner_push_time_reference[
                "距離"
            ].get(
                run.get(
                    "距離",
                    0,
                ),
                [],
            )
        )

        if len(distance_values) >= 6:
            values = distance_values
            mode = "同距離全体"
        else:
            return {
                "倍率": 1.00,
                "判定": "比較母数不足・中立",
                "順位率": None,
                "母数": max(
                    len(track_values),
                    len(distance_values),
                ),
            }

    # 同値タイムは一番良い順位側で扱う。
    rank = next(
        (
            idx + 1
            for idx, value in enumerate(values)
            if value >= time_seconds - 1e-9
        ),
        len(values),
    )

    rank_rate = (
        rank / len(values)
    )

    if rank_rate <= 0.25:
        factor = 1.08
        judgement = "速い・上位25％"

    elif rank_rate <= 0.50:
        factor = 1.02
        judgement = "やや速い・上位50％"

    elif rank_rate <= 0.75:
        factor = 0.95
        judgement = "やや遅い"

    elif rank_rate <= 0.90:
        factor = 0.85
        judgement = "遅い"

    else:
        factor = 0.75
        judgement = "かなり遅い"

    return {
        "倍率": factor,
        "判定": (
            f"{mode}・{judgement}"
        ),
        "順位率": round(
            rank_rate,
            3,
        ),
        "母数": len(values),
    }


def calc_corner_push_class_factor(
    run,
    current_class,
):
    """
    押し上げた走のクラスを今回クラスと比較する。

    下級条件ほど押上価値を割り引く。
    クラス不明時は中立。
    """

    current_value = get_race_class_value(
        current_class
    )

    past_class = run.get(
        "クラス"
    )

    past_value = get_race_class_value(
        past_class
    )

    if (
        current_value is None
        or past_value is None
    ):
        return {
            "倍率": 1.00,
            "判定": "クラス不明・中立",
            "差": None,
        }

    class_gap = (
        past_value
        - current_value
    )

    # 値が小さいほど上位クラス。
    if class_gap <= 0:
        factor = 1.00
        judgement = "同格以上"

    elif class_gap <= 2:
        factor = 0.95
        judgement = "少し下級"

    elif class_gap <= 5:
        factor = 0.85
        judgement = "下級"

    elif class_gap <= 9:
        factor = 0.75
        judgement = "明確な下級"

    else:
        factor = 0.65
        judgement = "大幅な下級"

    return {
        "倍率": factor,
        "判定": judgement,
        "差": class_gap,
    }


def calc_corner_push_ranking(
    horse_list,
    current_distance,
    start_index,
    end_index,
    point_per_head,
    current_class=None,
):
    """
    指定区間の押上ランキングを作る。

    start_index / end_index
      1 = 2角
      2 = 3角
      3 = 4角

    位置番号は小さくなるほど前進なので、
    start_position - end_position がプラスなら押上。

    K/Lで使う4角終点のランキングでは、
    押上そのものを土台にしつつ、
    ・押し上げたレースの走破タイム
    ・押し上げたレースのクラス
    だけを倍率補正する。

    ※押上後の着順・失速はこのK/L補正には入れない。
    """

    ranking = []

    for horse in horse_list:
        target = get_corner_push_runs(
            horse,
            current_distance,
        )

        target_runs = target[
            "走"
        ]

        distance_weight = target[
            "距離倍率"
        ]

        if not target_runs:
            continue

        score = 0.0
        raw_push_score = 0.0
        push_count = 0
        total_gain = 0
        max_gain = 0
        quality_adjustment_count = 0
        details = []

        for run in target_runs:
            flow = run[
                "元通過順"
            ]

            start_position = flow[
                start_index
            ]

            end_position = flow[
                end_index
            ]

            gain = (
                start_position
                - end_position
            )

            # 順位を上げた走だけ加点。
            if gain <= 0:
                continue

            base_score = (
                gain
                * point_per_head
            )

            # 勝負所で前まで取り付いた価値を追加。
            position_bonus = 0

            if end_index == 2:
                # 3角時点
                if end_position <= 3:
                    position_bonus = 15
                elif end_position <= 5:
                    position_bonus = 10

            elif end_index == 3:
                # 4角時点
                if end_position <= 3:
                    position_bonus = 30
                elif end_position <= 5:
                    position_bonus = 20

            raw_applied_score = round(
                (
                    base_score
                    + position_bonus
                )
                * run[
                    "新しさ倍率"
                ]
                * distance_weight,
                1,
            )

            # --------------------------------------------------
            # K/Lの押上「質」補正
            #
            # K＝3角→4角、L＝2角→4角なので、
            # 4角を終点にするランキングだけへ適用する。
            #
            # 押上素点 × タイム倍率 × クラス倍率
            #
            # 着順・押上後の失速はここでは評価しない。
            # --------------------------------------------------
            if end_index == 3:

                time_info = (
                    calc_corner_push_time_factor(
                        run
                    )
                )

                class_info = (
                    calc_corner_push_class_factor(
                        run,
                        current_class,
                    )
                )

                quality_factor = round(
                    time_info[
                        "倍率"
                    ]
                    * class_info[
                        "倍率"
                    ],
                    4,
                )

            else:

                # 2角→3角はデバッグ用ランキングなので、
                # 従来の押上評価をそのまま残す。
                time_info = {
                    "倍率": 1.00,
                    "判定": "K/L対象外・中立",
                    "順位率": None,
                    "母数": 0,
                }

                class_info = {
                    "倍率": 1.00,
                    "判定": "K/L対象外・中立",
                    "差": None,
                }

                quality_factor = 1.00

            applied_score = round(
                raw_applied_score
                * quality_factor,
                1,
            )

            score += applied_score
            raw_push_score += (
                raw_applied_score
            )
            push_count += 1
            total_gain += gain
            max_gain = max(
                max_gain,
                gain,
            )

            if abs(
                quality_factor - 1.0
            ) >= 0.001:
                quality_adjustment_count += 1

            details.append({
                "何走前": run[
                    "何走前"
                ],
                "距離": run[
                    "距離"
                ],
                "競馬場": run[
                    "競馬場"
                ],
                "通過順": flow,
                "着順": run.get(
                    "着順"
                ),
                "タイム": run.get(
                    "タイム"
                ),
                "クラス": (
                    run.get(
                        "クラス",
                        {}
                    ) or {}
                ).get(
                    "表示",
                    "不明",
                ),
                "区間": (
                    f"{start_position}→"
                    f"{end_position}"
                ),
                "押上": gain,
                "素点": raw_applied_score,
                "タイム倍率": time_info[
                    "倍率"
                ],
                "タイム判定": time_info[
                    "判定"
                ],
                "クラス倍率": class_info[
                    "倍率"
                ],
                "クラス判定": class_info[
                    "判定"
                ],
                "総合倍率": quality_factor,
                "加点": applied_score,
            })

        if score <= 0:
            continue

        ranking.append({
            "馬番": horse[
                "馬番"
            ],
            "馬名": horse[
                "馬名"
            ],
            "スコア": round(
                score,
                1,
            ),
            "押上素点": round(
                raw_push_score,
                1,
            ),
            "押上回数": push_count,
            "質補正回数": quality_adjustment_count,
            "合計押上頭数": total_gain,
            "最大押上頭数": max_gain,
            "距離倍率": distance_weight,
            "距離モード": target[
                "モード"
            ],
            "最短距離差": target[
                "最短距離差"
            ],
            "詳細": details,
        })

    ranking.sort(
        key=lambda x: (
            x["スコア"],
            x["合計押上頭数"],
            x["押上回数"],
            -x["馬番"],
        ),
        reverse=True,
    )

    return ranking


def render_corner_push_ranking(
    title,
    ranking,
):
    """デバッグ画面へ押上ランキングTOP5を表示する。"""

    st.markdown(
        f"#### {title}"
    )

    if not ranking:
        st.write(
            "対象となる押上通過順データなし"
        )
        return

    for rank, horse in enumerate(
        ranking[:5],
        start=1,
    ):
        st.write(
            f"{rank}位｜"
            f"{horse['馬番']}番 "
            f"{horse['馬名']} "
            f"｜{horse['スコア']}点 "
            f"｜押上{horse['押上回数']}回 "
            f"｜合計{horse['合計押上頭数']}頭 "
            f"｜最大{horse['最大押上頭数']}頭 "
            f"｜{horse['距離モード']} "
            f"×{horse['距離倍率']}"
        )

        st.caption(
            f"詳細：{horse['詳細']}"
        )


# 2角→3角：中盤で自分から動ける力。
# K・Lの買い目でも押上ランキングを使うため、
# デバッグOFFでもランキング自体は計算しておく。
corner_push_2to3 = (
    calc_corner_push_ranking(
        horses,
        distance_num,
        start_index=1,
        end_index=2,
        point_per_head=20,
        current_class=current_race_class,
    )
)

# 3角→4角：最も重視する勝負所の押上。
# Kは1位から候補を開始する。Lも別ランキングの1位から開始する。
corner_push_3to4 = (
    calc_corner_push_ranking(
        horses,
        distance_num,
        start_index=2,
        end_index=3,
        point_per_head=30,
        current_class=current_race_class,
    )
)

# 2角→4角：勝負所全体でどれだけ前へ進んだか。
corner_push_2to4 = (
    calc_corner_push_ranking(
        horses,
        distance_num,
        start_index=1,
        end_index=3,
        point_per_head=25,
        current_class=current_race_class,
    )
)

if debug_mode:

    with st.expander(
        "🚀 2〜4角・押上ランキング",
        expanded=False,
    ):
        st.caption(
            (
                "盛岡のみ2地点・3地点の通過順も既存の4地点補完を使って評価。"
                if baba_name == "盛岡"
                else (
                    f"{baba_name}の過去走は、3地点を2角・3角・4角、"
                    "2地点を3角・4角としてK/L評価。"
                    if baba_name in ["門別", "大井"]
                    else "元通過順が4地点ある過去走だけで評価。"
                )
            )
            + "今回距離帯を優先し、最新走ほど少し重くしています。"
            + " K/Lはさらに走破タイム・クラスだけを質補正します。"
            + (
                " K＝3角→4角【勝負所重視】1位、"
                "L＝2角→4角【総合押上】1位を使用します。"
            )
        )

        render_corner_push_ranking(
            "2角 → 3角",
            corner_push_2to3,
        )

        render_corner_push_ranking(
            "3角 → 4角【勝負所重視】",
            corner_push_3to4,
        )

        render_corner_push_ranking(
            "2角 → 4角【総合押上】",
            corner_push_2to4,
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

    # 一括検証では新馬戦を買わない扱いにする。
    # 投資0円・払戻0円・回収率0%として記録し、
    # 全体の総投資・総払戻・回収率計算から実質的に除外する。
    if st.session_state.batch_mode:

        st.session_state.batch_results.append({
            "R": int(race_no),
            "状態": "対象外",
            "理由": "新馬戦（過去レースデータなし）",
            "軸": int(popular_horse_num),
            "軸タイプ": "新馬戦",
            "結果": "-",
            "投資": 0,
            "払戻": 0,
            "収支": 0,
            "回収率": 0.0,
            "三連複": [],
            "ワイド": [],
            "浮き輪": [],
        })

        # 次Rへ行く前に後詰め軸の一時状態をクリア
        st.session_state.batch_axis_override_num = None
        st.session_state.batch_axis_override_race = None
        st.session_state.batch_original_a = None
        st.session_state.batch_original_f = None
        st.session_state.batch_af_match = None

        if (
            st.session_state.batch_race_no
            < st.session_state.batch_last_race
        ):
            st.session_state.batch_race_no += 1
            st.rerun()

        else:
            st.session_state.batch_mode = False
            st.session_state.batch_race_no = 1
            st.rerun()

    # 通常表示で新馬戦だった場合でも、ここで一括検証UIを出す。
    # これにより st.stop() より下にある分析処理へ進まず、
    # かつ全R回収率計算は実行できる。
    render_batch_controls(
        st.session_state.get("race_url", url),
        "newhorse",
    )
    st.stop()

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

    # ==================================================
    # 反復垂れ追加減点
    #
    # 目的：
    # タイムや前進力はあるが、前へ行ったあと何度も止まる馬を、
    # 安定して好走している馬より上に置きすぎない。
    #
    # 条件：
    # ・地力評価に使っている過去5走が対象
    # ・前半3番手以内
    # ・最終着順までに4つ以上順位を落とした
    # ・このレースが2回以上ある
    #
    # 該当2回以上なら、通常の失速減点とは別に追加 -100。
    # 例：2番手→9着、2番手→10着がある馬。
    # ==================================================
    repeat_front_fade_count = 0
    repeat_front_fade_details = []

    for item in evaluation_pairs:

        flow = item.get(
            "通過順",
            []
        )

        finish = item.get(
            "着順"
        )

        if (
            finish is None
            or len(flow) < 1
        ):
            continue

        first = flow[0]
        total_drop = finish - first

        if (
            first <= 3
            and total_drop >= 4
        ):
            repeat_front_fade_count += 1

            repeat_front_fade_details.append({
                "距離": item.get("距離"),
                "通過順": flow,
                "着順": finish,
                "前半から着順の後退": total_drop,
            })

    repeat_front_fade_penalty = (
        100
        if repeat_front_fade_count >= 2
        else 0
    )

    # 複数の通常失速があっても、
    # 地力全体を破壊しないよう通常部分は最大260点。
    raw_applied_risk_penalty = min(
        risk_penalty,
        260
    )

    # 南関から他地区への転入初戦は、
    # 格上の南関での通常失速を40％へ弱め、
    # 最大100点までに抑える。
    #
    # 反復垂れ追加減点も同じく40％へ弱める。
    # 直近大失速はこの下の別枠減点として残す。
    if is_nankan_transfer_first:

        base_applied_risk_penalty = min(
            round(
                raw_applied_risk_penalty
                * NANKAN_TRANSFER_PENALTY_WEIGHT,
                1
            ),
            NANKAN_TRANSFER_RISK_CAP
        )

        applied_repeat_front_fade_penalty = round(
            repeat_front_fade_penalty
            * NANKAN_TRANSFER_PENALTY_WEIGHT,
            1
        )

    else:
        base_applied_risk_penalty = (
            raw_applied_risk_penalty
        )

        applied_repeat_front_fade_penalty = (
            repeat_front_fade_penalty
        )

    # 画面の「失速」には通常失速＋反復垂れをまとめて表示。
    # これにより、例えば従来 -120 の馬が
    # 反復垂れ2回なら -220 になる。
    applied_risk_penalty = (
        base_applied_risk_penalty
        + applied_repeat_front_fade_penalty
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

        # 前半3番手以内から最終着順まで4つ以上後退した
        # レースが2回以上ある場合の追加減点。
        "反復垂れ回数": repeat_front_fade_count,
        "反復垂れ減点": applied_repeat_front_fade_penalty,
        "反復垂れ詳細": repeat_front_fade_details,

        # 直近3走の前崩れ。
        # 地力ランキングには残すが、代表Cには採用しない。
        "近走前崩れ": horse.get(
            "近走前崩れ",
            False,
        ),
        "近走前崩れ回数": horse.get(
            "近走前崩れ回数",
            0,
        ),
        "近走前崩れ詳細": horse.get(
            "近走前崩れ詳細",
            [],
        ),

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
    for h in long_spurt_candidates
    if not h.get(
        "近走前崩れ",
        False,
    )
][:5]
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
                f"｜失速合計 "
                f"-{h.get('失速減点', 0)} "
                f"｜うち反復垂れ "
                f"-{h.get('反復垂れ減点', 0)} "
                f"｜大失速 "
                f"-{h.get('大失速減点', 0)} "
                f"｜決め手不足 "
                f"-{h.get('決め手不足減点', 0)} "
                f"｜近走前崩れ "
                f"{'⚠️' if h.get('近走前崩れ', False) else '-'}"
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
                f"｜反復垂れ "
                f"{h.get('反復垂れ回数', 0)}回 "
                f"(-{h.get('反復垂れ減点', 0)}) "
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
                f"{h.get('失速詳細', [])}\n\n"
                f"反復垂れ詳細："
                f"{h.get('反復垂れ詳細', [])}\n\n"
                f"近走前崩れ："
                f"{h.get('近走前崩れ', False)} "
                f"｜該当 "
                f"{h.get('近走前崩れ回数', 0)}回\n\n"
                f"近走前崩れ詳細："
                f"{h.get('近走前崩れ詳細', [])}"
            )
        
if not long_spurt_candidates:
    st.error("長く脚の評価データが取れていません")
    st.stop()

# 地力ランキング自体は評価順を残す。
# ただし「近走前崩れ」は、前へ行けても現在は持続できていないため
# 地力代表C（持続して脚を使えるタイプ）には採用しない。
long_representative_candidates = [
    h
    for h in long_spurt_candidates
    if not h.get(
        "近走前崩れ",
        False,
    )
]

# 全馬が該当する特殊ケースだけ、ランキング1位へ戻す。
long_best = (
    long_representative_candidates[0]
    if long_representative_candidates
    else long_spurt_candidates[0]
)

long_spurt_horse = (
    f"{long_best['馬番']}番 "
    f"{long_best['馬名']}"
)

# 展開が向く馬：人気馬の脚色と合う馬を選ぶ

# 展開馬は、使用者が選んだ人気馬の脚色から算出する
base_horse_no = popular_horse_num

strong_data = None

for horse in horses:
    if horse["馬番"] == base_horse_no:
        strong_data = horse
        break

strong_flows = strong_data["通過順"] if strong_data else []
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


def classify_basic_flow_type(
    escape_rate,
    front_count,
    stable_count,
    push_count,
    avg_first,
    avg_last,
):
    """通過順集計から共通の基本脚質を判定する。"""

    if escape_rate >= 0.5:
        return "逃げ"

    elif front_count >= 2:
        return "先行"

    elif (
        stable_count >= 2
        and stable_count >= push_count
    ):
        return "持続"

    elif push_count >= 2:
        return "差し"

    elif (
        push_count >= 1
        and avg_first >= 4.5
        and avg_last <= avg_first - 1.5
    ):
        return "差し"

    elif (
        stable_count >= 1
        and 3 <= avg_first <= 6
        and abs(avg_last - avg_first) <= 1.0
    ):
        return "持続"

    elif (
        front_count >= 1
        and avg_first <= 4
        and avg_last <= 5
    ):
        return "先行"

    return "展開待ち"


def build_marble_style_profile(
    style,
    avg_first,
    avg_last,
    primary_type,
    recent_front_break=False,
):
    """
    1頭を1種類の脚質だけに押し込めず、
    「主脚質＋副脚質」のマーブル脚質として保持する。

    主脚質：従来ロジックで決まった最終脚質。
    副脚質：過去走で実際に確認できた別の走り方。

    能力タグ
    ・逃げ   ：1番手を取った経験
    ・先行   ：1角4番手以内を複数回
    ・持続   ：前〜中団で位置を保った経験
    ・押上   ：5番手以下から2つ以上位置を上げた経験
    ・差し   ：押し上げが複数回、または平均的に明確な前進

    「押上」は差しそのものではなく、
    先行馬でも持っていることがある副能力として独立させる。
    """

    valid_count = max(
        style.get("有効数", 0),
        1,
    )

    escape_count = style.get(
        "逃げ回数",
        0,
    )

    front_count = style.get(
        "前団回数",
        0,
    )

    stable_count = style.get(
        "持続回数",
        0,
    )

    push_count = style.get(
        "押し上げ回数",
        0,
    )

    # 0〜100の能力値。
    # 押上は1回でも展開対応力として価値が高いため、
    # 1回確認できれば最低55点を与える。
    ability_scores = {
        "逃げ": round(
            escape_count
            / valid_count
            * 100,
            1,
        ),
        "先行": round(
            front_count
            / valid_count
            * 100,
            1,
        ),
        "持続": (
            0.0
            if recent_front_break
            else round(
                stable_count
                / valid_count
                * 100,
                1,
            )
        ),
        "押上": round(
            max(
                push_count
                / valid_count
                * 100,
                55 if push_count >= 1 else 0,
            ),
            1,
        ),
    }

    tags = []

    # 逃げは一度でも実戦で確認できれば副能力として残す。
    if escape_count >= 1:
        tags.append("逃げ")

    # 先行は複数回の前団経験を基本条件にする。
    # 主脚質が先行なら救済判定で決まった場合も必ず残す。
    if (
        front_count >= 2
        or primary_type == "先行"
    ):
        tags.append("先行")

    # 持続は1回でも位置維持が確認できれば副能力として残す。
    # ただし直近3走で前から繰り返し崩れている馬は、
    # 古い持続実績だけで「現在も持続できる」とは扱わない。
    if (
        stable_count >= 1
        and not recent_front_break
    ):
        tags.append("持続")

    # 押し上げは1回でも明確なら残す。
    if push_count >= 1:
        tags.append("押上")

    # 差しは「押上の再現性」がある時だけ独立タグにする。
    is_clear_closer = (
        push_count >= 2
        or (
            push_count >= 1
            and avg_first >= 4.5
            and avg_last
                <= avg_first - 1.5
        )
        or primary_type == "差し"
    )

    if is_clear_closer:
        tags.append("差し")

    # 主脚質は必ずタグへ残す。
    if (
        primary_type
        not in {"展開待ち"}
        and primary_type not in tags
    ):
        tags.append(primary_type)

    # 重複を消しつつ順序を維持。
    unique_tags = []
    for tag in tags:
        if tag not in unique_tags:
            unique_tags.append(tag)

    # 副脚質は主脚質以外。
    # 差しが主脚質の場合、押上は意味がほぼ重なるため
    # 表示だけは二重に見せない。
    secondary_tags = [
        tag
        for tag in unique_tags
        if tag != primary_type
    ]

    if primary_type == "差し":
        secondary_tags = [
            tag
            for tag in secondary_tags
            if tag != "押上"
        ]

    # 内部判定では副脚質を能力値の高い順に最大3つ保持する。
    # 画面表示では、この中の最上位1つだけを表示する。
    def secondary_sort_score(tag):
        if tag == "差し":
            return ability_scores.get(
                "押上",
                0,
            )

        return ability_scores.get(
            tag,
            0,
        )

    secondary_tags = sorted(
        secondary_tags,
        key=secondary_sort_score,
        reverse=True,
    )[:3]

    # 主＋副で何種類の走り方を持つか。
    marble_degree = (
        1
        + len(secondary_tags)
        if primary_type != "展開待ち"
        else len(secondary_tags)
    )

    return {
        "主脚質": primary_type,
        "副脚質": secondary_tags,
        # 画面表示は副脚質を1つだけ。
        # 内部の副脚質リスト・脚質タグは従来どおり複数保持する。
        "副脚質表示": (
            secondary_tags[0]
            if secondary_tags
            else "なし"
        ),
        "脚質タグ": unique_tags,
        "マーブル度": marble_degree,
        "能力点": ability_scores,
        "逃げ回数": escape_count,
        "前団回数": front_count,
        "持続回数": stable_count,
        "押し上げ回数": push_count,
        "近走前崩れ": recent_front_break,
    }


def format_marble_style(profile):
    """画面表示用の短い主・副脚質表記。"""

    if not profile:
        return "主：不明｜副：なし"

    return (
        f"主：{profile.get('主脚質', '不明')}"
        f"｜副：{profile.get('副脚質表示', 'なし')}"
    )
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

strong_front_count = strong_style["前団回数"]

strong_stable_count = strong_style["持続回数"]
strong_push_count = strong_style["押し上げ回数"]

escape_rate = strong_style["逃げ率"]
# ==================================================
# 軸馬の大まかな脚色判定
#
# 表示は従来どおり、
# 逃げ・先行・持続・差し・展開待ちの5種類
#
# 強いか弱いかではなく、
# 過去5走で大体どこを走る馬かだけを見る
# ==================================================
kyakushoku_type = classify_basic_flow_type(
    escape_rate,
    strong_front_count,
    strong_stable_count,
    strong_push_count,
    strong_avg_first,
    strong_avg_last,
)

# ⑧ 最終救済
# ここまで主脚質が決まらなくても、
# 押し上げ実績が1回でもある馬は「差し」とする。
# 押上実績もない馬だけ「展開待ち」に残す。
if (
    kyakushoku_type == "展開待ち"
    and strong_push_count >= 1
):
    kyakushoku_type = "差し"
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


# ==================================================
# ③ 1番人気 × 持ちタイム上位の「展開待ち」救済
#
# 目的：
# 1番人気で、今回距離の持ちタイムがメンバー上位なのに、
# 通過順の回数条件だけで「展開待ち」へ落ちる馬を救済する。
#
# 重要：
# ・従来判定で「展開待ち」の時だけ発動
# ・NAR出馬表で実際に「1人気」と表示される馬だけ
# ・最高タイムがメンバー2位以内の馬だけ
# ・どの脚質へ入れるかは、速い時計を出した実走の通過順で決める
#
# これにより、
# 「タイムが速いから全部先行」にするのではなく、
# 持ち時計は救済資格、脚質は実際の位置取りで判定する。
# ==================================================

if kyakushoku_type == "展開待ち":

    strong_text = strong_data.get(
        "取得テキスト",
        ""
    )

    # NAR出馬表の「(1人気)」を確認。
    # 軸番号を手入力しただけの馬には無条件で発動させない。
    is_first_favorite = bool(
        re.search(
            r"\(\s*1人気\s*\)",
            strong_text
        )
    )

    # 今回距離の「最高タイム」ランキング。
    # NARの最高タイム欄は当距離成績に対応しているため、
    # 同一レース内では秒数が小さいほど上位とする。
    valid_best_times = sorted(
        [
            (
                h.get("最高タイム秒"),
                h["馬番"],
            )
            for h in horses
            if h.get("最高タイム秒") is not None
        ],
        key=lambda x: (
            x[0],
            x[1],
        )
    )

    best_time_rank_map = {
        horse_no: rank
        for rank, (_, horse_no) in enumerate(
            valid_best_times,
            start=1,
        )
    }

    strong_best_time_rank = (
        best_time_rank_map.get(
            popular_horse_num,
            99,
        )
    )

    # 最高タイム1〜2位だけ救済対象。
    is_time_top2 = (
        strong_best_time_rank <= 2
    )

    if (
        is_first_favorite
        and is_time_top2
    ):

        # ------------------------------------------
        # 今回距離に近い過去走から、
        # 最も速い走破タイムのレースを探す。
        #
        # 1100mは1000〜1200mを近似帯、
        # それ以外は既存距離帯に合わせる。
        # ------------------------------------------
        comparable_time_runs = []

        for item in strong_data.get(
            "距離付きタイム",
            []
        ):

            past_distance = item.get(
                "距離",
                0,
            )

            time_text = item.get(
                "タイム",
                "",
            )

            flow = item.get(
                "通過順",
                [],
            )

            finish = item.get(
                "着順"
            )

            if (
                not past_distance
                or not time_text
                or len(flow) < 2
            ):
                continue

            if distance_num <= 1000:

                time_distance_ok = (
                    800
                    <= past_distance
                    <= 1000
                )

            elif distance_num == 1100:

                time_distance_ok = (
                    1000
                    <= past_distance
                    <= 1200
                )

            elif distance_num <= 1400:

                time_distance_ok = (
                    1200
                    <= past_distance
                    <= 1400
                )

            else:

                time_distance_ok = (
                    abs(
                        past_distance
                        - distance_num
                    )
                    <= 300
                )

            if not time_distance_ok:
                continue

            time_seconds = (
                parse_time_to_seconds(
                    time_text
                )
            )

            if time_seconds is None:
                continue

            comparable_time_runs.append({
                "タイム秒": time_seconds,
                "距離": past_distance,
                "通過順": flow,
                "着順": finish,
            })

        if comparable_time_runs:

            best_time_run = min(
                comparable_time_runs,
                key=lambda x: x[
                    "タイム秒"
                ]
            )

            best_flow = best_time_run[
                "通過順"
            ]

            best_finish = best_time_run[
                "着順"
            ]

            best_first = best_flow[0]
            best_last = best_flow[-1]

            # --------------------------------------
            # 持ち時計を出したレースの走り方でタイプ分け
            # --------------------------------------

            # 逃げ：
            # 速い時計を1番手から出している。
            if (
                best_first == 1
                and best_last <= 2
            ):
                kyakushoku_type = "逃げ"

            # 先行：
            # 速い時計を4番手以内から出し、
            # 4角でも5番手以内を保っている。
            elif (
                best_first <= 4
                and best_last <= 5
            ):
                kyakushoku_type = "先行"

            # 差し：
            # 中団以降から2つ以上押し上げて
            # 速い時計を出している。
            elif (
                best_first >= 5
                and best_last
                    <= best_first - 2
            ):
                kyakushoku_type = "差し"

            # 持続：
            # 3〜7番手付近で大きく位置を変えず
            # 速い時計を出している。
            elif (
                3 <= best_first <= 7
                and abs(
                    best_last
                    - best_first
                ) <= 1
            ):
                kyakushoku_type = "持続"

            # どの型にも明確に入らない場合でも、
            # 1番人気＋持ち時計上位を展開待ちのままにしない。
            # 好走実績があれば位置取りに応じて保守的に振り分ける。
            elif (
                best_finish is not None
                and best_finish <= 3
            ):

                if best_first <= 4:
                    kyakushoku_type = "先行"

                elif best_last < best_first:
                    kyakushoku_type = "差し"

                else:
                    kyakushoku_type = "持続"

            else:
                # 時計上位でも脚質材料が弱い時は、
                # 最も中立的な「持続」へ救済する。
                kyakushoku_type = "持続"


# ==================================================
# 🎨 軸馬のマーブル脚質
#
# 従来の kyakushoku_type は買い目ロジック用の主脚質として維持。
# そのうえで、逃げ・先行・持続・押上などの副能力を保持する。
# ==================================================
axis_marble_profile = build_marble_style_profile(
    strong_style,
    strong_avg_first,
    strong_avg_last,
    kyakushoku_type,
    recent_front_break=(
        strong_data.get(
            "近走前崩れ",
            False,
        )
        if strong_data
        else False
    ),
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
# 地力C × 先行D 被り調整（脚質で役割を分ける）
#
# 基本方針：
# ・C（地力＝持続役）とD（先行役）が同じ馬になった時だけ調整する。
# ・その馬の主脚質または表示上の副脚質が
#   「先行」「逃げ」なら、先行Dを優先してその馬を残す。
#   → 地力Cは地力ランキングの次点へ繰り下げる。
# ・それ以外は従来どおり地力Cを残し、
#   → 先行Dを前進気勢ランキングの次点へ繰り下げる。
#
# 重要：
# ・軸Aと先行Dの重複は許可する。
#   例：軸9番が「主：先行｜副：逃げ」で前進1位なら、
#       Dも9番のままでよい。
# ・ランキングそのものは変更しない。
#   あくまで画面の代表C/Dだけを役割に合わせて振り分ける。
# ==================================================

def get_cd_overlap_profile(horse_no):
    """
    CとDが被った馬の「主脚質＋表示上の副脚質」を取得する。

    軸馬なら、すでに確定済みのaxis_marble_profileをそのまま使う。
    軸馬以外なら、軸判定と同じ通過順ベースの考え方で
    仮の主脚質を作り、マーブル脚質を組み立てる。
    """

    if horse_no == popular_horse_num:
        return axis_marble_profile

    horse_data = next(
        (
            h
            for h in horses
            if h["馬番"] == horse_no
        ),
        None,
    )

    if horse_data is None:
        return {
            "主脚質": "不明",
            "副脚質": [],
            "副脚質表示": "なし",
            "脚質タグ": [],
        }

    race_flows = horse_data.get(
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

    escape_rate_for_cd = style.get(
        "逃げ率",
        0,
    )

    front_count_for_cd = style.get(
        "前団回数",
        0,
    )

    stable_count_for_cd = style.get(
        "持続回数",
        0,
    )

    push_count_for_cd = style.get(
        "押し上げ回数",
        0,
    )

    primary_type_for_cd = classify_basic_flow_type(
        escape_rate_for_cd,
        front_count_for_cd,
        stable_count_for_cd,
        push_count_for_cd,
        avg_first,
        avg_last,
    )

    return build_marble_style_profile(
        style,
        avg_first,
        avg_last,
        primary_type_for_cd,
        recent_front_break=horse_data.get(
            "近走前崩れ",
            False,
        ),
    )


cd_overlap_profile = None

if (
    front_best["馬番"]
    == long_best["馬番"]
):
    overlap_no = front_best["馬番"]

    cd_overlap_profile = get_cd_overlap_profile(
        overlap_no
    )

    overlap_primary = cd_overlap_profile.get(
        "主脚質",
        "不明",
    )

    overlap_secondary = cd_overlap_profile.get(
        "副脚質表示",
        "なし",
    )

    # 主または表示上の副が「先行・逃げ」なら、
    # この馬はD（先行代表）として残す。
    prefer_front_d = (
        overlap_primary in {
            "先行",
            "逃げ",
        }
        or overlap_secondary in {
            "先行",
            "逃げ",
        }
    )

    if prefer_front_d:

        # ------------------------------------------
        # Dを残して、Cを地力ランキング次点へ
        # ------------------------------------------
        for h in long_representative_candidates:

            if h["馬番"] == overlap_no:
                continue

            long_best = h

            long_spurt_horse = (
                f"{long_best['馬番']}番 "
                f"{long_best['馬名']}"
            )

            break

    else:

        # ------------------------------------------
        # Cを残して、Dを前進ランキング次点へ
        #
        # 軸AとDの重複は許可するため、
        # popular_horse_numは除外しない。
        # ------------------------------------------
        for h in front_candidates:

            if h["馬番"] == long_best["馬番"]:
                continue

            front_best = h

            front_horse = (
                f"{front_best['馬番']}番 "
                f"{front_best['馬名']}"
            )

            break



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

# 近走で前から崩れ続けている馬は、
# 前進TOP5×地力TOP5の共通候補からも外す。
common_top5_numbers_for_tenkai -= (
    recent_front_break_horse_numbers
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

    target_type = classify_basic_flow_type(
        escape_rate,
        front_count,
        stable_count,
        push_count,
        avg_first,
        avg_last,
    )

    recent_front_break = horse.get(
        "近走前崩れ",
        False,
    )

    # 直近で前から崩れ続けている馬を、
    # 古い位置維持実績だけで「持続」と分類しない。
    if (
        recent_front_break
        and target_type == "持続"
    ):
        if front_count >= 1:
            target_type = "先行"
        else:
            target_type = "展開待ち"

    marble_profile = build_marble_style_profile(
        style,
        avg_first,
        avg_last,
        target_type,
        recent_front_break=recent_front_break,
    )

    return {
        "候補脚質": target_type,
        "主脚質": marble_profile["主脚質"],
        "副脚質": marble_profile["副脚質"],
        "副脚質表示": marble_profile["副脚質表示"],
        "脚質タグ": marble_profile["脚質タグ"],
        "マーブル度": marble_profile["マーブル度"],
        "能力点": marble_profile["能力点"],
        "平均前半": avg_first,
        "平均4角": avg_last,
        "逃げ率": escape_rate,
        "前団回数": front_count,
        "持続回数": stable_count,
        "押し上げ回数": push_count,
        "近走前崩れ": recent_front_break,
    }


def calc_marble_tenkai_fit(
    axis_profile,
    candidate_profile,
):
    """
    軸の主・副脚質と、相手の主・副脚質を照合して
    展開への対応力を数値化する。

    特に逃げ軸では、
    「前について行けるだけ」の馬より、
    「先行＋押上」の両方を持つ馬を強く評価する。

    例：
    逃げ軸7番に対して、
    5番＝先行のみ
    10番＝先行＋押上
    なら10番を展開上位へ持ち上げる。
    """

    # 近走で前から崩れ続けている馬は、
    # 前進能力は認めても展開馬には採用しない。
    if candidate_profile.get(
        "近走前崩れ",
        False,
    ):
        return {
            "スコア": -999.0,
            "理由": [
                "近走前崩れのため展開対象外"
            ],
        }

    axis_type = axis_profile.get(
        "主脚質",
        "展開待ち",
    )

    axis_tags = set(
        axis_profile.get(
            "脚質タグ",
            [],
        )
    )

    candidate_tags = set(
        candidate_profile.get(
            "脚質タグ",
            [],
        )
    )

    ability = candidate_profile.get(
        "能力点",
        {},
    )

    # 主脚質別に「相手へ欲しい能力」の比率を変える。
    # 合計は概ね100点前後。
    fit_weights = {
        "逃げ": {
            "先行": 0.35,
            "押上": 0.45,
            "持続": 0.20,
            "逃げ": 0.05,
        },
        "先行": {
            "先行": 0.20,
            "押上": 0.40,
            "持続": 0.35,
            "逃げ": 0.05,
        },
        "持続": {
            "先行": 0.25,
            "押上": 0.35,
            "持続": 0.35,
            "逃げ": 0.05,
        },
        "差し": {
            "先行": 0.20,
            "押上": 0.40,
            "持続": 0.35,
            "逃げ": 0.05,
        },
        "展開待ち": {
            "先行": 0.30,
            "押上": 0.30,
            "持続": 0.30,
            "逃げ": 0.10,
        },
    }

    weights = fit_weights.get(
        axis_type,
        fit_weights["展開待ち"],
    )

    fit_score = 0.0
    reasons = []

    for ability_name, weight in weights.items():
        ability_value = ability.get(
            ability_name,
            0,
        )

        fit_score += (
            ability_value
            * weight
        )

    # ----------------------------------------------
    # マーブル組み合わせボーナス
    # ----------------------------------------------
    if axis_type == "逃げ":

        # 今回の本命ルール。
        # 逃げ軸について行ける先行力に加え、
        # ペースが変わった時に自力で押し上げられる馬を優先。
        if {"先行", "押上"}.issubset(
            candidate_tags
        ):
            fit_score += 60
            reasons.append(
                "逃げ軸×先行＋押上"
            )

        elif "先行" in candidate_tags:
            fit_score += 15
            reasons.append(
                "逃げ軸×先行"
            )

    elif axis_type == "先行":

        if {"持続", "押上"}.issubset(
            candidate_tags
        ):
            fit_score += 45
            reasons.append(
                "先行軸×持続＋押上"
            )

        elif {"先行", "持続"}.issubset(
            candidate_tags
        ):
            fit_score += 30
            reasons.append(
                "先行軸×先行＋持続"
            )

    elif axis_type == "持続":

        if {"持続", "押上"}.issubset(
            candidate_tags
        ):
            fit_score += 40
            reasons.append(
                "持続軸×持続＋押上"
            )

        elif {"先行", "持続"}.issubset(
            candidate_tags
        ):
            fit_score += 30
            reasons.append(
                "持続軸×先行＋持続"
            )

    elif axis_type == "差し":

        if {"持続", "押上"}.issubset(
            candidate_tags
        ):
            fit_score += 45
            reasons.append(
                "差し軸×持続＋押上"
            )

        elif "押上" in candidate_tags:
            fit_score += 20
            reasons.append(
                "差し軸×押上"
            )

    # 軸自身にも押上の副能力がある場合、
    # 相手にも押上があれば「もう一つの展開」へ対応しやすい。
    if (
        "押上" in axis_tags
        and "押上" in candidate_tags
    ):
        fit_score += 25
        reasons.append(
            "軸副脚質の押上と一致"
        )

    # 副脚質が複数ある馬は展開の変化に対応しやすい。
    marble_degree = candidate_profile.get(
        "マーブル度",
        0,
    )

    if marble_degree >= 4:
        fit_score += 20
        reasons.append(
            "高マーブル度"
        )

    elif marble_degree >= 3:
        fit_score += 10
        reasons.append(
            "マーブル脚質"
        )

    return {
        "スコア": round(
            fit_score,
            1,
        ),
        "理由": reasons,
    }


# 軸タイプごとに、展開相手として優先する脚質
# 最上位の脚質が1頭でもいれば、その脚質内だけで選ぶ。
tenkai_type_priority = {
    "逃げ": [
        # 逃げ軸では、同型逃げよりも
        # 「前について行けて、その後も動ける馬」を先に見る。
        "先行",
        "持続",
        "差し",
        "逃げ",
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


# ==================================================
# 展開馬試験用・同距離タイム比較
#
# 目的：
# ・前進TOP5×地力TOP5で作った展開候補の中で、
#   「今回と同じ距離で実際に速く走れた馬」を最終比較に使う。
# ・タイムが無い馬は減点しない。従来順位のまま扱う。
# ・まず今回競馬場×同距離の実績を最優先する。
# ・今回競馬場に同距離実績が無い場合だけ、
#   他場の同距離実績を補助的に使う。
# ・園田⇔姫路は既存総合評価と同じ5.0秒補正を使用する。
# ・盛岡⇔水沢、浦和⇔川崎・船橋は、
#   距離付きタイム作成時点で既存補正済みの値を使う。
#
# 今回は「タイムだけで展開馬を決める」のではなく、
# 軸タイプに合う脚質グループ内の最終タイブレークとして使う。
# ==================================================

def get_tenkai_same_distance_best_time(horse):
    same_track_times = []
    fallback_times = []

    for item in horse.get(
        "距離付きタイム",
        [],
    ):
        if item.get("距離") != distance_num:
            continue

        time_text = item.get("タイム", "")
        past_place = item.get("競馬場", "")

        if not time_text:
            continue

        try:
            minutes, seconds = time_text.split(":")
            total_seconds = (
                int(minutes) * 60
                + float(seconds)
            )
        except (ValueError, TypeError, AttributeError):
            continue

        # 園田⇔姫路は既存総合評価と同じ補正を使用。
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

        if past_place == baba_name:
            same_track_times.append(
                total_seconds
            )
        else:
            fallback_times.append(
                total_seconds
            )

    # 今回競馬場×同距離の時計があれば、それだけを使用。
    if same_track_times:
        return {
            "秒": min(same_track_times),
            "モード": "同競馬場・同距離",
        }

    # 無い場合だけ他場の同距離時計を補助使用。
    if fallback_times:
        return {
            "秒": min(fallback_times),
            "モード": "他場・同距離",
        }

    return {
        "秒": None,
        "モード": "同距離タイムなし",
    }


tenkai_same_distance_time_info = {}

for horse in horses:
    tenkai_same_distance_time_info[
        horse["馬番"]
    ] = get_tenkai_same_distance_best_time(
        horse
    )

# 有効な同距離タイムだけでメンバー順位を作る。
# タイムが無い馬は99位扱いだが、減点はしない。
valid_tenkai_times = sorted(
    [
        (
            info["秒"],
            horse_no,
        )
        for horse_no, info
        in tenkai_same_distance_time_info.items()
        if info.get("秒") is not None
    ],
    key=lambda x: (x[0], x[1]),
)

tenkai_time_rank_map = {
    horse_no: rank
    for rank, (_, horse_no)
    in enumerate(
        valid_tenkai_times,
        start=1,
    )
}

axis_tenkai_time = (
    tenkai_same_distance_time_info
    .get(
        popular_horse_num,
        {},
    )
    .get("秒")
)


# ==================================================
# 🌊 展開馬・消去法ベース候補作成
#
# ここからは「共通TOP5に入った馬だけを候補」にしない。
#
# ① まず全馬から明確な不適合馬を消す
# ② 残った馬だけに、近況・前進・地力・同距離タイム・
#    マーブル脚質の適応度を加点する
# ③ 総合ランキング確定後に最後の総合点を足して決定する
#
# 前進TOP5×地力TOP5は「候補資格」ではなく加点材料。
# マーブル脚質も「最優先条件」ではなく加点材料。
# ==================================================


def judge_tenkai_elimination(
    horse,
    long_distance_info=None,
    relax_recent_losses=False,
):
    """
    展開馬をスコア比較する前の消去判定。

    前へ行ける・昔好走した、という能力は否定しない。
    ただし「今の状態で展開馬として推しづらい」馬を先に落とす。

    強制消去：
    ① 近走前崩れ
       直近3走で前半4番手以内→3つ以上後退が2回以上。

    ② 近走低調
       直近3走のうち8着以下が2回以上、かつ3着以内なし。
       例：9着→8着→5着。

    ③ 直近2走連続大敗
       直近2走がともに8着以下。

    ④ 最新走大失速＋大敗
       最新走の大失速強度が100％で、最新着順も8着以下。

    軸馬自身は別で除外する。
    """

    reasons = []

    if horse.get("近走前崩れ", False):
        reasons.append("近走前崩れ")

    recent_finishes = [
        finish
        for finish in horse.get("着順", [])[:3]
        if isinstance(finish, int)
    ]

    if recent_finishes:
        bottom8_count = sum(
            1
            for finish in recent_finishes
            if finish >= 8
        )

        top3_count = sum(
            1
            for finish in recent_finishes
            if finish <= 3
        )

        long_distance_elimination_rescue = bool(
            long_distance_info
            and long_distance_info.get(
                "消去救済",
                False,
            )
        )

        # 1900m以上で同距離好走歴が強い馬は、
        # 1600〜1800mなど近走着順の悪さだけで
        # 展開候補から即消去しない。
        #
        # ただし「近走前崩れ」と
        # 「最新走大失速＋大敗」は別問題なので残す。
        if (
            not relax_recent_losses
            and not long_distance_elimination_rescue
            and len(recent_finishes) >= 3
            and bottom8_count >= 2
            and top3_count == 0
        ):
            reasons.append(
                "直近3走で8着以下2回以上・3着以内なし"
            )

        if (
            not relax_recent_losses
            and not long_distance_elimination_rescue
            and len(recent_finishes) >= 2
            and recent_finishes[0] >= 8
            and recent_finishes[1] >= 8
        ):
            reasons.append(
                "直近2走連続8着以下"
            )

        if (
            horse.get("直近大失速強度", 0) >= 1.0
            and recent_finishes[0] >= 8
        ):
            reasons.append(
                "最新走大失速＋8着以下"
            )

    # 同じ理由が重なった時は表示を整理する
    unique_reasons = []
    for reason in reasons:
        if reason not in unique_reasons:
            unique_reasons.append(reason)

    return {
        "消去": bool(unique_reasons),
        "理由": unique_reasons,
        "直近着順": recent_finishes,
    }



# ==================================================
# 🛤️ 1900m以上専用・長距離適性救済
#
# 目的：
# 2200mなどの特殊な長距離では、
# 1600〜1800mの近走着順だけで評価を落としすぎず、
# 「今回と同じ距離を実際に走れた実績」を強く見る。
#
# 発動：
# ・今回1900m以上のみ
#
# 主な評価：
# ① 同距離3着以内歴あり
#    → 強加点
#
# ② 同距離5着以内
#    ＋今回と同格以上のクラスで走っている
#    → 強加点
#
# ③ 同距離好走歴がある馬は、
#    近走の悪い着順による展開馬近況減点を弱める。
#
# 重要：
# ・通常距離では一切発動しない
# ・総合F / 地力C / 先行Dそのものは変更しない
# ・展開Bと抑えEの救済材料として使う
# ==================================================

def calc_long_distance_special_info(
    horse,
    current_distance,
    current_class,
):
    """
    1900m以上のレースだけで使う長距離適性情報。

    戻り値：
      発動
      加点
      近況減点倍率
      消去救済
      同距離3着以内回数
      同距離5着以内回数
      同距離・同格以上5着以内回数
      同距離実績
      判定
    """

    default_result = {
        "発動": False,
        "加点": 0,
        "近況減点倍率": 1.0,
        "消去救済": False,
        "同距離3着以内回数": 0,
        "同距離5着以内回数": 0,
        "同距離同格以上5着以内回数": 0,
        "同距離実績": [],
        "判定": "対象外",
    }

    if current_distance < 1900:
        return default_result

    current_class_value = get_race_class_value(
        current_class
    )

    exact_distance_runs = []

    for item in horse.get(
        "距離付きタイム",
        [],
    ):
        if item.get("距離") != current_distance:
            continue

        finish = item.get(
            "着順"
        )

        if not isinstance(
            finish,
            int
        ):
            continue

        past_class = item.get(
            "クラス"
        )

        past_class_value = get_race_class_value(
            past_class
        )

        exact_distance_runs.append({
            "着順": finish,
            "競馬場": item.get(
                "競馬場",
                ""
            ),
            "クラス": past_class,
            "クラス値": past_class_value,
            "タイム": item.get(
                "タイム",
                ""
            ),
            "通過順": item.get(
                "通過順",
                []
            ),
        })

    if not exact_distance_runs:
        return {
            **default_result,
            "発動": True,
            "判定": "同距離実績なし",
        }

    top3_count = sum(
        1
        for item in exact_distance_runs
        if item["着順"] <= 3
    )

    top5_count = sum(
        1
        for item in exact_distance_runs
        if item["着順"] <= 5
    )

    same_or_higher_top5_count = 0

    if current_class_value is not None:

        same_or_higher_top5_count = sum(
            1
            for item in exact_distance_runs
            if (
                item["着順"] <= 5
                and item["クラス値"] is not None
                and item["クラス値"]
                    <= current_class_value
            )
        )

    # ----------------------------------------------
    # 長距離専用加点
    #
    # 同距離3着以内を最優先。
    # 複数回なら再現性としてさらに強く評価。
    #
    # 同距離5着以内＋同格以上クラスも強く救済。
    # ----------------------------------------------
    long_bonus = 0
    recent_negative_factor = 1.0
    elimination_rescue = False
    judgement_parts = []

    if top3_count >= 2:
        long_bonus = 150
        recent_negative_factor = 0.30
        elimination_rescue = True
        judgement_parts.append(
            "同距離3着以内を複数回"
        )

    elif top3_count == 1:
        long_bonus = 115
        recent_negative_factor = 0.40
        elimination_rescue = True
        judgement_parts.append(
            "同距離3着以内あり"
        )

    elif same_or_higher_top5_count >= 1:
        long_bonus = 95
        recent_negative_factor = 0.50
        elimination_rescue = True
        judgement_parts.append(
            "同距離5着以内＋同格以上"
        )

    elif top5_count >= 1:
        long_bonus = 55
        recent_negative_factor = 0.70
        judgement_parts.append(
            "同距離5着以内あり"
        )

    else:
        judgement_parts.append(
            "同距離好走なし"
        )

    # 同格以上の同距離5着以内が複数回ある場合は、
    # 上位クラスでの再現性として追加で少し評価。
    if same_or_higher_top5_count >= 2:
        long_bonus += 25
        judgement_parts.append(
            "同格以上で複数回"
        )

    # 上限を付けて既存ロジックを壊しすぎない。
    long_bonus = min(
        long_bonus,
        175
    )

    return {
        "発動": True,
        "加点": long_bonus,
        "近況減点倍率": recent_negative_factor,
        "消去救済": elimination_rescue,
        "同距離3着以内回数": top3_count,
        "同距離5着以内回数": top5_count,
        "同距離同格以上5着以内回数": (
            same_or_higher_top5_count
        ),
        "同距離実績": exact_distance_runs,
        "判定": "・".join(
            judgement_parts
        ),
    }


def apply_long_distance_recent_relief(
    recent_score,
    long_distance_info,
):
    """
    長距離好走歴がある馬について、
    展開馬の「負の近況点」だけを弱める。

    プラスの近況点はそのまま。
    これにより、近走1600〜1800mで負けた馬を
    2200m実績だけで過剰加点するのではなく、
    「悪い近況を少し割り引いて見る」形にする。
    """

    if recent_score >= 0:
        return recent_score

    factor = long_distance_info.get(
        "近況減点倍率",
        1.0,
    )

    return round(
        recent_score * factor,
        1,
    )


def calc_tenkai_recent_form_score(horse):
    """
    展開馬専用の近況点。

    古い好走より、直近の状態を先に見る。
    最新走ほど強く反映する。
    """

    recent = [
        finish
        for finish in horse.get("着順", [])[:3]
        if isinstance(finish, int)
    ]

    point_table = {
        1: 60,
        2: 50,
        3: 40,
        4: 25,
        5: 15,
        6: 5,
        7: 0,
        8: -20,
        9: -30,
        10: -40,
        11: -45,
        12: -50,
    }

    weights = [
        1.00,
        0.70,
        0.45,
    ]

    score = 0.0

    for idx, finish in enumerate(recent):
        base = point_table.get(
            finish,
            -50 if finish >= 13 else 0,
        )

        weight = (
            weights[idx]
            if idx < len(weights)
            else 0.45
        )

        score += base * weight

    # 直近3走すべて5着以内なら安定感を加点
    if (
        len(recent) == 3
        and all(finish <= 5 for finish in recent)
    ):
        score += 25

    # 直近3走で2回以上3着以内なら好調加点
    if sum(1 for finish in recent if finish <= 3) >= 2:
        score += 20

    return round(score, 1)


def calc_tenkai_rank_bonus(front_rank, long_rank):
    """
    前進・地力順位は「候補資格」ではなく加点。
    圏外でも消さない。
    """

    front_bonus_table = {
        1: 55,
        2: 45,
        3: 35,
        4: 25,
        5: 15,
    }

    long_bonus_table = {
        1: 65,
        2: 52,
        3: 40,
        4: 28,
        5: 18,
    }

    front_bonus = front_bonus_table.get(
        front_rank,
        0,
    )

    long_bonus = long_bonus_table.get(
        long_rank,
        0,
    )

    common_bonus = (
        30
        if (
            front_rank <= 5
            and long_rank <= 5
        )
        else 0
    )

    return {
        "前進加点": front_bonus,
        "地力加点": long_bonus,
        "共通TOP5加点": common_bonus,
        "合計": (
            front_bonus
            + long_bonus
            + common_bonus
        ),
    }


def calc_tenkai_type_match_bonus(candidate_profile):
    """
    軸の主脚質に対して欲しい相手脚質を軽く加点する。

    ここも絶対条件にはしない。
    複数タグを持つマーブル馬は、最も高い一致だけ採用する。
    """

    candidate_tags = set(
        candidate_profile.get(
            "脚質タグ",
            [],
        )
    )

    priorities = tenkai_type_priority.get(
        kyakushoku_type,
        [],
    )

    bonus_by_order = [
        35,
        25,
        15,
        8,
    ]

    for idx, wanted_type in enumerate(priorities):
        if wanted_type not in candidate_tags:
            continue

        bonus = (
            bonus_by_order[idx]
            if idx < len(bonus_by_order)
            else 5
        )

        return {
            "加点": bonus,
            "一致脚質": wanted_type,
        }

    return {
        "加点": 0,
        "一致脚質": "なし",
    }


# ==================================================
# 🏎️ 園田820m専用・展開B距離短縮ボーナス
#
# 820mでは近走着順より、
# 「長い距離で前へ行けていた馬が短縮で前進できるか」を重視する。
#
# 最も強い該当1走だけを採用し、複数走の加点は重ねない。
#
# 301〜600m短縮 ＋ 1角1〜2番手 → +120
# 100〜300m短縮 ＋ 1角1〜2番手 → +80
# 100〜600m短縮 ＋ 1角3〜4番手 → +50
# ==================================================
def calc_sonoda_820_shortening_bonus(
    horse,
    current_distance,
):
    if (
        baba_name != "園田"
        or current_distance != 820
    ):
        return {
            "加点": 0,
            "理由": "対象外",
            "詳細": None,
        }

    best_bonus = 0
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

        if (
            not past_distance
            or len(flow) < 1
        ):
            continue

        shortening = (
            past_distance
            - current_distance
        )

        if not (100 <= shortening <= 600):
            continue

        first = flow[0]
        bonus = 0
        reason = ""

        if (
            301 <= shortening <= 600
            and first <= 2
        ):
            bonus = 120
            reason = "301〜600m短縮＋1角1〜2番手"

        elif (
            100 <= shortening <= 300
            and first <= 2
        ):
            bonus = 80
            reason = "100〜300m短縮＋1角1〜2番手"

        elif first <= 4:
            bonus = 50
            reason = "100〜600m短縮＋1角3〜4番手"

        if bonus > best_bonus:
            best_bonus = bonus
            best_detail = {
                "過去距離": past_distance,
                "今回距離": current_distance,
                "短縮距離": shortening,
                "通過順": flow,
                "理由": reason,
            }

    return {
        "加点": best_bonus,
        "理由": (
            best_detail["理由"]
            if best_detail
            else "該当なし"
        ),
        "詳細": best_detail,
    }


# --------------------------------------------------
# 全馬を一度候補として見る。
# 軸馬と消去対象だけを先に落とす。
#
# 園田820mだけは、
# ・直近3走の大敗条件
# ・直近2走連続大敗条件
# を消去理由から外す。
#
# 近走前崩れと最新走大失速＋大敗は従来どおり残す。
# --------------------------------------------------
tenkai_pre_candidates = []
tenkai_eliminated_candidates = []

for horse in horses:

    horse_no = horse["馬番"]

    if horse_no == popular_horse_num:
        continue

    long_distance_info = (
        calc_long_distance_special_info(
            horse,
            distance_num,
            current_race_class,
        )
    )

    sonoda_820_relax = (
        baba_name == "園田"
        and distance_num == 820
    )

    elimination = judge_tenkai_elimination(
        horse,
        long_distance_info=long_distance_info,
        relax_recent_losses=sonoda_820_relax,
    )

    if elimination["消去"]:
        tenkai_eliminated_candidates.append({
            "馬番": horse_no,
            "馬名": horse["馬名"],
            "理由": elimination["理由"],
            "直近着順": elimination["直近着順"],
        })
        continue

    style_info = classify_tenkai_candidate(
        horse
    )

    marble_fit = calc_marble_tenkai_fit(
        axis_marble_profile,
        style_info,
    )

    front_rank = front_rank_map_for_tenkai.get(
        horse_no,
        99,
    )

    long_rank = long_rank_map_for_tenkai.get(
        horse_no,
        99,
    )

    rank_bonus = calc_tenkai_rank_bonus(
        front_rank,
        long_rank,
    )

    type_match = calc_tenkai_type_match_bonus(
        style_info
    )

    recent_form_score = calc_tenkai_recent_form_score(
        horse
    )

    # 1900m以上で同距離好走歴がある場合だけ、
    # 負の近況点を弱める。
    long_distance_recent_score = (
        apply_long_distance_recent_relief(
            recent_form_score,
            long_distance_info,
        )
    )

    # マーブル適応点は上限を付けて50％だけ反映する。
    # これで「タグが多いだけ」の馬が近況を無視して
    # 一気に展開1位になるのを防ぐ。
    raw_marble_fit_score = max(
        0,
        marble_fit.get("スコア", 0),
    )

    marble_bonus = round(
        min(
            raw_marble_fit_score,
            120,
        )
        * 0.50,
        1,
    )

    time_rank = tenkai_time_rank_map.get(
        horse_no,
        99,
    )

    if time_rank <= 3:
        time_bonus = 25
    elif time_rank <= 5:
        time_bonus = 12
    else:
        time_bonus = 0

    # --------------------------------------------------
    # 強制消去まではしないリスクは減点で扱う。
    # --------------------------------------------------
    risk_penalty = 0
    risk_reasons = []

    if horse_no in shissoku_heavy_horse_numbers:
        risk_penalty += 45
        risk_reasons.append("反復失速")

    if horse.get("徐々垂れ", False):
        risk_penalty += 25
        risk_reasons.append("徐々垂れ")

    if horse.get("踏ん張り不足", False):
        risk_penalty += 20
        risk_reasons.append("踏ん張り不足")

    if horse.get("直近大失速強度", 0) >= 0.6:
        risk_penalty += 25
        risk_reasons.append("直近大失速")

    # ==================================================
    # 🌊 展開馬専用クラス補正
    #
    # クラス差で直接馬を消さない。
    #
    # 今回より下級中心の馬だけ、
    # ・近況
    # ・前進順位加点
    # ・地力順位加点
    # ・共通TOP5加点
    #
    # の「プラス材料」を割り引く。
    #
    # 脚質・マーブル・同距離タイム・リスクは
    # クラス補正の対象外。
    #
    # これにより展開馬Bだけを調整し、
    # 総合F・地力C・先行D・抑えEは変えない。
    # ==================================================
    class_adjustment = (
        calc_tenkai_class_adjustment(
            horse,
            current_race_class,
            distance_num,
        )
    )

    class_factor = (
        class_adjustment[
            "係数"
        ]
    )

    class_experience_bonus = (
        class_adjustment[
            "経験加点"
        ]
    )

    recent_score_before_cap = (
        apply_positive_class_factor(
            long_distance_recent_score,
            class_factor,
        )
    )

    # 展開Bは「近況の良さ」だけで1位にならないよう、
    # プラスの近況点だけ最大+60に制限する。
    # マイナス点は従来どおりそのまま残す。
    adjusted_recent_form_score = (
        min(
            recent_score_before_cap,
            60,
        )
        if recent_score_before_cap > 0
        else recent_score_before_cap
    )

    adjusted_front_bonus = (
        apply_positive_class_factor(
            rank_bonus[
                "前進加点"
            ],
            class_factor,
        )
    )

    adjusted_long_bonus = (
        apply_positive_class_factor(
            rank_bonus[
                "地力加点"
            ],
            class_factor,
        )
    )

    adjusted_common_bonus = (
        apply_positive_class_factor(
            rank_bonus[
                "共通TOP5加点"
            ],
            class_factor,
        )
    )

    adjusted_rank_bonus_total = (
        adjusted_front_bonus
        + adjusted_long_bonus
        + adjusted_common_bonus
    )

    long_distance_bonus = (
        long_distance_info.get(
            "加点",
            0,
        )
    )

    sonoda_820_shortening_info = (
        calc_sonoda_820_shortening_bonus(
            horse,
            distance_num,
        )
    )

    sonoda_820_shortening_bonus = (
        sonoda_820_shortening_info[
            "加点"
        ]
    )

    preliminary_score = round(
        adjusted_recent_form_score
        + adjusted_rank_bonus_total
        + type_match["加点"]
        + marble_bonus
        + time_bonus
        + class_experience_bonus
        + long_distance_bonus
        + sonoda_820_shortening_bonus
        - risk_penalty,
        1,
    )

    tenkai_pre_candidates.append({
        "馬番": horse_no,
        "馬名": horse["馬名"],
        "候補脚質": style_info["候補脚質"],
        "主脚質": style_info["主脚質"],
        "副脚質": style_info["副脚質"],
        "副脚質表示": style_info["副脚質表示"],
        "脚質タグ": style_info["脚質タグ"],
        "マーブル度": style_info["マーブル度"],
        "脚質能力点": style_info["能力点"],
        "展開適応点": raw_marble_fit_score,
        "展開適応加点": marble_bonus,
        "展開適応理由": marble_fit.get("理由", []),
        "前進順位": front_rank,
        "地力順位": long_rank,
        "順位合計": front_rank + long_rank,
        # クラス補正後に実際に使った点
        "前進加点": adjusted_front_bonus,
        "地力加点": adjusted_long_bonus,
        "共通TOP5加点": adjusted_common_bonus,
        "近況点": adjusted_recent_form_score,

        # デバッグ確認用の補正前点
        "前進元加点": rank_bonus["前進加点"],
        "地力元加点": rank_bonus["地力加点"],
        "共通元加点": rank_bonus["共通TOP5加点"],
        "近況元点": recent_form_score,
        "近況上限前点": recent_score_before_cap,
        "長距離補正前近況点": recent_form_score,
        "長距離補正後近況点": long_distance_recent_score,

        # 1900m以上専用・同距離適性
        "長距離適性加点": long_distance_bonus,
        "長距離適性判定": long_distance_info.get(
            "判定",
            "対象外",
        ),

        # 園田820m専用
        "園田820短縮加点": sonoda_820_shortening_bonus,
        "園田820短縮理由": (
            sonoda_820_shortening_info[
                "理由"
            ]
        ),
        "園田820短縮詳細": (
            sonoda_820_shortening_info[
                "詳細"
            ]
        ),
        "園田820消去緩和": sonoda_820_relax,

        "長距離同距離3着以内回数": long_distance_info.get(
            "同距離3着以内回数",
            0,
        ),
        "長距離同距離5着以内回数": long_distance_info.get(
            "同距離5着以内回数",
            0,
        ),
        "長距離同距離同格以上5着以内回数": (
            long_distance_info.get(
                "同距離同格以上5着以内回数",
                0,
            )
        ),
        "長距離同距離実績": long_distance_info.get(
            "同距離実績",
            [],
        ),

        # 展開馬専用クラス補正
        "クラス係数": class_factor,
        "クラス経験加点": class_experience_bonus,
        "クラス同格以上回数": class_adjustment[
            "同格以上回数"
        ],
        "クラス格上回数": class_adjustment.get(
            "格上回数",
            0,
        ),
        "クラス格上同距離回数": class_adjustment.get(
            "格上同距離回数",
            0,
        ),
        "クラス最上位差": class_adjustment.get(
            "最上位クラス差"
        ),
        "クラス平均差": class_adjustment[
            "平均クラス差"
        ],
        "過去クラス": class_adjustment[
            "過去クラス"
        ],
        "クラス判定": class_adjustment[
            "判定"
        ],

        "脚質一致加点": type_match["加点"],
        "脚質一致": type_match["一致脚質"],
        "展開タイム順位": time_rank,
        "展開タイム加点": time_bonus,
        "展開同距離タイム秒": (
            tenkai_same_distance_time_info
            .get(horse_no, {})
            .get("秒")
        ),
        "展開タイムモード": (
            tenkai_same_distance_time_info
            .get(horse_no, {})
            .get(
                "モード",
                "同距離タイムなし",
            )
        ),
        "展開軸タイム差": (
            (
                tenkai_same_distance_time_info
                .get(horse_no, {})
                .get("秒")
                - axis_tenkai_time
            )
            if (
                axis_tenkai_time is not None
                and tenkai_same_distance_time_info
                .get(horse_no, {})
                .get("秒") is not None
            )
            else None
        ),
        "リスク減点": risk_penalty,
        "リスク理由": risk_reasons,
        "近走前崩れ": style_info.get(
            "近走前崩れ",
            False,
        ),
        "平均前半": style_info.get(
            "平均前半",
            99,
        ),
        "平均4角": style_info.get(
            "平均4角",
            99,
        ),
        "逃げ率": style_info.get(
            "逃げ率",
            0,
        ),
        "前団回数": style_info.get(
            "前団回数",
            0,
        ),
        "持続回数": style_info.get(
            "持続回数",
            0,
        ),
        "押し上げ回数": style_info.get(
            "押し上げ回数",
            0,
        ),
        "予備展開点": preliminary_score,
        "選出元": "消去法＋適応スコア",
    })


# 総合ランキング確定後に最終点を加えるため、
# この段階ではまだ展開馬を確定しない。
tenkai_selection_source = "消去法＋適応スコア"

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
# 総合タイム評価用・NAR最高タイム救済の準備
#
# 過去走の同距離タイム評価が弱い／0点でも、
# NAR出馬表に表示される当距離の「最高タイム」を
# 補助評価として使えるようにする。
#
# ・最高タイムを持つ馬が2頭以上いる時だけ有効
# ・最も遅い最高タイムを0点基準
# ・1秒速いごとに70点
# ・最大70点
#
# 通常の同距離タイム点と比較し、高い方だけを採用する。
# 二重加点はしない。
# ==================================================
display_best_time_map = {
    h["馬番"]: h.get("最高タイム秒")
    for h in horses
    if h.get("最高タイム秒") is not None
}

if len(display_best_time_map) >= 2:
    slowest_display_best_time = max(
        display_best_time_map.values()
    )
else:
    slowest_display_best_time = None
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
        # ==================================================
        # 高知限定・持ちタイム強化
        #
        # 高知は同距離の持ち時計を通常の1.25倍で評価する。
        # 他会場には一切影響しない。
        # ==================================================
        if baba_name == "高知":
            time_score *= 1.25

        total_score += time_score

        debug_total_parts[
            "持ちタイム"
        ] += time_score

    # ==================================================
    # NAR最高タイムによる持ちタイム救済
    #
    # 通常の同距離タイム点とNAR最高タイム点を比較し、
    # 高い方を最終的な「持ちタイム」評価として採用する。
    #
    # すでに通常タイム点を加算している場合は、
    # 最高タイム点との差額だけを追加して二重加点を防ぐ。
    # ==================================================
    if slowest_display_best_time is not None:

        display_best_time = (
            display_best_time_map.get(
                horse_no
            )
        )

        if display_best_time is not None:

            # 最も遅い最高タイムとの差。
            # 秒数が小さいほど速いので、差が大きいほど高評価。
            display_time_advantage = max(
                0,
                slowest_display_best_time
                - display_best_time
            )

            # 1秒速いごとに70点。
            # 最高タイムだけで総合を壊さないよう最大70点。
            display_time_score = min(
                70,
                display_time_advantage * 70
            )

            # 通常タイム点より最高タイム点の方が高い場合だけ、
            # 差額を加えて最終タイム点を置き換える。
            if display_time_score > time_score:

                extra_time_score = (
                    display_time_score
                    - time_score
                )

                total_score += extra_time_score

                debug_total_parts[
                    "持ちタイム"
                ] += extra_time_score

                time_score = display_time_score
                best_time = display_best_time
                time_weight = 1.0
                time_diff = (
                    -display_time_advantage
                )
                used_times = [
                    display_best_time
                ]

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
# ⚔️ 後詰め軸・全R一括検証
#
# 思想：
# ・まず通常どおりNAR1番人気をAにして分析する
# ・その時点の後詰めF（総合1位）を確定する
# ・AとFが一致するかどうかを記録する
# ・A≠Fなら同じRをもう一度走らせ、
#   Fを新しいAとして全ロジック・買い目を再計算する
#
# AとFが一致していても問題なし。
# 一致時は今の計算結果がそのまま「後詰め軸」の結果になる。
# ==================================================
if (
    st.session_state.batch_mode
    and st.session_state.batch_axis_mode == "backfill"
):

    is_second_backfill_pass = (
        st.session_state.batch_axis_override_num is not None
        and st.session_state.batch_axis_override_race == int(race_no)
    )

    if not is_second_backfill_pass:

        original_a_num = int(
            popular_horse_num
        )

        original_f_num = int(
            total_best["馬番"]
        )

        af_match = (
            original_a_num
            == original_f_num
        )

        st.session_state.batch_original_a = (
            original_a_num
        )

        st.session_state.batch_original_f = (
            original_f_num
        )

        st.session_state.batch_af_match = (
            af_match
        )

        # AとFが違う場合だけ、
        # FをAへ差し替えて同じレースを最初から再計算する。
        if not af_match:

            st.session_state.batch_axis_override_num = (
                original_f_num
            )

            st.session_state.batch_axis_override_race = (
                int(race_no)
            )

            st.rerun()

        # A=Fなら現在の計算がそのまま後詰め軸計算。
        # overrideは作らず、このまま買い目・回収率まで進む。


# ==================================================
# 🌊 展開馬の最終決定・消去法一本化
#
# ① 事前消去を通過した馬だけを対象
# ② 近況プラスは最大+60まで
# ③ 総合順位は加点せず、同点時のタイブレークだけ
# ④ 格上クラス経験を明確に加点する
# ⑤ 最終点の高い順に展開馬を決める
# ==================================================

tenkai_candidates = []

for candidate in tenkai_pre_candidates:

    horse_no = candidate["馬番"]

    total_rank = final_total_rank_map.get(
        horse_no,
        99,
    )

    # 総合Fと展開Bの役割を明確に分ける。
    # 総合順位は展開点へ一切加点しない。
    # 同点時のタイブレークとしてだけ後段の並び替えで使う。
    total_rank_bonus = 0

    final_tenkai_score = round(
        candidate["予備展開点"]
        + total_rank_bonus,
        1,
    )

    candidate = dict(candidate)

    candidate["最終総合順位"] = total_rank
    candidate["総合順位加点"] = total_rank_bonus
    candidate["展開最終点"] = final_tenkai_score

    # 既存の後段処理は "スコア" を参照するため、
    # ここで最終展開点を統一スコアとして入れる。
    candidate["スコア"] = final_tenkai_score

    tenkai_candidates.append(
        candidate
    )


# 高い順。
# 展開最終点が同点の時だけ総合順位をタイブレークに使う。
# それでも同じなら近況 → 地力順位 → 前進順位で決める。
tenkai_candidates = sorted(
    tenkai_candidates,
    key=lambda h: (
        -h.get("展開最終点", -9999),
        h.get("最終総合順位", 99),
        -h.get("近況点", -9999),
        h.get("地力順位", 99),
        h.get("前進順位", 99),
        h.get("馬番", 99),
    ),
)


# 万一、消去条件が厳しすぎて全馬消えた時だけ、
# 強制消去を緩めて「近走前崩れ」以外から救済する。
# 通常時には発動しない安全網。
if not tenkai_candidates:

    emergency_candidates = []

    for horse in horses:

        horse_no = horse["馬番"]

        if horse_no == popular_horse_num:
            continue

        # 近走前崩れだけは最後まで展開馬へ戻さない。
        if horse.get("近走前崩れ", False):
            continue

        style_info = classify_tenkai_candidate(
            horse
        )

        marble_fit = calc_marble_tenkai_fit(
            axis_marble_profile,
            style_info,
        )

        total_rank = final_total_rank_map.get(
            horse_no,
            99,
        )

        front_rank = front_rank_map_for_tenkai.get(
            horse_no,
            99,
        )

        long_rank = long_rank_map_for_tenkai.get(
            horse_no,
            99,
        )

        rescue_class_adjustment = (
            calc_tenkai_class_adjustment(
                horse,
                current_race_class,
                distance_num,
            )
        )

        rescue_recent_score = (
            calc_tenkai_recent_form_score(
                horse
            )
        )

        rescue_recent_score = (
            apply_positive_class_factor(
                rescue_recent_score,
                rescue_class_adjustment[
                    "係数"
                ],
            )
        )

        if rescue_recent_score > 0:
            rescue_recent_score = min(
                rescue_recent_score,
                60,
            )

        rescue_score = (
            rescue_recent_score
            + max(
                0,
                min(
                    marble_fit.get("スコア", 0),
                    100,
                )
                * 0.30,
            )
            + 0  # 総合順位は緊急救済でも加点しない
            + rescue_class_adjustment[
                "経験加点"
            ]
        )

        emergency_candidates.append({
            "馬番": horse_no,
            "馬名": horse["馬名"],
            "スコア": round(rescue_score, 1),
            "展開最終点": round(rescue_score, 1),
            "候補脚質": style_info.get("候補脚質", "展開待ち"),
            "主脚質": style_info.get("主脚質", "展開待ち"),
            "副脚質": style_info.get("副脚質", []),
            "副脚質表示": style_info.get("副脚質表示", "なし"),
            "脚質タグ": style_info.get("脚質タグ", []),
            "マーブル度": style_info.get("マーブル度", 0),
            "脚質能力点": style_info.get("能力点", {}),
            "展開適応点": marble_fit.get("スコア", 0),
            "展開適応加点": 0,
            "展開適応理由": marble_fit.get("理由", []),
            "前進順位": front_rank,
            "地力順位": long_rank,
            "順位合計": front_rank + long_rank,
            "近況点": rescue_recent_score,
            "近況元点": calc_tenkai_recent_form_score(horse),
            "クラス係数": rescue_class_adjustment["係数"],
            "クラス経験加点": rescue_class_adjustment["経験加点"],
            "クラス同格以上回数": rescue_class_adjustment[
                "同格以上回数"
            ],
            "クラス格上回数": rescue_class_adjustment.get(
                "格上回数",
                0,
            ),
            "クラス格上同距離回数": rescue_class_adjustment.get(
                "格上同距離回数",
                0,
            ),
            "クラス最上位差": rescue_class_adjustment.get(
                "最上位クラス差"
            ),
            "クラス平均差": rescue_class_adjustment[
                "平均クラス差"
            ],
            "過去クラス": rescue_class_adjustment["過去クラス"],
            "クラス判定": rescue_class_adjustment["判定"],
            "最終総合順位": total_rank,
            "押し上げ回数": style_info.get("押し上げ回数", 0),
            "選出元": "緊急救済",
        })

    tenkai_candidates = sorted(
        emergency_candidates,
        key=lambda h: (
            -h.get("展開最終点", -9999),
            h.get("最終総合順位", 99),
            h.get("地力順位", 99),
        ),
    )

    tenkai_selection_source = "緊急救済"


if not tenkai_candidates:
    st.error(
        "展開馬候補を作成できませんでした"
    )
    st.stop()


# 展開馬を最終決定
tenkai_final_candidates = tenkai_candidates

tenkai_best = tenkai_final_candidates[0]

# ==================================================
# 岩手限定（盛岡・水沢）・展開B＝K
#
# 岩手では軸タイプに関係なく、
# 展開馬Bを「3角→4角【勝負所重視】押上ランキング」
# の最上位馬から採用する。
#
# Kの元ランキング1位が軸Aと同じ場合は、
# 2位→3位→…へ順送りして最初の別馬を採用する。
#
# 目的：
# ・岩手だけ、通常の展開適応スコアより
#   勝負所で実際に位置を上げる能力を優先する。
# ・他会場の展開Bロジックは一切変更しない。
#
# 後段の三連複B候補も同じKランキング順に揃える。
# ==================================================
iwate_k_tenkai_candidates = []
iwate_tenkai_uses_k = False

if baba_name in {
    "盛岡",
    "水沢",
}:
    for push_h in corner_push_3to4:
        push_no = push_h.get(
            "馬番"
        )

        # 展開Bは軸A自身にはしない。
        if push_no == popular_horse_num:
            continue

        horse_data_for_k = next(
            (
                h
                for h in horses
                if h["馬番"] == push_no
            ),
            None,
        )

        if horse_data_for_k is None:
            continue

        style_info_for_k = (
            classify_tenkai_candidate(
                horse_data_for_k
            )
        )

        k_row = {
            "馬番": push_no,
            "馬名": push_h.get(
                "馬名",
                horse_data_for_k.get(
                    "馬名",
                    "",
                ),
            ),
            # 岩手では展開表示のスコアも
            # Kの3→4押上スコアを基準にする。
            "スコア": push_h.get(
                "スコア",
                0,
            ),
            "展開最終点": push_h.get(
                "スコア",
                0,
            ),
            "K押上順位元": True,
            **style_info_for_k,
        }

        iwate_k_tenkai_candidates.append(
            k_row
        )

    if iwate_k_tenkai_candidates:
        iwate_tenkai_uses_k = True

        tenkai_best = (
            iwate_k_tenkai_candidates[0]
        )

        # デバッグの最終展開候補も、
        # 岩手ではKランキングを先頭に見せる。
        k_numbers = {
            h["馬番"]
            for h in iwate_k_tenkai_candidates
        }

        tenkai_final_candidates = (
            iwate_k_tenkai_candidates
            + [
                h
                for h in tenkai_candidates
                if h["馬番"] not in k_numbers
            ]
        )

        tenkai_selection_source = (
            "岩手K＝3→4押上固定"
        )

# ==================================================
# 大井限定・軸に「持続」が含まれる時の展開B
#
# 主脚質または副脚質に「持続」が1つでも含まれる場合、
# 展開候補を「前進TOP5 ∩ 地力TOP5＝共通TOP5」に限定する。
#
# 共通TOP5内の順位は、既存の展開最終点ランキング順をそのまま使う。
# 例：共通TOP5の展開順位が 1番 → 13番 → 15番 なら、
#   B＝1位の1番
#   J＝2位の13番（後段で設定）
# とする。
#
# 主：先行｜副：持続 のようなマーブル軸でも発動する。
# 他会場・大井の持続非該当軸には影響させない。
# ==================================================
oi_axis_has_sustain = (
    baba_name == "大井"
    and (
        axis_marble_profile.get(
            "主脚質",
            kyakushoku_type,
        ) == "持続"
        or "持続" in set(
            axis_marble_profile.get(
                "副脚質",
                [],
            )
        )
    )
)

oi_common_tenkai_candidates = []
oi_tenkai_uses_common_top5 = False

if oi_axis_has_sustain:
    oi_common_tenkai_candidates = [
        h
        for h in tenkai_candidates
        if h.get("馬番")
        in common_top5_numbers_for_tenkai
    ]

    if oi_common_tenkai_candidates:
        oi_tenkai_uses_common_top5 = True

        # 展開Bは共通TOP5内の1位。
        tenkai_best = (
            oi_common_tenkai_candidates[0]
        )

        # デバッグ等の最終候補も、共通TOP5勢を先頭へ並べる。
        oi_common_numbers = {
            h["馬番"]
            for h in oi_common_tenkai_candidates
        }

        tenkai_final_candidates = (
            oi_common_tenkai_candidates
            + [
                h
                for h in tenkai_candidates
                if h["馬番"]
                not in oi_common_numbers
            ]
        )

        tenkai_selection_source = (
            "大井・軸持続含む＝共通TOP5固定"
        )

selected_target_type = tenkai_best.get(
    "主脚質",
    tenkai_best.get(
        "候補脚質",
        "不明",
    ),
)

tenkai_horse = (
    f"{tenkai_best['馬番']}番 "
    f"{tenkai_best['馬名']}"
)


# デバッグ時は「誰を消したか」と「残った馬の点数内訳」を見せる。
if debug_mode:

    with st.expander(
        "🧹 展開馬・消去法チェック",
        expanded=False,
    ):

        if tenkai_eliminated_candidates:

            st.markdown("#### 消去馬")

            for h in tenkai_eliminated_candidates:
                st.write(
                    f"❌ {h['馬番']}番 {h['馬名']} "
                    f"｜直近 {h.get('直近着順', [])} "
                    f"｜{', '.join(h.get('理由', []))}"
                )

        else:
            st.write("消去馬なし")

        st.markdown("#### 残存候補")

        for rank, h in enumerate(
            tenkai_candidates[:8],
            start=1,
        ):
            st.write(
                f"{rank}位｜{h['馬番']}番 {h['馬名']} "
                f"｜最終 {round(h.get('展開最終点', 0), 1)} "
                f"｜近況 {round(h.get('近況点', 0), 1)} "
                f"｜前進+{h.get('前進加点', 0)} "
                f"｜地力+{h.get('地力加点', 0)} "
                f"｜共通+{h.get('共通TOP5加点', 0)} "
                f"｜脚質+{h.get('脚質一致加点', 0)} "
                f"｜マーブル+{h.get('展開適応加点', 0)} "
                f"｜タイム+{h.get('展開タイム加点', 0)} "
                f"｜クラス×{h.get('クラス係数', 1.0)} "
                f"+{h.get('クラス経験加点', 0)} "
                f"(格上{h.get('クラス格上回数', 0)}回/"
                f"同距離{h.get('クラス格上同距離回数', 0)}回) "
                f"｜長距離+{h.get('長距離適性加点', 0)} "
                f"｜総合+{h.get('総合順位加点', 0)} "
                f"｜リスク-{h.get('リスク減点', 0)}"
            )

            st.caption(
                f"{format_marble_style(h)} "
                f"｜クラス：{h.get('クラス判定', '判定なし')} "
                f"｜過去クラス：{h.get('過去クラス', [])} "
                f"｜最上位差：{h.get('クラス最上位差')} "
                f"｜長距離：{h.get('長距離適性判定', '対象外')} "
                f"｜同距離3着内{h.get('長距離同距離3着以内回数', 0)}回 "
                f"｜同距離5着内{h.get('長距離同距離5着以内回数', 0)}回 "
                f"｜補正前 "
                f"近況{h.get('近況元点', h.get('近況点', 0))} "
                f"→上限前{h.get('近況上限前点', h.get('近況点', 0))} "
                f"→採用{h.get('近況点', 0)} "
                f"前進+{h.get('前進元加点', h.get('前進加点', 0))} "
                f"地力+{h.get('地力元加点', h.get('地力加点', 0))} "
                f"共通+{h.get('共通元加点', h.get('共通TOP5加点', 0))} "
                f"｜適応理由：{h.get('展開適応理由', [])} "
                f"｜リスク理由：{h.get('リスク理由', [])}"
            )


# 三連複Bの繰り下げ候補。
#
# 通常会場：最終の展開ランキング順。
# 岩手    ：B＝Kとするため、3→4押上ランキング順。
if oi_tenkai_uses_common_top5:
    tenkai_rank_source_for_trio = (
        oi_common_tenkai_candidates
    )
elif iwate_tenkai_uses_k:
    tenkai_rank_source_for_trio = (
        iwate_k_tenkai_candidates
    )
else:
    tenkai_rank_source_for_trio = (
        tenkai_candidates
    )

tenkai_rank_for_trio = [
    {
        "馬番": h["馬番"],
        "馬名": h["馬名"],
    }
    for h in tenkai_rank_source_for_trio
]


if debug_mode:

    with st.expander(
        "🌊 新・展開馬ランキング",
        expanded=False,
    ):

        st.write(
            f"軸タイプ：**{kyakushoku_type}** "
            f"｜{format_marble_style(axis_marble_profile)} "
            f"｜選出元：**{tenkai_selection_source}** "
            f"｜採用能力："
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

        if oi_tenkai_uses_common_top5:
            oi_common_rank_text = (
                " → ".join(
                    f"{h['馬番']}番"
                    for h in oi_common_tenkai_candidates
                )
            )

            st.write(
                "大井・持続系 共通TOP5展開順位："
                + oi_common_rank_text
            )

            if len(oi_common_tenkai_candidates) >= 2:
                oi_j_debug_horse = (
                    oi_common_tenkai_candidates[1]
                )
                st.write(
                    "J＝共通TOP5展開2位："
                    f"{oi_j_debug_horse['馬番']}番 "
                    f"{oi_j_debug_horse['馬名']}"
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
                f"｜主 {h.get('主脚質', h.get('候補脚質', '不明'))} "
                f"｜副 {h.get('副脚質表示', 'なし')} "
                f"｜適応 {round(h.get('展開適応点', 0), 1)} "
                f"｜前進 {front_rank_text}位 "
                f"｜地力 {long_rank_text}位 "
                f"｜総合 "
                f"{h.get('最終総合順位', 99)}位 "
                f"｜選出元 {h.get('選出元', '')}"
            )

            if h.get(
                "展開適応理由"
            ):
                st.caption(
                    f"適応理由："
                    f"{h.get('展開適応理由', [])} "
                    f"｜能力点："
                    f"{h.get('脚質能力点', {})}"
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
            "通常より下がります。\n\n"
            "※JRA転入馬への軸替えでハマる場合がありますので"
            "買い目の確認を推奨しています。"
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
                f"｜主 {h.get('主脚質', h.get('候補脚質', '不明'))} "
                f"｜副 {h.get('副脚質表示', 'なし')} "
                f"｜適応 {round(h.get('展開適応点', 0), 1)} "
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
    # 1900m以上専用・長距離適性
    #
    # 展開Bだけでなく、主要5役から漏れた長距離巧者を
    # 抑えE側でも拾えるようにする。
    # --------------------------------------------------
    ana_long_distance_info = (
        calc_long_distance_special_info(
            target_horse,
            distance_num,
            current_race_class,
        )
        if target_horse
        else {
            "加点": 0,
            "判定": "対象外",
            "同距離3着以内回数": 0,
            "同距離5着以内回数": 0,
            "同距離同格以上5着以内回数": 0,
        }
    )

    # 抑えでは展開馬ほど強くしすぎないよう、
    # 長距離適性点の80％を使用する。
    ana_long_distance_bonus = round(
        ana_long_distance_info.get(
            "加点",
            0,
        )
        * 0.80,
        1,
    )

    ana_score += ana_long_distance_bonus

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

        # 1900m以上専用・長距離適性
        "抑え長距離適性加点": ana_long_distance_bonus,
        "抑え長距離適性判定": ana_long_distance_info.get(
            "判定",
            "対象外",
        ),
        "抑え長距離同距離3着以内回数": (
            ana_long_distance_info.get(
                "同距離3着以内回数",
                0,
            )
        ),
        "抑え長距離同距離5着以内回数": (
            ana_long_distance_info.get(
                "同距離5着以内回数",
                0,
            )
        ),
        "抑え長距離同格以上5着以内回数": (
            ana_long_distance_info.get(
                "同距離同格以上5着以内回数",
                0,
            )
        ),

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
# 1900m以上・長距離適性馬を抑え候補へ救済
#
# 同距離3着以内、
# または同距離5着以内＋同格以上経験がある馬が、
# 主要5役に出ず通常抑え候補からも漏れた時に復活させる。
#
# これにより2200mなどで、
# 近走1600〜1800mの着順が悪いだけの長距離巧者を
# 完全に消さない。
# ==================================================

long_distance_special_watch_numbers = set()
long_distance_special_watch_info = {}

if distance_num >= 1900:

    for horse in horses:

        horse_no = horse["馬番"]

        info = calc_long_distance_special_info(
            horse,
            distance_num,
            current_race_class,
        )

        is_strong_long_watch = (
            info.get(
                "同距離3着以内回数",
                0,
            ) >= 1
            or info.get(
                "同距離同格以上5着以内回数",
                0,
            ) >= 1
        )

        if not is_strong_long_watch:
            continue

        long_distance_special_watch_numbers.add(
            horse_no
        )

        long_distance_special_watch_info[
            horse_no
        ] = info

        # 主要5役に出ている馬は、
        # その役割を優先して抑えへ重複させない。
        if horse_no in used_for_ana:
            continue

        existing_long_candidate = next(
            (
                candidate
                for candidate in ana_candidates
                if candidate["馬番"] == horse_no
            ),
            None,
        )

        rescue_score = round(
            info.get(
                "加点",
                0,
            )
            * 0.80,
            1,
        )

        if existing_long_candidate is not None:

            # すでに抑え候補にいる場合は、
            # 長距離救済印と加点だけ追加。
            existing_long_candidate[
                "長距離適性救済"
            ] = True

            existing_long_candidate[
                "抑え長距離適性加点"
            ] = max(
                existing_long_candidate.get(
                    "抑え長距離適性加点",
                    0,
                ),
                rescue_score,
            )

            existing_long_candidate[
                "抑え長距離適性判定"
            ] = info.get(
                "判定",
                "長距離適性",
            )

        else:

            ana_candidates.append({
                "馬番": horse_no,
                "馬名": horse["馬名"],
                "スコア": rescue_score,
                "長距離適性救済": True,
                "抑え長距離適性加点": rescue_score,
                "抑え長距離適性判定": info.get(
                    "判定",
                    "長距離適性",
                ),
                "抑え長距離同距離3着以内回数": (
                    info.get(
                        "同距離3着以内回数",
                        0,
                    )
                ),
                "抑え長距離同距離5着以内回数": (
                    info.get(
                        "同距離5着以内回数",
                        0,
                    )
                ),
                "抑え長距離同格以上5着以内回数": (
                    info.get(
                        "同距離同格以上5着以内回数",
                        0,
                    )
                ),
            })

# 既存候補にも救済印を統一して付ける
for candidate in ana_candidates:

    candidate["長距離適性救済"] = (
        candidate["馬番"]
        in long_distance_special_watch_numbers
        and candidate["馬番"]
        not in used_for_ana
    )


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

        # 1900m以上では同距離長距離適性救済を優先
        x.get(
            "長距離適性救済",
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
    with st.expander(
        "⭐ 抑え候補スコア",
        expanded=False,
    ):

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
    format_marble_style(
        axis_marble_profile
    ),
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

# 園田では後段でM候補が確定してから、
# この場所に「展開の向く馬」を描画する。
# 園田・差し軸だけは従来の展開馬Bを表示する。
tenkai_card_placeholder = st.empty()

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
# 斬り捨て御免馬の入力欄は廃止。
# 後段の既存買い目生成は変えず、除外対象だけ常に空にする。
kirisute_horse_numbers = set()
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
# J：大井・持続を含む軸では共通TOP5展開2位／それ以外は前進気勢3位
# K：3角→4角【勝負所重視】押上ランキング1位（全会場共通）
# L：2角→4角【総合押上】ランキング1位
#    （会場別A-B-L／佐賀先行軸／園田先行＋押上軸／岩手前受け軸で使用）
# M：園田専用・中間重複馬
#    総合・地力・前進・抑え・3→4押上・2→4押上の
#    2〜5位に複数回入る馬を重複度で評価する。
#
# 異なる記号が同じ馬になった場合の優先順位：
# A → B → F → C → E → D → G → I → J → K → L → M
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
            ["A", "B", "D"],
            ["A", "C", "G"],
        ],
        "ワイド": [
            ["A", "B"],
            ["A", "E"],
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
            ["E", "D"],
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
# 会場別ルールを安全に適用するため、
# 元テンプレートを直接変更しないよう最初にコピーする。
# ==================================================
current_bet_template = {
    bet_type: [
        bet[:] for bet in bets
    ]
    for bet_type, bets
    in current_bet_template.items()
}

axis_secondary_for_bet = (
    axis_marble_profile.get(
        "副脚質表示",
        "なし",
    )
)

# ==================================================
# 岩手（盛岡・水沢）・前受け能力を持つ軸
#
# 主脚質または副脚質のどこかに
# 「逃げ」「先行」のどちらかが入っていれば発動対象。
#
# 例：
# ・主：先行｜副：持続 → 対象
# ・主：持続｜副：先行 → 対象
# ・主：逃げ｜副：押上   → 対象
# ・主：差し｜副：持続   → 対象外
# ==================================================
axis_primary_for_bet = axis_marble_profile.get(
    "主脚質",
    kyakushoku_type,
)

axis_secondary_tags_for_bet = set(
    axis_marble_profile.get(
        "副脚質",
        [],
    )
)

# ==================================================
# 買い目用・軸タイプ3分類
#
# 既存の脚質判定（kyakushoku_type）は変更しない。
# 買い目表を会場別に整理するためだけに、
# 逃げ・先行を「前受け」へまとめる。
#
# ・逃げ／先行 → 前受け
# ・持続       → 持続
# ・差し／展開待ち → 差し
#
# 「展開待ち」は正式な3分類では「差し」へまとめる。
# ここでは分類名を作るだけで、既存買い目は変更しない。
# ==================================================
def classify_bet_axis_type(axis_type):
    if axis_type in {
        "逃げ",
        "先行",
    }:
        return "前受け"

    if axis_type in {
        "差し",
        "展開待ち",
    }:
        return "差し"

    return "持続"


# ==================================================
# 買い目共通補助処理
#
# 会場ごとに同じ条件判定を持たせず、既存と同じ適用位置から
# この4処理を呼び出す。いずれも候補取得や脚質判定は変更しない。
# ==================================================
def build_second_trio_with_f(
    second_trio,
    use_f,
):
    """AとFが別馬の時だけ、三連複2点目の中央をFにする。"""
    result = second_trio[:]

    if use_f and len(result) >= 2:
        result[1] = "F"

    return result


def build_adg_or_abg_trio(d_is_a):
    """元の先行代表Dが軸AならA-B-G、違えばA-D-Gを返す。"""
    return [
        "A",
        "B" if d_is_a else "D",
        "G",
    ]


def append_nankan_large_field_trio(
    template,
    should_append,
    third_symbol="J",
):
    """南関10頭以上の三連複3点目を追加する。"""
    if should_append:
        template["三連複"].append(
            ["A", "B", third_symbol]
        )


def remove_ab_wide_keep_second(template):
    """南関以外ではA-Bワイドを外し、既存2点目だけを残す。"""
    wide_bets = template.get(
        "ワイド",
        [],
    )

    if len(wide_bets) >= 2:
        template["ワイド"] = [
            wide_bets[1][:]
        ]


bet_axis_type = classify_bet_axis_type(
    kyakushoku_type
)

is_iwate_front_axis = (
    baba_name in {
        "盛岡",
        "水沢",
    }
    and (
        axis_primary_for_bet in {
            "逃げ",
            "先行",
        }
        or bool(
            axis_secondary_tags_for_bet
            & {
                "逃げ",
                "先行",
            }
        )
    )
)

# ==================================================
# 南関10頭以上
#
# 浦和・船橋・大井・川崎
# ＋ 出走馬10頭以上
#
# 三連複3点目 A-B-J を追加する。
# J＝前進気勢3位から下位へ順送り。
# ==================================================
is_nankan_large_field = (
    baba_name in {
        "浦和",
        "船橋",
        "大井",
        "川崎",
    }
    and len(horses) >= 10
)

# 大井限定・逃げ軸
# 三連複3点目 A-D-E / ワイド2点目 A-D
is_ooi_escape = (
    baba_name == "大井"
    and kyakushoku_type == "逃げ"
)

# 大井限定・先行軸／持続軸
# 頭数に関係なく三連複を専用3点へ固定する。
is_ooi_senko_or_jizoku = (
    baba_name == "大井"
    and kyakushoku_type in {
        "先行",
        "持続",
    }
)

# ==================================================
# 先行軸・三連複の会場別／マーブル分岐
#
# 【1点目】
# 園田                  → A-B-D
# 先行＋押上            → A-B-C
# 先行＋持続／差し      → A-B-E
# 先行＋逃げ／なし      → A-B-D
#
# 【2点目】
# 園田                  → A-L-G  ※試験
# 笠松・川崎            → A-E-G
# その他                → A-C-G
# ==================================================
if kyakushoku_type == "先行":

    if baba_name == "園田":
        current_bet_template[
            "三連複"
        ][0] = [
            "A",
            "B",
            "D",
        ]

    elif axis_secondary_for_bet == "押上":
        current_bet_template[
            "三連複"
        ][0] = [
            "A",
            "B",
            "C",
        ]

    elif axis_secondary_for_bet in {
        "持続",
        "差し",
    }:
        current_bet_template[
            "三連複"
        ][0] = [
            "A",
            "B",
            "E",
        ]

    else:
        current_bet_template[
            "三連複"
        ][0] = [
            "A",
            "B",
            "D",
        ]

    # 園田だけ試験的に2点目を A-L-G。
    # L＝2角→4角【総合押上】ランキング1位。
    # A・Gと被ればLは2位→3位→…へ順送りする。
    if baba_name == "園田":
        current_bet_template[
            "三連複"
        ][1] = [
            "A",
            "L",
            "G",
        ]

    elif baba_name in {
        "笠松",
        "川崎",
    }:
        current_bet_template[
            "三連複"
        ][1] = [
            "A",
            "E",
            "G",
        ]

    else:
        current_bet_template[
            "三連複"
        ][1] = [
            "A",
            "C",
            "G",
        ]

# ==================================================
# 園田限定・先行＋押上軸
#
# 主：先行｜副：押上 のとき
# 三連複1点目を A-B-L にする。
#
# L＝2角→4角【総合押上】ランキング1位。
# A・Bと被る場合は2位→3位→4位…へ順送りする。
#
# 園田の通常先行1点目 A-B-D より後で上書きし、
# この条件だけ最終的に A-B-L を採用する。
# ==================================================
if (
    baba_name == "園田"
    and kyakushoku_type == "先行"
    and axis_secondary_for_bet == "押上"
):
    current_bet_template[
        "三連複"
    ][0] = [
        "A",
        "B",
        "L",
    ]

# ==================================================
# 佐賀限定・先行軸
#
# 軸タイプが「先行」のとき、
# 三連複1点目を A-B-L にする。
#
# L＝2角→4角【総合押上】ランキング1位。
# A・Bと被る場合は2位→3位→4位…へ順送りする。
#
# 先行軸の通常マーブル分岐より後で上書きするため、
# 佐賀では副脚質に関係なく最終的に A-B-L を採用する。
# ==================================================
if (
    baba_name == "佐賀"
    and kyakushoku_type == "先行"
):
    current_bet_template[
        "三連複"
    ][0] = [
        "A",
        "B",
        "L",
    ]

# ==================================================
# 三連複2点目
#
# Aと後詰めFが別馬なら、
# 先行軸以外は2点目の2文字目をFへ変更する。
#
# 園田「逃げ＋先行」はこの後で専用ルールを
# 上書きするため、A-D-Gが最終的に必ず残る。
# ==================================================
current_bet_template[
    "三連複"
][1] = build_second_trio_with_f(
    current_bet_template[
        "三連複"
    ][1],
    (
        int(total_best["馬番"])
        != int(popular_horse_num)
        and kyakushoku_type != "先行"
    ),
)

# ==================================================
# 門別限定・三連複専用ルール
#
# 差し軸
# 1点目 A-B-I
# 2点目 A-F-E
#
# 先行軸
# 2点目 A-C-I
#
# 持続軸
# 2点目 A-D-I
# 3点目 A-C-G
#
# 逃げ軸
# 2点目 A-J-G
# J＝前進気勢3位から下位へ順送り
#
# 上の共通A-F変更より後で上書きすることで、
# 門別だけ必ずこの形を最終採用する。
# 他会場の買い目には影響させない。
# ==================================================
if baba_name == "門別":

    if kyakushoku_type == "差し":
        current_bet_template[
            "三連複"
        ][0] = [
            "A",
            "B",
            "I",
        ]

        current_bet_template[
            "三連複"
        ][1] = [
            "A",
            "F",
            "E",
        ]

    elif kyakushoku_type == "先行":
        current_bet_template[
            "三連複"
        ][1] = [
            "A",
            "C",
            "I",
        ]

    elif kyakushoku_type == "持続":
        current_bet_template[
            "三連複"
        ][1] = [
            "A",
            "D",
            "I",
        ]

        # 門別・持続だけ3点目を A-C-G にする。
        if len(current_bet_template["三連複"]) >= 3:
            current_bet_template[
                "三連複"
            ][2] = [
                "A",
                "C",
                "G",
            ]

    elif kyakushoku_type == "逃げ":
        current_bet_template[
            "三連複"
        ][1] = [
            "A",
            "J",
            "G",
        ]

# ==================================================
# 園田限定
# 主：逃げ｜副：先行
#
# 三連複
# 1点目 A-B-I
# 2点目 A-D-G
#
# 上のA-F変更より後で上書きする。
# ==================================================
is_sonoda_escape_senko = (
    baba_name == "園田"
    and kyakushoku_type == "逃げ"
    and axis_secondary_for_bet == "先行"
)

if is_sonoda_escape_senko:
    current_bet_template[
        "三連複"
    ][0] = [
        "A",
        "B",
        "I",
    ]

    current_bet_template[
        "三連複"
    ][1] = [
        "A",
        "D",
        "G",
    ]

# ==================================================
# 園田限定・差し軸
#
# 三連複2点目
# A-F-K → A-D-K
#
# K＝3角→4角【勝負所重視】押上ランキング1位。
# A・Dと被る場合は既存の候補順送り／三連複3点不足救済で調整する。
# ==================================================
if (
    baba_name == "園田"
    and kyakushoku_type == "差し"
):
    current_bet_template[
        "三連複"
    ][1] = [
        "A",
        "D",
        "K",
    ]

# ==================================================
# 園田限定・差し軸
#
# ワイド
# 1点目 A-B はそのまま
# 2点目 A-E
# ==================================================
if (
    baba_name == "園田"
    and kyakushoku_type == "差し"
):
    current_bet_template[
        "ワイド"
    ][1] = [
        "A",
        "E",
    ]

# ==================================================
# 名古屋限定・差し軸
#
# 三連複
# 2点目 A-D-I → A-N-I
# N＝穴5
#
# ワイド
# 1点目 A-B はそのまま
# 2点目 A-C → A-E
#
# 南関以外の買い目整理で1点目A-Bが外れた後は、
# このA-Eだけがワイドとして残る。
# 他会場・他脚質には影響させない。
# ==================================================
if (
    baba_name == "名古屋"
    and kyakushoku_type == "差し"
):
    current_bet_template[
        "三連複"
    ][1] = [
        "A",
        "N",
        "I",
    ]

    current_bet_template[
        "ワイド"
    ][1] = [
        "A",
        "E",
    ]

# ==================================================
# 岩手限定（盛岡・水沢）
# 軸に「逃げ」または「先行」が入っている時
#
# 三連複1点目：A-B-L
# 浮き輪      ：L-K
#
# さらに、主：先行｜副：持続 の時だけ
# 三連複2点目：A-E-G
#
# K＝3角→4角【勝負所重視】ランキング1位（全会場共通）
# L＝2角→4角【総合押上】ランキング1位
#
# ワイドは既存ルールをそのまま使う。
# 他会場には一切影響させない。
# ==================================================
if is_iwate_front_axis:
    current_bet_template[
        "三連複"
    ][0] = [
        "A",
        "B",
        "L",
    ]

    # 岩手のみ・主：先行｜副：持続
    # 三連複2点目を A-E-G に固定する。
    if (
        axis_primary_for_bet == "先行"
        and axis_secondary_for_bet == "持続"
    ):
        current_bet_template[
            "三連複"
        ][1] = [
            "A",
            "E",
            "G",
        ]

    current_bet_template[
        "浮き輪"
    ] = [
        [
            "L",
            "K",
        ]
    ]

# ==================================================
# 盛岡限定・先行軸／持続軸
#
# 三連複2点目を A-C-G に固定する。
#
# ・主脚質が先行 → A-C-G
# ・主脚質が持続 → A-C-G
#
# 岩手共通の「先行＋持続ならA-E-G」より後で
# 盛岡だけ上書きする。
# 水沢・他会場には影響させない。
# ==================================================
if (
    baba_name == "盛岡"
    and kyakushoku_type in {
        "先行",
        "持続",
    }
):
    current_bet_template[
        "三連複"
    ][1] = [
        "A",
        "C",
        "G",
    ]

# ==================================================
# 盛岡限定・差し軸／持続軸
#
# 三連複1点目を A-B-C に固定する。
#
# ・主脚質が差し → A-B-C
# ・主脚質が持続 → A-B-C
#
# 盛岡だけ上書きする。
# 水沢・他会場には影響させない。
#
# ※持続軸は、直前の盛岡専用ルールにより
#   三連複2点目 A-C-G もそのまま維持する。
# ==================================================
if (
    baba_name == "盛岡"
    and kyakushoku_type in {
        "差し",
        "持続",
    }
):
    current_bet_template[
        "三連複"
    ][0] = [
        "A",
        "B",
        "C",
    ]

# ==================================================
# 盛岡限定・差し軸
#
# 浮き輪ワイド：K - L
#
# K＝3角→4角【勝負所重視】押上ランキング1位
# L＝2角→4角【総合押上】ランキング1位
#
# 盛岡の差し軸だけに適用し、
# 三連複・通常ワイド・他会場・他脚質には影響させない。
# ==================================================
if (
    baba_name == "盛岡"
    and kyakushoku_type == "差し"
):
    current_bet_template[
        "浮き輪"
    ] = [
        [
            "K",
            "L",
        ]
    ]

# ==================================================
# 南関10頭以上
#
# 通常の三連複2点を残したまま、
# 3点目だけ A-B-J を追加する。
#
# ただし大井・逃げ軸は専用3点目 A-D-E を使うため、
# ここではA-B-Jを追加しない。
#
# 大井・先行軸／持続軸はこの後の専用処理で、
# 頭数に関係なく三連複3点を丸ごと上書きする。
# ==================================================
append_nankan_large_field_trio(
    current_bet_template,
    (
        is_nankan_large_field
        and not is_ooi_escape
    ),
)

# ==================================================
# 大井限定・先行軸／持続軸
#
# 頭数に関係なく三連複を3点へ固定する。
#
# 1点目
#   先行軸 → A-B-D
#   持続軸 → A-B-C
#
# 2点目
#   共通   → A-G-L
#
# 3点目
#   先行軸 → A-D-G
#   持続軸 → A-K-J
#
# L＝2角→4角【総合押上】ランキング1位。
# K＝3角→4角【勝負所重視】押上ランキング1位。
# J＝前進気勢3位。
# ==================================================
if is_ooi_senko_or_jizoku:
    ooi_first_trio = (
        [
            "A",
            "B",
            "C",
        ]
        if kyakushoku_type == "持続"
        else [
            "A",
            "B",
            "D",
        ]
    )

    ooi_third_trio = (
        [
            "A",
            "K",
            "J",
        ]
        if kyakushoku_type == "持続"
        else [
            "A",
            "D",
            "G",
        ]
    )

    current_bet_template[
        "三連複"
    ] = [
        ooi_first_trio,
        [
            "A",
            "G",
            "L",
        ],
        ooi_third_trio,
    ]

# ==================================================
# 大井限定・逃げ軸
#
# 三連複3点目：A-D-E
# ワイド2点目：A-D
#
# 頭数に関係なく大井の逃げ軸では三連複を3点にする。
# 南関10頭以上の通常3点目 A-B-J よりこちらを優先する。
# ==================================================
if is_ooi_escape:

    ooi_escape_trio3 = [
        "A",
        "D",
        "E",
    ]

    if len(
        current_bet_template[
            "三連複"
        ]
    ) >= 3:
        current_bet_template[
            "三連複"
        ][2] = ooi_escape_trio3

    else:
        current_bet_template[
            "三連複"
        ].append(
            ooi_escape_trio3
        )

    current_bet_template[
        "ワイド"
    ][1] = [
        "A",
        "D",
    ]

# ==================================================
# 南関以外・A-Bワイド100円を三連複3点目へ移行
#
# 南関4場（浦和・船橋・大井・川崎）は完全に現状維持。
#
# 【園田】
# 軸が逃げ・先行
#   → 三連複3点目 A-E-K
# それ以外の軸
#   → 三連複3点目 A-B-K
#
# 【A-B-L 採用会場】
# 笠松・佐賀・水沢・高知
#   → 三連複3点目 A-B-L
#
# 【それ以外の南関以外】
# 金沢・名古屋・姫路・門別
#   → 基本 A-D-G
#   → ただし、画面上の先行代表Dが軸Aと同じ馬なら A-B-G
#
# 【盛岡だけ例外】
#   → 三連複は従来の2点のまま
#   → 通常ワイドも従来の2点を残す
#   → 浮き輪1点も残す
#   → 合計：三連複2点＋ワイド系3点＝5点
#
# ワイドは従来の1点目 A-B を削除し、
# 既存の2点目だけを残す。
#
# これにより南関以外は原則、
#   三連複3点 + ワイド1点 + 浮き輪1点 = 5点（500円）
# となる。
#
# ※既存の三連複1〜2点目と同じ3頭になった場合は、
#   make_unique_trio_bets() の既存重複回避により、
#   右側の記号（LやGなど）を次候補へ順送りする。
# ==================================================
NON_NANKAN_ABK_TRACKS = {
    "園田",
}

NON_NANKAN_ABL_TRACKS = {
    "笠松",
    "佐賀",
    "水沢",
    "高知",
}

NON_NANKAN_ADG_TRACKS = {
    # 盛岡は三連複2点＋通常ワイド2点＋浮き輪1点に戻すため除外。
    "金沢",
    "名古屋",
    "姫路",
    "門別",
}

is_non_nankan_bet_track = (
    baba_name in (
        NON_NANKAN_ABK_TRACKS
        | NON_NANKAN_ABL_TRACKS
        | NON_NANKAN_ADG_TRACKS
    )
)

non_nankan_extra_trio_symbols = None
non_nankan_adg_switched_to_abg = False

if is_non_nankan_bet_track:

    # ----------------------------------------------
    # ワイドA-Bを削除。
    # 会場別修正済みの「2点目」だけを残す。
    # ----------------------------------------------
    remove_ab_wide_keep_second(
        current_bet_template
    )

    # ----------------------------------------------
    # 園田
    # 軸が逃げ・先行 → 3点目 A-E-K
    # それ以外       → 3点目 A-B-K
    # ----------------------------------------------
    if baba_name in NON_NANKAN_ABK_TRACKS:

        if kyakushoku_type in {
            "逃げ",
            "先行",
        }:
            non_nankan_extra_trio_symbols = [
                "A",
                "E",
                "K",
            ]

        else:
            non_nankan_extra_trio_symbols = [
                "A",
                "B",
                "K",
            ]

    # ----------------------------------------------
    # 笠松・佐賀・水沢・高知
    # 3点目 A-B-L
    # ----------------------------------------------
    elif baba_name in NON_NANKAN_ABL_TRACKS:
        non_nankan_extra_trio_symbols = [
            "A",
            "B",
            "L",
        ]

    # ----------------------------------------------
    # 金沢・名古屋・姫路・門別
    # 基本 A-D-G。
    #
    # ここでいう A=D は、アルファベット重複回避で
    # Dが2位へ送られる前の「本来の先行代表D」が軸Aと同じ、
    # という意味。
    # その場合はD次点を使わず、指定どおり A-B-G にする。
    # ----------------------------------------------
    elif baba_name in NON_NANKAN_ADG_TRACKS:

        raw_d_is_axis_a = (
            int(
                front_best[
                    "馬番"
                ]
            )
            == int(
                popular_horse_num
            )
        )

        non_nankan_extra_trio_symbols = (
            build_adg_or_abg_trio(
                raw_d_is_axis_a
            )
        )

        if raw_d_is_axis_a:
            non_nankan_adg_switched_to_abg = True

    if non_nankan_extra_trio_symbols is not None:
        current_bet_template[
            "三連複"
        ].append(
            non_nankan_extra_trio_symbols
        )

# ==================================================
# 園田限定・軸に「逃げ」または「先行」が入る時
#
# 主脚質または副脚質に「逃げ／先行」が1つでもあれば適用。
#
# 三連複3点
#   1点目 A-M-G
#   2点目 A-D-C
#   3点目 逃げ軸のみ A-C-L
#          それ以外は A-M-L
#
# ワイド1点
#   A-I
#
# 浮き輪1点
#   D-E
#
# ここを園田の最終上書きにして、
# それ以前の園田専用買い目よりこちらを優先する。
# 他会場には影響させない。
# ==================================================
is_sonoda_escape_or_senko_axis = (
    baba_name == "園田"
    and (
        axis_primary_for_bet in {
            "逃げ",
            "先行",
        }
        or bool(
            axis_secondary_tags_for_bet
            & {
                "逃げ",
                "先行",
            }
        )
    )
)

if is_sonoda_escape_or_senko_axis:
    sonoda_third_trio = (
        ["A", "C", "L"]
        if kyakushoku_type == "逃げ"
        else ["A", "M", "L"]
    )

    current_bet_template[
        "三連複"
    ] = [
        ["A", "M", "G"],
        ["A", "D", "C"],
        sonoda_third_trio,
    ]

    current_bet_template[
        "ワイド"
    ] = [
        ["A", "I"],
    ]

    current_bet_template[
        "浮き輪"
    ] = [
        ["D", "E"],
    ]

# ==================================================
# 14会場 × 軸3タイプ＝42通り
# 会場別・最終買い目上書き表
#
# 適用順：
#   1) ここまでの既存ロジックで買い目を作る
#   2) 最後に「会場 × 3分類」の設定だけを上書きする
#
# 14会場42枠すべて設定済み。
# ==================================================
BET_TRACKS_14 = (
    "浦和",
    "船橋",
    "大井",
    "川崎",
    "金沢",
    "笠松",
    "名古屋",
    "園田",
    "姫路",
    "高知",
    "佐賀",
    "門別",
    "盛岡",
    "水沢",
)

BET_AXIS_TYPES_3 = (
    "前受け",
    "持続",
    "差し",
)


def build_kanazawa_axis_bet_override(context):
    """金沢の正式3分類ルール。"""

    axis_type = context["axis_type"]

    third_trio = build_adg_or_abg_trio(
        context["d_is_a"]
    )

    rules = {
        "前受け": {
            "三連複": [
                ["A", "B", "D"],
                ["A", "C", "G"],
                third_trio,
            ],
            "ワイド": [["A", "E"]],
            "浮き輪": [["D", "E"]],
        },
        "持続": {
            "三連複": [
                ["A", "B", "C"],
                ["A", "C", "E"],
                third_trio,
            ],
            "ワイド": [["D", "C"]],
            "浮き輪": [["E", "D"]],
        },
        "差し": {
            "三連複": [
                ["A", "B", "E"],
                ["A", "D", "I"],
                third_trio,
            ],
            "ワイド": [["A", "C"]],
            "浮き輪": [["I", "G"]],
        },
    }

    result = {
        bet_type: [bet[:] for bet in bets]
        for bet_type, bets in rules[axis_type].items()
    }

    if (
        axis_type in {"持続", "差し"}
        and context["a_is_not_f"]
    ):
        result["三連複"][1][1] = "F"

    return result

def build_kasamatsu_axis_bet_override(context):
    """笠松の正式3分類ルール。"""

    axis_type = context["axis_type"]

    rules = {
        "前受け": {
            "三連複": [
                ["A", "B", "D"],
                ["A", "E", "G"],
                ["A", "B", "L"],
            ],
            "ワイド": [["A", "E"]],
            "浮き輪": [["D", "E"]],
        },
        "持続": {
            "三連複": [
                ["A", "B", "C"],
                ["A", "C", "E"],
                ["A", "B", "L"],
            ],
            "ワイド": [["D", "C"]],
            "浮き輪": [["E", "D"]],
        },
        "差し": {
            "三連複": [
                ["A", "B", "E"],
                ["A", "D", "I"],
                ["A", "B", "L"],
            ],
            "ワイド": [["A", "C"]],
            "浮き輪": [["I", "G"]],
        },
    }

    result = {
        bet_type: [bet[:] for bet in bets]
        for bet_type, bets in rules[axis_type].items()
    }

    if (
        axis_type in {"持続", "差し"}
        and context["a_is_not_f"]
    ):
        result["三連複"][1][1] = "F"

    return result

def build_urawa_funabashi_axis_bet_override(context):
    """浦和・船橋の買い目を正式3分類だけで作る。"""
    axis_type = context["axis_type"]

    rules = {
        "前受け": {
            "三連複": [
                ["A", "B", "D"],
                ["A", "C", "G"],
            ],
            "ワイド": [
                ["A", "B"],
                ["A", "E"],
            ],
            "浮き輪": [["D", "E"]],
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
            "浮き輪": [["E", "D"]],
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
            "浮き輪": [["I", "G"]],
        },
    }

    result = {
        bet_type: [bet[:] for bet in bets]
        for bet_type, bets in rules[axis_type].items()
    }

    # 現行結果を維持する持続・差しだけ、A≠F時にFを使う。
    # 前受けには旧逃げ専用のA≠F分岐を適用しない。
    if (
        axis_type in {"持続", "差し"}
        and context["a_is_not_f"]
    ):
        result["三連複"][1][1] = "F"

    # 浦和・船橋は10頭以上の3点目を A-B-F にする。
    # 川崎もこの共通関数を使うため同じく A-B-F になる。
    # Jは大井専用として残す。
    append_nankan_large_field_trio(
        result,
        context["is_nankan_large_field"],
        third_symbol="F",
    )

    return result


def build_kawasaki_axis_bet_override(context):
    """浦和・船橋共通ルールとの差分だけを適用する。"""
    result = build_urawa_funabashi_axis_bet_override(
        context
    )

    if context["axis_type"] == "前受け":
        result["三連複"][1] = ["A", "E", "G"]

    return result


def build_nagoya_himeji_axis_bet_override(context):
    """名古屋・姫路の共通3分類ルールを作る。"""
    result = build_urawa_funabashi_axis_bet_override(
        context
    )

    remove_ab_wide_keep_second(result)
    result["三連複"].append(
        build_adg_or_abg_trio(context["d_is_a"])
    )

    if (
        context["track"] == "名古屋"
        and context["axis_type"] == "前受け"
    ):
        result["三連複"][1] = ["A", "M", "G"]

        # 名古屋のみ・主＝先行／副＝持続の時は、
        # 三連複3点目を A-I-G にする。
        if (
            context.get("axis_primary") == "先行"
            and context.get("axis_secondary") == "持続"
        ):
            result["三連複"][2] = ["A", "I", "G"]

    if (
        context["track"] == "名古屋"
        and context["axis_type"] == "差し"
    ):
        result["三連複"][1] = ["A", "N", "I"]
        result["三連複"][2] = ["A", "L", "G"]
        result["ワイド"] = [["A", "E"]]

    return result


def build_kochi_saga_axis_bet_override(context):
    """高知・佐賀の共通3分類ルールを作る。"""
    result = build_urawa_funabashi_axis_bet_override(
        context
    )

    remove_ab_wide_keep_second(result)
    result["三連複"].append(["A", "B", "L"])

    # --------------------------------------------------
    # 高知限定・軸に「持続」が入っている時
    #
    # 主脚質が持続、または内部の副脚質タグに持続がある場合、
    # 三連複3点目を A-G-K に固定する。
    #
    # 例：
    # ・主：持続｜副：○○
    # ・主：先行｜副：持続
    # ・主：差し｜副脚質内に持続
    #
    # 高知だけの差分で、佐賀・他会場には影響させない。
    # --------------------------------------------------
    kochi_axis_has_sustain = (
        context["track"] == "高知"
        and (
            context.get("axis_primary") == "持続"
            or "持続" in context.get(
                "axis_secondary_tags",
                frozenset(),
            )
        )
    )

    if kochi_axis_has_sustain:
        result["三連複"][2] = ["A", "G", "K"]

    # 高知限定・軸が前受けの時は、
    # ワイド A-E の1点だけを A-M に変更する。
    if (
        context["track"] == "高知"
        and context["axis_type"] == "前受け"
    ):
        result["ワイド"] = [["A", "M"]]

    # 高知限定・軸が差しの時は、
    # 三連複2点目を A-M-L に変更する。
    # 3点目 A-F-C は既存どおり維持する。
    if (
        context["track"] == "高知"
        and context["axis_type"] == "差し"
    ):
        result["三連複"][1] = ["A", "M", "L"]
        result["三連複"][2] = ["A", "F", "C"]

    if (
        context["track"] == "佐賀"
        and context["axis_type"] == "前受け"
    ):
        # 佐賀・前受けの既存1点目 A-B-L は維持する。
        result["三連複"][0] = ["A", "B", "L"]

        # 今回の変更は3点目だけ。
        result["三連複"][2] = ["A", "M", "L"]

    # 佐賀・差しだけ2点目を A-D-G に固定する。
    # 共通側のA≠F時のA-F-I差し替えより後で上書きするため、
    # AとFが異なる場合でも最終買い目はA-D-Gになる。
    if (
        context["track"] == "佐賀"
        and context["axis_type"] == "差し"
    ):
        result["三連複"][1] = ["A", "D", "G"]

    return result


def build_iwate_axis_bet_override(context):
    """盛岡・水沢を三連複3点＋ワイド1点＋浮き輪1点の5点で統一する。"""
    track = context["track"]
    axis_type = context["axis_type"]

    result = build_urawa_funabashi_axis_bet_override(
        context
    )

    # ----------------------------------------------
    # 前受け
    # 1点目：展開＋穴寄りL
    # 2点目：固めC＋穴G
    # 3点目：盛岡・水沢ともに A-I-E
    # ワイド2点目 A-E を浮き輪へ移す。
    # ----------------------------------------------
    if axis_type == "前受け":
        result["三連複"] = [
            ["A", "B", "L"],
            ["A", "C", "G"],
            ["A", "I", "E"],
        ]
        result["ワイド"] = [
            ["A", "B"],
        ]
        result["浮き輪"] = [["A", "E"]]
        return result

    # ----------------------------------------------
    # 持続
    # A≠F時の2点目F差し替えは共通ルール側を維持。
    # 3点目は展開B＋穴L。
    # ワイド2点目 D-C を浮き輪へ移す。
    # ----------------------------------------------
    if axis_type == "持続":
        if track == "盛岡":
            result["三連複"][1] = ["A", "C", "G"]

        result["三連複"].append(
            ["A", "B", "L"]
        )

        result["ワイド"] = [
            ["A", "B"],
        ]
        result["浮き輪"] = [["D", "C"]]
        return result

    # ----------------------------------------------
    # 差し
    # 盛岡だけ1点目A-B-Cを維持。
    # 水沢は共通のA-B-E。
    # 3点目は展開B＋穴L。
    # ワイド2点目 A-C を浮き輪へ移す。
    # ----------------------------------------------
    if track == "盛岡":
        result["三連複"][0] = ["A", "B", "C"]

    result["三連複"].append(
        ["A", "B", "L"]
    )

    result["ワイド"] = [
        ["A", "B"],
    ]
    result["浮き輪"] = [["A", "C"]]

    return result

def build_monbetsu_axis_bet_override(context):
    """門別の買い目を正式3分類だけで作る。"""
    axis_type = context["axis_type"]
    third_trio = build_adg_or_abg_trio(
        context["d_is_a"]
    )

    rules = {
        "前受け": {
            "三連複": [
                ["A", "B", "E"],
                ["A", "C", "I"],
            ],
            "ワイド": [["A", "G"]],
            "浮き輪": [["D", "E"]],
        },
        "持続": {
            "三連複": [
                ["A", "B", "C"],
                ["A", "D", "I"],
            ],
            "ワイド": [["D", "C"]],
            "浮き輪": [["E", "D"]],
        },
        "差し": {
            "三連複": [
                ["A", "B", "I"],
                ["A", "F", "E"],
            ],
            "ワイド": [["A", "C"]],
            "浮き輪": [["I", "G"]],
        },
    }

    result = {
        bet_type: [bet[:] for bet in bets]
        for bet_type, bets in rules[axis_type].items()
    }

    # 門別・前受けは3点目 A-E-G。
    # 門別・持続は3点目 A-C-G。
    # 差しだけ従来の D=A 重複回避付き3点目を維持する。
    if axis_type == "前受け":
        result["三連複"].append(["A", "E", "G"])
    elif axis_type == "持続":
        result["三連複"].append(["A", "C", "G"])
    else:
        result["三連複"].append(third_trio)

    return result


def build_ooi_axis_bet_override(context):
    """大井の買い目を正式3分類だけで作る。"""
    axis_type = context["axis_type"]
    is_ten_or_less = context["horse_count"] <= 10

    rules = {
        "前受け": {
            "三連複": [
                ["A", "B", "D"],
                ["A", "F", "L"],
                ["A", "D", "G"],
            ],
            "ワイド": [
                ["A", "F"],
                ["A", "E"],
            ],
            "浮き輪": [["D", "E"]],
        },
        "持続": {
            "三連複": [
                ["A", "B", "C"],
                ["A", "G", "L"],
                ["A", "K", "J"],
            ],
            "ワイド": [
                ["A", "F"],
                ["D", "C"],
            ],
            "浮き輪": [["E", "D"]],
        },
        "差し": {
            "三連複": [
                ["A", "B", "E"],
                ["A", "D", "I"],
            ],
            "ワイド": [
                ["A", "F"],
                ["A", "C"],
            ],
            "浮き輪": [["I", "G"]],
        },
    }

    result = {
        bet_type: [bet[:] for bet in bets]
        for bet_type, bets in rules[axis_type].items()
    }

    # 大井・前受けのマーブル脚質差分。
    # ・主＝先行・副＝持続 → 三連複2点目 A-D-N
    # ・主＝逃げ・副＝先行 → 三連複2点目 A-B-J
    # ・主＝先行/逃げ・副＝持続 → 三連複3点目 A-E-I
    # それ以外の前受け・持続・差しには影響させない。
    if (
        axis_type == "前受け"
        and context.get("axis_primary") == "先行"
        and context.get("axis_secondary") == "持続"
    ):
        result["三連複"][1] = [
            "A",
            "D",
            "N",
        ]

    if (
        axis_type == "前受け"
        and context.get("axis_primary") == "逃げ"
        and context.get("axis_secondary") == "先行"
    ):
        result["三連複"][1] = [
            "A",
            "B",
            "J",
        ]

    if (
        axis_type == "前受け"
        and context.get("axis_primary") in {"先行", "逃げ"}
        and context.get("axis_secondary") == "持続"
    ):
        result["三連複"][2] = [
            "A",
            "E",
            "I",
        ]

    if axis_type == "差し":
        result["三連複"][1] = build_second_trio_with_f(
            result["三連複"][1],
            context["a_is_not_f"],
        )

        if is_ten_or_less:
            result["三連複"].append(["A", "D", "E"])
        else:
            append_nankan_large_field_trio(
                result,
                context["is_nankan_large_field"],
            )

    # 大井10頭以下は通常ワイド1点＋浮き輪1点にする。
    # 全3タイプとも先頭はA-Fなので、1点目だけを外す。
    if is_ten_or_less:
        result["ワイド"] = result["ワイド"][1:]

    return result


def build_sonoda_axis_bet_override(context):
    """園田の買い目を正式3分類だけで作る。"""
    axis_type = context["axis_type"]
    current_distance = context.get(
        "current_distance"
    )

    # 園田820m・前受けだけは、
    # 距離短縮補正で強化した通常Bを買い目へ直接使う。
    #
    # 1点目：A-B-D ＝ 軸＋展開＋先行（前残り筋）
    # 2点目：A-F-I ＝ 後詰め＋押上
    # 3点目：A-M-D
    sonoda_front_first_trio = (
        ["A", "B", "D"]
        if current_distance == 820
        else ["A", "M", "G"]
    )

    rules = {
        "前受け": {
            "三連複": [
                sonoda_front_first_trio,
                ["A", "F", "I"],
                ["A", "M", "D"],
            ],
            "ワイド": [["A", "I"]],
            "浮き輪": [["D", "E"]],
        },
        "持続": {
            "三連複": [
                ["A", "B", "C"],
                ["A", "C", "E"],
                ["A", "B", "K"],
            ],
            "ワイド": [["D", "C"]],
            "浮き輪": [["E", "D"]],
        },
        "差し": {
            "三連複": [
                ["A", "B", "E"],
                ["A", "D", "K"],
                ["A", "B", "K"],
            ],
            "ワイド": [["A", "E"]],
            "浮き輪": [["I", "G"]],
        },
    }

    result = {
        bet_type: [bet[:] for bet in bets]
        for bet_type, bets in rules[axis_type].items()
    }

    # 園田・軸先行だけ、三連複2点目を A-F-I にする。
    # 「前受け」全体を書き換えず、逃げ軸には影響させない。
    if (
        axis_type == "前受け"
        and context.get("axis_primary") == "先行"
    ):
        result["三連複"][1] = [
            "A",
            "F",
            "I",
        ]

    if axis_type == "持続":
        result["三連複"][1] = build_second_trio_with_f(
            result["三連複"][1],
            context["a_is_not_f"],
        )

    # 園田・元の主脚質が展開待ちの時だけ
    # 三連複1点目を A-F-E、2点目を A-D-E、3点目を A-D-G にする。
    if (
        axis_type == "差し"
        and context.get("axis_primary") == "展開待ち"
    ):
        result["三連複"][0] = [
            "A",
            "F",
            "E",
        ]
        result["三連複"][1] = [
            "A",
            "D",
            "E",
        ]
        result["三連複"][2] = [
            "A",
            "D",
            "G",
        ]

    return result


VENUE_AXIS_BET_OVERRIDES = {
    track: {
        axis_type: None
        for axis_type in BET_AXIS_TYPES_3
    }
    for track in BET_TRACKS_14
}

# 14会場42枠すべて設定済み。
VENUE_AXIS_BET_OVERRIDES["金沢"] = {
    "前受け": build_kanazawa_axis_bet_override,
    "持続": build_kanazawa_axis_bet_override,
    "差し": build_kanazawa_axis_bet_override,
}

VENUE_AXIS_BET_OVERRIDES["笠松"] = {
    "前受け": build_kasamatsu_axis_bet_override,
    "持続": build_kasamatsu_axis_bet_override,
    "差し": build_kasamatsu_axis_bet_override,
}

# 浦和・船橋は正式3分類の共通実ルールを使う。
# 旧逃げ／先行、legacy、副脚質、existing_templateには依存しない。
for track in ("浦和", "船橋"):
    VENUE_AXIS_BET_OVERRIDES[track] = {
        axis_type: build_urawa_funabashi_axis_bet_override
        for axis_type in BET_AXIS_TYPES_3
    }

# 川崎は持続・差しを浦和・船橋と共用し、
# 前受けの三連複2点目だけA-E-Gへ変更する。
VENUE_AXIS_BET_OVERRIDES["川崎"] = {
    axis_type: build_kawasaki_axis_bet_override
    for axis_type in BET_AXIS_TYPES_3
}

# 名古屋・姫路は共通3分類ルールを使い、
# 名古屋の前受け2点目A-M-Gと、差しA-N-I／A-L-G／A-Eを差分上書きする。
for track in ("名古屋", "姫路"):
    VENUE_AXIS_BET_OVERRIDES[track] = {
        axis_type: build_nagoya_himeji_axis_bet_override
        for axis_type in BET_AXIS_TYPES_3
    }

# 高知・佐賀は共通3分類ルールを使い、
# 佐賀の前受けだけ1点目をA-B-Lへ差分上書きする。
for track in ("高知", "佐賀"):
    VENUE_AXIS_BET_OVERRIDES[track] = {
        axis_type: build_kochi_saga_axis_bet_override
        for axis_type in BET_AXIS_TYPES_3
    }

# 盛岡・水沢は岩手共通3分類ルールを使い、
# 三連複3点目・ワイド本数・盛岡持続／差しだけ差分処理する。
for track in ("盛岡", "水沢"):
    VENUE_AXIS_BET_OVERRIDES[track] = {
        axis_type: build_iwate_axis_bet_override
        for axis_type in BET_AXIS_TYPES_3
    }

# 門別は正式3分類だけで作り、旧逃げ／先行、legacy、
# 副脚質、existing_template、A≠F分岐には依存しない。
VENUE_AXIS_BET_OVERRIDES["門別"] = {
    axis_type: build_monbetsu_axis_bet_override
    for axis_type in BET_AXIS_TYPES_3
}

# 大井は正式3分類だけで作る。10頭以下は三連複3点・
# 通常ワイド1点＋浮き輪1点とし、11頭以上は従来仕様を維持する。
VENUE_AXIS_BET_OVERRIDES["大井"] = {
    axis_type: build_ooi_axis_bet_override
    for axis_type in BET_AXIS_TYPES_3
}

# 園田は正式3分類だけで作る。前受けはMを直接使い、
# 持続だけB候補をMへ差し替え、差しは通常Bを使う。
VENUE_AXIS_BET_OVERRIDES["園田"] = {
    axis_type: build_sonoda_axis_bet_override
    for axis_type in BET_AXIS_TYPES_3
}


def build_venue_axis_bet_rule_context(
    track,
    axis_type,
    legacy_axis_type,
    axis_primary,
    axis_secondary,
    axis_secondary_tags,
    a_is_f,
    d_is_a,
    horse_count,
    is_nankan_large_field,
    candidate_pools,
    existing_template,
    current_distance,
):
    """
    会場×3軸タイプのルール関数へ渡す共通コンテキスト。

    各ルール関数は、この辞書だけを受け取る。
    候補プールはルール側で誤って変更しないようtuple化する。
    """
    a_is_not_f = not a_is_f

    return {
        "track": track,
        "axis_type": axis_type,
        "legacy_axis_type": legacy_axis_type,
        "axis_primary": axis_primary,
        "axis_secondary": axis_secondary,
        "axis_secondary_tags": frozenset(
            axis_secondary_tags
        ),
        "a_is_f": a_is_f,
        "a_is_not_f": a_is_not_f,
        "d_is_a": d_is_a,
        "horse_count": horse_count,
        "current_distance": current_distance,
        "is_nankan_large_field": (
            is_nankan_large_field
        ),
        "existing_template": {
            bet_type: [bet[:] for bet in bets]
            for bet_type, bets in existing_template.items()
        },
        "candidate_pools": {
            symbol: tuple(pool)
            for symbol, pool
            in candidate_pools.items()
        },
    }


def apply_venue_axis_bet_override(
    base_template,
    context,
):
    """
    既存買い目をコピーし、会場×3分類の設定がある券種だけを
    最後に上書きして返す。
    """
    result = {
        bet_type: [
            bet[:]
            for bet in bets
        ]
        for bet_type, bets
        in base_template.items()
    }

    track = context["track"]
    axis_type = context["axis_type"]

    track_table = (
        VENUE_AXIS_BET_OVERRIDES.get(
            track,
            {},
        )
    )

    override = track_table.get(
        axis_type
    )

    if not override:
        return result

    # 設定済みの各ルール関数は、全会場共通のcontextを受け取る。
    # 金沢・笠松も旧脚質と既存分岐条件をcontextから参照する。
    if callable(override):
        override = override(context)

    for bet_type in (
        "三連複",
        "ワイド",
        "浮き輪",
    ):
        override_bets = override.get(
            bet_type
        )

        if override_bets is None:
            continue

        result[bet_type] = [
            bet[:]
            for bet in override_bets
        ]

    return result

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

# N＝穴5
# 穴5を最優先にし、買い目内でA・Iと被った時だけ
# 穴4 → 穴1 → 穴2 → 穴3 → その他候補の順へ送る。
n_pool = unique_texts(
    [
        ana_fifth_horse,
        ana_fourth_horse,
        ana_horse,
        ana_second_horse,
        ana_third_horse,
    ]
    + [horse_text(h) for h in ana_fallback]
    + all_bet_pool
)

# ==================================================
# J
#
# 大井で軸の主・副脚質に「持続」が含まれる時：
#   共通TOP5に残った展開ランキングの2位から開始する。
#   例：1番 → 13番 → 15番 なら J＝13番。
#   同じ買い目内でKなどと被れば15番へ繰り下げる。
#
# それ以外：
#   従来どおり前進気勢ランキング3位から開始する。
#
# 現在、最終買い目でJを使う会場は大井のみ。
# ==================================================
front_ranking_for_j = [
    h
    for h in nankan_front_candidates
    if h.get(
        "スコア",
        0,
    ) > 0
]

default_j_candidates = [
    horse_text(h)
    for h in front_ranking_for_j[2:]
]

if (
    oi_axis_has_sustain
    and len(oi_common_tenkai_candidates) >= 2
):
    # 1位はBとして使うため、Jは共通TOP5展開2位から。
    oi_common_j_candidates = [
        horse_text(h)
        for h in oi_common_tenkai_candidates[1:]
    ]

    # 共通TOP5内で被り回避できない場合だけ、
    # 従来J候補を安全網として後ろへつなぐ。
    j_pool = unique_texts(
        oi_common_j_candidates
        + default_j_candidates
    )
else:
    j_pool = unique_texts(
        default_j_candidates
    )

# ==================================================
# K＝3角→4角【勝負所重視】押上ランキング1位
#
# 全会場共通：
#   3角→4角【勝負所重視】ランキング1位から開始。
#   A・B・Fなど、同じ買い目内の記号と同じ馬になった場合だけ、
#   2位 → 3位 → 4位…へ順送りする。
#
# Lは別枠で2角→4角【総合押上】ランキング1位。
# ==================================================
k_pool = unique_texts(
    [
        horse_text(h)
        for h in corner_push_3to4
    ]
)

# ==================================================
# L＝押上ランキング1位
#
# 2角→4角【総合押上】ランキングを使用する。
# 1位から候補を開始し、A・Bなど同じ買い目内で被れば
# 2位 → 3位 → 4位…へ順送りする。
#
# 会場別A-B-L、佐賀先行軸、園田・先行＋押上軸、および岩手前受け軸で使用。
# ==================================================
l_pool = unique_texts(
    [
        horse_text(h)
        for h in corner_push_2to4
    ]
)

# ==================================================
# M＝園田専用・中間重複馬
#
# 目的：
# 各部門1位にはならないが、複数ランキングの2〜5位に
# 何度も顔を出す「中間上位馬」を三連複3頭目で拾う。
#
# 使用ランキング（オッズ不使用）：
#   ・総合
#   ・地力
#   ・前進気勢
#   ・抑え候補
#   ・3角→4角【勝負所重視】押上
#   ・2角→4角【総合押上】
#
# 点数：2位=4 / 3位=3 / 4位=2 / 5位=1
# 2〜5位に2部門以上入った馬を最優先。
#
# さらに「画面の主要5役」
#   A軸 / B展開 / 地力代表 / D先行 / E抑え
# と違う馬を先に並べる。
# これにより既存5頭から漏れた中間馬を優先して試す。
#
# 候補不足時は、同条件の主要5役馬 → 1部門だけ該当馬
# → 全馬の順で安全にフォールバックする。
# ==================================================

def build_rank_map(ranking):
    return {
        int(h["馬番"]): rank
        for rank, h in enumerate(
            ranking,
            start=1,
        )
    }


m_rank_maps = {
    "総合": build_rank_map(
        total_candidates
    ),
    "地力": build_rank_map(
        long_spurt_candidates
    ),
    "前進": build_rank_map(
        front_candidates
    ),
    "抑え": build_rank_map(
        ana_candidates
    ),
    "3→4押上": build_rank_map(
        corner_push_3to4
    ),
    "2→4押上": build_rank_map(
        corner_push_2to4
    ),
}

m_rank_point_table = {
    2: 4,
    3: 3,
    4: 2,
    5: 1,
}

m_horse_name_map = {
    int(h["馬番"]): h["馬名"]
    for h in horses
}

m_candidates = []

for horse_no, horse_name in m_horse_name_map.items():

    rank_details = {}
    m_score = 0
    m_hit_count = 0
    m_rank_sum = 0

    for rank_name, rank_map in m_rank_maps.items():
        rank = rank_map.get(
            horse_no
        )

        if rank in m_rank_point_table:
            rank_details[rank_name] = rank
            m_score += m_rank_point_table[
                rank
            ]
            m_hit_count += 1
            m_rank_sum += rank

    if m_hit_count <= 0:
        continue

    m_candidates.append({
        "馬番": horse_no,
        "馬名": horse_name,
        "Mスコア": m_score,
        "該当数": m_hit_count,
        "順位合計": m_rank_sum,
        "順位詳細": rank_details,
        "総合順位": m_rank_maps[
            "総合"
        ].get(
            horse_no,
            99,
        ),
    })

# 点数 → 該当部門数 → 順位合計の小ささ → 総合順位
# の順で「中間重複度」が高い馬を上位にする。
m_candidates.sort(
    key=lambda x: (
        -x["Mスコア"],
        -x["該当数"],
        x["順位合計"],
        x["総合順位"],
        x["馬番"],
    )
)

# 画面主要5役。Mではまず、この5頭以外を優先する。
m_major_numbers = {
    int(popular_horse_num),
    int(tenkai_best["馬番"]),
    int(long_best["馬番"]),
    int(front_best["馬番"]),
    int(ana_best["馬番"]),
}

m_primary = [
    h
    for h in m_candidates
    if h["該当数"] >= 2
    and h["馬番"] not in m_major_numbers
]

m_secondary = [
    h
    for h in m_candidates
    if h["該当数"] >= 2
    and h["馬番"] in m_major_numbers
]

m_single = [
    h
    for h in m_candidates
    if h["該当数"] == 1
]

# ==================================================
# 全14会場共通・Mを同距離持ちタイムで上から斬る
#
# まず従来どおり「中間重複」で候補を絞る。
#
# 優先順位：
#   1) 2部門以上＋主要5役外
#   2) 2部門以上＋主要5役
#   3) 1部門だけ該当
#
# 各グループ内だけ、
# 今回と完全同距離の持ちタイム
# （総合評価で使っている上位2走平均）が速い順に並べる。
#
# 同距離タイムあり → 速い順
# 同距離タイムなし → 従来M順位を維持
#
# A・Eなど同じ買い目内の馬と被った場合は、
# 既存のアルファベット競合処理で次のM候補へ繰り下がる。
#
# ※Mの取得・並び替えは全14会場共通。
# ※園田でBそのものをMへ差し替える既存仕様はこの下で維持する。
# ==================================================
def get_m_same_distance_time(h):
    time_info = total_same_distance_time_map.get(
        h["馬番"]
    )

    if not time_info:
        return None

    return time_info.get(
        "代表タイム"
    )


def sort_m_group_by_time(group):
    return sorted(
        group,
        key=lambda h: (
            # 同距離タイムを持つ馬を先にする
            0
            if get_m_same_distance_time(h)
            is not None
            else 1,

            # 持ちタイムは小さいほど速い
            get_m_same_distance_time(h)
            if get_m_same_distance_time(h)
            is not None
            else float("inf"),

            # タイムが無い馬同士、同タイム時は
            # 従来のM評価で順位を維持する
            -h["Mスコア"],
            -h["該当数"],
            h["順位合計"],
            h["総合順位"],
            h["馬番"],
        )
    )


# 全14会場で共通して同距離持ちタイム順を適用
m_primary = sort_m_group_by_time(
    m_primary
)

m_secondary = sort_m_group_by_time(
    m_secondary
)

m_single = sort_m_group_by_time(
    m_single
)

m_selection_candidates = (
    m_primary
    + m_secondary
    + m_single
)

m_pool = unique_texts(
    [
        horse_text(h)
        for h in m_selection_candidates
    ]
    + all_bet_pool
)

# ==================================================
# 園田・持続だけは、買い目上のB候補そのものをMプールへ差し替える。
#
# 画面の「🌊 展開の向く馬」は、この時点ではまだ描画しない。
# MやBは後段の重複回避・斬り捨て処理で次候補へ動く可能性があるため、
# 最終買い目用の記号が確定した後に描画し、実際の買い目と一致させる。
# ==================================================
sonoda_b_uses_m = (
    baba_name == "園田"
    and bet_axis_type == "持続"
)

# ==================================================
# Mランキング・デバッグ表示
# 全14会場で同じ説明・同じ並びを表示
# ==================================================
if debug_mode:
    with st.expander(
        f"🧩 {baba_name}・中間重複Mランキング",
        expanded=False,
    ):
        st.caption(
            "2〜5位のみ加点｜"
            "2位=4点・3位=3点・4位=2点・5位=1点｜"
            "2部門以上＋主要5役外を優先｜"
            "全14会場・各グループ内は同距離持ちタイム順"
        )

        if not m_candidates:
            st.write(
                "M候補なし"
            )
        else:
            for rank, h in enumerate(
                m_selection_candidates[:10],
                start=1,
            ):
                detail_text = " / ".join(
                    f"{name}{value}位"
                    for name, value
                    in h["順位詳細"].items()
                )

                major_mark = (
                    "｜主要5役"
                    if h["馬番"]
                    in m_major_numbers
                    else "｜主要5役外"
                )

                m_time = (
                    get_m_same_distance_time(h)
                )

                m_time_text = (
                    f"{m_time:.1f}秒"
                    if m_time is not None
                    else "なし"
                )

                st.write(
                    f"{rank}位｜"
                    f"{h['馬番']}番 {h['馬名']} "
                    f"｜持ちタイム {m_time_text} "
                    f"｜M {h['Mスコア']}点 "
                    f"｜該当{h['該当数']}部門"
                    f"{major_mark}"
                )

                st.caption(
                    detail_text
                    if detail_text
                    else "該当順位なし"
                )

#
# 園田で正式3分類が「持続」の時だけ、
# Bの候補プールを従来の展開b_poolではなく、
# 「中間重複M＋持ちタイム優先」のm_poolへ差し替える。
#
# ・園田の前受けは買い目でBを使わず、Mを直接使用
# ・園田の差し軸Bは従来どおりb_pool
# ・他会場のBも従来どおりb_pool
# ・画面の「展開の向く馬」欄もM馬へ連動
# ・M記号そのものは従来どおりm_pool
# ==================================================
sonoda_b_pool = (
    m_pool
    if sonoda_b_uses_m
    else b_pool
)

alphabet_candidate_pools = {
    "A": [popular],
    "F": f_pool,
    "C": c_pool,
    "E": e_pool,
    "D": d_pool,
    "B": sonoda_b_pool,
    "G": g_pool,
    "I": i_pool,
    "N": n_pool,
    "J": j_pool,
    "K": k_pool,
    "L": l_pool,
    "M": m_pool,
}

# ==================================================
# 工程⑤・会場別ルール関数の共通インターフェース
#
# 42表の適用を候補プール完成後に置き、各会場×3タイプの
# 関数が同じcontextから条件とA〜M候補を参照できるようにする。
# この位置までcurrent_bet_templateの変更処理はないため、
# 42枠の設定済みルールは、すべてこの後で最終適用する。
# ==================================================
venue_axis_bet_rule_context = (
    build_venue_axis_bet_rule_context(
        track=baba_name,
        axis_type=bet_axis_type,
        legacy_axis_type=kyakushoku_type,
        axis_primary=axis_primary_for_bet,
        axis_secondary=axis_secondary_for_bet,
        axis_secondary_tags=(
            axis_secondary_tags_for_bet
        ),
        a_is_f=(
            int(total_best["馬番"])
            == int(popular_horse_num)
        ),
        d_is_a=(
            int(front_best["馬番"])
            == int(popular_horse_num)
        ),
        horse_count=len(horses),
        is_nankan_large_field=(
            is_nankan_large_field
        ),
        candidate_pools=(
            alphabet_candidate_pools
        ),
        existing_template=(
            current_bet_template
        ),
        current_distance=distance_num,
    )
)

# 14会場×3タイプの表は、すべて既存ロジックの後で適用する。
current_bet_template = apply_venue_axis_bet_override(
    current_bet_template,
    venue_axis_bet_rule_context,
)

alphabet_role_names = {
    "A": "軸",
    "F": "後詰め",
    "C": "地力",
    "E": "抑え",
    "D": "先行",
    "B": (
        "展開(M＝中間重複＋持ちタイム)"
        if sonoda_b_uses_m
        else (
            "展開(K＝3→4押上)"
            if baba_name in {"盛岡", "水沢"}
            else "展開"
        )
    ),
    "G": "穴3",
    "I": "穴2",
    "N": "穴5",
    "J": (
        "大井・共通TOP5展開2位"
        if oi_axis_has_sustain
        else "前進3位"
    ),
    "K": "3→4押上1位",
    "L": "総合押上1位",
    "M": "中間重複",
}

# J・K・Lは最後に確定する。
# 既存A〜Iの選出結果を追加記号で動かさないため。
# K/Lが両方必要な岩手では、L＝総合押上1位を優先して確定する。
# 同じ馬がK＝3→4押上1位にも該当した場合は、K側を次候補へ送る。
if baba_name in {"盛岡", "水沢"}:
    alphabet_priority = [
        "A",
        "B",
        "F",
        "C",
        "E",
        "D",
        "G",
        "I",
        "N",
        "J",
        "L",
        "K",
        "M",
    ]
else:
    alphabet_priority = [
        "A",
        "B",
        "F",
        "M",
        "C",
        "E",
        "D",
        "G",
        "I",
        "N",
        "L",
        "K",
        "J",
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
    同じ「1つの買い目」の中に出る記号同士だけを競合扱いにする。

    重要：
    ワイド2点が同じ軸を共有していても、
    それぞれの相手記号同士は競合扱いにしない。

    例：
      ワイド A-B / A-C
      B＝1番、C＝1番

    この場合でもBやCそのものは動かさない。
    三連複で使うアルファベットの役割を優先する。

    ワイド2点が同じ組み合わせになった場合だけ、
    後段の make_unique_wide_bets() で
    ワイド専用に次候補へずらす。
    """

    conflicts = {}

    # 同じ1つの買い目内に出る記号同士だけ競合。
    # 三連複・ワイド・浮き輪それぞれの
    # 「1点の中」で同じ馬にならないための最低限の制約。
    for bet_type, bet_group in template.items():
        for symbol_list in bet_group:
            for symbol in symbol_list:
                conflicts.setdefault(
                    symbol,
                    set(),
                )

                conflicts[symbol].update(
                    other_symbol
                    for other_symbol in symbol_list
                    if (
                        other_symbol != symbol
                        and not (
                            # 園田820m・前受けのA-B-Dだけは、
                            # BとDが同じ馬でもアルファベット本体は動かさない。
                            #
                            # 例：
                            # B=7、D=7 の場合でも
                            # D本体は7のまま保持。
                            #
                            # 実際のA-B-D買い目を作る時だけ、
                            # make_unique_trio_bets()側でDを次候補へ繰り下げる。
                            (
                                baba_name == "園田"
                                and distance_num == 820
                                and bet_axis_type == "前受け"
                                and {symbol, other_symbol} == {"B", "D"}
                            )
                            or (
                                # 大井のワイド A-F はワイド専用で重複解消する。
                                # F本体を2位へ動かさず、A=F1位なら
                                # make_unique_wide_bets() 側でF3位へ飛ばす。
                                baba_name == "大井"
                                and bet_type == "ワイド"
                                and symbol_list == ["A", "F"]
                                and {symbol, other_symbol} == {"A", "F"}
                            )
                            or (
                                # 高知・前受けのワイド A-M 専用。
                                # AとMが同じ馬でもM本体の順位は動かさず、
                                # ワイド生成時だけ次候補へ繰り下げる。
                                baba_name == "高知"
                                and bet_axis_type == "前受け"
                                and bet_type == "ワイド"
                                and symbol_list == ["A", "M"]
                                and {symbol, other_symbol} == {"A", "M"}
                            )
                            or (
                                # 高知・差しの三連複2点目 A-M-L 専用。
                                # 新しい買い目を追加したことでA/M/L本体の
                                # 選出順位が動かないよう、競合解消は
                                # make_unique_trio_bets() 内だけで行う。
                                baba_name == "高知"
                                and bet_axis_type == "差し"
                                and bet_type == "三連複"
                                and symbol_list == ["A", "M", "L"]
                                and {symbol, other_symbol}.issubset(
                                    {"A", "M", "L"}
                                )
                            )
                            or (
                                # 佐賀・前受けの3点目 A-M-L 専用。
                                #
                                # 今回は「従来3点目 A-B-L のBだけをMへ変更」
                                # したいので、Mの追加によってL本体の選出順位まで
                                # 動かさないようにする。
                                #
                                # MとLが同じ馬になった場合の重複解消は、
                                # make_unique_trio_bets() の買い目内処理へ任せる。
                                #
                                # これにより、従来の1点目・2点目の選出結果を維持し、
                                # 3点目だけを A-M-L に変更できる。
                                baba_name == "佐賀"
                                and bet_axis_type == "前受け"
                                and bet_type == "三連複"
                                and symbol_list == ["A", "M", "L"]
                                and {symbol, other_symbol} == {"M", "L"}
                            )
                        )
                    )
                )

    # 以前はここで、
    # A-B / A-C のようなワイド2点について
    # BとCも競合扱いにしていた。
    #
    # その処理だとワイドの重複回避のために
    # B（展開）そのものが次候補へ動き、
    # 三連複まで変わってしまうため廃止。
    #
    # ワイドの重複はワイド生成時だけ解消する。

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
    alphabet_priority の順で確定する。
    現在は A → B → F → C → E → D → G → I → J → K → L → M。

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
    # アルファベット優先順位は
    # alphabet_priority をそのまま使う。
    # B（展開）とF（後詰め）が同じ馬でも、
    # Fを先に確定し、後から処理されるBを次候補へ繰り下げる。
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

def make_unique_wide_bets(
    symbol_templates,
    selected_symbols,
    excluded_numbers=None,
):
    """
    ワイドを上から順番に作る。

    最優先：
    三連複用に確定したアルファベットは変更しない。

    例：
      B（展開）＝1番
      C（地力）＝1番
      ワイド ＝ A-B / A-C

    この場合、
    BやCのアルファベット本体を動かすのではなく、

      1点目 A-B はそのまま
      2点目 A-C だけ、Cの次候補へワイド専用でずらす

    という処理を行う。

    そのため三連複では、
    B＝1番をそのまま使用できる。
    """

    excluded_numbers = set(
        excluded_numbers or set()
    )

    result = []
    used_wide_keys = set()

    for symbol_list in symbol_templates:

        if len(symbol_list) != 2:
            continue

        if not all(
            symbol in selected_symbols
            for symbol in symbol_list
        ):
            continue

        # アルファベット本体は変更しない。
        bet = [
            selected_symbols[symbol]
            for symbol in symbol_list
        ]

        bet_numbers = [
            get_num(horse_name)
            for horse_name in bet
        ]

        bet_key = frozenset(
            bet_numbers
        )

        # ==================================================
        # 大井限定・ワイド A-F の特別ルール
        #
        # Fランキング1位が軸Aと同じ馬だった場合、
        # 通常の「次候補＝F2位」にはせず、
        # F3位から下へ順番に探す。
        #
        # これはワイド専用処理。
        # F記号本体や三連複のF選出は変更しない。
        # ==================================================
        if (
            baba_name == "大井"
            and symbol_list == ["A", "F"]
            and f_pool
            and get_num(f_pool[0]) == get_num(bet[0])
        ):
            resolved_ooi_af = None

            # index 2 ＝ Fランキング3位。
            # 3位が斬り捨て・A重複などで使えない場合だけ、
            # 4位、5位…へ順番に繰り下げる。
            for candidate in f_pool[2:]:
                candidate_number = get_num(candidate)

                if candidate_number in excluded_numbers:
                    continue

                if candidate_number == get_num(bet[0]):
                    continue

                test_bet = [
                    bet[0],
                    candidate,
                ]

                test_key = frozenset(
                    get_num(horse_name)
                    for horse_name in test_bet
                )

                if test_key in used_wide_keys:
                    continue

                resolved_ooi_af = test_bet
                break

            if resolved_ooi_af is not None:
                result.append(
                    resolved_ooi_af
                )
                used_wide_keys.add(
                    frozenset(
                        get_num(horse_name)
                        for horse_name
                        in resolved_ooi_af
                    )
                )
                continue

            # F3位以降に有効馬がいない場合は、
            # F2位へ戻さず、このA-Fワイドは作らない。
            continue

        # 2頭が別馬で、
        # まだ出していないワイドならそのまま確定。
        if (
            len(set(bet_numbers)) == 2
            and bet_key not in used_wide_keys
        ):
            result.append(
                bet
            )

            used_wide_keys.add(
                bet_key
            )

            continue

        # --------------------------------------------------
        # 同じワイドがすでに出ている、
        # または同一馬同士になってしまった場合だけ
        # 「このワイド内」で次候補へずらす。
        #
        # 後ろの記号から変更する。
        # A（軸）は固定。
        # --------------------------------------------------
        resolved_bet = None

        for change_index in range(
            len(symbol_list) - 1,
            -1,
            -1,
        ):

            change_symbol = symbol_list[
                change_index
            ]

            # 軸Aは絶対に動かさない
            if change_symbol == "A":
                continue

            candidate_pool = (
                alphabet_candidate_pools.get(
                    change_symbol,
                    all_bet_pool,
                )
            )

            current_horse = (
                selected_symbols[
                    change_symbol
                ]
            )

            current_number = get_num(
                current_horse
            )

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

            # 現在馬より下位の候補だけを試す。
            # これで各アルファベット本来の優先順位を守る。
            next_candidates = (
                candidate_pool[
                    current_pool_index + 1:
                ]
                if current_pool_index >= 0
                else candidate_pool
            )

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

                # ワイド内で同じ馬は不可
                if len(set(test_numbers)) != 2:
                    continue

                test_key = frozenset(
                    test_numbers
                )

                # すでに出したワイドと同じ組み合わせも不可
                if test_key in used_wide_keys:
                    continue

                resolved_bet = (
                    test_bet
                )
                break

            if resolved_bet is not None:
                break

        if resolved_bet is not None:

            result.append(
                resolved_bet
            )

            used_wide_keys.add(
                frozenset(
                    get_num(horse_name)
                    for horse_name
                    in resolved_bet
                )
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

    さらに、AとFが別馬のため2点目がA-F-○になり、
    1点目と同じ3頭になった場合は、
    本来の抑え候補を3頭目として優先する。
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

        # ==================================================
        # 三連複2点目 A-F-○ の重複対策
        #
        # Aと後詰めFが別馬のため2点目を A-F-○ にした結果、
        # 1点目と同じ3頭になった場合は、
        # ○を「本来の抑え候補」へ差し替える。
        #
        # ここでは ana_candidates だけを使い、
        # 穴2・穴3や全出走馬への補充は行わない。
        # 抑え候補で有効な3頭目を作れなかった場合だけ、
        # 下の従来の重複解消ロジックへ進む。
        # ==================================================
        if (
            bet_index == 1
            and len(symbol_list) >= 2
            and symbol_list[0] == "A"
            and symbol_list[1] == "F"
            and bet_key in used_trio_keys
            and ana_candidates
        ):
            second_trio_osae_pool = unique_texts(
                [
                    horse_text(h)
                    for h in ana_candidates
                ]
            )

            for candidate in second_trio_osae_pool:

                candidate_number = get_num(candidate)

                if candidate_number in excluded_numbers:
                    continue

                test_bet = [
                    bet[0],
                    bet[1],
                    candidate,
                ]

                test_numbers = [
                    get_num(horse_name)
                    for horse_name in test_bet
                ]

                # A・F・抑えの3頭がすべて別馬であること
                if len(set(test_numbers)) != 3:
                    continue

                test_key = frozenset(test_numbers)

                # 1点目と同じ3頭なら次の抑え候補へ
                if test_key in used_trio_keys:
                    continue

                resolved_bet = test_bet
                break

            # 抑え候補で解決できた場合は、
            # 後続のCや穴候補への繰り下げ処理を行わず確定する。
            if resolved_bet is not None:
                result.append(resolved_bet)
                used_trio_keys.add(
                    frozenset(
                        get_num(horse_name)
                        for horse_name in resolved_bet
                    )
                )
                continue
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

            continue

        # ==================================================
        # 三連複の最終不足救済
        #
        # 記号上は別の買い目でも、実馬へ変換すると
        # 1点目と同じ3頭になり、通常の次候補でも
        # 解消できないことがある。
        #
        # 例：
        #   A-B-E = 5-2-3
        #   A-F-K = 5-2-3
        #   （BとF、EとKが同じ馬）
        #
        # この場合、Aと2頭目の役割は固定したまま、
        # 3頭目だけを「意味のある候補」へ救済する。
        #
        # 優先：
        #   ① 元の3頭目記号の次候補
        #   ② K（3角→4角押上）
        #   ③ L（2角→4角総合押上）
        #   ④ E（抑え）
        #   ⑤ G（穴3）
        #
        # 同じ3頭の並び替えは三連複では同一なので不可。
        # Aは絶対に動かさない。
        # 1・2頭目もこの最終救済では動かさない。
        # ==================================================
        if (
            len(symbol_list) == 3
            and symbol_list[0] == "A"
            and len(bet) == 3
        ):

            rescue_first = bet[0]
            rescue_second = bet[1]

            rescue_first_number = get_num(
                rescue_first
            )

            rescue_second_number = get_num(
                rescue_second
            )

            # Aと2頭目がすでに同一馬なら、
            # 3頭目だけでは三連複を成立させられない。
            if (
                rescue_first_number
                != rescue_second_number
            ):

                original_third_symbol = (
                    symbol_list[2]
                )

                rescue_symbol_order = []

                for rescue_symbol in (
                    [original_third_symbol]
                    + ["K", "L", "E", "G"]
                ):
                    if (
                        rescue_symbol != "A"
                        and rescue_symbol
                        not in rescue_symbol_order
                    ):
                        rescue_symbol_order.append(
                            rescue_symbol
                        )

                final_rescue_bet = None

                for rescue_symbol in (
                    rescue_symbol_order
                ):

                    rescue_pool = (
                        alphabet_candidate_pools.get(
                            rescue_symbol,
                            [],
                        )
                    )

                    if not rescue_pool:
                        continue

                    # その記号が今回すでに選出済みなら、
                    # 本来候補から下位へ順送りする。
                    # 未使用記号ならランキング1位から試す。
                    selected_rescue_horse = (
                        bet_selected_symbols.get(
                            rescue_symbol
                        )
                        or selected_symbols.get(
                            rescue_symbol
                        )
                    )

                    rescue_start_index = 0

                    if selected_rescue_horse:

                        selected_rescue_number = (
                            get_num(
                                selected_rescue_horse
                            )
                        )

                        found_index = next(
                            (
                                index
                                for index, candidate
                                in enumerate(
                                    rescue_pool
                                )
                                if get_num(candidate)
                                == selected_rescue_number
                            ),
                            -1,
                        )

                        if found_index >= 0:
                            rescue_start_index = (
                                found_index
                            )

                    for candidate in rescue_pool[
                        rescue_start_index:
                    ]:

                        candidate_number = get_num(
                            candidate
                        )

                        if (
                            candidate_number
                            in excluded_numbers
                        ):
                            continue

                        if candidate_number in {
                            rescue_first_number,
                            rescue_second_number,
                        }:
                            continue

                        test_bet = [
                            rescue_first,
                            rescue_second,
                            candidate,
                        ]

                        test_numbers = [
                            get_num(horse_name)
                            for horse_name
                            in test_bet
                        ]

                        if len(set(test_numbers)) != 3:
                            continue

                        test_key = frozenset(
                            test_numbers
                        )

                        if test_key in used_trio_keys:
                            continue

                        final_rescue_bet = (
                            test_bet
                        )
                        break

                    if final_rescue_bet is not None:
                        break

                if final_rescue_bet is not None:

                    result.append(
                        final_rescue_bet
                    )

                    used_trio_keys.add(
                        frozenset(
                            get_num(horse_name)
                            for horse_name
                            in final_rescue_bet
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

# 画面表示を実際の買い目と一致させるため、
# どの記号セットから最終買い目を作ったかも保持する。
trio_symbol_source = final_bet_symbols
wide_symbol_source = final_bet_symbols
float_symbol_source = final_bet_symbols

trio_bets = make_unique_trio_bets(
    current_bet_template["三連複"],
    final_bet_symbols,
    excluded_numbers=kirisute_horse_numbers,
)

wide_bets = make_unique_wide_bets(
    current_bet_template["ワイド"],
    final_bet_symbols,
    excluded_numbers=kirisute_horse_numbers,
)

float_bets = make_bets_from_symbols(
    current_bet_template["浮き輪"],
    final_bet_symbols,
)

# 必要な買い目を作れなかった場合は、
# 斬り捨て前の通常選出へ戻す。
#
# 南関以外は原則、A-Bワイドを外して三連複3点。
# ただし盛岡だけは例外で、三連複2点＋通常ワイド2点＋浮き輪1点に戻す。
# 園田は逃げ・先行軸のみ3点目A-E-K、それ以外はA-B-K。
# 笠松・佐賀・水沢・高知は3点目A-B-L。
# 金沢・名古屋・姫路・門別は3点目A-D-G、A=DならA-B-G。
# 浦和・船橋・川崎の10頭以上はA-B-F追加で三連複3点。
# 大井の多頭数Jルールは従来どおり維持する。
# 大井の先行軸／持続軸だけは頭数に関係なく
# A-B-D / A-G-L / A-D-G の三連複3点へ固定。
required_trio_count = len(
    current_bet_template[
        "三連複"
    ]
)

if len(trio_bets) < required_trio_count:
    trio_bets = make_unique_trio_bets(
        current_bet_template["三連複"],
        normal_bet_symbols,
    )
    trio_symbol_source = normal_bet_symbols

required_wide_count = len(
    current_bet_template[
        "ワイド"
    ]
)

if len(wide_bets) < required_wide_count:
    wide_bets = make_unique_wide_bets(
        current_bet_template["ワイド"],
        normal_bet_symbols,
    )
    wide_symbol_source = normal_bet_symbols

if len(float_bets) < 1:
    float_bets = make_bets_from_symbols(
        current_bet_template["浮き輪"],
        normal_bet_symbols,
    )
    float_symbol_source = normal_bet_symbols


def make_float_bets_from_pools(
    symbol_templates,
    excluded_numbers=None,
):
    """
    浮き輪専用の最終救済。

    三連複・ワイド用に確定した記号配置とは切り離し、
    各記号本来の候補プールから浮き輪1点だけを作る。

    重要：
    ・三連複2点／通常ワイド2点は一切変更しない。
    ・盛岡の浮き輪ルール自体も変更しない。
    ・同じ馬同士の組み合わせだけは出さない。
    """

    excluded_numbers = set(
        excluded_numbers or set()
    )

    result = []

    for symbol_list in symbol_templates:

        resolved_bet = []
        used_numbers = set()

        for symbol in symbol_list:

            preferred_candidates = []

            if symbol in final_bet_symbols:
                preferred_candidates.append(
                    final_bet_symbols[symbol]
                )

            if symbol in normal_bet_symbols:
                preferred_candidates.append(
                    normal_bet_symbols[symbol]
                )

            candidate_pool = unique_texts(
                preferred_candidates
                + alphabet_candidate_pools.get(
                    symbol,
                    all_bet_pool,
                )
                + all_bet_pool
            )

            selected_horse = None

            # まずは斬り捨て馬を避けて作る。
            for candidate in candidate_pool:
                candidate_number = get_num(
                    candidate
                )

                if candidate_number in used_numbers:
                    continue

                if candidate_number in excluded_numbers:
                    continue

                selected_horse = candidate
                break

            # それでも作れない時だけ斬り捨て前へ戻し、
            # 浮き輪が空欄になることを防ぐ。
            if selected_horse is None:
                for candidate in candidate_pool:
                    candidate_number = get_num(
                        candidate
                    )

                    if candidate_number in used_numbers:
                        continue

                    selected_horse = candidate
                    break


            if selected_horse is None:
                resolved_bet = []
                break

            resolved_bet.append(
                selected_horse
            )
            used_numbers.add(
                get_num(selected_horse)
            )

        if (
            len(resolved_bet)
            == len(symbol_list)
            and len({
                get_num(horse_name)
                for horse_name in resolved_bet
            })
            == len(resolved_bet)
        ):
            result.append(
                resolved_bet
            )
            break

    return result


# 最終救済：浮き輪の記号ルールはそのまま、
# 候補プールから1点だけ作り直す。
if len(float_bets) < 1:
    float_bets = make_float_bets_from_pools(
        current_bet_template["浮き輪"],
        excluded_numbers=kirisute_horse_numbers,
    )


# ==================================================
# 園田のみ・Mを「🌊 展開の向く馬」として画面表示
#
# 目的：
#   買い目にMが出るのに主要5頭表示にMが見えない、という混乱を防ぐ。
#
# 方針：
# ・園田で買い目にMを直接使う時
#     → 最終買い目用に確定したMを表示
# ・園田・持続でB候補をMプールへ差し替えている時
#     → 最終買い目用に確定したB（実体はM候補）を表示
# ・園田でもMを使わない差し等、および他会場
#     → 従来の展開馬Bを表示
#
# B/Mの取得ロジックや買い目ルール自体は変更しない。
# ==================================================
def template_uses_symbol(template, symbol):
    return any(
        symbol in symbol_list
        for bet_group in template.values()
        for symbol_list in bet_group
    )

sonoda_directly_uses_m = (
    baba_name == "園田"
    and template_uses_symbol(
        current_bet_template,
        "M",
    )
)

sonoda_display_m_horse = None

if sonoda_directly_uses_m:
    # 現在の園田ルールではMは三連複で使用。
    # 斬り捨て等で通常選出へ戻った場合も、実際に使った記号セットへ合わせる。
    sonoda_display_m_horse = (
        trio_symbol_source.get("M")
        or final_bet_symbols.get("M")
        or normal_bet_symbols.get("M")
    )

elif sonoda_b_uses_m:
    # 持続ではBの候補プール自体がM。
    sonoda_display_m_horse = (
        trio_symbol_source.get("B")
        or wide_symbol_source.get("B")
        or final_bet_symbols.get("B")
        or normal_bet_symbols.get("B")
    )

with tenkai_card_placeholder.container():
    if sonoda_display_m_horse:
        show_card(
            "🌊",
            "展開の向く馬",
            "M：中間重複＋同距離持ちタイム",
            sonoda_display_m_horse,
            "#e0f2fe",
            "#7dd3fc",
            "#0369a1"
        )
    else:
        show_card(
            "🌊",
            "展開の向く馬",
            (
                f"主：{tenkai_best.get('主脚質', tenkai_best.get('候補脚質', '不明'))}"
                f"｜副：{tenkai_best.get('副脚質表示', 'なし')}"
            ),
            tenkai_horse,
            "#e0f2fe",
            "#7dd3fc",
            "#0369a1"
        )


if debug_mode:

    with st.expander(
        "🔤 買い目用アルファベット選出",
        expanded=False,
    ):

        st.write(
            "優先順位："
            + " → ".join(
                alphabet_priority
            )
        )

        st.write(
            f"軸タイプ：{kyakushoku_type}"
        )

        if (
            baba_name == "門別"
            and kyakushoku_type == "差し"
        ):
            st.write(
                "🟣 門別・差し軸："
                "三連複 A-B-I / A-F-E"
            )

        if (
            baba_name == "門別"
            and kyakushoku_type in {
                "先行",
                "持続",
            }
        ):
            st.write(
                f"🟣 門別・{kyakushoku_type}軸："
                "三連複2点目 A-C-I"
            )

        if (
            baba_name == "門別"
            and kyakushoku_type == "逃げ"
        ):
            st.write(
                "🟣 門別・逃げ軸："
                "三連複2点目 A-J-G"
            )

        if is_sonoda_escape_senko:
            st.write(
                "🟢 園田・逃げ＋先行："
                "三連複 A-B-I / A-D-G"
            )

        if (
            baba_name == "佐賀"
            and kyakushoku_type == "先行"
        ):
            st.write(
                "🔵 佐賀・先行軸："
                "三連複1点目 A-B-L "
                "（L＝2角→4角・総合押上1位）"
            )

        if (
            baba_name == "園田"
            and kyakushoku_type == "先行"
            and axis_secondary_for_bet == "押上"
        ):
            st.write(
                "🟢 園田・先行＋押上軸："
                "三連複1点目 A-B-L "
                "（L＝2角→4角・総合押上1位）"
            )

        if (
            baba_name == "園田"
            and kyakushoku_type == "差し"
        ):
            st.write(
                "🟢 園田・差し軸："
                "ワイド2点目 A-E"
            )

        if (
            baba_name == "園田"
            and kyakushoku_type == "先行"
        ):
            st.write(
                "🧪 園田・先行軸 M試験："
                "三連複 A-E-M / A-E-L / A-G-K"
            )

            st.write(
                "M候補："
                + (
                    " → ".join(
                        m_pool[:5]
                    )
                    if m_pool
                    else "候補なし"
                )
            )

        if (
            baba_name == "笠松"
            and kyakushoku_type == "先行"
        ):
            st.write(
                "🟢 笠松・先行軸："
                "三連複2点目 A-E-G"
            )

        if iwate_tenkai_uses_k:
            st.write(
                "🌊 岩手・展開B固定："
                "B＝K（3角→4角【勝負所重視】押上最上位）"
            )

        if is_iwate_front_axis:
            st.write(
                "🟦 岩手・前受け軸："
                "三連複1点目 A-B-L "
                "｜浮き輪 L-K"
            )

        if (
            baba_name == "盛岡"
            and kyakushoku_type in {
                "先行",
                "持続",
            }
        ):
            st.write(
                "🟦 盛岡・先行／持続軸："
                "三連複2点目 A-C-G"
            )

        if (
            baba_name == "盛岡"
            and kyakushoku_type in {
                "差し",
                "持続",
            }
        ):
            st.write(
                "🟦 盛岡・差し／持続軸："
                "三連複1点目 A-B-C"
            )

        if (
            baba_name == "盛岡"
            and kyakushoku_type == "差し"
        ):
            st.write(
                "🟦 盛岡・差し軸："
                "浮き輪 K-L"
            )


            st.write(
                "K＝3角→4角【勝負所重視】1位 "
                "｜L＝2角→4角【総合押上】1位"
            )

        if baba_name == "盛岡":
            st.write(
                "🟦 盛岡専用：三連複2点＋通常ワイド2点＋浮き輪1点 "
                "（ワイド系3点・合計5点）"
            )

        if is_non_nankan_bet_track:

            st.write(
                "🌱 南関以外・買い方変更："
                "A-Bワイドを削除 → 三連複3点目へ移行"
            )

            if baba_name in NON_NANKAN_ABK_TRACKS:

                if kyakushoku_type in {
                    "逃げ",
                    "先行",
                }:
                    st.write(
                        f"{baba_name}・{kyakushoku_type}軸："
                        "三連複3点目 A-E-K"
                    )

                else:
                    st.write(
                        f"{baba_name}：三連複3点目 A-B-K"
                    )

            elif baba_name in NON_NANKAN_ABL_TRACKS:
                st.write(
                    f"{baba_name}：三連複3点目 A-B-L"
                )

            elif non_nankan_adg_switched_to_abg:
                st.write(
                    f"{baba_name}：本来のDがAと同馬のため "
                    "三連複3点目 A-B-G"
                )

            else:
                st.write(
                    f"{baba_name}：三連複3点目 A-D-G"
                )

            st.write(
                f"ワイドは1点："
                f"{current_bet_template['ワイド']}"
            )

        if (
            baba_name == "大井"
            and len(horses) <= 10
        ):
            st.write(
                "🔵 大井・10頭以下："
                "三連複3点・通常ワイド1点・浮き輪1点"
            )
            st.write(
                f"最終買い目：{current_bet_template}"
            )

        elif is_ooi_escape:
            st.write(
                "🔵 大井・逃げ軸："
                "三連複3点目 A-D-E "
                "｜ワイド2点目 A-D"
            )

        elif is_ooi_senko_or_jizoku:
            if kyakushoku_type == "持続":
                st.write(
                    "🔵 大井・持続軸："
                    "三連複 A-B-D / A-G-L / A-K-J"
                )
                st.write(
                    "L＝2角→4角【総合押上】1位｜"
                    "K＝3角→4角【勝負所重視】押上1位｜"
                    "J＝前進気勢3位"
                )
            else:
                st.write(
                    "🔵 大井・先行軸："
                    "三連複 A-B-D / A-G-L / A-D-G"
                )
                st.write(
                    "L＝2角→4角【総合押上】1位"
                )

        elif is_nankan_large_field:
            if baba_name in {"浦和", "船橋", "川崎"}:
                st.write(
                    f"🏙 {baba_name}10頭以上："
                    "三連複3点目 A-B-F"
                )
            else:
                st.write(
                    "🏙 大井10頭以上："
                    "三連複3点目 A-B-J"
                )

                st.write(
                    "J候補："
                    + (
                        " → ".join(j_pool)
                        if j_pool
                        else "候補なし"
                    )
                )

        if kyakushoku_type == "先行":
            st.write(
                "先行軸マーブル分岐："
                f"副＝{axis_marble_profile.get('副脚質表示', 'なし')} "
                f"｜三連複1点目＝"
                f"{'-'.join(current_bet_template['三連複'][0])}"
            )

        st.caption(
            "三連複優先：ワイド2点が同じ組み合わせになる場合でも、"
            "B・Cなどのアルファベット本体は動かさず、"
            "ワイド側だけ次候補へ補正します。"
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
# NAR公式オッズ取得
#
# NAR公式スマホ版の人気順オッズを第一候補として取得する。
# スマホ版の正式ホストは sp.keiba.go.jp。
# 取得できない場合だけPC版へフォールバックする。
#
# ・三連複：単一倍率（例 18.6倍）
# ・ワイド：下限〜上限（例 3.4〜3.8倍）
# ・オッズ未発表 / 取得失敗時は何も表示しない
# ・予想ロジックや買い目生成には一切使わない
# ==================================================

def _normalize_odds_text(value):
    return (
        str(value or "")
        .replace("　", "")
        .replace("−", "-")
        .replace("－", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("～", "-")
        .replace("〜", "-")
        .strip()
    )


def _parse_mobile_trio_odds_page(soup):
    """三連複の人気順表を {(1,2,3): 18.6} にする。"""
    odds_map = {}

    for row in soup.find_all("tr"):
        row_text = " ".join(
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"])
        )
        row_text = _normalize_odds_text(row_text)

        if not row_text:
            continue

        combo_match = re.search(
            r"(?<!\d)(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})(?!\d)",
            row_text,
        )
        if combo_match is None:
            continue

        combo_numbers = tuple(
            sorted(int(combo_match.group(i)) for i in (1, 2, 3))
        )
        if len(set(combo_numbers)) != 3:
            continue

        # 組合せより後ろにある最初の数値が三連複オッズ。
        suffix = row_text[combo_match.end():]
        odds_match = re.search(r"\d+(?:\.\d+)?", suffix)
        if odds_match is None:
            continue

        try:
            odds_value = float(odds_match.group(0))
        except (TypeError, ValueError):
            continue

        if odds_value > 0:
            odds_map[combo_numbers] = odds_value

    return odds_map


def _parse_mobile_wide_odds_page(soup):
    """ワイドの人気順表を {(1,2): (3.4,3.8)} にする。"""
    odds_map = {}

    for row in soup.find_all("tr"):
        row_text = " ".join(
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"])
        )
        row_text = _normalize_odds_text(row_text)

        if not row_text:
            continue

        combo_match = re.search(
            r"(?<!\d)(\d{1,2})\s*-\s*(\d{1,2})(?!\s*-\s*\d)(?!\d)",
            row_text,
        )
        if combo_match is None:
            continue

        combo_numbers = tuple(
            sorted((int(combo_match.group(1)), int(combo_match.group(2))))
        )
        if len(set(combo_numbers)) != 2:
            continue

        # 組合せより後ろの「下限-上限」を取得。
        suffix = row_text[combo_match.end():]
        range_match = re.search(
            r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)",
            suffix,
        )
        if range_match is None:
            continue

        try:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
        except (TypeError, ValueError):
            continue

        if low <= 0 or high <= 0:
            continue

        if low > high:
            low, high = high, low

        odds_map[combo_numbers] = (low, high)

    return odds_map


@st.cache_data(ttl=30, show_spinner=False)
def get_official_bet_odds(source_url):
    """
    NAR公式から三連複・ワイドの現在オッズを取得する。

    第一候補：sp.keiba.go.jp のスマホ版人気順ページ
    第二候補：www.keiba.go.jp のPC版ページ

    三連複とワイドは個別に取得するため、片方の失敗で
    もう片方まで空になることはない。
    """
    import requests
    from bs4 import BeautifulSoup

    result = {
        "三連複": {},
        "ワイド": {},
        "取得元": {},
        "エラー": {},
    }

    try:
        parsed = urlparse(source_url)
        params = parse_qs(parsed.query)

        race_date_value = params.get("k_raceDate", [None])[0]
        race_no_value = params.get("k_raceNo", [None])[0]
        baba_code_value = params.get("k_babaCode", [None])[0]
    except Exception:
        return result

    if not all((race_date_value, race_no_value, baba_code_value)):
        return result

    common_params = {
        "k_raceDate": race_date_value,
        "k_raceNo": race_no_value,
        "k_babaCode": baba_code_value,
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9",
    }

    # PC版は全組合せ表を持っているため先に取得し、
    # スマホ版は現在表示されている人気順オッズを補助として重ねる。
    # 以前はスマホ版で1件でも取れると break していたため、
    # 上位人気にない組合せ（例：2-3-6）が辞書に入らないことがあった。
    targets = {
        "三連複": {
            "parser": _parse_mobile_trio_odds_page,
            "urls": [
                "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/Odds3LenFuku",
                "https://sp.keiba.go.jp/KeibaWebSP/TodayRaceInfo/S_Odds3LenFuku",
            ],
        },
        "ワイド": {
            "parser": _parse_mobile_wide_odds_page,
            "urls": [
                "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/OddsWide",
                "https://sp.keiba.go.jp/KeibaWebSP/TodayRaceInfo/S_OddsWide",
            ],
        },
    }

    for bet_type, target in targets.items():
        errors = []
        merged_odds = {}
        source_urls = []

        for odds_url in target["urls"]:
            try:
                request_params = dict(common_params)

                # PC版は人気順の一覧表を指定。
                # 一覧は25件ずつのブロックでもHTML内には全件存在するため、
                # 高配当の組合せまでまとめて取得できる。
                if "/KeibaWeb/" in odds_url:
                    request_params["odds_flg"] = 5

                response = requests.get(
                    odds_url,
                    params=request_params,
                    headers=headers,
                    timeout=10,
                    allow_redirects=True,
                )
                response.raise_for_status()

                soup = BeautifulSoup(response.content, "html.parser")
                odds_map = target["parser"](soup)

                if odds_map:
                    # PC版の全件を土台にし、後から取得したスマホ版の
                    # 同一組合せだけ最新値として上書きする。
                    merged_odds.update(odds_map)
                    source_urls.append(response.url)
                else:
                    errors.append(
                        f"{odds_url}：HTTP{response.status_code}・オッズ0件"
                    )

            except Exception as exc:
                errors.append(
                    f"{odds_url}：{type(exc).__name__}"
                )

        result[bet_type] = merged_odds

        if source_urls:
            result["取得元"][bet_type] = source_urls

        if errors and not merged_odds:
            result["エラー"][bet_type] = errors

    return result


def get_trio_odds_suffix(bet, trio_odds_map):
    try:
        key = tuple(sorted(get_num(horse_text) for horse_text in bet))
    except Exception:
        return ""

    odds_value = trio_odds_map.get(key)
    if odds_value is None:
        return ""

    return f"（{odds_value:.1f}倍）"


def get_wide_odds_suffix(bet, wide_odds_map):
    try:
        key = tuple(sorted(get_num(horse_text) for horse_text in bet))
    except Exception:
        return ""

    odds_value = wide_odds_map.get(key)
    if odds_value is None:
        return ""

    low, high = odds_value
    return f"（{low:.1f}〜{high:.1f}倍）"


# 一括検証では倍率表示を使わないため、NAR公式オッズ通信を完全に省略する。
# 通常分析では従来どおり三連複・ワイドの現在オッズを取得する。
if st.session_state.get("batch_mode", False):
    official_bet_odds = {
        "三連複": {},
        "ワイド": {},
    }
else:
    official_bet_odds = get_official_bet_odds(url)

trio_odds_map = official_bet_odds.get("三連複", {})
wide_odds_map = official_bet_odds.get("ワイド", {})

if debug_mode:
    st.caption(
        "公式オッズ取得｜"
        f"三連複 {len(trio_odds_map)}件｜"
        f"ワイド {len(wide_odds_map)}件"
    )

    odds_sources = official_bet_odds.get("取得元", {})
    if odds_sources:
        st.caption(
            "オッズ取得元｜"
            + "｜".join(
                f"{bet_type}:"
                + (" / ".join(source) if isinstance(source, list) else str(source))
                for bet_type, source in odds_sources.items()
            )
        )

    odds_errors = official_bet_odds.get("エラー", {})
    if odds_errors:
        st.caption(
            "オッズ取得エラー｜"
            + "｜".join(
                f"{bet_type}:{' / '.join(messages)}"
                for bet_type, messages in odds_errors.items()
            )
        )

# ==================================================
# 最終表示
# ==================================================
st.subheader(
    f"おすすめの三連複 {len(trio_bets)}点"
)

for bet in trio_bets:
    st.write(
        f"{bet[0]} - {bet[1]} - {bet[2]}"
        + get_trio_odds_suffix(
            bet,
            trio_odds_map,
        )
    )

# 通常買い目とは完全に独立した、使用者の追加1点。
all_horse_options = [
    f"{h['馬番']}番 {h['馬名']}"
    for h in horses
]
unselected_option = "未選択"

st.markdown("#### 三連複オリジナル")
st.caption(f"軸馬：{popular_horse_label}")

original_trio_options = [
    horse_label
    for horse_label in all_horse_options
    if get_num(horse_label) != popular_horse_num
]

if st.session_state.get("original_trio_first") not in (
    [unselected_option] + original_trio_options
):
    st.session_state.pop("original_trio_first", None)

trio_original_col1, trio_original_col2 = st.columns(2)

with trio_original_col1:
    original_trio_first = st.selectbox(
        "相手馬1",
        [unselected_option] + original_trio_options,
        key="original_trio_first",
    )

with trio_original_col2:
    original_trio_second_options = [
        horse_label
        for horse_label in original_trio_options
        if horse_label != original_trio_first
    ]
    if st.session_state.get("original_trio_second") not in (
        [unselected_option] + original_trio_second_options
    ):
        st.session_state.pop("original_trio_second", None)
    original_trio_second = st.selectbox(
        "相手馬2",
        [unselected_option] + original_trio_second_options,
        key="original_trio_second",
    )

if (
    original_trio_first != unselected_option
    and original_trio_second != unselected_option
):
    original_trio_bet = (
        popular_horse_label,
        original_trio_first,
        original_trio_second,
    )
    st.write(
        f"{popular_horse_label} - "
        f"{original_trio_first} - {original_trio_second}"
        + get_trio_odds_suffix(
            original_trio_bet,
            trio_odds_map,
        )
    )

st.subheader(
    f"おすすめのワイド {len(wide_bets)}点"
)

for bet in wide_bets:
    st.write(
        f"{bet[0]} - {bet[1]}"
        + get_wide_odds_suffix(
            bet,
            wide_odds_map,
        )
    )

st.markdown("#### ワイドオリジナル")

if st.session_state.get("original_wide_first") not in (
    [unselected_option] + all_horse_options
):
    st.session_state.pop("original_wide_first", None)

wide_original_col1, wide_original_col2 = st.columns(2)

with wide_original_col1:
    original_wide_first = st.selectbox(
        "馬1",
        [unselected_option] + all_horse_options,
        key="original_wide_first",
    )

with wide_original_col2:
    original_wide_second_options = [
        horse_label
        for horse_label in all_horse_options
        if horse_label != original_wide_first
    ]
    if st.session_state.get("original_wide_second") not in (
        [unselected_option] + original_wide_second_options
    ):
        st.session_state.pop("original_wide_second", None)
    original_wide_second = st.selectbox(
        "馬2",
        [unselected_option] + original_wide_second_options,
        key="original_wide_second",
    )

if (
    original_wide_first != unselected_option
    and original_wide_second != unselected_option
):
    original_wide_bet = (
        original_wide_first,
        original_wide_second,
    )
    st.write(
        f"{original_wide_first} - {original_wide_second}"
        + get_wide_odds_suffix(
            original_wide_bet,
            wide_odds_map,
        )
    )

st.markdown("### 🛟 カッパの浮き輪保険")

for bet in float_bets:
    st.write(
        f"{bet[0]} - {bet[1]}"
        + get_wide_odds_suffix(
            bet,
            wide_odds_map,
        )
    )

st.caption(
    "※買い目の一例です。最終判断はオッズや馬場を見て調整してください。"
)

# ==================================================
# 📊 公式結果自動取得・回収率計算
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


def extract_race_result_and_payouts(
    result_soup
):
    """
    NAR RaceMarkTable から
    ・1〜3着馬番
    ・ワイド払戻
    ・三連複払戻
    を取得する。
    """

    top3 = {}

    # ------------------------------------------
    # 1〜3着
    # ------------------------------------------
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

        if len(cells) < 4:
            continue

        # 通常の成績表：
        # 着順 / 枠番 / 馬番 / 馬名 ...
        if (
            cells[0] in {"1", "2", "3"}
            and cells[1].isdigit()
            and cells[2].isdigit()
        ):
            finish = int(
                cells[0]
            )

            horse_no = int(
                cells[2]
            )

            if finish not in top3:
                top3[
                    finish
                ] = horse_no

        if len(top3) == 3:
            break

    result_text = result_soup.get_text(
        " ",
        strip=True,
    )

    wide_payouts = {}
    trio_payouts = {}

    # ------------------------------------------
    # ワイド
    # ------------------------------------------
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
                wide_payouts[
                    nums
                ] = int(
                    payout.replace(
                        ",",
                        "",
                    )
                )

    # ------------------------------------------
    # 三連複
    # ------------------------------------------
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
            trio_payouts[
                nums
            ] = int(
                trio_match.group(2)
                .replace(
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

check_result = (
    st.button(
        "🏁 結果を取得して回収率を計算"
    )
    or st.session_state.batch_mode
)

if check_result:

    result_url = url.replace(
        "/DebaTable?",
        "/RaceMarkTable?",
    )

    if result_url == url:
        result_url = url.replace(
            "DebaTable",
            "RaceMarkTable",
        )

    try:

        # --------------------------------------
        # 結果ページ取得
        # 一時的な429/5xxや反映遅延に備えて最大3回まで再試行
        # --------------------------------------
        session = requests.Session()

        result_response = None
        last_error = None

        for retry_index in range(3):

            try:
                result_response = session.get(
                    result_url,
                    timeout=15,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 "
                            "(Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 "
                            "(KHTML, like Gecko) "
                            "Chrome/151 Safari/537.36"
                        ),
                        "Referer": url,
                    },
                )

                # 一時的な混雑・更新待ちなら少し待って再取得
                if result_response.status_code in [
                    429,
                    500,
                    502,
                    503,
                    504,
                ]:
                    import time
                    time.sleep(
                        1.5 + retry_index
                    )
                    continue

                result_response.raise_for_status()
                break

            except requests.RequestException as e:
                last_error = e

                if retry_index < 2:
                    import time
                    time.sleep(
                        1.5 + retry_index
                    )

        if result_response is None:
            raise requests.RequestException(
                f"結果ページ取得失敗: {last_error}"
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

        top3 = result_data[
            "着順"
        ]

        wide_payouts = result_data[
            "ワイド払戻"
        ]

        trio_payouts = result_data[
            "三連複払戻"
        ]

        if len(top3) < 3:

            st.warning(
                "着順がまだ確定していないか、"
                "結果ページの着順を正常に読み取れませんでした。"
            )

        elif (
            not wide_payouts
            or not trio_payouts
        ):

            st.warning(
                "着順は取得できましたが、払戻欄がまだ反映途中か、"
                "払戻表記を正常に読み取れませんでした。"
            )

            st.info(
                "数秒後にもう一度 "
                "『結果を取得して回収率を計算』を押してください。"
            )

            if debug_mode:

                with st.expander(
                    "結果取得デバッグ",
                    expanded=False,
                ):

                    st.write(
                        f"結果URL：{result_url}"
                    )

                    st.write(
                        f"1〜3着：{top3}"
                    )

                    st.write(
                        "ワイド払戻："
                        f"{wide_payouts}"
                    )

                    st.write(
                        "三連複払戻："
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

            total_return = 0
            ticket_rows = []

            # --------------------------------------
            # 三連複2点
            # --------------------------------------
            for index, bet in enumerate(
                trio_bets,
                start=1,
            ):

                key = (
                    normalize_bet_numbers(
                        bet
                    )
                )

                payout = (
                    trio_payouts.get(
                        key,
                        0,
                    )
                )

                total_return += payout

                ticket_rows.append({
                    "券種": (
                        f"三連複{index}"
                    ),
                    "買い目": "-".join(
                        str(x)
                        for x in key
                    ),
                    "的中": payout > 0,
                    "払戻": payout,
                })

            # --------------------------------------
            # 通常ワイド（南関以外は1点、南関は従来どおり）
            # --------------------------------------
            for index, bet in enumerate(
                wide_bets,
                start=1,
            ):

                key = (
                    normalize_bet_numbers(
                        bet
                    )
                )

                payout = (
                    wide_payouts.get(
                        key,
                        0,
                    )
                )

                total_return += payout

                ticket_rows.append({
                    "券種": (
                        f"ワイド{index}"
                    ),
                    "買い目": "-".join(
                        str(x)
                        for x in key
                    ),
                    "的中": payout > 0,
                    "払戻": payout,
                })

            # --------------------------------------
            # 浮き輪ワイド
            # --------------------------------------
            for index, bet in enumerate(
                float_bets,
                start=1,
            ):

                key = (
                    normalize_bet_numbers(
                        bet
                    )
                )

                payout = (
                    wide_payouts.get(
                        key,
                        0,
                    )
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

            # 1点100円固定
            investment = (
                ticket_count
                * 100
            )

            profit = (
                total_return
                - investment
            )

            recovery_rate = (
                total_return
                / investment
                * 100
                if investment > 0
                else 0.0
            )

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


            # --------------------------------------
            # 📋 結果コピペ用
            #
            # 回収率まで計算できた時だけ表示。
            # st.code() 右上のコピーボタンから
            # そのままChatGPTやメモへ貼り付けられる。
            # --------------------------------------
            result_copy_lines = [
                f"{race_date} {baba_name}{race_no}R",
                f"軸：{popular_horse_num}番",
                f"軸タイプ：{kyakushoku_type}",
                "公式結果："
                f"{finish_order[0]}-"
                f"{finish_order[1]}-"
                f"{finish_order[2]}",
                "",
                "【検証結果】",
            ]

            for row in ticket_rows:

                mark = (
                    "的中"
                    if row["的中"]
                    else "ハズレ"
                )

                result_copy_lines.append(
                    f"{row['券種']}："
                    f"{row['買い目']} "
                    f"{mark} "
                    f"払戻{row['払戻']:,}円"
                )

            result_copy_lines.extend([
                "",
                f"投資：{investment:,}円",
                f"払戻：{total_return:,}円",
                f"収支：{profit:+,}円",
                f"回収率：{recovery_rate:.1f}%",
            ])

            st.markdown(
                "#### 📋 結果をコピー"
            )

            st.caption(
                "右上のコピーボタンを押すと、"
                "検証結果をそのまま貼り付けできます。"
            )

            st.code(
                "\n".join(
                    result_copy_lines
                ),
                language=None,
            )


            # ==================================================
            # 一括検証：このRの結果を保存して次Rへ
            # ==================================================
            if st.session_state.batch_mode:

                st.session_state.batch_results.append({
                    "R": int(race_no),
                    "状態": "完了",
                    "検証モード": st.session_state.batch_axis_mode,
                    "軸": int(popular_horse_num),
                    "軸タイプ": kyakushoku_type,
                    "元A": (
                        int(st.session_state.batch_original_a)
                        if st.session_state.batch_axis_mode == "backfill"
                        and st.session_state.batch_original_a is not None
                        else int(popular_horse_num)
                    ),
                    "元F": (
                        int(st.session_state.batch_original_f)
                        if st.session_state.batch_axis_mode == "backfill"
                        and st.session_state.batch_original_f is not None
                        else None
                    ),
                    "AF一致": (
                        bool(st.session_state.batch_af_match)
                        if st.session_state.batch_axis_mode == "backfill"
                        and st.session_state.batch_af_match is not None
                        else None
                    ),
                    "結果": "-".join(
                        str(x)
                        for x in finish_order
                    ),
                    "投資": int(investment),
                    "払戻": int(total_return),
                    "収支": int(profit),
                    "回収率": float(recovery_rate),
                    "三連複": [
                        "-".join(
                            str(x)
                            for x in normalize_bet_numbers(bet)
                        )
                        for bet in trio_bets
                    ],
                    "ワイド": [
                        "-".join(
                            str(x)
                            for x in normalize_bet_numbers(bet)
                        )
                        for bet in wide_bets
                    ],
                    "浮き輪": [
                        "-".join(
                            str(x)
                            for x in normalize_bet_numbers(bet)
                        )
                        for bet in float_bets
                    ],
                })

                # このRの後詰め2パス状態をクリア
                st.session_state.batch_axis_override_num = None
                st.session_state.batch_axis_override_race = None
                st.session_state.batch_original_a = None
                st.session_state.batch_original_f = None
                st.session_state.batch_af_match = None

                if (
                    st.session_state.batch_race_no
                    < st.session_state.batch_last_race
                ):

                    st.session_state.batch_race_no += 1
                    st.rerun()

                else:

                    st.session_state.batch_mode = False
                    st.session_state.batch_race_no = 1
                    st.rerun()

    except requests.RequestException as e:

        st.error(
            "公式結果ページの取得に失敗しました。"
        )

        if debug_mode:
            st.caption(
                f"エラー：{e}"
            )

        if st.session_state.batch_mode:

            st.session_state.batch_results.append({
                "R": int(race_no),
                "状態": "失敗",
                "理由": f"結果取得失敗: {e}",
                "投資": 0,
                "払戻": 0,
            })

            st.session_state.batch_axis_override_num = None
            st.session_state.batch_axis_override_race = None
            st.session_state.batch_original_a = None
            st.session_state.batch_original_f = None
            st.session_state.batch_af_match = None

            if (
                st.session_state.batch_race_no
                < st.session_state.batch_last_race
            ):
                st.session_state.batch_race_no += 1
            else:
                st.session_state.batch_mode = False
                st.session_state.batch_race_no = 1

            st.rerun()

    except Exception as e:

        st.error(
            "結果の解析中にエラーが発生しました。"
        )

        if debug_mode:
            st.caption(
                f"エラー：{e}"
            )

        if st.session_state.batch_mode:

            st.session_state.batch_results.append({
                "R": int(race_no),
                "状態": "失敗",
                "理由": f"解析失敗: {e}",
                "投資": 0,
                "払戻": 0,
            })

            st.session_state.batch_axis_override_num = None
            st.session_state.batch_axis_override_race = None
            st.session_state.batch_original_a = None
            st.session_state.batch_original_f = None
            st.session_state.batch_af_match = None

            if (
                st.session_state.batch_race_no
                < st.session_state.batch_last_race
            ):
                st.session_state.batch_race_no += 1
            else:
                st.session_state.batch_mode = False
                st.session_state.batch_race_no = 1

            st.rerun()


# ==================================================
# 🏇 全R一括検証
# 通常分析の最後に表示。
# 新馬戦時は上の早期終了ブロックから同じ共通UIを呼ぶ。
# ==================================================
render_batch_controls(
    st.session_state.get("race_url", url),
    "bottom",
)
