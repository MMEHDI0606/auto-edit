import React from "react";
import type {SlowPush as SlowPushProps} from "../primitiveTypes";
import {ScaleRamp} from "./ScaleRamp";

export const SlowPush: React.FC<SlowPushProps & {durationInFrames: number; children: React.ReactNode}> = (
  props,
) => <ScaleRamp {...props} />;
