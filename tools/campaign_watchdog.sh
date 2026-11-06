#!/usr/bin/env bash
#
# Babysitter for a long submission campaign on a flaky infrastructure.
#
# It was written after the daemon's circus arbiter wedged itself (its workers all
# died following a network outage, and the daemon then stopped itself), which left
# eight `pw.x` uploads cancelled and the campaign frozen with `Active workers [0]`.
#
# Every iteration it:
#   1. restarts the daemon if no worker is alive;
#   2. replays every calculation that has been sitting in a cancelled-transport state
#      for more than one interval;
#   3. prints the progress of the group it watches;
#   4. exits when all the workchains of that group are in a terminal state.
#
# Usage:
#   bash tools/campaign_watchdog.sh <workflows-group-label> [max-hours]
#   bash tools/campaign_watchdog.sh --like 'acwf-verification/<set>/%' [max-hours]
#
set -uo pipefail

GROUP_LABEL="${1:?usage: campaign_watchdog.sh <group-label|--like pattern> [max-hours]}"
if [ "${GROUP_LABEL}" = "--like" ]; then
    GROUP_LABEL="${2:?usage: campaign_watchdog.sh --like <pattern> [max-hours]}"
    GROUP_MATCH="g.label like '${GROUP_LABEL}'"
    MAX_HOURS="${3:-6}"
else
    GROUP_MATCH="g.label = '${GROUP_LABEL}'"
    MAX_HOURS="${2:-6}"
fi
INTERVAL=180
ITERATIONS=$(( MAX_HOURS * 3600 / INTERVAL ))

source "${CONDA_SH:-$HOME/install/miniconda3/etc/profile.d/conda.sh}"
conda activate aiida
export PGPASSWORD="${PGPASSWORD:-123}"
PSQL="psql -h 127.0.0.1 -U aiida_user -d aiida_db -t -A"

for i in $(seq 1 "$ITERATIONS"); do
    # 1. daemon health
    workers=$(verdi daemon status 2>/dev/null | grep -c '^ *[0-9]\+  *[0-9]')
    if [ "$workers" -eq 0 ]; then
        echo "[$(date +%H:%M:%S)] WARNING: no daemon workers -> restarting the daemon"
        verdi daemon restart >/dev/null 2>&1
        sleep 20
        verdi daemon incr 3 >/dev/null 2>&1
    fi

    # 2. replay calculations whose transport task was cancelled and which are stale
    stale=$($PSQL -c "
        select n.id from db_dbnode n
        join db_dbgroup_dbnodes m on m.dbnode_id = n.id
        join db_dbgroup g on g.id = m.dbgroup_id
        where $GROUP_MATCH
          and n.process_type = 'aiida.calculations:quantumespresso.pw'
          and n.attributes->>'process_state' = 'waiting'
          and n.attributes->>'process_status' like '%cancelled%'
          and n.mtime < now() - interval '10 minutes';" | tr '\n' ' ')
    if [ -n "${stale// /}" ]; then
        echo "[$(date +%H:%M:%S)] replaying stale calculations: $stale"
        verdi process play $stale >/dev/null 2>&1
    fi

    # 3. progress
    read -r ok bad run tot <<<"$($PSQL -c "
        select count(*) filter (where n.attributes->>'process_state' = 'finished' and n.attributes->>'exit_status' = '0'),
               count(*) filter (where n.attributes->>'process_state' in ('excepted','killed')
                                  or (n.attributes->>'process_state' = 'finished' and n.attributes->>'exit_status' <> '0')),
               count(*) filter (where n.attributes->>'process_state' = 'waiting'),
               count(*)
        from db_dbnode n
        join db_dbgroup_dbnodes m on m.dbnode_id = n.id
        join db_dbgroup g on g.id = m.dbgroup_id
        where $GROUP_MATCH
          and n.process_type = 'aiida.workflows:common_workflows.eos';" | tr '|' ' ')"
    echo "[$(date +%H:%M:%S)] workers=$workers EOS ok=$ok failed=$bad running=$run total=$tot"

    # 4. done?
    if [ "$tot" -gt 0 ] && [ $(( ok + bad )) -eq "$tot" ]; then
        echo "CAMPAIGN_DONE ok=$ok failed=$bad total=$tot"
        exit 0
    fi
    sleep "$INTERVAL"
done

echo "WATCHDOG_TIMEOUT after ${MAX_HOURS}h"
