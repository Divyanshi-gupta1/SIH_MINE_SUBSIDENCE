/*
  Payload formatter for the existing ESP32 LoRa NODE packets.

  Call buildMlPacket() only after the MPU, HC-SR04 and DS18B20 readings have
  been obtained for the SAME node sample. Send `packet` unchanged with the
  existing LoRa transmit code. The receiver already prints its received payload
  after "Data:", which the Python bridge understands.

  P/R : MPU pitch and roll in degrees.
  V   : RMS of the high-pass / gravity-removed acceleration in g, not a raw
        accelerometer axis or an arbitrary 'vibration' number.
  E   : HC-SR04 echo pulse duration in microseconds (pulseIn result), not
        integer centimetres. This retains the sensor resolution.
  T   : DS18B20 temperature in degrees C, used by the laptop to correct sound
        speed before turning E into distance.
  GX/GY/GZ : MPU gyro degrees/second. They are safety evidence that the node
        is not being physically handled; they are not model features.
*/

#include <Arduino.h>
#include <math.h>

bool buildMlPacket(char *out, size_t outSize,
                   uint8_t nodeId,
                   float pitchDeg, float rollDeg, float vibrationRmsG,
                   unsigned long echoUs, float tempC,
                   float gxDps, float gyDps, float gzDps) {
  if (out == nullptr || outSize == 0 || nodeId == 0 || echoUs == 0 ||
      !isfinite(pitchDeg) || !isfinite(rollDeg) || !isfinite(vibrationRmsG) ||
      !isfinite(tempC) || !isfinite(gxDps) || !isfinite(gyDps) || !isfinite(gzDps) ||
      tempC < -55.0f || tempC > 125.0f || vibrationRmsG < 0.0f) {
    return false;  // Do not transmit a made-up replacement for a failed sensor.
  }

  int written = snprintf(out, outSize,
      "NODE_%u|P:%.3f|R:%.3f|V:%.5f|E:%lu|T:%.2f|GX:%.3f|GY:%.3f|GZ:%.3f",
      static_cast<unsigned>(nodeId), pitchDeg, rollDeg, vibrationRmsG, echoUs,
      tempC, gxDps, gyDps, gzDps);
  return written > 0 && static_cast<size_t>(written) < outSize;
}

/* Example integration with the existing LoRa sender:

  char packet[192];
  if (buildMlPacket(packet, sizeof(packet), NODE_ID, pitchDeg, rollDeg,
                    vibrationRmsG, echoUs, ds18TempC, gxDps, gyDps, gzDps)) {
    LoRa.beginPacket();
    LoRa.print(packet);
    LoRa.endPacket();
  }

  Do not replace a failed echo or temperature reading with 0. The receiver
  should print the packet exactly as received; RSSI/SNR may remain appended.
*/
