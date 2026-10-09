#!/usr/bin/env python3
"""match_optimizer.json をサーバの is_optimize 機能の代わりに事前生成するスクリプト。

チーム数(team_count)と総ゲーム数(game_count)・役職構成は default 系 yml を参照し、
チーム名は teams.yml の該当 track(track_5 等)から取得して、
- 総出場回数が均一(±1)
- 各役職の担当回数が均一(±1)
になるようなマッチ組み合わせを構築して matching.output_path に出力する。
game_count 的に完全均一が不可能な場合は floor/ceil 丸めによる最近接解になる。
名簿の件数が config の team_count と食い違う場合はエラーで停止する。

アルゴリズム:
  1. チーム×役職のクォータ行列を作る。各セルは理論値 n_r*G/T の floor か ceil、
     各行和(チーム総出場数)も S*G/T の floor か ceil になるよう転送問題として解く。
     (行列丸め定理によりこの同時丸めは常に実行可能 = 数学的最適マージン)
  2. クォータを固定したまま、各役職の担当をどのゲームに割り当てるかを
     焼きなまし(同役職の2ゲーム間スワップ)で最適化し、
     同一ゲーム内のチーム重複を最小化・均等化する。

使い方:
  python3 generate_match_optimizer.py --config config/default_9.yml \
      --teams-yml teams.yml --track track_9
  python3 generate_match_optimizer.py --config config/default_5.yml \
      --teams "teamA,teamB,teamC,teamD,teamE"   # ad hoc 上書き
"""

import argparse
import json
import math
import random
import sys
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
    matching = cfg["matching"]
    agent_count = cfg["game"]["agent_count"]
    roles_by_count = cfg["logic"]["roles"]
    roles_cfg = roles_by_count.get(agent_count) or roles_by_count.get(str(agent_count))
    if roles_cfg is None:
        sys.exit(f"error: logic.roles に agent_count={agent_count} の定義がありません")
    # 0 人役職は除外し、定義順を保持
    roles = {r: int(n) for r, n in roles_cfg.items() if int(n) > 0}
    if sum(roles.values()) != agent_count:
        print(
            f"warn: 役職合計 {sum(roles.values())} が agent_count {agent_count} と一致しません",
            file=sys.stderr,
        )
    return cfg, matching, roles


def build_quota(T: int, roles: dict[str, int], G: int, rng: random.Random):
    """チーム×役職のクォータ行列。各セル・各行和とも理論値の floor/ceil に収める。"""
    S = sum(roles.values())
    total = S * G
    base_tot, rem_tot = divmod(total, T)
    order = list(range(T))
    rng.shuffle(order)
    row_target = [base_tot] * T
    for i in range(rem_tot):
        row_target[order[i]] += 1

    quota = {r: [0] * T for r in roles}
    need = row_target[:]  # 残り行和
    for r, n in roles.items():
        b, rem = divmod(n * G, T)
        for t in range(T):
            quota[r][t] = b
            need[t] -= b
        # +1 の余りは残り行和が大きいチームへ
        cand = sorted(range(T), key=lambda t: (-need[t], rng.random()))
        for t in cand[:rem]:
            quota[r][t] += 1
            need[t] -= 1

    # まれな行和ズレを修復(役職単位で floor/ceil 内の付け替え)
    for relax in (False, True):
        for _ in range(10 * T * len(roles)):
            over = [t for t in range(T) if need[t] < 0]
            under = [t for t in range(T) if need[t] > 0]
            if not under:
                break
            moved = False
            for tp in under:
                for tn in over:
                    for r, n in roles.items():
                        b, rem = divmod(n * G, T)
                        ceil_r = b + (1 if rem else 0) + (1 if relax else 0)
                        if quota[r][tn] > max(b - (1 if relax else 0), 0) and quota[r][tp] < ceil_r:
                            quota[r][tn] -= 1
                            quota[r][tp] += 1
                            need[tn] += 1
                            need[tp] -= 1
                            moved = True
                            break
                    if moved:
                        break
                if moved:
                    break
            if not moved:
                break
        if all(v == 0 for v in need):
            break
    if any(v != 0 for v in need):
        sys.exit("error: クォータ行列の構築に失敗しました(想定外)")
    return quota, row_target


def pair(x: int) -> int:
    return x * (x - 1) // 2


class Schedule:
    """assign[r][g] = そのゲームで役職 r を担当するチーム idx のリスト(長さ n_r)。"""

    W_DUP = 1000.0   # 同一ゲーム内の同一チーム重複ペア
    W_SAMEROLE = 500.0  # 同一ゲーム内で同一チームが同じ役職を複数担当
    W_SPREAD = 1.0   # 重複担当(2枠出場)がチーム間で偏らないように

    def __init__(self, quota, roles, G, T, rng):
        self.roles = roles
        self.G = G
        self.T = T
        self.rng = rng
        self.assign = {}
        for r, n in roles.items():
            pool = []
            for t in range(T):
                pool += [t] * quota[r][t]
            rng.shuffle(pool)
            self.assign[r] = [pool[g * n : (g + 1) * n] for g in range(G)]
        # cnt[g][t]: ゲーム g でのチーム t の枠数
        self.cnt = [[0] * T for _ in range(G)]
        for r in roles:
            for g in range(G):
                for t in self.assign[r][g]:
                    self.cnt[g][t] += 1
        # dup[t]: チーム t が 2 枠以上出場しているゲームでの超過枠合計
        self.dup = [0] * T
        for t in range(T):
            self.dup[t] = sum(max(0, self.cnt[g][t] - 1) for g in range(G))

    def cost(self) -> float:
        c = 0.0
        for g in range(self.G):
            for t in range(self.T):
                c += self.W_DUP * pair(self.cnt[g][t])
        for r in self.roles:
            for g in range(self.G):
                counts = {}
                for t in self.assign[r][g]:
                    counts[t] = counts.get(t, 0) + 1
                for v in counts.values():
                    c += self.W_SAMEROLE * pair(v)
        mean = sum(self.dup) / self.T
        c += self.W_SPREAD * sum((d - mean) ** 2 for d in self.dup)
        return c

    def _local(self, g, r, teams):
        """ゲーム g / 役職 r 周辺の、対象チーム集合に関する局所コスト。"""
        c = 0.0
        for t in teams:
            c += self.W_DUP * pair(self.cnt[g][t])
            c += self.W_SAMEROLE * pair(self.assign[r][g].count(t))
        return c

    def _spread_cost(self):
        mean = sum(self.dup) / self.T
        return self.W_SPREAD * sum((d - mean) ** 2 for d in self.dup)

    def try_swap(self, temp: float) -> bool:
        r = self.rng.choice(list(self.roles))
        n = self.roles[r]
        g1, g2 = self.rng.sample(range(self.G), 2)
        i = self.rng.randrange(n)
        j = self.rng.randrange(n)
        a = self.assign[r][g1][i]
        b = self.assign[r][g2][j]
        if a == b:
            return False
        teams = {a, b}
        before = self._local(g1, r, teams) + self._local(g2, r, teams) + self._spread_cost()
        # スワップ適用
        self._apply(r, g1, i, g2, j, a, b)
        after = self._local(g1, r, teams) + self._local(g2, r, teams) + self._spread_cost()
        delta = after - before
        if delta <= 0 or (temp > 0 and self.rng.random() < math.exp(-delta / temp)):
            return True
        # 差し戻し
        self._apply(r, g1, i, g2, j, b, a)
        return False

    def _apply(self, r, g1, i, g2, j, a, b):
        """(g1,i) の a と (g2,j) の b を交換し cnt/dup を更新する。"""
        for g, t_out, t_in in ((g1, a, b), (g2, b, a)):
            self.dup[t_out] -= max(0, self.cnt[g][t_out] - 1)
            self.dup[t_in] -= max(0, self.cnt[g][t_in] - 1)
            self.cnt[g][t_out] -= 1
            self.cnt[g][t_in] += 1
            self.dup[t_out] += max(0, self.cnt[g][t_out] - 1)
            self.dup[t_in] += max(0, self.cnt[g][t_in] - 1)
        self.assign[r][g1][i] = b
        self.assign[r][g2][j] = a

    def anneal(self, iters: int):
        t0, t1 = 50.0, 0.01
        for k in range(iters):
            temp = t0 * (t1 / t0) ** (k / max(1, iters - 1))
            self.try_swap(temp)
        # 仕上げの山登り
        for _ in range(iters // 4):
            self.try_swap(0.0)

    def eliminate_duplicates(self, max_passes: int = 500) -> bool:
        """同一ゲーム内の重複(同じチームが2枠以上)を完全に解消する。

        同一役職内で別ゲームと1枠だけ入れ替えるため、各チーム×役職の担当数
        (クォータ=均一性)は一切変わらない。新たな重複を生まない入れ替えのみ行う。
        すべて解消できたら True。
        """
        roles = list(self.roles)
        for _ in range(max_passes):
            dups = [(g, t) for g in range(self.G) for t in range(self.T)
                    if self.cnt[g][t] > 1]
            if not dups:
                return True
            progressed = False
            for g, t in dups:
                if self.cnt[g][t] <= 1:
                    continue
                # 役職 r で t がゲーム g に入っている枠を、別ゲーム g2 の同役職枠と交換。
                # 条件: 受け入れ先チーム b が g に未出場、かつ t が g2 に未出場 → 重複を新たに作らない
                for r in roles:
                    if t not in self.assign[r][g]:
                        continue
                    i = self.assign[r][g].index(t)
                    order = list(range(self.G))
                    self.rng.shuffle(order)
                    done = False
                    for g2 in order:
                        if g2 == g or self.cnt[g2][t] != 0:
                            continue
                        row = self.assign[r][g2]
                        for j in range(len(row)):
                            b = row[j]
                            if b == t or self.cnt[g][b] != 0:
                                continue
                            self._apply(r, g, i, g2, j, t, b)
                            progressed = done = True
                            break
                        if done:
                            break
                    if done:
                        break
            if not progressed:
                break
        return all(self.cnt[g][t] <= 1
                   for g in range(self.G) for t in range(self.T))

    # ---- 対戦相手の均一化(第1段階のクォータ=出場数/役職数は不変) ----
    def _build_cooccurrence(self):
        """present[g]=そのゲームの出場チーム集合, co[a][b]=同席回数, opp_cost=Σco^2。"""
        self.present = [set(t for t in range(self.T) if self.cnt[g][t] > 0)
                        for g in range(self.G)]
        self.co = [[0] * self.T for _ in range(self.T)]
        for g in range(self.G):
            ps = sorted(self.present[g])
            for x in range(len(ps)):
                for y in range(x + 1, len(ps)):
                    self.co[ps[x]][ps[y]] += 1
                    self.co[ps[y]][ps[x]] += 1
        self.opp_cost = sum(self.co[a][b] ** 2
                            for a in range(self.T) for b in range(a + 1, self.T))

    def opponent_cost(self) -> int:
        self._build_cooccurrence()
        return self.opp_cost

    def balance_opponents(self, iters: int):
        """対戦ペアの同席回数のばらつき(Σco^2)を最小化する。

        同一役職・別ゲーム間の1枠入れ替えのみ行うため、各チームの出場数・役職数は不変。
        重複を新たに作らない入れ替えだけを採用するので、重複ゼロも維持される。
        (総同席数 G*C(S,2) は一定なので、Σco^2 の最小化=分散の最小化)
        """
        self._build_cooccurrence()
        roles = list(self.roles)
        t0, t1 = 5.0, 0.001
        total = max(1, iters)
        for k in range(total):
            temp = t0 * (t1 / t0) ** (k / total)
            r = self.rng.choice(roles)
            n = self.roles[r]
            g1, g2 = self.rng.sample(range(self.G), 2)
            i, j = self.rng.randrange(n), self.rng.randrange(n)
            a = self.assign[r][g1][i]
            b = self.assign[r][g2][j]
            if a == b:
                continue
            # 重複ゼロを保つ: b が g1 に未出場、a が g2 に未出場のときのみ
            if self.cnt[g1][b] != 0 or self.cnt[g2][a] != 0:
                continue
            # 同席回数の差分を集計(g1: a→b, g2: b→a)
            changes = {}
            for t in self.present[g1]:
                if t == a:
                    continue
                changes[(a, t)] = changes.get((a, t), 0) - 1
                changes[(b, t)] = changes.get((b, t), 0) + 1
            for t in self.present[g2]:
                if t == b:
                    continue
                changes[(a, t)] = changes.get((a, t), 0) + 1
                changes[(b, t)] = changes.get((b, t), 0) - 1
            delta = 0
            for (x, y), d in changes.items():
                if d:
                    old = self.co[x][y]
                    delta += (old + d) ** 2 - old ** 2
            if delta <= 0 or self.rng.random() < math.exp(-delta / temp):
                for (x, y), d in changes.items():
                    if d:
                        self.co[x][y] += d
                        self.co[y][x] += d
                self.present[g1].discard(a); self.present[g1].add(b)
                self.present[g2].discard(b); self.present[g2].add(a)
                self._apply(r, g1, i, g2, j, a, b)
                self.opp_cost += delta


def solve(T, roles, G, seed, restarts=8, iters=20000, forbid_dup=True, balance=True):
    best = None
    best_key = None
    for k in range(restarts):
        rng = random.Random(seed + k)
        quota, row_target = build_quota(T, roles, G, rng)
        sch = Schedule(quota, roles, G, T, rng)
        sch.anneal(iters)
        if forbid_dup:
            sch.eliminate_duplicates()
        dup_total = sum(sch.dup)
        # 対戦相手の均一化は重複ゼロを保てる場合のみ実施
        do_balance = balance and dup_total == 0
        if do_balance:
            sch.balance_opponents(iters)
        opp = sch.opponent_cost() if do_balance else 0
        # 重複ゼロ最優先 → 対戦相手の偏り(Σco^2) → 配置コスト
        key = (dup_total if forbid_dup else 0, opp, sch.cost())
        if best is None or key < best_key:
            best_key = key
            best = (sch, quota, row_target)
    return best


def report(sch: "Schedule", quota, teams, roles, G):
    T = len(teams)
    S = sum(roles.values())
    width = max(len(t) for t in teams) + 2
    header = "team".ljust(width) + "".join(r[:9].rjust(11) for r in roles) + "total".rjust(8)
    print("\n=== 担当回数(理論値: " + ", ".join(
        f"{r}={n * G / T:.3f}" for r, n in roles.items()) + f", total={S * G / T:.3f}) ===")
    print(header)
    for t in range(T):
        row = teams[t].ljust(width)
        tot = 0
        for r in roles:
            row += str(quota[r][t]).rjust(11)
            tot += quota[r][t]
        row += str(tot).rjust(8)
        print(row)
    dup_games = sum(1 for g in range(sch.G) for t in range(T) if sch.cnt[g][t] > 1)
    max_in_game = max(sch.cnt[g][t] for g in range(sch.G) for t in range(T))
    print(f"\nゲーム内重複枠: 合計 {sum(sch.dup)} (同一チームが同一ゲームに複数枠) / "
          f"1チームの同一ゲーム内最大枠数: {max_in_game}")
    if dup_games:
        for g in range(sch.G):
            dups = [f"{teams[t]}x{sch.cnt[g][t]}" for t in range(T) if sch.cnt[g][t] > 1]
            if dups:
                print(f"  game {g}: {', '.join(dups)}")
    # 偏差(サーバの CalcDeviation と同じ定義)
    dev = 0.0
    for t in range(T):
        for r, n in roles.items():
            dev += (quota[r][t] - n * G / T) ** 2
    print(f"役職偏差(二乗和, サーバ CalcDeviation 相当): {dev:.4f}")

    # 対戦相手の同席回数の分布
    co = [[0] * T for _ in range(T)]
    for g in range(sch.G):
        ps = [t for t in range(T) if sch.cnt[g][t] > 0]
        for x in range(len(ps)):
            for y in range(x + 1, len(ps)):
                co[ps[x]][ps[y]] += 1
                co[ps[y]][ps[x]] += 1
    covals = [co[a][b] for a in range(T) for b in range(a + 1, T)]
    if covals and S >= 2:
        mean = sum(covals) / len(covals)
        var = sum((v - mean) ** 2 for v in covals) / len(covals)
        print(f"対戦相手 同席回数: min={min(covals)} max={max(covals)} 幅={max(covals) - min(covals)} "
              f"平均={mean:.1f} 標準偏差={var ** 0.5:.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True, help="default 系 yml のパス")
    ap.add_argument("--teams-yml", default="teams.yml",
                    help="チーム名簿 YAML のパス(既定: teams.yml)")
    ap.add_argument("--track", help="名簿内の track 名(例: track_5)")
    ap.add_argument("--teams", help="カンマ区切りのチーム名リスト(名簿の代わりに直接指定)")
    ap.add_argument("--game-count", type=int, help="matching.game_count を上書き")
    ap.add_argument("--output", help="matching.output_path を上書き")
    ap.add_argument("--seed", type=int, default=0, help="乱数シード(再現用)")
    ap.add_argument("--restarts", type=int, default=8)
    ap.add_argument("--iters", type=int, default=20000)
    ap.add_argument("--allow-duplicates", action="store_true",
                    help="同一ゲーム内の同一チーム重複を許可する(既定は禁止)")
    ap.add_argument("--balance-opponents", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="対戦相手の同席回数も均一化する(既定: 有効。--no-balance-opponents で無効)")
    args = ap.parse_args()

    if bool(args.track) == bool(args.teams):
        ap.error("--track(名簿から取得) か --teams(直接指定) のどちらか一方を指定してください")

    cfg_path = Path(args.config)
    cfg, matching, roles = load_config(cfg_path)
    if args.teams:
        teams = [t.strip() for t in args.teams.split(",") if t.strip()]
    else:
        teams = load_teams_from_yml(Path(args.teams_yml), args.track)
    if len(set(teams)) != len(teams):
        sys.exit("error: チーム名が重複しています")

    T = len(teams)
    G = args.game_count or int(matching["game_count"])
    S = sum(roles.values())  # 1ゲームの枠数(= agent_count)
    forbid_dup = not args.allow_duplicates
    if forbid_dup and T < S:
        sys.exit(
            f"error: 重複禁止では同一ゲームに同じチームを入れられません。\n"
            f"  チーム数 {T} が1ゲームの枠数 {S} に満たないため、必ずどこかで重複します。\n"
            f"  あと {S - T} チーム必要です(または --allow-duplicates で重複を許可)。"
        )
    team_count = int(matching["team_count"])
    if T != team_count:
        src = f"--teams" if args.teams else f"名簿 {args.teams_yml} の track '{args.track}'"
        diff = (f"あと {team_count - T} チーム足りません。" if T < team_count
                else f"{T - team_count} チーム多すぎます。")
        sys.exit(
            f"error: チーム数が config の team_count と一致しません。\n"
            f"  {src} の件数 = {T} / config({cfg_path}) の team_count = {team_count}\n"
            f"  {diff}\n"
            f"  名簿の件数を team_count に揃えるか、config の team_count を修正してください。"
        )

    sch, quota, _ = solve(T, roles, G, args.seed, args.restarts, args.iters,
                          forbid_dup=forbid_dup, balance=args.balance_opponents)
    if forbid_dup and sum(sch.dup) > 0:
        sys.exit(
            "error: 重複禁止の対戦表を構成できませんでした(重複が残りました)。\n"
            "  --restarts / --iters を増やして再試行するか、--allow-duplicates を検討してください。"
        )

    scheduled = []
    for g in range(G):
        role_idxs = {r: sorted(sch.assign[r][g]) for r in roles}
        scheduled.append({"role_idxs": role_idxs, "weight": 1.0})

    out = {
        "infinite_loop": bool(matching.get("infinite_loop", False)),
        "team_count": T,
        "game_count": G,
        "role_num_map": {r: n for r, n in roles.items()},
        "idx_team_map": {str(i): t for i, t in enumerate(teams)},
        "scheduled_matches": scheduled,
        "ended_matches": [],
    }

    out_path = Path(args.output or matching["output_path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.with_suffix(out_path.suffix + ".bak").write_bytes(out_path.read_bytes())
        print(f"backup: {out_path}.bak")
    out_path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n",
                        encoding="utf-8")
    print(f"wrote: {out_path} (games={G}, teams={T})")
    report(sch, quota, teams, roles, G)


if __name__ == "__main__":
    main()
