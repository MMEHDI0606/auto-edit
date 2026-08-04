import React from "react";
import type {PunchIn as PunchInProps} from "../primitiveTypes";
import {ScaleRamp} from "./ScaleRamp";

export const PunchIn: React.FC<PunchInProps & {durationInFrames: number; children: React.ReactNode}> = (
  props,
) => <ScaleRamp {...props} />;
