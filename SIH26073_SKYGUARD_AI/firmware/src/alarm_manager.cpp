#include "alarm_manager.h"

#include <string.h>

namespace { char currentState[16]="NORMAL"; }

void alarmBegin(){pinMode(GREEN_LED_PIN,OUTPUT);pinMode(YELLOW_LED_PIN,OUTPUT);pinMode(RED_LED_PIN,OUTPUT);pinMode(BUZZER_PIN,OUTPUT);digitalWrite(GREEN_LED_PIN,LOW);digitalWrite(YELLOW_LED_PIN,LOW);digitalWrite(RED_LED_PIN,LOW);digitalWrite(BUZZER_PIN,LOW);}

void alarmUpdate(const LocalDecision& decision){
  const bool critical=decision.severityScore>=75.0f||decision.failureRiskScore>=80.0f;
  const bool warning=decision.anomaly||decision.preFailureWarning;
  digitalWrite(GREEN_LED_PIN,!warning?HIGH:LOW);digitalWrite(YELLOW_LED_PIN,warning&&!critical?HIGH:LOW);digitalWrite(RED_LED_PIN,critical?HIGH:LOW);
  digitalWrite(BUZZER_PIN,critical&&((millis()/250UL)%2==0)?HIGH:LOW);
  strcpy(currentState,critical?"RED":warning?"YELLOW":"GREEN");
}

const char* alarmState(){return currentState;}
