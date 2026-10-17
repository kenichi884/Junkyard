/* ----------------------------------------------------------------
  M5DialToioNUS.ino



  Dependencies:
  - M5Dial (Library Manager)
  - M5Unified (Library Manager)
  - M5GFX (Library Manager)
  - NimBLE-Arduino 
  -------------------------------------------------------------- */
#include <Arduino.h>
#include <M5Dial.h>
#include <NimBLEDevice.h>
#include <math.h>

#define Serial USBSerial

#define DEVICE_NAME "M5Dial"
// ==============================
//  BLE UART Service UUIDs
// ==============================
static const char* SERVICE_UUID           = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
static const char* CHARACTERISTIC_UUID_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";
static const char* CHARACTERISTIC_UUID_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E";

// ==============================
//  Global Variables
// ==============================
NimBLECharacteristic* g_tx = nullptr;
bool g_connected = false;

// ===================================================
//  BLE Server Callbacks
// ===================================================
class ServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo) override {
        (void)pServer; (void)connInfo;
        g_connected = true;
        Serial.println("✅ Central connected!");
    }
    void onDisconnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo, int reason) override {
        (void)pServer; (void)connInfo;
        g_connected = false;
        Serial.printf("❌ Central disconnected (reason=%d)\n", reason);
        // 再度アドバタイズ開始
        NimBLEDevice::getAdvertising()->start();
        Serial.println("🔁 Advertising restarted!");
    }
};


// ===================================================
//  RX Characteristic Callback
// ===================================================
class RxCallbacks : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* ch, NimBLEConnInfo& info) override {
        (void)info;
        std::string v = ch->getValue();
        if (!v.empty()) {
            Serial.print("📩 RX: "); Serial.println(v.c_str());
        }
    }
};


int target_angle = 0;
int target_speed = 0;
// Touch tracking
int base_x = 0;
int base_y = 0;
unsigned long base_msec = 0;
bool is_touching = false;
int touch_x = 0;
int touch_y = 0;

// Double buffer screen canvas
M5Canvas canvas(&M5Dial.Display);

// ---------------------------------------------------------------
// Graphical User Interface Drawing
// ---------------------------------------------------------------
void drawUI() {
  canvas.fillSprite(BLACK);
  
  // Center coordinates of M5Dial round display (240x240)
  int cx = 120;
  int cy = 120;
  
  // 1. Draw outer compass card ticks
  for (int a = 0; a < 360; a += 30) {
    float rad = a * DEG_TO_RAD;
    int x1 = cx + (int)(110 * cos(rad));
    int y1 = cy + (int)(110 * sin(rad));
    int x2 = cx + (int)(102 * cos(rad));
    int y2 = cy + (int)(102 * sin(rad));
    canvas.drawLine(x1, y1, x2, y2, canvas.color565(60, 60, 65));
  }
  
  /*
  // 2. Draw Target Angle needle (Green)
  {
    float rad = target_angle * DEG_TO_RAD;
    int tx = cx + (int)(95 * cos(rad));
    int ty = cy + (int)(95 * sin(rad));
    canvas.drawLine(cx, cy, tx, ty, GREEN);
    canvas.fillCircle(tx, ty, 4, GREEN);
  }
  
  // 3. Draw Actual Angle pointer (Orange/Yellow) if on mat
  if (g_connected == true) {
    float rad = current_angle * DEG_TO_RAD;
    int ax = cx + (int)(85 * cos(rad));
    int ay = cy + (int)(85 * sin(rad));
    canvas.drawLine(cx, cy, ax, ay, ORANGE);
    
    // Draw arrowhead pointer at the tip
    float arrow_left_rad = (current_angle - 150) * DEG_TO_RAD;
    float arrow_right_rad = (current_angle + 150) * DEG_TO_RAD;
    int al_x = ax + (int)(12 * cos(arrow_left_rad));
    int al_y = ay + (int)(12 * sin(arrow_left_rad));
    int ar_x = ax + (int)(12 * cos(arrow_right_rad));
    int ar_y = ay + (int)(12 * sin(arrow_right_rad));
    canvas.fillTriangle(ax, ay, al_x, al_y, ar_x, ar_y, ORANGE);
  }
  */

  // 4. Draw central instrument housing mask
  canvas.fillCircle(cx, cy, 72, canvas.color565(15, 15, 20));
  canvas.drawCircle(cx, cy, 72, canvas.color565(80, 80, 90));
  canvas.drawCircle(cx, cy, 74, canvas.color565(40, 40, 45));
  
  // 5. Draw Touch vector feedback
  if (is_touching) {
    canvas.drawLine(base_x, base_y, touch_x, touch_y, SKYBLUE);
    canvas.drawCircle(touch_x, touch_y, 8, SKYBLUE);
  }

  // 6. Draw central status texts
  canvas.setTextDatum(middle_center);

  // Y = 85: Connection Status
  if (g_connected == true) {
    canvas.setTextColor(GREEN);
    canvas.drawString("CONNECTED", cx, 85, &fonts::Font2);
  } else {
    canvas.setTextColor(RED);
    canvas.drawString("DISCONNECTED", cx, 85, &fonts::Font2);
  }
  
  // Y = 120: Speed Indicator
  canvas.setTextColor(WHITE);
  canvas.drawString("SPD: " + String(target_speed), cx, 120, &fonts::Font4);
  
  // Y = 155: Mat Info or Warning
  /*
  if (g_connected == true) {
    if (on_mat) {
      canvas.setTextColor(canvas.color565(180, 180, 180));
      canvas.drawString(String(current_x) + ", " + String(current_y), cx, 155, &fonts::Font2);
    } else {
      // Flashing alert
      if ((millis() / 250) % 2 == 0) {
        canvas.setTextColor(RED);
        canvas.drawString("OFF MAT!", cx, 155, &fonts::Font2);
      }
    }
  } else if (g_connected == false) {
    canvas.setTextColor(canvas.color565(100, 100, 100));
    canvas.drawString("Tap Btn to Retry", cx, 155, &fonts::Font2);
  }
    */
  
  // Push the final buffer to screen
  canvas.pushSprite(0, 0);
}

void sendNUS(String msg)
{
  if(g_connected)
  {
    g_tx->setValue(msg.c_str());
    g_tx->notify();
  }
}

// ---------------------------------------------------------------
// Input Handlers
// ---------------------------------------------------------------
long old_position = 0;

void handleDial() {
  
  long new_position = M5Dial.Encoder.read();
  
  if (new_position != old_position) {
    long diff = new_position - old_position;
    old_position = new_position;
    Serial.print("handleDial new_position "); Serial.print(new_position, DEC); 
    // Map each click (diff of 1) to 6 degrees change (60 clicks = 360 degrees)
    target_angle = (target_angle + diff * 6) % 360;
    
    if (target_angle < 0) {
      target_angle += 360;
    }

    String str = "ANGLE " + String(target_angle);
    sendNUS(str);
    
    Serial.print(" target_angle "); Serial.print(target_angle, DEC);
    Serial.println("");
  }
  
}

void handleTouch() {
  
  auto touchDetail = M5Dial.Touch.getDetail();
  touch_x = touchDetail.x;
  touch_y = touchDetail.y;
  
  if (touchDetail.wasPressed()) {
    base_x = touchDetail.x;
    base_y = touchDetail.y;
    base_msec = millis();
    is_touching = true;
  }
  
  if (touchDetail.wasReleased()) {
    is_touching = false;
    int dx = touchDetail.x - base_x;
    int dy = touchDetail.y - base_y;
    unsigned long dt = millis() - base_msec;
    float dist = sqrt(dx*dx + dy*dy);
    
    if (dist < 15 && dt < 300) {
      // Tap detected -> Brake (Stop immediately)
      target_speed = 0;
      String str = "TAP" ;
      sendNUS(str);
      Serial.println("handleTouch target speed zero");
    } else if (dist >= 15 && dt > 0) {
      float velocity = dist / (float)dt; // pixels/ms
      
      if (abs(dy) > abs(dx)) {
        // Mostly vertical gesture
        // Map velocity (typically 0.2 to 1.5) to toio speed (20 to 100)
        float speed_val = 20.0 + (velocity - 0.2) * (100.0 - 20.0) / (1.5 - 0.2);
        target_speed = (int)constrain(speed_val, 20, 100);
        if (dy < 0) {
          // Swipe Up -> Drive forward
          String str = "FWD " + String(target_speed);
          sendNUS(str);

          Serial.print("handleTouch target speed "); Serial.println(target_speed, DEC);
        } else {
          // Swipe Down -> Drive backward
          String str = "BACK " + String(target_speed);
          sendNUS(str);
          Serial.println("handleTouch target speed down "); 
        }
      }
    }
  }
}

void initBLE()
{
  // Initialize NimBLE
  NimBLEDevice::init(DEVICE_NAME);

  // Transmit Power
  NimBLEDevice::setPowerLevel(ESP_PWR_LVL_P21, ESP_BLE_PWR_TYPE_ADV);

  // Security (Static PIN, v2.x API) & MTU
  //NimBLEDevice::setSecurityAuth(true, true, true);   // bonding, MITM, secure
  //NimBLEDevice::setSecurityPasskey(SECURITY_PIN);
  //NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_YESNO);
  NimBLEDevice::setMTU(247);  // 実効244 bytes（安定・実装上限）Payload + 3バイト（ATTヘッダ）

  // Create Server
  NimBLEServer* server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  // Create Service and Characteristics
  NimBLEService* svc = server->createService(SERVICE_UUID);
  g_tx = svc->createCharacteristic(CHARACTERISTIC_UUID_TX, NIMBLE_PROPERTY::NOTIFY);
  NimBLECharacteristic* rx = svc->createCharacteristic(CHARACTERISTIC_UUID_RX, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  rx->setCallbacks(new RxCallbacks());
  svc->start();

  // Start Advertising
  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  NimBLEAdvertisementData advData; advData.addServiceUUID(SERVICE_UUID);
  adv->setAdvertisementData(advData);
  NimBLEAdvertisementData scanData; scanData.setName(DEVICE_NAME); scanData.addServiceUUID(SERVICE_UUID);
  adv->setScanResponseData(scanData);
  adv->setMinInterval(0x20);
  adv->setMaxInterval(0x40);
  adv->start();  
  Serial.println("BLE advertising start");
}


// ---------------------------------------------------------------
// Setup and Loop
// ---------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  // Initialize M5Dial config
  auto cfg = M5.config();
  // Enable encoder, disable RFID
  M5Dial.begin(cfg, true, false);

  initBLE();
  
  // Configure display and canvas
  M5Dial.Display.setBrightness(100);
  canvas.createSprite(240, 240);
  canvas.setTextDatum(middle_center);

}

void loop() {

  M5Dial.update();
 
  
  // Process encoder and touch screen
  handleDial();
  handleTouch();
  
  // Run motor control closed loop
  //runControlLoop();
  
  // Redraw dashboard UI
  drawUI();
  
  delay(1);
}
