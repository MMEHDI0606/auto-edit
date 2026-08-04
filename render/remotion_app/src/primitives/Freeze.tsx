import React from "react";
import {Freeze as RemotionFreeze} from "remotion";
import type {Freeze as FreezeProps} from "../primitiveTypes";

/**
 * Thin wrapper around Remotion's OWN built-in <Freeze> component (it ships
 * exactly this capability natively - no need to reimplement frame-holding
 * logic). `duration_f` isn't passed to Remotion's Freeze directly (it
 * takes a target frame, not a duration) - signals/effects.py::detect_freeze
 * already scopes duration_f to exactly the frozen run's length, so this
 * component's job is just "hold local frame 0 for as long as this
 * Sequence renders it," which is what freezing at frame={0} does.
 */
export const Freeze: React.FC<FreezeProps & {children: React.ReactNode}> = ({children}) => {
  return <RemotionFreeze frame={0}>{children}</RemotionFreeze>;
};
