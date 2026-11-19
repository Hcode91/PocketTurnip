#!/usr/bin/env python3
"""Apply PocketTurnip changes to a Mesa source tree.

Usage: apply_patches.py <mesa_dir> [default_fps]

Each patch looks for an exact anchor in the Mesa source and fails loudly if
the anchor has moved, so a Mesa update can never silently skip a patch.
"""
import sys
from pathlib import Path

mesa = Path(sys.argv[1])
default_fps = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else 0


def patch(rel_path, old, new, name):
    path = mesa / rel_path
    text = path.read_text()
    if new in text:
        print(f"[skip] {name}: already applied")
        return
    if text.count(old) != 1:
        sys.exit(f"[FAIL] {name}: anchor not found exactly once in {rel_path}")
    path.write_text(text.replace(old, new))
    print(f"[ok]   {name}")


# 1. UBWC fix for newer Qualcomm gralloc (S23 / Android 14+).
#    Newer gralloc no longer writes the 'gmsm' magic word, so Mesa fails to
#    detect compressed (UBWC) buffers and the picture comes out garbled.
patch(
    "src/util/u_gralloc/u_gralloc_fallback.c",
    "if (hnd->handle->numInts >= 2 && hnd->handle->data[hnd->handle->numFds] == gmsm) {",
    "(void)gmsm; /* PocketTurnip: magic check disabled for newer QCOM gralloc */\n"
    "   if (hnd->handle->numInts >= 2) {",
    "UBWC gralloc fix",
)

# 2. Frame limiter, applied at vkQueuePresentKHR.
#    Cap is read (re-checked once a second, so it can change live) from:
#      - env var POCKETTURNIP_FPS            (Winlator / GameNative env settings)
#      - system property debug.pocketturnip.fps (setprop via LADB / Shizuku)
#      - otherwise the build-time default (0 = off)
LIMITER = r'''
/* ---- PocketTurnip frame limiter ---------------------------------------- */
#include <time.h>
#include <stdlib.h>
#ifdef __ANDROID__
#include <sys/system_properties.h>
#endif

#define PT_DEFAULT_FPS @DEFAULT_FPS@

static int
pt_read_fps_cap(void)
{
   const char *env = getenv("POCKETTURNIP_FPS");
   if (env && *env)
      return atoi(env);
#ifdef __ANDROID__
   char val[PROP_VALUE_MAX] = {0};
   if (__system_property_get("debug.pocketturnip.fps", val) > 0 && val[0])
      return atoi(val);
#endif
   return PT_DEFAULT_FPS;
}

static uint64_t
pt_now_ns(void)
{
   struct timespec ts;
   clock_gettime(CLOCK_MONOTONIC, &ts);
   return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void
pt_frame_limit(void)
{
   static simple_mtx_t lock = SIMPLE_MTX_INITIALIZER;
   static int fps = 0;
   static uint64_t next_check = 0, next_frame = 0;

   simple_mtx_lock(&lock);
   uint64_t now = pt_now_ns();
   if (now >= next_check) {
      fps = pt_read_fps_cap();
      next_check = now + 1000000000ull;
   }
   if (fps <= 0 || fps > 1000) {
      next_frame = 0;
      simple_mtx_unlock(&lock);
      return;
   }

   uint64_t interval = 1000000000ull / (uint64_t)fps;
   uint64_t wait = 0;
   if (next_frame > now) {
      wait = next_frame - now;
      if (wait > interval)
         wait = interval;
      next_frame += interval;
   } else {
      next_frame = now + interval;
   }
   simple_mtx_unlock(&lock);

   if (wait) {
      struct timespec ts = {
         .tv_sec = (time_t)(wait / 1000000000ull),
         .tv_nsec = (long)(wait % 1000000000ull),
      };
      nanosleep(&ts, NULL);
   }
}
/* ------------------------------------------------------------------------ */

VKAPI_ATTR VkResult VKAPI_CALL
wsi_QueuePresentKHR(VkQueue _queue, const VkPresentInfoKHR *pPresentInfo)
{
   pt_frame_limit();
'''.replace("@DEFAULT_FPS@", str(default_fps))

patch(
    "src/vulkan/wsi/wsi_common.c",
    "VKAPI_ATTR VkResult VKAPI_CALL\n"
    "wsi_QueuePresentKHR(VkQueue _queue, const VkPresentInfoKHR *pPresentInfo)\n"
    "{\n",
    LIMITER.lstrip("\n"),
    f"frame limiter (default {default_fps or 'off'})",
)

# simple_mtx is needed by the limiter; make sure wsi_common.c includes it.
src = mesa / "src/vulkan/wsi/wsi_common.c"
text = src.read_text()
if '#include "util/simple_mtx.h"' not in text:
    anchor = '#include "wsi_common_private.h"'
    if text.count(anchor) != 1:
        sys.exit("[FAIL] simple_mtx include: anchor not found")
    src.write_text(text.replace(anchor, anchor + '\n#include "util/simple_mtx.h"'))
    print("[ok]   simple_mtx include")
