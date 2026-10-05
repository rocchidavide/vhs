import { api } from './client'

/** Versions of VHS and its tools, and the latest release (GET /api/v1/system/info). */
export interface SystemInfo {
  vhs_version: string
  ytdlp_version: string
  deno_version: string
  /** The emergency option that installs the latest yt-dlp at every start. */
  ytdlp_auto_update: boolean
  latest_version: string | null
  latest_release_url: string | null
  /** True only with latest_version and latest_release_url set. */
  update_available: boolean
}

export const systemApi = {
  info: () => api.get<SystemInfo>('/system/info'),
}
