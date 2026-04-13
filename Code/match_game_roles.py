import pandas as pd
import re
import os

ROLE_TO_CAMP = {
    '狼人':   '狼',
    '平民':   '民',
    '预言家': '神',
    '女巫':   '神',
    '猎人':   '神',
    '白神':   '神',
    '混血儿': '未知',  
    '法官':   '法官',
}


def extract_vid_from_filename(csv_path):

    filename = os.path.basename(csv_path)
    match    = re.search(r'Game\d+_(.+)\.csv', filename)
    return match.group(1)


def get_role_config(game_csv_path, role_info_csv_path):


    vid = extract_vid_from_filename(game_csv_path)

    role_df  = pd.read_csv(role_info_csv_path)
    row_mask = role_df['VID'] == vid

    if not row_mask.any():
        raise ValueError(
            f"在 Role Info 表中找不到 VID='{vid}'\n"
            f"表中现有 VID：{role_df['VID'].tolist()}"
        )

    row     = role_df[row_mask].iloc[0]
    game_id = int(row['Game_ID'])

    ground_truth = {}
    for p in range(0, 13):
        col  = f'player_{p}'
        role = str(row[col]).strip()
        ground_truth[p] = role

    hybrid_target_id = int(row['player_13'])

    hybrid_id = None
    for p, role in ground_truth.items():
        if role == '混血儿':
            hybrid_id = p
            break

    camp_truth = {}
    for p, role in ground_truth.items():
        if p == 0:
            continue
        camp_truth[p] = ROLE_TO_CAMP.get(role, '未知')

    if hybrid_id is not None:
        target_role = ground_truth.get(hybrid_target_id, '')
        target_camp = ROLE_TO_CAMP.get(target_role, '未知')
        if target_camp == '狼':
            camp_truth[hybrid_id] = '狼'
        else:
            camp_truth[hybrid_id] = '神'

    wolf_team = [
        p for p, camp in camp_truth.items()
        if camp == '狼'
    ]

    hybrid_target = {hybrid_id: hybrid_target_id} if hybrid_id else {}

    return {
        'game_id':       game_id,
        'vid':           vid,
        'ground_truth':  ground_truth,
        'camp_truth':    camp_truth,
        'wolf_team':     wolf_team,
        'hybrid_id':     hybrid_id,
        'hybrid_target': hybrid_target,
    }


def print_role_config(cfg):

    print(f"\nGame {cfg['game_id']}  (VID: {cfg['vid']})")
    print(f"{'─'*50}")


    gt = {p: r for p, r in cfg['ground_truth'].items() if p != 0}
    print("ground_truth =", {p: r for p, r in gt.items()})
    print("camp_truth   =", cfg['camp_truth'])
    print("wolf_team    =", cfg['wolf_team'])
    print("hybrid_target=", cfg['hybrid_target'])


    hid = cfg['hybrid_id']
    if hid:
        tid    = list(cfg['hybrid_target'].values())[0]
        t_role = cfg['ground_truth'].get(tid, '?')
        h_camp = cfg['camp_truth'].get(hid, '?')
        print(f"\n混血儿: {hid}号 | 榜样: {tid}号({t_role}) | 混血儿阵营: {h_camp}")

    print(f"\n狼人阵营: {cfg['wolf_team']}")
    good = [p for p, c in cfg['camp_truth'].items() if c in ['民', '神']]
    print(f"好人阵营: {good}")

