package com.smarthome.ble;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.ParcelUuid;
import android.util.Log;

import java.io.OutputStream;
import java.net.Socket;
import java.util.ArrayList;
import java.util.List;

public class BleService extends Service {
    private static final String TAG = "BleService";
    private static final String CHANNEL_ID = "ble_scan_channel";
    private BluetoothLeScanner scanner;
    private Socket tcpSocket;
    private OutputStream tcpOut;
    private long resultCount = 0;
    private Handler scanHandler;
    private Runnable scanKeepaliveRunnable;

    // Service Data UUIDs for Xiaomi Thermometers
    private static final ParcelUuid UUID_PVVX = ParcelUuid.fromString("0000181a-0000-1000-8000-00805f9b34fb");
    private static final ParcelUuid UUID_BTHOME = ParcelUuid.fromString("0000fcd2-0000-1000-8000-00805f9b34fb");
    private static final ParcelUuid UUID_MIBEACON = ParcelUuid.fromString("0000fe95-0000-1000-8000-00805f9b34fb");

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        Notification notification = new Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("BLE Gateway")
            .setContentText("Filtered Sensor Scanning Active (24/7)...")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .build();
        startForeground(1, notification);

        // Connect TCP to btsnoop_scanner.py
        new Thread(new Runnable() {
            @Override
            public void run() {
                connectTcp();
            }
        }).start();

        scanHandler = new Handler(Looper.getMainLooper());
        scanKeepaliveRunnable = new Runnable() {
            @Override
            public void run() {
                restartBleScan();
                scanHandler.postDelayed(this, 30000); // Refresh scan every 30s
            }
        };

        startBleScan();
        scanHandler.postDelayed(scanKeepaliveRunnable, 30000);
    }

    private void connectTcp() {
        while (true) {
            try {
                if (tcpSocket == null || tcpSocket.isClosed() || !tcpSocket.isConnected()) {
                    tcpSocket = new Socket("127.0.0.1", 9999);
                    tcpOut = tcpSocket.getOutputStream();
                    Log.i(TAG, "TCP connected to scanner pipeline on port 9999");
                }
            } catch (Exception e) {
                // Wait and retry
            }
            try {
                Thread.sleep(5000);
            } catch (Exception ignored) {}
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "BLE Scan", NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
    }

    private synchronized void startBleScan() {
        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null || !adapter.isEnabled()) {
            Log.e(TAG, "Bluetooth is disabled or null");
            return;
        }
        scanner = adapter.getBluetoothLeScanner();
        if (scanner == null) {
            Log.e(TAG, "BluetoothLeScanner is null");
            return;
        }

        // Specific Service Data filters to bypass Android screen-off scan restrictions
        List<ScanFilter> filters = new ArrayList<ScanFilter>();
        filters.add(new ScanFilter.Builder().setServiceData(UUID_PVVX, new byte[0]).build());
        filters.add(new ScanFilter.Builder().setServiceData(UUID_BTHOME, new byte[0]).build());
        filters.add(new ScanFilter.Builder().setServiceData(UUID_MIBEACON, new byte[0]).build());
        filters.add(new ScanFilter.Builder().setServiceUuid(UUID_PVVX).build());
        filters.add(new ScanFilter.Builder().setServiceUuid(UUID_BTHOME).build());
        filters.add(new ScanFilter.Builder().setServiceUuid(UUID_MIBEACON).build());

        ScanSettings settings = new ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build();

        try {
            scanner.startScan(filters, settings, scanCallback);
            Log.i(TAG, "BLE FILTERED scan started for PVVX (0x181A), BTHome (0xFCD2), MiBeacon (0xFE95)");
        } catch (Exception e) {
            Log.e(TAG, "startScan error: " + e.getMessage());
        }
    }

    private synchronized void restartBleScan() {
        if (scanner != null) {
            try {
                scanner.stopScan(scanCallback);
            } catch (Exception ignored) {}
        }
        startBleScan();
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            resultCount++;
            String mac = result.getDevice().getAddress();
            int rssi = result.getRssi();
            byte[] adBytes = result.getScanRecord() != null
                ? result.getScanRecord().getBytes() : new byte[0];
            StringBuilder hex = new StringBuilder();
            for (byte b : adBytes) {
                hex.append(String.format("%02X", b & 0xFF));
            }
            String line = mac + "," + rssi + "," + hex.toString() + "\n";

            Log.i(TAG, "Filter Scan Result #" + resultCount + " | MAC: " + mac + " RSSI: " + rssi);

            if (tcpOut != null) {
                try {
                    tcpOut.write(line.getBytes());
                    tcpOut.flush();
                } catch (Exception e) {
                    tcpOut = null;
                }
            }
        }

        @Override
        public void onScanFailed(int errorCode) {
            Log.e(TAG, "Scan failed with code " + errorCode);
        }
    };

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onDestroy() {
        if (scanHandler != null && scanKeepaliveRunnable != null) {
            scanHandler.removeCallbacks(scanKeepaliveRunnable);
        }
        if (scanner != null) {
            try { scanner.stopScan(scanCallback); } catch (Exception ignored) {}
        }
        try { if (tcpSocket != null) tcpSocket.close(); } catch (Exception ignored) {}
        super.onDestroy();
    }
}
