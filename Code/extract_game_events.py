import pandas as pd
import re


HAN_DIGIT = {
    '一':1,'二':2,'三':3,'四':4,'五':5,
    '六':6,'七':7,'八':8,'九':9,'十':10,
    '十一':11,'十二':12,
}

def han_to_int(s):

    m = re.search(r'\d+', s)
    if m:
        return int(m.group())
    for han, val in sorted(HAN_DIGIT.items(), key=lambda x: -len(x[0])):
        if han in s:
            return val
    return None

def parse_cell(actor_id, cell_text):

    s = str(cell_text).strip()


    if re.match(r'验[\d一二三四五六七八九十]+[，,](金水|查杀)', s):
        return [_parse_single(actor_id, s)]


    if re.match(r'混[\d一二三四五六七八九十]+[，,](好人混|狼混)', s):
        return [_parse_single(actor_id, s)]


    parts = re.split(r'[，,、]', s)
    results = []
    for part in parts:
        part = part.strip()
        if part:
            results.append(_parse_single(actor_id, part))
    return results


def _parse_single(actor_id, s):



    m = re.search(r'验(\d+)[，,、\s]*(金水|查杀)', s)
    if m:
        return {'action':'seer_check','actor':actor_id,
                'target':int(m.group(1)),'result':m.group(2)}
    m = re.search(r'验(\d+)', s)
    if m:
        return {'action':'seer_check','actor':actor_id,
                'target':int(m.group(1)),'result':None}


    m = re.search(r'混(\d+)[，,、\s]*(好人混|狼混)?', s)
    if m:
        return {'action':'hybrid_mix','actor':actor_id,
                'target':int(m.group(1)),
                'result':m.group(2) if m.group(2) else None}
    if s.startswith('混'):
        target = han_to_int(s[1:])
        result = '好人混' if '好人混' in s else ('狼混' if '狼混' in s else None)
        return {'action':'hybrid_mix','actor':actor_id,
                'target':target,'result':result}


    m = re.search(r'[救就](\d+)', s)
    if m:
        return {'action':'save','actor':actor_id,'target':int(m.group(1))}
    if s in ('救','就'):
        return {'action':'save','actor':actor_id,'target':None}


    m = re.search(r'毒(\d+)', s)
    if m:
        return {'action':'poison','actor':actor_id,'target':int(m.group(1))}


    m = re.search(r'刀(\d+)', s)
    if m:
        return {'action':'knife','actor':actor_id,'target':int(m.group(1))}


    if '首刀' in s:
        return {'action':'first_knife','actor':actor_id}
    if '自刀' in s:
        return {'action':'self_knife','actor':actor_id}
    if '吃刀' in s or ('被' in s and '刀' in s):
        return {'action':'take_knife','actor':actor_id}
    if '吃毒' in s or '被毒' in s:
        return {'action':'take_poison','actor':actor_id}
    if '可开枪' in s:
        return {'action':'hunter_ready','actor':actor_id}
    if '开枪' in s:
        return {'action':'hunter_shoot','actor':actor_id}

    return {'action':'unknown','actor':actor_id,'raw':s}


def extract_game_events(df, player_cols=None):

    if player_cols is None:
        player_cols = [f'player {i}' for i in range(1, 13)]

    timeline      = []
    judge_rows    = df[df['发言玩家'] == 0]
    in_night      = False
    night_num     = 0
    current_night = None

    def get_vals(row):
        return {
            int(col.replace('player ', '')): str(row[col]).strip()
            for col in player_cols if pd.notna(row.get(col))
        }

    def get_marked(row):
        return [
            int(col.replace('player ', ''))
            for col in player_cols
            if pd.notna(row.get(col)) and str(row[col]).strip() == '1'
        ]

    for row_idx, row in judge_rows.iterrows():
        text = str(row.get('text', '')).strip()
        vals = get_vals(row)

        if re.match(r'第[一二三四五六七八九十\d]+夜$', text):
            night_num += 1
            in_night = True
            current_night = {'night': night_num, 'row_index': row_idx}
            timeline.append({
                'row_index': row_idx,
                'event':     'night_start',
                'night':     night_num,
            })
            continue

        if re.match(r'第[一二三四五六七八九十\d]+夜信息结束$', text):
            timeline.append({
                'row_index': row_idx,
                'event':     'night_end',
                'night':     night_num,
            })
            in_night = False
            current_night = None
            continue

        if in_night and '混人、刀人' in text:
            actions = []
            for pid, cell_text in vals.items():
                actions.extend(parse_cell(pid, cell_text))
            timeline.append({
                'row_index': row_idx,
                'event':     'night_actions',
                'night':     night_num,
                'raw':       vals,
                'actions':   actions,
            })
            continue

        if text == '死亡信息': #in_night and 
            #print('-------Find death info ----')
            deaths = [
                pid for pid, v in vals.items()
                if v in ('1', '死亡') or '死亡' in v
            ]
            timeline.append({
                'row_index': row_idx,
                'event':     'night_deaths',
                'night':     night_num,
                'deaths':    deaths,
            })
            continue

        if text in ('上警信息', '上警环节'):
            #print('------上警信息------')
            timeline.append({
                'row_index':  row_idx,
                'event':      'sheriff_register',
                'registered': get_marked(row),
            })
            continue

        if text == '仍留警上玩家':
            timeline.append({
                'row_index': row_idx,
                'event':     'sheriff_remaining',
                'remaining': get_marked(row),
            })
            continue

        if '警徽投票' in text or '二轮警徽投票' in text:
            votes = {}
            for voter, candidate in vals.items():
                try:
                    votes[voter] = int(candidate)
                except ValueError:
                    pass
            timeline.append({
                'row_index': row_idx,
                'event':     'sheriff_vote',
                'round':     text,
                'votes':     votes,
            })
            continue

        if text in ('警长归属', '警长'):
            marked = get_marked(row)
            if marked:
                timeline.append({
                    'row_index': row_idx,
                    'event':     'sheriff_elected',
                    'sheriff':   marked[0],
                })
            continue

        if '放逐投票' in text or '321请出票' in text or '投票环节' in text:
            votes = {}
            for voter, candidate in vals.items():
                try:
                    votes[voter] = int(candidate)
                except ValueError:
                    pass
            if votes:  # 排除纯标题行
                timeline.append({
                    'row_index': row_idx,
                    'event':     'banishment_vote',
                    'votes':     votes,
                })
            continue

        if text in ('放逐信息', '出局信息', '出局'):
            exiled = get_marked(row)
            if not exiled:
                exiled = [pid for pid, v in vals.items()
                          if '出局' in v or v == '1']
            timeline.append({
                'row_index': row_idx,
                'event':     'banishment_result',
                'exiled':    exiled,
            })
            continue

        if text == '自爆':
            exploded = get_marked(row)
            for p in exploded:
                timeline.append({
                    'row_index': row_idx,
                    'event':     'explosion',
                    'player':    p,
                })
            continue

        if text == '警徽移交':
            current_sheriff = None
            for ev in reversed(timeline):
                if ev['event'] == 'sheriff_elected':
                    current_sheriff = ev['sheriff']
                    break
                if ev['event'] == 'badge_transfer':
                    current_sheriff = ev['to']
                    break
            for p in get_marked(row):
                timeline.append({
                    'row_index': row_idx,
                    'event':     'badge_transfer',
                    'from':      current_sheriff,
                    'to':        p,
                })
            continue

    return timeline


# =============================================================================
# print
# =============================================================================

EVENT_LABELS = {
    'night_start':       '【第{night}夜 开始】',
    'night_actions':     '  夜间行动',
    'night_deaths':      '  夜间死亡',
    'night_end':         '【第{night}夜 结束】',
    'sheriff_register':  '【上警】',
    'sheriff_remaining': '【仍留警上】',
    'sheriff_vote':      '【警徽投票】',
    'sheriff_elected':   '【警长产生】',
    'banishment_vote':   '【放逐投票】',
    'banishment_result': '【放逐出局】',
    'explosion':         '【自爆】',
    'badge_transfer':    '【警徽移交】',
}

def print_game_events(timeline, label=''):
    print(f"\n{'='*55}")
    print(f"比赛事件时间线 {label}")
    print(f"{'='*55}")

    for ev in timeline:
        t    = ev['event']
        ridx = ev['row_index']

        if t == 'night_start':
            print(f"\n[行{ridx:4d}] 【第{ev['night']}夜 开始】")

        elif t == 'night_actions':
            print(f"[行{ridx:4d}]   夜间行动 →")
            for a in ev['actions']:
                print(f"           {a}")

        elif t == 'night_deaths':
            print(f"[行{ridx:4d}]   死亡公告 → {ev['deaths']}")

        elif t == 'night_end':
            print(f"[行{ridx:4d}] 【第{ev['night']}夜 结束】")

        elif t == 'sheriff_register':
            print(f"\n[行{ridx:4d}] 【上警】 → {ev['registered']}")

        elif t == 'sheriff_remaining':
            print(f"[行{ridx:4d}] 【仍留警上】 → {ev['remaining']}")

        elif t == 'sheriff_vote':
            print(f"[行{ridx:4d}] 【警徽投票】({ev['round']}) → {ev['votes']}")

        elif t == 'sheriff_elected':
            print(f"[行{ridx:4d}] 【警长产生】 → {ev['sheriff']}号")

        elif t == 'banishment_vote':
            print(f"\n[行{ridx:4d}] 【放逐投票】 → {ev['votes']}")

        elif t == 'banishment_result':
            print(f"[行{ridx:4d}] 【放逐出局】 → {ev['exiled']}")

        elif t == 'explosion':
            print(f"\n[行{ridx:4d}] 【自爆】 → {ev['player']}号")

        elif t == 'badge_transfer':
            print(f"[行{ridx:4d}] 【警徽移交】 → {ev['from']}号 → {ev['to']}号")



if __name__ == '__main__':
    player_cols = [f'player {i}' for i in range(1, 13)]

    for label, fpath in [
        ('Game4', 'E:\\GaTech\\Research Projects\\werewolf\\Data\\Game4_BV1ZGwAzZEny.csv'),
        #('Game3', 'E:\\GaTech\\Research Projects\\werewolf\\Data\\Game3_BV1juPwzfEj5.csv'),
    ]:
        df = pd.read_csv(fpath)
        events = extract_game_events(df, player_cols)
        print_game_events(events, label)
