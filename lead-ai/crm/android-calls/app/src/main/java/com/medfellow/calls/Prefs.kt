package com.medfellow.calls

import android.content.Context

/** Server address, pairing token and the "synced up to" marker, kept on the phone. */
class Prefs(ctx: Context) {
    private val p = ctx.getSharedPreferences("medfellow_calls", Context.MODE_PRIVATE)

    var server: String
        get() = p.getString("server", DEFAULT_SERVER) ?: DEFAULT_SERVER
        set(v) = p.edit().putString("server", v.trim()).apply()

    var token: String
        get() = p.getString("token", "") ?: ""
        set(v) = p.edit().putString("token", v.trim()).apply()

    var cursor: Long
        get() = p.getLong("cursor", 0L)
        set(v) = p.edit().putLong("cursor", v).apply()

    var lastSyncMillis: Long
        get() = p.getLong("last_sync", 0L)
        set(v) = p.edit().putLong("last_sync", v).apply()

    companion object {
        // The CRM's API address (same host the web app calls). Editable on the pairing screen.
        const val DEFAULT_SERVER = "https://medfellow-crm-api.onrender.com"
    }
}
