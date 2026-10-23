#!/usr/bin/env bash
# Remove the obsolete mount alias while retaining the verified HDD mount.
set -euo pipefail
export LC_ALL=C

if [[ $EUID -ne 0 ]]; then
  echo 'Run this cleanup through sudo or the Ubuntu administrator prompt.' >&2
  exit 1
fi

drive_uuid=B2261B36261AFAD5
preferred_path=/run/media/trijal/HDD
old_path=/run/media/trijal/HDD1

verify_preferred() {
  if [[ $(findmnt -rn -o UUID --mountpoint "$preferred_path" || true) != "$drive_uuid" ]]; then
    echo 'The expected drive is not mounted at HDD; nothing will be removed.' >&2
    exit 1
  fi
  local options
  options=$(findmnt -rn -o OPTIONS --mountpoint "$preferred_path")
  if [[ ,$options, != *,rw,* || ! -f "$preferred_path/FinalYearProjectByAstra/implementation_plan.md" ]]; then
    echo 'The HDD project is not writable and accessible; nothing will be removed.' >&2
    exit 1
  fi
}

verify_preferred
if [[ -L "$old_path" ]]; then
  echo 'HDD1 is a symlink rather than the expected mount alias; cleanup stopped.' >&2
  exit 1
fi

if findmnt -rn --mountpoint "$old_path" >/dev/null; then
  if [[ $(findmnt -rn -o UUID --mountpoint "$old_path") != "$drive_uuid" ]]; then
    echo 'HDD1 refers to another filesystem; cleanup stopped.' >&2
    exit 1
  fi
  mapfile -t mounts < <(findmnt -rn -R -o TARGET --mountpoint "$old_path")
  if (( ${#mounts[@]} != 1 )); then
    echo 'HDD1 contains additional mounts; cleanup stopped.' >&2
    exit 1
  fi

  # Isolate this alias from shared-mount propagation before detaching it.
  mount --make-rprivate "$old_path"
  verify_preferred
  if ! unmount_error=$(umount -- "$old_path" 2>&1); then
    if [[ $unmount_error != *'target is busy'* && $unmount_error != *'Device or resource busy'* ]]; then
      echo "$unmount_error" >&2
      exit 1
    fi
    # Retain outstanding file handles; HDD continues to mount the filesystem.
    verify_preferred
    umount --lazy -- "$old_path"
    echo 'Detached the old alias while preserving its outstanding file handles.'
  fi
fi

verify_preferred
if findmnt -rn --mountpoint "$old_path" >/dev/null; then
  echo 'HDD1 is still mounted; its directory was left in place.' >&2
  exit 1
fi

# Only remove an empty, unmounted directory. Never recurse into drive contents.
if [[ -d "$old_path" ]]; then
  rmdir -- "$old_path"
fi
if [[ -e "$old_path" ]]; then
  echo 'HDD1 still exists; inspect it before any further cleanup.' >&2
  exit 1
fi
findmnt --source "UUID=$drive_uuid" --output TARGET,SOURCE,FSTYPE,OPTIONS
echo 'HDD1 removed. The project remains at /run/media/trijal/HDD/FinalYearProjectByAstra.'
