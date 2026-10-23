# Drive path repair

Completed on **2 October 2026**. The project is available at:

```text
/run/media/trijal/HDD/FinalYearProjectByAstra
```

An older Docker stack recreated an empty, root-owned directory at `/run/media/trijal/HDD` before the external drive mounted. The desktop mounter selected `HDD1` because the original path was occupied. A subsequent NTFS file-table mirror mismatch also prevented writable mounting. After the Windows disk check, Ubuntu mounted the drive read/write again.

The initial repair bound the existing drive onto `HDD`, preserving open applications while the paths were updated. The obsolete `HDD1` mount and its empty mount-point directory have since been removed. Ubuntu now reports only `/run/media/trijal/HDD` for this drive. A UUID-based systemd automount is configured in `/etc/fstab` for future boots:

```fstab
UUID=B2261B36261AFAD5 /run/media/trijal/HDD ntfs3 rw,nofail,x-systemd.automount,x-systemd.device-timeout=10s,uid=1000,gid=1000,acl,nosuid,nodev 0 0
```

The automount starts before Docker and mounts the drive when its path is accessed. The `nofail` option allows booting without the external drive. Use `HDD` in terminal commands and bookmarks. The Python editable package registration was refreshed to use the restored path.

The previous fstab is saved inside this project at:

```text
.runtime/mount-repair/20261002-122700-19377/fstab.before
```

Verification passed for the drive UUID, writable access through the restored path, generated automount configuration, backend imports, frontend JavaScript syntax and the saved demo database's quick integrity check. After cleanup, both the mount table and Ubuntu's disk service report only `HDD`, the `HDD1` path is absent, and the running dashboard's backend remains healthy. Boot ordering and generated unit files were checked; the computer was not rebooted as part of verification.

The helper used for this repair is [fix-drive-path.sh](../scripts/fix-drive-path.sh). It checks the drive identity, driver and write access, preserves the previous fstab, validates the proposed configuration and replaces fstab atomically.

The alias cleanup helper is [remove-hdd1-alias.sh](../scripts/remove-hdd1-alias.sh). It verifies that `HDD` remains writable, isolates the obsolete alias from mount propagation, detaches that alias and removes only its empty mount-point directory.

See [getting started](getting-started.md) for running the project.
