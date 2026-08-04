/**
 * Note: When using the Node.JS APIs, the config file
 * doesn't apply. Instead, pass options directly to the APIs.
 *
 * All configuration options: https://remotion.dev/docs/config
 */

import { Config } from "@remotion/cli/config";
import { enableTailwind } from '@remotion/tailwind-v4';

Config.setRspack(true);
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.overrideBundlerConfig(enableTailwind);

// NOTE: bound assets (AssetBinding.asset_id) are arbitrary local files the
// user provided, not bundled under this project's public/ folder. Two
// approaches were tried and rejected before settling on the current one
// (remotion_engine.py stages assets through a short-lived local HTTP
// server and rewrites asset_id to an http://127.0.0.1 URL):
//   1. <OffthreadVideo src={absolutePath}> - its frame-extraction proxy
//      only accepts http(s):// sources; a raw path auto-converts to
//      file:// and gets rejected ("Can only download URLs starting with
//      http:// or https://").
//   2. <Video src={absolutePath}> with Config.setChromiumDisableWebSecurity(true)
//      - headless Chrome's own <video> element still refused file:// media
//      (net::ERR_UNKNOWN_URL_SCHEME) regardless of this setting, so it's
//      NOT enabled here - it doesn't fix the actual problem.
