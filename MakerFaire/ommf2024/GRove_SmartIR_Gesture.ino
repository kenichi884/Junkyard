
//#include <SPI.h>
#include <Wire.h>
#include "Gesture.h"

#if USE_XIAORP2040
const int redled = 17; //GPIO17 //    //RX_LED
const int greenled = 16; //GPIO16 //    //TX_LED
const int blueled = 25; //GPIO25 //LED_BUILTIN //YELLOW_LED
#else // XIAO SAMD21
const int buttonPin = 6;     // the number of the pushbutton pin
const int ledPin =  13;
#endif
#define PAG7660_CS D3 // SPI CS
//pag7660 Gesture; // Combined mode is used by default
pag7660 Gesture(GESTURE_CURSOR_MODE);
//pag7660 Gesture(GESTURE_THUMB_MODE);

bool initSensor(int retrycount){
  for (int i = 0; i < retrycount; i++){
    if(Gesture.init() == false){ // I2C
    //if(Gesture.init(PAG7660_CS) == false){ // SPI
      Serial.print("PAG7660 initialization failed ");
      Serial.println(i+1);

#if USE_XIAORP2040
      digitalWrite(redled, LOW);
#endif
    } else {
#if USE_XIAORP2040
      digitalWrite(redled, HIGH);
      digitalWrite(greenled, LOW);
#else
      digitalWrite(ledPin, HIGH);
#endif
      return true;
    }
    delay(50);
  }
  return false;

}

void setup() {
    Serial.begin(115200);
    while(!Serial) {
        delay(100);
    }
#if USE_XIAORP2040
    pinMode(redled, OUTPUT);
    pinMode(greenled, OUTPUT);
    pinMode(blueled, OUTPUT);
    digitalWrite(redled, HIGH);
    digitalWrite(greenled, HIGH);
    digitalWrite(blueled, HIGH);
#else 
    pinMode(ledPin, OUTPUT);
    digitalWrite(ledPin, LOW);
#endif
    initSensor(100);
}


int mode = 0;
void loop() {
  if(Serial.available() > 0){
    String command = Serial.readString(); 
    command.trim();
    if(command == "T"){
      mode = 1;
#if USE_XIAORP2040
      digitalWrite(blueled, LOW);
#endif
    } else if(command == "R") {
      initSensor(10);
    }
  }
  pag7660_out_t out;
  if (Gesture.getOutput(out)){
    Serial.print(out.palm.valid); Serial.print(", "); // 0
    Serial.print(out.palm.x); Serial.print(", "); // 1
    Serial.print(out.palm.y); Serial.print(", "); // 2
    Serial.print(out.palm.r); Serial.print(", "); 
    Serial.print(out.palm.b); Serial.print(", "); 
    Serial.print(out.result.rotate);  Serial.print(", ");  // 5
    Serial.print(out.result.type); Serial.print(", "); // 6
    Serial.print(out.result.cursor.type), Serial.print(", "); // 7
    Serial.print(out.result.cursor.select);// 8
        Serial.print(", ");
    if(mode == 1) { // print tip positions
      for(int i =0 ; i < GESTURE_MAX_TIPS; i++){
        // 5 times 
        // 9 10 11 12 
        // 13 14 15 16
        // 17 18 19 20
        // 21 22 23 24
        // 25 26 27 28
        Serial.print(" "); 
        Serial.print(out.tips[i].id); Serial.print(", "); 
        Serial.print(out.tips[i].x) ; Serial.print(", "); 
        Serial.print(out.tips[i].y); Serial.print(", ");
        Serial.print(out.tips[i].b); Serial.print(", ");
      }
    }
    Serial.println();
  }

  // 10fps
  //delay(100);
  delay(50);
  

}
