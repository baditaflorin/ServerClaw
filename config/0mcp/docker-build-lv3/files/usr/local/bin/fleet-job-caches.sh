#!/bin/sh
# fleet-job gc --caches, fleet-job cache ls and fleet-job cache prune: look at, and bound, the fleet-job-cache-* docker volumes of this host.
# usage: caches.sh MODE MAX_AGE MAX_BYTES MIN_KEEP IMAGE [NAME [BUSY_KEEP]]
#   MODE list  what gc --caches would take from the Go build caches (only reads)
#        trim  gc --caches --yes: takes it. No volume is ever removed in these two modes
#        ls    cache ls: what each volume holds, when anything in it was last written, whether a container uses it (only reads)
#        plan  cache prune: what prune would do with each volume: remove it, trim it, keep it, or skip it (only reads)
#        prune cache prune --yes: does it
# NAME limits it to the one volume fleet-job-cache-NAME (the short name --cache takes); without it (or when it is empty) every such volume is
# looked at. BUSY_KEEP is 0 (or absent), or at least 21600 seconds, and is for plan and prune only: it lets them trim the Go build cache of a
# volume that a container uses (see below), and says how young a file in it may be and never go.
# MAX_AGE, MIN_KEEP: whole seconds; MAX_BYTES: whole bytes; IMAGE: the docker image of the container that walks a volume
# (GNU find and awk in it: the golang image has them). The ssh user cannot read /var/lib/docker, so a volume is only ever looked
# at, or emptied, through a root container that mounts that one volume (--pull never, --network none, a memory and a task cap, the
# volume mounted ro for everything but a trim).
# What a volume may lose, and only that:
#   - the volume is called fleet-job-cache-NAME: no other volume is looked at, whoever uses it. It is looked at only if docker
#     still has it (mounting a name that does not exist makes docker create it, empty);
#   - only a Go build cache is trimmed inside. It is a directory whose README starts with the text the go tool writes there, at the
#     top of the volume or one or two levels down (a volume that also holds the module cache keeps the build cache in build/).
#     Module caches and everything else in the volume are counted and never touched;
#   - inside it, a file goes when it was last modified at least the cut ago, where the cut is MAX_AGE, moved towards younger
#     files only as far as it takes to bring the build cache under MAX_BYTES, and never below MIN_KEEP. The go tool sets a
#     file's modification time whenever it uses it (at most once an hour), and treats a missing entry as a miss, so a trimmed
#     entry costs a rebuild and nothing else; README, trim.txt and the directories stay. An executable entry (go run, go tool: a
#     directory named *-d that holds the binary) is judged by its directory's time, which is not the time of the file in it, so
#     it is left to the go tool's own five-day trim;
#   - plan and prune: a volume that nothing has written to for MAX_AGE (the newest file in it, README and trim.txt not counted;
#     a volume with no file has the time of its top directory) is not trimmed but removed, whatever it holds, by docker itself,
#     which refuses a volume that any container (a stopped one too) still refers to. One that docker will not remove is trimmed
#     inside like any other;
#   - a volume with a container that is running, created, restarting or paused is only counted, never trimmed or removed (the
#     first thing the program asks docker, again for each volume). A docker that does not answer counts as busy. prune does not
#     even walk such a volume. This program's own walkers are containers too, so two runs at once leave each other's volumes alone.
#     The one exception is BUSY_KEEP: with it, plan and prune treat the Go build cache of such a volume (state busy, not unknown) like
#     any other, except that the cut never goes below BUSY_KEEP, so no file used within that time is ever taken, and the volume itself
#     is never removed. The go tool refreshes a file's time before it hands out the path of an entry (GetFile, OutputFile), so an entry
#     a running action holds is at most an hour plus that action old: a floor of six hours cannot reach one, and a trim like this one
#     is what the go tool itself does while builds run (a missing entry is a miss). Anything else in a volume in use is left alone.
# Prints fleet-job-caches/1 and a key=value block for each volume (it starts at its volume= line), then a --summary-- line with
# the number of blocks and docker=ok|down. A volume that could not be walked, trimmed or removed has result=failed and error=;
# the exit status is 0 once every volume has been looked at.

die() {
	code=$1
	shift
	printf 'fleet-job-remote: %s\n' "$*" >&2
	exit "$code"
}

# The program that runs in the container, as
#   sh -c WORKER worker ROOT MODE NOW MAX_AGE MAX_BYTES MIN_KEEP REMOVE_AFTER
# with the volume at ROOT. MODE is ls (what is in it), scan (also the build cache's profile, read only) or trim. REMOVE_AFTER is
# 0, or the seconds a volume must have gone unwritten to be removed whole: then it says verdict=remove for such a volume and
# does nothing else to it. It prints key=value lines only.
worker_text() {
	cat <<'FJ_WORKER'
root=$1 mode=$2 now=$3 maxage=$4 maxbytes=$5 minkeep=$6 removeafter=$7
cd "$root" || { echo 'kind=unknown'; echo 'error=cannot enter the volume'; exit 1; }
if ! find . -maxdepth 0 -printf '' -newermt @0 >/dev/null 2>&1; then
	echo 'kind=unknown'
	echo 'error=the image has no GNU find (-printf and -newermt): use an image such as golang'
	echo 'result=failed'
	exit 1
fi
# the whole volume: what is in it, whatever it is, and the newest modification time of any file in it. README and trim.txt do not
# count for the time (the go tool rewrites trim.txt whenever it trims, which says nothing about a build having used the cache)
tot=$( { find . -xdev -type f -printf '%T@ %s %f\n'; echo "FJ_STATUS $?"; } | awk '/^FJ_STATUS/ { st = $2; next } { n++; b += $2; if ($3 != "README" && $3 != "trim.txt" && $1 + 0 > nw) nw = $1 + 0 } END { printf "files=%.0f\nbytes=%.0f\nlast_write=%.0f\nwalk_status=%s\n", n, b, int(nw), st }')
printf '%s\n' "$tot" | grep -v '^last_write='
walk=0
case $tot in *walk_status=0*) ;; *) walk=1 ;; esac
lw=$(printf '%s\n' "$tot" | sed -n 's/^last_write=\([0-9][0-9]*\)$/\1/p')
case $lw in '' | *[!0-9]*) lw=0 ;; esac
if [ "$lw" = 0 ]; then
	# no file but the go tool's own: the volume was made, and never written to, at the time of its top directory
	lw=$(find . -maxdepth 0 -printf '%T@\n' | sed 's/\..*//')
	case $lw in '' | *[!0-9]*) lw=0 ;; esac
fi
echo "last_write=$lw"
# the Go build caches in it: a directory whose README is the one the go tool writes
sig='This directory holds cached build artifacts from the Go build system.'
isroot() {
	[ -d "$1" ] && [ ! -L "$1" ] && [ -f "$1/README" ] && [ ! -L "$1/README" ] || return 1
	IFS= read -r first <"$1/README" || true
	case $first in "$sig"*) return 0 ;; esac
	return 1
}
set --
names=
if isroot .; then
	set -- .
	names=.
else
	for d in */ */*/; do
		d=${d%/}
		case $d in '' | *[!A-Za-z0-9_./-]*) continue ;; esac
		case " $names " in *" ${d%/*} "*) continue ;; esac
		if isroot "./$d"; then
			set -- "$@" "./$d"
			names="$names $d"
		fi
	done
fi
if [ $# = 0 ]; then
	echo 'kind=other'
else
	echo 'kind=go-build'
	echo "roots=$(printf '%s' "$names" | sed 's/^ //; s/ /,/g')"
fi
if [ "$mode" = ls ]; then exit 0; fi
# a volume that nothing has written to for removeafter goes whole: the host removes it (or says why it cannot), so nothing is
# deleted file by file here. A walk that failed says nothing about the time.
if [ "$removeafter" -gt 0 ] && [ "$walk" = 0 ] && [ "$lw" -gt 0 ] && [ $((now - lw)) -ge "$removeafter" ]; then
	echo 'verdict=remove'
	exit 0
fi
if [ $# = 0 ]; then
	if [ "$mode" = trim ]; then echo 'result=nothing'; fi
	exit 0
fi
# one pass over the build caches: how many bytes there are at each age in minutes, from which the cut follows
prof=$( { find "$@" -xdev -type f ! -name README ! -name trim.txt ! -path '*-d/*' -printf '%T@ %s\n'; echo "FJ_STATUS $?"; } | awk -v now="$now" -v maxage="$maxage" -v maxbytes="$maxbytes" -v minkeep="$minkeep" '
/^FJ_STATUS/ { st = $2; next }
{ a = now - $1; if (a < 0) a = 0; m = int(a / 60); n[m]++; b[m] += $2; tn++; tb += $2 }
END {
	maxbytes += 0
	cut = int(maxage / 60); low = int(minkeep / 60); keep = 0
	if (cut < low) cut = low
	for (m in b) if (m + 0 < cut) keep += b[m]
	while (keep > maxbytes && cut > low) { cut--; keep -= ((cut in b) ? b[cut] : 0) }
	tf = 0; tbytes = 0
	for (m in b) if (m + 0 >= cut) { tf += n[m]; tbytes += b[m] }
	printf "cache_files=%.0f\ncache_bytes=%.0f\ntrim_files=%.0f\ntrim_bytes=%.0f\ncut_age=%d\ncap_unmet=%s\nprofile_status=%s\n", tn, tb, tf, tbytes, cut * 60, (keep > maxbytes ? "yes" : "no"), st
}')
cut_age= trim_files= pst=
while IFS= read -r line; do
	case $line in
	cache_files=* | cache_bytes=* | trim_files=* | trim_bytes=* | cut_age=* | cap_unmet=*) printf '%s\n' "$line" ;;
	esac
	case $line in
	cut_age=*) cut_age=${line#cut_age=} ;;
	trim_files=*) trim_files=${line#trim_files=} ;;
	profile_status=*) pst=${line#profile_status=} ;;
	esac
done <<FJ_PROF
$prof
FJ_PROF
[ "$mode" = trim ] || exit 0
case $cut_age$trim_files in '' | *[!0-9]*) pst=x ;; esac
if [ "$walk" != 0 ] || [ "$pst" != 0 ]; then
	echo 'error=the walk of the volume failed: nothing was removed'
	echo 'result=failed'
	exit 0
fi
if [ "$trim_files" = 0 ]; then
	echo 'result=nothing'
	exit 0
fi
# the files that are still not newer than the cut are judged again as they are removed: one the go tool used since the
# profile has a new modification time and stays
cutoff=$((now - cut_age))
del=$( { find "$@" -xdev -type f ! -name README ! -name trim.txt ! -path '*-d/*' ! -newermt "@$cutoff" -delete -printf '%s\n'; echo "FJ_STATUS $?"; } | awk '/^FJ_STATUS/ { st = $2; next } { n++; b += $1 } END { printf "removed_files=%.0f\nremoved_bytes=%.0f\nremove_status=%s\n", n, b, st }')
rst=x
while IFS= read -r line; do
	case $line in
	removed_files=* | removed_bytes=*) printf '%s\n' "$line" ;;
	remove_status=*) rst=${line#remove_status=} ;;
	esac
done <<FJ_DEL
$del
FJ_DEL
if [ "$rst" = 0 ]; then
	echo 'result=trimmed'
else
	echo "error=find could not remove every file it chose (status $rst)"
	echo 'result=failed'
fi
FJ_WORKER
}

mode=$1
maxage=$2
maxbytes=$3
minkeep=$4
image=$5
only=$6
busykeep=${7:-0}
case $mode in
list | trim | ls | plan | prune) ;;
*) die 66 "bad mode: $mode" ;;
esac
isnum() {
	case $1 in
	'' | *[!0-9]* | 0[0-9]* | ?????????????????*) return 1 ;;
	esac
	return 0
}
isnum "$maxage" || die 66 "bad maximum age: $maxage"
isnum "$maxbytes" || die 66 "bad size cap: $maxbytes"
isnum "$minkeep" || die 66 "bad minimum to keep: $minkeep"
if [ "$minkeep" -lt 60 ] || [ "$maxage" -lt "$minkeep" ] || [ "$maxbytes" -lt 1 ]; then
	die 66 "the limits do not make sense: age $maxage, keep $minkeep, size $maxbytes"
fi
case $image in
'' | -* | *[!A-Za-z0-9_.:/@-]*) die 66 "bad image: $image" ;;
esac
case $only in
'') ;;
*[!A-Za-z0-9_.-]* | [-_.]*) die 66 "bad volume name: $only" ;;
esac
isnum "$busykeep" || die 66 "bad floor for volumes in use: $busykeep"
if [ "$busykeep" != 0 ]; then
	case $mode in
	plan | prune) ;;
	*) die 66 "a floor for volumes in use is for plan and prune only" ;;
	esac
	[ "$busykeep" -ge 21600 ] || die 66 "the floor for volumes in use is at least six hours: $busykeep"
fi
command -v docker >/dev/null 2>&1 || die 72 "docker is not installed on this host"

# a walk of the volumes must not slow the jobs and pipelines this host is for
if command -v renice >/dev/null 2>&1; then renice -n 19 -p $$ >/dev/null 2>&1; fi
if command -v ionice >/dev/null 2>&1; then ionice -c 2 -n 7 -p $$ >/dev/null 2>&1; fi

now=$(date +%s)
isnum "$now" || die 74 "this host's clock does not say the time: $now"

# dk LIMIT ARGS...: docker, cut off after LIMIT seconds when the host has timeout
dk() {
	lim=$1
	shift
	if command -v timeout >/dev/null 2>&1; then
		timeout "$lim" docker "$@"
	else
		docker "$@"
	fi
}

# the only modes that remove a volume ask the worker for a verdict on it
removeafter=0
case $mode in plan | prune) removeafter=$maxage ;; esac

worker=$(worker_text)

# run_worker VOLUME WORKERMODE MOUNTSUFFIX REMOVEAFTER [FLOOR]: walks the volume in a throw-away root container, with the youngest a file
# may be and still go (MIN_KEEP unless a floor is given); sets out and rc
run_worker() {
	out=$(dk 900 run --rm --pull never --network none --user 0 --cpus 1 --memory 512m --pids-limit 256 \
		--label fleet-job.gc=caches --entrypoint sh -v "$1:/v$3" "$image" -c "$worker" worker /v "$2" "$now" "$maxage" "$maxbytes" "${5:-$minkeep}" "$4" 2>&1)
	rc=$?
}

# getnum KEY: the whole number the worker printed for KEY; 0 when it printed none, or anything else
getnum() {
	num=$(printf '%s\n' "$out" | sed -n "s|^$1=||p" | head -n 1)
	case $num in '' | *[!0-9]*) num=0 ;; esac
	printf '%s\n' "$num"
}

# count_refs VOLUME: how many containers of any status refer to the volume, once the one this program ran on it has had a few
# seconds to be removed (docker run --rm can return before the daemon has finished removing the container); a docker that does
# not answer counts as one. Sets refs.
count_refs() {
	tries=0
	while :; do
		if ids=$(dk 30 ps -a -q --no-trunc --filter "volume=$1" 2>/dev/null); then
			refs=$(printf '%s\n' "$ids" | grep -c .)
		else
			refs=1
		fi
		if [ "$refs" = 0 ] || [ "$tries" -ge 5 ]; then return; fi
		tries=$((tries + 1))
		sleep 1
	done
}

dstate=ok
vols=$(dk 30 volume ls -q --filter name=fleet-job-cache- 2>/dev/null) || {
	dstate=down
	vols=
}
n_vol=0
printf 'fleet-job-caches/1\nmode=%s\nmax_age=%s\nmax_bytes=%s\nmin_keep=%s\nbusy_keep=%s\nhost_time=%s\n' "$mode" "$maxage" "$maxbytes" "$minkeep" "$busykeep" "$now"
for v in $(printf '%s\n' "$vols" | sort); do
	case $v in
	fleet-job-cache-?*) ;;
	*) continue ;;
	esac
	case $v in
	*[!A-Za-z0-9_.-]*) continue ;;
	esac
	if [ -n "$only" ] && [ "$v" != "fleet-job-cache-$only" ]; then continue; fi
	# the volume may have been removed since the list was taken: a container that mounts a name docker does not have makes docker
	# create it, empty, so a volume that is gone is not mounted
	if ! insp=$(dk 30 volume inspect "$v" 2>&1); then
		case $insp in
		*[Nn]o\ such\ volume*) ;;
		*) dstate=down ;;
		esac
		continue
	fi
	n_vol=$((n_vol + 1))
	state=idle
	containers=0
	if ids=$(dk 30 ps -a -q --no-trunc --filter "volume=$v" --filter status=running --filter status=created --filter status=restarting --filter status=paused 2>/dev/null); then
		containers=$(printf '%s\n' "$ids" | grep -c .)
		if [ "$containers" -gt 0 ]; then state=busy; fi
	else
		state=unknown
		dstate=down
	fi
	printf 'volume=%s\nstate=%s\ncontainers=%s\n' "$v" "$state" "$containers"
	# a volume that a container uses is left alone, unless plan and prune were given a floor (BUSY_KEEP): then its Go build cache is
	# trimmed (or planned) with nothing younger than the floor ever taken. Not a volume docker did not answer for.
	floor=$minkeep
	inuse=no
	if [ "$state" = busy ] && [ "$busykeep" != 0 ]; then
		inuse=yes
		floor=$busykeep
	fi
	if [ "$mode" = prune ] && [ "$state" != idle ] && [ "$inuse" != yes ]; then
		# nothing is done to this volume, so there is nothing to learn from it: a run that is on a timer does not walk the biggest
		# volume every time it is in use
		printf 'kind=unscanned\nresult=skipped\n'
		continue
	fi
	wmode=scan
	suffix=:ro
	case $mode in
	ls) wmode='ls' ;;
	trim | prune)
		if [ "$state" = idle ] || [ "$inuse" = yes ]; then
			wmode=trim
			suffix=
		fi
		;;
	esac
	# a volume that is in use is never asked for a verdict on removing it: plan only says what a trim would take from it
	ra=$removeafter
	if [ "$state" != idle ]; then ra=0; fi
	run_worker "$v" "$wmode" "$suffix" "$ra" "$floor"
	err=$(printf '%s\n' "$out" | grep -E "^error=[A-Za-z0-9 ._,:()/-]*\$" | head -n 1)
	res=$(printf '%s\n' "$out" | grep -E "^result=(trimmed|nothing|failed)\$" | head -n 1)
	if [ "$rc" != 0 ] && [ -z "$err" ]; then
		last=$(printf '%s\n' "$out" | tail -n 1 | tr -c 'A-Za-z0-9 ._,:()/-' ' ' | cut -c1-160)
		err="error=the container that walks the volume ended with status $rc: $last"
		res=result=failed
	fi
	verdict=
	if [ "$rc" = 0 ] && [ -z "$err" ] && printf '%s\n' "$out" | grep -q "^verdict=remove\$"; then
		verdict=remove
		# docker refuses to remove a volume that any container refers to, a stopped one too: then it is trimmed inside, like a
		# volume that is still in use by the clock
		count_refs "$v"
		if [ "$refs" != 0 ]; then
			verdict=
			run_worker "$v" "$wmode" "$suffix" 0 "$floor"
			err=$(printf '%s\n' "$out" | grep -E "^error=[A-Za-z0-9 ._,:()/-]*\$" | head -n 1)
			res=$(printf '%s\n' "$out" | grep -E "^result=(trimmed|nothing|failed)\$" | head -n 1)
			if [ "$rc" != 0 ] && [ -z "$err" ]; then
				last=$(printf '%s\n' "$out" | tail -n 1 | tr -c 'A-Za-z0-9 ._,:()/-' ' ' | cut -c1-160)
				err="error=the container that walks the volume ended with status $rc: $last"
				res=result=failed
			fi
		fi
	fi
	if [ "$inuse" = yes ] && [ -z "$err" ] && ! printf '%s\n' "$out" | grep -q "^kind=go-build\$"; then
		res=result=skipped # a volume in use that holds no Go build cache
	fi
	extra=
	action=
	if [ "$mode" = prune ] && [ "$verdict" = remove ]; then
		# removing a cache of tens of GiB and a million files takes a while
		if rmout=$(dk 600 volume rm "$v" 2>&1); then
			res=result=removed
			extra="removed_files=$(getnum files)
removed_bytes=$(getnum bytes)"
		else
			case $rmout in
			*"in use"*) res=result=skipped ;;
			*[Nn]o\ such\ volume*) res=result=nothing ;;
			*)
				err="error=docker could not remove the volume: $(printf '%s\n' "$rmout" | head -n 1 | tr -c 'A-Za-z0-9 ._,:()/-' ' ' | cut -c1-120)"
				res=result=failed
				;;
			esac
		fi
	fi
	if [ "$mode" = plan ]; then
		action=keep
		if [ "$state" != idle ] && { [ "$inuse" != yes ] || ! printf '%s\n' "$out" | grep -q "^kind=go-build\$"; }; then
			action=skip
		elif [ "$verdict" = remove ]; then
			action=remove
		elif printf '%s\n' "$out" | grep -q "^kind=go-build\$" && [ "$(getnum trim_files)" -gt 0 ]; then
			action=trim
		fi
	fi
	if [ "$mode" = trim ] && [ "$wmode" = scan ]; then
		res=result=skipped
	fi
	# a listing has no results: a volume that could not be walked has an error and no kind
	case $mode in list | ls | plan) res= ;; esac
	printf '%s\n' "$out" | grep -E "^(kind|roots|files|bytes|last_write|cache_files|cache_bytes|trim_files|trim_bytes|cut_age|cap_unmet|removed_files|removed_bytes)=[A-Za-z0-9._/,-]*\$"
	if [ -n "$err" ] && ! printf '%s\n' "$out" | grep -q '^kind='; then printf 'kind=unknown\n'; fi
	if [ -n "$extra" ]; then printf '%s\n' "$extra"; fi
	if [ -n "$err" ]; then printf '%s\n' "$err"; fi
	if [ -n "$action" ]; then printf 'action=%s\n' "$action"; fi
	if [ -n "$res" ]; then printf '%s\n' "$res"; fi
done
printf '%s\nvolumes=%s\ndocker=%s\n' '--summary--' "$n_vol" "$dstate"
