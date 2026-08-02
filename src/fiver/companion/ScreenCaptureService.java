package com.fiver.companion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.util.DisplayMetrics;
import android.view.WindowManager;

import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public class ScreenCaptureService extends Service {
    private static final String CHANNEL_ID = "fiver_mirror";
    private static final int NOTIFICATION_ID = 1;
    
    private MediaProjectionManager projectionManager;
    private MediaProjection mediaProjection;
    private VirtualDisplay virtualDisplay;
    private ImageReader imageReader;
    
    private HandlerThread handlerThread;
    private Handler handler;
    private ExecutorService networkExecutor;
    
    private String serverUrl;
    private AtomicBoolean isSending = new AtomicBoolean(false);
    private long lastFrameTime = 0;
    private static final long MIN_FRAME_INTERVAL_MS = 50; // Max ~20 FPS

    @Override
    public void onCreate() {
        super.onCreate();
        projectionManager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        
        handlerThread = new HandlerThread("ScreenCaptureThread");
        handlerThread.start();
        handler = new Handler(handlerThread.getLooper());
        
        networkExecutor = Executors.newSingleThreadExecutor();
        
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Notification.Builder builder = new Notification.Builder(this)
                .setContentTitle("Fiver Mirror")
                .setContentText("Screen sharing active")
                .setSmallIcon(android.R.drawable.ic_menu_camera)
                .setOngoing(true);
                
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder.setChannelId(CHANNEL_ID);
        }
        
        startForeground(NOTIFICATION_ID, builder.build());
        
        if (intent != null) {
            int resultCode = intent.getIntExtra("resultCode", 0);
            Intent resultData = intent.getParcelableExtra("resultData");
            serverUrl = intent.getStringExtra("serverUrl");
            
            if (resultCode != 0 && resultData != null) {
                startCapture(resultCode, resultData);
            }
        }
        
        return START_NOT_STICKY;
    }
    
    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "Fiver Mirror",
                    NotificationManager.IMPORTANCE_LOW
            );
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }
    
    private void startCapture(int resultCode, Intent resultData) {
        mediaProjection = projectionManager.getMediaProjection(resultCode, resultData);
        if (mediaProjection == null) return;
        
        mediaProjection.registerCallback(new MediaProjection.Callback() {
            @Override
            public void onStop() {
                stopSelf();
            }
        }, null);
        
        WindowManager windowManager = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        DisplayMetrics metrics = new DisplayMetrics();
        windowManager.getDefaultDisplay().getMetrics(metrics);
        
        int width = metrics.widthPixels;
        int height = metrics.heightPixels;
        int density = metrics.densityDpi;
        
        // Scale to max 720px width for performance
        if (width > 720) {
            float scale = 720f / width;
            width = 720;
            height = (int) (height * scale);
        }
        
        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        virtualDisplay = mediaProjection.createVirtualDisplay(
                "FiverMirror",
                width, height, density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                imageReader.getSurface(),
                null, handler
        );
        
        final int finalWidth = width;
        final int finalHeight = height;
        
        imageReader.setOnImageAvailableListener(new ImageReader.OnImageAvailableListener() {
            @Override
            public void onImageAvailable(ImageReader reader) {
                long currentTime = System.currentTimeMillis();
                if (currentTime - lastFrameTime < MIN_FRAME_INTERVAL_MS) {
                    Image image = reader.acquireLatestImage();
                    if (image != null) image.close();
                    return;
                }
                
                if (isSending.get()) {
                    Image image = reader.acquireLatestImage();
                    if (image != null) image.close();
                    return;
                }
                
                Image image = null;
                try {
                    image = reader.acquireLatestImage();
                    if (image == null) return;
                    
                    lastFrameTime = currentTime;
                    
                    Image.Plane[] planes = image.getPlanes();
                    ByteBuffer buffer = planes[0].getBuffer();
                    int pixelStride = planes[0].getPixelStride();
                    int rowStride = planes[0].getRowStride();
                    int rowPadding = rowStride - pixelStride * finalWidth;
                    
                    int bitmapWidth = finalWidth + rowPadding / pixelStride;
                    Bitmap bitmap = Bitmap.createBitmap(bitmapWidth, finalHeight, Bitmap.Config.ARGB_8888);
                    bitmap.copyPixelsFromBuffer(buffer);
                    
                    Bitmap croppedBitmap = bitmap;
                    if (bitmapWidth != finalWidth) {
                        croppedBitmap = Bitmap.createBitmap(bitmap, 0, 0, finalWidth, finalHeight);
                    }
                    
                    sendFrame(croppedBitmap);
                    
                } catch (Exception e) {
                    e.printStackTrace();
                } finally {
                    if (image != null) {
                        image.close();
                    }
                }
            }
        }, handler);
    }
    
    private void sendFrame(final Bitmap bitmap) {
        isSending.set(true);
        networkExecutor.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    ByteArrayOutputStream bos = new ByteArrayOutputStream();
                    bitmap.compress(Bitmap.CompressFormat.JPEG, 60, bos);
                    byte[] jpegBytes = bos.toByteArray();
                    
                    if (serverUrl != null && !serverUrl.isEmpty()) {
                        URL url = new URL(serverUrl + "/api/frame");
                        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                        conn.setRequestMethod("POST");
                        conn.setRequestProperty("Content-Type", "image/jpeg");
                        conn.setDoOutput(true);
                        conn.setConnectTimeout(3000);
                        conn.setReadTimeout(3000);
                        
                        OutputStream os = conn.getOutputStream();
                        os.write(jpegBytes);
                        os.flush();
                        os.close();
                        
                        conn.getResponseCode();
                        conn.disconnect();
                    }
                } catch (Exception e) {
                    // Silently ignore network errors to keep trying
                } finally {
                    bitmap.recycle();
                    isSending.set(false);
                }
            }
        });
    }

    @Override
    public void onDestroy() {
        if (virtualDisplay != null) {
            virtualDisplay.release();
        }
        if (imageReader != null) {
            imageReader.close();
        }
        if (mediaProjection != null) {
            mediaProjection.stop();
        }
        if (handlerThread != null) {
            handlerThread.quitSafely();
        }
        if (networkExecutor != null) {
            networkExecutor.shutdownNow();
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
