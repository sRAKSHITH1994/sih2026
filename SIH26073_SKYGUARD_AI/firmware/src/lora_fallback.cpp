#include "lora_fallback.h"

#include <stdio.h>

#if ENABLE_LORA
#include <LoRa.h>
#include <SPI.h>
#endif

namespace { bool available=false; }

void loraFallbackBegin(){
#if ENABLE_LORA
  SPI.begin(LORA_SCK_PIN,LORA_MISO_PIN,LORA_MOSI_PIN,LORA_CS_PIN);LoRa.setPins(LORA_CS_PIN,LORA_RST_PIN,LORA_DIO0_PIN);
  available=LoRa.begin(LORA_FREQUENCY_HZ);Serial.printf("[LORA] %s\n",available?"fallback ready":"module not detected");
#else
  Serial.println("[LORA] optional fallback disabled");
#endif
}

bool loraFallbackAvailable(){return available;}

bool loraSendCritical(const SensorSnapshot& snapshot,const LocalDecision& decision){
#if ENABLE_LORA
  if(!available)return false;char message[220];snprintf(message,sizeof(message),"%s|%lu|%s|%.0f|%.2f|%.0f|%s",STATION_ID,snapshot.sequence,decision.faultType,decision.severityScore,decision.confidence,decision.failureRiskScore,decision.stationState);
  if(!LoRa.beginPacket())return false;LoRa.print(message);return LoRa.endPacket(true)==1;
#else
  (void)snapshot;(void)decision;return false;
#endif
}

bool loraSendPayload(const char* payload){
#if ENABLE_LORA
  if(!available||payload==nullptr||!payload[0])return false;
  if(!LoRa.beginPacket())return false;LoRa.print(payload);return LoRa.endPacket(true)==1;
#else
  (void)payload;return false;
#endif
}
