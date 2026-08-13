"use client";

import { VoiceChat } from "./ia-siri-chat";

// Usage demo export
export default function VoiceChatDemo() {
  return (
    <VoiceChat
      onStart={() => console.log("Voice recording started")}
      onStop={(duration) => console.log(`Voice recording stopped after ${duration}s`)}
      onVolumeChange={(volume) => console.log(`Volume: ${volume}%`)}
      demoMode={true}
    />
  );
}
