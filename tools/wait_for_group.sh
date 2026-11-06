#!/usr/bin/env bash
#
# Wait until every EOS workchain of a workflows group has reached a terminal state.
#
# Written after a one-line polling loop got this wrong: it counted only
# `process_state = 'waiting'`, and AiiDA workchains pass through `running` for a moment
# every time they wake up to process a finished child — which is exactly what happens
# between the "first volume" and "the remaining volumes" phases of the ACWF EOS
# workchain. The loop therefore declared the campaign finished while six fresh
# calculations had just been submitted. This script asks the opposite question ("is any
# node not terminal yet?") which has no such window.
#
# It talks to the database directly instead of to the daemon, so it keeps working when
# the daemon is unhealthy, and it has a longer horizon than tools/campaign_watchdog.sh
# (which babysits the daemon and therefore restarts itself in shorter stretches).
#
# Usage:
#     bash tools/wait_for_group.sh <workflows-group-label> [max-hours] [interval-seconds]
#     bash tools/wait_for_group.sh --like '<sql-LIKE-pattern>' [max-hours] [interval-seconds]
#
# ``--like`` covers groups that are split over several labels, e.g. the cutoff
# convergence scan, which has one workflows group per cutoff point.
#
set -uo pipefail

MATCH="g.label = '"
if [ "${1:-}" = "--like" ]; then
    GROUP_LABEL="${2:?usage: wait_for_group.sh --like <pattern> [max-hours] [interval-seconds]}"
    MAX_HOURS="${3:-12}"
    INTERVAL="${4:-120}"
    MATCH="g.label like '"
    shift 1
else
    GROUP_LABEL="${1:?usage: wait_for_group.sh <workflows-group-label> [max-hours] [interval-seconds]}"
    MAX_HOURS="${2:-12}"
    INTERVAL="${3:-120}"
fi
WHERE="${MATCH}${GROUP_LABEL}'"

export PGPASSWORD=123
PSQL="psql -h 127.0.0.1 -U aiida_user -d aiida_db -t -A"

count() {
    $PSQL -c "
        select count(*) from db_dbnode n
        join db_dbgroup_dbnodes m on m.dbnode_id = n.id
        join db_dbgroup g on g.id = m.dbgroup_id
        where $WHERE
          and n.process_type = 'aiida.workflows:common_workflows.eos'
          and $1;" | tr -d ' \n'
}

ITERATIONS=$(( MAX_HOURS * 3600 / INTERVAL ))
for _ in $(seq 1 "$ITERATIONS"); do
    total=$(count "'true'")
    if [ -z "${total}" ] || [ "${total}" = "0" ]; then
        echo "[$(date +%H:%M:%S)] no EOS workchain matching '${GROUP_LABEL}' — is the label right?"
        exit 2
    fi
    unfinished=$(count "n.attributes->>'process_state' not in ('finished','excepted','killed')")
    ok=$(count "n.attributes->>'process_state' = 'finished' and n.attributes->>'exit_status' = '0'")
    bad=$(( total - unfinished - ok ))

    if [ "${unfinished}" = "0" ]; then
        echo "[$(date +%H:%M:%S)] SETTLED: ${ok} ok, ${bad} failed, 0 running (of ${total}) in ${GROUP_LABEL}"
        if [ "${bad}" != "0" ]; then
            echo "--- failures"
            $PSQL -c "
                select n.id, n.attributes->>'process_state', n.attributes->>'exit_status'
                from db_dbnode n
                join db_dbgroup_dbnodes m on m.dbnode_id = n.id
                join db_dbgroup g on g.id = m.dbgroup_id
                where $WHERE
                  and n.process_type = 'aiida.workflows:common_workflows.eos'
                  and not (n.attributes->>'process_state' = 'finished'
                           and n.attributes->>'exit_status' = '0');"
        fi
        exit 0
    fi

    echo "[$(date +%H:%M:%S)] running=${unfinished} ok=${ok} failed=${bad} total=${total}"
    sleep "${INTERVAL}"
done

echo "WAITER_TIMEOUT after ${MAX_HOURS}h (group ${GROUP_LABEL} still has unfinished workchains)"
exit 1
