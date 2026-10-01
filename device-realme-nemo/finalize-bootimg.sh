#!/bin/sh
# SPDX-License-Identifier: MIT
# boot-deploy calls this after mkbootimg, passing the initramfs path.
set -eu
boot_image="$(dirname "$1")/boot.img"
test -s "$boot_image"
avbtool add_hash_footer --image "$boot_image" --partition_name boot \
	--partition_size 33554432 --algorithm NONE
avbtool verify_image --image "$boot_image"
