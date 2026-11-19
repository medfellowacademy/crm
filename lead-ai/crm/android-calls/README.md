# MedFellow Calls (Android)

Counts calls for the CRM's **Calls** page. Reads the phone's call log (type, number, time, duration)
and sends it every ~15 minutes. No audio, contacts or messages.

## Build
1. Install Android Studio, choose **Open** and pick this `android-calls` folder (it creates the Gradle wrapper).
2. **Build > Build APK(s)**. Copy `app/build/outputs/apk/debug/app-debug.apk` to the counselors' phones and install it
   (allow "install unknown apps").

## Pair a phone
1. In the CRM open **Calls > Pair a phone**, copy the one-time code.
2. In the app paste the code, tap **Save and sync now**, allow **Call log**.

Notes: Google Play restricts call-log apps, so distribute the APK directly. On some phones (Xiaomi, Oppo, Vivo)
set the app's battery option to "No restrictions" so syncing keeps running in the background.
