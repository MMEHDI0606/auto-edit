import React from "react";
import {useCurrentFrame, useVideoConfig} from "remotion";
import type {CaptionKaraoke as CaptionKaraokeProps, TranscriptWord} from "../primitiveTypes";

export function findActiveWordIndex(currentTime: number, words: TranscriptWord[]): number {
  for (let i = words.length - 1; i >= 0; i--) {
    if (currentTime >= words[i].t) {
      return i;
    }
  }
  return -1;
}

export const CaptionKaraoke: React.FC<CaptionKaraokeProps> = ({transcript_words}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const currentTime = frame / fps;
  const activeIndex = findActiveWordIndex(currentTime, transcript_words);

  return (
    <span>
      {transcript_words.map((w, i) => (
        <span key={i} style={{color: i === activeIndex ? "#FFD700" : "white", marginRight: 4}}>
          {w.word}
        </span>
      ))}
    </span>
  );
};
