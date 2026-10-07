package com.smarthome;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.os.Looper;

import java.lang.reflect.Method;
import java.util.List;

/**
 * Minimal BLE Scanner that runs via app_process.
 * Outputs one line per scan result: MAC,RSSI,HEX_AD_BYTES
 * to stdout for consumption by Python pipeline.
 */
public class BleScanner {
    public static void main(String[] args) {
        // app_process needs a Looper for BLE callbacks
        if (Looper.myLooper() == null) {
            Looper.prepareMainLooper();
        }

        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) {
            System.err.println("ERROR: No Bluetooth adapter");
            System.exit(1);
        }
        if (!adapter.isEnabled()) {
            System.err.println("ERROR: Bluetooth is disabled. Enable with: svc bluetooth enable");
            System.exit(1);
        }

        BluetoothLeScanner scanner = adapter.getBluetoothLeScanner();
        if (scanner == null) {
            System.err.println("ERROR: BluetoothLeScanner is null (BT off or unsupported)");
            System.exit(1);
        }

        ScanSettings settings = new ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build();

        ScanCallback callback = new ScanCallback() {
            @Override
            public void onScanResult(int callbackType, ScanResult result) {
                String mac = result.getDevice().getAddress();
                int rssi = result.getRssi();
                byte[] adBytes = result.getScanRecord() != null
                    ? result.getScanRecord().getBytes() : new byte[0];
                StringBuilder hex = new StringBuilder();
                for (byte b : adBytes) {
                    hex.append(String.format("%02X", b & 0xFF));
                }
                // Output format: MAC,RSSI,HEX
                System.out.println(mac + "," + rssi + "," + hex.toString());
                System.out.flush();
            }

            @Override
            public void onBatchScanResults(List<ScanResult> results) {
                for (ScanResult r : results) {
                    onScanResult(0, r);
                }
            }

            @Override
            public void onScanFailed(int errorCode) {
                System.err.println("ERROR: Scan failed with code " + errorCode);
            }
        };

        System.err.println("INFO: Starting BLE LE scan (low latency)...");
        scanner.startScan(null, settings, callback);

        // Keep the main looper running indefinitely
        Looper.loop();
    }
}
