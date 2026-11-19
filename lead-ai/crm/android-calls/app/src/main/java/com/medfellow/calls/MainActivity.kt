package com.medfellow.calls

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.format.DateFormat
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.Date
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/** One screen: paste the pairing code from the CRM, allow call-log access, done. */
class MainActivity : Activity() {

    private lateinit var prefs: Prefs
    private lateinit var status: TextView
    private lateinit var server: EditText
    private lateinit var token: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)

        val pad = (16 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad * 2, pad, pad)
        }
        fun label(t: String, size: Float = 14f) = TextView(this).apply {
            text = t; textSize = size; setPadding(0, pad / 2, 0, pad / 4)
        }

        root.addView(label("MedFellow Calls", 24f))
        root.addView(label("Sends your call counts (type, number, time, duration) to the CRM. No recordings, no contacts, no messages."))

        root.addView(label("CRM address"))
        server = EditText(this).apply { setText(prefs.server); setSingleLine() }
        root.addView(server)

        root.addView(label("Pairing code (from CRM > Calls > Pair a phone)"))
        token = EditText(this).apply { setText(prefs.token); setSingleLine() }
        root.addView(token)

        val save = Button(this).apply { text = "Save and sync now" }
        root.addView(save)

        status = TextView(this).apply { gravity = Gravity.START; setPadding(0, pad, 0, 0) }
        root.addView(status)
        setContentView(root)

        save.setOnClickListener {
            prefs.server = server.text.toString()
            prefs.token = token.text.toString()
            if (checkSelfPermission(Manifest.permission.READ_CALL_LOG) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(arrayOf(Manifest.permission.READ_CALL_LOG), 1)
            } else {
                startSync()
            }
        }
        render("")
    }

    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, perms, results)
        if (results.firstOrNull() == PackageManager.PERMISSION_GRANTED) startSync()
        else render("Call log permission is needed to count calls.")
    }

    private fun startSync() {
        // Repeats about every 15 minutes (Android's minimum) whenever the phone is online.
        val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(this)
            .enqueueUniquePeriodicWork("calls-sync", ExistingPeriodicWorkPolicy.UPDATE, request)
        render("Syncing...")
        thread {
            val r = SyncWorker.syncNow(applicationContext)
            runOnUiThread { render(r.message) }
        }
    }

    override fun onResume() {
        super.onResume()
        render("")
    }

    private fun render(message: String) {
        val last = prefs.lastSyncMillis
        val lastText = if (last > 0) DateFormat.format("dd MMM, h:mm a", Date(last)).toString() else "never"
        val today = SyncWorker.todayStats(this)
        val todayText = if (today == null) "" else
            "Today on this phone: ${today.made} made, ${today.connected} connected, ${today.received} received, ${today.missed} missed"
        val paired = if (prefs.token.isBlank()) "Not paired yet. Get a code from CRM > Calls > Pair a phone." else "Paired"
        status.text = listOf(
            paired, message.ifBlank { prefs.lastMessage }, "Last successful sync: $lastText", todayText,
            "Tip: set this app's battery to \"No restrictions\" so syncing keeps running."
        ).filter { it.isNotBlank() }.joinToString("\n\n")
    }
}
