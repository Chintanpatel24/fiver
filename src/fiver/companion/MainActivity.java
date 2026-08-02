package com.fiver.companion;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public class MainActivity extends Activity {
    private static final int REQUEST_CODE_SCREEN_CAPTURE = 1000;
    private static final int REQUEST_CODE_NOTIFICATIONS = 1001;
    
    private static final String SERVER_URL = "__FIVER_SERVER_URL__";
    
    private MediaProjectionManager projectionManager;
    private TextView statusText;
    private Button startButton;
    private Button stopButton;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        projectionManager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, REQUEST_CODE_NOTIFICATIONS);
            }
        }
        
        setupUI();
    }
    
    private void setupUI() {
        LinearLayout mainLayout = new LinearLayout(this);
        mainLayout.setOrientation(LinearLayout.VERTICAL);
        mainLayout.setGravity(Gravity.CENTER);
        mainLayout.setBackgroundColor(Color.BLACK);
        mainLayout.setPadding(32, 32, 32, 32);
        
        TextView titleText = new TextView(this);
        titleText.setText("FIVER SCREEN MIRROR");
        titleText.setTextColor(Color.WHITE);
        titleText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24);
        titleText.setGravity(Gravity.CENTER);
        titleText.setPadding(0, 0, 0, 16);
        
        TextView descText = new TextView(this);
        descText.setText("Mirror your device screen to the Fiver web client.");
        descText.setTextColor(Color.LTGRAY);
        descText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        descText.setGravity(Gravity.CENTER);
        descText.setPadding(0, 0, 0, 48);
        
        statusText = new TextView(this);
        statusText.setText("Status: Disconnected");
        statusText.setTextColor(Color.GRAY);
        statusText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        statusText.setGravity(Gravity.CENTER);
        statusText.setPadding(0, 0, 0, 32);
        
        startButton = new Button(this);
        startButton.setText("START SCREEN SHARE");
        startButton.setBackgroundColor(Color.WHITE);
        startButton.setTextColor(Color.BLACK);
        startButton.setPadding(32, 16, 32, 16);
        
        stopButton = new Button(this);
        stopButton.setText("STOP SCREEN SHARE");
        stopButton.setBackgroundColor(Color.RED);
        stopButton.setTextColor(Color.WHITE);
        stopButton.setPadding(32, 16, 32, 16);
        stopButton.setVisibility(View.GONE);
        
        mainLayout.addView(titleText);
        mainLayout.addView(descText);
        mainLayout.addView(statusText);
        mainLayout.addView(startButton);
        mainLayout.addView(stopButton);
        
        setContentView(mainLayout);
        
        startButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startScreenCapture();
            }
        });
        
        stopButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                stopScreenCapture();
            }
        });
    }
    
    private void startScreenCapture() {
        if (projectionManager != null) {
            startActivityForResult(projectionManager.createScreenCaptureIntent(), REQUEST_CODE_SCREEN_CAPTURE);
        }
    }
    
    private void stopScreenCapture() {
        Intent serviceIntent = new Intent(this, ScreenCaptureService.class);
        stopService(serviceIntent);
        
        statusText.setText("Status: Disconnected");
        startButton.setVisibility(View.VISIBLE);
        stopButton.setVisibility(View.GONE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQUEST_CODE_SCREEN_CAPTURE) {
            if (resultCode == RESULT_OK) {
                Intent serviceIntent = new Intent(this, ScreenCaptureService.class);
                serviceIntent.putExtra("resultCode", resultCode);
                serviceIntent.putExtra("resultData", data);
                serviceIntent.putExtra("serverUrl", SERVER_URL);
                
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(serviceIntent);
                } else {
                    startService(serviceIntent);
                }
                
                statusText.setText("Streaming to: " + SERVER_URL);
                startButton.setVisibility(View.GONE);
                stopButton.setVisibility(View.VISIBLE);
            } else {
                statusText.setText("Permission denied");
            }
        }
        super.onActivityResult(requestCode, resultCode, data);
    }
}
