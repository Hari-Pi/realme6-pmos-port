# Fixing the "Cmdline Overflow" Bootloop on Realme 6 (nemo)

During the process of porting postmarketOS to the Realme 6 (MT6785), we encountered a critical boot error that caused the device to immediately panic or bootloop with a "cmdline overflow" exception.

## The Cause: MediaTek Bootloader Limits
The core issue stems from the MediaTek bootloader implemented on the Realme 6. This bootloader has a very strict, hardcoded limit on the maximum length of the kernel command line (`cmdline`) that it can pass to the kernel during boot.

In a standard postmarketOS installation, `pmbootstrap` and `boot-deploy` generate the `/etc/fstab` and the kernel cmdline using partition UUIDs (Universally Unique Identifiers) by default. UUIDs are long, 36-character alphanumeric strings (e.g., `UUID=12345678-1234-1234-1234-123456789abc`). 

When postmarketOS adds both the boot partition UUID and the root partition UUID to the kernel parameters (e.g., `pmos_root_uuid=... pmos_boot_uuid=...`), the total command line length easily exceeds **176 characters**. The MediaTek bootloader cannot handle a command line of this length, truncates it or overflows its buffer, and immediately aborts the boot process.

## The Solution: Switching to Partition Labels
To bypass the bootloader's length restriction, we needed to drastically shorten the kernel command line. We achieved this by abandoning long UUIDs in favor of shorter filesystem labels.

### Steps Taken to Fix:
1. **Patching `pmbootstrap` Configuration:**
   We modified the postmarketOS installation generation step so that it uses standard block device labels instead of UUIDs for mounting the core partitions.

2. **Using Short Labels:**
   Instead of `pmos_root_uuid=...`, we configured the system to identify partitions via labels:
   - Root Partition: `LABEL=pmOS_root`
   - Boot Partition: `LABEL=pmOS_boot`

3. **Shortening the Cmdline:**
   By stripping out the long UUID references, we reduced the total length of the kernel command line from **176 characters** down to just **92 characters**. This easily fits within the MediaTek bootloader's strict limits.

4. **Initramfs Fallback:**
   The postmarketOS `initramfs` (`init_functions.sh`) is already designed to automatically fall back to scanning for block devices via their labels (`blkid --label pmOS_root`) if the UUID variables are absent from the kernel command line. Because we formatted the F2FS partition with the label `pmOS_root`, the `initramfs` successfully finds the partition during boot.

By implementing this label-based mounting strategy, the cmdline overflow panic was entirely resolved, allowing the kernel to initialize and pass control to the `initramfs`.
