# Fixing Realme 6 (nemo) AVB Bootloop

Realme and OPPO devices enforce Android Verified Boot (AVB). If the flashed `boot.img` does not have a valid AVB signature or hash footer, the bootloader will reject it, leading to a bootloop or immediate fallback to Fastboot/Recovery.

## The Problem
When building postmarketOS, `pmbootstrap` (via `mkinitfs` and `boot-deploy`) generates a standard `boot.img`. However, it does not automatically attach the AVB footer required by the Realme 6 bootloader. 

The stock or custom ROM `boot.img` for this device uses AVB but with the verification algorithm set to `NONE`. The `vbmeta.img` also has verification disabled (Flags: 3). Therefore, we do not need cryptographic signing, but we *do* need the structural AVB footer appended to the `boot.img` so the bootloader recognizes it as a valid image.

## How to Fix It

To fix this, we use `avbtool` to append an empty hash footer (`Algorithm: NONE`) to the generated postmarketOS `boot.img`. 

**Crucially, the image size must exactly match the expected partition size or rollback index size.**

### Step-by-Step Guide

1. **Locate your postmarketOS `boot.img`**
   If you are using a chroot or local build, locate the generated `boot.img`. For example:
   `/home/dazai/.local/var/pmbootstrap/chroot_rootfs_realme-nemo/boot/boot.img`

2. **Determine the `boot` partition size**
   For the Realme 6 (RMX2001), the `boot` partition size is exactly `33554432` bytes (32 MB).

3. **Add the AVB Hash Footer**
   Run `avbtool` to add the footer. `avbtool` will automatically pad the file to the specified `--partition_size` and embed the AVB metadata at the end.

   ```bash
   # Define paths and sizes
   PMOS_BOOT="/path/to/pmos/boot.img"
   OUTPUT_BOOT="pmos_boot_avb.img"
   PARTITION_SIZE=33554432

   # Copy the original boot.img
   cp "$PMOS_BOOT" "$OUTPUT_BOOT"

   # Append the AVB footer
   avbtool add_hash_footer \
     --image "$OUTPUT_BOOT" \
     --partition_name boot \
     --partition_size $PARTITION_SIZE \
     --algorithm NONE \
     --salt $(openssl rand -hex 32)
   ```

4. **Verify the Footer**
   You can verify the footer was added correctly by running:
   ```bash
   avbtool info_image --image pmos_boot_avb.img
   ```
   You should see output indicating:
   - `Algorithm: NONE`
   - `Image size: 33554432 bytes`
   - A valid VBMeta offset.

5. **Flash the AVB-patched Image**
   Reboot your device to Fastboot mode and flash the patched image:
   ```bash
   fastboot flash boot pmos_boot_avb.img
   fastboot reboot
   ```

Once flashed, the Realme 6 bootloader will accept the image and proceed to boot the postmarketOS kernel and initramfs.
