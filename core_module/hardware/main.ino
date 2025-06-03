#include <Servo.h>
// Pin definitions
#define TRIG_PIN 2
#define ECHO_PIN 3
#define RED_LED_PIN 4
#define BLUE_LED_PIN 5
#define SERVO_PIN 6
#define GROUND_PIN_1 7
#define GROUND_PIN_2 8
#define BUZZER_PIN 12
// Servo object
Servo myServo;
// Function prototypes
void initializeComponents();
void blinkLEDsAndBuzzer(int ledPin1, int ledPin2, int times, int delayMs);
float readDistance();
void handleSerialCommands();
void handleAlarmBlinking();
void stopAlarmBlinking();
// State variables
bool isAlarmActive = false;
unsigned long lastBlinkTime = 0;
bool blinkState = false;
void setup() {
  Serial.begin(9600);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BLUE_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(GROUND_PIN_1, OUTPUT);
  pinMode(GROUND_PIN_2, OUTPUT);
  digitalWrite(GROUND_PIN_1, LOW);
  digitalWrite(GROUND_PIN_2, LOW);
  initializeComponents();
}
void loop() {
  handleSerialCommands();
  if (isAlarmActive) {
    handleAlarmBlinking();  // Blink blue LED and buzzer
  } else {
    stopAlarmBlinking();    // Ensure buzzer and LED are off
    // Read distance only when alarm is not active
    float distance = readDistance();
    Serial.println(distance, 2);
  }
  delay(50); // Adjusted delay for smooth operation
}
// ---------------------- Modules ----------------------
void initializeComponents() {
  myServo.attach(SERVO_PIN);
  myServo.write(0); // Close at 0 degrees
  blinkLEDsAndBuzzer(RED_LED_PIN, BLUE_LED_PIN, 5, 300); // Startup blink
}
void blinkLEDsAndBuzzer(int ledPin1, int ledPin2, int times, int delayMs) {
  for (int i = 0; i < times; i++) {
    if (ledPin1) digitalWrite(ledPin1, HIGH);
    if (ledPin2) digitalWrite(ledPin2, HIGH);
    tone(BUZZER_PIN, 1000);
    delay(delayMs / 2);
    if (ledPin1) digitalWrite(ledPin1, LOW);
    if (ledPin2) digitalWrite(ledPin2, LOW);
    noTone(BUZZER_PIN);
    delay(delayMs / 2);
  }
}
float readDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 25000); // Timeout after 25ms
  if (duration == 0) return 9999.99;
  return duration * 0.034 / 2;
}
void handleSerialCommands() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == '1') {
      myServo.write(180);
      isAlarmActive = true;
    } else if (cmd == '0') {
      myServo.write(0);
      isAlarmActive = false;
    } else if (cmd == '2') {
      blinkLEDsAndBuzzer(RED_LED_PIN, 0, 3, 300);
    }
  }
}
void handleAlarmBlinking() {
  unsigned long currentMillis = millis();
  if (currentMillis - lastBlinkTime >= 250) {
    lastBlinkTime = currentMillis;
    blinkState = !blinkState;
    digitalWrite(BLUE_LED_PIN, blinkState);
    if (blinkState) {
      tone(BUZZER_PIN, 1000);
    } else {
      noTone(BUZZER_PIN);
    }
  }
}
void stopAlarmBlinking() {
  digitalWrite(BLUE_LED_PIN, LOW);
  noTone(BUZZER_PIN);
  blinkState = false;
}