from datetime import datetime
import time
import json
import requests
import numpy as np
import pandas as pd
import pickle
import copy
import trueskill
from time import sleep
from collections import OrderedDict
import itertools
import math
from catboost import CatBoostClassifier,cv, Pool
from sklearn.model_selection import train_test_split
from flask import Flask, jsonify, request, make_response, abort, render_template


class OpenDotaAPI():
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.last_match_id = 0

    def _call(self, url, parameters, tries=50, headers=None):
        for i in range(tries):
            try:
                if self.verbose: print("Sending API request... ", end="", flush=True)
                resp = requests.get(url, params=parameters, headers=headers, timeout=20)
                load_resp = json.loads(resp.text)
                if self.verbose: print("done")
                return load_resp
            except Exception as e:
                print("failed. Trying again in 5s")
                print(e)
                time.sleep(5)
        else:
            ValueError("Unable to connect to OpenDota API")

    def get_pro_matches_custom_sql(self, limit=100000):
        err = True
        url = "https://api.opendota.com/api/explorer?sql=select team_r.name radiant_team_name, team_d.name dire_team_name, team_r.tag radiant_team_tag, team_d.tag dire_team_tag, m.match_id, m.radiant_win, p.patch, m.start_time, m.leagueid, m.game_mode, m.radiant_team_id, m.dire_team_id, m.radiant_team_complete, m.dire_team_complete, m.radiant_captain, m.dire_captain, max(case when pm.rn = 1 then pm.account_id end) account_id_1, max(case when pm.rn = 2 then pm.account_id end) account_id_2, max(case when pm.rn = 3 then pm.account_id end) account_id_3, max(case when pm.rn = 4 then pm.account_id end) account_id_4, max(case when pm.rn = 5 then pm.account_id end) account_id_5, max(case when pm.rn = 6 then pm.account_id end) account_id_6, max(case when pm.rn = 7 then pm.account_id end) account_id_7, max(case when pm.rn = 8 then pm.account_id end) account_id_8, max(case when pm.rn = 9 then pm.account_id end) account_id_9, max(case when pm.rn = 10 then pm.account_id end) account_id_10 , max(case when pm.rn = 1 then pm.account_id end) account_id_1, max(case when pm.rn = 2 then pm.account_id end) account_id_2, max(case when pm.rn = 3 then pm.account_id end) account_id_3, max(case when pm.rn = 4 then pm.account_id end) account_id_4, max(case when pm.rn = 5 then pm.account_id end) account_id_5, max(case when pm.rn = 6 then pm.account_id end) account_id_6, max(case when pm.rn = 7 then pm.account_id end) account_id_7, max(case when pm.rn = 8 then pm.account_id end) account_id_8, max(case when pm.rn = 9 then pm.account_id end) account_id_9, max(case when pm.rn = 10 then pm.account_id end) account_id_10, max(case when pm.rn = 1 then pm.hero_id end) hero_id_1, max(case when pm.rn = 2 then pm.hero_id end) hero_id_2, max(case when pm.rn = 3 then pm.hero_id end) hero_id_3, max(case when pm.rn = 4 then pm.hero_id end) hero_id_4, max(case when pm.rn = 5 then pm.hero_id end) hero_id_5, max(case when pm.rn = 6 then pm.hero_id end) hero_id_6, max(case when pm.rn = 7 then pm.hero_id end) hero_id_7, max(case when pm.rn = 8 then pm.hero_id end) hero_id_8, max(case when pm.rn = 9 then pm.hero_id end) hero_id_9, max(case when pm.rn = 10 then pm.hero_id end) hero_id_10 from matches m inner join( select pm.*, row_number() over(partition by match_id order by player_slot) rn from player_matches pm) pm on pm.match_id = m.match_id join match_patch p on m.match_id=p.match_id join teams team_r on m.radiant_team_id=team_r.team_id join teams team_d on m.dire_team_id=team_d.team_id group by m.match_id,p.patch,team_r.name,team_d.name,team_r.tag,team_d.tag order by m.match_id desc"
        while err:
            resp = self._call(url, None, tries=2)
            if resp['err'] is None:
                err = False
                continue
            print(resp['err'])
        matches = resp['rows']
        return pd.DataFrame(matches, index=[match['match_id'] for match in matches])

    def get_pb_ids(self, match_id, limit=60000):
        err = True
        url = 'https://api.opendota.com/api/explorer?sql=select match_id from public_matches where avg_mmr > 5000 and match_id > {} and lobby_type = 7 order by match_id desc limit {}'.format(match_id, limit)

        while err:
            resp = self._call(url, None, tries=2)
            if resp['err'] is None:
                err = False
                continue
            print(resp['err'])
        return [x['match_id'] for x in resp['rows']]

    def get_pro_ids(self, match_id, limit=10000):
        err = True
        url = 'https://api.opendota.com/api/explorer?sql=select match_id, radiant_captain, dire_captain,radiant_team_id,dire_team_id  from matches where radiant_captain >0 and match_id > {} order by match_id desc limit {}'.format(match_id,limit)
        # url = "https://api.opendota.com/api/explorer?sql=select pp.*, pm.*,(pp.player_slot < 128) = pm.radiant_win win FROM public_player_matches pp join public_matches pm on pp.match_id=pm.match_id where pm.avg_mmr > 5000 and pm.lobby_type = 7 and pp.hero_id = {} and pp.match_id > {} order by pp.match_id limit 500".format(hero_id,match_id)
        while err:
            resp = self._call(url, None, tries=2)
            if resp['err'] is None:
                err = False
                continue
            print(resp['err'])
        return resp['rows']

    def get_public_matches_stratz(self, arr):
        err = True
        url = "https://api.stratz.com/api/v1/match?matchid={}&include=Team,Player".format(str(arr[:10])[1:-1])
        resp = self._call(url, None, headers={
            "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1laWQiOiJodHRwczovL3N0ZWFtY29tbXVuaXR5LmNvbS9vcGVuaWQvaWQvNzY1NjExOTgwMzMxODkxNDkiLCJ1bmlxdWVfbmFtZSI6Ik1lbGVvbiIsIlN1YmplY3QiOiIyZDVlMDI2Mi0wODI2LTQzMzItOWEzZi1kMzBlNWRiZmYyOTAiLCJTdGVhbUlkIjoiNzI5MjM0MjEiLCJuYmYiOjE1ODg0ODk3MTksImV4cCI6MTYyMDAyNTcxOSwiaWF0IjoxNTg4NDg5NzE5LCJpc3MiOiJodHRwczovL2FwaS5zdHJhdHouY29tIn0.5gaIgXxoJu3bPm_FGqcr8xfGUSsAHCiwysGQEEBxfL8"},
                          tries=10)
        return resp


# r = requests.get('', headers={"Bearer":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1laWQiOiJodHRwczovL3N0ZWFtY29tbXVuaXR5LmNvbS9vcGVuaWQvaWQvNzY1NjExOTgwMzMxODkxNDkiLCJ1bmlxdWVfbmFtZSI6Ik1lbGVvbiIsIlN1YmplY3QiOiIyZDVlMDI2Mi0wODI2LTQzMzItOWEzZi1kMzBlNWRiZmYyOTAiLCJTdGVhbUlkIjoiNzI5MjM0MjEiLCJuYmYiOjE1ODg0ODk3MTksImV4cCI6MTYyMDAyNTcxOSwiaWF0IjoxNTg4NDg5NzE5LCJpc3MiOiJodHRwczovL2FwaS5zdHJhdHouY29tIn0.5gaIgXxoJu3bPm_FGqcr8xfGUSsAHCiwysGQEEBxfL8"}), timeout= 20)

def get_id_by_name(name1):
    id1 = None
    name1 = name1.replace("-", "")
    name1 = name1.replace(" ", "")
    name1 = name1.replace(".", "")
    name1 = name1.lower().strip()
    for word in ['team', 'gaming', '!']:
        if word in name1:
            name1 = name1.replace(word, "")
    team_info_new = team_info.sort_values(by='last_match_time', ascending=False)
    if name1 == 'og':
        id1 = 2586976
    else:
        for row in team_info_new.iterrows():
            team_name = row[1]['name']
            team_name = team_name.replace("-", "")
            team_name = team_name.replace(".", "")
            team_name = team_name.replace(" ", "")
            team_name = team_name.lower().strip()
            for word in ['team', 'gaming', '!']:
                if word in team_name:
                    team_name = team_name.replace(word, "")
            team_tag = row[1]['tag']
            team_tag = team_tag.replace("-", "")
            team_tag = team_tag.replace(".", " ")
            team_tag = team_tag.lower().strip()
            # if row[1]['team_id'] ==7553952:
            #     print(name1)
            #     print(team_name )
            if (name1 == team_name) or (name1 == team_tag):
                id1 = row[1]['id']
                break
            else:
                if (len(team_name) != 0) and (name1 == team_name.split()[0]):
                    id1 = row[1]['id']
                    break

    return id1


env = trueskill.TrueSkill(draw_probability=0)
env.make_as_global()


def win_probability(team1, team2):
    delta_mu = sum(r.mu for r in team1) - sum(r.mu for r in team2)
    sum_sigma = sum(r.sigma ** 2 for r in itertools.chain(team1, team2))
    size = len(team1) + len(team2)
    denom = math.sqrt(size * (4.166666666666667 * 4.166666666666667) + sum_sigma)
    ts = trueskill.global_env()
    return ts.cdf(delta_mu / denom)


def get_player_stat(player_id, stat, version=None, hero_id=None):
    if player_id not in player_dict:
        player_dict[player_id] = {
            'wins': 1,
            'losses': 1,
            'rating': env.Rating(),
            'imp': 0,
            'p_wins': 1,
            'p_losses': 1,
            'heroes': {}
        }
    if 'hero' in stat:
        if version not in player_dict[player_id]['heroes']:
            player_dict[player_id]['heroes'][version] = {}
        if hero_id not in player_dict[player_id]['heroes'][version]:
            player_dict[player_id]['heroes'][version][hero_id] = {
                'player_hero_wins': 1,
                'player_hero_losses': 1,
                'player_hero_rating': env.Rating(),
                'player_hero_imp': 0
            }
        if stat == 'player_hero_games':
            return player_dict[player_id]['heroes'][version][hero_id]['player_hero_wins'] + \
                   player_dict[player_id]['heroes'][version][hero_id]['player_hero_losses']
        if stat == 'player_hero_imp':
            if player_dict[player_id]['heroes'][version][hero_id]['player_hero_imp'] == 0:
                return 100
            else:
                return player_dict[player_id]['heroes'][version][hero_id]['player_hero_imp']
        if stat == 'player_hero_rating':
            return player_dict[player_id]['heroes'][version][hero_id]['player_hero_rating'].mu
        return player_dict[player_id]['heroes'][version][hero_id][stat]

    if stat == 'p_games':
        return player_dict[player_id]['p_wins'] + player_dict[player_id]['p_losses']
    if stat == 'games':
        return player_dict[player_id]['wins'] + player_dict[player_id]['losses']
    if stat == 'imp':
        if player_dict[player_id][stat] == 0:
            return 100
        else:
            return player_dict[player_id]['imp']
    if stat == 'rating':
        return player_dict[player_id][stat].mu
    return player_dict[player_id][stat]


def get_hero_stat(hero_id, stat, version):
    if version not in global_heroes:
        global_heroes[version] = {}
    if hero_id not in global_heroes[version]:
        global_heroes[version][hero_id] = {
            'wins': 1,
            'losses': 1,
            'rating': env.Rating(),
        }

    if stat == 'games':
        return global_heroes[version][hero_id]['wins'] + global_heroes[version][hero_id]['losses']
    if stat == 'rating':
        return global_heroes[version][hero_id][stat].mu
    return global_heroes[version][hero_id][stat]


def get_team_stat(team_id, stat):
    if team_id not in team_dict:
        team_dict[team_id] = {
            'wins': 1,
            'losses': 1,
            'rating': env.Rating(),
            'elo_rating': 1000
        }
    if stat == 'rating':
        return team_dict[team_id][stat].mu
    return team_dict[team_id][stat]


def get_captain_stat(captain_id, stat):
    if captain_id not in captain_dict:
        captain_dict[captain_id] = {
            'wins': 1,
            'losses': 1
        }
    return captain_dict[captain_id][stat]


def update_captain_stat(radiant_id, dire_id, win):
    win = int(win)
    captain_dict[radiant_id]['wins'] += win
    captain_dict[radiant_id]['losses'] += (1 - win)
    captain_dict[dire_id]['wins'] += (1 - win)
    captain_dict[dire_id]['losses'] += win


def update_team_stat(match):
    player_ids = [player['steamAccountId'] for player in match['players']]
    win = int(match['didRadiantWin'])
    radiant_id = match['radiant_team_id']
    dire_id = match['dire_team_id']
    team_dict[radiant_id]['wins'] += win
    team_dict[radiant_id]['losses'] += (1 - win)
    team_dict[radiant_id]['name'] = match['radiantTeam']['name'] if (
                'radiantTeam' in match and 'name' in match['radiantTeam']) else '_'
    team_dict[radiant_id]['tag'] = match['radiantTeam']['tag'] if (
                'radiantTeam' in match and 'tag' in match['radiantTeam']) else '_'
    team_dict[radiant_id]['id'] = radiant_id
    team_dict[radiant_id]['last_match_time'] = match['startDateTime']
    team_dict[radiant_id]['captain'] = match['radiant_captain']
    team_dict[radiant_id]['player1'] = player_ids[0]
    team_dict[radiant_id]['player2'] = player_ids[1]
    team_dict[radiant_id]['player3'] = player_ids[2]
    team_dict[radiant_id]['player4'] = player_ids[3]
    team_dict[radiant_id]['player5'] = player_ids[4]

    team_dict[dire_id]['wins'] += (1 - win)
    team_dict[dire_id]['losses'] += win
    team_dict[dire_id]['name'] = match['direTeam']['name'] if (
                'direTeam' in match and 'name' in match['direTeam']) else '_'
    team_dict[dire_id]['tag'] = match['direTeam']['tag'] if (
                'direTeam' in match and 'tag' in match['direTeam']) else '_'
    team_dict[dire_id]['id'] = dire_id
    team_dict[dire_id]['last_match_time'] = match['startDateTime']
    team_dict[dire_id]['captain'] = match['dire_captain']
    team_dict[dire_id]['player1'] = player_ids[5]
    team_dict[dire_id]['player2'] = player_ids[6]
    team_dict[dire_id]['player3'] = player_ids[7]
    team_dict[dire_id]['player4'] = player_ids[8]
    team_dict[dire_id]['player5'] = player_ids[9]

    t1 = [team_dict[radiant_id]['rating']]
    t2 = [team_dict[dire_id]['rating']]
    new_r1, new_r2 = trueskill.rate([t1, t2], ranks=[1 - win, win])
    new_r1, new_r2 = new_r1[0], new_r2[0]
    team_dict[radiant_id]['rating'] = new_r1
    team_dict[dire_id]['rating'] = new_r2

    kFactor = 32
    currRating1 = team_dict[radiant_id]['elo_rating']
    currRating2 = team_dict[dire_id]['elo_rating']
    r1 = 10 ** (currRating1 / 400)
    r2 = 10 ** (currRating2 / 400)
    e1 = r1 / (r1 + r2)
    e2 = r2 / (r1 + r2)
    win1 = win
    win2 = 1 - win1
    ratingDiff1 = kFactor * (win1 - e1)
    ratingDiff2 = kFactor * (win2 - e2)
    team_dict[radiant_id]['elo_rating'] += ratingDiff1
    team_dict[dire_id]['elo_rating'] += ratingDiff2


def update_player_stat(player_ids, player_imps, win, isPro, version, heroes_ids):
    if isPro:
        imp = 'imp'
        wins = 'wins'
        losses = 'losses'
        rating = 'rating'
    else:
        wins = 'p_wins'
        losses = 'p_losses'
    win = int(win)
    for idx, player_id in enumerate(player_ids):
        if player_id not in player_dict:
            player_dict[player_id] = {
                'wins': 1,
                'losses': 1,
                'rating': env.Rating(),
                'imp': 0,
                'p_wins': 1,
                'p_losses': 1,
                'heroes': {}
            }
        hero_id = heroes_ids[idx]
        if version not in player_dict[player_id]['heroes']:
            player_dict[player_id]['heroes'][version] = {}
        if hero_id not in player_dict[player_id]['heroes'][version]:
            player_dict[player_id]['heroes'][version][hero_id] = {
                'player_hero_wins': 1,
                'player_hero_losses': 1,
                'player_hero_rating': env.Rating(),
                'player_hero_imp': 0
            }

        if idx < 5:
            player_dict[player_id][wins] += win
            player_dict[player_id][losses] += (1 - win)
            player_dict[player_id]['heroes'][version][hero_id]['player_hero_wins'] += win
            player_dict[player_id]['heroes'][version][hero_id]['player_hero_losses'] += (1 - win)
        else:
            player_dict[player_id][wins] += (1 - win)
            player_dict[player_id][losses] += win
            player_dict[player_id]['heroes'][version][hero_id]['player_hero_wins'] += (1 - win)
            player_dict[player_id]['heroes'][version][hero_id]['player_hero_losses'] += win
        if player_dict[player_id]['heroes'][version][hero_id]['player_hero_imp'] == 0:
            player_dict[player_id]['heroes'][version][hero_id]['player_hero_imp'] = 90 + 0.1 * player_imps[idx]
        else:
            player_dict[player_id]['heroes'][version][hero_id]['player_hero_imp'] = 0.9 * \
                                                                                    player_dict[player_id]['heroes'][
                                                                                        version][hero_id][
                                                                                        'player_hero_imp'] + 0.1 * \
                                                                                    player_imps[idx]
    r1 = player_dict[player_ids[0]]['heroes'][version][heroes_ids[0]]['player_hero_rating']
    r2 = player_dict[player_ids[1]]['heroes'][version][heroes_ids[1]]['player_hero_rating']
    r3 = player_dict[player_ids[2]]['heroes'][version][heroes_ids[2]]['player_hero_rating']
    r4 = player_dict[player_ids[3]]['heroes'][version][heroes_ids[3]]['player_hero_rating']
    r5 = player_dict[player_ids[4]]['heroes'][version][heroes_ids[4]]['player_hero_rating']
    r6 = player_dict[player_ids[5]]['heroes'][version][heroes_ids[5]]['player_hero_rating']
    r7 = player_dict[player_ids[6]]['heroes'][version][heroes_ids[6]]['player_hero_rating']
    r8 = player_dict[player_ids[7]]['heroes'][version][heroes_ids[7]]['player_hero_rating']
    r9 = player_dict[player_ids[8]]['heroes'][version][heroes_ids[8]]['player_hero_rating']
    r10 = player_dict[player_ids[9]]['heroes'][version][heroes_ids[9]]['player_hero_rating']
    t1 = [r1, r2, r3, r4, r5]
    t2 = [r6, r7, r8, r9, r10]
    new_r1, new_r2 = trueskill.rate([t1, t2], ranks=[1 - win, win])
    r1, r2, r3, r4, r5 = new_r1
    r6, r7, r8, r9, r10 = new_r2
    player_dict[player_ids[0]]['heroes'][version][heroes_ids[0]]['player_hero_rating'] = r1
    player_dict[player_ids[1]]['heroes'][version][heroes_ids[1]]['player_hero_rating'] = r2
    player_dict[player_ids[2]]['heroes'][version][heroes_ids[2]]['player_hero_rating'] = r3
    player_dict[player_ids[3]]['heroes'][version][heroes_ids[3]]['player_hero_rating'] = r4
    player_dict[player_ids[4]]['heroes'][version][heroes_ids[4]]['player_hero_rating'] = r5
    player_dict[player_ids[5]]['heroes'][version][heroes_ids[5]]['player_hero_rating'] = r6
    player_dict[player_ids[6]]['heroes'][version][heroes_ids[6]]['player_hero_rating'] = r7
    player_dict[player_ids[7]]['heroes'][version][heroes_ids[7]]['player_hero_rating'] = r8
    player_dict[player_ids[8]]['heroes'][version][heroes_ids[8]]['player_hero_rating'] = r9
    player_dict[player_ids[9]]['heroes'][version][heroes_ids[9]]['player_hero_rating'] = r10

    if isPro:
        if player_dict[player_id][imp] == 0:
            player_dict[player_id][imp] = 90 + 0.1 * player_imps[idx]
        else:
            player_dict[player_id][imp] = 0.9 * player_dict[player_id][imp] + 0.1 * player_imps[idx]
        r1 = player_dict[player_ids[0]][rating]
        r2 = player_dict[player_ids[1]][rating]
        r3 = player_dict[player_ids[2]][rating]
        r4 = player_dict[player_ids[3]][rating]
        r5 = player_dict[player_ids[4]][rating]
        r6 = player_dict[player_ids[5]][rating]
        r7 = player_dict[player_ids[6]][rating]
        r8 = player_dict[player_ids[7]][rating]
        r9 = player_dict[player_ids[8]][rating]
        r10 = player_dict[player_ids[9]][rating]
        t1 = [r1, r2, r3, r4, r5]
        t2 = [r6, r7, r8, r9, r10]
        new_r1, new_r2 = trueskill.rate([t1, t2], ranks=[1 - win, win])
        r1, r2, r3, r4, r5 = new_r1
        r6, r7, r8, r9, r10 = new_r2
        player_dict[player_ids[0]][rating] = r1
        player_dict[player_ids[1]][rating] = r2
        player_dict[player_ids[2]][rating] = r3
        player_dict[player_ids[3]][rating] = r4
        player_dict[player_ids[4]][rating] = r5
        player_dict[player_ids[5]][rating] = r6
        player_dict[player_ids[6]][rating] = r7
        player_dict[player_ids[7]][rating] = r8
        player_dict[player_ids[8]][rating] = r9
        player_dict[player_ids[9]][rating] = r10


def update_hero_stat(hero_ids, hero_imps, win, version):
    wins = 'wins'
    losses = 'losses'
    rating = 'rating'
    win = int(win)
    for idx, hero_id in enumerate(hero_ids):
        if version not in global_heroes:
            global_heroes[version] = {}
        if hero_id not in global_heroes[version]:
            global_heroes[version][hero_id] = {
                'wins': 1,
                'losses': 1,
                'rating': env.Rating(),
            }

        if idx < 5:
            global_heroes[version][hero_id][wins] += win
            global_heroes[version][hero_id][losses] += (1 - win)
        else:
            global_heroes[version][hero_id][wins] += (1 - win)
            global_heroes[version][hero_id][losses] += win
    r1 = global_heroes[version][hero_ids[0]][rating]
    r2 = global_heroes[version][hero_ids[1]][rating]
    r3 = global_heroes[version][hero_ids[2]][rating]
    r4 = global_heroes[version][hero_ids[3]][rating]
    r5 = global_heroes[version][hero_ids[4]][rating]
    r6 = global_heroes[version][hero_ids[5]][rating]
    r7 = global_heroes[version][hero_ids[6]][rating]
    r8 = global_heroes[version][hero_ids[7]][rating]
    r9 = global_heroes[version][hero_ids[8]][rating]
    r10 = global_heroes[version][hero_ids[9]][rating]
    t1 = [r1, r2, r3, r4, r5]
    t2 = [r6, r7, r8, r9, r10]
    new_r1, new_r2 = trueskill.rate([t1, t2], ranks=[1 - win, win])
    r1, r2, r3, r4, r5 = new_r1
    r6, r7, r8, r9, r10 = new_r2
    global_heroes[version][hero_ids[0]][rating] = r1
    global_heroes[version][hero_ids[1]][rating] = r2
    global_heroes[version][hero_ids[2]][rating] = r3
    global_heroes[version][hero_ids[3]][rating] = r4
    global_heroes[version][hero_ids[4]][rating] = r5
    global_heroes[version][hero_ids[5]][rating] = r6
    global_heroes[version][hero_ids[6]][rating] = r7
    global_heroes[version][hero_ids[7]][rating] = r8
    global_heroes[version][hero_ids[8]][rating] = r9
    global_heroes[version][hero_ids[9]][rating] = r10

def make_row(id1, id2):
    match = {}
    player_ids = []
    [player_ids.append(team_info.loc[id1]['player{}'.format(i)]) for i in range(1, 6)]
    [player_ids.append(team_info.loc[id2]['player{}'.format(i)]) for i in range(1, 6)]
    #     #local_dict_hero = {'hero_{}'.format(idx+1):hero_id for idx, hero_id in enumerate(hero_ids)}
    #     #local_hero_stats = {'global_hero_{}_{}'.format(idx+1,stat):get_hero_stat(hero_id,stat,matches_dict[key]['gameVersionId']) for idx, hero_id in enumerate(hero_ids) for stat in ['wins','losses','rating','games']}
    local_dict_acc = {'account_pro_{}_{}'.format(idx + 1, stat): get_player_stat(player_id, stat) for idx, player_id in
                      enumerate(player_ids) for stat in ['wins', 'losses', 'rating', 'imp', 'games']}
    # local_dict_wins = {'account_{}_{}'.format(idx+1,stat):get_player_stat(player['steamAccountId'],stat,matches_dict[key]['gameVersionId'],player['heroId']) for idx, player in enumerate(matches_dict[key]['players']) for stat in ['player_hero_wins','player_hero_losses','player_hero_rating','player_hero_imp','player_hero_games']}
    local_dict_team_stats = {'{}_team_{}'.format('r' if idx == 0 else 'd', stat): get_team_stat(team_id, stat) for
                             idx, team_id in enumerate([id1, id2]) for stat in
                             ['wins', 'losses', 'rating', 'elo_rating']}
    local_dict_captain_stats = {'{}_captain_{}'.format('r' if idx == 0 else 'd', stat): get_captain_stat(team_id, stat)
                                for idx, team_id in
                                enumerate([team_info.loc[id1]['captain'], team_info.loc[id2]['captain']]) for stat in
                                ['wins', 'losses']}

    t1 = [player_dict[player_id]['rating'] for player_id in player_ids[:5]]
    t2 = [player_dict[player_id]['rating'] for player_id in player_ids[5:]]
    match['pro_players_win_prob'] = win_probability(t1, t2)
    r1 = team_dict[id1]['rating']
    r2 = team_dict[id2]['rating']
    t1 = [r1]
    t2 = [r2]
    match['pro_teams_win_prob'] = win_probability(t1, t2)
    match['elo_pro_teams_win_prob'] = (
                1.0 / (1.0 + pow(10, ((team_dict[id1]['elo_rating'] - team_dict[id2]['elo_rating']) / 400))))
    local_dict_public_stats = {'account_public_{}_{}'.format(idx + 1, stat): get_player_stat(player_id, stat) for
                               idx, player_id in enumerate(player_ids) for stat in ['p_games']}
    match = {**match, **local_dict_acc, **local_dict_team_stats, **local_dict_captain_stats, **local_dict_public_stats}
    df = pd.DataFrame.from_dict(match, orient='index').T
    df['r_team_winrate'] = df['r_team_wins'] / (df['r_team_wins'] + df['r_team_losses'])
    df['d_team_winrate'] = df['d_team_wins'] / (df['d_team_wins'] + df['d_team_losses'])
    df['r_captain_winrate'] = df['r_captain_wins'] / (df['r_captain_wins'] + df['r_captain_losses'])
    df['d_captain_winrate'] = df['d_captain_wins'] / (df['d_captain_wins'] + df['d_captain_losses'])
    for i in range(1, 11):
        # df['account_{}_player_hero_winrate'.format(i)] =df['account_{}_player_hero_wins'.format(i)]/(df['account_{}_player_hero_wins'.format(i)]+ df['account_{}_player_hero_losses'.format(i)])
        df['account_id_{}_pro_winrate'.format(i)] = df['account_pro_{}_wins'.format(i)] / (
                    df['account_pro_{}_wins'.format(i)] + df['account_pro_{}_losses'.format(i)])
        # df['global_hero_{}_winrate'.format(i)] =df['global_hero_{}_wins'.format(i)]/(df['global_hero_{}_wins'.format(i)]+ df['global_hero_{}_losses'.format(i)])

    df['winrate_team_ratio'] = df['r_team_winrate'] / df['d_team_winrate']
    df['winrate_captain_ratio'] = df['r_captain_winrate'] / df['d_captain_winrate']
    # df['sum_r_global_hero_winrate'] = df[['global_hero_{}_winrate'.format(i) for i in range(1, 6)]].sum(axis=1)
    # df['sum_d_global_hero_winrate'] = df[['global_hero_{}_winrate'.format(i) for i in range(6, 11)]].sum(axis=1)
    df['sum_r_account_pro_winrate'] = df[['account_id_{}_pro_winrate'.format(i) for i in range(1, 6)]].sum(axis=1)
    df['sum_d_account_pro_winrate'] = df[['account_id_{}_pro_winrate'.format(i) for i in range(6, 11)]].sum(axis=1)
    # df['sum_r_player_hero_winrate'] = df[['account_{}_player_hero_winrate'.format(i) for i in range(1, 6)]].sum(axis=1)
    # df['sum_d_player_hero_winrate'] = df[['account_{}_player_hero_winrate'.format(i) for i in range(6, 11)]].sum(axis=1)

    df['sum_winrate_account_pro_ratio'] = df['sum_r_account_pro_winrate'] / df['sum_d_account_pro_winrate']
    # df['sum_winrate_global_hero_ratio'] = df['sum_r_global_hero_winrate'] / df['sum_d_global_hero_winrate']
    # df['sum_winrate_player_hero_ratio'] = df['sum_r_player_hero_winrate'] / df['sum_d_player_hero_winrate']

    # df['total_r_player_hero_games'] = df[['account_{}_player_hero_games'.format(i) for i in range(1, 6)]].sum(axis=1)
    # df['total_d_player_hero_games'] = df[['account_{}_player_hero_games'.format(i) for i in range(6, 11)]].sum(axis=1)
    # df['total_r_global_hero_games'] = df[['global_hero_{}_games'.format(i) for i in range(1, 6)]].sum(axis=1)
    # df['total_d_global_hero_games'] = df[['global_hero_{}_games'.format(i) for i in range(6, 11)]].sum(axis=1)
    # df['total_global_hero_games_tario'] = df['total_r_global_hero_games'] / df['total_d_global_hero_games']
    df['r_total_captain_games'] = df['r_captain_wins'] + df['r_captain_losses']
    df['d_total_captain_games'] = df['d_captain_wins'] + df['d_captain_losses']
    df['total_r_pro_games'] = df[['account_pro_{}_games'.format(i) for i in range(1, 6)]].sum(axis=1)
    df['total_d_pro_games'] = df[['account_pro_{}_games'.format(i) for i in range(6, 11)]].sum(axis=1)
    df['total_r_public_games'] = df[['account_public_{}_p_games'.format(i) for i in range(1, 6)]].sum(axis=1)
    df['total_d_public_games'] = df[['account_public_{}_p_games'.format(i) for i in range(6, 11)]].sum(axis=1)

    # df['total_player_hero_tario'] = df['total_r_player_hero_games'] / df['total_d_player_hero_games']
    df['total_captain_games_tario'] = df['r_total_captain_games'] / df['d_total_captain_games']
    df['total_pro_players_games_tario'] = df['total_r_pro_games'] / df['total_d_pro_games']
    df['total_public_players_games_tario'] = df['total_r_public_games'] / df['total_d_public_games']

    df['TS_rating_ratio'] = df['r_team_rating'] / df['d_team_rating']
    df['elo_rating_ratio'] = df['r_team_elo_rating'] / df['d_team_elo_rating']

    df['total_r_TS_pro_rating'] = df[['account_pro_{}_rating'.format(i) for i in range(1, 6)]].sum(axis=1)
    df['total_d_TS_pro_rating'] = df[['account_pro_{}_rating'.format(i) for i in range(6, 11)]].sum(axis=1)
    df['teams_players_pro_rating_TS_ratio'] = df['total_r_TS_pro_rating'] / df['total_d_TS_pro_rating']

    # df['total_r_TS_player_hero_rating'] = df[['account_{}_player_hero_rating'.format(i) for i in range(1, 6)]].sum(axis=1)
    # df['total_d_TS_player_hero_rating'] = df[['account_{}_player_hero_rating'.format(i) for i in range(6, 11)]].sum(axis=1)
    # df['player_hero_rating_TS_ratio'] = df['total_r_TS_player_hero_rating'] / df['total_d_TS_player_hero_rating']

    # df['total_r_TS_global_hero_rating'] = df[['global_hero_{}_rating'.format(i) for i in range(1, 6)]].sum(axis=1)
    # df['total_d_TS_global_hero_rating'] = df[['global_hero_{}_rating'.format(i) for i in range(6, 11)]].sum(axis=1)
    # df['global_hero_rating_TS_ratio'] = df['total_r_TS_global_hero_rating'] / df['total_d_TS_global_hero_rating']

    df['r_imp_pro'] = df[['account_pro_{}_imp'.format(i) for i in range(1, 6)]].sum(axis=1)
    df['d_imp_pro'] = df[['account_pro_{}_imp'.format(i) for i in range(6, 11)]].sum(axis=1)
    df['imp_pro_ratio'] = df['r_imp_pro'] / df['d_imp_pro']

    # df['r_imp_player_hero'] =df[['account_{}_player_hero_imp'.format(i) for i in range(1, 6)]].sum(axis=1)
    # df['d_imp_player_hero'] = df[['account_{}_player_hero_imp'.format(i) for i in range(6, 11)]].sum(axis=1)
    # df['imp_player_hero_ratio']= df['r_imp_player_hero'] /df['d_imp_player_hero']
    return df[['pro_players_win_prob', 'pro_teams_win_prob', 'elo_pro_teams_win_prob',
       'r_team_wins', 'r_team_losses', 'r_team_rating', 'r_team_elo_rating',
       'd_team_wins', 'd_team_losses', 'd_team_rating', 'd_team_elo_rating',
       'r_captain_wins', 'r_captain_losses', 'd_captain_wins',
       'd_captain_losses', 'r_team_winrate', 'd_team_winrate',
       'r_captain_winrate', 'd_captain_winrate', 'winrate_team_ratio',
       'winrate_captain_ratio', 'sum_r_account_pro_winrate',
       'sum_d_account_pro_winrate', 'sum_winrate_account_pro_ratio',
       'r_total_captain_games', 'd_total_captain_games', 'total_r_pro_games',
       'total_d_pro_games', 'total_r_public_games', 'total_d_public_games',
       'total_captain_games_tario', 'total_pro_players_games_tario',
       'total_public_players_games_tario', 'TS_rating_ratio',
       'elo_rating_ratio', 'total_r_TS_pro_rating', 'total_d_TS_pro_rating',
       'teams_players_pro_rating_TS_ratio', 'r_imp_pro', 'd_imp_pro',
       'imp_pro_ratio']]


def update_state(max_id):
    api = OpenDotaAPI(verbose = True)
    ids = api.get_pb_ids(match_id=max_id)
    public_matches_dict = {}
    counter = 0
    while True:
        sleep(1)
        to_add = sorted(list(set(ids) - set(public_matches_dict.keys())))
        if len(to_add) == 0:
            with open('public_matches_local.pickle', 'wb') as f2:
                pickle.dump(public_matches_dict, f2)
            print('finish public, to add = 0')
            break
        resp = api.get_public_matches_stratz(to_add)
        if len(resp) < 10:
            for el in list(set(to_add[:10]) - set([x['id'] for x in resp])):
                ids.remove(el)
        local_d = {x['id']: x for x in resp}
        public_matches_dict = {**public_matches_dict, **local_d}
        if counter == 50:
            with open('public_matches_local.pickle', 'wb') as f2:
                pickle.dump(public_matches_dict, f2)
            counter = 0
        counter += 1
        print(len(public_matches_dict), len(to_add))
    pro_match = api.get_pro_ids(match_id=max_id)
    ids = [match['match_id'] for match in pro_match]
    pro_match = {match['match_id']: match for match in pro_match}
    counter = 0
    pro_matches_dict = {}
    while True:
        sleep(1)
        to_add = sorted(list(set(ids) - set(pro_matches_dict.keys())))
        if len(to_add) == 0:
            with open('pro_matches_local.pickle', 'wb') as f2:
                pickle.dump(pro_matches_dict, f2)

            print('finish, to add = 0')
            break

        resp = api.get_public_matches_stratz(to_add)
        if len(resp) < 10:
            for el in list(set(to_add[:10]) - set([x['id'] for x in resp])):
                ids.remove(el)
        local_d = {x['id']: x for x in resp}
        for match_id in local_d.keys():
            local_d[match_id]['radiant_captain'] = pro_match[match_id]['radiant_captain']
            local_d[match_id]['dire_captain'] = pro_match[match_id]['dire_captain']
            local_d[match_id]['radiant_team_id'] = pro_match[match_id]['radiant_team_id']
            local_d[match_id]['dire_team_id'] = pro_match[match_id]['dire_team_id']
        pro_matches_dict = {**pro_matches_dict, **local_d}
        counter += 1
        if counter == 50:
            with open('pro_matches_local.pickle', 'wb') as f2:
                pickle.dump(pro_matches_dict, f2)
            counter = 0
        print(len(pro_matches_dict), len(to_add))
def make_stat(max_id):
    pro_matches_dict = pickle.load(open('pro_matches_local.pickle', 'rb'))
    to_del = []
    for key, value in pro_matches_dict.items():
        if pro_matches_dict[key]['id'] <= max_id:
            to_del.append(key)
    for key in to_del:
        del pro_matches_dict[key]
    pro_ids = list(pro_matches_dict.keys())

    public_matches_dict = pickle.load(open('public_matches_local.pickle', 'rb'))
    to_del = []
    for key, value in public_matches_dict.items():
        if public_matches_dict[key]['id'] <= max_id:
            to_del.append(key)
    for key in to_del:
        del public_matches_dict[key]
    matches_dict = {**pro_matches_dict, **public_matches_dict}
    matches_dict = OrderedDict(sorted(matches_dict.items()))
    del pro_matches_dict
    del public_matches_dict
    to_del = []

    for key, value in matches_dict.items():
        if matches_dict[key]['id'] <= max_id:
            to_del.append(key)
            continue
        player_ids = [player['steamAccountId'] for player in matches_dict[key]['players']]
        if len(player_ids) < 10:
            to_del.append(key)
            continue
        local_dict_acc = {'account_id_{}'.format(idx + 1): player_id for idx, player_id in enumerate(player_ids)}
        player_imps = [player['imp'] if 'imp' in player else 100 for player in matches_dict[key]['players']]
        hero_ids = [player['heroId'] for player in matches_dict[key]['players']]
        if matches_dict[key]['id'] in pro_ids:
            if (matches_dict[key]['radiant_team_id'] == None or matches_dict[key]['dire_team_id'] == None):
                to_del.append(key)
                continue
            local_dict_hero = {'hero_{}'.format(idx + 1): hero_id for idx, hero_id in enumerate(hero_ids)}
            local_hero_stats = {'global_hero_{}_{}'.format(idx + 1, stat): get_hero_stat(hero_id, stat,
                                                                                         matches_dict[key][
                                                                                             'gameVersionId']) for
                                idx, hero_id in enumerate(hero_ids) for stat in ['wins', 'losses', 'rating', 'games']}
            local_dict_acc = {'account_pro_{}_{}'.format(idx + 1, stat): get_player_stat(player_id, stat) for
                              idx, player_id in enumerate(player_ids) for stat in
                              ['wins', 'losses', 'rating', 'imp', 'games']}
            local_dict_wins = {'account_{}_{}'.format(idx + 1, stat): get_player_stat(player['steamAccountId'], stat,
                                                                                      matches_dict[key][
                                                                                          'gameVersionId'],
                                                                                      player['heroId']) for idx, player
                               in enumerate(matches_dict[key]['players']) for stat in
                               ['player_hero_wins', 'player_hero_losses', 'player_hero_rating', 'player_hero_imp',
                                'player_hero_games']}
            local_dict_team_stats = {'{}_team_{}'.format('r' if idx == 0 else 'd', stat): get_team_stat(team_id, stat)
                                     for idx, team_id in enumerate(
                    [matches_dict[key]['radiant_team_id'], matches_dict[key]['dire_team_id']]) for stat in
                                     ['wins', 'losses', 'rating', 'elo_rating']}
            local_dict_captain_stats = {
                '{}_captain_{}'.format('r' if idx == 0 else 'd', stat): get_captain_stat(team_id, stat) for idx, team_id
                in enumerate([matches_dict[key]['radiant_captain'], matches_dict[key]['dire_captain']]) for stat in
                ['wins', 'losses']}

            t1 = [player_dict[player_id]['rating'] for player_id in player_ids[:5]]
            t2 = [player_dict[player_id]['rating'] for player_id in player_ids[5:]]
            matches_dict[key]['pro_players_win_prob'] = win_probability(t1, t2)
            r1 = team_dict[matches_dict[key]['radiant_team_id']]['rating']
            r2 = team_dict[matches_dict[key]['dire_team_id']]['rating']
            t1 = [r1]
            t2 = [r2]
            matches_dict[key]['pro_teams_win_prob'] = win_probability(t1, t2)
            matches_dict[key]['elo_pro_teams_win_prob'] = (1.0 / (1.0 + pow(10, ((team_dict[matches_dict[key][
                'radiant_team_id']]['elo_rating'] - team_dict[matches_dict[key]['dire_team_id']][
                                                                                      'elo_rating']) / 400))))
            local_dict_public_stats = {'account_public_{}_{}'.format(idx + 1, stat): get_player_stat(player_id, stat)
                                       for idx, player_id in enumerate(player_ids) for stat in ['p_games']}
            matches_dict[key] = {**matches_dict[key], **local_dict_acc, **local_dict_wins, **local_dict_team_stats,
                                 **local_dict_captain_stats, **local_dict_public_stats, **local_dict_hero,
                                 **local_hero_stats}
            update_player_stat(player_ids, player_imps, matches_dict[key]['didRadiantWin'], True,
                               matches_dict[key]['gameVersionId'], hero_ids)
            update_team_stat(matches_dict[key])
            update_captain_stat(matches_dict[key]['radiant_captain'], matches_dict[key]['dire_captain'],
                                matches_dict[key]['didRadiantWin'])
            update_hero_stat(hero_ids, player_imps, matches_dict[key]['didRadiantWin'],
                             matches_dict[key]['gameVersionId'])
        else:
            to_del.append(key)
            update_player_stat(player_ids, player_imps, matches_dict[key]['didRadiantWin'], False,
                               matches_dict[key]['gameVersionId'], hero_ids)
            update_hero_stat(hero_ids, player_imps, matches_dict[key]['didRadiantWin'],
                             matches_dict[key]['gameVersionId'])
        max_id = matches_dict[key]['id']
        del matches_dict[key]['players']
        if 'numHumanPlayers' in matches_dict[key]:
            del matches_dict[key]['numHumanPlayers']
        if 'avgImp' in matches_dict[key]:
            del matches_dict[key]['avgImp']
        if 'firstBloodTime' in matches_dict[key]:
            del matches_dict[key]['firstBloodTime']
        if 'analysisOutcome' in matches_dict[key]:
            del matches_dict[key]['analysisOutcome']
        if 'predictedOutcomeWeight' in matches_dict[key]:
            del matches_dict[key]['predictedOutcomeWeight']
        if 'radiantTeam' in matches_dict[key]:
            del matches_dict[key]['radiantTeam']
        if 'direTeam' in matches_dict[key]:
            del matches_dict[key]['direTeam']
        if 'parsedDateTime' in matches_dict[key]:
            del matches_dict[key]['parsedDateTime']
        if 'startDateTime' in matches_dict[key]:
            del matches_dict[key]['startDateTime']
        if 'replaySalt' in matches_dict[key]:
            del matches_dict[key]['replaySalt']
        if 'isStats' in matches_dict[key]:
            del matches_dict[key]['isStats']
        if 'regionId' in matches_dict[key]:
            del matches_dict[key]['regionId']
        if 'endDateTime' in matches_dict[key]:
            del matches_dict[key]['endDateTime']
        if 'sequenceNum' in matches_dict[key]:
            del matches_dict[key]['sequenceNum']
        if 'clusterId' in matches_dict[key]:
            del matches_dict[key]['clusterId']
        if 'lobbyType' in matches_dict[key]:
            del matches_dict[key]['lobbyType']
        if 'gameMode' in matches_dict[key]:
            del matches_dict[key]['gameMode']
        if 'seriesId' in matches_dict[key]:
            del matches_dict[key]['seriesId']
        if 'rank' in matches_dict[key]:
            del matches_dict[key]['rank']
        if 'statsDateTime' in matches_dict[key]:
            del matches_dict[key]['statsDateTime']
        if 'leagueId' in matches_dict[key]:
            del matches_dict[key]['leagueId']
        if 'bracket' in matches_dict[key]:
            del matches_dict[key]['bracket']
        if 'durationSeconds' in matches_dict[key]:
            del matches_dict[key]['durationSeconds']
    with open('all_players_dict.pickle', 'wb') as f2:
        pickle.dump(player_dict, f2)
    players = list(set([team_dict[team]['player{}'.format(p_id)] for p_id in range(1, 6) for team in team_dict]))
    pro_players = [player_dict[player] for player in players]
    new_dict = {players[idx]: player for idx, player in enumerate(pro_players)}
    main_dict['player_dict'] = new_dict
    main_dict['team_dict'] = team_dict
    main_dict['captain_dict'] = captain_dict
    main_dict['global_heroes'] = global_heroes
    main_dict['max_id'] = max_id
    with open('main_dict.pickle', 'wb') as f2:
        pickle.dump(main_dict, f2)
    with open('new_dict.pickle', 'wb') as f2:
        pickle.dump(new_dict, f2)
    with open('team_dict.pickle', 'wb') as f2:
        pickle.dump(team_dict, f2)
    with open('captain_dict.pickle', 'wb') as f2:
        pickle.dump(captain_dict, f2)
    with open('global_heroes.pickle', 'wb') as f2:
        pickle.dump(global_heroes, f2)
    with open('max_id.pickle', 'wb') as f2:
        pickle.dump(max_id, f2)
app = Flask(__name__)
model = pickle.load(open('model.pickle', 'rb'))
# main_dict = pickle.load(open('main_dict.pickle', 'rb'))
# player_dict = main_dict['player_dict']
# team_dict = main_dict['team_dict']
# captain_dict = main_dict['captain_dict']
# global_heroes = main_dict['global_heroes']
# max_id = main_dict['max_id']

# player_dict = pickle.load(open('new_dict.pickle', 'rb'))
# print(len(player_dict))

# player_dict = pickle.load(open('all_players_dict.pickle', 'rb'))
# update_state(max_id)
# make_stat(max_id)
# player_dict = main_dict['player_dict']
team_dict = pickle.load(open('team_dict.pickle', 'rb'))
team_info = pd.DataFrame(team_dict).T
print(len(team_info))
@app.route('/predictbyname', methods=['GET'])
def get_tasks2():
    name1 = request.args.get('name1', None)
    name2 = request.args.get('name2', None)
    if name1 is None:
        abort(400, description="id1 is None")
    if name2 is None:
        abort(400, description="id2 is None")
    print(name1,name2)
    id1 = get_id_by_name(name1)
    if id1 is None:
        abort(400, description="Name 1 not found")
    id2 = get_id_by_name(name2)
    if id2 is None:
        abort(400, description="Name 2 not found")
    print(id1, id2)
    x1 = make_row(int(id1), int(id2))
    result = model.predict_proba(x1)

    x2 = make_row(int(id2), int(id1))

    result2 = model.predict_proba(x2)

    resp = {'Team_1': (result[0][1] + result2[0][0]) / 2,
            'Team_2': (result[0][0] + result2[0][1]) / 2,
            'Name_1': team_info.loc[id1]['name'],
            'Name_2': team_info.loc[id2]['name'],
            'id1' : id1,
            'id2' : id2
            }
    return jsonify(resp)
@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


@app.errorhandler(400)
def not_found2(error):
    return make_response(jsonify({'error': error.description}), 400)

if __name__ == '__main__':
    app.run(debug=True)
