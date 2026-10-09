#!/usr/bin/env python3
"""チーム数から「完全均一に揃う総ゲーム数」を逆算して出力するスクリプト。

default 系 yml の matching.team_count からチーム数 T を、
役職構成(agent_count / logic.roles)を参照して、
- 各チームの総出場数
- 各役職の担当回数
がすべて整数で揃う(=偏差0で完全均一になる)総ゲーム数 G の候補を、
指定した「1チームあたりの試合数レンジ(最小~最大)」の範囲で列挙する。

完全均一の条件:
  各役職 r について T | n_r * G が必要。よって G は
    L = lcm_r( T / gcd(T, n_r) )
  の倍数でなければならない。各チームの出場数は S*G/T (S=1ゲームの総枠数=agent_count)。

team_count が1ゲームの参加人数(agent_count)に満たない場合は、
重複なしでゲームを構成できないためエラーにする。

使い方:
  python3 plan_game_count.py --config config/default_5.yml \
      --min-per-team 75 --max-per-team 100
  python3 plan_game_count.py --config config/default_9.yml --per-team 90
"""

import argparse
import math
import sys
from functools import reduce
from pathlib import Path

import yaml


def load_teams_from_yml(path: Path, track: str) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        sys.exit(f"error: {path} は track: [チーム名, ...] 形式の YAML である必要があります")
    if track not in data:
        sys.exit(f"error: {path} に track '{track}' がありません(存在する track: {list(data)})")
    teams = data[track]
    if not isinstance(teams, list) or not teams:
        sys.exit(f"error: track '{track}' はチーム名のリストである必要があります")
    return [str(t) for t in teams]


def load_config(path: Path):
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    agent_count = cfg["game"]["agent_count"]
    roles_by_count = cfg["logic"]["roles"]
    roles_cfg = roles_by_count.get(agent_count) or roles_by_count.get(str(agent_count))
    if roles_cfg is None:
        sys.exit(f"error: logic.roles に agent_count={agent_count} の定義がありません")
    roles = {r: int(n) for r, n in roles_cfg.items() if int(n) > 0}
    return cfg, cfg["matching"], roles, int(agent_count)


def lcm(a: int, b: int) -> int:
    return a * b // math.gcd(a, b)


def required_period(T: int, roles: dict[str, int]) -> int:
    """G がこの値の倍数のとき、全役職・全チームの担当数が整数で揃う。"""
    return reduce(lcm, (T // math.gcd(T, n) for n in roles.values()), 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True, help="default 系 yml のパス")
    ap.add_argument("--teams-yml", default="teams.yml",
                    help="チーム名簿 YAML のパス(件数チェック用, 既定: teams.yml)")
    ap.add_argument("--track",
                    help="名簿内の track 名。指定時は名簿の件数が config の team_count と"
                         "一致するか検証し、食い違えばエラーにする")
    ap.add_argument("--min-per-team", type=int, help="1チームあたり試合数の最小")
    ap.add_argument("--max-per-team", type=int, help="1チームあたり試合数の最大")
    ap.add_argument("--per-team", type=int, help="1チームあたり試合数(min=max の指定)")
    args = ap.parse_args()

    # 1チームあたり試合数レンジの決定
    if args.per_team is not None:
        lo = hi = args.per_team
    else:
        lo = args.min_per_team
        hi = args.max_per_team
        if lo is None or hi is None:
            ap.error("--per-team か、--min-per-team と --max-per-team の両方を指定してください")
    if lo > hi:
        ap.error(f"最小 {lo} が最大 {hi} を上回っています")

    cfg, matching, roles, agent_count = load_config(Path(args.config))
    if "team_count" not in matching:
        sys.exit(f"error: {args.config} に matching.team_count がありません")
    T = int(matching["team_count"])
    S = sum(roles.values())  # 1ゲームの総枠数 = agent_count 相当

    # --- 名簿の件数チェック(--track 指定時のみ) ---
    if args.track:
        names = load_teams_from_yml(Path(args.teams_yml), args.track)
        if len(set(names)) != len(names):
            sys.exit(f"error: 名簿 {args.teams_yml} の track '{args.track}' にチーム名の重複があります")
        if len(names) != T:
            diff = (f"あと {T - len(names)} チーム足りません。" if len(names) < T
                    else f"{len(names) - T} チーム多すぎます。")
            sys.exit(
                f"error: チーム数が config の team_count と一致しません。\n"
                f"  名簿 {args.teams_yml} の track '{args.track}' の件数 = {len(names)} "
                f"/ config({args.config}) の team_count = {T}\n"
                f"  {diff}\n"
                f"  名簿の件数を team_count に揃えるか、config の team_count を修正してください。"
            )

    print(f"config      : {args.config}")
    print(f"agent_count : {agent_count} (1ゲームの参加人数 / 総枠数)")
    print(f"roles       : " + ", ".join(f"{r}={n}" for r, n in roles.items()) + f" (合計 {S})")
    print(f"team_count  : {T} (config の matching.team_count)")
    print(f"1チーム試合数: {lo} 〜 {hi}")
    print()

    # --- チーム数チェック ---
    if T < agent_count:
        sys.exit(
            f"error: チームが足りません。\n"
            f"  team_count {T} が1ゲームの参加人数 {agent_count} に満たないため、"
            f"重複なしでゲームを構成できません。\n"
            f"  あと {agent_count - T} チーム必要です。"
        )

    # --- 完全均一に必要な総ゲーム数 G の候補 ---
    L = required_period(T, roles)
    per_team_at_L = S * L // T

    # per-team = S*G/T を [lo, hi] に収める G(= L の倍数)を列挙
    # G の下限/上限
    g_min = math.ceil(lo * T / S)
    g_max = (hi * T) // S
    # L の倍数に丸める
    first = math.ceil(g_min / L) * L
    candidates = list(range(first, g_max + 1, L)) if first <= g_max else []

    print(f"完全均一の必要条件: 総ゲーム数 G は {L} の倍数")
    print(f"  (この場合の最小単位: G={L} → 各チーム {per_team_at_L} 試合)")
    print()

    if not candidates:
        # レンジ内に均一解が無い → 近傍を案内
        below = (first - L)
        near = []
        if below >= L:
            near.append(below)
        near.append(first)
        print(f"指定レンジ({lo}〜{hi}試合/チーム)内に完全均一となる G はありません。")
        print("近い候補:")
        for G in near:
            print(f"  G={G:>4} → 各チーム {S * G // T} 試合")
        sys.exit(1)

    print(f"=== 完全均一になる総ゲーム数の候補({lo}〜{hi}試合/チーム) ===")
    header = "G(総試合)".rjust(9) + "  " + "1チーム".rjust(7) + "  " + \
        "  ".join(f"{r[:9]}".rjust(9) for r in roles)
    print(header)
    for G in candidates:
        per_team = S * G // T
        row = f"{G:>9}  {per_team:>7}  " + "  ".join(f"{n * G // T:>9}" for n in roles.values())
        print(row)
    print()
    rec = candidates[0]
    print(f"→ 最小は G={rec}(各チーム {S * rec // T} 試合)。"
          f"生成は generate_match_optimizer.py に --game-count {rec} を渡してください:")
    print(f"  python3 generate_match_optimizer.py --config {args.config} "
          f"--teams-yml teams.yml --track <track名> --game-count {rec}")


if __name__ == "__main__":
    main()
