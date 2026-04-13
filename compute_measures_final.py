from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

import pandas as pd


# =============================================================================
# Constants
# =============================================================================

LAMBDA = 0.1

VERIFY_PATTERN = re.compile(r"验\d+[，,]?\s*(金水|银水|查杀)")
WOLF_MIX_PATTERN = re.compile(r"狼混|混子或狼|非狼即混")
CLAIM_PATTERN = re.compile(r"跳(预言家|女巫|猎人|白神|愚者|混子)")

POS_KW = [
    "金水", "银水", "好人", "像好人", "不像狼", "不是狼", "不像狼人",
    "还行", "还可以", "比较像预言家", "像预言家", "发言好", "像白神",
    r"比\d+号好", "认可度高", "好身份", r"站边\d+", r"站边\w+号",
    r"倾向于\d+号", "不一定是狼",
]
NEG_KW = [
    r"^狼$", r"^狼人$", "出局", "查杀", "像狼", r"^是狼$",
    "不像好人", "不太好", "不是平民", "悍跳", "诈身份", "装狼混", "炸身份",
    "不像预言家", "排除预言家", "做不了预言家", "有爆点", "发言有问题",
    r"\w+的同伴", "同身份", "身份或狼", "怀疑", "紧张", "不简单", "太简短",
    "不是好人", "不好", "奇怪", "不一定是好人", "不排水", "不能完全排水",
    "看放不放手", r"投\d+", r"毒\d+", "毒十", r"自刀\w*", r"^认狼$",
]
NEU_KW = [
    r"警徽流\d*", r"^听发言$", r"^像混子$", r"^混子$",
    r"^有可能混子$", r"^跳\w+$", r"^关注$", r"^\w*愚者\w*$",
]


# =============================================================================
# Step 1: extract private information from timeline
# =============================================================================

def extract_private_info(timeline: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Any]:

    ground_truth = cfg["ground_truth"]
    true_seer = next((p for p, r in ground_truth.items() if r == "预言家"), None)
    true_witch = next((p for p, r in ground_truth.items() if r == "女巫"), None)

    info = {
        "seer_checks": {},
        "witch_saved": None,
        "witch_poisoned": {},
        "knife_targets": {},
        "hybrid_mix": {},
        "night_deaths": {},
    }

    for ev in timeline:
        if ev["event"] == "night_actions":
            night = ev["night"]
            for a in ev["actions"]:
                actor = a["actor"]
                action = a["action"]

                if action == "seer_check" and actor == true_seer:
                    if a.get("target") and a.get("result"):
                        info["seer_checks"][a["target"]] = a["result"]

                elif action == "save" and actor == true_witch:
                    info["witch_saved"] = a.get("target")

                elif action == "poison" and actor == true_witch:
                    info["witch_poisoned"][night] = a.get("target")

                elif action == "knife":
                    info["knife_targets"].setdefault(night, [])
                    info["knife_targets"][night].append(a["target"])

                elif action == "hybrid_mix":
                    info["hybrid_mix"][night] = {
                        "actor": actor,
                        "target": a.get("target"),
                        "result": a.get("result"),
                    }

        elif ev["event"] == "night_deaths":
            info["night_deaths"][ev["night"]] = ev.get("deaths", [])

    return info


# =============================================================================
# Step 2: build turns from subtitle rows
# =============================================================================

def build_turns(df: pd.DataFrame, player_cols: List[str]) -> List[Dict[str, Any]]:

    speech = df[(df["发言玩家"].notna()) & (df["发言玩家"] != 0)].copy()
    speech["_row"] = speech.index

    turns: Dict[int, Dict[str, Any]] = {}
    for _, row in speech.iterrows():
        t = int(row["发言轮次"])
        sp = int(row["发言玩家"])
        rid = int(row["_row"])

        if t not in turns:
            turns[t] = {
                "turn": t,
                "speaker": sp,
                "row_min": rid,
                "row_max": rid,
                "stances": {},
                "text_parts": [],
            }
        else:
            turns[t]["row_min"] = min(turns[t]["row_min"], rid)
            turns[t]["row_max"] = max(turns[t]["row_max"], rid)

        txt = str(row.get("text", "")).strip()
        if txt and txt.lower() != "nan":
            turns[t]["text_parts"].append(txt)

        for col in player_cols:
            if pd.notna(row.get(col)):
                target = int(col.replace("player ", ""))
                label = str(row[col]).strip().replace("'", "")
                if label and label.lower() != "nan":
                    turns[t]["stances"].setdefault(target, []).append(label)

    ordered = sorted(turns.values(), key=lambda x: x["row_min"])
    for item in ordered:
        item["uid"] = f"{item['speaker']}_{item['turn']}"
        item["text"] = " ".join(item["text_parts"]).strip()
        del item["text_parts"]
    return ordered


# =============================================================================
# Step 3: snapshot before current turn
# =============================================================================

def get_snapshot(turn_idx: int, turns: List[Dict[str, Any]], timeline: List[Dict[str, Any]]) -> Dict[str, Any]:

    cur_row = turns[turn_idx]["row_min"]
    past_t = turns[:turn_idx]
    past_ev = [ev for ev in timeline if ev["row_index"] < cur_row]

    dead = set()
    revealed_roles = {}   

    for ev in past_ev:
        event_type = ev["event"]

        if event_type == "night_deaths":
            dead.update(ev.get("deaths", []))

        elif event_type == "banishment_result":
            dead.update(ev.get("exiled", []) or [])

        elif event_type == "explosion":
            player = ev.get("player")
            if player:
                dead.add(player)

                revealed_roles[player] = "狼人"


        elif event_type == "flip_reveal":
            player = ev.get("player")
            role = ev.get("role")
            if player and role:
                revealed_roles[player] = role

        elif event_type == "hunter_shot":
            shooter = ev.get("player") or ev.get("shooter")
            if shooter:
                revealed_roles[shooter] = "猎人"

        elif event_type == "white_god_reveal":
            player = ev.get("player")
            if player:
                revealed_roles[player] = "白神"

        elif event_type == "role_reveal":
            player = ev.get("player")
            role = ev.get("role")
            if player and role:
                revealed_roles[player] = role

    alive = set(range(1, 13)) - dead

    role_claims = defaultdict(set)
    for pt in past_t:
        for _, labels in pt["stances"].items():
            for lb in labels:
                m = CLAIM_PATTERN.search(lb)
                if m:
                    role_claims[m.group(1)].add(pt["speaker"])

    return {
        "past_turns": past_t,
        "past_events": past_ev,
        "dead": dead,
        "alive": alive,
        "role_claims": {k: sorted(v) for k, v in role_claims.items()},
        "revealed_roles": revealed_roles,
    }
# =============================================================================
# Step 4: stance helpers
# =============================================================================

import re
import math
from typing import List, Dict, Any

STRONG_POS_KW = [
    r"金水", r"银水", r"好身份", r"像白神",
    r"比\d+号好", r"认可度高",
    r"站边\d+", r"站边\w+号", r"倾向于\d+号",
]

WEAK_POS_KW = [
    r"好人", r"像好人", r"不像狼", r"不是狼", r"不像狼人",
    r"还行", r"还可以", r"比较像预言家", r"像预言家",
    r"发言好", r"不一定是狼",
]

STRONG_NEG_KW = [
    r"^狼$", r"^狼人$", r"^是狼$", r"^认狼$",
    r"查杀", r"出局", r"悍跳", r"诈身份", r"炸身份",
    r"装狼混", r"\w+的同伴", r"同身份", r"身份或狼",
    r"投\d+", r"毒\d+", r"毒十", r"自刀\w*",
]

WEAK_NEG_KW = [
    r"像狼", r"不像好人", r"不太好", r"不是平民",
    r"不像预言家", r"排除预言家", r"做不了预言家",
    r"有爆点", r"发言有问题", r"怀疑", r"紧张",
    r"不简单", r"太简短", r"不是好人", r"不好",
    r"奇怪", r"不一定是好人", r"不排水",
    r"不能完全排水", r"看放不放手",
]

NEU_KW = [
    r"警徽流\d*", r"^听发言$", r"^像混子$", r"^混子$",
    r"^有可能混子$", r"^跳\w+$", r"^关注$", r"^\w*愚者\w*$",
]


def ldir(label: str) -> float:
    l = label.strip().replace("'", "")

    m = VERIFY_PATTERN.search(l)
    if m:
        return 1.0 if m.group(1) in ("金水", "银水") else -1.0

    if WOLF_MIX_PATTERN.search(l):
        return -0.8

    for p in NEU_KW:
        if re.search(p, l):
            return 0.0

    for p in STRONG_POS_KW:
        if re.search(p, l):
            return 1.0

    for p in WEAK_POS_KW:
        if re.search(p, l):
            return 0.5

    for p in STRONG_NEG_KW:
        if re.search(p, l):
            return -1.0

    for p in WEAK_NEG_KW:
        if re.search(p, l):
            return -0.5

    return 0.0


def tscore(labels: List[str]) -> float:
    if not labels:
        return 0.0

    vals = [ldir(l) for l in labels]
    return sum(vals) / len(vals)


def disc(t_ev: int, t_now: int) -> float:
    return math.exp(-LAMBDA * max(0, t_now - t_ev))


def stance_vals(target: int, past_turns: List[Dict[str, Any]], t_now: int) -> List[float]:
    return [
        tscore(pt["stances"][target]) * disc(pt["turn"], t_now)
        for pt in past_turns
        if target in pt["stances"] and pt["speaker"] != target
    ]

# =============================================================================
# Step 5: core measures
# =============================================================================

def m_role_ambiguity(snap: Dict[str, Any], t: int) -> float:

    unique = {"预言家", "女巫", "猎人", "白神"}


    conf = sum(
        max(0, len(v) - 1)
        for k, v in snap["role_claims"].items()
        if k in unique
    )

    revealed_count = len(snap.get("revealed_roles", {}))
    rev_public = revealed_count / 12.0

    return round((conf + (1 - rev_public)) * (1 - 0.5 * rev_public), 4)

def m_public_conflict(snap: Dict[str, Any], t: int) -> float:

    alive = snap["alive"]
    mads = []
    for p in alive:
        vs = stance_vals(p, snap["past_turns"], t)
        if len(vs) < 2:
            continue
        mu = sum(vs) / len(vs)
        mad = sum(abs(v - mu) for v in vs) / len(vs)
        mads.append(mad)
    return round(sum(mads) / len(mads), 4) if mads else 0.0


def m_self_pressure(speaker: int, snap: Dict[str, Any], t: int) -> float:

    return round(sum(
        abs(tscore(pt["stances"][speaker])) * disc(pt["turn"], t)
        for pt in snap["past_turns"]
        if pt["speaker"] != speaker
        and speaker in pt["stances"]
        and tscore(pt["stances"][speaker]) < 0
    ), 4)


def _speaker_claim_history(speaker: int, snap: Dict[str, Any]) -> Dict[str, Any]:
    claims = {
        "role_claims": set(),
        "verify_claims": {},
        "silver_claims": set(),
        "poison_claims": set(),
    }

    for pt in snap["past_turns"]:
        if pt["speaker"] != speaker:
            continue
        for target, labels in pt["stances"].items():
            for lb in labels:
                m_role = CLAIM_PATTERN.search(lb)
                if m_role:
                    claims["role_claims"].add(m_role.group(1))

                m_verify = VERIFY_PATTERN.search(lb)
                if m_verify:
                    claims["verify_claims"][target] = m_verify.group(1)

                if "银水" in lb:
                    claims["silver_claims"].add(target)
                if re.search(r"毒\d+|毒十", lb):
                    claims["poison_claims"].add(target)

    return claims


def _wolf_private_public(speaker: int, snap: Dict[str, Any], cfg: Dict[str, Any], t: int) -> float:
    score = 0.0
    teammates = [p for p in cfg["wolf_team"] if p != speaker]

    for pt in snap["past_turns"]:
        if pt["speaker"] == speaker:
            continue
        for tgt, lbls in pt["stances"].items():
            d = tscore(lbls)
            w = disc(pt["turn"], t)

            if tgt in teammates:
                if d < 0:
                    score += abs(d) * w
                elif d > 0:
                    score += 0.3 * abs(d) * w

    return score


def _seer_private_public(speaker: int, snap: Dict[str, Any], priv: Dict[str, Any], t: int) -> float:

    score = 0.0
    print(snap["role_claims"])

    for tgt, res in priv["seer_checks"].items():
        good = res in ("金水", "银水")
        for pt in snap["past_turns"]:
            if pt["speaker"] == speaker or tgt not in pt["stances"]:
                continue
            d = tscore(pt["stances"][tgt])
            w = disc(pt["turn"], t)

            if good and d < 0:
                score += abs(d) * w
            elif (not good) and d > 0:
                score += abs(d) * w


    seer_claimants = snap["role_claims"].get("预言家", [])
    other_claimants = [p for p in seer_claimants if p != speaker]


    score += 1.0 * len(other_claimants)

    for pt in snap["past_turns"]:
        if pt["speaker"] not in other_claimants:
            continue

        for tgt, labels in pt["stances"].items():
            for lb in labels:
                m_verify = VERIFY_PATTERN.search(lb)
                if not m_verify:
                    continue

                claimed_res = m_verify.group(1)
                true_res = priv["seer_checks"].get(tgt)
                w = disc(pt["turn"], t)

                if true_res is not None:
                    if claimed_res != true_res:
                        score += 1.5 * w
                    else:

                        score += 0.5 * w
                else:

                    score += 0.6 * w

    return score


def _witch_private_public(speaker: int, snap: Dict[str, Any], priv: Dict[str, Any], t: int) -> float:

    score = 0.0

    saved = priv.get("witch_saved")
    poisoned = None
    if priv.get("witch_poisoned"):
        latest_night = max(priv["witch_poisoned"].keys())
        poisoned = priv["witch_poisoned"].get(latest_night)

    for pt in snap["past_turns"]:
        if pt["speaker"] == speaker:
            continue
        w = disc(pt["turn"], t)

        if saved and saved in pt["stances"]:
            d = tscore(pt["stances"][saved])
            if d < 0:
                score += abs(d) * w

        if poisoned and poisoned in pt["stances"]:
            d = tscore(pt["stances"][poisoned])
            if d > 0:
                score += abs(d) * w

    witch_claimants = snap["role_claims"].get("女巫", [])
    other_claimants = [p for p in witch_claimants if p != speaker]
    score += 1.0 * len(other_claimants)

    for pt in snap["past_turns"]:
        if pt["speaker"] not in other_claimants:
            continue

        w = disc(pt["turn"], t)

        for tgt, labels in pt["stances"].items():
            for lb in labels:

                if "银水" in lb:
                    if saved is not None:
                        if tgt != saved:
                            score += 1.5 * w
                        else:

                            score += 0.5 * w
                    else:

                        score += 1.0 * w


                if re.search(r"毒\d+|毒十", lb):
                    if poisoned is not None:
                        if tgt != poisoned:
                            score += 1.5 * w
                        else:
                            score += 0.5 * w
                    else:

                        score += 1.0 * w

    return score


def _hybrid_private_public(speaker: int, snap: Dict[str, Any], cfg: Dict[str, Any], t: int) -> float:

    tgt = cfg.get("hybrid_target", {}).get(speaker)
    if not tgt:
        return 0.0

    vs = stance_vals(tgt, snap["past_turns"], t)
    if vs:
        mu = sum(vs) / len(vs)
        disagreement = sum(abs(v - mu) for v in vs) / len(vs)
    else:
        disagreement = 0.0

    target_risk = 0.0
    for pt in snap["past_turns"]:
        if pt["speaker"] == speaker:
            continue
        if tgt in pt["stances"]:
            d = tscore(pt["stances"][tgt])
            w = disc(pt["turn"], t)
            if d < 0:
                target_risk += abs(d) * w


    hybrid_claimants = snap["role_claims"].get("混血儿", [])
    other_claimants = [p for p in hybrid_claimants if p != speaker]
    claim_pressure = 1.0 * len(other_claimants)


    return 0.5 * disagreement + 0.3 * target_risk + 0.2 * claim_pressure

def _commitment_maintenance(speaker: int, role: str, snap: Dict[str, Any], priv: Dict[str, Any], t: int) -> float:
    claims = _speaker_claim_history(speaker, snap)
    maint = 0.0

    for k, v in snap["role_claims"].items():
        if k in {"预言家", "女巫", "猎人", "白神"} and len(v) > 1:
            if k in claims["role_claims"]:
                maint += 0.8 * (len(v) - 1)

    if role == "预言家":
        for tgt, claimed_res in claims["verify_claims"].items():
            true_res = priv["seer_checks"].get(tgt)
            if true_res and claimed_res != true_res:
                maint += 2.0
                maint += sum(
                    0.5 * disc(pt["turn"], t)
                    for pt in snap["past_turns"]
                    if pt["speaker"] != speaker and tgt in pt["stances"]
                )

    if role == "女巫":
        saved = priv["witch_saved"]
        poisoned = None
        if priv["witch_poisoned"]:
            latest_night = max(priv["witch_poisoned"].keys())
            poisoned = priv["witch_poisoned"].get(latest_night)

        for tgt in claims["silver_claims"]:
            if saved is not None and tgt != saved:
                maint += 1.5
        for tgt in claims["poison_claims"]:
            if poisoned is not None and tgt != poisoned:
                maint += 1.5

    return maint


def m_L_consistency(speaker: int, snap: Dict[str, Any], cfg: Dict[str, Any], priv: Dict[str, Any], t: int) -> float:

    role = cfg["ground_truth"].get(speaker, "")

    private_public = 0.0
    if role == "狼人":
        private_public = _wolf_private_public(speaker, snap, cfg, t)
    elif role == "预言家":
        private_public = _seer_private_public(speaker, snap, priv, t)
    elif role == "女巫":
        private_public = _witch_private_public(speaker, snap, priv, t)
    elif role == "混血儿":
        private_public = _hybrid_private_public(speaker, snap, cfg, t)

    maintenance = _commitment_maintenance(speaker, role, snap, priv, t)
    return round(private_public + maintenance, 4)


def _print_header(cfg: Dict[str, Any]) -> None:
    gt = cfg["ground_truth"]
    wt = set(cfg["wolf_team"])
    print("=" * 60)
    print("本局游戏身份（上帝视角）")
    print("=" * 60)
    for p in range(1, 13):
        role = gt.get(p, "?")
        camp = cfg["camp_truth"].get(p, "?")
        tag = "★" if p in wt else " "
        print(f"  {tag} {p:2d}号  {role:<5}  ({camp}营)")
    hid = cfg.get("hybrid_id")
    if hid:
        tid = list(cfg["hybrid_target"].values())[0]
        print(f"\n  混血儿: {hid}号，榜样: {tid}号({gt.get(tid,'')})")
    print()


def _fmt_actions(ev: Dict[str, Any], cfg: Dict[str, Any]) -> List[str]:
    gt = cfg["ground_truth"]
    lines = []
    for a in ev["actions"]:
        act = a["action"]
        actor = a["actor"]
        role = gt.get(actor, "?")

        if act == "seer_check":
            tgt = a["target"]
            res = a.get("result", "?")
            lines.append(f"    {actor}号({role}) 验 {tgt}号({gt.get(tgt,'?')}) → {res}")
        elif act == "save":
            tgt = a.get("target")
            lines.append(f"    {actor}号({role}) 救 {tgt}号({gt.get(tgt,'?')})")
        elif act == "poison":
            tgt = a.get("target")
            lines.append(f"    {actor}号({role}) 毒 {tgt}号({gt.get(tgt,'?')})")
        elif act == "knife":
            tgt = a.get("target")
            lines.append(f"    {actor}号({role}) 刀 {tgt}号({gt.get(tgt,'?')})")
        elif act == "hybrid_mix":
            tgt = a.get("target")
            res = a.get("result", "?")
            lines.append(f"    {actor}号({role}) 混 {tgt}号({gt.get(tgt,'?')}) → {res}")
        elif act == "first_knife":
            lines.append(f"    {actor}号({role}) 首刀目标")
        elif act in ("take_knife", "take_poison"):
            lines.append(f"    {actor}号({role}) {act}")

    return lines


# =============================================================================
# Main run function
# =============================================================================

def run(
    df: pd.DataFrame,
    cfg: Dict[str, Any],
    timeline: List[Dict[str, Any]],
    player_cols: Optional[List[str]] = None,
    output_csv: Optional[str] = None,
    verbose: bool = True,
) -> pd.DataFrame:

    if player_cols is None:
        player_cols = [f"player {i}" for i in range(1, 13)]

    priv = extract_private_info(timeline, cfg)
    turns = build_turns(df, player_cols)
    gt = cfg["ground_truth"]

    ev_items = [{'_type': 'event', '_row': ev['row_index'], **ev} for ev in timeline]
    sp_items = [{'_type': 'speech', '_row': t['row_min'], '_turn_idx': idx, **t}
                for idx, t in enumerate(turns)]
    all_items = sorted(ev_items + sp_items, key=lambda x: x["_row"])

    rows = []

    if verbose:
        _print_header(cfg)

    for item in all_items:

        if item["_type"] == "event":
            et = item["event"]

            if et == "night_start" and verbose:
                print(f"\n{'─'*60}")
                print(f"【第 {item['night']} 夜】")

            elif et == "night_actions" and verbose:
                print("  夜间行动：")
                for line in _fmt_actions(item, cfg):
                    print(line)

            elif et == "night_end" and verbose:
                print("  天亮")

            elif et == "sheriff_register" and verbose:
                print(f"\n  上警环节  玩家: {item['registered']}")

            elif et == "sheriff_remaining" and verbose:
                print(f"  仍留警上: {item['remaining']}")

            elif et == "sheriff_vote" and verbose:
                vs = "  ".join(f"{v}→{c}" for v, c in item["votes"].items())
                print(f"  警徽投票: {vs}")

            elif et == "sheriff_elected" and verbose:
                sh = item["sheriff"]
                print(f"  警长归属: {sh}号({gt.get(sh,'?')}) ★")

            elif et == "banishment_vote" and verbose:
                vs = "  ".join(f"{v}→{c}" for v, c in item["votes"].items())
                print(f"\n  投票环节: {vs}")

            elif et == "banishment_result" and verbose:
                for p in (item.get("exiled") or []):
                    print(f"  出局: {p}号({gt.get(p,'?')})")

            elif et == "explosion" and verbose:
                p = item["player"]
                print(f"\n  自爆: {p}号({gt.get(p,'?')})")

            elif et == "night_deaths" and verbose:
                for p in (item.get("deaths") or []):
                    print(f"  死亡: {p}号({gt.get(p,'?')})")

            elif et == "badge_transfer" and verbose:
                print(f"  警徽移交: {item['from']}号 → {item['to']}号")

        else:
            idx = item["_turn_idx"]
            ti = item
            sp = ti["speaker"]
            t = ti["turn"]
            role = gt.get(sp, "?")
            camp = cfg["camp_truth"].get(sp, "?")
            snap = get_snapshot(idx, turns, timeline)

            L_cons = m_L_consistency(sp, snap, cfg, priv, t)
            pressure = m_self_pressure(sp, snap, t)
            role_amb = m_role_ambiguity(snap, t)
            pub_conf = m_public_conflict(snap, t)

            if verbose:
                print(
                    f"\n  玩家{sp:2d}号（{role}/{camp}）"
                    f"  [L_cons={L_cons:.2f}  pressure={pressure:.2f}  "
                    f"role_amb={role_amb:.2f}  pub_conf={pub_conf:.2f}]"
                )
                print(
                    f"    core: L_cons={L_cons:.2f}  "
                    f"pressure={pressure:.2f}  "
                    f"role_amb={role_amb:.2f}  "
                    f"pub_conf={pub_conf:.2f}"
                )

            rows.append({
                "uid": ti["uid"],
                "turn": t,
                "speaker": sp,
                "role": role,
                "camp": camp,
                "row_min": ti["row_min"],
                "row_max": ti["row_max"],
                "text": ti["text"],
                "L_consistency": L_cons,
                "self_pressure": pressure,
                "role_ambiguity": role_amb,
                "public_conflict": pub_conf,
            })

    if verbose:
        print(f"\n{'='*60}")
        print("游戏结束")
        print(f"{'='*60}")

    result = pd.DataFrame(rows)

    if output_csv:
        result.to_csv(output_csv, index=False,encoding="utf-8-sig")
        print(f"\n保存至: {output_csv}")

    return result
