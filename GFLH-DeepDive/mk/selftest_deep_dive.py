# -*- coding: utf-8 -*-
# selftest_deep_dive.py
# 离线自检：用 动作顺序/ 里的真实抓包验证判定逻辑与 1T 请求顺序，不需要连服务器。
#
# 运行：python mk/selftest_deep_dive.py

import copy
import glob
import json
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() not in ("utf-8", "utf8"):
            _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

MK_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(MK_DIR)
# 抓包数据（动作顺序/、Index/index）默认放在项目根目录；
# 如果为了隐私把数据挪到了别处，可以用环境变量指向存放这些数据的目录。
DATA_ROOT = os.environ.get('GFLH_DEEPDIVE_DATA') or ROOT_DIR
TRACE_DIR = os.path.join(DATA_ROOT, '动作顺序')


def find_index_file():
    """抓包文件名带时间戳，这里取最新的 *Index_index*.json。"""
    matches = sorted(glob.glob(os.path.join(DATA_ROOT, '*Index_index*.json')))
    return matches[-1] if matches else None


def data_ready():
    """没有抓包数据时（例如为了隐私没有提交 Index），自检直接跳过。"""
    if not os.path.isdir(TRACE_DIR):
        return False
    if not os.path.isfile(os.path.join(TRACE_DIR, '0061_S2C_4000_Mission_startMission_1793605218.json')):
        return False
    return find_index_file() is not None

sys.path.insert(0, os.path.join(ROOT_DIR, 'src'))

import deep_dive_core as core  # noqa: E402


def load(name):
    with open(os.path.join(TRACE_DIR, name), 'r', encoding='utf-8') as fh:
        return json.load(fh)


class MockClient:
    """按端点回放抓包，记录请求顺序。"""

    def __init__(self):
        self.calls = []
        self.queues = {}

    def set(self, endpoint, *responses):
        self.queues[endpoint] = list(responses)

    def send_request(self, endpoint, payload, max_retries=3, timeout=15):
        self.calls.append((endpoint, payload))
        queue = self.queues.get(endpoint)
        if not queue:
            return {}
        if len(queue) > 1:
            return queue.pop(0)
        return queue[0]

    def endpoints(self):
        return [endpoint for endpoint, _ in self.calls]


FAILED = []


def check(name, condition, detail=''):
    if condition:
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s %s" % (name, detail))
        FAILED.append(name)


def build_client(start_resp, turn2_resp):
    client = MockClient()
    # 真实服 Mission/combinationInfo 的回包就是空列表
    client.set(core.API_MISSION_COMBINFO, [])
    client.set(core.API_MISSION_START, start_resp)
    client.set(core.API_MISSION_SUPPLY, {})
    client.set(core.API_MISSION_TEAM_MOVE, load('0065_S2C_4000_Mission_teamMove_1793605224.json'),
               load('0074_S2C_4000_Mission_teamMove_1793605247.json'))
    client.set(core.API_MISSION_SANGVIS_BATTLE_FINISH, {})
    client.set(core.API_MISSION_REINFORCE, load('0070_S2C_4000_Mission_reinforceTeam_1793605246.json'))
    client.set(core.API_MISSION_BATTLE_FINISH, {})
    client.set(core.API_MISSION_END_TURN, load('0079_S2C_4000_Mission_endTurn_1793605269.json'))
    client.set(core.API_MISSION_START_ENEMY_TURN, load('0080_S2C_4000_Mission_startEnemyTurn_1793605275.json'))
    client.set(core.API_MISSION_END_ENEMY_TURN, load('0081_S2C_4000_Mission_endEnemyTurn_1793605284.json'))
    client.set(core.API_MISSION_START_TURN, turn2_resp)
    client.set(core.API_MISSION_ABORT, {})
    return client


def test_supply_and_rules():
    print("\n[1] 条件判定")
    start = load('0061_S2C_4000_Mission_startMission_1793605218.json')
    supply = core.find_supply_point(start)
    check("startMission 能识别补给点 9414", supply is not None and supply.get('spot_id') == 9414,
          repr(supply))

    blank = copy.deepcopy(start)
    blank['new_spot_change'] = {}
    check("补给点缺失时不通过", core.find_supply_point(blank) is None)

    wrong_type = copy.deepcopy(start)
    wrong_type['new_spot_change'] = {'9414': {'spot_id': 9414, 'type': 5}}
    check("type 不符时不通过", core.find_supply_point(wrong_type) is None)

    turn2 = load('0082_S2C_4000_Mission_startTurn_1793605298.json')
    evaluation = core.evaluate_2t(turn2)
    check("抓包样本 2T 判定为未通过（9447/9421 均被占领）", evaluation['pass'] is False,
          evaluation['text'])
    check("抓包样本 9438/9442 判定为被占领",
          all(item['ok'] for item in evaluation['required']), evaluation['text'])
    check("抓包样本 9446 判定为无敌人",
          all(item['ok'] for item in evaluation['empty']), evaluation['text'])
    print("    明细: %s" % evaluation['text'])

    free_case = copy.deepcopy(turn2)
    for spot in free_case['spot_act_info']:
        if str(spot.get('spot_id')) == '9447':
            spot['enemy_team_id'] = '0'
    evaluation = core.evaluate_2t(free_case)
    check("9447 空闲时 2T 判定通过", evaluation['pass'] is True, evaluation['text'])
    evaluation = core.evaluate_2t(free_case, {'either_free_mode': 'all'})
    check("either_free_mode=all 时只有一点空闲不通过", evaluation['pass'] is False,
          evaluation['text'])

    # README：不在 startTurn 的 spot_act_info 中表现 == 不被占领 / 不存在敌人
    absent_case = copy.deepcopy(turn2)
    absent_case['spot_act_info'] = [
        spot for spot in absent_case['spot_act_info']
        if str(spot.get('spot_id')) not in ('9447', '9421')
    ]
    evaluation = core.evaluate_2t(absent_case)
    check("9447/9421 未出现在 startTurn 时 2T 判定通过", evaluation['pass'] is True,
          evaluation['text'])

    absent_empty = copy.deepcopy(turn2)
    absent_empty['spot_act_info'] = [
        spot for spot in absent_empty['spot_act_info']
        if str(spot.get('spot_id')) != '9446'
    ]
    evaluation = core.evaluate_2t(absent_empty)
    empty_item = [item for item in evaluation['empty'] if item['spot_id'] == 9446][0]
    check("9446 未出现在 startTurn 时视为无敌人", empty_item['ok'] is True, evaluation['text'])


def test_roster():
    print("\n[2] 阵容解析")
    with open(find_index_file(), 'r', encoding='utf-8') as fh:
        index = json.load(fh)
    roster = core.extract_roster(index, 1, 2)
    check("格里芬 2 队 5 人", len(roster['guns']) == 5, roster['guns'])
    check("铁血 1 队 7 人", len(roster['sangvis_units']) == 7, roster['sangvis_units'])
    check("妖精 265574", roster['fairy_id'] == 265574, roster['fairy_id'])
    check("阵容可用", core.validate_roster(roster) == [], core.validate_roster(roster))
    print("    %s" % core.format_roster(roster))
    return roster


def test_attempt_fail(roster):
    print("\n[3] 一次完整尝试（2T 不满足 → 中止）")
    start = load('0061_S2C_4000_Mission_startMission_1793605218.json')
    turn2 = load('0082_S2C_4000_Mission_startTurn_1793605298.json')
    client = build_client(start, turn2)
    engine = core.DeepDiveReroll(client, roster, delay=0, log=print)
    result = engine.attempt(1)

    expected = [
        core.API_MISSION_COMBINFO,
        core.API_MISSION_START,
        core.API_MISSION_SUPPLY,
        core.API_MISSION_TEAM_MOVE,
        core.API_MISSION_SANGVIS_BATTLE_FINISH,
        core.API_MISSION_COMBINFO,
        core.API_MISSION_REINFORCE,
        core.API_MISSION_SUPPLY,
        core.API_MISSION_TEAM_MOVE,
        core.API_MISSION_BATTLE_FINISH,
        core.API_MISSION_COMBINFO,
        core.API_MISSION_END_TURN,
        core.API_MISSION_START_ENEMY_TURN,
        core.API_MISSION_END_ENEMY_TURN,
        core.API_MISSION_START_TURN,
        core.API_MISSION_ABORT,
    ]
    check("请求顺序与 动作顺序/ 一致", client.endpoints() == expected, client.endpoints())
    check("条件 1 通过", result.cond1 is True)
    check("条件 2 未通过", result.cond2 is False)
    check("该局被中止", result.ok is False and client.endpoints()[-1] == core.API_MISSION_ABORT)

    start_call = client.calls[1][1]
    check("startMission 使用铁血 1 队在 9457 部署",
          start_call['sangvis_spots'] == [{'spot_id': 9457, 'sangvis_team_id': roster['sangvis_team_id']}],
          start_call['sangvis_spots'])
    battle_call = client.calls[4][1]
    check("sangvisBattleFinish 使用移动后的 seed",
          battle_call['user_rec'] == '{"seed":3478,"record":[]}', battle_call['user_rec'])
    griffin_call = client.calls[9][1]
    check("battleFinish 使用移动后的 seed",
          griffin_call['user_rec'] == '{"seed":6235,"record":[]}', griffin_call['user_rec'])
    check("battleFinish 带上 5 个枪娘", len(griffin_call['guns']) == 5, griffin_call['guns'])


def test_attempt_pass(roster):
    print("\n[4] 一次完整尝试（2T 满足 → 保留任务）")
    start = load('0061_S2C_4000_Mission_startMission_1793605218.json')
    turn2 = load('0082_S2C_4000_Mission_startTurn_1793605298.json')
    for spot in turn2['spot_act_info']:
        if str(spot.get('spot_id')) == '9421':
            spot['enemy_team_id'] = '0'
    client = build_client(start, turn2)
    engine = core.DeepDiveReroll(client, roster, delay=0, log=print)
    result = engine.attempt(2)
    check("条件满足", result.ok is True and result.cond2 is True, result.detail)
    check("成功后不中止任务", core.API_MISSION_ABORT not in client.endpoints(),
          client.endpoints())


def test_supply_missing(roster):
    print("\n[5] 补给点未刷出（快速中止）")
    start = load('0061_S2C_4000_Mission_startMission_1793605218.json')
    start['new_spot_change'] = {}
    client = build_client(start, {})
    engine = core.DeepDiveReroll(client, roster, delay=0, log=print)
    result = engine.attempt(3)
    check("条件 1 未通过", result.ok is False and result.cond1 is False)
    check("只发了 3 个请求就中止",
          client.endpoints() == [core.API_MISSION_COMBINFO, core.API_MISSION_START,
                                 core.API_MISSION_ABORT],
          client.endpoints())


def test_protocol_error(roster):
    print("\n[6] 服务端报错时中止并返回错误")
    client = MockClient()
    client.set(core.API_MISSION_COMBINFO, [])
    client.set(core.API_MISSION_START, {'error': 'mission not exist'})
    client.set(core.API_MISSION_ABORT, {})
    engine = core.DeepDiveReroll(client, roster, delay=0, log=print)
    result = engine.attempt(4)
    check("返回错误信息", result.error is not None and 'mission not exist' in result.error,
          result.error)
    check("错误后尝试中止", core.API_MISSION_ABORT in client.endpoints(), client.endpoints())


def test_response_shapes(roster):
    print("\n[7] 回包格式兼容（combinationInfo 正常就是 []）")
    client = MockClient()
    client.set(core.API_MISSION_COMBINFO, [])
    client.set(core.API_MISSION_START, [])
    client.set(core.API_MISSION_ABORT, {'error_local': 'Unexpected plaintext response',
                                        'raw': 'error:3'})
    engine = core.DeepDiveReroll(client, roster, delay=0, log=print)
    result = engine.attempt(5)
    check("[] 不当作协议错误，能继续走到 startMission",
          core.API_MISSION_START in client.endpoints(), client.endpoints())
    check("startMission 返回 [] 时给出格式错误",
          result.error is not None and '返回格式异常' in result.error, result.error)

    # 中止时服务端回 error:3 视为「没有任务可中止」，不当作致命错误
    fake = MockClient()
    fake.set(core.API_MISSION_ABORT, {'error_local': 'Unexpected plaintext response',
                                      'raw': 'error:3'})
    engine2 = core.DeepDiveReroll(fake, roster, delay=0, log=print)
    check("中止返回 error:3 不抛异常", engine2.abort() is False)


def test_server_detection():
    print("\n[8] 区服识别")
    url_4000 = ("http://gfcn-game.ly.merge.sunborngame.com/index.php/4000"
                "/Mission/combinationInfo")
    check("识别 RO635(4000)", core.detect_server_url(url_4000) == core.SERVERS['RO635'],
          core.detect_server_url(url_4000))
    check("识别 M4A1(1000)",
          core.detect_server_url("http://gfcn-game.gw.merge.sunborngame.com/index.php/1000/Index/index")
          == core.SERVERS['M4A1'])
    check("普通 URL 返回 None", core.detect_server_url("https://example.com/") is None)

    collector = core.CaptureCollector()
    collector.handle("S2C", url_4000, {"uid": "1", "sign": "s"})
    check("CaptureCollector 记录区服", collector.server_url == core.SERVERS['RO635'],
          collector.server_url)


def main():
    if not data_ready():
        print("[跳过] 没有找到 动作顺序/ 或 Index/index 抓包数据，离线自检不执行。")
        print("       把抓包放回 %s，或用环境变量 GFLH_DEEPDIVE_DATA 指向存放这些数据的目录。" % ROOT_DIR)
        return 0

    test_supply_and_rules()
    roster = test_roster()
    test_attempt_fail(roster)
    test_attempt_pass(roster)
    test_supply_missing(roster)
    test_protocol_error(roster)
    test_response_shapes(roster)
    test_server_detection()

    print("\n==============================")
    if FAILED:
        print("失败 %d 项: %s" % (len(FAILED), ', '.join(FAILED)))
        return 1
    print("全部自检通过")
    return 0


if __name__ == '__main__':
    sys.exit(main())
