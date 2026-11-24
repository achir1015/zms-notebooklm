package com.achir.zmsnotebooklm;

import android.app.DownloadManager;
import android.content.BroadcastReceiver;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.Locale;

/**
 * 網頁呼叫的 Android 功能（window.ZMSAndroid）：
 * 存檔（PowerPoint、Word、圖片、網頁、ZIP 存到「下載／NotebookLM簡報」並開分享面板，可傳給 LINE、雲端硬碟、電腦）、
 * 用手機語音朗讀（WebView 沒有 speechSynthesis）、下載並安裝新版、用瀏覽器開網址。JavaScript 介面在背景執行緒執行；回傳值一律是 JSON 字串。
 */
final class Bridge {
    static final String REPO = "achir1015/zms-notebooklm";
    static final String FOLDER = "NotebookLM簡報";

    final MainActivity a;
    volatile JSONObject updateStatus = st("idle", 0);

    TextToSpeech tts;
    volatile boolean ttsReady = false;

    Bridge(MainActivity a) {
        this.a = a;
        // 手機內建語音：優先臺灣華語，其次華語
        tts = new TextToSpeech(a.getApplicationContext(), status -> {
            if (status != TextToSpeech.SUCCESS) return;
            for (Locale l : new Locale[]{Locale.TAIWAN, Locale.TRADITIONAL_CHINESE, Locale.CHINESE}) {
                int r = tts.isLanguageAvailable(l);
                if (r >= TextToSpeech.LANG_AVAILABLE) { tts.setLanguage(l); ttsReady = true; break; }
            }
        });
    }

    /** 朗讀講者備註 */
    @JavascriptInterface
    public boolean ttsSpeak(String text) {
        if (!ttsReady) { a.runOnUiThread(() -> Toast.makeText(a, "手機沒有中文語音，請到設定安裝「文字轉語音」的中文資料", Toast.LENGTH_LONG).show()); return false; }
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "nb");
        return true;
    }

    @JavascriptInterface
    public void ttsStop() { if (tts != null) tts.stop(); }

    void shutdown() { if (tts != null) { tts.stop(); tts.shutdown(); } }

    static JSONObject st(String state, int pct) {
        JSONObject o = new JSONObject();
        try { o.put("state", state); o.put("pct", pct); } catch (Exception ignored) { }
        return o;
    }
    static String ok(Object... kv) {
        JSONObject o = new JSONObject();
        try { o.put("status", "ok"); for (int i = 0; i + 1 < kv.length; i += 2) o.put((String) kv[i], kv[i + 1]); } catch (Exception ignored) { }
        return o.toString();
    }
    static String err(Exception e) {
        JSONObject o = new JSONObject();
        try { o.put("status", "error"); o.put("message", String.valueOf(e.getMessage())); } catch (Exception ignored) { }
        return o.toString();
    }

    static String version(Context c) {
        try { return c.getPackageManager().getPackageInfo(c.getPackageName(), 0).versionName; } catch (Exception e) { return "0"; }
    }

    @JavascriptInterface
    public String appInfo() { return ok("name", a.getString(R.string.app_name), "version", version(a), "platform", "android", "sdk", Build.VERSION.SDK_INT, "model", Build.MODEL); }

    @JavascriptInterface
    public String getVersion() { return version(a); }

    static String mimeOf(String name) {
        String n = name.toLowerCase();
        if (n.endsWith(".pptx")) return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
        if (n.endsWith(".docx")) return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
        if (n.endsWith(".png")) return "image/png";
        if (n.endsWith(".html")) return "text/html";
        if (n.endsWith(".zip")) return "application/zip";
        if (n.endsWith(".txt") || n.endsWith(".md")) return "text/plain";
        if (n.endsWith(".json")) return "application/json";
        return "application/octet-stream";
    }

    /** 存到「下載／NotebookLM簡報」，然後開分享面板 */
    @JavascriptInterface
    public String saveFile(String name, String b64) {
        try {
            name = new File(name).getName();
            if (name.isEmpty()) name = "成品.zip";
            byte[] data = Base64.decode(b64, Base64.DEFAULT);
            String mime = mimeOf(name);
            Uri uri;
            if (Build.VERSION.SDK_INT >= 29) {
                ContentResolver cr = a.getContentResolver();
                ContentValues v = new ContentValues();
                v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                v.put(MediaStore.MediaColumns.MIME_TYPE, mime);
                v.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/" + FOLDER);
                uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                if (uri == null) throw new Exception("無法建立檔案");
                try (OutputStream out = cr.openOutputStream(uri)) { out.write(data); }
            } else {
                File dir = new File(a.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), FOLDER);
                dir.mkdirs();
                File f = new File(dir, name);
                try (FileOutputStream out = new FileOutputStream(f)) { out.write(data); }
                uri = null;
            }
            final String shown = name;
            final Uri share = uri;
            a.runOnUiThread(() -> {
                Toast.makeText(a, "已存到「下載／" + FOLDER + "／" + shown + "」", Toast.LENGTH_LONG).show();
                if (share != null) {
                    Intent s = new Intent(Intent.ACTION_SEND).setType(mimeOf(shown)).putExtra(Intent.EXTRA_STREAM, share)
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    try { a.startActivity(Intent.createChooser(s, "分享 " + shown)); } catch (Exception ignored) { }
                }
            });
            return ok("name", name);
        } catch (Exception e) { return err(e); }
    }

    /** 只允許開啟本專案與 NotebookLM 的網址 */
    @JavascriptInterface
    public boolean openUrl(String url) {
        if (!(url.startsWith("https://github.com/achir1015/") || url.startsWith("https://achir1015.github.io/")
                || url.startsWith("https://notebook.google.com/") || url.startsWith("https://notebooklm.google.com/"))) return false;
        try { a.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); return true; } catch (Exception e) { return false; }
    }

    // ---- 版本更新：下載 GitHub Release 的 .apk 並交給系統安裝 ----
    @JavascriptInterface
    public String updateStatus() { return updateStatus.toString(); }

    @JavascriptInterface
    public String installUpdate(final String url, final String ver) {
        if (!url.startsWith("https://github.com/" + REPO + "/releases/download/")) return err(new Exception("bad url"));
        if (!a.getPackageManager().canRequestPackageInstalls()) {   // Android 8+：先允許本 App 安裝未知應用程式
            a.runOnUiThread(() -> {
                try { a.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + a.getPackageName()))); } catch (Exception ignored) { }
            });
            updateStatus = st("permission", 0);
            return ok();
        }
        final DownloadManager dm = (DownloadManager) a.getSystemService(Context.DOWNLOAD_SERVICE);
        String file = "ZMSNotebookLM-" + ver + ".apk";
        File old = new File(a.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), file);
        if (old.exists()) old.delete();
        DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url))
                .setTitle(a.getString(R.string.app_name) + " v" + ver)
                .setMimeType("application/vnd.android.package-archive")
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalFilesDir(a, Environment.DIRECTORY_DOWNLOADS, file);
        final long id = dm.enqueue(req);
        updateStatus = st("downloading", 0);
        final Context app = a.getApplicationContext();
        BroadcastReceiver done = new BroadcastReceiver() {
            public void onReceive(Context c, Intent i) {
                if (i.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1) != id) return;
                try { app.unregisterReceiver(this); } catch (Exception ignored) { }
                Uri uri = dm.getUriForDownloadedFile(id);
                if (uri == null) { updateStatus = st("error", 0); return; }
                updateStatus = st("launching", 100);
                Intent v = new Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
                try { app.startActivity(v); } catch (Exception e) { updateStatus = st("error", 0); }
            }
        };
        IntentFilter f = new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        if (Build.VERSION.SDK_INT >= 33) app.registerReceiver(done, f, Context.RECEIVER_EXPORTED);
        else app.registerReceiver(done, f);
        new Thread(() -> {
            while ("downloading".equals(updateStatus.optString("state"))) {
                try (Cursor cur = dm.query(new DownloadManager.Query().setFilterById(id))) {
                    if (cur != null && cur.moveToFirst()) {
                        long got = cur.getLong(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                        long all = cur.getLong(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES));
                        int s = cur.getInt(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                        if (s == DownloadManager.STATUS_FAILED) { updateStatus = st("error", 0); break; }
                        if (all > 0) updateStatus = st("downloading", (int) (got * 100 / all));
                    }
                } catch (Exception ignored) { }
                try { Thread.sleep(500); } catch (InterruptedException e) { break; }
            }
        }).start();
        return ok();
    }

}
