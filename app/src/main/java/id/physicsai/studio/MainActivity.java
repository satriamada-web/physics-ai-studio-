package id.physicsai.studio;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.SafeBrowsingResponse;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.content.Intent;
import android.net.Uri;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.content.SharedPreferences;

public class MainActivity extends Activity {
    private static final String PREFS = "physics_ai_studio";
    private static final String URL_KEY = "server_url";
    private static final int BG = Color.rgb(16, 25, 35);
    private static final int PANEL = Color.rgb(25, 38, 51);
    private static final int CYAN = Color.rgb(53, 197, 232);
    private static final int TEXT = Color.rgb(235, 243, 249);
    private static final int MUTED = Color.rgb(145, 165, 184);

    private WebView webView;
    private ProgressBar progress;
    private TextView status;
    private LinearLayout root;
    private SharedPreferences prefs;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        Window window = getWindow();
        window.setStatusBarColor(BG);
        window.setNavigationBarColor(BG);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        buildShell();
        String saved = prefs.getString(URL_KEY, "");
        if (saved == null || saved.trim().isEmpty()) {
            showServerSetup();
        } else {
            loadApp(saved);
        }
    }

    private GradientDrawable rounded(int color, int radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(radiusDp * getResources().getDisplayMetrics().density);
        return d;
    }

    private int dp(float value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private TextView text(String value, float size, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextSize(size);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return t;
    }

    private Button button(String label) {
        Button b = new Button(this);
        b.setText(label);
        b.setTextColor(Color.rgb(8, 25, 35));
        b.setAllCaps(false);
        b.setTextSize(14);
        b.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        b.setBackground(rounded(CYAN, 14));
        return b;
    }

    private void buildShell() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);

        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(dp(16), 0, dp(10), 0);
        bar.setBackgroundColor(BG);
        TextView brand = text("PHYSICS AI STUDIO", 14, TEXT, true);
        brand.setLetterSpacing(0.08f);
        bar.addView(brand, new LinearLayout.LayoutParams(0, dp(54), 1));

        Button reload = new Button(this);
        reload.setText("↻");
        reload.setTextSize(22);
        reload.setTextColor(TEXT);
        reload.setAllCaps(false);
        reload.setBackgroundColor(Color.TRANSPARENT);
        bar.addView(reload, new LinearLayout.LayoutParams(dp(46), dp(48)));
        reload.setOnClickListener(v -> {
            if (webView != null) webView.reload();
        });

        Button settings = new Button(this);
        settings.setText("⋮");
        settings.setTextSize(22);
        settings.setTextColor(TEXT);
        settings.setAllCaps(false);
        settings.setBackgroundColor(Color.TRANSPARENT);
        bar.addView(settings, new LinearLayout.LayoutParams(dp(42), dp(48)));
        settings.setOnClickListener(v -> showServerDialog());

        root.addView(bar, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(54)));

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setProgressTintList(android.content.res.ColorStateList.valueOf(CYAN));
        progress.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(PANEL));
        root.addView(progress, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(3)));

        FrameLayout content = new FrameLayout(this);
        LinearLayout.LayoutParams contentParams = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1);
        root.addView(content, contentParams);

        webView = new WebView(this);
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setDatabaseEnabled(true);
        ws.setLoadsImagesAutomatically(true);
        ws.setSupportZoom(true);
        ws.setBuiltInZoomControls(false);
        ws.setDisplayZoomControls(false);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        ws.setAllowFileAccess(false);
        ws.setAllowContentAccess(false);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);
        webView.setBackgroundColor(BG);
        webView.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) {
                progress.setProgress(value);
                progress.setVisibility(value >= 100 ? View.GONE : View.VISIBLE);
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                progress.setVisibility(View.VISIBLE);
                progress.setProgress(5);
            }
            @Override public void onPageFinished(WebView view, String url) {
                progress.setProgress(100);
                progress.setVisibility(View.GONE);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    status.setText("Tidak dapat terhubung. Periksa koneksi internet atau alamat server, lalu muat ulang.");
                    status.setVisibility(View.VISIBLE);
                }
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme() == null ? "" : uri.getScheme();
                if ("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme)) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (Exception ignored) {}
                return true;
            }
        });
        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, length) -> {
            try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); }
            catch (Exception ignored) {
                status.setText("Unduhan ini tidak dapat dibuka oleh aplikasi. Coba gunakan menu unduh pada halaman.");
                status.setVisibility(View.VISIBLE);
            }
        });
        content.addView(webView, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        status = text("", 13, MUTED, false);
        status.setPadding(dp(18), dp(10), dp(18), dp(10));
        status.setBackgroundColor(PANEL);
        status.setVisibility(View.GONE);
        FrameLayout.LayoutParams statusParams = new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM);
        content.addView(status, statusParams);

        setContentView(root);
    }

    private void showServerSetup() {
        webView.setVisibility(View.GONE);
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setGravity(Gravity.CENTER_VERTICAL);
        panel.setPadding(dp(26), dp(28), dp(26), dp(28));
        panel.setBackground(rounded(PANEL, 22));

        TextView eyebrow = text("ENGINEERING SIMULATION PLATFORM", 10, CYAN, true);
        eyebrow.setLetterSpacing(0.12f);
        panel.addView(eyebrow);
        TextView title = text("Physics AI Studio", 28, TEXT, true);
        LinearLayout.LayoutParams titleP = new LinearLayout.LayoutParams(-1, -2);
        titleP.topMargin = dp(12);
        panel.addView(title, titleP);
        TextView desc = text("Hubungkan aplikasi Android ini ke server Physics AI Studio yang sudah di-deploy.", 14, MUTED, false);
        LinearLayout.LayoutParams descP = new LinearLayout.LayoutParams(-1, -2);
        descP.topMargin = dp(10);
        panel.addView(desc, descP);
        TextView label = text("URL SERVER STREAMLIT", 11, TEXT, true);
        LinearLayout.LayoutParams labelP = new LinearLayout.LayoutParams(-1, -2);
        labelP.topMargin = dp(26);
        panel.addView(label, labelP);
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setTextColor(TEXT);
        input.setHintTextColor(MUTED);
        input.setHint("https://nama-aplikasi.streamlit.app");
        input.setText(prefs.getString(URL_KEY, ""));
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        input.setPadding(dp(14), dp(12), dp(14), dp(12));
        input.setBackground(rounded(BG, 12));
        LinearLayout.LayoutParams inputP = new LinearLayout.LayoutParams(-1, -2);
        inputP.topMargin = dp(9);
        panel.addView(input, inputP);
        Button connect = button("Hubungkan ke Physics AI Studio");
        LinearLayout.LayoutParams connectP = new LinearLayout.LayoutParams(-1, dp(52));
        connectP.topMargin = dp(16);
        panel.addView(connect, connectP);
        connect.setOnClickListener(v -> {
            String value = input.getText().toString().trim();
            if (!value.startsWith("https://") || value.length() < 13) {
                input.setError("Masukkan URL HTTPS aplikasi Streamlit");
                return;
            }
            prefs.edit().putString(URL_KEY, value).apply();
            panel.setVisibility(View.GONE);
            webView.setVisibility(View.VISIBLE);
            loadApp(value);
        });

        FrameLayout content = (FrameLayout) root.getChildAt(2);
        FrameLayout.LayoutParams p = new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.CENTER);
        p.setMargins(dp(18), dp(18), dp(18), dp(18));
        content.addView(panel, p);
    }

    private void showServerDialog() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setTextColor(TEXT);
        input.setHintTextColor(MUTED);
        input.setHint("https://nama-aplikasi.streamlit.app");
        input.setText(prefs.getString(URL_KEY, ""));
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        new AlertDialog.Builder(this)
            .setTitle("Alamat server simulasi")
            .setView(input)
            .setNegativeButton("Batal", null)
            .setPositiveButton("Simpan", (dialog, which) -> {
                String value = input.getText().toString().trim();
                if (value.startsWith("https://")) {
                    prefs.edit().putString(URL_KEY, value).apply();
                    loadApp(value);
                }
            }).show();
    }

    private void loadApp(String value) {
        String url = value.trim();
        if (!url.startsWith("https://")) url = "https://" + url;
        status.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
        webView.loadUrl(url);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
        }
        super.onDestroy();
    }
}
