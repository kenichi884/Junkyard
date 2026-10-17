/* ----------------------------------------------------------------
  M5DialToio_Mat.ino

  M5Stack M5Dial (ESP32-S3) application to control Sony toio Core Cube.
  - Dial rotation: changes the target heading (direction).
  - Touch swipe up: drives forward, speed matches swipe velocity.
  - Screen tap or swipe down: stops the cube.
  - Closed-loop steering control using toio Developer Mat coordinates.
  - Automatically stops if off the mat for safety.

  Dependencies:
  - M5Dial (Library Manager)
  - M5Unified (Library Manager)
  - M5GFX (Library Manager)
  - M5StackToio (https://github.com/kenichi884/M5StackToio)
  - NimBLE-Arduino (Important: Install version 1.4.3)
  -------------------------------------------------------------- */
#include <Arduino.h>
#include <M5Dial.h>
#include <Toio.h>
#include <math.h>

#define Serial USBSerial

// BLE & toio Core
static Toio toio;
static ToioCore* toiocore = nullptr;
bool is_connected = false;

// Connection States
enum ConnState {
  STATE_SCANNING,
  STATE_CONNECTING,
  STATE_CONNECTED,
  STATE_DISCONNECTED
};
ConnState conn_state = STATE_SCANNING;

// Coordinates & mat state
uint16_t current_x = 0;
uint16_t current_y = 0;
uint16_t current_angle = 0;
bool on_mat = false;
unsigned long last_mat_time = 0;

// Target state (steering and speed)
int target_angle = 0; // 0 to 359 degrees
int target_speed = 0; // 0 to 110

// Touch tracking
int base_x = 0;
int base_y = 0;
unsigned long base_msec = 0;
bool is_touching = false;
int touch_x = 0;
int touch_y = 0;

// Control parameters
const float Kp = 1.3; // Proportional gain for steering
const int MAX_STEER = 50; // Maximum steer speed offset
const unsigned long CONTROL_INTERVAL = 50; // Control loop interval in ms
unsigned long last_control_time = 0;

// Double buffer screen canvas
M5Canvas canvas(&M5Dial.Display);

// ---------------------------------------------------------------
// toio Event Callbacks
// ---------------------------------------------------------------

// Connection state callback
void onConnection(bool connected) {
  is_connected = connected;
  if (connected) {
    conn_state = STATE_CONNECTED;
  } else {
    conn_state = STATE_DISCONNECTED;
    on_mat = false;
    target_speed = 0;
  }
}

// Position ID / Mat reading callback
void onIDData(ToioCoreIDData id_data) {
  if (id_data.type == ToioCoreIDTypePosition) {
    current_x = id_data.position.cubePosX;
    current_y = id_data.position.cubePosY;
    current_angle = id_data.position.cubeAngleDegree;
    on_mat = true;
    last_mat_time = millis();
  } else if (id_data.type == ToioCoreIDTypeNone) {
    // Left the mat (Position ID missed)
    on_mat = false;
  }
}


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
  
  // 2. Draw Target Angle needle (Green)
  {
    float rad = target_angle * DEG_TO_RAD;
    int tx = cx + (int)(95 * cos(rad));
    int ty = cy + (int)(95 * sin(rad));
    canvas.drawLine(cx, cy, tx, ty, GREEN);
    canvas.fillCircle(tx, ty, 4, GREEN);
  }
  
  // 3. Draw Actual Angle pointer (Orange/Yellow) if on mat
  if (is_connected && on_mat) {
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
  if (conn_state == STATE_SCANNING) {
    canvas.setTextColor(SKYBLUE);
    canvas.drawString("SCANNING...", cx, 85, &fonts::Font2);
  } else if (conn_state == STATE_CONNECTING) {
    canvas.setTextColor(YELLOW);
    canvas.drawString("PAIRING...", cx, 85, &fonts::Font2);
  } else if (conn_state == STATE_CONNECTED) {
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
  if (is_connected) {
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
  } else if (conn_state == STATE_DISCONNECTED) {
    canvas.setTextColor(canvas.color565(100, 100, 100));
    canvas.drawString("Tap Btn to Retry", cx, 155, &fonts::Font2);
  }
  
  // Push the final buffer to screen
  canvas.pushSprite(0, 0);
}

// ---------------------------------------------------------------
// BLE Scan & Connect Execution
// ---------------------------------------------------------------
void scanAndConnect() {
  Serial.println("scanAndConnect");
  conn_state = STATE_SCANNING;
  drawUI();
  
  Serial.print("start toio.scan ");
  // Scan for 3 seconds
  std::vector<ToioCore*> toiocore_list = toio.scan(3);
  Serial.print("found "); Serial.print(toiocore_list.size()); Serial.print(" toios");
  
  if (toiocore_list.size() > 0) {
    toiocore = toiocore_list.at(0);
    conn_state = STATE_CONNECTING;
    drawUI();
    
    if (toiocore->connect()) {
      is_connected = true;
      conn_state = STATE_CONNECTED;
      // Register callbacks
      toiocore->onConnection(onConnection);
      toiocore->onIDReaderData(onIDData);
      
      // Configure ID notification settings: notify every 20ms, always notify
      toiocore->setIDnotificationSettings(2, ToioCoreNotificationCondition::NotifyAllways);
      
      // Play a short startup sound effect (success)
      toiocore->playSoundEffect(0x01, 0xff); 
      toiocore->turnOnLed(0, 255, 255); // Cyan LED
    } else {
      conn_state = STATE_DISCONNECTED;
    }
  } else {
    conn_state = STATE_DISCONNECTED;
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
    if (is_connected && toiocore) {
      if(on_mat)
        toiocore->controlMotorWithTarget(0, 5, 0, 30, 0x03,current_x, current_y, target_angle);
    }
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
      if (is_connected && toiocore) {
        toiocore->playSoundEffect(0x04, 0xff); // Short beep
        toiocore->controlMotor(true, 0, true, 0, 100);
      }
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
          if (is_connected && toiocore) {
            toiocore->playSoundEffect(0x02, 0xff); // Upward chirp
            toiocore->controlMotor(true, target_speed, true, target_speed, 300);
          }
          Serial.print("handleTouch target speed "); Serial.println(target_speed, DEC);
        } else {
          // Swipe Down -> Drive backward
          if (is_connected && toiocore) {
            toiocore->playSoundEffect(0x03, 0xff); // Downward chirp
            toiocore->controlMotor(false, target_speed, false, target_speed, 300);
          }
          Serial.println("handleTouch target speed down "); 
        }
      }
    }
  }
}

// ---------------------------------------------------------------
// Closed-Loop Control Loop
// ---------------------------------------------------------------
void runControlLoop() {

  if (millis() - last_control_time < CONTROL_INTERVAL) {
    return;
  }
  last_control_time = millis();
  
  if (!is_connected || toiocore == nullptr) {
    return;
  }
  
  // Mat connection safety timeout (500ms since last coordinate update)
  if (!on_mat || (millis() - last_mat_time > 500)) {
    on_mat = false;
    toiocore->controlMotor(true, 0, true, 0, 100); // Stop
    toiocore->turnOnLed(255, 0, 0); // Solid red LED warning
    return;
  }
  
  // Set LED to green/cyan while driving normally on mat
  if (target_speed > 0) {
    toiocore->turnOnLed(0, 255, 0); // Green when moving
  } else {
    toiocore->turnOnLed(0, 0, 255); // Blue when stopped on mat
  }

  // Calculate shortest steering angle error
  int error = target_angle - current_angle;
  while (error > 180) error -= 360;
  while (error < -180) error += 360;
  
  // Proportional steering control
  int steer = (int)(Kp * error);
  steer = constrain(steer, -MAX_STEER, MAX_STEER);
  
  // Compute left and right speeds
  int left_speed = target_speed + steer;
  int right_speed = target_speed - steer;
  
  // Map signs to direction bits (true = forward, false = backward)
  bool ldir = (left_speed >= 0);
  bool rdir = (right_speed >= 0);
  
  uint8_t lspeed = abs(left_speed);
  uint8_t rspeed = abs(right_speed);
  
  // Constrain speeds to toio limits
  lspeed = constrain(lspeed, 0, 115);
  rspeed = constrain(rspeed, 0, 115);
  
  // Avoid motor twitching if stopped and target heading is practically achieved
  if (target_speed == 0 && abs(error) <= 3) {
    toiocore->controlMotor(true, 0, true, 0, 100);
  } else {
    // Send command with 100ms duration
    toiocore->controlMotor(ldir, lspeed, rdir, rspeed, 100);
  }
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
  
  // Configure display and canvas
  M5Dial.Display.setBrightness(100);
  canvas.createSprite(240, 240);
  canvas.setTextDatum(middle_center);
  
  // Run initial scan and connect
  scanAndConnect();
}

void loop() {

  M5Dial.update();
  toio.loop(); // Poll BLE events and invoke callbacks
  
  // Handle connection retries on center button press
  if (conn_state == STATE_DISCONNECTED && M5Dial.BtnA.wasPressed()) {
    scanAndConnect();
  }
  
  // Process encoder and touch screen
  handleDial();
  handleTouch();
  
  // Run motor control closed loop
  //runControlLoop();
  
  // Redraw dashboard UI
  drawUI();
  
  delay(1);
}
