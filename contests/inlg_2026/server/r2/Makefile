# ops server render が生成した Makefile（大会 inlg_2026 / 回 r2）。手で直すなら ops 側の雛形を。
# 使い方: make plan-<track> optimize-<track> run-<track> status-<track> stop-<track> analyze-<track> / run-pre-<track> stop-pre-<track> / live
SHELL := /bin/bash
BIN   := ./aiwolf-nlp-server-linux-amd64
SCORE := $(HOME)/aiwolf-nlp-calculate-score
TRACKS := turn5 turn9 anytime5

.PHONY: help plan-all optimize-all live check
help:
	@echo "tracks: $(TRACKS)"; echo "targets: plan-<t> optimize-<t> run-<t> status-<t> stop-<t> analyze-<t> run-pre-<t> stop-pre-<t> plan-all optimize-all live check"

plan-all: $(addprefix plan-,$(TRACKS))
optimize-all: $(addprefix optimize-,$(TRACKS))

# 起動前チェック: ポートが空いていて、公開ディレクトリが書けること
check:
	@for t in $(TRACKS); do p=$$(grep -m1 "port:" $$t.yml | awk '{print $$2}'); ss -tln | grep -q ":$$p " && echo "NG: port $$p in use ($$t)" || echo "OK: port $$p free ($$t)"; done
	@for d in $$(grep -h "output_dir: /var/www" *.yml | awk '{print $$2}' | sort -u); do [ -d "$$d" ] && [ -w "$$d" ] && echo "OK: $$d" || echo "NG: $$d (mkdir -p で作る)"; done

# calculate-score の配信（全トラック分の tmux ウィンドウ）
live:
	@[ -x $(SCORE)/scripts/start_live.sh ] || { echo "$(SCORE) がありません: git clone https://github.com/aiwolfdial/aiwolf-nlp-calculate-score.git $(SCORE) && (cd $(SCORE) && uv sync)"; exit 1; }
	$(SCORE)/scripts/start_live.sh $(addsuffix .yml,$(TRACKS))

# ---- turn5 (ターン式 × 5人村) : port 8005, 18 teams, 270 games ----
plan-turn5:
	python3 plan_game_count.py --config turn5.yml --teams-yml teams.yml --track track_turn5 --min-per-team 75 --max-per-team 100
optimize-turn5:
	python3 generate_match_optimizer.py --config turn5.yml --teams-yml teams.yml --track track_turn5 --output log/match_optimizer_turn5.json
run-turn5:
	@mkdir -p log; nohup $(BIN) -c ./turn5.yml >> log_turn5.log 2>&1 & echo "turn5: pid=$$!"
run-pre-turn5:
	@mkdir -p log; nohup $(BIN) -c ./turn5_pre.yml >> log_turn5_pre.log 2>&1 & echo "turn5 (pre): pid=$$!"
status-turn5:
	@ps aux | grep "[/]turn5.yml" || echo "turn5: not running"; ss -tln | grep ":8005 " || echo "port 8005: free"
	@[ -f log/match_optimizer_turn5.json ] && echo "ended: $$(jq '.ended_matches | length' log/match_optimizer_turn5.json) / 270  remaining(w=1): $$(jq '[.scheduled_matches[] | select(.weight==1)] | length' log/match_optimizer_turn5.json)" || true
stop-turn5:
	-pkill -f "[/]turn5.yml"; sleep 3; ps aux | grep "[/]turn5.yml" || echo "turn5: stopped"
stop-pre-turn5:
	-pkill -f "[/]turn5_pre.yml"; sleep 3; ps aux | grep "[/]turn5_pre.yml" || echo "turn5 (pre): stopped"
analyze-turn5:
	$(BIN) -c ./turn5.yml -a

# ---- turn9 (ターン式 × 9人村) : port 8009, 14 teams, 28 games ----
plan-turn9:
	python3 plan_game_count.py --config turn9.yml --teams-yml teams.yml --track track_turn9 --min-per-team 12 --max-per-team 18
optimize-turn9:
	python3 generate_match_optimizer.py --config turn9.yml --teams-yml teams.yml --track track_turn9 --output log/match_optimizer_turn9.json
run-turn9:
	@mkdir -p log; nohup $(BIN) -c ./turn9.yml >> log_turn9.log 2>&1 & echo "turn9: pid=$$!"
run-pre-turn9:
	@mkdir -p log; nohup $(BIN) -c ./turn9_pre.yml >> log_turn9_pre.log 2>&1 & echo "turn9 (pre): pid=$$!"
status-turn9:
	@ps aux | grep "[/]turn9.yml" || echo "turn9: not running"; ss -tln | grep ":8009 " || echo "port 8009: free"
	@[ -f log/match_optimizer_turn9.json ] && echo "ended: $$(jq '.ended_matches | length' log/match_optimizer_turn9.json) / 28  remaining(w=1): $$(jq '[.scheduled_matches[] | select(.weight==1)] | length' log/match_optimizer_turn9.json)" || true
stop-turn9:
	-pkill -f "[/]turn9.yml"; sleep 3; ps aux | grep "[/]turn9.yml" || echo "turn9: stopped"
stop-pre-turn9:
	-pkill -f "[/]turn9_pre.yml"; sleep 3; ps aux | grep "[/]turn9_pre.yml" || echo "turn9 (pre): stopped"
analyze-turn9:
	$(BIN) -c ./turn9.yml -a

# ---- anytime5 (いつでも発話 × 5人村) : port 8105, 12 teams, 24 games ----
plan-anytime5:
	python3 plan_game_count.py --config anytime5.yml --teams-yml teams.yml --track track_anytime5 --min-per-team 8 --max-per-team 12
optimize-anytime5:
	python3 generate_match_optimizer.py --config anytime5.yml --teams-yml teams.yml --track track_anytime5 --output log/match_optimizer_anytime5.json
run-anytime5:
	@mkdir -p log; nohup $(BIN) -c ./anytime5.yml >> log_anytime5.log 2>&1 & echo "anytime5: pid=$$!"
run-pre-anytime5:
	@mkdir -p log; nohup $(BIN) -c ./anytime5_pre.yml >> log_anytime5_pre.log 2>&1 & echo "anytime5 (pre): pid=$$!"
status-anytime5:
	@ps aux | grep "[/]anytime5.yml" || echo "anytime5: not running"; ss -tln | grep ":8105 " || echo "port 8105: free"
	@[ -f log/match_optimizer_anytime5.json ] && echo "ended: $$(jq '.ended_matches | length' log/match_optimizer_anytime5.json) / 24  remaining(w=1): $$(jq '[.scheduled_matches[] | select(.weight==1)] | length' log/match_optimizer_anytime5.json)" || true
stop-anytime5:
	-pkill -f "[/]anytime5.yml"; sleep 3; ps aux | grep "[/]anytime5.yml" || echo "anytime5: stopped"
stop-pre-anytime5:
	-pkill -f "[/]anytime5_pre.yml"; sleep 3; ps aux | grep "[/]anytime5_pre.yml" || echo "anytime5 (pre): stopped"
analyze-anytime5:
	$(BIN) -c ./anytime5.yml -a

