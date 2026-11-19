package com.medfellow.calls

import android.content.Context
import android.provider.CallLog
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** Reads calls newer than the last successful sync and pushes them to the CRM. */
class SyncWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val result = syncNow(applicationContext)
        Prefs(applicationContext).lastMessage = result.message
        return if (result.ok) Result.success() else if (result.retry) Result.retry() else Result.failure()
    }

    data class Outcome(val ok: Boolean, val retry: Boolean, val message: String)

    companion object {
        private const val BATCH = 400
        private const val FIRST_SYNC_DAYS = 7L

        fun syncNow(ctx: Context): Outcome {
            val prefs = Prefs(ctx)
            val server = prefs.server
            val token = prefs.token
            if (server.isBlank() || token.isBlank()) return Outcome(false, false, "Not paired yet")
            if (ctx.checkSelfPermission(android.Manifest.permission.READ_CALL_LOG)
                != android.content.pm.PackageManager.PERMISSION_GRANTED
            ) return Outcome(false, false, "Call log permission is off")

            val since = if (prefs.cursor > 0) prefs.cursor
            else System.currentTimeMillis() - FIRST_SYNC_DAYS * 24 * 3600 * 1000
            val calls = readCalls(ctx, since)
            if (calls.isEmpty()) return Outcome(true, false, "Up to date")

            var newest = prefs.cursor
            var sent = 0
            for (chunk in calls.chunked(BATCH)) {
                val code = push(server, token, chunk)
                if (code == 401) return Outcome(false, false, "This phone was removed in the CRM. Pair again.")
                if (code !in 200..299) return Outcome(false, true, "Server error $code")
                sent += chunk.size
                newest = maxOf(newest, chunk.maxOf { it.date })
                prefs.cursor = newest            // advance only after the server accepted the batch
            }
            prefs.lastSyncMillis = System.currentTimeMillis()
            return Outcome(true, false, "Sent $sent calls")
        }

        /** Today's totals as this phone sees them (same 5-second rule as the CRM), shown on the app screen. */
        data class Today(val made: Int, val connected: Int, val received: Int, val missed: Int)

        fun todayStats(ctx: Context): Today? {
            if (ctx.checkSelfPermission(android.Manifest.permission.READ_CALL_LOG)
                != android.content.pm.PackageManager.PERMISSION_GRANTED
            ) return null
            val midnight = java.util.Calendar.getInstance().apply {
                set(java.util.Calendar.HOUR_OF_DAY, 0); set(java.util.Calendar.MINUTE, 0)
                set(java.util.Calendar.SECOND, 0); set(java.util.Calendar.MILLISECOND, 0)
            }.timeInMillis
            var made = 0; var connected = 0; var received = 0; var missed = 0
            for (c in readCalls(ctx, midnight - 1)) {
                when (c.direction) {
                    "outgoing" -> { made++; if (c.duration >= MIN_CONNECTED) connected++ }
                    "incoming" -> if (c.duration >= MIN_CONNECTED) received++ else missed++
                    else -> missed++
                }
            }
            return Today(made, connected, received, missed)
        }

        private const val MIN_CONNECTED = 5

        private data class Call(val phone: String, val direction: String, val duration: Int, val date: Long)

        private fun readCalls(ctx: Context, since: Long): List<Call> {
            val out = ArrayList<Call>()
            val cols = arrayOf(
                CallLog.Calls.NUMBER, CallLog.Calls.TYPE, CallLog.Calls.DURATION, CallLog.Calls.DATE
            )
            ctx.contentResolver.query(
                CallLog.Calls.CONTENT_URI, cols, "${CallLog.Calls.DATE} > ?",
                arrayOf(since.toString()), "${CallLog.Calls.DATE} ASC"
            )?.use { c ->
                while (c.moveToNext()) {
                    val direction = when (c.getInt(1)) {
                        CallLog.Calls.OUTGOING_TYPE -> "outgoing"
                        CallLog.Calls.INCOMING_TYPE -> "incoming"
                        CallLog.Calls.MISSED_TYPE -> "missed"
                        CallLog.Calls.REJECTED_TYPE -> "rejected"
                        else -> continue          // voicemail, blocked, etc. are not conversations
                    }
                    val number = c.getString(0)?.trim().orEmpty()
                    if (number.isEmpty()) continue
                    out.add(Call(number, direction, c.getInt(2), c.getLong(3)))
                }
            }
            return out
        }

        private fun push(server: String, token: String, calls: List<Call>): Int {
            val arr = JSONArray()
            calls.forEach {
                arr.put(
                    JSONObject()
                        .put("phone", it.phone).put("direction", it.direction)
                        .put("duration_sec", it.duration).put("started_at", it.date)
                )
            }
            val body = JSONObject().put("calls", arr).toString().toByteArray()
            val conn = URL(server.trimEnd('/') + "/api/calls/sync").openConnection() as HttpURLConnection
            return try {
                conn.requestMethod = "POST"
                conn.connectTimeout = 15000
                conn.readTimeout = 30000
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("X-Device-Token", token)
                conn.outputStream.use { it.write(body) }
                conn.responseCode
            } catch (e: Exception) {
                -1
            } finally {
                conn.disconnect()
            }
        }
    }
}
