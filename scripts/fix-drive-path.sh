#!/usr/bin/env bash
# Restore the original HDD path and configure a UUID-based automount.
set -euo pipefail
umask 077

if [[ $EUID -ne 0 ]]; then
  echo 'Run this repair through sudo or the Ubuntu administrator prompt.' >&2
  exit 1
fi

drive_uuid=B2261B36261AFAD5
preferred_path=/run/media/trijal/HDD
active_path=
for candidate_path in "$preferred_path" /run/media/trijal/HDD1; do
  if [[ $(findmnt -rn -o UUID --mountpoint "$candidate_path" || true) == "$drive_uuid" ]]; then
    active_path=$candidate_path
    break
  fi
done
if [[ -z $active_path ]]; then
  echo 'The expected HDD is not mounted; nothing changed.' >&2
  exit 1
fi
mount_options=$(findmnt -rn -o OPTIONS --mountpoint "$active_path")
if [[ ,$mount_options, != *,rw,* ]]; then
  echo 'The HDD is read-only; repair its filesystem before applying this configuration.' >&2
  exit 1
fi
if [[ $(findmnt -rn -o FSTYPE --mountpoint "$active_path") != ntfs3 ]]; then
  echo 'The HDD is using a different driver; nothing changed.' >&2
  exit 1
fi
project_path="$active_path/FinalYearProjectByAstra"
if [[ ! -f "$project_path/implementation_plan.md" ]]; then
  echo 'The expected project is missing; nothing changed.' >&2
  exit 1
fi
if [[ -L "$preferred_path" || ! -d "$preferred_path" ]]; then
  echo 'HDD must be an existing directory for this repair; nothing changed.' >&2
  exit 1
fi
already_mounted=false
if findmnt -rn --mountpoint "$preferred_path" >/dev/null; then
  if [[ $(findmnt -rn -o UUID --mountpoint "$preferred_path") != "$drive_uuid" ]]; then
    echo 'Another filesystem is mounted at HDD; nothing changed.' >&2
    exit 1
  fi
  already_mounted=true
fi

backup_path="$project_path/.runtime/mount-repair/$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$backup_path"
cp --preserve=mode,timestamps /etc/fstab "$backup_path/fstab.before"

/usr/bin/python3 - "$backup_path/fstab.candidate" <<'PY_FSTAB'
from pathlib import Path
import os
import sys

source = Path('/etc/fstab').read_text()
uuid = 'UUID=B2261B36261AFAD5'
target = '/run/media/trijal/HDD'
expected = {'rw', 'nofail', 'x-systemd.automount', 'uid=1000', 'gid=1000', 'acl', 'nosuid', 'nodev'}
found = False
for line in source.splitlines():
    parts = line.split()
    if not parts or parts[0].startswith('#'):
        continue
    if len(parts) < 4:
        raise SystemExit('An existing fstab entry is malformed; nothing changed.')
    if parts[1] == target:
        if found or parts[0] != uuid:
            raise SystemExit('HDD has a conflicting fstab entry; nothing changed.')
        if parts[2] != 'ntfs3' or not expected.issubset(set(parts[3].split(','))):
            raise SystemExit('HDD has a custom fstab configuration; nothing changed.')
        found = True
    elif parts[0] == uuid:
        raise SystemExit('This drive already has another fstab mount point; nothing changed.')
if not found:
    source = source.rstrip() + '\n\n# Stable HDD path; automount when accessed, allow boot without the USB drive.\n'
    source += f'{uuid} {target} ntfs3 rw,nofail,x-systemd.automount,x-systemd.device-timeout=10s,uid=1000,gid=1000,acl,nosuid,nodev 0 0\n'
with Path(sys.argv[1]).open('w') as stream:
    stream.write(source)
    stream.flush()
    os.fsync(stream.fileno())
PY_FSTAB

findmnt --verify --tab-file "$backup_path/fstab.candidate"
if [[ $already_mounted == false ]]; then
  # Existing HDD1 applications keep their paths and open descriptors.
  # The stale directories underneath HDD are preserved, not deleted.
  mount --bind "$active_path" "$preferred_path"
fi
if [[ ! -f "$preferred_path/FinalYearProjectByAstra/implementation_plan.md" ]]; then
  echo 'The original project path is not visible; fstab was left unchanged.' >&2
  exit 1
fi

if ! cmp -s /etc/fstab "$backup_path/fstab.candidate"; then
  /usr/bin/python3 - "$backup_path/fstab.candidate" "$backup_path/fstab.before" <<'PY_REPLACE'
from pathlib import Path
import os
import stat
import sys
import tempfile

target = Path('/etc/fstab')
if target.read_bytes() != Path(sys.argv[2]).read_bytes():
    raise SystemExit('fstab changed during repair; its new contents were preserved.')
metadata = target.stat()
fd, temporary = tempfile.mkstemp(prefix='.fstab.waterwise-', dir='/etc')
try:
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
        os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
        stream.write(Path(sys.argv[1]).read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    directory = os.open('/etc', os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
finally:
    Path(temporary).unlink(missing_ok=True)
PY_REPLACE
fi
systemctl daemon-reload
findmnt --verify --tab-file /etc/fstab
if [[ $(systemctl show run-media-trijal-HDD.automount -p LoadState --value) != loaded ]]; then
  echo 'The mount path was restored, but the generated automount unit needs inspection.' >&2
  exit 1
fi
chown -R 1000:1000 "$backup_path"
chmod 700 "$backup_path"
chmod 600 "$backup_path"/*
findmnt --mountpoint "$preferred_path" --output TARGET,SOURCE,FSTYPE,OPTIONS
echo "Original project path restored: $preferred_path/FinalYearProjectByAstra"
echo 'The UUID-based HDD automount is configured for future boots.'
echo "Previous fstab saved at: $backup_path/fstab.before"
